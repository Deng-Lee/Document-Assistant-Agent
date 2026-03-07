from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import PDABaseModel
from .bjj import BJJAnswerType
from .enums import ClarifySlot, ClarifyWho
from .locators import SourceLocator


class ClarifyRequest(PDABaseModel):
    who: ClarifyWho
    slot: ClarifySlot
    options: list[str] = Field(default_factory=list)
    template_id: str
    round: int
    why: str


class LiteraryAnchor(PDABaseModel):
    evidence_id: str
    doc_version_id: str
    locator: SourceLocator
    citation: str
    heading_path: list[str] = Field(default_factory=list)


class LiteraryFinalAnswer(PDABaseModel):
    text: str
    anchors: list[LiteraryAnchor] = Field(default_factory=list)


class ChatClarifyTurnResponse(PDABaseModel):
    response_type: Literal["clarify_request"] = "clarify_request"
    trace_id: str
    conversation_id: str
    response: ClarifyRequest


class ChatFinalTurnResponse(PDABaseModel):
    response_type: Literal["final_answer"] = "final_answer"
    trace_id: str
    conversation_id: str
    response: BJJAnswerType | LiteraryFinalAnswer


ChatTurnResponseType = ChatClarifyTurnResponse | ChatFinalTurnResponse
