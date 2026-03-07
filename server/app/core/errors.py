from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from .base import PDABaseModel


class ErrorCode(str, Enum):
    INVALID_BJJ_FRONTMATTER = "INVALID_BJJ_FRONTMATTER"
    MISSING_BJJ_REQUIRED_FIELD = "MISSING_BJJ_REQUIRED_FIELD"
    INVALID_BJJ_ENUM = "INVALID_BJJ_ENUM"
    INVALID_CHAT_PLAN = "INVALID_CHAT_PLAN"
    INVALID_CLARIFY_RESPONSE = "INVALID_CLARIFY_RESPONSE"
    INVALID_BJJ_OUTPUT = "INVALID_BJJ_OUTPUT"
    INVALID_CITATION = "INVALID_CITATION"
    INVALID_TRACE_PAYLOAD = "INVALID_TRACE_PAYLOAD"
    INVALID_RUNTIME_CONFIG = "INVALID_RUNTIME_CONFIG"
    UNSUPPORTED_MODEL_VARIANT = "UNSUPPORTED_MODEL_VARIANT"


class APIErrorDetail(PDABaseModel):
    code: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
