from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .base import PDABaseModel
from .enums import EvalMetricName, EvalRunStatus, EvalStageStatus, ModelVariant


class GoldenCase(PDABaseModel):
    case_id: str
    query: str
    domain: str
    trace_id: str | None = None
    expected_behavior: dict[str, Any] = Field(default_factory=dict)
    expected_chunk_ids: list[str] = Field(default_factory=list)


class EvalRunRequest(PDABaseModel):
    eval_set_id: str
    model_variant: ModelVariant = ModelVariant.BASE
    use_frozen_evidence: bool = True


class EvalMetricValue(PDABaseModel):
    metric: EvalMetricName
    value: float


class EvalSummary(PDABaseModel):
    sample_count: int = 0
    p50: float | None = None
    p95: float | None = None
    min: float | None = None
    max: float | None = None


class EvalFailure(PDABaseModel):
    trace_id: str
    failure_tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class EvalStageResult(PDABaseModel):
    status: EvalStageStatus
    evaluator: str
    reason: str | None = None
    sample_count: int = 0
    metrics: list[EvalMetricValue] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class EvalRunResult(PDABaseModel):
    eval_run_id: str
    eval_set_id: str
    model_variant: ModelVariant
    created_at: datetime
    run_status: EvalRunStatus = EvalRunStatus.COMPLETED
    golden_case_count: int = 0
    source_trace_ids: list[str] = Field(default_factory=list)
    metrics: list[EvalMetricValue] = Field(default_factory=list)
    failures: list[EvalFailure] = Field(default_factory=list)
    latency_summary: EvalSummary | None = None
    cost_summary: EvalSummary | None = None
    ragas: EvalStageResult | None = None
    judge: EvalStageResult | None = None
