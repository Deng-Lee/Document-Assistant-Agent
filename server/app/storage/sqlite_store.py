from __future__ import annotations

import sqlite3
from pathlib import Path

from server.app.core import (
    ChunkRecord,
    DocVersionRecord,
    DocumentRecord,
    EvalRunResult,
    GoldenCase,
)

from .serialization import model_to_dict, model_to_json, parse_json_blob
from .sqlite_schema import ALL_SQLITE_STATEMENTS


class SQLiteStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def init_schema(self) -> None:
        with self.connect() as connection:
            for statement in ALL_SQLITE_STATEMENTS:
                connection.execute(statement)
            connection.commit()


class SQLiteDocumentRepository:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def init_schema(self) -> None:
        self.store.init_schema()

    def upsert_document(self, document: DocumentRecord) -> None:
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (doc_id, doc_type, title, latest_version_id, created_at, updated_at, status)
                VALUES (:doc_id, :doc_type, :title, :latest_version_id, :created_at, :updated_at, :status)
                ON CONFLICT(doc_id) DO UPDATE SET
                    doc_type=excluded.doc_type,
                    title=excluded.title,
                    latest_version_id=excluded.latest_version_id,
                    updated_at=excluded.updated_at,
                    status=excluded.status
                """,
                model_to_dict(document),
            )
            connection.commit()

    def insert_doc_version(self, doc_version: DocVersionRecord) -> None:
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO doc_versions
                (doc_version_id, doc_id, content_hash, ingest_time, source_path, size_bytes)
                VALUES (:doc_version_id, :doc_id, :content_hash, :ingest_time, :source_path, :size_bytes)
                """,
                model_to_dict(doc_version),
            )
            connection.commit()

    def insert_chunk(self, chunk: ChunkRecord) -> None:
        payload = model_to_dict(chunk)
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO chunks
                (chunk_id, doc_id, doc_version_id, doc_type, chunk_type, record_date, position, orientation,
                 distance, goal, opponent_control, heading_path_json, locator_json, metadata_digest_json,
                 safe_summary, clean_search_text, clean_embed_text, raw_text_ref)
                VALUES (:chunk_id, :doc_id, :doc_version_id, :doc_type, :chunk_type, :record_date, :position, :orientation,
                        :distance, :goal, :opponent_control, :heading_path_json, :locator_json, :metadata_digest_json,
                        :safe_summary, :clean_search_text, :clean_embed_text, :raw_text_ref)
                """,
                {
                    "chunk_id": payload["chunk_id"],
                    "doc_id": payload["doc_id"],
                    "doc_version_id": payload["doc_version_id"],
                    "doc_type": payload["doc_type"],
                    "chunk_type": payload["chunk_type"],
                    "record_date": payload["metadata_digest"].get("date"),
                    "position": payload["metadata_digest"].get("position"),
                    "orientation": payload["metadata_digest"].get("orientation"),
                    "distance": payload["metadata_digest"].get("distance"),
                    "goal": payload["metadata_digest"].get("goal"),
                    "opponent_control": payload["metadata_digest"].get("opponent_control"),
                    "heading_path_json": model_to_json(payload["metadata_digest"].get("heading_path", [])),
                    "locator_json": model_to_json(chunk.locator),
                    "metadata_digest_json": model_to_json(chunk.metadata_digest),
                    "safe_summary": payload.get("safe_summary"),
                    "clean_search_text": payload.get("clean_search_text"),
                    "clean_embed_text": payload.get("clean_embed_text"),
                    "raw_text_ref": payload.get("raw_text_ref"),
                },
            )
            if chunk.clean_search_text:
                connection.execute("DELETE FROM chunk_fts WHERE chunk_id = ?", (chunk.chunk_id,))
                connection.execute(
                    "INSERT INTO chunk_fts (chunk_id, doc_type, clean_search_text) VALUES (?, ?, ?)",
                    (chunk.chunk_id, chunk.doc_type.value, chunk.clean_search_text),
                )
            connection.commit()

    def list_chunks(self) -> list[ChunkRecord]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id, doc_id, doc_version_id, doc_type, chunk_type, locator_json, metadata_digest_json,
                       safe_summary, clean_search_text, clean_embed_text, raw_text_ref
                FROM chunks
                ORDER BY chunk_id
                """
            ).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    def list_chunks_for_doc_version(self, doc_version_id: str) -> list[ChunkRecord]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id, doc_id, doc_version_id, doc_type, chunk_type, locator_json, metadata_digest_json,
                       safe_summary, clean_search_text, clean_embed_text, raw_text_ref
                FROM chunks
                WHERE doc_version_id = ?
                ORDER BY chunk_id
                """,
                (doc_version_id,),
            ).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    def structured_filter_chunks(self, filters: dict[str, object], limit: int | None = None) -> list[ChunkRecord]:
        clauses = []
        parameters: list[object] = []
        mapping = {
            "doc_type": "doc_type = ?",
            "doc_version_id": "doc_version_id = ?",
            "position": "position = ?",
            "orientation": "orientation = ?",
            "distance": "distance = ?",
            "goal": "goal = ?",
            "opponent_control": "opponent_control = ?",
        }
        for key, clause in mapping.items():
            value = filters.get(key)
            if value is None:
                continue
            clauses.append(clause)
            parameters.append(value.value if hasattr(value, "value") else value)

        date_range = filters.get("date_range")
        if isinstance(date_range, dict):
            if date_range.get("start"):
                clauses.append("record_date >= ?")
                parameters.append(str(date_range["start"]))
            if date_range.get("end"):
                clauses.append("record_date <= ?")
                parameters.append(str(date_range["end"]))

        sql = """
            SELECT chunk_id, doc_id, doc_version_id, doc_type, chunk_type, locator_json, metadata_digest_json,
                   safe_summary, clean_search_text, clean_embed_text, raw_text_ref
            FROM chunks
        """
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY record_date DESC, chunk_id ASC"
        if limit is not None:
            sql += " LIMIT ?"
            parameters.append(limit)

        with self.store.connect() as connection:
            rows = connection.execute(sql, tuple(parameters)).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    def bm25_search(self, query_text: str, limit: int, filters: dict[str, object] | None = None) -> list[ChunkRecord]:
        sql = """
            SELECT c.chunk_id, c.doc_id, c.doc_version_id, c.doc_type, c.chunk_type, c.locator_json, c.metadata_digest_json,
                   c.safe_summary, c.clean_search_text, c.clean_embed_text, c.raw_text_ref
            FROM chunk_fts f
            JOIN chunks c ON c.chunk_id = f.chunk_id
            WHERE f.clean_search_text MATCH ?
        """
        parameters: list[object] = [query_text]
        if filters:
            filtered_sql, filtered_params = self._filters_to_sql(filters)
            if filtered_sql:
                sql += " AND " + filtered_sql
                parameters.extend(filtered_params)
        sql += " ORDER BY bm25(chunk_fts) LIMIT ?"
        parameters.append(limit)
        with self.store.connect() as connection:
            rows = connection.execute(sql, tuple(parameters)).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    @staticmethod
    def _filters_to_sql(filters: dict[str, object]) -> tuple[str, list[object]]:
        clauses = []
        parameters: list[object] = []
        for key in ("doc_type", "doc_version_id", "position", "orientation", "distance", "goal", "opponent_control"):
            value = filters.get(key)
            if value is None:
                continue
            clauses.append(f"c.{key} = ?")
            parameters.append(value.value if hasattr(value, "value") else value)
        date_range = filters.get("date_range")
        if isinstance(date_range, dict):
            if date_range.get("start"):
                clauses.append("c.record_date >= ?")
                parameters.append(str(date_range["start"]))
            if date_range.get("end"):
                clauses.append("c.record_date <= ?")
                parameters.append(str(date_range["end"]))
        return " AND ".join(clauses), parameters

    @staticmethod
    def _row_to_chunk(row) -> ChunkRecord:
        payload = dict(row)
        payload["locator"] = parse_json_blob(payload.pop("locator_json"))
        payload["metadata_digest"] = parse_json_blob(payload.pop("metadata_digest_json"))
        return ChunkRecord(**payload)


class SQLiteGoldenCaseRepository:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def upsert_golden_case(self, case: GoldenCase) -> None:
        payload = model_to_dict(case)
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO golden_cases
                (case_id, query, domain, expected_behavior_json, expected_chunk_ids_json)
                VALUES (:case_id, :query, :domain, :expected_behavior_json, :expected_chunk_ids_json)
                """,
                {
                    "case_id": payload["case_id"],
                    "query": payload["query"],
                    "domain": payload["domain"],
                    "expected_behavior_json": model_to_json(case.expected_behavior),
                    "expected_chunk_ids_json": model_to_json(case.expected_chunk_ids),
                },
            )
            connection.commit()

    def list_golden_cases(self) -> list[GoldenCase]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT case_id, query, domain, expected_behavior_json, expected_chunk_ids_json
                FROM golden_cases
                ORDER BY case_id
                """
            ).fetchall()
        return [
            GoldenCase(
                case_id=row["case_id"],
                query=row["query"],
                domain=row["domain"],
                expected_behavior=parse_json_blob(row["expected_behavior_json"]),
                expected_chunk_ids=parse_json_blob(row["expected_chunk_ids_json"]),
            )
            for row in rows
        ]

    def record_eval_run(self, result: EvalRunResult) -> None:
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO eval_runs
                (eval_run_id, eval_set_id, model_variant, created_at, metrics_json, failures_json)
                VALUES (:eval_run_id, :eval_set_id, :model_variant, :created_at, :metrics_json, :failures_json)
                """,
                {
                    "eval_run_id": result.eval_run_id,
                    "eval_set_id": result.eval_set_id,
                    "model_variant": result.model_variant.value,
                    "created_at": result.created_at.isoformat(),
                    "metrics_json": model_to_json(result.metrics),
                    "failures_json": model_to_json(result.failures),
                },
            )
            connection.commit()
