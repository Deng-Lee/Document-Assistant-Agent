from __future__ import annotations

from pydantic import Field

from server.app.core import ClarifySlot, PDABaseModel


class ConversationState(PDABaseModel):
    pending_slot: ClarifySlot | None = None
    clarify_round: int = Field(default=0, ge=0, le=2)
    slots: dict[str, str] = Field(default_factory=dict)
    chat_summary: str | None = None
    coach_pending_slot: str | None = None
    coach_clarify_round: int = Field(default=0, ge=0, le=1)
