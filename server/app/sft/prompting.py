from __future__ import annotations

import json
from typing import Any

from server.app.core import EvidencePack, GenerationInputSnapshot


SYSTEM_PROMPT = (
    "You are a Brazilian Jiu-Jitsu (BJJ) and literary coach policy model. "
    "You must output exactly one valid JSON object matching the target contract for the task. "
    "Do not add markdown fences or commentary. "
    "Use only the supplied frozen evidence pack and baseline output context."
)


def build_policy_prompt(input_payload: dict[str, Any]) -> str:
    return f"{SYSTEM_PROMPT}\n\nINPUT_JSON:\n{json.dumps(input_payload, ensure_ascii=False)}\n\nOUTPUT_JSON:\n"


def build_policy_input_payload(
    input_snapshot: GenerationInputSnapshot,
    baseline_output: dict[str, Any],
    prompt_version: str | None = None,
    prompt_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "task": input_snapshot.task,
        "query_original": input_snapshot.query_original,
        "query_clean": input_snapshot.query_clean,
        "confirmed_slots": _to_jsonable(input_snapshot.confirmed_slots),
        "coach_clarify_round": input_snapshot.coach_clarify_round,
        "coach_pending_slot": input_snapshot.coach_pending_slot,
        "profile_version_id": input_snapshot.profile_version_id,
        "profile_summary_snapshot": _to_jsonable(input_snapshot.profile_summary_snapshot),
        "frozen_evidence_pack": _to_jsonable(input_snapshot.frozen_evidence_pack),
        "prompt_version": prompt_version,
        "prompt_hash": prompt_hash,
        "baseline_output": _to_jsonable(baseline_output),
    }


def evidence_pack_from_items(items: list[Any]) -> dict[str, Any]:
    return _to_jsonable(EvidencePack(items=items))


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return {k: _to_jsonable(v) for k, v in value.model_dump(by_alias=True).items()}
    if hasattr(value, "dict"):
        return {k: _to_jsonable(v) for k, v in value.dict(by_alias=True).items()}
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            pass
    return value
