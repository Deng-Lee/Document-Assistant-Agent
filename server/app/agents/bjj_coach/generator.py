from __future__ import annotations

from server.app.core import (
    BJJBranchPlan,
    BJJDrill,
    BJJMistake,
    BJJNextStep,
    BJJObservation,
    BJJPlanBlock,
    BJJPlanBranch,
    BJJPlanCollection,
    BJJAmbiguousFinalAnswer,
    BJJAssumptions,
    BJJFullAnswer,
    BJJLowEvidenceAnswer,
    BJJReasoningStatus,
    DrillStart,
    EvidencePack,
    NextStepType,
)

from .types import EvidenceSummary, GateDecision, RequestSemantics


def build_full_answer(
    request: RequestSemantics,
    evidence_pack: EvidencePack,
    evidence_summary: EvidenceSummary,
    gate_decision: GateDecision,
    coach_clarify_round: int,
) -> BJJFullAnswer:
    primary_ids = [item.evidence_id for item in evidence_pack.items[:3]]
    opponent_control = request.opponent_control or "不确定"
    observations = [
        BJJObservation(text=f"你的日志集中在 {request.position} / {request.orientation} / {request.goal} 这个语境。", evidence_ids=primary_ids[:1]),
        BJJObservation(text=f"现有证据里最常见的控制线索与应对集中度较高，说明可以给到更具体的分支。", evidence_ids=primary_ids[:2] or primary_ids[:1]),
        BJJObservation(text=f"已有记录覆盖了核心槽位，适合把建议拆成保底路线、进攻路线和分支路线。", evidence_ids=primary_ids[:3] or primary_ids[:1]),
    ]
    plans = BJJPlanCollection(
        A_baseline=BJJPlanBlock(
            title="Plan A: 先稳住姿势和空间",
            preconditions=[f"position={request.position}", f"orientation={request.orientation}"],
            steps=[
                "先恢复头位和肘膝连接，避免被继续压扁。",
                f"围绕 goal={request.goal} 先建立最低风险的保底路线。",
                "一旦对手压力减弱，优先回到可继续进攻或脱困的中间位。",
            ],
            evidence_ids=primary_ids[:2] or primary_ids[:1],
        ),
        B_offense=BJJPlanBlock(
            title="Plan B: 在保底稳定后再争取主动",
            preconditions=["对手压力已被缓解", f"opponent_control={opponent_control}"],
            steps=[
                "先确认对手当前主要控制点，再选择对应的进攻或起身窗口。",
                "若窗口不稳定，立即退回 Plan A 的保底结构。",
            ],
            evidence_ids=primary_ids[:2] or primary_ids[:1],
        ),
        C_branch=BJJBranchPlan(
            branches=[
                BJJPlanBranch(
                    **{
                        "if": f"对手主要抓 {opponent_control}",
                        "then": ["优先处理该控制点，再执行最短脱困路径。"],
                        "evidence_ids": primary_ids[:1],
                    }
                ),
                BJJPlanBranch(
                    **{
                        "if": "对手改为拉回或转向背后控制",
                        "then": ["立即回到头位和内线控制，切断连续追击。"],
                        "evidence_ids": primary_ids[:2] or primary_ids[:1],
                    }
                ),
            ]
        ),
    )
    drills = [
        BJJDrill(
            name="Baseline recovery reps",
            start=DrillStart(
                position=request.position or "",
                orientation=request.orientation or "",
                distance=request.distance or "",
            ),
            opponent_control=opponent_control,
            goal=request.goal or "",
            dosage="每组 2 分钟，3 组轮换",
            constraints=["先做低风险保底动作", "一旦失去头位立即重置"],
            success_criteria=["能在 10 秒内回到稳定中间位", "连续 3 次不被拉回原位"],
            evidence_ids=primary_ids[:2] or primary_ids[:1],
        )
    ]
    mistakes = [
        BJJMistake(
            text="保底结构建立偏慢，给了对手连续控制的机会。",
            fix="先把节奏降下来，优先完成最短的稳定步骤。",
            evidence_ids=primary_ids[:1],
        )
    ]
    citations = sorted({eid for obs in observations for eid in obs.evidence_ids} | {eid for eid in primary_ids if eid})
    return BJJFullAnswer(
        assumptions=BJJAssumptions(
            ruleset=request.ruleset,
            confirmed_slots=_confirmed_slots(request),
            opponent_control=opponent_control,
        ),
        reasoning_status=BJJReasoningStatus(
            gate_label=gate_decision.gate_label,
            reason_codes=gate_decision.reason_codes,
            coach_clarify_round=coach_clarify_round,
        ),
        observations=observations,
        plans=plans,
        mistakes=mistakes,
        drills=drills,
        citations=citations,
    )


def build_ambiguous_answer(
    request: RequestSemantics,
    evidence_pack: EvidencePack,
    gate_decision: GateDecision,
    coach_clarify_round: int,
) -> BJJAmbiguousFinalAnswer:
    primary_ids = [item.evidence_id for item in evidence_pack.items[:3]]
    caveats = [
        "当前证据无法稳定锁定对手的主要控制点。",
        "因此 Plan B/C 只给保守分支，不给高风险细节链条。",
    ]
    citations = sorted(set(primary_ids))
    return BJJAmbiguousFinalAnswer(
        assumptions=BJJAssumptions(
            ruleset=request.ruleset,
            confirmed_slots=_confirmed_slots(request),
            opponent_control=request.opponent_control or "不确定",
        ),
        reasoning_status=BJJReasoningStatus(
            gate_label=gate_decision.gate_label,
            reason_codes=gate_decision.reason_codes,
            coach_clarify_round=coach_clarify_round,
        ),
        caveats=caveats,
        observations=[
            BJJObservation(
                text="已有日志仍然支持先走低风险保底路线，而不是直接跳进精细分支。",
                evidence_ids=primary_ids[:1],
            )
        ],
        plans=BJJPlanCollection(
            A_baseline=BJJPlanBlock(
                title="Plan A: 保底恢复",
                preconditions=[f"position={request.position}", f"orientation={request.orientation}"],
                steps=[
                    "先恢复姿势完整性与内线控制。",
                    "把目标限定在最小可执行的脱困或回防动作。",
                ],
                evidence_ids=primary_ids[:1],
            ),
            B_offense=BJJPlanBlock(
                title="Plan B: 条件性主动路线",
                preconditions=["只有在控制点明确时才继续细化"],
                steps=["控制点未明确时保持 generic 保守处理。"],
                generic=True,
            ),
            C_branch=BJJBranchPlan(
                branches=[
                    BJJPlanBranch(
                        **{
                            "if": "对手主要控制上肢",
                            "then": ["先解开手部控制，再回到保底路线。"],
                            "generic": True,
                        }
                    ),
                    BJJPlanBranch(
                        **{
                            "if": "对手主要控制髋或下肢",
                            "then": ["先制造角度和距离，再决定是否继续脱困。"],
                            "generic": True,
                        }
                    ),
                ]
            ),
        ),
        drills=[
            BJJDrill(
                name="Branch rotation drill",
                start=DrillStart(
                    position=request.position or "",
                    orientation=request.orientation or "",
                    distance=request.distance or "",
                ),
                opponent_control="不确定",
                goal=request.goal or "",
                dosage="每轮 90 秒，轮换 4 轮",
                constraints=["搭档轮换不同控制类型", "未识别控制点时立即退回保底结构"],
                success_criteria=["每轮都能完成一次低风险脱困或回防", "不会因猜错控制点而暴露高风险动作"],
                evidence_ids=primary_ids[:1],
            )
        ],
        next_step=BJJNextStep(
            type=NextStepType.RECORD_SUGGESTION,
            message="下次记录时补上 opponent_control 和 distance，能显著提升分支建议精度。",
            record_template="position / orientation / distance / goal / opponent_control / your_action / opponent_response",
        ),
        citations=citations,
    )


def build_low_evidence_answer(
    request: RequestSemantics,
    gate_decision: GateDecision,
    evidence_pack: EvidencePack,
    coach_clarify_round: int,
) -> BJJLowEvidenceAnswer:
    reason_text = _low_reason_text(gate_decision.reason_codes)
    query_examples = [
        f"在 {request.position or 'turtle'}、{request.orientation or '下位'}、近距离、对手抓袖子时怎么先稳住？",
        f"我在 {request.goal or 'escape'} 目标下，下一步最该记录哪些信息？",
    ]
    citations = sorted({item.evidence_id for item in evidence_pack.items[:1]})
    return BJJLowEvidenceAnswer(
        assumptions=BJJAssumptions(
            ruleset=request.ruleset,
            confirmed_slots=_confirmed_slots(request),
            opponent_control=request.opponent_control or "不确定",
        ),
        reasoning_status=BJJReasoningStatus(
            gate_label=gate_decision.gate_label,
            reason_codes=gate_decision.reason_codes,
            coach_clarify_round=coach_clarify_round,
        ),
        caveats=[
            "Status: 我当前无法基于你的日志给可靠的个性化建议。",
            f"Reason: {reason_text}",
            "Next: 先补更具体的 query 或补一条结构化训练记录。",
            "Fallback: 我只能给你通用、低风险的保底框架，不把它写成你的个人结论。",
        ],
        plans=BJJPlanCollection(
            A_baseline=BJJPlanBlock(generic=True),
            B_offense=BJJPlanBlock(generic=True),
            C_branch=BJJBranchPlan(branches=[]),
        ),
        next_step=BJJNextStep(
            type=NextStepType.RECORD_SUGGESTION if _should_suggest_record(gate_decision.reason_codes) else NextStepType.QUERY_REFINE,
            message="；".join(query_examples) if not _should_suggest_record(gate_decision.reason_codes) else "建议补 position / orientation / distance / goal / opponent_control 这些字段。",
            record_template="position / orientation / distance / goal / opponent_control / your_action / opponent_response",
        ),
        citations=citations,
    )


def _confirmed_slots(request: RequestSemantics) -> dict[str, str]:
    payload = {}
    for key in ("position", "orientation", "distance", "goal", "date_range"):
        value = getattr(request, key)
        if value:
            payload[key] = value
    return payload


def _should_suggest_record(reason_codes: list[str]) -> bool:
    return any(code.startswith("MISSING_CORE_") or code == "EVIDENCE_TOO_THIN" for code in reason_codes)


def _low_reason_text(reason_codes: list[str]) -> str:
    if "EVIDENCE_TOO_THIN" in reason_codes:
        return "当前命中的训练记录太少，无法稳定支撑个性化归纳。"
    if "DOC_SCOPE_MIXED" in reason_codes or "OFF_TOPIC" in reason_codes:
        return "检索结果不够聚焦，当前证据和你的问题语境对不上。"
    if "NO_CONCENTRATION" in reason_codes:
        return "命中的证据过于分散，还不足以锁定最可靠的建议方向。"
    return "当前输入缺少足够稳定的结构信息。"
