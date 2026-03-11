from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import Field, ValidationError

from server.app.core import ChunkMetadataDigest, ChunkRecord, PDABaseModel, RuntimeConfigSnapshot


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


class CrossEncoderBackend(Protocol):
    model_name: str
    is_ready: bool
    missing_dependencies: list[str]

    def score(self, query_text: str, candidates: list[CrossEncoderCandidate]) -> dict[str, float]: ...


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


class TransformersCrossEncoderBackend:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._tokenizer = None
        self._model = None
        self._torch = None
        self.missing_dependencies = self._resolve_missing_dependencies()

    @property
    def is_ready(self) -> bool:
        return not self.missing_dependencies

    def score(self, query_text: str, candidates: list[CrossEncoderCandidate]) -> dict[str, float]:
        if not self.is_ready:
            raise CrossEncoderUnavailableError(
                "missing_dependencies:" + ",".join(self.missing_dependencies)
            )
        if not candidates:
            return {}
        torch = self._load_torch()
        tokenizer = self._load_tokenizer()
        model = self._load_model()
        pairs = [(query_text, _candidate_text(candidate)) for candidate in candidates]
        encoded = tokenizer(
            pairs,
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=512,
        )
        model.eval()
        with torch.no_grad():
            outputs = model(**encoded)
        logits = outputs.logits
        if len(logits.shape) == 1:
            values = logits.tolist()
            normalized = [_sigmoid(value) for value in values]
        elif logits.shape[-1] == 1:
            values = logits.squeeze(-1).tolist()
            normalized = [_sigmoid(value) for value in values]
        else:
            probabilities = torch.softmax(logits, dim=-1)[:, -1].tolist()
            normalized = [float(value) for value in probabilities]
        return {
            candidate.chunk_id: round(float(score), 6)
            for candidate, score in zip(candidates, normalized, strict=False)
        }

    def _resolve_missing_dependencies(self) -> list[str]:
        missing: list[str] = []
        try:
            import torch  # noqa: F401
        except ImportError:
            missing.append("torch")
        try:
            import transformers  # noqa: F401
        except ImportError:
            missing.append("transformers")
        return missing

    def _load_torch(self):
        if self._torch is None:
            import torch

            self._torch = torch
        return self._torch

    def _load_tokenizer(self):
        if self._tokenizer is None:
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        return self._tokenizer

    def _load_model(self):
        if self._model is None:
            from transformers import AutoModelForSequenceClassification

            self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        return self._model


class HFCrossEncoderReranker:
    provider_name = "hf_cross_encoder_v1"

    def __init__(
        self,
        runtime_config: RuntimeConfigSnapshot,
        backend: CrossEncoderBackend | None = None,
    ):
        self.runtime_config = runtime_config
        self.model_name = runtime_config.reranker.model or runtime_config.model_routing.base_model
        self.backend = backend or TransformersCrossEncoderBackend(self.model_name)

    @property
    def is_ready(self) -> bool:
        return bool(self.backend.is_ready)

    @property
    def missing_dependencies(self) -> list[str]:
        return list(getattr(self.backend, "missing_dependencies", []))

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
        try:
            scores_by_chunk = self.backend.score(query_text, candidates)
        except CrossEncoderUnavailableError:
            raise
        except OSError as exc:
            raise CrossEncoderUnavailableError(f"model_load_error:{exc}") from exc
        except Exception as exc:
            raise CrossEncoderError(str(exc)) from exc
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


def _metadata_payload(metadata: ChunkMetadataDigest) -> dict[str, Any]:
    data = metadata.model_dump(mode="json") if hasattr(metadata, "model_dump") else metadata.dict()
    return {key: value for key, value in data.items() if value not in (None, "", [], {})}


def _candidate_text(candidate: CrossEncoderCandidate) -> str:
    metadata = _metadata_payload(candidate.metadata_digest)
    metadata_text = " ".join(f"{key}:{value}" for key, value in metadata.items())
    body = " ".join(
        part
        for part in (
            candidate.safe_summary,
            candidate.text,
            metadata_text,
        )
        if part
    )
    return body[:1600]


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


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + pow(2.718281828459045, -value))
