#!/usr/bin/env python3
import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


MODES = {"FULL", "AMBIGUOUS_FINAL", "LOW_EVIDENCE"}


@dataclass
class Error:
    code: str
    message: str
    path: str


def _json_load(path: Path | None) -> Any:
    if path is None:
        return json.load(__import__("sys").stdin)
    return json.loads(path.read_text(encoding="utf-8"))


def _find_key_anywhere(obj: Any, key: str, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"
            if k == key:
                found.append(p)
            found.extend(_find_key_anywhere(v, key, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(_find_key_anywhere(v, key, f"{path}[{i}]"))
    return found


def _as_list(x: Any) -> list[Any]:
    return x if isinstance(x, list) else []


def _collect_evidence_ids(output: dict[str, Any]) -> set[str]:
    ids: set[str] = set()

    def add_from(items: Iterable[Any]) -> None:
        for it in items:
            if isinstance(it, dict):
                for k in ("evidence_ids",):
                    v = it.get(k)
                    if isinstance(v, list):
                        for eid in v:
                            if isinstance(eid, str) and eid:
                                ids.add(eid)

    add_from(_as_list(output.get("observations")))
    add_from(_as_list(output.get("mistakes")))
    add_from(_as_list(output.get("drills")))

    plans = output.get("plans")
    if isinstance(plans, dict):
        for plan_key in ("A_baseline", "B_offense"):
            p = plans.get(plan_key)
            if isinstance(p, dict):
                for eid in _as_list(p.get("evidence_ids")):
                    if isinstance(eid, str) and eid:
                        ids.add(eid)
        c = plans.get("C_branch")
        if isinstance(c, dict):
            branches = _as_list(c.get("branches"))
            for br in branches:
                if isinstance(br, dict):
                    for eid in _as_list(br.get("evidence_ids")):
                        if isinstance(eid, str) and eid:
                            ids.add(eid)

    return ids


def validate(output: dict[str, Any], allowed: set[str] | None = None) -> list[Error]:
    errors: list[Error] = []

    mode = output.get("mode")
    if mode not in MODES:
        errors.append(Error("MODE_INVALID", f"mode must be one of {sorted(MODES)}", "$.mode"))
        return errors

    # Forbidden key anywhere
    forbidden_paths = _find_key_anywhere(output, "followup_question")
    for p in forbidden_paths:
        errors.append(Error("FORBIDDEN_KEY", "followup_question is forbidden", p))

    rs = output.get("reasoning_status")
    if not isinstance(rs, dict):
        errors.append(Error("MISSING", "reasoning_status must exist", "$.reasoning_status"))
        return errors

    gate = rs.get("gate_label")
    c_round = rs.get("coach_clarify_round")

    # Gate <-> mode mapping
    if gate == "HIGH_EVIDENCE" and mode != "FULL":
        errors.append(Error("MODE_POLICY", "HIGH_EVIDENCE must map to mode=FULL", "$.mode"))
    if gate == "LOW_EVIDENCE" and mode != "LOW_EVIDENCE":
        errors.append(Error("MODE_POLICY", "LOW_EVIDENCE must map to mode=LOW_EVIDENCE", "$.mode"))
    if gate == "AMBIGUOUS" and mode != "AMBIGUOUS_FINAL":
        errors.append(Error("MODE_POLICY", "AMBIGUOUS must map to mode=AMBIGUOUS_FINAL", "$.mode"))

    caveats = output.get("caveats")
    if mode in ("AMBIGUOUS_FINAL", "LOW_EVIDENCE"):
        if not isinstance(caveats, list) or len(caveats) == 0:
            errors.append(Error("CAVEATS_REQUIRED", "caveats must be non-empty", "$.caveats"))

    if mode == "LOW_EVIDENCE":
        if not isinstance(caveats, list) or len(caveats) < 4:
            errors.append(Error("LOW_CAVEATS", "LOW_EVIDENCE caveats must include 4 segments", "$.caveats"))
        drills = output.get("drills")
        if isinstance(drills, list) and len(drills) != 0:
            errors.append(Error("LOW_DRILLS", "LOW_EVIDENCE drills must be empty", "$.drills"))

    if mode == "AMBIGUOUS_FINAL":
        if c_round != 1:
            errors.append(Error("AMBIG_ROUND", "AMBIGUOUS_FINAL requires coach_clarify_round==1", "$.reasoning_status.coach_clarify_round"))
        next_step = output.get("next_step")
        if not isinstance(next_step, dict) or next_step.get("type") != "RECORD_SUGGESTION":
            errors.append(Error("AMBIG_NEXT", "AMBIGUOUS_FINAL next_step.type must be RECORD_SUGGESTION", "$.next_step.type"))

    if mode == "FULL":
        obs = output.get("observations")
        if not isinstance(obs, list) or not (3 <= len(obs) <= 5):
            errors.append(Error("FULL_OBS", "FULL observations must be 3–5", "$.observations"))
        else:
            for i, o in enumerate(obs):
                if not isinstance(o, dict) or not _as_list(o.get("evidence_ids")):
                    errors.append(Error("OBS_EVIDENCE", "Each observation must include evidence_ids", f"$.observations[{i}]"))

        plans = output.get("plans")
        c = plans.get("C_branch") if isinstance(plans, dict) else None
        branches = []
        if isinstance(c, dict):
            branches = _as_list(c.get("branches"))
        if len(branches) < 2:
            errors.append(Error("PLAN_C_BRANCH", "Plan C must have at least 2 branches", "$.plans.C_branch.branches"))

    # citations union check
    used = _collect_evidence_ids(output)
    citations = output.get("citations")
    if not isinstance(citations, list):
        errors.append(Error("CITATIONS", "citations must be a list", "$.citations"))
    else:
        cit_set = {c for c in citations if isinstance(c, str) and c}
        if used != cit_set:
            errors.append(
                Error(
                    "CITATIONS_MISMATCH",
                    f"citations must equal union of used evidence_ids. used={len(used)} citations={len(cit_set)}",
                    "$.citations",
                )
            )

    if allowed is not None:
        illegal = sorted(e for e in used if e not in allowed)
        if illegal:
            errors.append(Error("CITATIONS_OUT_OF_SET", f"Evidence ids not in allowed set: {illegal[:5]}...", "$.citations"))

    return errors


def main() -> None:
    p = argparse.ArgumentParser(description="Validate BJJ Coach JSON output against DEV_SPEC policy constraints.")
    p.add_argument("--json", dest="json_path", help="Path to output JSON (default: stdin)")
    p.add_argument("--allowed", help="Path to a JSON file containing allowed evidence_ids[] (optional)")
    p.add_argument("--report", help="Write a JSON report to this path (optional)")
    args = p.parse_args()

    output = _json_load(Path(args.json_path) if args.json_path else None)
    allowed = None
    if args.allowed:
        allowed_obj = _json_load(Path(args.allowed))
        if isinstance(allowed_obj, dict):
            allowed = set(x for x in allowed_obj.get("allowed_evidence_ids", []) if isinstance(x, str))
        elif isinstance(allowed_obj, list):
            allowed = set(x for x in allowed_obj if isinstance(x, str))

    if not isinstance(output, dict):
        raise SystemExit("Top-level output must be a JSON object")

    errors = validate(output, allowed)
    report = {
        "pass": len(errors) == 0,
        "error_count": len(errors),
        "errors": [e.__dict__ for e in errors],
    }

    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
