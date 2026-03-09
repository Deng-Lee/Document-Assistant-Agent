from __future__ import annotations

import os
from pathlib import Path


def load_local_env(start_dir: str | Path | None = None, *, override: bool = False) -> Path | None:
    env_path = _find_env_file(start_dir)
    if env_path is None:
        return None
    for key, value in _parse_env_file(env_path).items():
        if override or key not in os.environ:
            os.environ[key] = value
    return env_path


def _find_env_file(start_dir: str | Path | None = None) -> Path | None:
    current = Path(start_dir or Path.cwd()).resolve()
    search_roots = [current, *current.parents]
    for candidate_root in search_roots:
        candidate = candidate_root / ".env"
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _parse_env_file(path: str | Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = _strip_quotes(raw_value.strip())
        if key:
            payload[key] = value
    return payload


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
