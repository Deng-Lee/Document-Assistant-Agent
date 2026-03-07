from __future__ import annotations

from server.app.core import (
    ClarifyDirective,
    ClarifySlot,
    DomainType,
    ExecutionPlan,
    ExecutionPlanExplain,
    NextAction,
    RetrievalFilters,
)
from server.app.core.retrieval import PlanCheck, ProbeStats, RetrievalPlan
from server.app.core.runtime_config import RuntimeConfigSnapshot

from .slot_parser import clarify_template_id
from .state import ConversationState


class DeterministicPlanBuilder:
    def build(
        self,
        user_message: str,
        state: ConversationState,
        plan_check: PlanCheck,
        probe_stats: ProbeStats,
        runtime_config: RuntimeConfigSnapshot,
    ) -> ExecutionPlan:
        if plan_check.need_clarify and state.clarify_round < runtime_config.orchestrator.clarify_round_limit:
            slot = plan_check.suggested_slot or ClarifySlot.DOMAIN
            return ExecutionPlan(
                task=plan_check.task_hint,
                domain=plan_check.domain,
                slots=state.slots,
                next_action=NextAction.CLARIFY,
                clarify=ClarifyDirective(
                    slot=slot,
                    question_template_id=clarify_template_id(slot),
                    options=self._clarify_options(slot, probe_stats),
                ),
                explain=ExecutionPlanExplain(reason_codes=plan_check.reason_codes, probe_used=True),
            )

        retrieval_filters = RetrievalFilters(
            doc_type=_domain_to_doc_type(plan_check.domain, state),
            position=state.slots.get("position"),
            orientation=state.slots.get("orientation"),
            distance=state.slots.get("distance"),
            goal=state.slots.get("goal"),
            opponent_control=state.slots.get("opponent_control"),
        )
        if "date_range" in state.slots:
            retrieval_filters.heading_hints.append(state.slots["date_range"])

        retrieval_plan = RetrievalPlan(
            doc_type=retrieval_filters.doc_type.value if retrieval_filters.doc_type else "ALL",
            filters=retrieval_filters,
            query_original=user_message,
            query_text=_render_query_text(user_message, state.slots),
            top_k=runtime_config.retrieval.full_top_k,
            per_doc_limit=runtime_config.retrieval.max_chunks_per_doc,
            token_budget=runtime_config.retrieval.token_budget,
        )
        reasons = list(plan_check.reason_codes)
        if plan_check.need_replan:
            reasons.append("LLM_REPLAN_DEFERRED_TO_DETERMINISTIC_FALLBACK")
        return ExecutionPlan(
            task=plan_check.task_hint,
            domain=plan_check.domain,
            slots=state.slots,
            next_action=NextAction.RETRIEVE,
            retrieval_plan=retrieval_plan,
            explain=ExecutionPlanExplain(reason_codes=reasons, probe_used=True),
        )

    @staticmethod
    def _clarify_options(slot: ClarifySlot, probe_stats: ProbeStats) -> list[str]:
        if slot == ClarifySlot.ORIENTATION:
            return ["上位", "下位"]
        if slot == ClarifySlot.DOMAIN:
            return ["训练", "写作/阅读"]
        if slot in {ClarifySlot.POSITION, ClarifySlot.GOAL}:
            counts = probe_stats.slot_value_hist.get(slot.value, {})
            ranked = [value for value, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)]
            return [value for value in ranked if value != "__missing__"][:3] + ["其他/不确定"]
        if slot == ClarifySlot.DISTANCE:
            return ["远距离", "近距离"]
        if slot == ClarifySlot.OPPONENT_CONTROL:
            return ["衣领", "袖子", "手腕", "裤子", "脚腕", "胯", "脖子", "不确定"]
        return []


def _domain_to_doc_type(domain: DomainType, state: ConversationState):
    from server.app.core import DocumentType

    if domain == DomainType.BJJ or state.slots.get("domain") == "BJJ":
        return DocumentType.BJJ
    if domain == DomainType.NOTES or state.slots.get("domain") == "NOTES":
        return DocumentType.NOTES
    return None


def _render_query_text(user_message: str, slots: dict[str, str]) -> str:
    if not slots:
        return user_message
    slot_text = " ".join(f"{key}:{value}" for key, value in slots.items() if value)
    return f"{user_message.strip()} {slot_text}".strip()
