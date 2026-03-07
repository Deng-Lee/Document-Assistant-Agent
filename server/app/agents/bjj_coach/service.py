from __future__ import annotations

from pydantic import Field

from server.app.core import (
    ClarifyRequest,
    ClarifySlot,
    ClarifyWho,
    EvidencePack,
    ProfileConstraint,
    ProfileSummary,
    RuntimeConfigSnapshot,
    build_runtime_config,
)

from .gate import build_request_semantics, evaluate_gate, summarize_evidence
from .generator import build_ambiguous_answer, build_full_answer, build_low_evidence_answer
from .types import BJJCoachInput, EvidenceSummary, GateDecision, RequestSemantics
from .validator import degrade_to_low_evidence, validate_bjj_answer


class BJJCoachTurnOutcome(BJJCoachInput):
    request_semantics: RequestSemantics
    evidence_summary: EvidenceSummary
    gate_decision: GateDecision
    clarify_request: ClarifyRequest | None = None
    final_answer: object | None = None
    validator_report: object | None = None


class BJJCoachService:
    def __init__(self, runtime_config: RuntimeConfigSnapshot | None = None):
        self.runtime_config = runtime_config or build_runtime_config()

    def run(self, coach_input: BJJCoachInput, evidence_pack: EvidencePack) -> BJJCoachTurnOutcome:
        constraints = [
            *(constraint.value for constraint in coach_input.profile_summary.injuries),
            *(constraint.value for constraint in coach_input.profile_summary.forbidden_actions),
            *(constraint.value for constraint in coach_input.profile_summary.preferences),
        ]
        request = build_request_semantics(
            confirmed_slots=coach_input.confirmed_slots,
            profile_ruleset=coach_input.profile_summary.ruleset_default,
            profile_constraints=constraints,
        )
        evidence_summary = summarize_evidence(evidence_pack, request)
        gate_decision = evaluate_gate(request, evidence_summary, self.runtime_config)

        if gate_decision.missing_slot == "opponent_control" and coach_input.coach_clarify_round == 0:
            clarify_request = ClarifyRequest(
                who=ClarifyWho.BJJ_COACH,
                slot=ClarifySlot.OPPONENT_CONTROL,
                options=["衣领", "袖子", "手腕", "裤子", "脚腕", "胯", "脖子", "不确定"],
                template_id="ASK_OPP_CONTROL_V1",
                round=1,
                why="缺少战术控制点信息，无法稳定细化 B/C 分支。",
            )
            return BJJCoachTurnOutcome(
                **_model_to_dict(coach_input),
                request_semantics=request,
                evidence_summary=evidence_summary,
                gate_decision=gate_decision,
                clarify_request=clarify_request,
            )

        if gate_decision.gate_label.value == "HIGH_EVIDENCE":
            answer = build_full_answer(
                request=request,
                evidence_pack=evidence_pack,
                evidence_summary=evidence_summary,
                gate_decision=gate_decision,
                coach_clarify_round=coach_input.coach_clarify_round,
            )
        elif gate_decision.gate_label.value == "AMBIGUOUS":
            answer = build_ambiguous_answer(
                request=request,
                evidence_pack=evidence_pack,
                gate_decision=gate_decision,
                coach_clarify_round=max(coach_input.coach_clarify_round, 1),
            )
        else:
            answer = build_low_evidence_answer(
                request=request,
                gate_decision=gate_decision,
                evidence_pack=evidence_pack,
                coach_clarify_round=coach_input.coach_clarify_round,
            )

        allowed = {item.evidence_id for item in evidence_pack.items}
        validator_report = validate_bjj_answer(answer, allowed)
        if not validator_report.validator_pass:
            answer = degrade_to_low_evidence(gate_decision.reason_codes)
            validator_report = validate_bjj_answer(answer, allowed)
            validator_report.repair_used = False
            validator_report.validator_fail_final = not validator_report.validator_pass

        return BJJCoachTurnOutcome(
            **_model_to_dict(coach_input),
            request_semantics=request,
            evidence_summary=evidence_summary,
            gate_decision=gate_decision,
            final_answer=answer,
            validator_report=validator_report,
        )


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
