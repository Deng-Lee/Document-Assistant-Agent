from __future__ import annotations

from typing import Any

from .bjj import BJJValidatorReport, BJJAmbiguousFinalAnswer, BJJFullAnswer, BJJLowEvidenceAnswer
from .chat import ChatClarifyTurnResponse, ChatFinalTurnResponse, ClarifyRequest, LiteraryFinalAnswer
from .documents import BJJRecordFields, ChunkRecord, DocVersionRecord, DocumentRecord
from .evaluation import EvalRunRequest, EvalRunResult, GoldenCase, ManualRubricEntry, ManualRubricScore
from .evidence import EvidencePack, EvidencePackItem
from .jobs import JobRecord, JobRunResult
from .profile import ProfileSummary
from .retrieval import ExecutionPlan, PlanCheck, ProbeStats, RetrievalPlan
from .runtime_config import RuntimeConfigSnapshot
from .sft import PolicyCheckpointRecord, PolicyTrainRequest, SFTDatasetManifest, SFTExportRequest, SFTExportSample
from .tracing import TraceRecord


SCHEMA_MODELS = {
    "runtime_config_snapshot": RuntimeConfigSnapshot,
    "document_record": DocumentRecord,
    "doc_version_record": DocVersionRecord,
    "bjj_record_fields": BJJRecordFields,
    "chunk_record": ChunkRecord,
    "retrieval_plan": RetrievalPlan,
    "probe_stats": ProbeStats,
    "plan_check": PlanCheck,
    "execution_plan": ExecutionPlan,
    "evidence_pack_item": EvidencePackItem,
    "evidence_pack": EvidencePack,
    "clarify_request": ClarifyRequest,
    "chat_clarify_turn_response": ChatClarifyTurnResponse,
    "chat_final_turn_response": ChatFinalTurnResponse,
    "bjj_full_answer": BJJFullAnswer,
    "bjj_ambiguous_final_answer": BJJAmbiguousFinalAnswer,
    "bjj_low_evidence_answer": BJJLowEvidenceAnswer,
    "bjj_validator_report": BJJValidatorReport,
    "literary_final_answer": LiteraryFinalAnswer,
    "trace_record": TraceRecord,
    "job_record": JobRecord,
    "job_run_result": JobRunResult,
    "golden_case": GoldenCase,
    "eval_run_request": EvalRunRequest,
    "eval_run_result": EvalRunResult,
    "manual_rubric_score": ManualRubricScore,
    "manual_rubric_entry": ManualRubricEntry,
    "profile_summary": ProfileSummary,
    "sft_export_request": SFTExportRequest,
    "sft_export_sample": SFTExportSample,
    "sft_dataset_manifest": SFTDatasetManifest,
    "policy_checkpoint_record": PolicyCheckpointRecord,
    "policy_train_request": PolicyTrainRequest,
}


def _model_schema(model: type) -> dict[str, Any]:
    if hasattr(model, "model_json_schema"):
        return model.model_json_schema()
    return model.schema()


def export_contract_schemas() -> dict[str, dict[str, Any]]:
    return {name: _model_schema(model) for name, model in SCHEMA_MODELS.items()}
