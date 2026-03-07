from __future__ import annotations

from pydantic import Field

from .base import PDABaseModel
from .enums import PolicyVersion, TraceCaptureLevel


class PromptVersions(PDABaseModel):
    bjj_coach: str = "bjj_coach.v1"
    literary: str = "literary.v1"
    safe_summary: str = "safe_summary.v1"
    replan: str = "replan.v1"


class RetrievalLimits(PDABaseModel):
    probe_top_k: int = 12
    full_top_k: int = 24
    max_chunks_per_doc: int = 3
    min_docs: int = 1
    token_budget: int = 4000


class OrchestratorThresholds(PDABaseModel):
    domain_bjj_threshold: float = 0.65
    domain_notes_threshold: float = 0.35
    slot_entropy_threshold: float = 0.60
    evidence_strength_threshold: float = 0.40
    clarify_round_limit: int = 2
    write_intent_prefixes: list[str] = Field(
        default_factory=lambda: ["帮我记录", "记录一下", "新增训练", "写入日志", "保存这条笔记"]
    )
    mixed_domain_strategy: str = "clarify_first"


class BJJGateThresholds(PDABaseModel):
    low_evidence_chunk_min: int = 2
    high_evidence_chunk_min: int = 3
    doc_type_purity_min: float = 0.80
    position_match_min: float = 0.50
    position_concentration_min: float = 0.50
    low_evidence_concentration_floor: float = 0.35
    coach_clarify_round_limit: int = 1


class ModelRoutingConfig(PDABaseModel):
    provider: str = "openai"
    base_model: str = "gpt-4.1-mini"
    policy_model: str = "policy://pending"
    embedding_model: str = "text-embedding-3-large"


class RuntimeConfigSnapshot(PDABaseModel):
    doc_version_ids: list[str] = Field(default_factory=list)
    embedding_version_id: str = "text-embedding-3-large:default"
    prompt_versions: PromptVersions = Field(default_factory=PromptVersions)
    policy_version: PolicyVersion = PolicyVersion.BASE
    profile_version_id: str | None = None
    trace_capture_level: TraceCaptureLevel = TraceCaptureLevel.MINIMAL
    retrieval: RetrievalLimits = Field(default_factory=RetrievalLimits)
    orchestrator: OrchestratorThresholds = Field(default_factory=OrchestratorThresholds)
    bjj_gate: BJJGateThresholds = Field(default_factory=BJJGateThresholds)
    model_routing: ModelRoutingConfig = Field(default_factory=ModelRoutingConfig)


DEFAULT_RUNTIME_CONFIG = RuntimeConfigSnapshot()
