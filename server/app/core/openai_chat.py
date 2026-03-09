from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import error, request


class OpenAITransportError(RuntimeError):
    pass


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
            raise OpenAITransportError(f"openai_http_error:{exc.code}:{body}") from exc
        except error.URLError as exc:
            raise OpenAITransportError(f"openai_transport_error:{exc.reason}") from exc


def resolve_openai_api_key(explicit_api_key: str | None = None) -> str | None:
    return explicit_api_key or os.getenv("OPENAI_API_KEY")


def resolve_openai_base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")


def extract_chat_completion_text(response: dict[str, Any]) -> str:
    choices = response.get("choices", [])
    if not choices:
        raise OpenAITransportError("missing_choices")
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
    raise OpenAITransportError("missing_message_content")
