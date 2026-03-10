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

from .plan_builder import build_retrieval_plan_for_state, clarify_options_for_slot, domain_clarify_options
from .replan_provider import (
    LLMReplanOutput,
    OpenAIReplanProvider,
    ReplanProvider,
    ReplanProviderError,
    ReplanProviderRequest,
    ReplanProviderSchemaError,
    ReplanProviderUnavailableError,
)
from .slot_parser import clarify_template_id
from .state import ConversationState


class ReplanAttempt(PDABaseModel):
    invoked: bool = False
    result: str = "skipped"
    execution_plan: ExecutionPlan | None = None


class OrchestratorReplanner:
    def __init__(
        self,
        runtime_config: RuntimeConfigSnapshot,
        provider: ReplanProvider | None = None,
    ):
        self.runtime_config = runtime_config
        self.provider = provider or self._default_provider(runtime_config)

    def provider_status(self) -> dict[str, object]:
        provider_name = self.provider.__class__.__name__ if self.provider is not None else None
        if self.provider is None:
            return {
                "profile_name": self.runtime_config.model_routing.profile_name,
                "provider_name": provider_name,
                "configured": False,
                "base_url": None,
            }
        transport = getattr(self.provider, "transport", None)
        return {
            "profile_name": self.runtime_config.model_routing.profile_name,
            "provider_name": provider_name,
            "configured": bool(getattr(self.provider, "is_ready", False)),
            "base_url": getattr(transport, "base_url", None),
        }

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
        if self.provider is None:
            return ReplanAttempt(invoked=True, result="provider_unavailable", execution_plan=None)
        try:
            output = self.provider.generate(
                ReplanProviderRequest(
                    user_message=user_message,
                    state_slots=dict(state.slots),
                    clarify_round=state.clarify_round,
                    pending_slot=state.pending_slot,
                    plan_check=plan_check,
                    probe_stats=probe_stats,
                    runtime_config=self.runtime_config,
                )
            )
        except ReplanProviderUnavailableError:
            return ReplanAttempt(invoked=True, result="provider_unavailable", execution_plan=None)
        except ReplanProviderSchemaError:
            return ReplanAttempt(invoked=True, result="schema_invalid", execution_plan=None)
        except ReplanProviderError:
            return ReplanAttempt(invoked=True, result="provider_error", execution_plan=None)
        execution_plan = self._execution_plan_from_output(
            user_message=user_message,
            state=state,
            plan_check=plan_check,
            probe_stats=probe_stats,
            output=output,
        )
        return ReplanAttempt(invoked=True, result="success", execution_plan=execution_plan)

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

    def _execution_plan_from_output(
        self,
        user_message: str,
        state: ConversationState,
        plan_check: PlanCheck,
        probe_stats: ProbeStats | None,
        output: LLMReplanOutput,
    ) -> ExecutionPlan:
        merged_slots = dict(state.slots)
        merged_slots.update(output.slot_updates)
        if output.domain in {DomainType.BJJ, DomainType.NOTES}:
            merged_slots["domain"] = output.domain.value
        reason_codes = _merge_reason_codes(plan_check.reason_codes, output.reason_codes, "OPENAI_REPLAN_USED")
        if output.next_action == NextAction.CLARIFY:
            clarify_slot = output.clarify_slot or ClarifySlot.DOMAIN
            return ExecutionPlan(
                task=output.task,
                domain=output.domain,
                slots=merged_slots,
                next_action=NextAction.CLARIFY,
                clarify=ClarifyDirective(
                    slot=clarify_slot,
                    question_template_id=clarify_template_id(clarify_slot),
                    options=output.clarify_options or _fallback_clarify_options(clarify_slot, probe_stats),
                ),
                explain=ExecutionPlanExplain(reason_codes=reason_codes, probe_used=True),
            )

        retrieval_plan = build_retrieval_plan_for_state(
            user_message=user_message,
            state=ConversationState(slots=merged_slots),
            domain=output.domain,
            runtime_config=self.runtime_config,
        )
        retrieval_plan.query_text = output.query_text or retrieval_plan.query_text
        return ExecutionPlan(
            task=output.task,
            domain=output.domain,
            slots=merged_slots,
            next_action=NextAction.RETRIEVE,
            retrieval_plan=retrieval_plan,
            explain=ExecutionPlanExplain(reason_codes=reason_codes, probe_used=True),
        )

    @staticmethod
    def _default_provider(runtime_config: RuntimeConfigSnapshot) -> ReplanProvider | None:
        if runtime_config.model_routing.provider == "openai":
            return OpenAIReplanProvider()
        return None


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


def _fallback_clarify_options(slot: ClarifySlot, probe_stats: ProbeStats | None) -> list[str]:
    if probe_stats is None:
        return domain_clarify_options() if slot == ClarifySlot.DOMAIN else []
    return clarify_options_for_slot(slot, probe_stats)


def _merge_reason_codes(*groups: list[str] | str) -> list[str]:
    ordered: list[str] = []
    for group in groups:
        values = [group] if isinstance(group, str) else list(group)
        for value in values:
            if value and value not in ordered:
                ordered.append(value)
    return ordered
