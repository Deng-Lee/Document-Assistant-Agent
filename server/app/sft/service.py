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


class SFTService:
    def __init__(self, trace_store: TraceStore, policy_root: str | Path | None = None):
        self.trace_store = trace_store
        self.policy_root = Path(policy_root).resolve() if policy_root is not None else None
        if self.policy_root is not None:
            self.policy_root.mkdir(parents=True, exist_ok=True)

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
                        "coach_pending_slot": sample.profile_summary.get("coach_pending_slot"),
                        "profile_summary": sample.profile_summary,
                        "gate_decision": sample.gate_decision,
                        "coach_clarify_round": sample.coach_clarify_round,
                        "allowed_evidence_ids": sample.allowed_evidence_ids,
                        "evidence_pack_selected": [_to_jsonable(item) for item in sample.evidence_pack_selected],
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
        checkpoint = self.register_policy_checkpoint(
            output_dir=output_dir,
            base_model=request.base_model or build_runtime_config().model_routing.base_model,
            dataset_manifest=manifest,
            target_row_count=target_row_count,
        )
        artifact_payload = {
            "schema_version": "local_policy_memory_v1",
            "created_at": datetime.utcnow().isoformat(),
            "policy_model_ref": checkpoint.policy_model_ref,
            "base_model": checkpoint.base_model,
            "train_path": str(train_path),
            "target_row_count": target_row_count,
            "examples": learned_examples,
        }
        self._write_json(output_dir / "policy_artifact.json", artifact_payload)
        self._register_policy_artifact(checkpoint, output_dir / "policy_artifact.json")
        if request.activate:
            self.set_active_policy_ref(checkpoint.policy_model_ref)
        return checkpoint

    def register_policy_checkpoint(
        self,
        output_dir: str | Path,
        base_model: str,
        dataset_manifest: SFTDatasetManifest,
        target_row_count: int = 0,
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
    ) -> tuple[dict[str, Any], str]:
        resolved_model = self.resolve_model_for_variant(runtime_config, variant)
        if variant != ModelVariant.POLICY:
            return baseline_output, resolved_model
        artifact = self.load_policy_artifact(resolved_model)
        if artifact is None:
            return baseline_output, resolved_model
        signature = self._signature_from_input_snapshot(input_snapshot)
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
    ) -> tuple[TraceRecord, object]:
        config = runtime_config or build_runtime_config()
        recorder = TraceRecorder(
            runtime_config_snapshot=_copy_runtime_config(config, variant),
            conversation_id=source_trace.conversation_id,
        )
        recorder.set_request_log(source_trace.request_log)
        recorder.set_retrieval_log(source_trace.retrieval_log)

        input_snapshot = self.resolve_replay_input_snapshot(source_trace, current_profile)
        replay_evidence = (
            input_snapshot.frozen_evidence_pack
            if use_frozen_evidence and input_snapshot.frozen_evidence_pack.items
            else source_trace.evidence_log
        )
        recorder.set_evidence_log(replay_evidence)

        if source_trace.request_log.task == "COACH_BJJ":
            coach_outcome = bjj_coach_service.run(
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
                runtime_config=config,
            )
            final_answer = _coerce_bjj_answer(final_output)
            validator_report = validate_bjj_answer(final_answer, {item.evidence_id for item in replay_evidence.items})
        else:
            final_answer = literary_service.run(input_snapshot.query_original, replay_evidence)
            final_output, model_ref = self.apply_policy_variant(
                variant,
                input_snapshot,
                _to_jsonable(final_answer),
                runtime_config=config,
            )
            final_answer = _coerce_literary_answer(final_output)
            validator_report = None

        recorder.set_generation_log(
            GenerationLog(
                provider=config.model_routing.provider,
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
        if snapshot is not None:
            return _copy_model(snapshot)
        retrieval_plan = trace.retrieval_log.retrieval_plan
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
        payload = row.get("input", {})
        return _signature(
            {
                "task": payload.get("task"),
                "query_original": payload.get("query_original", ""),
                "query_clean": payload.get("query_clean", ""),
                "confirmed_slots": payload.get("confirmed_slots", {}),
                "coach_clarify_round": payload.get("coach_clarify_round", 0),
                "coach_pending_slot": payload.get("coach_pending_slot"),
                "profile_version_id": payload.get("profile_summary", {}).get("profile_version_id"),
                "frozen_evidence_ids": [
                    item.get("evidence_id")
                    for item in payload.get("evidence_pack_selected", [])
                    if isinstance(item, dict) and item.get("evidence_id")
                ]
                or payload.get("allowed_evidence_ids", []),
            }
        )

    @staticmethod
    def _signature_from_input_snapshot(input_snapshot: GenerationInputSnapshot) -> str:
        return _signature(
            {
                "task": input_snapshot.task,
                "query_original": input_snapshot.query_original,
                "query_clean": input_snapshot.query_clean,
                "confirmed_slots": input_snapshot.confirmed_slots,
                "coach_clarify_round": input_snapshot.coach_clarify_round,
                "coach_pending_slot": input_snapshot.coach_pending_slot,
                "profile_version_id": input_snapshot.profile_version_id,
                "frozen_evidence_ids": [item.evidence_id for item in input_snapshot.frozen_evidence_pack.items],
            }
        )

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
