from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field

from server.app.core import PDABaseModel, cosine_similarity


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
    Persistent local vector adapter kept behind the Chroma-shaped boundary.

    The repo does not depend on the external Chroma package during tests, so the
    adapter stores embeddings as JSON and preserves the same call surface that a
    real Chroma client would implement later.
    """

    def __init__(self, persist_directory: str | Path, collection_name: str):
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self.collection_path = self.persist_directory / f"{collection_name}.json"

    def ensure_collection(self) -> None:
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        if not self.collection_path.exists():
            self.collection_path.write_text("[]", encoding="utf-8")

    def upsert_embeddings(self, records: list[EmbeddingUpsertRecord]) -> None:
        if not records:
            return
        self.ensure_collection()
        existing = self._load_rows()
        record_map = {
            (row["chunk_id"], row["embedding_version_id"]): row
            for row in existing
        }
        for record in records:
            record_map[(record.chunk_id, record.embedding_version_id)] = _dump_record(record)
        self._write_rows(list(record_map.values()))

    def delete_doc_version(self, doc_version_id: str) -> None:
        self.ensure_collection()
        kept_rows = [
            row
            for row in self._load_rows()
            if row.get("doc_version_id") != doc_version_id
        ]
        self._write_rows(kept_rows)

    def query(
        self,
        query_vector: list[float],
        top_k: int,
        where: dict[str, str] | None = None,
    ) -> list[VectorQueryMatch]:
        self.ensure_collection()
        matches: list[VectorQueryMatch] = []
        for row in self._load_rows():
            if not _matches_where(row, where):
                continue
            score = cosine_similarity(query_vector, row.get("vector", []))
            matches.append(
                VectorQueryMatch(
                    chunk_id=row["chunk_id"],
                    score=score,
                    metadata=row.get("metadata", {}),
                )
            )
        matches.sort(key=lambda item: (-item.score, item.chunk_id))
        return matches[:top_k]

    def _load_rows(self) -> list[dict]:
        if not self.collection_path.exists():
            return []
        content = self.collection_path.read_text(encoding="utf-8").strip()
        if not content:
            return []
        payload = json.loads(content)
        return payload if isinstance(payload, list) else []

    def _write_rows(self, rows: list[dict]) -> None:
        ordered = sorted(rows, key=lambda row: (row.get("embedding_version_id", ""), row.get("chunk_id", "")))
        self.collection_path.write_text(
            json.dumps(ordered, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _matches_where(row: dict, where: dict[str, str] | None) -> bool:
    if not where:
        return True
    metadata = row.get("metadata", {})
    for key, expected in where.items():
        actual = row.get(key)
        if actual is None:
            actual = metadata.get(key)
        if str(actual) != str(expected):
            return False
    return True


def _dump_record(record: EmbeddingUpsertRecord) -> dict:
    if hasattr(record, "model_dump"):
        return record.model_dump()
    return record.dict()
