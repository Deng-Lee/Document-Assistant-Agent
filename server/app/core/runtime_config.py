from __future__ import annotations

from pydantic import Field

from .base import PDABaseModel
from .enums import PolicyVersion, TraceCaptureLevel
from .model_profiles import ModelProfileSettings, active_model_profile_name, get_model_profile


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


class IngestionConfig(PDABaseModel):
    notes_chunk_size_chars: int = 1200
    notes_overlap_chars: int = 120


class RerankerConfig(PDABaseModel):
    enabled: bool = False
    provider: str = "mock"
    model: str | None = None
    candidate_pool_multiplier: int = Field(default=3, ge=1)
    max_candidates: int = Field(default=24, ge=1)


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
    profile_name: str = "fake"
    provider: str = "openai"
    base_model: str = "gpt-4.1-mini"
    sft_base_model: str | None = None
    policy_model: str = "policy://pending"
    embedding_model: str = "text-embedding-3-large"


class GenerationConfig(PDABaseModel):
    bjj: dict[str, float | int] = Field(default_factory=dict)
    literary: dict[str, float | int] = Field(default_factory=dict)
    replan: dict[str, float | int] = Field(default_factory=dict)
    safe_summary: dict[str, float | int] = Field(default_factory=dict)


class RuntimeConfigSnapshot(PDABaseModel):
    doc_version_ids: list[str] = Field(default_factory=list)
    embedding_version_id: str = Field(default_factory=lambda: get_model_profile().embedding_version_id)
    prompt_versions: PromptVersions = Field(default_factory=PromptVersions)
    policy_version: PolicyVersion = PolicyVersion.BASE
    profile_version_id: str | None = None
    trace_capture_level: TraceCaptureLevel = TraceCaptureLevel.MINIMAL
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    retrieval: RetrievalLimits = Field(default_factory=RetrievalLimits)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    orchestrator: OrchestratorThresholds = Field(default_factory=OrchestratorThresholds)
    bjj_gate: BJJGateThresholds = Field(default_factory=BJJGateThresholds)
    model_routing: ModelRoutingConfig = Field(default_factory=lambda: _model_routing_from_profile(get_model_profile()))
    generation: GenerationConfig = Field(default_factory=lambda: _generation_config_from_profile(get_model_profile()))

def build_runtime_config(profile_name: str | None = None) -> RuntimeConfigSnapshot:
    profile = get_model_profile(profile_name)
    return RuntimeConfigSnapshot(
        embedding_version_id=profile.embedding_version_id,
        ingestion=_ingestion_config_from_profile(profile),
        reranker=_reranker_config_from_profile(profile),
        model_routing=_model_routing_from_profile(profile),
        generation=_generation_config_from_profile(profile),
    )


def _model_routing_from_profile(profile: ModelProfileSettings) -> ModelRoutingConfig:
    return ModelRoutingConfig(
        profile_name=profile.name,
        provider=profile.provider,
        base_model=profile.base_model,
        sft_base_model=profile.sft_base_model,
        policy_model=profile.policy_model,
        embedding_model=profile.embedding_model,
    )


def _generation_config_from_profile(profile: ModelProfileSettings) -> GenerationConfig:
    generation = profile.generation
    dump = lambda model: model.model_dump() if hasattr(model, "model_dump") else model.dict()
    return GenerationConfig(
        bjj=dump(generation.bjj),
        literary=dump(generation.literary),
        replan=dump(generation.replan),
        safe_summary=dump(generation.safe_summary),
    )


def _ingestion_config_from_profile(profile: ModelProfileSettings) -> IngestionConfig:
    ingestion = profile.ingestion
    return IngestionConfig(
        notes_chunk_size_chars=ingestion.notes_chunk_size_chars,
        notes_overlap_chars=ingestion.notes_overlap_chars,
    )


def _reranker_config_from_profile(profile: ModelProfileSettings) -> RerankerConfig:
    reranker = profile.reranker
    return RerankerConfig(
        enabled=reranker.enabled,
        provider=reranker.provider,
        model=reranker.model,
        candidate_pool_multiplier=reranker.candidate_pool_multiplier,
        max_candidates=reranker.max_candidates,
    )


DEFAULT_RUNTIME_CONFIG = build_runtime_config(active_model_profile_name())
