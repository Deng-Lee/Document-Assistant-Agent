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


class PolicyCheckpointRecord(SFTDatasetManifest):
    run_id: str
    checkpoint_path: str
    base_model: str
    policy_model_ref: str
    training_backend: str = "hf_lora_qlora_v1"
    target_row_count: int = Field(default=0, ge=0)


class PolicyTrainRequest(PDABaseModel):
    train_path: str
    output_path: str
    base_model: str | None = None
    model_variant: ModelVariant = ModelVariant.POLICY
    training_backend: str = "hf_lora_qlora_v1"
    epochs: int = Field(default=1, ge=1)
    learning_rate: float = Field(default=2e-4, gt=0)
    batch_size: int = Field(default=1, ge=1)
    max_seq_len: int = Field(default=2048, ge=1)
    lora_r: int = Field(default=16, ge=1)
    lora_alpha: int = Field(default=32, ge=1)
    lora_dropout: float = Field(default=0.05, ge=0.0, le=1.0)
    lora_targets: list[str] = Field(default_factory=list)
    load_in_4bit: bool = False
    dry_run: bool = True
    activate: bool = True
