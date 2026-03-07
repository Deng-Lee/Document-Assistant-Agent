from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return {k: to_jsonable(v) for k, v in value.model_dump(by_alias=True).items()}
    if hasattr(value, "dict"):
        return {k: to_jsonable(v) for k, v in value.dict(by_alias=True).items()}
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def model_to_dict(model: Any) -> dict[str, Any]:
    payload = to_jsonable(model)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected dict-like payload, got {type(payload)!r}")
    return payload


def model_to_json(model: Any) -> str:
    return json.dumps(to_jsonable(model), ensure_ascii=False, default=_json_default)


def parse_json_blob(value: str | None) -> Any:
    if not value:
        return {}
    return json.loads(value)


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def read_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)
