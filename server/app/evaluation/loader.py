from __future__ import annotations

import json
from pathlib import Path

from server.app.core import GoldenCase


def load_golden_cases(repo_root: str | Path, eval_set_id: str) -> list[GoldenCase]:
    root = Path(repo_root)
    candidates = [
        root / "datasets" / "golden" / f"{eval_set_id}.jsonl",
        root / "datasets" / "golden" / f"{eval_set_id}.json",
    ]
    for path in candidates:
        if path.exists():
            return _load_cases_from_path(path)
    return []


def _load_cases_from_path(path: Path) -> list[GoldenCase]:
    if path.suffix == ".jsonl":
        return [
            GoldenCase(**json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("cases", [])
    return [GoldenCase(**item) for item in payload]
