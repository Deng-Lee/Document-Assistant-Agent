from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .base import PDABaseModel
from .bjj import BJJValidatorReport
from .evidence import EvidencePack
from .profile import ProfileSummary
from .retrieval import ExecutionPlan, PlanCheck, ProbeStats, RetrievalPlan
from .runtime_config import RuntimeConfigSnapshot


class TraceSpan(PDABaseModel):
    name: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)


class TraceEvent(PDABaseModel):
    name: str
    timestamp: datetime
    attributes: dict[str, Any] = Field(default_factory=dict)


class RequestLog(PDABaseModel):
    entrypoint: str
    domain: str | None = None
    task: str | None = None
    profile_version_id: str | None = None
    confirmed_slots: dict[str, str] = Field(default_factory=dict)
    plan_check: PlanCheck | None = None
    execution_plan: ExecutionPlan | None = None
    stage_transitions: list[str] = Field(default_factory=list)


class RetrievalLog(PDABaseModel):
    retrieval_plan: RetrievalPlan | None = None
    probe_stats: ProbeStats | None = None
    structured_filter_count: int = Field(default=0, ge=0)
    bm25_count: int = Field(default=0, ge=0)
    dense_count: int = Field(default=0, ge=0)
    rerank_applied: bool = False
    rerank_status: str = "disabled"
    rerank_provider_name: str | None = None
    rerank_model: str | None = None
    rerank_candidate_count: int = Field(default=0, ge=0)
    discarded_after_filter: int = Field(default=0, ge=0)
    notes: list[str] = Field(default_factory=list)


class GenerationInputSnapshot(PDABaseModel):
    task: str | None = None
    query_original: str = ""
    query_clean: str = ""
    confirmed_slots: dict[str, str] = Field(default_factory=dict)
    coach_clarify_round: int = Field(default=0, ge=0)
    coach_pending_slot: str | None = None
    profile_summary_snapshot: ProfileSummary | None = None
    profile_version_id: str | None = None
    frozen_evidence_pack: EvidencePack = Field(default_factory=EvidencePack)


class PromptSnapshot(PDABaseModel):
    task: str | None = None
    query_original_hash: str | None = None
    query_clean_hash: str | None = None
    confirmed_slot_keys: list[str] = Field(default_factory=list)
    coach_clarify_round: int = Field(default=0, ge=0)
    coach_pending_slot: str | None = None
    profile_version_id: str | None = None
    evidence_item_count: int = Field(default=0, ge=0)
    query_original_preview: str | None = None
    query_clean_preview: str | None = None
    confirmed_slots_snapshot: dict[str, str] = Field(default_factory=dict)
    frozen_evidence_ids: list[str] = Field(default_factory=list)


class GenerationLog(PDABaseModel):
    provider: str
    model: str
    prompt_version: str
    prompt_hash: str | None = None
    prompt_snapshot: PromptSnapshot | None = None
    input_snapshot: GenerationInputSnapshot | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    token_usage: dict[str, int] = Field(default_factory=dict)
    cost_estimate: float | None = Field(default=None, ge=0.0)
    output: dict[str, Any] = Field(default_factory=dict)
    validator_report: BJJValidatorReport | None = None


class TraceRecord(PDABaseModel):
    trace_id: str
    conversation_id: str | None = None
    runtime_config_snapshot: RuntimeConfigSnapshot
    request_log: RequestLog
    retrieval_log: RetrievalLog
    evidence_log: EvidencePack
    generation_log: GenerationLog
    spans: list[TraceSpan] = Field(default_factory=list)
    events: list[TraceEvent] = Field(default_factory=list)
