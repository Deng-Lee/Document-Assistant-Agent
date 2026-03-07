from __future__ import annotations

from server.app.core import ChunkRecord, RuntimeConfigSnapshot
from server.app.core.embeddings import build_text_embedding

from .vector_store import EmbeddingUpsertRecord


def build_embedding_upsert_records(
    chunks: list[ChunkRecord],
    runtime_config: RuntimeConfigSnapshot,
) -> list[EmbeddingUpsertRecord]:
    records: list[EmbeddingUpsertRecord] = []
    for chunk in chunks:
        source_text = chunk.clean_embed_text or chunk.clean_search_text or chunk.safe_summary or ""
        vector = build_text_embedding(source_text)
        if not any(vector):
            continue
        records.append(
            EmbeddingUpsertRecord(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                doc_version_id=chunk.doc_version_id,
                embedding_version_id=runtime_config.embedding_version_id,
                vector=vector,
                metadata=_build_metadata(chunk, runtime_config.embedding_version_id),
            )
        )
    return records


def _build_metadata(chunk: ChunkRecord, embedding_version_id: str) -> dict[str, str]:
    metadata = {
        "doc_id": chunk.doc_id,
        "doc_version_id": chunk.doc_version_id,
        "doc_type": chunk.doc_type.value,
        "embedding_version_id": embedding_version_id,
    }
    if chunk.metadata_digest.position:
        metadata["position"] = chunk.metadata_digest.position
    if chunk.metadata_digest.orientation:
        metadata["orientation"] = chunk.metadata_digest.orientation.value
    if chunk.metadata_digest.distance:
        metadata["distance"] = chunk.metadata_digest.distance.value
    if chunk.metadata_digest.goal:
        metadata["goal"] = chunk.metadata_digest.goal
    if chunk.metadata_digest.opponent_control:
        metadata["opponent_control"] = chunk.metadata_digest.opponent_control.value
    return metadata
