from __future__ import annotations

from server.app.core import ClarifyDirective, ClarifySlot, DateRange
from server.app.retrieval import QueryParser

from .state import ConversationState


QUESTION_TEMPLATE_IDS = {
    ClarifySlot.DOMAIN: "ASK_DOMAIN_V1",
    ClarifySlot.POSITION: "ASK_POSITION_V1",
    ClarifySlot.ORIENTATION: "ASK_ORIENTATION_V1",
    ClarifySlot.DISTANCE: "ASK_DISTANCE_V1",
    ClarifySlot.GOAL: "ASK_GOAL_V1",
    ClarifySlot.DATE_RANGE: "ASK_DATE_RANGE_V1",
    ClarifySlot.OPPONENT_CONTROL: "ASK_OPP_CONTROL_V1",
}


def try_resolve_pending_slot(user_message: str, state: ConversationState) -> tuple[bool, ConversationState]:
    if state.pending_slot is None:
        return False, state

    stripped = user_message.strip()
    updated = state.copy(deep=True)
    slot = state.pending_slot

    if slot == ClarifySlot.ORIENTATION and stripped in {"上位", "下位"}:
        updated.slots["orientation"] = stripped
    elif slot == ClarifySlot.DOMAIN:
        if stripped in {"训练", "BJJ"}:
            updated.slots["domain"] = "BJJ"
        elif stripped in {"写作", "阅读", "NOTES"}:
            updated.slots["domain"] = "NOTES"
        else:
            return False, state
    elif slot == ClarifySlot.DATE_RANGE:
        parsed = QueryParser._parse_date_range(stripped)
        if parsed is None:
            return False, state
        updated.slots["date_range"] = parsed.expression or stripped
    elif slot in {ClarifySlot.POSITION, ClarifySlot.GOAL, ClarifySlot.DISTANCE, ClarifySlot.OPPONENT_CONTROL}:
        if not stripped:
            return False, state
        updated.slots[slot.value] = stripped
    else:
        return False, state

    updated.pending_slot = None
    return True, updated


def clarify_template_id(slot: ClarifySlot) -> str:
    return QUESTION_TEMPLATE_IDS[slot]
