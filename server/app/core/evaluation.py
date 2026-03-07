from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .base import PDABaseModel
from .enums import EvalMetricName, ModelVariant


class GoldenCase(PDABaseModel):
    case_id: str
    query: str
    domain: str
    expected_behavior: dict[str, Any] = Field(default_factory=dict)
    expected_chunk_ids: list[str] = Field(default_factory=list)


class EvalRunRequest(PDABaseModel):
    eval_set_id: str
    model_variant: ModelVariant = ModelVariant.BASE
    use_frozen_evidence: bool = True


class EvalMetricValue(PDABaseModel):
    metric: EvalMetricName
    value: float


class EvalFailure(PDABaseModel):
    trace_id: str
    failure_tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class EvalRunResult(PDABaseModel):
    eval_run_id: str
    eval_set_id: str
    model_variant: ModelVariant
    created_at: datetime
    metrics: list[EvalMetricValue] = Field(default_factory=list)
    failures: list[EvalFailure] = Field(default_factory=list)
