from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from server.app.core import JobRecord, JobRunResult, JobStatus, RuntimeConfigSnapshot, build_runtime_config
from server.app.ingestion.chunker import build_safe_summary_fallback
from server.app.storage import DocumentRepository, JobRepository, VectorStore


class JobService:
    def __init__(
        self,
        document_repository: DocumentRepository,
        job_repository: JobRepository,
        runtime_config: RuntimeConfigSnapshot | None = None,
        vector_store: VectorStore | None = None,
    ):
        self.document_repository = document_repository
        self.job_repository = job_repository
        self.runtime_config = runtime_config or build_runtime_config()
        self.vector_store = vector_store

    def enqueue(self, job_type: str, payload: dict[str, object], job_id: str | None = None) -> JobRecord:
        now = datetime.utcnow()
        record = JobRecord(
            job_id=job_id or f"job_{uuid4().hex[:12]}",
            job_type=job_type,
            status=JobStatus.QUEUED,
            payload=payload,
            created_at=now,
            updated_at=now,
        )
        self.job_repository.enqueue_job(record)
        return record

    def list_jobs(self, status: JobStatus | None = None, limit: int | None = None) -> list[JobRecord]:
        return self.job_repository.list_jobs(status=status, limit=limit)

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
        source_text = chunk.clean_search_text or chunk.safe_summary or ""
        safe_summary = build_safe_summary_fallback(source_text)
        self.document_repository.update_chunk_safe_summary(chunk_id, safe_summary)
        return [
            "safe_summary_updated",
            f"prompt_version={job.payload.get('summary_prompt_version') or self.runtime_config.prompt_versions.safe_summary}",
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
        return [f"vector_store_ready_for={doc_version_id}"]

