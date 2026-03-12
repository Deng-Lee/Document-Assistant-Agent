#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from server.app.core.bjj import BJJAmbiguousFinalAnswer, BJJFullAnswer, BJJLowEvidenceAnswer

from generate_bjj_train_300 import POSITION_CONFIGS, _build_baseline_output, _slug


DATASET_DIR = REPO_ROOT / "datasets" / "sft" / "manual_seed" / date.today().strftime("%Y%m%d")
SOURCE_PATH = DATASET_DIR / "bjj_train_300.jsonl"
EDGE_PATH = DATASET_DIR / "bjj_edge_cases_60.jsonl"
COMBINED_PATH = DATASET_DIR / "bjj_train_360.jsonl"
TRAIN_PATH = DATASET_DIR / "train.jsonl"
VAL_PATH = DATASET_DIR / "val.jsonl"
MANIFEST_PATH = DATASET_DIR / "split_manifest.json"

LOW_REASON_CODES = ["SEED_EDGE_DATASET", "LOW_EVIDENCE", "QUERY_REFINE"]
AMB_REASON_CODES = ["SEED_EDGE_DATASET", "AMBIGUOUS", "RECORD_MORE_DETAIL"]


def main() -> None:
    base_rows = _read_jsonl(SOURCE_PATH)
    if len(base_rows) != 300:
        raise ValueError(f"Expected 300 base rows at {SOURCE_PATH}, got {len(base_rows)}")
    edge_rows = _build_edge_rows()
    combined_rows = base_rows + edge_rows
    train_rows, val_rows = _split_rows(combined_rows)

    _write_jsonl(EDGE_PATH, edge_rows)
    _write_jsonl(COMBINED_PATH, combined_rows)
    _write_jsonl(TRAIN_PATH, train_rows)
    _write_jsonl(VAL_PATH, val_rows)
    manifest = {
        "dataset_name": "bjj_seed_plus_edges",
        "base_sample_count": len(base_rows),
        "edge_sample_count": len(edge_rows),
        "combined_sample_count": len(combined_rows),
        "train_sample_count": len(train_rows),
        "val_sample_count": len(val_rows),
        "train_mode_counts": _mode_counts(train_rows),
        "val_mode_counts": _mode_counts(val_rows),
        "edge_mode_counts": _mode_counts(edge_rows),
        "source_path": str(SOURCE_PATH.relative_to(REPO_ROOT)),
        "edge_path": str(EDGE_PATH.relative_to(REPO_ROOT)),
        "combined_path": str(COMBINED_PATH.relative_to(REPO_ROOT)),
        "train_path": str(TRAIN_PATH.relative_to(REPO_ROOT)),
        "val_path": str(VAL_PATH.relative_to(REPO_ROOT)),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "bjj_sft_split_ok "
        f"combined={len(combined_rows)} train={len(train_rows)} val={len(val_rows)} "
        f"edge_low={_mode_counts(edge_rows).get('LOW_EVIDENCE', 0)} "
        f"edge_ambiguous={_mode_counts(edge_rows).get('AMBIGUOUS_FINAL', 0)}"
    )


def _build_edge_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for config_index, config in enumerate(POSITION_CONFIGS):
        patterns = ["LOW_EVIDENCE", "AMBIGUOUS_FINAL", "LOW_EVIDENCE"] if config_index % 2 == 0 else ["AMBIGUOUS_FINAL", "LOW_EVIDENCE", "AMBIGUOUS_FINAL"]
        for variant_index, mode in enumerate(patterns, start=1):
            rows.append(_build_edge_row(config_index, config, variant_index, mode))
    if len(rows) != 60:
        raise ValueError(f"Expected 60 edge rows, got {len(rows)}")
    return rows


def _build_edge_row(config_index: int, config: dict[str, Any], variant_index: int, mode: str) -> dict[str, Any]:
    control = "不确定" if mode == "LOW_EVIDENCE" else "手腕"
    position = config["position"]
    orientation = config["orientation"]
    distance = "近距离" if variant_index != 2 else "远距离"
    goal = config["goal"]
    suffix = "low" if mode == "LOW_EVIDENCE" else "amb"
    trace_id = f"edge_{_slug(position)}_{_slug(orientation)}_{suffix}_{variant_index:02d}"
    evidence_id = f"edge_ev_{_slug(position)}_{_slug(orientation)}_{suffix}_{variant_index:02d}"
    doc_id = f"edge_{_slug(position)}_{_slug(orientation)}"
    doc_version_id = f"{doc_id}_v1"
    query_original = (
        f"我在 {position} {orientation}、{distance} 想做 {goal}。"
        f"但这轮记录只知道对手大概在干扰，没有足够细节。"
        if mode == "LOW_EVIDENCE"
        else f"我在 {position} {orientation}、{distance} 想做 {goal}，"
        f"但我只知道自己试了“{config['your_action']}”，还不确定关键分歧应该先问控制点还是动作时机。"
    )
    query_clean = (
        f"{position} {orientation} {distance} {goal} edge_case mode={mode} "
        f"action={config['your_action']} adjustment={config['your_adjustment']}"
    )
    slots = {
        "position": position,
        "orientation": orientation,
        "distance": distance,
        "goal": goal,
        "opponent_control": control,
    }
    evidence_item = {
        "evidence_id": evidence_id,
        "doc_id": doc_id,
        "doc_version_id": doc_version_id,
        "locator": {
            "doc_version_id": doc_version_id,
            "source_path": str(EDGE_PATH.relative_to(REPO_ROOT)),
            "line_range": {"start": config_index * 3 + variant_index, "end": config_index * 3 + variant_index},
            "char_range": {"start": 0, "end": 120},
        },
        "safe_summary": (
            f"{position}{orientation}{distance} {goal}: "
            + (
                "证据太稀，只有动作意图，没有稳定的控制点和结果链。"
                if mode == "LOW_EVIDENCE"
                else "已有部分结构信息，但对控制点和动作失败原因仍存在两个合理解释。"
            )
        ),
        "excerpt_snapshot": None if mode == "LOW_EVIDENCE" else f"可能需要先确认 {config['mistake']} 还是 {config['opponent_response']} 更关键。",
        "metadata_digest": {
            "position": position,
            "orientation": orientation,
            "distance": distance,
            "goal": goal,
            "opponent_control": control,
            "heading_path": [position, orientation, mode],
        },
        "rank_signals": {
            "structured_filter_applied": True,
            "bm25_rank": 1,
            "dense_rank": 1,
            "rrf_rank": 1,
            "cross_encoder_rank": 1,
            "cross_encoder_score": 0.62 if mode == "LOW_EVIDENCE" else 0.74,
        },
    }
    baseline_output = _build_baseline_output(config, control, evidence_id, slots)
    target_output = (
        _build_low_evidence_output(config, control, evidence_id, slots)
        if mode == "LOW_EVIDENCE"
        else _build_ambiguous_output(config, control, evidence_id, slots)
    )
    _validate_target(target_output)
    return {
        "trace_id": trace_id,
        "input": {
            "task": "COACH_BJJ",
            "query_original": query_original,
            "query_clean": query_clean,
            "confirmed_slots": slots,
            "coach_clarify_round": 0,
            "coach_pending_slot": None,
            "profile_version_id": "profile_seed_v1",
            "profile_summary_snapshot": {
                "profile_version_id": "profile_seed_v1",
                "ruleset_default": "Gi",
                "injuries": [],
                "forbidden_actions": [],
                "preferences": [],
            },
            "frozen_evidence_pack": {
                "items": [evidence_item],
                "token_budget": 4000,
                "per_doc_limit": 3,
            },
            "prompt_version": "bjj.seed.edge.v1",
            "prompt_hash": None,
            "baseline_output": baseline_output,
        },
        "target_output": target_output,
    }


def _build_low_evidence_output(
    config: dict[str, Any],
    control: str,
    evidence_id: str,
    slots: dict[str, str],
) -> dict[str, Any]:
    return {
        "mode": "LOW_EVIDENCE",
        "assumptions": {
            "ruleset": "Gi",
            "confirmed_slots": slots,
            "opponent_control": control,
        },
        "reasoning_status": {
            "gate_label": "LOW_EVIDENCE",
            "reason_codes": LOW_REASON_CODES,
            "coach_clarify_round": 0,
        },
        "caveats": [
            "当前证据不足以直接给出高置信度主线方案。",
            f"至少还缺对手控制点、失败瞬间和 {config['goal']} 前一拍结构状态中的关键信息。",
        ],
        "observations": [
            {
                "text": f"目前只能看出你想做“{config['your_action']}”，但不足以判断先该修 {config['your_adjustment']} 还是别的第一层结构。",
                "evidence_ids": [evidence_id],
            }
        ],
        "plans": {
            "A_baseline": {"title": "", "preconditions": [], "steps": [], "evidence_ids": [], "generic": False},
            "B_offense": {"title": "", "preconditions": [], "steps": [], "evidence_ids": [], "generic": False},
            "C_branch": {"branches": []},
        },
        "mistakes": [],
        "drills": [],
        "next_step": {
            "type": "QUERY_REFINE",
            "message": f"先补充 {config['position']} {config['orientation']} 下对手的控制点、你失败的具体瞬间，以及是否已经建立第一层框架。",
            "record_template": "",
        },
        "citations": [evidence_id],
    }


def _build_ambiguous_output(
    config: dict[str, Any],
    control: str,
    evidence_id: str,
    slots: dict[str, str],
) -> dict[str, Any]:
    return {
        "mode": "AMBIGUOUS_FINAL",
        "assumptions": {
            "ruleset": "Gi",
            "confirmed_slots": slots,
            "opponent_control": control,
        },
        "reasoning_status": {
            "gate_label": "AMBIGUOUS",
            "reason_codes": AMB_REASON_CODES,
            "coach_clarify_round": 0,
        },
        "caveats": [
            f"当前证据支持两个合理解释：要么先修“{config['your_adjustment']}”，要么先补充对 {control} 控制的处理细节。",
            "在没看到更细的失败瞬间前，不应把其中一个分支当成唯一正确答案。",
        ],
        "observations": [
            {
                "text": f"你遇到的问题边界已经比较清楚，但还差一步：要确认失败是出在“{config['opponent_response']}”之前，还是出在第一层结构没立住。",
                "evidence_ids": [evidence_id],
            }
        ],
        "plans": {
            "A_baseline": {
                "title": "先保留最稳的第一层处理",
                "preconditions": [f"位置仍是 {config['position']} {config['orientation']}"],
                "steps": [config["your_adjustment"]],
                "evidence_ids": [evidence_id],
                "generic": False,
            },
            "B_offense": {"title": "", "preconditions": [], "steps": [], "evidence_ids": [], "generic": False},
            "C_branch": {
                "branches": [
                    {
                        "if": f"如果真正问题是 {control} 控制点先把结构锁死",
                        "then": ["先记录并补充对该控制点的处理细节。"],
                        "evidence_ids": [evidence_id],
                        "generic": False,
                    },
                    {
                        "if": f"如果真正问题是“{config['opponent_response']}”发生前第一层结构没立住",
                        "then": [f"先把“{config['your_adjustment']}”做稳，再回到主线动作。"],
                        "evidence_ids": [evidence_id],
                        "generic": False,
                    },
                ]
            },
        },
        "mistakes": [],
        "drills": [],
        "next_step": {
            "type": "RECORD_SUGGESTION",
            "message": "把失败瞬间补录成一条更完整的记录，再决定应该走哪个分支。",
            "record_template": "position/orientation/distance/goal/your_action/opponent_response/opponent_control/your_adjustment/notes",
        },
        "citations": [evidence_id],
    }


def _validate_target(target_output: dict[str, Any]) -> None:
    mode = target_output["mode"]
    if mode == "FULL":
        BJJFullAnswer(**target_output)
    elif mode == "LOW_EVIDENCE":
        BJJLowEvidenceAnswer(**target_output)
    elif mode == "AMBIGUOUS_FINAL":
        BJJAmbiguousFinalAnswer(**target_output)
    else:
        raise ValueError(f"unsupported_mode:{mode}")


def _split_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[row["target_output"]["mode"]].append(row)
    train_rows: list[dict[str, Any]] = []
    val_rows: list[dict[str, Any]] = []
    for mode, bucket in buckets.items():
        ordered = sorted(bucket, key=lambda item: item["trace_id"])
        val_count = max(1, round(len(ordered) * 0.1))
        val_rows.extend(ordered[:val_count])
        train_rows.extend(ordered[val_count:])
    return (
        sorted(train_rows, key=lambda item: item["trace_id"]),
        sorted(val_rows, key=lambda item: item["trace_id"]),
    )


def _mode_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["target_output"]["mode"]] += 1
    return dict(sorted(counts.items()))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
