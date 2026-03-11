from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field

from server.app.core import (
    ChunkMetadataDigest,
    ChunkRecord,
    DocumentType,
    EvidencePack,
    EvidencePackItem,
    EvidenceStrength,
    ProbeHit,
    ProbeStats,
    RankSignals,
    RetrievalFilters,
    RetrievalLog,
    RetrievalPlan,
    RuntimeConfigSnapshot,
    TimeSignal,
    build_runtime_config,
    build_text_embedding,
)
from server.app.storage import DocumentRepository, VectorStore

from .fusion import reciprocal_rank_fusion
from .query_parser import QueryParser
from .reranker import (
    CrossEncoderError,
    CrossEncoderReranker,
    CrossEncoderSchemaError,
    CrossEncoderUnavailableError,
    DeterministicMockCrossEncoderReranker,
    HFCrossEncoderReranker,
    RerankResult,
    build_cross_encoder_candidates,
)


class RetrievalOutcome(EvidencePack):
    retrieval_log: RetrievalLog
    probe_stats: ProbeStats | None = None


class RetrievalService:
    def __init__(
        self,
        document_repository: DocumentRepository,
        vector_store: VectorStore | None = None,
        runtime_config: RuntimeConfigSnapshot | None = None,
        reranker: CrossEncoderReranker | None = None,
    ):
        self.document_repository = document_repository
        self.vector_store = vector_store
        self.runtime_config = runtime_config or build_runtime_config()
        self.query_parser = QueryParser()
        self.reranker = reranker or self._default_reranker(self.runtime_config)

    def retrieve(
        self,
        query_text: str,
        filters_hint: RetrievalFilters | None = None,
        mode: str = "full",
        top_k: int | None = None,
    ) -> RetrievalOutcome:
        retrieval_plan = self.query_parser.parse(
            query_text=query_text,
            filters_hint=filters_hint,
            top_k=top_k or (12 if mode == "probe" else 24),
        )
        filter_payload = self._filters_to_payload(retrieval_plan.filters)

        structured_hits = self.document_repository.structured_filter_chunks(filter_payload, limit=retrieval_plan.top_k)
        bm25_hits = self._run_bm25(retrieval_plan.query_text, retrieval_plan.top_k, filter_payload)
        dense_enabled = self.vector_store is not None
        dense_hits = self._run_dense(retrieval_plan.query_text, retrieval_plan.top_k, filter_payload) if dense_enabled else []

        fused_ids = reciprocal_rank_fusion(
            [
                [chunk.chunk_id for chunk in structured_hits],
                [chunk.chunk_id for chunk in bm25_hits],
                [chunk.chunk_id for chunk in dense_hits],
            ]
        )
        all_chunks = {chunk.chunk_id: chunk for chunk in structured_hits + bm25_hits + dense_hits}
        fused_chunks = [all_chunks[chunk_id] for chunk_id in fused_ids if chunk_id in all_chunks]
        rerank_result = self._run_rerank(retrieval_plan.query_text, fused_chunks, retrieval_plan.top_k)
        ranked_chunks = self._ordered_chunks(fused_chunks, rerank_result)
        selected_chunks = self._apply_diversity_limit(
            ranked_chunks=ranked_chunks,
            per_doc_limit=retrieval_plan.per_doc_limit,
            top_k=retrieval_plan.top_k,
        )
        evidence_items = self._build_evidence_pack(
            selected_chunks,
            structured_hits,
            bm25_hits,
            dense_hits,
            rerank_result,
        )
        evidence_pack = EvidencePack(
            items=evidence_items,
            token_budget=retrieval_plan.token_budget,
            per_doc_limit=retrieval_plan.per_doc_limit,
        )
        retrieval_log = RetrievalLog(
            retrieval_plan=retrieval_plan,
            structured_filter_count=len(structured_hits),
            bm25_count=len(bm25_hits),
            dense_count=len(dense_hits),
            rerank_applied=rerank_result.applied,
            rerank_status=rerank_result.status,
            rerank_provider_name=rerank_result.provider_name,
            rerank_model=rerank_result.model_name,
            rerank_candidate_count=rerank_result.candidate_count,
            discarded_after_filter=max(len(fused_ids) - len(selected_chunks), 0),
            notes=[
                "dense_disabled" if not dense_enabled else "dense_enabled",
                f"rerank_status:{rerank_result.status}",
            ],
        )
        probe_stats = self._build_probe_stats(query_text, retrieval_plan.filters, selected_chunks, evidence_items) if mode == "probe" else None
        return RetrievalOutcome(
            items=evidence_items,
            token_budget=evidence_pack.token_budget,
            per_doc_limit=evidence_pack.per_doc_limit,
            retrieval_log=retrieval_log,
            probe_stats=probe_stats,
        )

    def _run_bm25(self, query_text: str, top_k: int, filter_payload: dict[str, object]) -> list[ChunkRecord]:
        sanitized = " ".join(token for token in query_text.replace("/", " ").split() if token)
        if not sanitized:
            return []
        try:
            return self.document_repository.bm25_search(sanitized, limit=top_k, filters=filter_payload)
        except Exception:
            return []

    def _run_dense(self, query_text: str, top_k: int, filter_payload: dict[str, object]) -> list[ChunkRecord]:
        if self.vector_store is None:
            return []
        query_vector = build_text_embedding(query_text)
        if not any(query_vector):
            return []
        where = {"embedding_version_id": self.runtime_config.embedding_version_id}
        for key in ("doc_type", "doc_version_id", "position", "orientation", "distance", "goal", "opponent_control"):
            value = filter_payload.get(key)
            if value is None:
                continue
            where[key] = value.value if hasattr(value, "value") else str(value)
        matches = self.vector_store.query(query_vector=query_vector, top_k=max(top_k * 3, top_k), where=where)
        resolved: list[ChunkRecord] = []
        seen: set[str] = set()
        for match in matches:
            chunk = self.document_repository.get_chunk(match.chunk_id)
            if chunk is None or chunk.chunk_id in seen:
                continue
            if not self._matches_date_range(chunk, filter_payload.get("date_range")):
                continue
            resolved.append(chunk)
            seen.add(chunk.chunk_id)
            if len(resolved) >= top_k:
                break
        return resolved

    @staticmethod
    def _filters_to_payload(filters: RetrievalFilters) -> dict[str, object]:
        payload: dict[str, object] = {}
        if filters.doc_type is not None:
            payload["doc_type"] = filters.doc_type
        if filters.date_range is not None:
            payload["date_range"] = {
                "start": filters.date_range.start,
                "end": filters.date_range.end,
            }
        for name in ("position", "orientation", "distance", "goal", "opponent_control"):
            value = getattr(filters, name)
            if value:
                payload[name] = value
        return payload

    @staticmethod
    def _apply_diversity_limit(
        ranked_chunks: list[ChunkRecord],
        per_doc_limit: int,
        top_k: int,
    ) -> list[ChunkRecord]:
        doc_counts: dict[str, int] = {}
        selected: list[ChunkRecord] = []
        for chunk in ranked_chunks:
            if doc_counts.get(chunk.doc_id, 0) >= per_doc_limit:
                continue
            selected.append(chunk)
            doc_counts[chunk.doc_id] = doc_counts.get(chunk.doc_id, 0) + 1
            if len(selected) >= top_k:
                break
        return selected

    @staticmethod
    def _build_evidence_pack(
        selected_chunks: list[ChunkRecord],
        structured_hits: list[ChunkRecord],
        bm25_hits: list[ChunkRecord],
        dense_hits: list[ChunkRecord],
        rerank_result: RerankResult,
    ) -> list[EvidencePackItem]:
        structured_ranks = {chunk.chunk_id: index for index, chunk in enumerate(structured_hits, start=1)}
        bm25_ranks = {chunk.chunk_id: index for index, chunk in enumerate(bm25_hits, start=1)}
        dense_ranks = {chunk.chunk_id: index for index, chunk in enumerate(dense_hits, start=1)}
        cross_encoder_ranks = {
            chunk_id: index for index, chunk_id in enumerate(rerank_result.ordered_chunk_ids, start=1)
        } if rerank_result.applied else {}
        return [
            EvidencePackItem(
                evidence_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                doc_version_id=chunk.doc_version_id,
                locator=chunk.locator,
                safe_summary=chunk.safe_summary or "",
                excerpt_snapshot=(chunk.clean_search_text or "")[:240] or None,
                metadata_digest=chunk.metadata_digest,
                rank_signals=RankSignals(
                    structured_filter_applied=chunk.chunk_id in structured_ranks,
                    bm25_rank=bm25_ranks.get(chunk.chunk_id),
                    dense_rank=dense_ranks.get(chunk.chunk_id),
                    rrf_rank=index,
                    cross_encoder_rank=cross_encoder_ranks.get(chunk.chunk_id),
                    cross_encoder_score=rerank_result.scores_by_chunk.get(chunk.chunk_id),
                ),
            )
            for index, chunk in enumerate(selected_chunks, start=1)
        ]

    def provider_status(self) -> dict[str, object]:
        provider_name = self.reranker.__class__.__name__ if self.reranker is not None else None
        transport = getattr(self.reranker, "transport", None)
        return {
            "profile_name": self.runtime_config.model_routing.profile_name,
            "provider_name": provider_name,
            "configured": bool(getattr(self.reranker, "is_ready", False)),
            "base_url": getattr(transport, "base_url", None),
            "model": getattr(self.reranker, "model_name", None),
            "enabled": self.runtime_config.reranker.enabled,
            "missing_dependencies": list(getattr(self.reranker, "missing_dependencies", [])),
        }

    def _run_rerank(self, query_text: str, fused_chunks: list[ChunkRecord], top_k: int) -> RerankResult:
        if not self.runtime_config.reranker.enabled or self.reranker is None:
            return RerankResult(
                applied=False,
                status="disabled",
                provider_name=getattr(self.reranker, "provider_name", None) if self.reranker is not None else None,
                model_name=getattr(self.reranker, "model_name", None),
                candidate_count=0,
                ordered_chunk_ids=[chunk.chunk_id for chunk in fused_chunks],
                scores_by_chunk={},
            )
        if not fused_chunks:
            return RerankResult(
                applied=False,
                status="skipped_no_candidates",
                provider_name=getattr(self.reranker, "provider_name", self.reranker.__class__.__name__),
                model_name=getattr(self.reranker, "model_name", None),
                candidate_count=0,
                ordered_chunk_ids=[],
                scores_by_chunk={},
            )
        candidate_limit = min(
            len(fused_chunks),
            max(top_k * self.runtime_config.reranker.candidate_pool_multiplier, top_k),
            self.runtime_config.reranker.max_candidates,
        )
        candidates = build_cross_encoder_candidates(fused_chunks[:candidate_limit])
        try:
            result = self.reranker.rerank(query_text, candidates)
        except CrossEncoderUnavailableError:
            status = "provider_unavailable"
        except CrossEncoderSchemaError:
            status = "schema_invalid"
        except CrossEncoderError:
            status = "provider_error"
        else:
            if result.ordered_chunk_ids:
                remainder = [chunk.chunk_id for chunk in fused_chunks[candidate_limit:]]
                result.ordered_chunk_ids = result.ordered_chunk_ids + remainder
            return result
        return RerankResult(
            applied=False,
            status=status,
            provider_name=getattr(self.reranker, "provider_name", self.reranker.__class__.__name__),
            model_name=getattr(self.reranker, "model_name", None),
            candidate_count=len(candidates),
            ordered_chunk_ids=[chunk.chunk_id for chunk in fused_chunks],
            scores_by_chunk={},
        )

    @staticmethod
    def _ordered_chunks(fused_chunks: list[ChunkRecord], rerank_result: RerankResult) -> list[ChunkRecord]:
        chunk_map = {chunk.chunk_id: chunk for chunk in fused_chunks}
        return [chunk_map[chunk_id] for chunk_id in rerank_result.ordered_chunk_ids if chunk_id in chunk_map]

    @staticmethod
    def _default_reranker(runtime_config: RuntimeConfigSnapshot) -> CrossEncoderReranker | None:
        if not runtime_config.reranker.enabled:
            return None
        if runtime_config.model_routing.profile_name == "fake":
            return DeterministicMockCrossEncoderReranker(
                model_name=runtime_config.reranker.model or "mock-cross-encoder-v1"
            )
        if runtime_config.reranker.provider in {"huggingface", "hf_cross_encoder"}:
            return HFCrossEncoderReranker(runtime_config)
        return None

    @staticmethod
    def _build_probe_stats(
        query_text: str,
        filters: RetrievalFilters,
        selected_chunks: list[ChunkRecord],
        evidence_items: list[EvidencePackItem],
    ) -> ProbeStats:
        total = len(selected_chunks)
        bjj_count = sum(1 for chunk in selected_chunks if chunk.doc_type == DocumentType.BJJ)
        notes_count = sum(1 for chunk in selected_chunks if chunk.doc_type == DocumentType.NOTES)
        slot_hist = _slot_histograms(selected_chunks)
        slot_entropy = _mean_slot_entropy(slot_hist, total) if total else 0.0
        headness = 1.0 if total <= 1 else max(0.0, 1.0 - ((min(total, 3) - 1) / max(total, 1)))
        coherence = max(0.0, 1.0 - slot_entropy)
        evidence_strength_value = max(0.0, min(1.0, 0.6 * headness + 0.4 * coherence))
        return ProbeStats(
            k=total,
            probe_query_text=query_text,
            probe_filters=filters,
            hits=[
                ProbeHit(
                    chunk_id=item.evidence_id,
                    doc_type=selected_chunks[index].doc_type,
                    doc_version_id=item.doc_version_id,
                    metadata_digest=item.metadata_digest,
                    safe_summary=item.safe_summary,
                    ranks=item.rank_signals,
                )
                for index, item in enumerate(evidence_items)
            ],
            doc_type_hist={
                "BJJ": bjj_count,
                "NOTES": notes_count,
                "p_bjj": (bjj_count / total) if total else 0.0,
                "p_notes": (notes_count / total) if total else 0.0,
            },
            slot_value_hist=slot_hist,
            slot_entropy=slot_entropy,
            evidence_strength=EvidenceStrength(
                value=evidence_strength_value,
                headness=headness,
                coherence=coherence,
            ),
            time_signal=TimeSignal(value=filters.date_range is not None, date_range=filters.date_range),
        )

    @staticmethod
    def _matches_date_range(chunk: ChunkRecord, date_range: dict[str, object] | None) -> bool:
        if not isinstance(date_range, dict):
            return True
        record_date = chunk.metadata_digest.date
        if record_date is None:
            return False
        start = date_range.get("start")
        end = date_range.get("end")
        if start and record_date < start:
            return False
        if end and record_date > end:
            return False
        return True


def _slot_histograms(chunks: list[ChunkRecord]) -> dict[str, dict[str, int]]:
    histograms: dict[str, dict[str, int]] = {"position": {}, "orientation": {}, "goal": {}}
    for chunk in chunks:
        digest: ChunkMetadataDigest = chunk.metadata_digest
        for slot, value in (
            ("position", digest.position),
            ("orientation", digest.orientation.value if digest.orientation else None),
            ("goal", digest.goal),
        ):
            key = value or "__missing__"
            histograms[slot][key] = histograms[slot].get(key, 0) + 1
    return histograms


def _mean_slot_entropy(slot_hist: dict[str, dict[str, int]], total: int) -> float:
    if total == 0:
        return 0.0
    entropies: list[float] = []
    for counts in slot_hist.values():
        probabilities = [count / total for count in counts.values() if count > 0]
        if len(probabilities) <= 1:
            entropies.append(0.0)
            continue
        entropy = 0.0
        for probability in probabilities:
            entropy -= probability * _safe_log(probability)
        entropies.append(entropy / _safe_log(len(probabilities)))
    return sum(entropies) / len(entropies) if entropies else 0.0


def _safe_log(value: float) -> float:
    from math import log

    return log(value) if value > 0 else 0.0
