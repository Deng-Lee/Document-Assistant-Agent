from __future__ import annotations

from server.app.core import (
    BJJAnswerType,
    BJJAmbiguousFinalAnswer,
    BJJFullAnswer,
    BJJLowEvidenceAnswer,
    BJJValidatorReport,
    GateLabel,
)


def validate_bjj_answer(answer: BJJAnswerType, allowed_evidence_ids: set[str]) -> BJJValidatorReport:
    errors: list[str] = []
    gate_label = answer.reasoning_status.gate_label

    if gate_label == GateLabel.HIGH_EVIDENCE and not isinstance(answer, BJJFullAnswer):
        errors.append("MODE_POLICY_HIGH_EVIDENCE")
    if gate_label == GateLabel.AMBIGUOUS and not isinstance(answer, BJJAmbiguousFinalAnswer):
        errors.append("MODE_POLICY_AMBIGUOUS")
    if gate_label == GateLabel.LOW_EVIDENCE and not isinstance(answer, BJJLowEvidenceAnswer):
        errors.append("MODE_POLICY_LOW_EVIDENCE")

    if isinstance(answer, BJJFullAnswer):
        if not (3 <= len(answer.observations) <= 5):
            errors.append("FULL_OBSERVATION_COUNT")
        if len(answer.plans.C_branch.branches) < 2:
            errors.append("FULL_PLAN_C_BRANCHES")
        for observation in answer.observations:
            if not observation.evidence_ids:
                errors.append("OBSERVATION_MISSING_EVIDENCE")
                break

    if isinstance(answer, BJJAmbiguousFinalAnswer):
        if answer.reasoning_status.coach_clarify_round != 1:
            errors.append("AMBIGUOUS_REQUIRES_CLARIFY_ROUND_1")
        if not answer.caveats:
            errors.append("AMBIGUOUS_CAVEATS_REQUIRED")
        if answer.next_step.type.value != "RECORD_SUGGESTION":
            errors.append("AMBIGUOUS_NEXT_STEP_INVALID")

    if isinstance(answer, BJJLowEvidenceAnswer):
        if len(answer.caveats) < 4:
            errors.append("LOW_EVIDENCE_REQUIRES_4_CAVEATS")
        if answer.drills:
            errors.append("LOW_EVIDENCE_DRILLS_MUST_BE_EMPTY")

    used_ids = set()
    for collection in (answer.observations, answer.mistakes, answer.drills):
        for item in collection:
            used_ids.update(item.evidence_ids)
    used_ids.update(answer.plans.A_baseline.evidence_ids)
    used_ids.update(answer.plans.B_offense.evidence_ids)
    for branch in answer.plans.C_branch.branches:
        used_ids.update(branch.evidence_ids)

    citation_ids = set(answer.citations)
    if used_ids != citation_ids:
        errors.append("CITATIONS_MUST_MATCH_USED_EVIDENCE")
    illegal_ids = sorted(eid for eid in used_ids if eid not in allowed_evidence_ids)
    if illegal_ids:
        errors.append(f"CITATIONS_OUT_OF_ALLOWED_SET:{','.join(illegal_ids[:5])}")

    return BJJValidatorReport(
        validator_pass=not errors,
        errors=errors,
    )


def degrade_to_low_evidence(reason_codes: list[str]) -> BJJLowEvidenceAnswer:
    return BJJLowEvidenceAnswer(
        reasoning_status={
            "gate_label": "LOW_EVIDENCE",
            "reason_codes": reason_codes or ["EVIDENCE_TOO_THIN", "NO_CONCENTRATION"],
            "coach_clarify_round": 0,
        },
        caveats=[
            "Status: 我当前无法基于你的日志给可靠的个性化建议。",
            "Reason: 当前输出未通过校验，因此退回到保守终态。",
            "Next: 建议补充结构化记录或把问题问得更具体。",
            "Fallback: 我只保留通用低风险框架，不继续输出精细分支。",
        ],
        next_step={
            "type": "RECORD_SUGGESTION",
            "message": "请补 position / orientation / distance / goal / opponent_control。",
            "record_template": "position / orientation / distance / goal / opponent_control / your_action / opponent_response",
        },
    )
