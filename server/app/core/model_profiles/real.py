from __future__ import annotations

from .base import GenerationParams, GenerationProfileSet, ModelProfileSettings


REAL_MODEL_PROFILE = ModelProfileSettings(
    name="real",
    provider="openai",
    base_model="gpt-4.1-mini",
    policy_model="policy://pending",
    embedding_model="text-embedding-3-large",
    embedding_version_id="text-embedding-3-large:default",
    generation=GenerationProfileSet(
        bjj=GenerationParams(temperature=0.1, top_p=1.0, max_tokens=1600),
        literary=GenerationParams(temperature=0.9, top_p=0.9, max_tokens=1800),
        replan=GenerationParams(temperature=0.1, top_p=1.0, max_tokens=800),
        safe_summary=GenerationParams(temperature=0.0, top_p=1.0, max_tokens=256),
    ),
)
