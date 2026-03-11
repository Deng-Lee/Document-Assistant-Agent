from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from pydantic import Field

from server.app.core import PDABaseModel

try:
    import numpy as np

    if not hasattr(np, "NaN"):
        np.NaN = np.nan
except Exception:
    pass

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings

logging.getLogger("chromadb.telemetry.posthog").disabled = True


class EmbeddingUpsertRecord(PDABaseModel):
    chunk_id: str
    doc_id: str
    doc_version_id: str
    embedding_version_id: str
    vector: list[float] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class VectorQueryMatch(PDABaseModel):
    chunk_id: str
    score: float
    metadata: dict[str, str] = Field(default_factory=dict)


class ChromaVectorStoreAdapter:
    """Persistent Chroma adapter with per-embedding-version collection isolation."""

    def __init__(self, persist_directory: str | Path, collection_name: str):
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self._client: chromadb.ClientAPI | None = None
        self._collections: dict[str, Collection] = {}

    def ensure_collection(self) -> None:
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self._get_client()

    def upsert_embeddings(self, records: list[EmbeddingUpsertRecord]) -> None:
        if not records:
            return
        self.ensure_collection()
        batches: dict[str, list[EmbeddingUpsertRecord]] = {}
        for record in records:
            batches.setdefault(record.embedding_version_id, []).append(record)
        for embedding_version_id, batch in batches.items():
            collection = self._get_or_create_collection(embedding_version_id)
            collection.upsert(
                ids=[record.chunk_id for record in batch],
                embeddings=[record.vector for record in batch],
                metadatas=[_metadata_for_chroma(record) for record in batch],
            )

    def delete_doc_version(self, doc_version_id: str, embedding_version_id: str | None = None) -> None:
        self.ensure_collection()
        collections = (
            [self._get_or_create_collection(embedding_version_id)]
            if embedding_version_id
            else self._iter_managed_collections()
        )
        for collection in collections:
            collection.delete(where={"doc_version_id": doc_version_id})

    def query(
        self,
        query_vector: list[float],
        top_k: int,
        where: dict[str, str] | None = None,
    ) -> list[VectorQueryMatch]:
        self.ensure_collection()
        if top_k <= 0 or not query_vector:
            return []
        embedding_version_id = (where or {}).get("embedding_version_id")
        if not embedding_version_id:
            return []
        collection = self._find_collection(embedding_version_id)
        if collection is None or collection.count() <= 0:
            return []
        chroma_where = _normalize_where(where)
        raw = collection.query(
            query_embeddings=[query_vector],
            n_results=min(top_k, collection.count()),
            where=chroma_where or None,
            include=["metadatas", "distances"],
        )
        ids = raw.get("ids", [[]])
        distances = raw.get("distances", [[]])
        metadatas = raw.get("metadatas", [[]])
        matches: list[VectorQueryMatch] = []
        for chunk_id, distance, metadata in zip(ids[0], distances[0], metadatas[0], strict=False):
            score = _distance_to_score(distance)
            matches.append(
                VectorQueryMatch(
                    chunk_id=chunk_id,
                    score=score,
                    metadata={str(key): str(value) for key, value in (metadata or {}).items()},
                )
            )
        matches.sort(key=lambda item: (-item.score, item.chunk_id))
        return matches

    def _get_client(self) -> chromadb.ClientAPI:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(
                    is_persistent=True,
                    persist_directory=str(self.persist_directory),
                    anonymized_telemetry=False,
                ),
            )
        return self._client

    def _get_or_create_collection(self, embedding_version_id: str) -> Collection:
        if embedding_version_id not in self._collections:
            client = self._get_client()
            self._collections[embedding_version_id] = client.get_or_create_collection(
                name=_collection_name(self.collection_name, embedding_version_id),
                metadata={
                    "embedding_version_id": embedding_version_id,
                    "hnsw:space": "cosine",
                },
            )
        return self._collections[embedding_version_id]

    def _find_collection(self, embedding_version_id: str) -> Collection | None:
        if embedding_version_id in self._collections:
            return self._collections[embedding_version_id]
        client = self._get_client()
        try:
            collection = client.get_collection(name=_collection_name(self.collection_name, embedding_version_id))
        except Exception:
            return None
        self._collections[embedding_version_id] = collection
        return collection

    def _iter_managed_collections(self) -> list[Collection]:
        client = self._get_client()
        collections = client.list_collections()
        return [
            collection
            for collection in collections
            if collection.name == self.collection_name or collection.name.startswith(f"{self.collection_name}-")
        ]


def _collection_name(base_name: str, embedding_version_id: str) -> str:
    digest = hashlib.sha1(embedding_version_id.encode("utf-8")).hexdigest()[:12]
    return f"{base_name}-{digest}"


def _normalize_where(where: dict[str, str] | None) -> dict[str, str]:
    if not where:
        return {}
    clauses = [{str(key): str(value)} for key, value in where.items() if value is not None]
    if not clauses:
        return {}
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _metadata_for_chroma(record: EmbeddingUpsertRecord) -> dict[str, str]:
    metadata = {
        "chunk_id": record.chunk_id,
        "doc_id": record.doc_id,
        "doc_version_id": record.doc_version_id,
        "embedding_version_id": record.embedding_version_id,
    }
    metadata.update({str(key): str(value) for key, value in record.metadata.items()})
    return metadata


def _distance_to_score(distance: float | None) -> float:
    if distance is None:
        return 0.0
    return 1.0 / (1.0 + max(float(distance), 0.0))
