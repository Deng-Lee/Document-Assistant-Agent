from __future__ import annotations

from server.app.core import (
    ClarifyDirective,
    ClarifySlot,
    DomainType,
    ExecutionPlan,
    ExecutionPlanExplain,
    NextAction,
    PDABaseModel,
    PlanCheck,
    ProbeStats,
    RuntimeConfigSnapshot,
    TaskType,
)

from .plan_builder import build_retrieval_plan_for_state, domain_clarify_options
from .state import ConversationState


class ReplanAttempt(PDABaseModel):
    invoked: bool = False
    result: str = "skipped"
    execution_plan: ExecutionPlan | None = None


class OrchestratorReplanner:
    def __init__(self, runtime_config: RuntimeConfigSnapshot):
        self.runtime_config = runtime_config

    def should_invoke(
        self,
        plan_check: PlanCheck,
        state: ConversationState,
    ) -> bool:
        if not plan_check.need_replan:
            return False
        if self._clarify_budget_exhausted(plan_check, state):
            return True
        if self._evidence_strength_low(plan_check) and not plan_check.need_clarify:
            return True
        if plan_check.domain == DomainType.MIXED and state.clarify_round < self.runtime_config.orchestrator.clarify_round_limit:
            return False
        return True

    def replan(
        self,
        user_message: str,
        state: ConversationState,
        plan_check: PlanCheck,
        probe_stats: ProbeStats | None,
    ) -> ReplanAttempt:
        profile_name = self.runtime_config.model_routing.profile_name
        if profile_name == "fake":
            execution_plan = self._fake_replan(user_message, state, plan_check, probe_stats)
            return ReplanAttempt(invoked=True, result="success", execution_plan=execution_plan)
        return ReplanAttempt(invoked=True, result="provider_unavailable", execution_plan=None)

    def _fake_replan(
        self,
        user_message: str,
        state: ConversationState,
        plan_check: PlanCheck,
        probe_stats: ProbeStats | None,
    ) -> ExecutionPlan:
        if plan_check.domain == DomainType.MIXED and state.clarify_round < self.runtime_config.orchestrator.clarify_round_limit:
            return ExecutionPlan(
                task=TaskType.MIXED,
                domain=DomainType.MIXED,
                slots=state.slots,
                next_action=NextAction.CLARIFY,
                clarify=ClarifyDirective(
                    slot=ClarifySlot.DOMAIN,
                    question_template_id="ASK_DOMAIN_V1",
                    options=domain_clarify_options(),
                ),
                explain=ExecutionPlanExplain(
                    reason_codes=list(plan_check.reason_codes) + ["MOCK_REPLAN_DOMAIN_CLARIFY"],
                    probe_used=True,
                ),
            )

        retrieval_plan = build_retrieval_plan_for_state(
            user_message=user_message,
            state=state,
            domain=plan_check.domain,
            runtime_config=self.runtime_config,
            extra_terms=_probe_hint_terms(probe_stats),
        )
        return ExecutionPlan(
            task=plan_check.task_hint,
            domain=plan_check.domain,
            slots=state.slots,
            next_action=NextAction.RETRIEVE,
            retrieval_plan=retrieval_plan,
            explain=ExecutionPlanExplain(
                reason_codes=list(plan_check.reason_codes) + ["MOCK_REPLAN_USED"],
                probe_used=True,
            ),
        )

    def _clarify_budget_exhausted(self, plan_check: PlanCheck, state: ConversationState) -> bool:
        return "CLARIFY_BUDGET_EXHAUSTED" in plan_check.reason_codes or (
            plan_check.need_clarify and state.clarify_round >= self.runtime_config.orchestrator.clarify_round_limit
        )

    @staticmethod
    def _evidence_strength_low(plan_check: PlanCheck) -> bool:
        return "EVIDENCE_STRENGTH_LOW" in plan_check.reason_codes


def _probe_hint_terms(probe_stats: ProbeStats | None) -> list[str]:
    if probe_stats is None:
        return []
    terms: list[str] = []
    for hit in probe_stats.hits[:3]:
        digest = hit.metadata_digest
        for value in (
            digest.position,
            digest.orientation.value if digest.orientation else None,
            digest.goal,
        ):
            if value and value not in terms:
                terms.append(value)
    return terms[:4]
