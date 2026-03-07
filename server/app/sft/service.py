from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Any

from pydantic import Field

from server.app.core import (
    ModelVariant,
    PolicyTrainRequest,
    RuntimeConfigSnapshot,
    SFTDatasetManifest,
    SFTExportRequest,
    SFTExportSample,
    TraceRecord,
    build_runtime_config,
)
from server.app.storage import TraceStore


class PolicyCheckpointRecord(SFTDatasetManifest):
    run_id: str
    checkpoint_path: str
    base_model: str
    policy_model_ref: str


class SFTService:
    def __init__(self, trace_store: TraceStore):
        self.trace_store = trace_store

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
                        "query_clean": sample.profile_summary.get("query_clean", ""),
                        "confirmed_slots": sample.confirmed_slots,
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

    def register_policy_checkpoint(
        self,
        output_dir: str | Path,
        base_model: str,
        dataset_manifest: SFTDatasetManifest,
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
        return config.model_routing.policy_model

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
        return SFTExportSample(
            trace_id=trace.trace_id,
            runtime_config_snapshot=trace.runtime_config_snapshot,
            gate_decision={
                "gate_label": reasoning_status.get("gate_label"),
                "reason_codes": reasoning_status.get("reason_codes", []),
            },
            coach_clarify_round=reasoning_status.get("coach_clarify_round", 0),
            confirmed_slots=assumptions.get("confirmed_slots", {}) if isinstance(assumptions, dict) else {},
            profile_summary={
                "profile_version_id": trace.request_log.profile_version_id,
                "query_clean": trace.retrieval_log.retrieval_plan.query_text if trace.retrieval_log.retrieval_plan else "",
            },
            allowed_evidence_ids=[item.evidence_id for item in trace.evidence_log.items],
            evidence_pack_selected=trace.evidence_log.items[:6],
            baseline_output=output if isinstance(output, dict) else {},
            target_output={},
            validator_report=trace.generation_log.validator_report,
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
