from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Any

from server.app.core import (
    BJJFullAnswer,
    BJJLowEvidenceAnswer,
    BJJAmbiguousFinalAnswer,
    GenerationInputSnapshot,
    GenerationLog,
    LiteraryFinalAnswer,
    ModelVariant,
    PolicyCheckpointRecord,
    PolicyTrainRequest,
    ProfileSummary,
    RuntimeConfigSnapshot,
    SFTDatasetManifest,
    SFTExportRequest,
    SFTExportSample,
    TraceRecord,
    build_runtime_config,
)
from server.app.agents.bjj_coach.types import BJJCoachInput
from server.app.agents.bjj_coach.validator import validate_bjj_answer
from server.app.observability import TraceRecorder, build_generation_input_snapshot, build_prompt_snapshot
from server.app.storage import TraceStore
from .inference_backend import HFLoRAQLoRAInferenceBackend, PolicyInferenceBackend, PolicyInferenceBackendError
from .prompting import build_policy_input_payload, evidence_pack_from_items
from .training_backend import HFLoRAQLoRATrainingBackend, PolicyTrainingBackend


class SFTService:
    def __init__(
        self,
        trace_store: TraceStore,
        policy_root: str | Path | None = None,
        training_backend: PolicyTrainingBackend | None = None,
        inference_backend: PolicyInferenceBackend | None = None,
    ):
        self.trace_store = trace_store
        self.policy_root = Path(policy_root).resolve() if policy_root is not None else None
        self.training_backend = training_backend or HFLoRAQLoRATrainingBackend()
        self.inference_backend = inference_backend or HFLoRAQLoRAInferenceBackend()
        if self.policy_root is not None:
            self.policy_root.mkdir(parents=True, exist_ok=True)

    def training_backend_status(self) -> dict[str, object]:
        return self.training_backend.status()

    def inference_backend_status(self) -> dict[str, object]:
        return self.inference_backend.status()

    def export_dataset(
        self,
        request: SFTExportRequest,
        output_dir: str | Path,
        trace_ids: list[str] | None = None,
    ) -> tuple[SFTDatasetManifest, list[SFTExportSample]]:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        traces = self._load_traces(trace_ids)
        samples = [self._trace_to_sample(trace) for trace in traces if self._match_trace_filter(trace, request.trace_filter)]
        manifest = SFTDatasetManifest(
            dataset_version=self._dataset_version(out_dir),
            created_at=datetime.utcnow(),
            trace_filter=request.trace_filter,
            prompt_versions=_extract_prompt_versions(samples),
            embedding_version_id=samples[0].runtime_config_snapshot.embedding_version_id if samples else build_runtime_config().embedding_version_id,
            sample_count=len(samples),
        )

        self._write_dataset_export(out_dir / "dataset_export.jsonl", samples)
        self._write_json(out_dir / "manifest.json", _to_jsonable(manifest))
        return manifest, samples

    def build_train_rows(
        self,
        samples: list[SFTExportSample],
        output_path: str | Path,
        prefer_target_output: bool = False,
    ) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for sample in samples:
                target_output = sample.target_output if prefer_target_output and sample.target_output else sample.baseline_output
                row = {
                    "trace_id": sample.trace_id,
                    "input": {
                        "task": sample.profile_summary.get("task"),
                        "query_original": sample.profile_summary.get("query_original", ""),
                        "query_clean": sample.profile_summary.get("query_clean", ""),
                        "confirmed_slots": sample.confirmed_slots,
                        "coach_clarify_round": sample.coach_clarify_round,
                        "coach_pending_slot": sample.profile_summary.get("coach_pending_slot"),
                        "profile_version_id": sample.profile_summary.get("profile_version_id"),
                        "profile_summary_snapshot": _profile_snapshot_payload(sample.profile_summary),
                        "frozen_evidence_pack": evidence_pack_from_items(sample.evidence_pack_selected),
                        "prompt_version": sample.prompt_version,
                        "prompt_hash": sample.prompt_hash,
                        "baseline_output": sample.baseline_output,
                    },
                    "target_output": target_output,
                }
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return output

    def train_policy(
        self,
        request: PolicyTrainRequest,
        dataset_manifest: SFTDatasetManifest | None = None,
    ) -> PolicyCheckpointRecord:
        train_path = Path(request.train_path).resolve()
        output_dir = Path(request.output_path).resolve()
        rows = _read_jsonl(train_path)
        if not rows:
            raise ValueError("Empty train.jsonl")
        if request.dry_run:
            raise ValueError("V1 requires a real training run; dry_run is not sufficient for policy activation")
        resolved_request = _copy_model(request)
        resolved_request.base_model = request.base_model or build_runtime_config().model_routing.base_model

        learned_examples: dict[str, dict[str, Any]] = {}
        target_row_count = 0
        for row in rows:
            target_output = row.get("target_output")
            if not isinstance(target_output, dict) or not target_output:
                raise ValueError("Each training row must contain a non-empty target_output")
            signature = self._signature_from_train_row(row)
            learned_examples[signature] = {
                "trace_id": row.get("trace_id"),
                "task": row.get("input", {}).get("task"),
                "target_output": target_output,
            }
            target_row_count += 1

        manifest = dataset_manifest or self._load_or_build_manifest(train_path, len(rows))
        training_artifact = self.training_backend.run(resolved_request)
        checkpoint = self.register_policy_checkpoint(
            output_dir=output_dir,
            base_model=resolved_request.base_model or build_runtime_config().model_routing.base_model,
            dataset_manifest=manifest,
            target_row_count=target_row_count,
            training_backend=training_artifact.backend_name,
        )
        artifact_payload = {
            "schema_version": training_artifact.schema_version,
            "created_at": datetime.utcnow().isoformat(),
            "policy_model_ref": checkpoint.policy_model_ref,
            "base_model": checkpoint.base_model,
            "train_path": str(train_path),
            "target_row_count": target_row_count,
            "training_backend": training_artifact.backend_name,
            "training_config": {
                "epochs": resolved_request.epochs,
                "learning_rate": resolved_request.learning_rate,
                "batch_size": resolved_request.batch_size,
                "max_seq_len": resolved_request.max_seq_len,
                "lora_r": resolved_request.lora_r,
                "lora_alpha": resolved_request.lora_alpha,
                "lora_dropout": resolved_request.lora_dropout,
                "lora_targets": list(resolved_request.lora_targets),
                "load_in_4bit": resolved_request.load_in_4bit,
            },
            "adapter_path": training_artifact.adapter_path,
            "tokenizer_path": training_artifact.tokenizer_path,
            "training_summary_path": training_artifact.training_summary_path,
            "training_metadata": _to_jsonable(training_artifact.metadata),
            "examples": learned_examples,
        }
        self._write_json(output_dir / "policy_artifact.json", artifact_payload)
        self._register_policy_artifact(checkpoint, output_dir / "policy_artifact.json")
        if resolved_request.activate:
            self.set_active_policy_ref(checkpoint.policy_model_ref)
        return checkpoint

    def register_policy_checkpoint(
        self,
        output_dir: str | Path,
        base_model: str,
        dataset_manifest: SFTDatasetManifest,
        target_row_count: int = 0,
        training_backend: str = "hf_lora_qlora_v1",
    ) -> PolicyCheckpointRecord:
        checkpoint_dir = Path(output_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        run_id = f"policy_{sha1(f'{checkpoint_dir}:{datetime.utcnow().isoformat()}'.encode('utf-8')).hexdigest()[:12]}"
        record = PolicyCheckpointRecord(
            run_id=run_id,
            dataset_version=dataset_manifest.dataset_version,
            created_at=datetime.utcnow(),
            trace_filter=dataset_manifest.trace_filter,
            prompt_versions=dataset_manifest.prompt_versions,
            embedding_version_id=dataset_manifest.embedding_version_id,
            sample_count=dataset_manifest.sample_count,
            checkpoint_path=str(checkpoint_dir),
            base_model=base_model,
            policy_model_ref=f"policy://{run_id}",
            training_backend=training_backend,
            target_row_count=target_row_count,
        )
        self._write_json(checkpoint_dir / "checkpoint_manifest.json", _to_jsonable(record))
        return record

    def build_policy_train_request(
        self,
        train_path: str | Path,
        output_path: str | Path,
        dry_run: bool = True,
    ) -> PolicyTrainRequest:
        return PolicyTrainRequest(
            train_path=str(Path(train_path)),
            output_path=str(Path(output_path)),
            base_model=build_runtime_config().model_routing.base_model,
            model_variant=ModelVariant.POLICY,
            dry_run=dry_run,
        )

    def resolve_model_for_variant(
        self,
        runtime_config: RuntimeConfigSnapshot | None,
        variant: ModelVariant,
        policy_checkpoint: PolicyCheckpointRecord | None = None,
    ) -> str:
        config = runtime_config or build_runtime_config()
        if variant == ModelVariant.BASE:
            return config.model_routing.base_model
        if policy_checkpoint is not None:
            return policy_checkpoint.policy_model_ref
        active_policy_ref = self.get_active_policy_ref()
        if active_policy_ref is not None:
            return active_policy_ref
        return config.model_routing.policy_model

    def get_active_policy_ref(self) -> str | None:
        if self.policy_root is None:
            return None
        active_path = self.policy_root / "active_policy_ref.txt"
        if not active_path.exists():
            return None
        value = active_path.read_text(encoding="utf-8").strip()
        return value or None

    def set_active_policy_ref(self, policy_model_ref: str) -> None:
        if self.policy_root is None:
            return
        (self.policy_root / "active_policy_ref.txt").write_text(policy_model_ref + "\n", encoding="utf-8")

    def load_policy_checkpoint(self, policy_model_ref: str | None = None) -> PolicyCheckpointRecord | None:
        if self.policy_root is None:
            return None
        registry = self._read_registry()
        resolved_ref = policy_model_ref or self.get_active_policy_ref()
        if not resolved_ref:
            return None
        metadata = registry.get(resolved_ref)
        if metadata is None:
            return None
        manifest_path = Path(metadata["checkpoint_manifest_path"])
        if not manifest_path.exists():
            return None
        return PolicyCheckpointRecord(**json.loads(manifest_path.read_text(encoding="utf-8")))

    def load_policy_artifact(self, policy_model_ref: str | None = None) -> dict[str, Any] | None:
        if self.policy_root is None:
            return None
        registry = self._read_registry()
        resolved_ref = policy_model_ref or self.get_active_policy_ref()
        if not resolved_ref:
            return None
        metadata = registry.get(resolved_ref)
        if metadata is None:
            return None
        artifact_path = Path(metadata["artifact_path"])
        if not artifact_path.exists():
            return None
        return json.loads(artifact_path.read_text(encoding="utf-8"))

    def apply_policy_variant(
        self,
        variant: ModelVariant,
        input_snapshot: GenerationInputSnapshot,
        baseline_output: dict[str, Any],
        runtime_config: RuntimeConfigSnapshot | None = None,
        prompt_version: str | None = None,
        prompt_hash: str | None = None,
        policy_input_output: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str]:
        resolved_model = self.resolve_model_for_variant(runtime_config, variant)
        if variant != ModelVariant.POLICY:
            return baseline_output, resolved_model
        artifact = self.load_policy_artifact(resolved_model)
        if artifact is None:
            return baseline_output, resolved_model
        input_payload = build_policy_input_payload(
            input_snapshot=input_snapshot,
            baseline_output=policy_input_output or baseline_output,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
        )
        try:
            generation_limits = runtime_config.generation if runtime_config is not None else None
            task_key = "literary" if input_snapshot.task == "COACH_LITERARY" else "bjj"
            max_new_tokens = int(generation_limits.__getattribute__(task_key).get("max_tokens", 1024)) if generation_limits is not None else 1024
            result = self.inference_backend.generate(
                artifact=artifact,
                input_payload=input_payload,
                max_new_tokens=max_new_tokens,
            )
            return result.output, resolved_model
        except PolicyInferenceBackendError:
            signature = self._signature_from_policy_input(input_payload)
            learned = artifact.get("examples", {}).get(signature)
            if learned is None:
                return baseline_output, resolved_model
            output = learned.get("target_output")
            if not isinstance(output, dict) or not output:
                return baseline_output, resolved_model
            return output, resolved_model

    def replay_trace(
        self,
        source_trace: TraceRecord,
        variant: ModelVariant,
        runtime_config: RuntimeConfigSnapshot | None,
        current_profile: ProfileSummary,
        bjj_coach_service,
        literary_service,
        use_frozen_evidence: bool = True,
        override_generation_config: dict[str, Any] | None = None,
    ) -> tuple[TraceRecord, object]:
        config = runtime_config or build_runtime_config()
        effective_config = _apply_generation_overrides(config, override_generation_config)
        recorder = TraceRecorder(
            runtime_config_snapshot=_copy_runtime_config(effective_config, variant),
            conversation_id=source_trace.conversation_id,
        )
        request_log = _copy_model(source_trace.request_log)
        request_log.override_generation_config = _to_jsonable(override_generation_config or {})
        recorder.set_request_log(request_log)
        recorder.set_retrieval_log(source_trace.retrieval_log)
        if request_log.override_generation_config:
            recorder.add_event(
                "replay.override_applied",
                override_generation_config=request_log.override_generation_config,
                use_frozen_evidence=use_frozen_evidence,
            )

        input_snapshot = self.resolve_replay_input_snapshot(source_trace, current_profile)
        replay_evidence = (
            input_snapshot.frozen_evidence_pack
            if use_frozen_evidence and input_snapshot.frozen_evidence_pack.items
            else source_trace.evidence_log
        )
        recorder.set_evidence_log(replay_evidence)
        bjj_runtime_service = _with_runtime_config(bjj_coach_service, effective_config)
        literary_runtime_service = _with_runtime_config(
            literary_service,
            effective_config,
            document_repository=getattr(literary_service, "document_repository", None),
        )

        if source_trace.request_log.task == "COACH_BJJ":
            coach_outcome = bjj_runtime_service.run(
                BJJCoachInput(
                    query_original=input_snapshot.query_original,
                    query_clean=input_snapshot.query_clean,
                    confirmed_slots=input_snapshot.confirmed_slots,
                    coach_clarify_round=input_snapshot.coach_clarify_round,
                    coach_pending_slot=input_snapshot.coach_pending_slot,
                    profile_summary=input_snapshot.profile_summary_snapshot or current_profile,
                ),
                evidence_pack=replay_evidence,
            )
            baseline_output = _to_jsonable(coach_outcome.final_answer) if coach_outcome.final_answer is not None else source_trace.generation_log.output
            final_output, model_ref = self.apply_policy_variant(
                variant,
                input_snapshot,
                baseline_output,
                runtime_config=effective_config,
                prompt_version=source_trace.generation_log.prompt_version,
                prompt_hash=source_trace.generation_log.prompt_hash,
                policy_input_output=source_trace.generation_log.output or baseline_output,
            )
            final_answer = _coerce_bjj_answer(final_output)
            validator_report = validate_bjj_answer(final_answer, {item.evidence_id for item in replay_evidence.items})
        else:
            final_answer = literary_runtime_service.run(input_snapshot.query_original, replay_evidence)
            final_output, model_ref = self.apply_policy_variant(
                variant,
                input_snapshot,
                _to_jsonable(final_answer),
                runtime_config=effective_config,
                prompt_version=source_trace.generation_log.prompt_version,
                prompt_hash=source_trace.generation_log.prompt_hash,
                policy_input_output=source_trace.generation_log.output or _to_jsonable(final_answer),
            )
            final_answer = _coerce_literary_answer(final_output)
            validator_report = None

        recorder.set_generation_log(
            GenerationLog(
                provider=effective_config.model_routing.provider,
                model=model_ref,
                prompt_version=source_trace.generation_log.prompt_version,
                prompt_snapshot=build_prompt_snapshot(input_snapshot),
                input_snapshot=input_snapshot,
                output=_to_jsonable(final_answer),
                validator_report=validator_report,
            )
        )
        recorder.persist(self.trace_store)
        return self.trace_store.read_trace(recorder.trace_id), final_answer

    def replay_eval_traces(
        self,
        traces: list[TraceRecord],
        variant: ModelVariant,
        runtime_config: RuntimeConfigSnapshot | None,
        current_profile: ProfileSummary,
        bjj_coach_service,
        literary_service,
        use_frozen_evidence: bool = True,
    ) -> list[TraceRecord]:
        replayed: list[TraceRecord] = []
        for trace in traces:
            replayed_trace, _final_answer = self.replay_trace(
                source_trace=trace,
                variant=variant,
                runtime_config=runtime_config,
                current_profile=current_profile,
                bjj_coach_service=bjj_coach_service,
                literary_service=literary_service,
                use_frozen_evidence=use_frozen_evidence,
            )
            replayed.append(replayed_trace)
        return replayed

    def resolve_replay_input_snapshot(
        self,
        trace: TraceRecord,
        fallback_profile: ProfileSummary,
    ) -> GenerationInputSnapshot:
        snapshot = trace.generation_log.input_snapshot
        retrieval_plan = trace.retrieval_log.retrieval_plan
        if snapshot is not None:
            hydrated = _copy_model(snapshot)
            if not hydrated.query_original and retrieval_plan is not None:
                hydrated.query_original = retrieval_plan.query_original
            if not hydrated.query_clean and retrieval_plan is not None:
                hydrated.query_clean = retrieval_plan.query_text
            if hydrated.profile_summary_snapshot is None:
                hydrated.profile_summary_snapshot = ProfileSummary(
                    profile_version_id=hydrated.profile_version_id or trace.request_log.profile_version_id or fallback_profile.profile_version_id,
                    ruleset_default=fallback_profile.ruleset_default,
                    injuries=_copy_model(fallback_profile.injuries),
                    forbidden_actions=_copy_model(fallback_profile.forbidden_actions),
                    preferences=_copy_model(fallback_profile.preferences),
                )
            if not hydrated.profile_version_id and hydrated.profile_summary_snapshot is not None:
                hydrated.profile_version_id = hydrated.profile_summary_snapshot.profile_version_id
            if not hydrated.frozen_evidence_pack.items:
                hydrated.frozen_evidence_pack = _copy_model(trace.evidence_log)
            return hydrated
        return build_generation_input_snapshot(
            task=trace.request_log.task,
            query_original=retrieval_plan.query_original if retrieval_plan is not None else "",
            query_clean=retrieval_plan.query_text if retrieval_plan is not None else "",
            confirmed_slots=trace.request_log.confirmed_slots,
            coach_clarify_round=0,
            coach_pending_slot=None,
            profile_summary=ProfileSummary(
                profile_version_id=trace.request_log.profile_version_id or fallback_profile.profile_version_id,
                ruleset_default=fallback_profile.ruleset_default,
                injuries=_copy_model(fallback_profile.injuries),
                forbidden_actions=_copy_model(fallback_profile.forbidden_actions),
                preferences=_copy_model(fallback_profile.preferences),
            ),
            frozen_evidence_pack=_copy_model(trace.evidence_log),
        )

    def _load_traces(self, trace_ids: list[str] | None = None) -> list[TraceRecord]:
        ids = trace_ids or self.trace_store.list_trace_ids()
        return [self.trace_store.read_trace(trace_id) for trace_id in ids]

    @staticmethod
    def _match_trace_filter(trace: TraceRecord, trace_filter: dict[str, Any]) -> bool:
        if not trace_filter:
            return True
        domain = trace_filter.get("domain")
        if domain and trace.request_log.domain != domain:
            return False
        validator_fail_only = trace_filter.get("validator_fail_only")
        if validator_fail_only and (trace.generation_log.validator_report is None or trace.generation_log.validator_report.validator_pass):
            return False
        gate_label = trace_filter.get("gate_label")
        output = trace.generation_log.output or {}
        if gate_label and output.get("reasoning_status", {}).get("gate_label") != gate_label:
            return False
        return True

    @staticmethod
    def _trace_to_sample(trace: TraceRecord) -> SFTExportSample:
        output = trace.generation_log.output or {}
        reasoning_status = output.get("reasoning_status", {}) if isinstance(output, dict) else {}
        assumptions = output.get("assumptions", {}) if isinstance(output, dict) else {}
        input_snapshot = trace.generation_log.input_snapshot
        frozen_input = input_snapshot or build_generation_input_snapshot(
            task=trace.request_log.task,
            query_original=trace.retrieval_log.retrieval_plan.query_original if trace.retrieval_log.retrieval_plan else "",
            query_clean=trace.retrieval_log.retrieval_plan.query_text if trace.retrieval_log.retrieval_plan else "",
            confirmed_slots=trace.request_log.confirmed_slots,
            coach_clarify_round=reasoning_status.get("coach_clarify_round", 0),
            coach_pending_slot=None,
            profile_summary=ProfileSummary(profile_version_id=trace.request_log.profile_version_id or "profile_default"),
            frozen_evidence_pack=trace.evidence_log,
        )
        return SFTExportSample(
            trace_id=trace.trace_id,
            runtime_config_snapshot=trace.runtime_config_snapshot,
            prompt_version=trace.generation_log.prompt_version,
            prompt_hash=trace.generation_log.prompt_hash,
            gate_decision={
                "gate_label": reasoning_status.get("gate_label"),
                "reason_codes": reasoning_status.get("reason_codes", []),
            },
            coach_clarify_round=frozen_input.coach_clarify_round,
            confirmed_slots=frozen_input.confirmed_slots
            or (assumptions.get("confirmed_slots", {}) if isinstance(assumptions, dict) else {}),
            profile_summary={
                "task": frozen_input.task,
                "profile_version_id": frozen_input.profile_version_id or trace.request_log.profile_version_id,
                "query_original": frozen_input.query_original,
                "query_clean": frozen_input.query_clean,
                "coach_pending_slot": frozen_input.coach_pending_slot,
                **(
                    _to_jsonable(frozen_input.profile_summary_snapshot)
                    if frozen_input.profile_summary_snapshot is not None
                    else {}
                ),
            },
            allowed_evidence_ids=[item.evidence_id for item in frozen_input.frozen_evidence_pack.items] or [item.evidence_id for item in trace.evidence_log.items],
            evidence_pack_selected=(frozen_input.frozen_evidence_pack.items or trace.evidence_log.items)[:6],
            baseline_output=output if isinstance(output, dict) else {},
            target_output={},
            validator_report=trace.generation_log.validator_report,
        )

    def _load_or_build_manifest(self, train_path: Path, sample_count: int) -> SFTDatasetManifest:
        manifest_path = train_path.parent / "manifest.json"
        if manifest_path.exists():
            return SFTDatasetManifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
        runtime = build_runtime_config()
        return SFTDatasetManifest(
            dataset_version=self._dataset_version(train_path.parent),
            created_at=datetime.utcnow(),
            prompt_versions=_to_jsonable(runtime.prompt_versions),
            embedding_version_id=runtime.embedding_version_id,
            sample_count=sample_count,
        )

    def _register_policy_artifact(self, checkpoint: PolicyCheckpointRecord, artifact_path: Path) -> None:
        if self.policy_root is None:
            return
        registry = self._read_registry()
        registry[checkpoint.policy_model_ref] = {
            "checkpoint_manifest_path": str(Path(checkpoint.checkpoint_path) / "checkpoint_manifest.json"),
            "artifact_path": str(artifact_path),
        }
        self._write_json(self.policy_root / "registry.json", registry)

    def _read_registry(self) -> dict[str, dict[str, str]]:
        if self.policy_root is None:
            return {}
        registry_path = self.policy_root / "registry.json"
        if not registry_path.exists():
            return {}
        return json.loads(registry_path.read_text(encoding="utf-8"))

    @staticmethod
    def _signature_from_train_row(row: dict[str, Any]) -> str:
        return _signature(row.get("input", {}))

    @staticmethod
    def _signature_from_input_snapshot(input_snapshot: GenerationInputSnapshot) -> str:
        return _signature(
            build_policy_input_payload(
                input_snapshot=input_snapshot,
                baseline_output={},
            )
        )

    @staticmethod
    def _signature_from_policy_input(input_payload: dict[str, Any]) -> str:
        return _signature(input_payload)

    @staticmethod
    def _dataset_version(output_dir: Path) -> str:
        parent = output_dir.name
        return parent if parent else datetime.utcnow().strftime("%Y%m%d")

    @staticmethod
    def _write_dataset_export(path: Path, samples: list[SFTExportSample]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for sample in samples:
                handle.write(json.dumps(_to_jsonable(sample), ensure_ascii=False) + "\n")

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _extract_prompt_versions(samples: list[SFTExportSample]) -> dict[str, str]:
    if not samples:
        runtime = build_runtime_config()
        prompt_versions = runtime.prompt_versions
        return _to_jsonable(prompt_versions)
    return _to_jsonable(samples[0].runtime_config_snapshot.prompt_versions)


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return {k: _to_jsonable(v) for k, v in value.model_dump(by_alias=True).items()}
    if hasattr(value, "dict"):
        return {k: _to_jsonable(v) for k, v in value.dict(by_alias=True).items()}
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            pass
    return value


def _signature(payload: dict[str, Any]) -> str:
    return sha1(json.dumps(_to_jsonable(payload), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _copy_runtime_config(runtime_config: RuntimeConfigSnapshot, variant: ModelVariant) -> RuntimeConfigSnapshot:
    if hasattr(runtime_config, "model_copy"):
        return runtime_config.model_copy(update={"policy_version": variant}, deep=True)
    return runtime_config.copy(update={"policy_version": variant}, deep=True)


def _apply_generation_overrides(
    runtime_config: RuntimeConfigSnapshot,
    override_generation_config: dict[str, Any] | None,
) -> RuntimeConfigSnapshot:
    overrides = override_generation_config or {}
    if not overrides:
        return _copy_model(runtime_config)
    generation = _copy_model(runtime_config.generation)
    for task_name in ("bjj", "literary", "replan", "safe_summary"):
        task_override = overrides.get(task_name)
        if not isinstance(task_override, dict):
            continue
        current = getattr(generation, task_name)
        setattr(generation, task_name, {**dict(current), **task_override})
    if hasattr(runtime_config, "model_copy"):
        return runtime_config.model_copy(update={"generation": generation}, deep=True)
    return runtime_config.copy(update={"generation": generation}, deep=True)


def _with_runtime_config(service, runtime_config: RuntimeConfigSnapshot, **extra_kwargs):
    init_kwargs = {"runtime_config": runtime_config, **extra_kwargs}
    try:
        return service.__class__(**init_kwargs)
    except TypeError:
        return service


def _copy_model(model):
    if hasattr(model, "model_copy"):
        return model.model_copy(deep=True)
    if hasattr(model, "copy"):
        try:
            return model.copy(deep=True)
        except TypeError:
            return model.copy()
    return model


def _coerce_bjj_answer(payload: dict[str, Any]):
    mode = payload.get("mode")
    if mode == "FULL":
        return BJJFullAnswer(**payload)
    if mode == "AMBIGUOUS_FINAL":
        return BJJAmbiguousFinalAnswer(**payload)
    return BJJLowEvidenceAnswer(**payload)


def _coerce_literary_answer(payload: dict[str, Any]):
    return LiteraryFinalAnswer(**payload)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _profile_snapshot_payload(profile_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_version_id": profile_summary.get("profile_version_id"),
        "ruleset_default": profile_summary.get("ruleset_default", "Gi"),
        "injuries": profile_summary.get("injuries", []),
        "forbidden_actions": profile_summary.get("forbidden_actions", []),
        "preferences": profile_summary.get("preferences", []),
    }
