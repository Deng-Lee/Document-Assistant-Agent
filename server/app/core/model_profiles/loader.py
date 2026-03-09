from __future__ import annotations

import os

from .base import ModelProfileSettings
from ..env import load_local_env
from .fake import FAKE_MODEL_PROFILE
from .real import REAL_MODEL_PROFILE


MODEL_PROFILE_ENV = "PDA_MODEL_PROFILE"

_PROFILES: dict[str, ModelProfileSettings] = {
    "fake": FAKE_MODEL_PROFILE,
    "real": REAL_MODEL_PROFILE,
}


def active_model_profile_name() -> str:
    load_local_env()
    return os.getenv(MODEL_PROFILE_ENV, "fake").strip().lower() or "fake"


def get_model_profile(profile_name: str | None = None) -> ModelProfileSettings:
    resolved = (profile_name or active_model_profile_name()).strip().lower()
    try:
        return _PROFILES[resolved]
    except KeyError as exc:
        raise ValueError(f"Unknown model profile: {resolved}") from exc


def set_active_model_profile(profile_name: str) -> None:
    os.environ[MODEL_PROFILE_ENV] = profile_name
