from __future__ import annotations

import json
import os
from pathlib import Path

from .base import ModelProfileSettings
from ..env import load_local_env
from .fake import FAKE_MODEL_PROFILE
from .real import default_real_profile_path


MODEL_PROFILE_ENV = "PDA_MODEL_PROFILE"
MODEL_PROFILE_CONFIG_DIR_ENV = "PDA_MODEL_PROFILE_CONFIG_DIR"

_STATIC_PROFILES: dict[str, ModelProfileSettings] = {
    "fake": FAKE_MODEL_PROFILE,
}


def active_model_profile_name() -> str:
    load_local_env()
    return os.getenv(MODEL_PROFILE_ENV, "fake").strip().lower() or "fake"


def get_model_profile(profile_name: str | None = None) -> ModelProfileSettings:
    resolved = (profile_name or active_model_profile_name()).strip().lower()
    dynamic = _load_dynamic_profile(resolved)
    if dynamic is not None:
        return dynamic
    try:
        return _STATIC_PROFILES[resolved]
    except KeyError as exc:
        raise ValueError(f"Unknown model profile: {resolved}") from exc


def set_active_model_profile(profile_name: str) -> None:
    os.environ[MODEL_PROFILE_ENV] = profile_name


def _load_dynamic_profile(profile_name: str) -> ModelProfileSettings | None:
    if profile_name != "real":
        return None
    payload = _read_profile_file(_profile_file_path(profile_name))
    try:
        return ModelProfileSettings(**payload)
    except Exception as exc:
        raise ValueError(f"Invalid model profile config for {profile_name}: {exc}") from exc


def _profile_file_path(profile_name: str) -> Path:
    config_dir = os.getenv(MODEL_PROFILE_CONFIG_DIR_ENV)
    if config_dir:
        return Path(config_dir).expanduser().resolve() / f"{profile_name}.json"
    if profile_name == "real":
        return default_real_profile_path()
    return Path(__file__).resolve().parents[4] / "config" / "model_profiles" / f"{profile_name}.json"


def _read_profile_file(path: Path) -> dict:
    if not path.exists():
        raise ValueError(f"Missing model profile config: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in model profile config: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Model profile config must be a JSON object: {path}")
    return payload
