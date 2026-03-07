from __future__ import annotations

from pydantic import Field

from server.app.core import (
    ClarifyDirective,
    ClarifySlot,
    EntryPoint,
    ExecutionPlan,
    ExecutionPlanExplain,
    NextAction,
    PDABaseModel,
    ProbeStats,
)
from server.app.core.runtime_config import RuntimeConfigSnapshot, build_runtime_config
from server.app.retrieval import RetrievalService

from .guards import maybe_short_circuit_write_flow
from .plan_builder import DeterministicPlanBuilder
from .plan_check import PlanCheckService
from .slot_parser import clarify_template_id, try_resolve_pending_slot
from .state import ConversationState


class OrchestratorOutcome(PDABaseModel):
    session_state: ConversationState
    execution_plan: ExecutionPlan
    probe_stats: ProbeStats | None = None


class OrchestratorService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        runtime_config: RuntimeConfigSnapshot | None = None,
    ):
        self.retrieval_service = retrieval_service
        self.runtime_config = runtime_config or build_runtime_config()
        self.plan_check_service = PlanCheckService()
        self.plan_builder = DeterministicPlanBuilder()

    def route(
        self,
        user_message: str,
        session_state: ConversationState | None = None,
        entrypoint: EntryPoint = EntryPoint.CHAT,
    ) -> OrchestratorOutcome:
        state = session_state or ConversationState()

        write_short_circuit = maybe_short_circuit_write_flow(entrypoint, user_message, self.runtime_config)
        if write_short_circuit is not None:
            return OrchestratorOutcome(session_state=state, execution_plan=write_short_circuit)

        if state.pending_slot is not None:
            resolved, updated_state = try_resolve_pending_slot(user_message, state)
            if not resolved:
                return OrchestratorOutcome(
                    session_state=state,
                    execution_plan=ExecutionPlan(
                        task=write_short_circuit.task if write_short_circuit else self._guess_pending_task(state),
                        domain=self._guess_pending_domain(state),
                        slots=state.slots,
                        next_action=NextAction.CLARIFY,
                        clarify=ClarifyDirective(
                            slot=state.pending_slot,
                            question_template_id=clarify_template_id(state.pending_slot),
                            options=[],
                        ),
                        explain=ExecutionPlanExplain(reason_codes=["PENDING_SLOT_UNRESOLVED"], probe_used=False),
                    ),
                )
            state = updated_state

        probe_filters = self._slots_to_filters(state)
        probe_outcome = self.retrieval_service.retrieve(
            query_text=user_message,
            filters_hint=probe_filters,
            mode="probe",
            top_k=self.runtime_config.retrieval.probe_top_k,
        )
        plan_check = self.plan_check_service.evaluate(
            probe_stats=probe_outcome.probe_stats or ProbeStats(
                k=0,
                probe_query_text=user_message,
                slot_entropy=0.0,
                evidence_strength={"value": 0.0, "headness": 0.0, "coherence": 0.0},
            ),
            state=state,
            user_message=user_message,
            runtime_config=self.runtime_config,
        )
        execution_plan = self.plan_builder.build(
            user_message=user_message,
            state=state,
            plan_check=plan_check,
            probe_stats=probe_outcome.probe_stats,
            runtime_config=self.runtime_config,
        )
        next_state = state.copy(deep=True)
        if execution_plan.next_action == NextAction.CLARIFY and execution_plan.clarify is not None:
            next_state.pending_slot = execution_plan.clarify.slot
            next_state.clarify_round = min(
                self.runtime_config.orchestrator.clarify_round_limit,
                next_state.clarify_round + 1,
            )
        else:
            next_state.pending_slot = None
        return OrchestratorOutcome(
            session_state=next_state,
            execution_plan=execution_plan,
            probe_stats=probe_outcome.probe_stats,
        )

    @staticmethod
    def _slots_to_filters(state: ConversationState):
        from server.app.core import RetrievalFilters

        filters = RetrievalFilters()
        if state.slots.get("domain") == "BJJ":
            from server.app.core import DocumentType

            filters.doc_type = DocumentType.BJJ
        elif state.slots.get("domain") == "NOTES":
            from server.app.core import DocumentType

            filters.doc_type = DocumentType.NOTES
        for name in ("position", "orientation", "distance", "goal", "opponent_control"):
            value = state.slots.get(name)
            if value:
                setattr(filters, name, value)
        return filters

    @staticmethod
    def _guess_pending_task(state: ConversationState):
        from server.app.core import TaskType

        if state.slots.get("domain") == "NOTES":
            return TaskType.COACH_LITERARY
        return TaskType.COACH_BJJ

    @staticmethod
    def _guess_pending_domain(state: ConversationState):
        from server.app.core import DomainType

        if state.slots.get("domain") == "NOTES":
            return DomainType.NOTES
        if state.slots.get("domain") == "BJJ":
            return DomainType.BJJ
        return DomainType.MIXED
