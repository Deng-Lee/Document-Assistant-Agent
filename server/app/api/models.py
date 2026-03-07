from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from server.app.core import PDABaseModel, RetrievalFilters, SFTExportRequest


class ChatTurnRequest(PDABaseModel):
    conversation_id: str | None = None
    user_message: str
    client_context: dict[str, Any] = Field(default_factory=dict)


class RetrieveRequest(PDABaseModel):
    mode: str = "full"
    query_text: str
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    k: int | None = None
    trace_id: str | None = None


class ReplayRequest(PDABaseModel):
    model_variant: str = "base"
    use_frozen_evidence: bool = True
    override_generation_config: dict[str, Any] = Field(default_factory=dict)


class NotesRecordRequest(PDABaseModel):
    notes_text: str
    doc_id: str | None = None


class BJJRecordRequest(PDABaseModel):
    bjj_markdown: str
    doc_id: str | None = None


class IngestTextRequest(PDABaseModel):
    markdown_text: str
    source_path_hint: str | None = None
    doc_id: str | None = None


class EvalRunAPIRequest(PDABaseModel):
    eval_set_id: str
    model_variant: str = "base"
    use_frozen_evidence: bool = True
    trace_ids: list[str] = Field(default_factory=list)


class ProfilePatchRequest(PDABaseModel):
    ruleset_default: str | None = None
    injuries: list[dict[str, str]] = Field(default_factory=list)
    forbidden_actions: list[dict[str, str]] = Field(default_factory=list)
    preferences: list[dict[str, str]] = Field(default_factory=list)


class RunJobsRequest(PDABaseModel):
    job_types: list[str] = Field(default_factory=list)
