from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from server.app.core import (
    ChunkRecord,
    DocVersionRecord,
    DocumentRecord,
    EvalFailure,
    EvalMetricValue,
    EvalRunResult,
    EvalSummary,
    GoldenCase,
    JobRecord,
    JobStatus,
    ManualRubricEntry,
    ManualRubricScore,
    ProfileSummary,
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
            self._run_lightweight_migrations(connection)
            connection.commit()

    @staticmethod
    def _run_lightweight_migrations(connection: sqlite3.Connection) -> None:
        _ensure_column(connection, "golden_cases", "trace_id", "TEXT")
        _ensure_column(connection, "eval_runs", "result_json", "TEXT")
        _ensure_column(connection, "chunks", "summary_model", "TEXT")
        _ensure_column(connection, "chunks", "summary_prompt_version", "TEXT")
        _ensure_column(connection, "chunks", "summary_status", "TEXT")
        _ensure_column(connection, "chunks", "summary_error_code", "TEXT")


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

    def get_doc_version(self, doc_version_id: str) -> DocVersionRecord | None:
        with self.store.connect() as connection:
            row = connection.execute(
                """
                SELECT doc_version_id, doc_id, content_hash, ingest_time, source_path, size_bytes
                FROM doc_versions
                WHERE doc_version_id = ?
                """,
                (doc_version_id,),
            ).fetchone()
        if row is None:
            return None
        return DocVersionRecord(
            doc_version_id=row["doc_version_id"],
            doc_id=row["doc_id"],
            content_hash=row["content_hash"],
            ingest_time=datetime.fromisoformat(row["ingest_time"]),
            source_path=row["source_path"],
            size_bytes=row["size_bytes"],
        )

    def insert_chunk(self, chunk: ChunkRecord) -> None:
        payload = model_to_dict(chunk)
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO chunks
                (chunk_id, doc_id, doc_version_id, doc_type, chunk_type, record_date, position, orientation,
                 distance, goal, opponent_control, heading_path_json, locator_json, metadata_digest_json,
                 safe_summary, summary_model, summary_prompt_version, summary_status, summary_error_code,
                 clean_search_text, clean_embed_text, raw_text_ref)
                VALUES (:chunk_id, :doc_id, :doc_version_id, :doc_type, :chunk_type, :record_date, :position, :orientation,
                        :distance, :goal, :opponent_control, :heading_path_json, :locator_json, :metadata_digest_json,
                        :safe_summary, :summary_model, :summary_prompt_version, :summary_status, :summary_error_code,
                        :clean_search_text, :clean_embed_text, :raw_text_ref)
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
                    "summary_model": payload.get("summary_model"),
                    "summary_prompt_version": payload.get("summary_prompt_version"),
                    "summary_status": payload.get("summary_status"),
                    "summary_error_code": payload.get("summary_error_code"),
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

    def get_chunk(self, chunk_id: str) -> ChunkRecord | None:
        with self.store.connect() as connection:
            row = connection.execute(
                """
                SELECT chunk_id, doc_id, doc_version_id, doc_type, chunk_type, locator_json, metadata_digest_json,
                       safe_summary, summary_model, summary_prompt_version, summary_status, summary_error_code,
                       clean_search_text, clean_embed_text, raw_text_ref
                FROM chunks
                WHERE chunk_id = ?
                """,
                (chunk_id,),
            ).fetchone()
        return self._row_to_chunk(row) if row is not None else None

    def update_chunk_safe_summary(self, chunk_id: str, safe_summary: str) -> None:
        self.update_chunk_summary_state(
            chunk_id,
            safe_summary=safe_summary,
            summary_model=None,
            summary_prompt_version=None,
            summary_status="built",
            summary_error_code=None,
        )

    def update_chunk_summary_state(
        self,
        chunk_id: str,
        *,
        safe_summary: str,
        summary_model: str | None,
        summary_prompt_version: str | None,
        summary_status: str,
        summary_error_code: str | None,
    ) -> None:
        with self.store.connect() as connection:
            connection.execute(
                """
                UPDATE chunks
                SET safe_summary = ?,
                    summary_model = ?,
                    summary_prompt_version = ?,
                    summary_status = ?,
                    summary_error_code = ?
                WHERE chunk_id = ?
                """,
                (
                    safe_summary,
                    summary_model,
                    summary_prompt_version,
                    summary_status,
                    summary_error_code,
                    chunk_id,
                ),
            )
            connection.commit()

    def list_chunks(self) -> list[ChunkRecord]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id, doc_id, doc_version_id, doc_type, chunk_type, locator_json, metadata_digest_json,
                       safe_summary, summary_model, summary_prompt_version, summary_status, summary_error_code,
                       clean_search_text, clean_embed_text, raw_text_ref
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
                       safe_summary, summary_model, summary_prompt_version, summary_status, summary_error_code,
                       clean_search_text, clean_embed_text, raw_text_ref
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
                   safe_summary, summary_model, summary_prompt_version, summary_status, summary_error_code,
                   clean_search_text, clean_embed_text, raw_text_ref
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
                   c.safe_summary, c.summary_model, c.summary_prompt_version, c.summary_status, c.summary_error_code,
                   c.clean_search_text, c.clean_embed_text, c.raw_text_ref
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
                (case_id, query, domain, trace_id, expected_behavior_json, expected_chunk_ids_json)
                VALUES (:case_id, :query, :domain, :trace_id, :expected_behavior_json, :expected_chunk_ids_json)
                """,
                {
                    "case_id": payload["case_id"],
                    "query": payload["query"],
                    "domain": payload["domain"],
                    "trace_id": payload.get("trace_id"),
                    "expected_behavior_json": model_to_json(case.expected_behavior),
                    "expected_chunk_ids_json": model_to_json(case.expected_chunk_ids),
                },
            )
            connection.commit()

    def list_golden_cases(self) -> list[GoldenCase]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT case_id, query, domain, trace_id, expected_behavior_json, expected_chunk_ids_json
                FROM golden_cases
                ORDER BY case_id
                """
            ).fetchall()
        return [
            GoldenCase(
                case_id=row["case_id"],
                query=row["query"],
                domain=row["domain"],
                trace_id=row["trace_id"],
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
                (eval_run_id, eval_set_id, model_variant, created_at, metrics_json, failures_json, result_json)
                VALUES (:eval_run_id, :eval_set_id, :model_variant, :created_at, :metrics_json, :failures_json, :result_json)
                """,
                {
                    "eval_run_id": result.eval_run_id,
                    "eval_set_id": result.eval_set_id,
                    "model_variant": result.model_variant.value,
                    "created_at": result.created_at.isoformat(),
                    "metrics_json": model_to_json(result.metrics),
                    "failures_json": model_to_json(result.failures),
                    "result_json": model_to_json(result),
                },
            )
            connection.commit()

    def get_eval_run(self, eval_run_id: str) -> EvalRunResult | None:
        with self.store.connect() as connection:
            row = connection.execute(
                """
                SELECT result_json
                FROM eval_runs
                WHERE eval_run_id = ?
                """,
                (eval_run_id,),
            ).fetchone()
        if row is None or row["result_json"] is None:
            return None
        return EvalRunResult(**parse_json_blob(row["result_json"]))

    def list_eval_runs(self) -> list[EvalRunResult]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT eval_run_id, eval_set_id, model_variant, created_at, metrics_json, failures_json, result_json
                FROM eval_runs
                ORDER BY created_at DESC
                """
            ).fetchall()
        results: list[EvalRunResult] = []
        for row in rows:
            result_payload = parse_json_blob(row["result_json"]) if row["result_json"] else None
            if result_payload:
                results.append(EvalRunResult(**result_payload))
                continue
            metrics_payload = parse_json_blob(row["metrics_json"]) or []
            failures_payload = parse_json_blob(row["failures_json"]) or []
            results.append(
                EvalRunResult(
                    eval_run_id=row["eval_run_id"],
                    eval_set_id=row["eval_set_id"],
                    model_variant=row["model_variant"],
                    created_at=row["created_at"],
                    metrics=[EvalMetricValue(**metric) for metric in metrics_payload],
                    failures=[EvalFailure(**failure) for failure in failures_payload],
                )
            )
        return results

    def upsert_manual_rubric(self, entry: ManualRubricEntry) -> None:
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO eval_rubrics
                (rubric_id, eval_run_id, trace_id, reviewer, scores_json, notes, created_at, updated_at)
                VALUES (:rubric_id, :eval_run_id, :trace_id, :reviewer, :scores_json, :notes, :created_at, :updated_at)
                """,
                {
                    "rubric_id": entry.rubric_id,
                    "eval_run_id": entry.eval_run_id,
                    "trace_id": entry.trace_id,
                    "reviewer": entry.reviewer,
                    "scores_json": model_to_json(entry.scores),
                    "notes": entry.notes,
                    "created_at": entry.created_at.isoformat(),
                    "updated_at": entry.updated_at.isoformat(),
                },
            )
            connection.commit()

    def list_manual_rubrics(self, eval_run_id: str) -> list[ManualRubricEntry]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT rubric_id, eval_run_id, trace_id, reviewer, scores_json, notes, created_at, updated_at
                FROM eval_rubrics
                WHERE eval_run_id = ?
                ORDER BY updated_at DESC, rubric_id ASC
                """,
                (eval_run_id,),
            ).fetchall()
        return [
            ManualRubricEntry(
                rubric_id=row["rubric_id"],
                eval_run_id=row["eval_run_id"],
                trace_id=row["trace_id"],
                reviewer=row["reviewer"],
                scores=[ManualRubricScore(**item) for item in parse_json_blob(row["scores_json"])],
                notes=row["notes"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    known = {row["name"] for row in rows}
    if column_name not in known:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


class SQLiteJobRepository:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def enqueue_job(self, job: JobRecord) -> None:
        payload = model_to_dict(job)
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO jobs
                (job_id, job_type, status, payload_json, error_message, created_at, updated_at)
                VALUES (:job_id, :job_type, :status, :payload_json, :error_message, :created_at, :updated_at)
                """,
                {
                    "job_id": payload["job_id"],
                    "job_type": payload["job_type"],
                    "status": payload["status"],
                    "payload_json": model_to_json(job.payload),
                    "error_message": payload.get("error_message"),
                    "created_at": payload["created_at"],
                    "updated_at": payload["updated_at"],
                },
            )
            connection.commit()

    def get_job(self, job_id: str) -> JobRecord | None:
        with self.store.connect() as connection:
            row = connection.execute(
                """
                SELECT job_id, job_type, status, payload_json, error_message, created_at, updated_at
                FROM jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
        return _row_to_job(row) if row is not None else None

    def list_jobs(self, status: JobStatus | None = None, limit: int | None = None) -> list[JobRecord]:
        sql = """
            SELECT job_id, job_type, status, payload_json, error_message, created_at, updated_at
            FROM jobs
        """
        parameters: list[object] = []
        if status is not None:
            sql += " WHERE status = ?"
            parameters.append(status.value)
        sql += " ORDER BY created_at ASC, job_id ASC"
        if limit is not None:
            sql += " LIMIT ?"
            parameters.append(limit)
        with self.store.connect() as connection:
            rows = connection.execute(sql, tuple(parameters)).fetchall()
        return [_row_to_job(row) for row in rows]

    def claim_next_job(self, job_types: list[str] | None = None) -> JobRecord | None:
        clauses = ["status = ?"]
        parameters: list[object] = [JobStatus.QUEUED.value]
        if job_types:
            placeholders = ", ".join("?" for _ in job_types)
            clauses.append(f"job_type IN ({placeholders})")
            parameters.extend(job_types)

        with self.store.connect() as connection:
            row = connection.execute(
                f"""
                SELECT job_id, job_type, status, payload_json, error_message, created_at, updated_at
                FROM jobs
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at ASC, job_id ASC
                LIMIT 1
                """,
                tuple(parameters),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, error_message = NULL, updated_at = ?
                WHERE job_id = ?
                """,
                (JobStatus.RUNNING.value, datetime.utcnow().isoformat(), row["job_id"]),
            )
            connection.commit()
        return self.get_job(row["job_id"])

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: str | None = None,
    ) -> JobRecord | None:
        with self.store.connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, error_message = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status.value, error_message, datetime.utcnow().isoformat(), job_id),
            )
            connection.commit()
        return self.get_job(job_id)


def _row_to_job(row) -> JobRecord:
    payload = dict(row)
    payload["payload"] = parse_json_blob(payload.pop("payload_json"))
    return JobRecord(**payload)


class SQLiteProfileRepository:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def upsert_profile(self, profile: ProfileSummary, created_at: str | None = None) -> None:
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO profiles (profile_version_id, profile_summary_json, created_at)
                VALUES (?, ?, ?)
                """,
                (
                    profile.profile_version_id,
                    model_to_json(profile),
                    created_at or datetime.utcnow().isoformat(),
                ),
            )
            connection.commit()

    def get_profile(self, profile_version_id: str) -> ProfileSummary | None:
        with self.store.connect() as connection:
            row = connection.execute(
                """
                SELECT profile_summary_json
                FROM profiles
                WHERE profile_version_id = ?
                """,
                (profile_version_id,),
            ).fetchone()
        if row is None:
            return None
        return ProfileSummary(**parse_json_blob(row["profile_summary_json"]))

    def get_latest_profile(self) -> ProfileSummary | None:
        with self.store.connect() as connection:
            row = connection.execute(
                """
                SELECT profile_summary_json
                FROM profiles
                ORDER BY created_at DESC, profile_version_id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return ProfileSummary(**parse_json_blob(row["profile_summary_json"]))

    def list_profiles(self, limit: int | None = None) -> list[ProfileSummary]:
        sql = """
            SELECT profile_summary_json
            FROM profiles
            ORDER BY created_at DESC, profile_version_id DESC
        """
        parameters: list[object] = []
        if limit is not None:
            sql += " LIMIT ?"
            parameters.append(limit)
        with self.store.connect() as connection:
            rows = connection.execute(sql, tuple(parameters)).fetchall()
        return [ProfileSummary(**parse_json_blob(row["profile_summary_json"])) for row in rows]
