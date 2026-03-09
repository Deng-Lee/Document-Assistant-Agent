from __future__ import annotations

from pathlib import Path


def default_real_profile_path() -> Path:
    return Path(__file__).resolve().parents[4] / "config" / "model_profiles" / "real.json"
