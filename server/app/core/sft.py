from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .base import PDABaseModel
from .bjj import BJJValidatorReport
from .evidence import EvidencePackItem
from .enums import ModelVariant
from .runtime_config import RuntimeConfigSnapshot


class SFTExportRequest(PDABaseModel):
    trace_filter: dict[str, Any] = Field(default_factory=dict)
    format: str = "jsonl"


class SFTExportSample(PDABaseModel):
    trace_id: str
    runtime_config_snapshot: RuntimeConfigSnapshot
    gate_decision: dict[str, Any] = Field(default_factory=dict)
    coach_clarify_round: int = 0
    confirmed_slots: dict[str, str] = Field(default_factory=dict)
    profile_summary: dict[str, Any] = Field(default_factory=dict)
    allowed_evidence_ids: list[str] = Field(default_factory=list)
    evidence_pack_selected: list[EvidencePackItem] = Field(default_factory=list)
    baseline_output: dict[str, Any] = Field(default_factory=dict)
    target_output: dict[str, Any] = Field(default_factory=dict)
    validator_report: BJJValidatorReport | None = None


class SFTDatasetManifest(PDABaseModel):
    dataset_version: str
    created_at: datetime
    trace_filter: dict[str, Any] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    embedding_version_id: str
    sample_count: int = Field(default=0, ge=0)


class PolicyTrainRequest(PDABaseModel):
    train_path: str
    output_path: str
    model_variant: ModelVariant = ModelVariant.POLICY
    dry_run: bool = True
