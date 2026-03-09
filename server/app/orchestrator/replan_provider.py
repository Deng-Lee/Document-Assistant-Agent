from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import error, request

from pydantic import Field, ValidationError, root_validator

from server.app.core import (
    ClarifySlot,
    DomainType,
    NextAction,
    PDABaseModel,
    PlanCheck,
    ProbeStats,
    RuntimeConfigSnapshot,
    TaskType,
)


class ReplanProviderUnavailableError(RuntimeError):
    pass


class ReplanProviderError(RuntimeError):
    pass


class ReplanProviderSchemaError(RuntimeError):
    pass


class ReplanProviderRequest(PDABaseModel):
    user_message: str
    state_slots: dict[str, str] = Field(default_factory=dict)
    clarify_round: int = 0
    pending_slot: ClarifySlot | None = None
    plan_check: PlanCheck
    probe_stats: ProbeStats | None = None
    runtime_config: RuntimeConfigSnapshot


class LLMReplanOutput(PDABaseModel):
    task: TaskType
    domain: DomainType
    next_action: NextAction
    slot_updates: dict[str, str] = Field(default_factory=dict)
    query_text: str | None = None
    clarify_slot: ClarifySlot | None = None
    clarify_options: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)

    @root_validator
    def _validate_shape(cls, values: dict[str, Any]) -> dict[str, Any]:
        next_action = values.get("next_action")
        if next_action == NextAction.WRITE_FLOW:
            raise ValueError("replan cannot emit WRITE_FLOW")
        if next_action == NextAction.RETRIEVE and not (values.get("query_text") or "").strip():
            raise ValueError("RETRIEVE replan output requires query_text")
        if next_action == NextAction.CLARIFY and values.get("clarify_slot") is None:
            raise ValueError("CLARIFY replan output requires clarify_slot")
        return values


class ReplanProvider(Protocol):
    def generate(self, provider_request: ReplanProviderRequest) -> LLMReplanOutput: ...


class ChatCompletionTransport(Protocol):
    def create_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class OpenAIChatCompletionTransport:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: int = 20

    def create_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        http_request = request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ReplanProviderError(f"openai_http_error:{exc.code}:{body}") from exc
        except error.URLError as exc:
            raise ReplanProviderError(f"openai_transport_error:{exc.reason}") from exc


class OpenAIReplanProvider:
    def __init__(
        self,
        api_key: str | None = None,
        transport: ChatCompletionTransport | None = None,
    ):
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.api_key = resolved_key
        self.transport = transport or (
            OpenAIChatCompletionTransport(api_key=resolved_key, base_url=base_url)
            if resolved_key
            else None
        )

    def generate(self, provider_request: ReplanProviderRequest) -> LLMReplanOutput:
        if not self.api_key or self.transport is None:
            raise ReplanProviderUnavailableError("missing_openai_api_key")
        payload = _build_openai_payload(provider_request)
        response = self.transport.create_chat_completion(payload)
        raw_content = _extract_content_text(response)
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ReplanProviderSchemaError("invalid_json_response") from exc
        try:
            return LLMReplanOutput(**parsed)
        except ValidationError as exc:
            raise ReplanProviderSchemaError("invalid_replan_schema") from exc


def _build_openai_payload(provider_request: ReplanProviderRequest) -> dict[str, Any]:
    generation = provider_request.runtime_config.generation.replan
    return {
        "model": provider_request.runtime_config.model_routing.base_model,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {
                "role": "user",
                "content": json.dumps(_prompt_payload(provider_request), ensure_ascii=False),
            },
        ],
        "temperature": generation.get("temperature", 0.1),
        "top_p": generation.get("top_p", 1.0),
        "max_tokens": generation.get("max_tokens", 800),
        "response_format": {"type": "json_object"},
    }


def _system_prompt() -> str:
    return (
        "You are the Orchestrator replan module for a Personal Document Assistant. "
        "Return exactly one JSON object with keys: "
        "task, domain, next_action, slot_updates, query_text, clarify_slot, clarify_options, reason_codes. "
        "Allowed task values: RETRIEVE_SIMPLE, COACH_BJJ, COACH_LITERARY, META, MIXED. "
        "Allowed domain values: BJJ, NOTES, MIXED. "
        "Allowed next_action values: RETRIEVE or CLARIFY. Never emit WRITE_FLOW. "
        "If next_action is RETRIEVE, query_text must be a non-empty retrieval-friendly rewrite. "
        "If next_action is CLARIFY, clarify_slot must be one of domain, position, orientation, distance, goal, date_range, opponent_control. "
        "Do not ask free-text questions; use clarify_slot and clarify_options only. "
        "Keep reason_codes short and machine-readable."
    )


def _prompt_payload(provider_request: ReplanProviderRequest) -> dict[str, Any]:
    probe_stats = provider_request.probe_stats
    return {
        "user_message": provider_request.user_message,
        "state_slots": provider_request.state_slots,
        "clarify_round": provider_request.clarify_round,
        "pending_slot": provider_request.pending_slot.value if provider_request.pending_slot is not None else None,
        "plan_check": _model_dump(provider_request.plan_check),
        "probe_stats": _model_dump(probe_stats) if probe_stats is not None else None,
        "runtime_limits": {
            "clarify_round_limit": provider_request.runtime_config.orchestrator.clarify_round_limit,
            "full_top_k": provider_request.runtime_config.retrieval.full_top_k,
            "per_doc_limit": provider_request.runtime_config.retrieval.max_chunks_per_doc,
            "token_budget": provider_request.runtime_config.retrieval.token_budget,
            "prompt_version": provider_request.runtime_config.prompt_versions.replan,
        },
    }


def _extract_content_text(response: dict[str, Any]) -> str:
    choices = response.get("choices", [])
    if not choices:
        raise ReplanProviderError("missing_choices")
    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    fragments.append(text)
        joined = "".join(fragments).strip()
        if joined:
            return joined
    raise ReplanProviderError("missing_message_content")


def _model_dump(model: Any) -> Any:
    if model is None:
        return None
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    if hasattr(model, "dict"):
        return model.dict()
    return model
