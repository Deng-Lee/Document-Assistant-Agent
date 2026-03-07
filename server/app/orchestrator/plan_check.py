from __future__ import annotations

from server.app.core import ClarifySlot, DomainType, PlanCheck, ProbeStats, TaskType
from server.app.core.runtime_config import RuntimeConfigSnapshot

from .state import ConversationState


LIST_INTENT_KEYWORDS = ("哪些", "列举", "汇总", "最近", "记录")


class PlanCheckService:
    def evaluate(
        self,
        probe_stats: ProbeStats,
        state: ConversationState,
        user_message: str,
        runtime_config: RuntimeConfigSnapshot,
    ) -> PlanCheck:
        reason_codes: list[str] = []
        domain_score = float(probe_stats.doc_type_hist.get("p_bjj", 0.0))
        thresholds = runtime_config.orchestrator

        if domain_score >= thresholds.domain_bjj_threshold:
            domain = DomainType.BJJ
        elif domain_score <= thresholds.domain_notes_threshold:
            domain = DomainType.NOTES
        else:
            domain = DomainType.MIXED
            reason_codes.append("DOMAIN_UNCLEAR")

        if probe_stats.time_signal.value and any(keyword in user_message for keyword in LIST_INTENT_KEYWORDS):
            task_hint = TaskType.RETRIEVE_SIMPLE
        elif domain == DomainType.BJJ:
            task_hint = TaskType.COACH_BJJ
        elif domain == DomainType.NOTES:
            task_hint = TaskType.COACH_LITERARY
        else:
            task_hint = TaskType.MIXED
            reason_codes.append("TASK_REQUIRES_REPLAN")

        need_clarify = False
        suggested_slot: ClarifySlot | None = None
        if task_hint == TaskType.COACH_BJJ:
            for slot in (ClarifySlot.POSITION, ClarifySlot.ORIENTATION, ClarifySlot.GOAL):
                if not state.slots.get(slot.value):
                    need_clarify = True
                    suggested_slot = slot
                    reason_codes.append(f"MISSING_CORE_{slot.value.upper()}")
                    break

            if (
                not need_clarify
                and probe_stats.slot_entropy > thresholds.slot_entropy_threshold
            ):
                suggested_slot = _highest_entropy_slot(probe_stats.slot_value_hist)
                need_clarify = suggested_slot is not None
                if suggested_slot is not None:
                    reason_codes.append("SLOT_ENTROPY_HIGH")

        need_replan = False
        if domain == DomainType.MIXED:
            need_replan = True
        if probe_stats.evidence_strength.value < thresholds.evidence_strength_threshold:
            need_replan = True
            reason_codes.append("EVIDENCE_STRENGTH_LOW")
        if state.clarify_round >= thresholds.clarify_round_limit and need_clarify:
            need_replan = True
            reason_codes.append("CLARIFY_BUDGET_EXHAUSTED")

        confidence_hint = max(
            0.0,
            min(
                1.0,
                0.5 * probe_stats.evidence_strength.value + 0.5 * abs(domain_score - 0.5) * 2.0,
            ),
        )

        return PlanCheck(
            domain=domain,
            task_hint=task_hint,
            need_replan=need_replan,
            need_clarify=need_clarify,
            suggested_slot=suggested_slot,
            confidence_hint=confidence_hint,
            reason_codes=reason_codes,
        )


def _highest_entropy_slot(slot_value_hist: dict[str, dict[str, int]]) -> ClarifySlot | None:
    order = {
        "position": ClarifySlot.POSITION,
        "orientation": ClarifySlot.ORIENTATION,
        "goal": ClarifySlot.GOAL,
    }
    ranked = sorted(slot_value_hist.items(), key=lambda item: _slot_dispersion(item[1]), reverse=True)
    for slot_name, counts in ranked:
        if _slot_dispersion(counts) > 0 and slot_name in order:
            return order[slot_name]
    return None


def _slot_dispersion(counts: dict[str, int]) -> float:
    distinct = sum(1 for value, count in counts.items() if count > 0 and value != "__missing__")
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return distinct / total
