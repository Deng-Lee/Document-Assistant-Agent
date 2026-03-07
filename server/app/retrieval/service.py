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
    TimeSignal,
)
from server.app.storage import DocumentRepository, VectorStore

from .fusion import reciprocal_rank_fusion
from .query_parser import QueryParser


class RetrievalOutcome(EvidencePack):
    retrieval_log: RetrievalLog
    probe_stats: ProbeStats | None = None


class RetrievalService:
    def __init__(self, document_repository: DocumentRepository, vector_store: VectorStore | None = None):
        self.document_repository = document_repository
        self.vector_store = vector_store
        self.query_parser = QueryParser()

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
        dense_hits: list[ChunkRecord] = []
        dense_enabled = self.vector_store is not None

        fused_ids = reciprocal_rank_fusion(
            [
                [chunk.chunk_id for chunk in structured_hits],
                [chunk.chunk_id for chunk in bm25_hits],
                [chunk.chunk_id for chunk in dense_hits],
            ]
        )
        all_chunks = {chunk.chunk_id: chunk for chunk in structured_hits + bm25_hits + dense_hits}
        selected_chunks = self._apply_diversity_limit(
            fused_ids=fused_ids,
            chunk_map=all_chunks,
            per_doc_limit=retrieval_plan.per_doc_limit,
            top_k=retrieval_plan.top_k,
        )
        evidence_items = self._build_evidence_pack(selected_chunks, structured_hits, bm25_hits, dense_hits)
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
            discarded_after_filter=max(len(fused_ids) - len(selected_chunks), 0),
            notes=["dense_disabled" if not dense_enabled else "dense_enabled"],
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
        fused_ids: list[str],
        chunk_map: dict[str, ChunkRecord],
        per_doc_limit: int,
        top_k: int,
    ) -> list[ChunkRecord]:
        doc_counts: dict[str, int] = {}
        selected: list[ChunkRecord] = []
        for chunk_id in fused_ids:
            chunk = chunk_map.get(chunk_id)
            if chunk is None:
                continue
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
    ) -> list[EvidencePackItem]:
        structured_ranks = {chunk.chunk_id: index for index, chunk in enumerate(structured_hits, start=1)}
        bm25_ranks = {chunk.chunk_id: index for index, chunk in enumerate(bm25_hits, start=1)}
        dense_ranks = {chunk.chunk_id: index for index, chunk in enumerate(dense_hits, start=1)}
        return [
            EvidencePackItem(
                evidence_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                doc_version_id=chunk.doc_version_id,
                locator=chunk.locator,
                safe_summary=chunk.safe_summary or "",
                metadata_digest=chunk.metadata_digest,
                rank_signals=RankSignals(
                    structured_filter_applied=chunk.chunk_id in structured_ranks,
                    bm25_rank=bm25_ranks.get(chunk.chunk_id),
                    dense_rank=dense_ranks.get(chunk.chunk_id),
                    rrf_rank=index,
                ),
            )
            for index, chunk in enumerate(selected_chunks, start=1)
        ]

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
