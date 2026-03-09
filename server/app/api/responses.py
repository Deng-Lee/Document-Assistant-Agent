from __future__ import annotations

from typing import Any

from pydantic import Field

from server.app.core import (
    BJJAnswerType,
    EvalRunResult,
    JobRecord,
    JobRunResult,
    LiteraryFinalAnswer,
    PDABaseModel,
    PolicyCheckpointRecord,
    ProbeStats,
    ProfileSummary,
    RetrievalLog,
    SFTDatasetManifest,
    TraceRecord,
)
from server.app.core import EvidencePack
from server.app.orchestrator import ConversationState


class HealthResponse(PDABaseModel):
    status: str


class IngestArtifactResponse(PDABaseModel):
    source_path: str | None = None
    doc_id: str
    doc_version_id: str
    chunk_ids: list[str] = Field(default_factory=list)
    jobs: list[JobRecord] = Field(default_factory=list)


class IngestTextResponse(IngestArtifactResponse):
    pass


class IngestFileResponse(IngestArtifactResponse):
    pass


class IngestDirectoryResponse(PDABaseModel):
    root_path: str
    recursive: bool
    imported_count: int
    results: list[IngestArtifactResponse] = Field(default_factory=list)


class RecordBJJResponse(PDABaseModel):
    doc_id: str
    doc_version_id: str
    chunk_id: str | None = None
    jobs: list[JobRecord] = Field(default_factory=list)


class RecordNotesResponse(PDABaseModel):
    doc_id: str
    doc_version_id: str
    chunk_ids: list[str] = Field(default_factory=list)
    jobs: list[JobRecord] = Field(default_factory=list)


class RetrieveResponse(PDABaseModel):
    trace_id: str | None = None
    probe_stats: ProbeStats | None = None
    retrieval_log: RetrievalLog
    evidence_pack: EvidencePack


class ChatConversationResponse(PDABaseModel):
    turns: list[dict[str, Any]] = Field(default_factory=list)
    last_state: ConversationState


class JobsListResponse(PDABaseModel):
    jobs: list[JobRecord] = Field(default_factory=list)


class RunJobResponse(PDABaseModel):
    result: JobRunResult | None = None


class TraceSummaryItem(PDABaseModel):
    trace_id: str
    created_at: str | None = None
    domain: str | None = None
    task: str | None = None
    gate_label: str | None = None
    latency: int | None = None
    cost: float | None = None
    validator_pass: bool | None = None


class TracesListResponse(PDABaseModel):
    traces: list[TraceSummaryItem] = Field(default_factory=list)


class ReplayTraceResponse(PDABaseModel):
    trace_id: str
    final_answer: BJJAnswerType | LiteraryFinalAnswer


class EvalRunLaunchResponse(PDABaseModel):
    eval_run_id: str


class EvalResultsResponse(PDABaseModel):
    runs: list[EvalRunResult] = Field(default_factory=list)


class SFTExportResponse(PDABaseModel):
    export_path: str
    manifest: SFTDatasetManifest


class SFTTrainResponse(PDABaseModel):
    checkpoint: PolicyCheckpointRecord
    active_policy_ref: str | None = None


class ProfileResponse(ProfileSummary):
    pass


class ProfileHistoryResponse(PDABaseModel):
    profiles: list[ProfileSummary] = Field(default_factory=list)
