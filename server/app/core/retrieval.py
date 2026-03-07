from __future__ import annotations

from datetime import date

from pydantic import Field

from .base import PDABaseModel
from .documents import ChunkMetadataDigest
from .enums import ClarifySlot, DomainType, DocumentType, NextAction, TaskType
from .evidence import RankSignals


class DateRange(PDABaseModel):
    start: date | None = None
    end: date | None = None
    expression: str | None = None


class RetrievalFilters(PDABaseModel):
    doc_type: DocumentType | None = None
    date_range: DateRange | None = None
    position: str | None = None
    orientation: str | None = None
    distance: str | None = None
    goal: str | None = None
    opponent_control: str | None = None
    heading_hints: list[str] = Field(default_factory=list)


class RetrievalPlan(PDABaseModel):
    doc_type: str = "ALL"
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    query_original: str
    query_text: str
    top_k: int = Field(default=12, ge=1)
    per_doc_limit: int = Field(default=3, ge=1)
    token_budget: int = Field(default=4000, ge=1)


class ProbeHit(PDABaseModel):
    chunk_id: str
    doc_type: DocumentType
    doc_version_id: str
    metadata_digest: ChunkMetadataDigest
    safe_summary: str
    ranks: RankSignals


class EvidenceStrength(PDABaseModel):
    value: float = Field(..., ge=0.0, le=1.0)
    headness: float = Field(..., ge=0.0, le=1.0)
    coherence: float = Field(..., ge=0.0, le=1.0)


class TimeSignal(PDABaseModel):
    value: bool = False
    date_range: DateRange | None = None


class ProbeStats(PDABaseModel):
    k: int = Field(..., ge=0)
    probe_query_text: str
    probe_filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    hits: list[ProbeHit] = Field(default_factory=list)
    doc_type_hist: dict[str, float] = Field(default_factory=dict)
    slot_value_hist: dict[str, dict[str, int]] = Field(default_factory=dict)
    slot_entropy: float = Field(..., ge=0.0, le=1.0)
    evidence_strength: EvidenceStrength
    time_signal: TimeSignal = Field(default_factory=TimeSignal)


class PlanCheck(PDABaseModel):
    domain: DomainType
    task_hint: TaskType
    need_replan: bool
    need_clarify: bool
    suggested_slot: ClarifySlot | None = None
    confidence_hint: float = Field(..., ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list)


class ClarifyDirective(PDABaseModel):
    slot: ClarifySlot
    question_template_id: str
    options: list[str] = Field(default_factory=list)


class ExecutionPlanExplain(PDABaseModel):
    reason_codes: list[str] = Field(default_factory=list)
    probe_used: bool = False


class ExecutionPlan(PDABaseModel):
    task: TaskType
    domain: DomainType
    slots: dict[str, str] = Field(default_factory=dict)
    next_action: NextAction
    clarify: ClarifyDirective | None = None
    retrieval_plan: RetrievalPlan | None = None
    explain: ExecutionPlanExplain = Field(default_factory=ExecutionPlanExplain)
