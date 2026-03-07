from __future__ import annotations

from typing import Any

from pydantic import Field

from server.app.core import EvidencePack, JobRecord, PDABaseModel, ProbeStats, RetrievalLog
from server.app.orchestrator import ConversationState


class HealthResponse(PDABaseModel):
    status: str


class IngestTextResponse(PDABaseModel):
    doc_id: str
    doc_version_id: str
    chunk_ids: list[str] = Field(default_factory=list)
    jobs: list[JobRecord] = Field(default_factory=list)


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
    result: dict[str, Any] | None = None
