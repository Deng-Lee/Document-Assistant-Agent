from __future__ import annotations

from pydantic import Field

from ..base import PDABaseModel


class GenerationParams(PDABaseModel):
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = Field(default=1024, ge=1)


class GenerationProfileSet(PDABaseModel):
    bjj: GenerationParams = Field(default_factory=GenerationParams)
    literary: GenerationParams = Field(default_factory=lambda: GenerationParams(temperature=0.8, top_p=0.9))
    replan: GenerationParams = Field(default_factory=lambda: GenerationParams(temperature=0.1, top_p=1.0, max_tokens=800))
    safe_summary: GenerationParams = Field(default_factory=lambda: GenerationParams(temperature=0.0, top_p=1.0, max_tokens=256))


class RerankerProfileSettings(PDABaseModel):
    enabled: bool = False
    provider: str = "mock"
    model: str | None = None
    candidate_pool_multiplier: int = Field(default=3, ge=1)
    max_candidates: int = Field(default=24, ge=1)


class IngestionProfileSettings(PDABaseModel):
    notes_chunk_size_chars: int = Field(default=1200, ge=1)
    notes_overlap_chars: int = Field(default=120, ge=0)


class ModelProfileSettings(PDABaseModel):
    name: str
    provider: str
    base_model: str
    sft_base_model: str | None = None
    policy_model: str
    embedding_model: str
    embedding_version_id: str
    ingestion: IngestionProfileSettings = Field(default_factory=IngestionProfileSettings)
    generation: GenerationProfileSet = Field(default_factory=GenerationProfileSet)
    reranker: RerankerProfileSettings = Field(default_factory=RerankerProfileSettings)
