#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.app.core.bjj import BJJFullAnswer


OUTPUT_PATH = REPO_ROOT / "datasets" / "sft" / "manual_seed" / date.today().strftime("%Y%m%d") / "bjj_train_300.jsonl"


POSITION_CONFIGS: list[dict[str, Any]] = [
    {
        "position": "closed guard",
        "orientation": "下位",
        "goal": "back_take",
        "your_action": "arm drag to climb the back",
        "opponent_response": "postured up before the hip angle changed",
        "your_adjustment": "break posture first with a collar pull before dragging",
        "mistake": "直接拉手不过先破姿势",
        "drill": "closed guard arm-drag timing",
    },
    {
        "position": "closed guard",
        "orientation": "上位",
        "goal": "guard_open",
        "your_action": "stood to open the ankles",
        "opponent_response": "pulled the knees tight and broke posture",
        "your_adjustment": "pin the hips and rebuild posture before standing",
        "mistake": "髋线没固定就急着站起",
        "drill": "closed guard posture-and-stand",
    },
    {
        "position": "half guard",
        "orientation": "下位",
        "goal": "sweep",
        "your_action": "came up on the underhook to dogfight",
        "opponent_response": "crossfaced and flattened the shoulders",
        "your_adjustment": "win the inside elbow and knee line before chasing height",
        "mistake": "肩线被压平还继续往上顶",
        "drill": "half guard underhook to dogfight",
    },
    {
        "position": "half guard",
        "orientation": "上位",
        "goal": "pass",
        "your_action": "crossfaced and tried to free the knee",
        "opponent_response": "framed under the neck and recovered knee shield",
        "your_adjustment": "flatten the hips first and clear the lower leg before windshield-wipering",
        "mistake": "上身压力建立不足就急着抽膝",
        "drill": "half guard flatten-and-free-knee",
    },
    {
        "position": "side control",
        "orientation": "下位",
        "goal": "reguard",
        "your_action": "framed on the neck and tried to hip escape",
        "opponent_response": "switched the hips and killed the near-side elbow",
        "your_adjustment": "rebuild the near-side elbow frame before moving the hips",
        "mistake": "肘线没回来就先移动髋部",
        "drill": "side control elbow-frame recovery",
    },
    {
        "position": "side control",
        "orientation": "上位",
        "goal": "mount",
        "your_action": "walked the hips north to clear the elbow",
        "opponent_response": "turned to the side and inserted a knee shield",
        "your_adjustment": "pin the near arm first and force the shoulders flat before stepping over",
        "mistake": "对手肩线还侧着就急着过腿",
        "drill": "side control pin-and-step-over",
    },
    {
        "position": "turtle",
        "orientation": "下位",
        "goal": "escape",
        "your_action": "posted and tried to stand up",
        "opponent_response": "dragged the posting arm and collapsed the base",
        "your_adjustment": "hide the elbow and win head position before the second post",
        "mistake": "没先保护肘线就二次起身",
        "drill": "turtle first-post recovery",
    },
    {
        "position": "turtle",
        "orientation": "上位",
        "goal": "back_take",
        "your_action": "drove weight forward and chased the seatbelt",
        "opponent_response": "sat through before the hook was secured",
        "your_adjustment": "control the near hip before reaching for the second hook",
        "mistake": "还没管住髋部就伸手找第二钩",
        "drill": "turtle hip-control to hook-in",
    },
    {
        "position": "open guard",
        "orientation": "下位",
        "goal": "sweep",
        "your_action": "used shin-to-shin to enter under the hips",
        "opponent_response": "backstepped and cleared the outside hook",
        "your_adjustment": "pull the weight over the lead foot before climbing underneath",
        "mistake": "没先破平衡就钻到底下",
        "drill": "open guard shin-to-shin kuzushi",
    },
    {
        "position": "open guard",
        "orientation": "上位",
        "goal": "pass",
        "your_action": "stapled the leg and tried to run around",
        "opponent_response": "re-pummeled the hooks and squared up again",
        "your_adjustment": "pin one hip and staple the second leg before circling",
        "mistake": "只控制一条腿就开始绕",
        "drill": "open guard double-staple passing",
    },
    {
        "position": "back control",
        "orientation": "下位",
        "goal": "escape",
        "your_action": "slid the shoulders to the mat side",
        "opponent_response": "tightened the seatbelt and followed the hip line",
        "your_adjustment": "trap the top leg first and rotate to the choking-arm side",
        "mistake": "没先控制腿线就开始转身",
        "drill": "back escape leg-trap first",
    },
    {
        "position": "back control",
        "orientation": "上位",
        "goal": "finish",
        "your_action": "attacked the collar while keeping both hooks",
        "opponent_response": "peeled the top hand and slid the shoulders down",
        "your_adjustment": "hide the choking elbow and angle the shoulders before the second grip",
        "mistake": "手线暴露太早被直接拆掉",
        "drill": "back control elbow-hide to collar finish",
    },
    {
        "position": "standing",
        "orientation": "下位",
        "goal": "takedown_defense",
        "your_action": "reached for the collar tie without moving the feet",
        "opponent_response": "changed level underneath and caught the lead leg",
        "your_adjustment": "win head position and move the feet before committing the upper-body tie",
        "mistake": "手先到了，脚却停在原地",
        "drill": "standing head-position before tie",
    },
    {
        "position": "standing",
        "orientation": "上位",
        "goal": "takedown",
        "your_action": "snapped and chased the single leg",
        "opponent_response": "circled out and squared the hips before the finish",
        "your_adjustment": "turn the corner immediately after the snap and pin the far hip",
        "mistake": "抓到腿以后还停在正面",
        "drill": "standing snap-to-corner-finish",
    },
    {
        "position": "butterfly guard",
        "orientation": "下位",
        "goal": "sweep",
        "your_action": "sat up for double underhooks and tried to elevate",
        "opponent_response": "posted wide and drove the forehead forward",
        "your_adjustment": "off-balance to one corner before loading with both hooks",
        "mistake": "没先把重量拉到角上就直接抬",
        "drill": "butterfly angle-first elevation",
    },
    {
        "position": "butterfly guard",
        "orientation": "上位",
        "goal": "pass",
        "your_action": "pressed the shins and tried to body-lock",
        "opponent_response": "elevated under the centerline and exposed the hips",
        "your_adjustment": "win the inside head position and collapse one hook before closing the lock",
        "mistake": "对手双钩还活着就去抱身体",
        "drill": "butterfly head-position to body-lock",
    },
    {
        "position": "X guard",
        "orientation": "下位",
        "goal": "sweep",
        "your_action": "lifted the far leg and tried to stand with the ankle",
        "opponent_response": "posted the free hand and widened the base",
        "your_adjustment": "rotate the trapped knee inward before coming up on the ankle",
        "mistake": "控制点没转进去就急着起身",
        "drill": "x-guard knee-turn to stand-up",
    },
    {
        "position": "X guard",
        "orientation": "上位",
        "goal": "pass",
        "your_action": "pushed the top foot and tried to backstep out",
        "opponent_response": "followed the hip line and reattached the hook",
        "your_adjustment": "clear the bottom hook first and staple the shin before backstepping",
        "mistake": "只处理上面的脚就转身",
        "drill": "x-guard bottom-hook clear",
    },
    {
        "position": "K guard",
        "orientation": "下位",
        "goal": "leg_entry",
        "your_action": "threaded the knee line and reached for the heel",
        "opponent_response": "hid the knee and backstepped before the hips connected",
        "your_adjustment": "control the far hip first and keep the knees pinched before exposing the heel",
        "mistake": "髋没锁住就先伸手找跟腱",
        "drill": "k-guard hip-control before heel exposure",
    },
    {
        "position": "K guard",
        "orientation": "上位",
        "goal": "pass",
        "your_action": "tried to smash the knees together and circle out",
        "opponent_response": "inverted deeper and re-centered under the hips",
        "your_adjustment": "pin the far shin and square the shoulders before circling",
        "mistake": "上身角度还斜着就开始转圈",
        "drill": "k-guard shin-pin to circle-out",
    },
]


DISTANCES = ["近距离", "远距离", "近距离"]
OPPONENT_CONTROLS = ["袖子", "衣领", "手腕", "裤子", "脚腕", "胯", "脖子", "underhook", "overhook", "腰带"]
EMPHASIS = [
    "先保护肘线",
    "先保护头位",
    "先破坏平衡",
    "先固定髋线",
    "先赢内侧位置",
    "先把肩线摆正",
    "先处理第一层抓握",
    "先把脚线固定",
    "先压住近侧手臂",
    "先把重量带到角上",
    "先把对手肩线压平",
    "先锁定远侧髋部",
    "先确认主支点",
    "先把第二支点放好",
    "先把节奏放慢半拍",
]


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = _build_rows()
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"bjj_train_300_ok samples={len(rows)} path={OUTPUT_PATH}")


def _build_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_day = date(2026, 1, 1)
    for config_index, config in enumerate(POSITION_CONFIGS):
        for variant_index in range(15):
            record_date = (base_day + timedelta(days=config_index * 15 + variant_index)).isoformat()
            distance = DISTANCES[variant_index % len(DISTANCES)]
            control = OPPONENT_CONTROLS[(config_index + variant_index) % len(OPPONENT_CONTROLS)]
            emphasis = EMPHASIS[variant_index]
            position = config["position"]
            orientation = config["orientation"]
            goal = config["goal"]
            query_original = (
                f"我在 {position} {orientation}、{distance} 时，对手用 {control} 控制住我。"
                f"我做了“{config['your_action']}”，但对手用“{config['opponent_response']}”把节奏拿走了。"
                f"这种情况下我怎么调整，才能更稳定地完成 {goal}？"
            )
            query_clean = (
                f"{position} {orientation} {distance} {goal} opponent_control={control} "
                f"action={config['your_action']} adjustment={config['your_adjustment']} emphasis={emphasis}"
            )
            trace_id = f"seed_{_slug(position)}_{_slug(orientation)}_{variant_index + 1:02d}"
            evidence_id = f"ev_{_slug(position)}_{_slug(orientation)}_{variant_index + 1:02d}"
            doc_id = f"seed_{_slug(position)}_{_slug(orientation)}"
            doc_version_id = f"{doc_id}_v1"
            summary = (
                f"{record_date} {position}{orientation} {distance} {goal}: "
                f"先做 {config['your_adjustment']}，同时记住 {emphasis}，"
                f"因为对手会用 {config['opponent_response']} 破坏原有结构。"
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
                    "source_path": str(OUTPUT_PATH.relative_to(REPO_ROOT)),
                    "line_range": {"start": len(rows) + 1, "end": len(rows) + 1},
                    "char_range": {"start": 0, "end": len(summary)},
                },
                "safe_summary": summary,
                "excerpt_snapshot": f"{config['mistake']}；{emphasis}。",
                "metadata_digest": {
                    "date": record_date,
                    "position": position,
                    "orientation": orientation,
                    "distance": distance,
                    "goal": goal,
                    "opponent_control": control,
                    "heading_path": [position, orientation],
                },
                "rank_signals": {
                    "structured_filter_applied": True,
                    "bm25_rank": 1,
                    "dense_rank": 1,
                    "rrf_rank": 1,
                    "cross_encoder_rank": 1,
                    "cross_encoder_score": round(0.96 - variant_index * 0.01, 2),
                },
            }
            baseline_output = _build_baseline_output(config, control, evidence_id, slots)
            target_output = _build_target_output(config, control, evidence_id, slots, emphasis, summary)
            BJJFullAnswer(**target_output)
            rows.append(
                {
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
                        "prompt_version": "bjj.seed.bulk.v1",
                        "prompt_hash": None,
                        "baseline_output": baseline_output,
                    },
                    "target_output": target_output,
                }
            )
    if len(rows) != 300:
        raise ValueError(f"Expected 300 rows, got {len(rows)}")
    return rows


def _build_baseline_output(
    config: dict[str, Any],
    control: str,
    evidence_id: str,
    slots: dict[str, str],
) -> dict[str, Any]:
    return {
        "mode": "FULL",
        "assumptions": {
            "ruleset": "Gi",
            "confirmed_slots": slots,
            "opponent_control": control,
        },
        "reasoning_status": {
            "gate_label": "HIGH_EVIDENCE",
            "reason_codes": ["BASELINE_SHORT"],
            "coach_clarify_round": 0,
        },
        "caveats": [f"先确认对手当前最主要的控制点是 {control}。"],
        "observations": [
            {
                "text": f"对手用“{config['opponent_response']}”拿回节奏，说明原来的 {config['your_action']} 进入得太早。",
                "evidence_ids": [evidence_id],
            }
        ],
        "plans": {
            "A_baseline": {
                "title": "先恢复结构",
                "preconditions": [f"位置仍是 {config['position']} {config['orientation']}"],
                "steps": [config["your_adjustment"]],
                "evidence_ids": [evidence_id],
                "generic": False,
            },
            "B_offense": {
                "title": "再回主线",
                "preconditions": ["结构恢复之后"],
                "steps": [config["your_action"]],
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


def _build_target_output(
    config: dict[str, Any],
    control: str,
    evidence_id: str,
    slots: dict[str, str],
    emphasis: str,
    summary: str,
) -> dict[str, Any]:
    return {
        "mode": "FULL",
        "assumptions": {
            "ruleset": "Gi",
            "confirmed_slots": slots,
            "opponent_control": control,
        },
        "reasoning_status": {
            "gate_label": "HIGH_EVIDENCE",
            "reason_codes": ["SEED_BULK_DATASET", "EVIDENCE_FIRST", "STRUCTURE_BEFORE_ACTION"],
            "coach_clarify_round": 0,
        },
        "caveats": [
            f"这条答案只覆盖 {config['position']} {config['orientation']} 下的当前交换；如果控制点不是 {control}，第一层处理顺序要跟着改。",
        ],
        "observations": [
            {
                "text": f"问题不只是动作没成，而是你在“{config['your_action']}”之前没有先完成“{config['your_adjustment']}”，所以对手能用“{config['opponent_response']}”立刻把结构打散。",
                "evidence_ids": [evidence_id],
            },
            {
                "text": f"这条记录的训练重点是：{emphasis}。{summary}",
                "evidence_ids": [evidence_id],
            },
        ],
        "plans": {
            "A_baseline": {
                "title": "A 先恢复第一层结构",
                "preconditions": [
                    f"确认当前位置是 {config['position']} {config['orientation']}",
                    f"对手的主控制点是 {control}",
                ],
                "steps": [
                    f"先执行“{config['your_adjustment']}”。",
                    f"执行时记住：{emphasis}。",
                ],
                "evidence_ids": [evidence_id],
                "generic": False,
            },
            "B_offense": {
                "title": "B 再把主线动作接回去",
                "preconditions": [
                    "第一层结构已经恢复稳定",
                    "对手暂时不能立刻重复原来的压制路径",
                ],
                "steps": [
                    f"把“{config['your_action']}”接回主线，但只在结构稳定后才推进。",
                    f"如果对手再用“{config['opponent_response']}”，立刻回到前一步。",
                ],
                "evidence_ids": [evidence_id],
                "generic": False,
            },
            "C_branch": {
                "branches": [
                    {
                        "if": f"如果对手继续用“{config['opponent_response']}”抢回节奏",
                        "then": [
                            f"先重复“{config['your_adjustment']}”，不要跳过第一层处理。",
                            f"优先做到“{emphasis}”，再继续朝 {config['goal']} 推进。",
                        ],
                        "evidence_ids": [evidence_id],
                        "generic": False,
                    }
                ]
            },
        },
        "mistakes": [
            {
                "text": config["mistake"],
                "fix": f"把“{config['your_adjustment']}”放在主动作前面，并把重点放在“{emphasis}”。",
                "evidence_ids": [evidence_id],
                "generic": False,
            }
        ],
        "drills": [
            {
                "name": config["drill"],
                "start": {
                    "position": config["position"],
                    "orientation": config["orientation"],
                    "distance": slots["distance"],
                },
                "opponent_control": control,
                "goal": config["goal"],
                "dosage": "每组 5 次，共 4 组，前两组慢做，后两组对抗进入。",
                "constraints": [
                    "第一拍必须先恢复结构，不能直接抢结果。",
                    f"每次都要把重点放在“{emphasis}”。",
                ],
                "success_criteria": [
                    "能先把第一层结构搭住。",
                    f"随后能把 {config['your_action']} 接回去而不被对手立刻用同一路线反制。",
                ],
                "evidence_ids": [evidence_id],
                "generic": False,
            }
        ],
        "next_step": {"type": "NONE", "message": "", "record_template": ""},
        "citations": [evidence_id],
    }


def _slug(value: str) -> str:
    return value.lower().replace(" ", "_").replace("/", "_")


if __name__ == "__main__":
    main()
