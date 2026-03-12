#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

import sys

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.app.core.bjj import BJJFullAnswer
from server.app.core.chat import LiteraryFinalAnswer


FIXTURE_ROOT = REPO_ROOT / "test" / "fixtures"
OUTPUT_ROOT = REPO_ROOT / "datasets" / "sft" / "manual_seed" / date.today().strftime("%Y%m%d")


@dataclass
class BJJRecord:
    fixture_path: Path
    title: str
    record_date: str
    start_line: int
    end_line: int
    fields: dict[str, str]


@dataclass
class NotesDoc:
    fixture_path: Path
    title: str
    headings: list[tuple[int, str]]
    paragraphs: list[tuple[int, str]]


def main() -> None:
    args = _parse_args()
    output_root = Path(args.out).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    rows = _build_rows(include_notes=args.include_notes)
    train_path = output_root / "train.jsonl"
    with train_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {
        "dataset_name": "manual_seed",
        "dataset_version": output_root.name,
        "created_from": str(FIXTURE_ROOT.relative_to(REPO_ROOT)),
        "include_notes": args.include_notes,
        "sample_count": len(rows),
        "bjj_sample_count": sum(1 for row in rows if row["input"]["task"] == "COACH_BJJ"),
        "notes_sample_count": sum(1 for row in rows if row["input"]["task"] == "COACH_LITERARY"),
        "train_path": str(train_path.relative_to(REPO_ROOT)),
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"seed_sft_dataset_ok samples={len(rows)} path={train_path}")


def _build_rows(include_notes: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fixture_path in sorted((FIXTURE_ROOT / "bjj").glob("*.md")):
        rows.extend(_build_bjj_rows(fixture_path))
    if include_notes:
        for fixture_path in sorted((FIXTURE_ROOT / "notes").glob("*.md")):
            rows.append(_build_notes_row(fixture_path))
    return rows


def _build_bjj_rows(fixture_path: Path) -> list[dict[str, Any]]:
    title, body_lines = _parse_markdown_fixture(fixture_path)
    records = _parse_bjj_records(fixture_path, title, body_lines)
    rows: list[dict[str, Any]] = []
    slug = fixture_path.stem
    for index, record in enumerate(records, start=1):
        doc_id = slug
        doc_version_id = f"{slug}_v1"
        evidence_id = f"{slug}_ev_{index}"
        position = record.fields["position"]
        orientation = record.fields["orientation"]
        distance = record.fields["distance"]
        goal = record.fields["goal"]
        opponent_control = record.fields.get("opponent_control", "不确定")
        query_original = (
            f"我在{position}{orientation}、{distance}时被对手以{opponent_control}控制，"
            f"做了“{record.fields['your_action']}”却被“{record.fields['opponent_response']}”压回去，"
            f"应该怎么调整才能更稳定地{goal}？"
        )
        query_clean = (
            f"{position} {orientation} {distance} {goal} opponent_control={opponent_control} "
            f"your_action={record.fields['your_action']} adjustment={record.fields['your_adjustment']}"
        )
        slots = {
            "position": position,
            "orientation": orientation,
            "distance": distance,
            "goal": goal,
            "opponent_control": opponent_control,
        }
        evidence_item = {
            "evidence_id": evidence_id,
            "doc_id": doc_id,
            "doc_version_id": doc_version_id,
            "locator": _locator_payload(
                doc_version_id=doc_version_id,
                source_path=str(fixture_path.relative_to(REPO_ROOT)),
                start_line=record.start_line,
                end_line=record.end_line,
                text="\n".join(_read_lines(fixture_path)[record.start_line - 1 : record.end_line]),
            ),
            "safe_summary": (
                f"{record.record_date} {position}{orientation} {distance} {goal}: "
                f"先做 {record.fields['your_adjustment']}，因为 {record.fields['opponent_response']} 会破坏原始支点。"
            ),
            "excerpt_snapshot": record.fields.get("notes"),
            "metadata_digest": {
                "date": record.record_date,
                "position": position,
                "orientation": orientation,
                "distance": distance,
                "goal": goal,
                "opponent_control": opponent_control,
                "heading_path": [record.record_date],
            },
            "rank_signals": {
                "structured_filter_applied": True,
                "bm25_rank": 1,
                "dense_rank": 1,
                "rrf_rank": 1,
                "cross_encoder_rank": 1,
                "cross_encoder_score": 0.98,
            },
        }
        baseline_output = {
            "mode": "FULL",
            "assumptions": {
                "ruleset": "Gi",
                "confirmed_slots": slots,
                "opponent_control": opponent_control,
            },
            "reasoning_status": {
                "gate_label": "HIGH_EVIDENCE",
                "reason_codes": ["BASELINE_SHORT"],
                "coach_clarify_round": 0,
            },
            "caveats": [f"优先解决 {opponent_control} 控制带来的平衡问题。"],
            "observations": [
                {
                    "text": f"对手用“{record.fields['opponent_response']}”压回，说明原先的 {record.fields['your_action']} 没先保护内侧肘线。",
                    "evidence_ids": [evidence_id],
                }
            ],
            "plans": {
                "A_baseline": {
                    "title": "先恢复框架",
                    "preconditions": [f"确认 {opponent_control} 控制点"],
                    "steps": [record.fields["your_adjustment"]],
                    "evidence_ids": [evidence_id],
                    "generic": False,
                },
                "B_offense": {
                    "title": "再做位移",
                    "preconditions": ["框架稳定后再转身或起身"],
                    "steps": [record.fields["your_action"]],
                    "evidence_ids": [evidence_id],
                    "generic": False,
                },
                "C_branch": {"branches": []},
            },
            "mistakes": [],
            "drills": [],
            "next_step": {"type": "NONE", "message": "", "record_template": ""},
            "citations": [evidence_id],
        }
        target_output = {
            "mode": "FULL",
            "assumptions": {
                "ruleset": "Gi",
                "confirmed_slots": slots,
                "opponent_control": opponent_control,
            },
            "reasoning_status": {
                "gate_label": "HIGH_EVIDENCE",
                "reason_codes": ["SEED_FIXTURE_DERIVED", "FOLLOW_EVIDENCE_FIRST"],
                "coach_clarify_round": 0,
            },
            "caveats": [
                f"这条建议只覆盖 {position}{orientation}{distance} 下的当前控制关系；如果控制点换成别的抓法，要重新确认第一层框架。",
            ],
            "observations": [
                {
                    "text": f"关键问题不是动作太慢，而是对手用“{record.fields['opponent_response']}”时，你的第一支点还没被 {record.fields['your_adjustment']} 保护起来。",
                    "evidence_ids": [evidence_id],
                },
                {
                    "text": record.fields.get("notes", "这条记录强调先恢复稳定结构，再继续逃脱。"),
                    "evidence_ids": [evidence_id],
                },
            ],
            "plans": {
                "A_baseline": {
                    "title": "A 先恢复内侧框架和头位",
                    "preconditions": [
                        f"你仍处在 {position}{orientation}，对手控制点是 {opponent_control}",
                        "先不要急着第二次起身或转身",
                    ],
                    "steps": [
                        f"先执行“{record.fields['your_adjustment']}”，把第一层框架和头位找回来。",
                        f"框架稳定后，再回到“{record.fields['your_action']}”这条主线。",
                    ],
                    "evidence_ids": [evidence_id],
                    "generic": False,
                },
                "B_offense": {
                    "title": "B 用更稳的时机完成逃脱",
                    "preconditions": ["第一层框架已经稳定", f"对手还在用 {opponent_control} 维持压力"],
                    "steps": [
                        "先赢回内侧肘线或脚位，再做第二次起身/转身。",
                        f"只在对手的重量被你重新导向后，继续朝 {goal} 的方向推进。",
                    ],
                    "evidence_ids": [evidence_id],
                    "generic": False,
                },
                "C_branch": {
                    "branches": [
                        {
                            "if": f"如果对手继续用“{record.fields['opponent_response']}”压回来",
                            "then": [
                                f"优先重做“{record.fields['your_adjustment']}”，不要跳过第一层保护。",
                                "等对手重量重新落到可控方向，再继续下一步逃脱。",
                            ],
                            "evidence_ids": [evidence_id],
                            "generic": False,
                        }
                    ]
                },
            },
            "mistakes": [
                {
                    "text": f"一被 {opponent_control} 控制就直接重复 {record.fields['your_action']}。",
                    "fix": f"先做“{record.fields['your_adjustment']}”，把结构恢复后再推进主动作。",
                    "evidence_ids": [evidence_id],
                    "generic": False,
                }
            ],
            "drills": [
                {
                    "name": f"{position} first-frame reset",
                    "start": {
                        "position": position,
                        "orientation": orientation,
                        "distance": distance,
                    },
                    "opponent_control": opponent_control,
                    "goal": goal,
                    "dosage": "每组 5 次，共 3 组，先慢后快。",
                    "constraints": [
                        "每次都先恢复第一层框架，再允许进入下一步位移。",
                        "如果头位或肘线没回来，这次重复不算成功。",
                    ],
                    "success_criteria": [
                        "能在第一拍先把结构恢复稳定。",
                        f"随后能把 {record.fields['your_action']} 接回主线而不被立即压回。",
                    ],
                    "evidence_ids": [evidence_id],
                    "generic": False,
                }
            ],
            "next_step": {"type": "NONE", "message": "", "record_template": ""},
            "citations": [evidence_id],
        }
        BJJFullAnswer(**target_output)
        rows.append(
            {
                "trace_id": f"seed_{slug}_{index}",
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
                    "prompt_version": "bjj.seed.v1",
                    "prompt_hash": None,
                    "baseline_output": baseline_output,
                },
                "target_output": target_output,
            }
        )
    return rows


def _build_notes_row(fixture_path: Path) -> dict[str, Any]:
    title, body_lines = _parse_markdown_fixture(fixture_path)
    notes_doc = _parse_notes_doc(fixture_path, title, body_lines)
    slug = fixture_path.stem
    doc_id = slug
    doc_version_id = f"{slug}_v1"
    raw_line, raw_excerpt = notes_doc.paragraphs[0]
    safe_line, safe_summary = notes_doc.paragraphs[min(1, len(notes_doc.paragraphs) - 1)]
    query_original = f"基于《{title}》这篇笔记，写一段回应它核心意象与写作角度的短评。"
    query_clean = f"{title} literary response using mirrors memory craft or training themes"
    raw_evidence_id = f"{slug}_raw_1"
    safe_evidence_id = f"{slug}_safe_2"
    heading_path = [item[1] for item in notes_doc.headings[:2]]
    baseline_output = {
        "text": f"《{title}》主要在提示一个可继续发展的主题，但目前回答还偏概括。",
        "anchors": [],
    }
    target_output = {
        "text": _build_notes_response(title, raw_excerpt, safe_summary),
        "anchors": [
            {
                "anchor_type": "raw_excerpt",
                "doc_rank": 1,
                "evidence_id": raw_evidence_id,
                "doc_version_id": doc_version_id,
                "locator": _locator_payload(
                    doc_version_id=doc_version_id,
                    source_path=str(fixture_path.relative_to(REPO_ROOT)),
                    start_line=raw_line,
                    end_line=raw_line,
                    text=raw_excerpt,
                ),
                "citation": f"raw_excerpt {doc_version_id}:{raw_line}",
                "content": raw_excerpt,
                "heading_path": heading_path[:1],
            },
            {
                "anchor_type": "safe_summary",
                "doc_rank": 2,
                "evidence_id": safe_evidence_id,
                "doc_version_id": doc_version_id,
                "locator": _locator_payload(
                    doc_version_id=doc_version_id,
                    source_path=str(fixture_path.relative_to(REPO_ROOT)),
                    start_line=safe_line,
                    end_line=safe_line,
                    text=safe_summary,
                ),
                "citation": f"safe_summary {doc_version_id}:{safe_line}",
                "content": safe_summary,
                "heading_path": heading_path,
            },
        ],
    }
    LiteraryFinalAnswer(**target_output)
    return {
        "trace_id": f"seed_{slug}",
        "input": {
            "task": "COACH_LITERARY",
            "query_original": query_original,
            "query_clean": query_clean,
            "confirmed_slots": {},
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
                "items": [
                    {
                        "evidence_id": raw_evidence_id,
                        "doc_id": doc_id,
                        "doc_version_id": doc_version_id,
                        "locator": _locator_payload(
                            doc_version_id=doc_version_id,
                            source_path=str(fixture_path.relative_to(REPO_ROOT)),
                            start_line=raw_line,
                            end_line=raw_line,
                            text=raw_excerpt,
                        ),
                        "safe_summary": raw_excerpt,
                        "excerpt_snapshot": raw_excerpt,
                        "metadata_digest": {"heading_path": heading_path[:1]},
                        "rank_signals": {
                            "structured_filter_applied": False,
                            "bm25_rank": 1,
                            "dense_rank": 1,
                            "rrf_rank": 1,
                            "cross_encoder_rank": 1,
                            "cross_encoder_score": 0.97,
                        },
                    },
                    {
                        "evidence_id": safe_evidence_id,
                        "doc_id": doc_id,
                        "doc_version_id": doc_version_id,
                        "locator": _locator_payload(
                            doc_version_id=doc_version_id,
                            source_path=str(fixture_path.relative_to(REPO_ROOT)),
                            start_line=safe_line,
                            end_line=safe_line,
                            text=safe_summary,
                        ),
                        "safe_summary": safe_summary,
                        "excerpt_snapshot": None,
                        "metadata_digest": {"heading_path": heading_path},
                        "rank_signals": {
                            "structured_filter_applied": False,
                            "bm25_rank": 2,
                            "dense_rank": 2,
                            "rrf_rank": 2,
                            "cross_encoder_rank": 2,
                            "cross_encoder_score": 0.91,
                        },
                    },
                ],
                "token_budget": 4000,
                "per_doc_limit": 3,
            },
            "prompt_version": "literary.seed.v1",
            "prompt_hash": None,
            "baseline_output": baseline_output,
        },
        "target_output": target_output,
    }


def _parse_markdown_fixture(fixture_path: Path) -> tuple[str, list[str]]:
    text = fixture_path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n\n", text, re.DOTALL)
    if not match:
        raise ValueError(f"Missing frontmatter: {fixture_path}")
    frontmatter = match.group(1)
    title_match = re.search(r"^title:\s*(.+)$", frontmatter, re.MULTILINE)
    if not title_match:
        raise ValueError(f"Missing title in frontmatter: {fixture_path}")
    body = text[match.end() :]
    return title_match.group(1).strip(), body.splitlines()


def _parse_bjj_records(fixture_path: Path, title: str, body_lines: list[str]) -> list[BJJRecord]:
    records: list[BJJRecord] = []
    current_date: str | None = None
    section_start: int | None = None
    fields: dict[str, str] = {}
    for index, line in enumerate(body_lines, start=1):
        if line.startswith("## "):
            if current_date is not None:
                records.append(
                    BJJRecord(
                        fixture_path=fixture_path,
                        title=title,
                        record_date=current_date,
                        start_line=section_start or 1,
                        end_line=index - 1,
                        fields=fields,
                    )
                )
            current_date = line[3:].strip()
            section_start = index
            fields = {}
            continue
        if line.startswith("- "):
            key, _, value = line[2:].partition(":")
            fields[key.strip()] = value.strip()
    if current_date is not None:
        records.append(
            BJJRecord(
                fixture_path=fixture_path,
                title=title,
                record_date=current_date,
                start_line=section_start or 1,
                end_line=len(body_lines),
                fields=fields,
            )
        )
    return records


def _parse_notes_doc(fixture_path: Path, title: str, body_lines: list[str]) -> NotesDoc:
    headings: list[tuple[int, str]] = []
    paragraphs: list[tuple[int, str]] = []
    for index, line in enumerate(body_lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            headings.append((index, stripped.lstrip("# ").strip()))
            continue
        paragraphs.append((index, stripped))
    if not paragraphs:
        raise ValueError(f"No paragraphs found in notes fixture: {fixture_path}")
    return NotesDoc(
        fixture_path=fixture_path,
        title=title,
        headings=headings,
        paragraphs=paragraphs,
    )


def _locator_payload(
    *,
    doc_version_id: str,
    source_path: str,
    start_line: int,
    end_line: int,
    text: str,
) -> dict[str, Any]:
    return {
        "doc_version_id": doc_version_id,
        "source_path": source_path,
        "line_range": {"start": start_line, "end": end_line},
        "char_range": {"start": 0, "end": len(text)},
    }


def _build_notes_response(title: str, raw_excerpt: str, safe_summary: str) -> str:
    return (
        f"《{title}》的力量在于它先用“{raw_excerpt}”搭出一个可以回声的意象空间，"
        f"然后再把论点压回到“{safe_summary}”这种更可操作的观察上。"
        "因此回应这篇笔记时，最好不要只重复主题词，而要把抽象意象和可执行写法并排写出来。"
    )


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate seed SFT train.jsonl rows from local fixtures.")
    parser.add_argument("--out", default=str(OUTPUT_ROOT))
    parser.add_argument("--include-notes", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
