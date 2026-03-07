from __future__ import annotations

from pathlib import Path

from pydantic import Field

from server.app.core import PDABaseModel


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
    """
    Thin adapter boundary for Chroma.

    V1 keeps the dependency behind this class so retrieval code does not import
    provider-specific APIs directly. The actual runtime can wire a real Chroma
    client when the dependency is installed.
    """

    def __init__(self, persist_directory: str | Path, collection_name: str):
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name

    def ensure_collection(self) -> None:
        self.persist_directory.mkdir(parents=True, exist_ok=True)

    def upsert_embeddings(self, records: list[EmbeddingUpsertRecord]) -> None:
        if not records:
            return
        raise NotImplementedError(
            "Chroma integration is intentionally kept behind an adapter boundary and will be implemented when retrieval wiring is added."
        )

    def delete_doc_version(self, doc_version_id: str) -> None:
        raise NotImplementedError(
            "Doc-version scoped vector deletion will be implemented with the concrete Chroma client."
        )

    def query(
        self,
        query_vector: list[float],
        top_k: int,
        where: dict[str, str] | None = None,
    ) -> list[VectorQueryMatch]:
        raise NotImplementedError(
            "Vector querying is deferred until the retrieval module wires a concrete Chroma client."
        )
