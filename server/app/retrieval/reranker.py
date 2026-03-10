from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import Field, ValidationError

from server.app.core import ChunkMetadataDigest, ChunkRecord, PDABaseModel, RuntimeConfigSnapshot
from server.app.core.openai_chat import (
    ChatCompletionTransport,
    OpenAIChatCompletionTransport,
    OpenAITransportError,
    extract_chat_completion_text,
    resolve_openai_api_key,
    resolve_openai_base_url,
)


class CrossEncoderUnavailableError(RuntimeError):
    pass


class CrossEncoderError(RuntimeError):
    pass


class CrossEncoderSchemaError(RuntimeError):
    pass


class CrossEncoderScore(PDABaseModel):
    chunk_id: str
    score: float = Field(..., ge=0.0, le=1.0)


class CrossEncoderResponse(PDABaseModel):
    scores: list[CrossEncoderScore] = Field(default_factory=list)


@dataclass
class CrossEncoderCandidate:
    chunk_id: str
    doc_id: str
    doc_version_id: str
    doc_type: str
    text: str
    safe_summary: str
    metadata_digest: ChunkMetadataDigest
    original_rank: int


@dataclass
class RerankResult:
    applied: bool
    status: str
    provider_name: str | None
    model_name: str | None
    candidate_count: int
    ordered_chunk_ids: list[str]
    scores_by_chunk: dict[str, float]


class CrossEncoderReranker(Protocol):
    provider_name: str
    model_name: str | None
    is_ready: bool

    def rerank(self, query_text: str, candidates: list[CrossEncoderCandidate]) -> RerankResult: ...


class DeterministicMockCrossEncoderReranker:
    provider_name = "deterministic_mock_cross_encoder_v1"

    def __init__(self, model_name: str = "mock-cross-encoder-v1"):
        self.model_name = model_name
        self.is_ready = True

    def rerank(self, query_text: str, candidates: list[CrossEncoderCandidate]) -> RerankResult:
        scores_by_chunk = {
            candidate.chunk_id: _deterministic_overlap_score(query_text, candidate)
            for candidate in candidates
        }
        ordered = [
            candidate.chunk_id
            for candidate in sorted(
                candidates,
                key=lambda candidate: (
                    -scores_by_chunk[candidate.chunk_id],
                    candidate.original_rank,
                    candidate.chunk_id,
                ),
            )
        ]
        return RerankResult(
            applied=bool(candidates),
            status="success" if candidates else "skipped_no_candidates",
            provider_name=self.provider_name,
            model_name=self.model_name,
            candidate_count=len(candidates),
            ordered_chunk_ids=ordered,
            scores_by_chunk=scores_by_chunk,
        )


class OpenAICrossEncoderReranker:
    provider_name = "openai_cross_encoder_v1"

    def __init__(
        self,
        runtime_config: RuntimeConfigSnapshot,
        api_key: str | None = None,
        transport: ChatCompletionTransport | None = None,
    ):
        self.runtime_config = runtime_config
        self.api_key = resolve_openai_api_key(api_key)
        self.model_name = runtime_config.reranker.model or runtime_config.model_routing.base_model
        self.transport = transport or (
            OpenAIChatCompletionTransport(
                api_key=self.api_key,
                base_url=resolve_openai_base_url(),
            )
            if self.api_key
            else None
        )

    @property
    def is_ready(self) -> bool:
        return bool(self.api_key and self.transport is not None)

    def rerank(self, query_text: str, candidates: list[CrossEncoderCandidate]) -> RerankResult:
        if not candidates:
            return RerankResult(
                applied=False,
                status="skipped_no_candidates",
                provider_name=self.provider_name,
                model_name=self.model_name,
                candidate_count=0,
                ordered_chunk_ids=[],
                scores_by_chunk={},
            )
        if not self.api_key or self.transport is None:
            raise CrossEncoderUnavailableError("missing_openai_api_key")
        request_payload = _build_openai_payload(self.runtime_config, self.model_name, query_text, candidates)
        try:
            response = self.transport.create_chat_completion(request_payload)
            content = extract_chat_completion_text(response)
        except OpenAITransportError as exc:
            raise CrossEncoderError(str(exc)) from exc
        try:
            parsed = CrossEncoderResponse(**json.loads(content))
        except json.JSONDecodeError as exc:
            raise CrossEncoderSchemaError("invalid_json_response") from exc
        except ValidationError as exc:
            raise CrossEncoderSchemaError("invalid_cross_encoder_schema") from exc
        scores_by_chunk = {item.chunk_id: item.score for item in parsed.scores}
        missing = [candidate.chunk_id for candidate in candidates if candidate.chunk_id not in scores_by_chunk]
        if missing:
            raise CrossEncoderSchemaError("missing_candidate_scores")
        ordered = [
            candidate.chunk_id
            for candidate in sorted(
                candidates,
                key=lambda candidate: (
                    -scores_by_chunk[candidate.chunk_id],
                    candidate.original_rank,
                    candidate.chunk_id,
                ),
            )
        ]
        return RerankResult(
            applied=True,
            status="success",
            provider_name=self.provider_name,
            model_name=self.model_name,
            candidate_count=len(candidates),
            ordered_chunk_ids=ordered,
            scores_by_chunk=scores_by_chunk,
        )


def build_cross_encoder_candidates(chunks: list[ChunkRecord]) -> list[CrossEncoderCandidate]:
    return [
        CrossEncoderCandidate(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            doc_version_id=chunk.doc_version_id,
            doc_type=chunk.doc_type.value if hasattr(chunk.doc_type, "value") else str(chunk.doc_type),
            text=(chunk.clean_search_text or "")[:1200],
            safe_summary=(chunk.safe_summary or "")[:400],
            metadata_digest=chunk.metadata_digest,
            original_rank=index,
        )
        for index, chunk in enumerate(chunks, start=1)
    ]


def _build_openai_payload(
    runtime_config: RuntimeConfigSnapshot,
    model_name: str,
    query_text: str,
    candidates: list[CrossEncoderCandidate],
) -> dict[str, Any]:
    generation = runtime_config.generation.replan
    candidate_payload = [
        {
            "chunk_id": candidate.chunk_id,
            "doc_type": candidate.doc_type,
            "safe_summary": candidate.safe_summary,
            "text": candidate.text,
            "metadata": _metadata_payload(candidate.metadata_digest),
        }
        for candidate in candidates
    ]
    return {
        "model": model_name,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "query_text": query_text,
                        "candidates": candidate_payload,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": 0.0,
        "top_p": generation.get("top_p", 1.0),
        "max_tokens": min(int(generation.get("max_tokens", 800)), 1200),
        "response_format": {"type": "json_object"},
    }


def _system_prompt() -> str:
    return (
        "You are a retrieval cross-encoder reranker. "
        "Score each candidate chunk for direct relevance to the query from 0.0 to 1.0. "
        "Return exactly one JSON object with key `scores`, containing an array of "
        "{chunk_id, score}. Score every candidate once. Higher is better. "
        "Use only the candidate text, safe_summary, and metadata. "
        "Do not explain the scores."
    )


def _metadata_payload(metadata: ChunkMetadataDigest) -> dict[str, Any]:
    data = metadata.model_dump(mode="json") if hasattr(metadata, "model_dump") else metadata.dict()
    return {key: value for key, value in data.items() if value not in (None, "", [], {})}


def _deterministic_overlap_score(query_text: str, candidate: CrossEncoderCandidate) -> float:
    query_terms = _tokenize(query_text)
    if not query_terms:
        return 0.0
    body = " ".join(
        value
        for value in (
            candidate.text,
            candidate.safe_summary,
            candidate.metadata_digest.position or "",
            candidate.metadata_digest.goal or "",
            candidate.metadata_digest.orientation.value if candidate.metadata_digest.orientation else "",
            candidate.metadata_digest.distance.value if candidate.metadata_digest.distance else "",
        )
        if value
    )
    candidate_terms = _tokenize(body)
    overlap = len(query_terms & candidate_terms) / max(len(query_terms), 1)
    substring_hits = sum(1 for term in query_terms if len(term) > 2 and term in body.lower())
    substring_bonus = min(substring_hits / max(len(query_terms), 1), 1.0)
    return round(min(1.0, 0.7 * overlap + 0.3 * substring_bonus), 6)


def _tokenize(text: str) -> set[str]:
    return {token for token in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", text.lower()) if token}
