from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from server.app.core import DocVersionRecord, JobRecord, JobRunResult, JobStatus, RuntimeConfigSnapshot, SummaryStatus, build_runtime_config
from server.app.ingestion.chunker import build_safe_summary_fallback
from server.app.storage import DocumentRepository, JobRepository, VectorStore
from server.app.storage.vector_indexing import build_embedding_upsert_records
from .safe_summary_provider import (
    SafeSummaryProvider,
    SafeSummaryProviderError,
    SafeSummaryProviderSchemaError,
    SafeSummaryProviderUnavailableError,
    SafeSummaryRequest,
    build_safe_summary_provider,
)


class JobService:
    SAFE_SUMMARY_MAX_RETRIES = 3

    def __init__(
        self,
        document_repository: DocumentRepository,
        job_repository: JobRepository,
        runtime_config: RuntimeConfigSnapshot | None = None,
        vector_store: VectorStore | None = None,
        safe_summary_provider: SafeSummaryProvider | None = None,
    ):
        self.document_repository = document_repository
        self.job_repository = job_repository
        self.runtime_config = runtime_config or build_runtime_config()
        self.vector_store = vector_store
        self.safe_summary_provider = safe_summary_provider or build_safe_summary_provider(self.runtime_config)

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, object],
        job_id: str | None = None,
        available_at: datetime | None = None,
    ) -> JobRecord:
        now = datetime.utcnow()
        record = JobRecord(
            job_id=job_id or f"job_{uuid4().hex[:12]}",
            job_type=job_type,
            status=JobStatus.QUEUED,
            payload=payload,
            available_at=available_at,
            created_at=now,
            updated_at=now,
        )
        self.job_repository.enqueue_job(record)
        return record

    def list_jobs(self, status: JobStatus | None = None, limit: int | None = None) -> list[JobRecord]:
        return self.job_repository.list_jobs(status=status, limit=limit)

    def resolve_doc_version_scope(
        self,
        *,
        scope: str,
        doc_version_id: str | None = None,
        doc_id: str | None = None,
    ) -> list[DocVersionRecord]:
        if scope == "doc_version_id":
            if not doc_version_id:
                raise ValueError("doc_version_id scope requires doc_version_id")
            doc_version = self.document_repository.get_doc_version(doc_version_id)
            if doc_version is None:
                raise ValueError(f"doc_version not found: {doc_version_id}")
            return [doc_version]
        if scope == "doc_id":
            if not doc_id:
                raise ValueError("doc_id scope requires doc_id")
            versions = self.document_repository.list_doc_versions(doc_id)
            if not versions:
                raise ValueError(f"doc_id not found: {doc_id}")
            return versions
        if scope == "all":
            versions = self.document_repository.list_doc_versions()
            if not versions:
                raise ValueError("no_doc_versions_available")
            return versions
        raise ValueError(f"unsupported_scope:{scope}")

    def preview_scope(
        self,
        *,
        scope: str,
        doc_version_id: str | None = None,
        doc_id: str | None = None,
    ) -> tuple[list[DocVersionRecord], int]:
        versions = self.resolve_doc_version_scope(
            scope=scope,
            doc_version_id=doc_version_id,
            doc_id=doc_id,
        )
        affected_chunks = sum(
            len(self.document_repository.list_chunks_for_doc_version(version.doc_version_id))
            for version in versions
        )
        return versions, affected_chunks

    def enqueue_reindex_jobs(
        self,
        *,
        scope: str,
        doc_version_id: str | None = None,
        doc_id: str | None = None,
        rebuild_fts5: bool,
        rebuild_chroma: bool,
        rebuild_safe_summary: bool = False,
    ) -> tuple[list[DocVersionRecord], int, list[JobRecord]]:
        if not any((rebuild_fts5, rebuild_chroma, rebuild_safe_summary)):
            raise ValueError("reindex_requires_at_least_one_rebuild_flag")
        versions, affected_chunks = self.preview_scope(
            scope=scope,
            doc_version_id=doc_version_id,
            doc_id=doc_id,
        )
        jobs: list[JobRecord] = []
        for version in versions:
            if rebuild_fts5:
                jobs.append(self.enqueue("reindex_doc_version", {"doc_version_id": version.doc_version_id}))
            if rebuild_chroma:
                jobs.append(
                    self.enqueue(
                        "reembed_doc_version",
                        {
                            "doc_version_id": version.doc_version_id,
                            "embedding_version_id": self.runtime_config.embedding_version_id,
                        },
                    )
                )
            if rebuild_safe_summary:
                for chunk in self.document_repository.list_chunks_for_doc_version(version.doc_version_id):
                    self.document_repository.update_chunk_summary_state(
                        chunk.chunk_id,
                        safe_summary=chunk.safe_summary or "",
                        summary_model=self.runtime_config.model_routing.base_model,
                        summary_prompt_version=self.runtime_config.prompt_versions.safe_summary,
                        summary_status=SummaryStatus.PENDING.value,
                        summary_error_code=None,
                        summary_retry_count=0,
                        summary_last_attempt_at=None,
                        summary_next_retry_at=None,
                        summary_last_error_at=None,
                    )
                    jobs.append(
                        self.enqueue(
                            "safe_summary_build",
                            {
                                "chunk_id": chunk.chunk_id,
                                "doc_version_id": chunk.doc_version_id,
                                "summary_prompt_version": self.runtime_config.prompt_versions.safe_summary,
                                "summary_model": self.runtime_config.model_routing.base_model,
                            },
                        )
                    )
        return versions, affected_chunks, jobs

    def enqueue_reembed_jobs(
        self,
        *,
        scope: str,
        embedding_version_id: str,
        doc_version_id: str | None = None,
        doc_id: str | None = None,
        dry_run: bool = False,
    ) -> tuple[list[DocVersionRecord], int, list[JobRecord]]:
        if not embedding_version_id:
            raise ValueError("embedding_version_id_required")
        versions, affected_chunks = self.preview_scope(
            scope=scope,
            doc_version_id=doc_version_id,
            doc_id=doc_id,
        )
        if dry_run:
            return versions, affected_chunks, []
        jobs = [
            self.enqueue(
                "reembed_doc_version",
                {
                    "doc_version_id": version.doc_version_id,
                    "embedding_version_id": embedding_version_id,
                },
            )
            for version in versions
        ]
        return versions, affected_chunks, jobs

    def run_next(self, job_types: list[str] | None = None) -> JobRunResult | None:
        job = self.job_repository.claim_next_job(job_types=job_types)
        if job is None:
            return None
        return self._run_claimed_job(job)

    def run_job(self, job_id: str) -> JobRunResult:
        job = self.job_repository.get_job(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        if job.status == JobStatus.SUCCEEDED:
            return JobRunResult(job=job, handled=True, notes=["already_succeeded"])
        if job.status != JobStatus.RUNNING:
            job = self.job_repository.update_job_status(job_id, JobStatus.RUNNING) or job
        return self._run_claimed_job(job)

    def _run_claimed_job(self, job: JobRecord) -> JobRunResult:
        try:
            notes = self._dispatch(job)
        except Exception as exc:
            failed = self.job_repository.update_job_status(job.job_id, JobStatus.FAILED, str(exc)) or job
            return JobRunResult(job=failed, handled=False, notes=["job_failed"])

        completed = self.job_repository.update_job_status(job.job_id, JobStatus.SUCCEEDED) or job
        return JobRunResult(job=completed, handled=True, notes=notes)

    def _dispatch(self, job: JobRecord) -> list[str]:
        if job.job_type == "safe_summary_build":
            return self._run_safe_summary_build(job)
        if job.job_type == "reindex_doc_version":
            return self._run_reindex_doc_version(job)
        if job.job_type == "reembed_doc_version":
            return self._run_reembed_doc_version(job)
        raise ValueError(f"unsupported job type: {job.job_type}")

    def _run_safe_summary_build(self, job: JobRecord) -> list[str]:
        chunk_id = str(job.payload.get("chunk_id") or "")
        if not chunk_id:
            raise ValueError("safe_summary_build requires chunk_id")
        chunk = self.document_repository.get_chunk(chunk_id)
        if chunk is None:
            raise ValueError(f"chunk not found: {chunk_id}")
        raw_chunk_text = (chunk.raw_text_ref or "").strip()
        if not raw_chunk_text:
            raw_chunk_text = chunk.clean_search_text or chunk.safe_summary or ""
        summary_model = str(job.payload.get("summary_model") or self.runtime_config.model_routing.base_model)
        prompt_version = str(job.payload.get("summary_prompt_version") or self.runtime_config.prompt_versions.safe_summary)
        attempt_started_at = datetime.utcnow()
        self.document_repository.update_chunk_summary_state(
            chunk_id,
            safe_summary=chunk.safe_summary or "",
            summary_model=summary_model,
            summary_prompt_version=prompt_version,
            summary_status=SummaryStatus.RUNNING.value,
            summary_error_code=None,
            summary_retry_count=chunk.summary_retry_count,
            summary_last_attempt_at=attempt_started_at.isoformat(),
            summary_next_retry_at=chunk.summary_next_retry_at.isoformat() if chunk.summary_next_retry_at else None,
            summary_last_error_at=chunk.summary_last_error_at.isoformat() if chunk.summary_last_error_at else None,
        )
        try:
            output = self.safe_summary_provider.summarize(
                SafeSummaryRequest(
                    raw_chunk_text=raw_chunk_text,
                    chunk=chunk,
                    runtime_config=self.runtime_config,
                )
            )
        except (
            SafeSummaryProviderUnavailableError,
            SafeSummaryProviderSchemaError,
            SafeSummaryProviderError,
        ) as exc:
            failed_at = datetime.utcnow()
            error_code = _safe_summary_error_code(exc)
            failure_class = _safe_summary_failure_class(exc)
            retry_count = chunk.summary_retry_count + 1
            should_retry = failure_class == "retryable" and retry_count < self.SAFE_SUMMARY_MAX_RETRIES
            next_retry_at = _safe_summary_backoff_at(failed_at, retry_count) if should_retry else None
            summary_status = SummaryStatus.FAILED.value if should_retry or failure_class == "terminal" else SummaryStatus.FALLBACK.value
            safe_summary = (
                chunk.safe_summary or ""
                if summary_status == SummaryStatus.FAILED.value
                else build_safe_summary_fallback(chunk.clean_search_text or raw_chunk_text)
            )
            self.document_repository.update_chunk_summary_state(
                chunk_id,
                safe_summary=safe_summary,
                summary_model=summary_model,
                summary_prompt_version=prompt_version,
                summary_status=summary_status,
                summary_error_code=error_code,
                summary_retry_count=retry_count,
                summary_last_attempt_at=attempt_started_at.isoformat(),
                summary_next_retry_at=next_retry_at.isoformat() if next_retry_at else None,
                summary_last_error_at=failed_at.isoformat(),
            )
            if should_retry:
                self.enqueue(
                    "safe_summary_build",
                    {
                        **job.payload,
                        "retry_attempt": retry_count,
                    },
                    available_at=next_retry_at,
                )
            elif summary_status == SummaryStatus.FALLBACK.value:
                return [
                    "safe_summary_fallback",
                    f"prompt_version={prompt_version}",
                    f"summary_model={summary_model}",
                    f"summary_error_code={error_code}",
                    f"retry_count={retry_count}",
                ]
            raise RuntimeError(error_code) from exc
        self.document_repository.update_chunk_summary_state(
            chunk_id,
            safe_summary=output.safe_summary,
            summary_model=output.model_name,
            summary_prompt_version=output.prompt_version,
            summary_status=SummaryStatus.BUILT.value,
            summary_error_code=None,
            summary_retry_count=0,
            summary_last_attempt_at=attempt_started_at.isoformat(),
            summary_next_retry_at=None,
            summary_last_error_at=None,
        )
        return [
            "safe_summary_updated",
            f"prompt_version={output.prompt_version}",
            f"summary_model={output.model_name}",
        ]

    def _run_reindex_doc_version(self, job: JobRecord) -> list[str]:
        doc_version_id = str(job.payload.get("doc_version_id") or "")
        if not doc_version_id:
            raise ValueError("reindex_doc_version requires doc_version_id")
        chunks = self.document_repository.list_chunks_for_doc_version(doc_version_id)
        for chunk in chunks:
            self.document_repository.insert_chunk(chunk)
        return [f"reindexed_chunks={len(chunks)}"]

    def _run_reembed_doc_version(self, job: JobRecord) -> list[str]:
        doc_version_id = str(job.payload.get("doc_version_id") or "")
        if not doc_version_id:
            raise ValueError("reembed_doc_version requires doc_version_id")
        if self.vector_store is None:
            return ["vector_store_unavailable", f"doc_version_id={doc_version_id}"]
        embedding_version_id = str(job.payload.get("embedding_version_id") or self.runtime_config.embedding_version_id)
        chunks = self.document_repository.list_chunks_for_doc_version(doc_version_id)
        self.vector_store.ensure_collection()
        self.vector_store.delete_doc_version(doc_version_id, embedding_version_id=embedding_version_id)
        runtime_config = (
            self.runtime_config.model_copy(update={"embedding_version_id": embedding_version_id})
            if hasattr(self.runtime_config, "model_copy")
            else self.runtime_config.copy(update={"embedding_version_id": embedding_version_id})
        )
        self.vector_store.upsert_embeddings(build_embedding_upsert_records(chunks, runtime_config))
        return [
            f"reembedded_chunks={len(chunks)}",
            f"embedding_version_id={embedding_version_id}",
        ]


def _safe_summary_error_code(exc: Exception) -> str:
    if isinstance(exc, SafeSummaryProviderUnavailableError):
        return f"provider_unavailable:{exc}"
    if isinstance(exc, SafeSummaryProviderSchemaError):
        return f"provider_schema_error:{exc}"
    if isinstance(exc, SafeSummaryProviderError):
        return f"provider_error:{exc}"
    return f"provider_error:{exc}"


def _safe_summary_failure_class(exc: Exception) -> str:
    if isinstance(exc, SafeSummaryProviderSchemaError):
        return "terminal"
    if isinstance(exc, (SafeSummaryProviderUnavailableError, SafeSummaryProviderError)):
        return "retryable"
    return "retryable"


def _safe_summary_backoff_at(failed_at: datetime, retry_count: int) -> datetime:
    delay_seconds = max(2 ** max(retry_count - 1, 0), 1)
    return failed_at + timedelta(seconds=delay_seconds)
