from __future__ import annotations

from .base import (
    GenerationParams,
    GenerationProfileSet,
    IngestionProfileSettings,
    ModelProfileSettings,
    RerankerProfileSettings,
)


FAKE_MODEL_PROFILE = ModelProfileSettings(
    name="fake",
    provider="mock",
    base_model="mock-bjj-base",
    sft_base_model="mock-bjj-base",
    policy_model="mock-bjj-policy",
    embedding_model="mock-embedding",
    embedding_version_id="mock-embedding:v1",
    ingestion=IngestionProfileSettings(
        notes_chunk_size_chars=1200,
        notes_overlap_chars=120,
    ),
    generation=GenerationProfileSet(
        bjj=GenerationParams(temperature=0.0, top_p=1.0, max_tokens=1200),
        literary=GenerationParams(temperature=0.7, top_p=0.9, max_tokens=1400),
        replan=GenerationParams(temperature=0.1, top_p=1.0, max_tokens=700),
        safe_summary=GenerationParams(temperature=0.0, top_p=1.0, max_tokens=200),
    ),
    reranker=RerankerProfileSettings(
        enabled=True,
        provider="mock",
        model="mock-cross-encoder-v1",
        candidate_pool_multiplier=3,
        max_candidates=24,
    ),
)
