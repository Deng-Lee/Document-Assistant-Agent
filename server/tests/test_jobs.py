from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from server.tests.support import activate_test_profile, build_ingested_stack, build_ingested_vector_stack


class JobServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        activate_test_profile("fake")

    def test_safe_summary_job_updates_chunk_and_status(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, job_repo, job_service, chunk = _build_job_stack(tmp)

            repo.update_chunk_safe_summary(chunk.chunk_id, "")
            queued = job_service.enqueue(
                "safe_summary_build",
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_version_id": chunk.doc_version_id,
                    "summary_prompt_version": "safe_summary.v1",
                },
            )

            result = job_service.run_job(queued.job_id)

            self.assertEqual(result.job.status.value, "succeeded")
            updated = repo.get_chunk(chunk.chunk_id)
            self.assertTrue(updated.safe_summary)
            self.assertEqual(updated.summary_status.value, "built")
            self.assertEqual(updated.summary_prompt_version, "safe_summary.v1")
            self.assertTrue(updated.summary_model)
            self.assertEqual(updated.summary_retry_count, 0)
            self.assertIsNotNone(updated.summary_last_attempt_at)
            self.assertIsNone(updated.summary_last_error_at)
            self.assertEqual(job_repo.get_job(queued.job_id).status.value, "succeeded")

    def test_safe_summary_job_requeues_retryable_provider_error(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, job_repo, _job_service, chunk = _build_job_stack(tmp)

            from server.app.jobs import JobService
            from server.app.jobs.safe_summary_provider import SafeSummaryProviderError

            class _FailingProvider:
                provider_name = "failing-summary-provider"
                model_name = "failing-model"
                is_ready = True

                def summarize(self, request):
                    raise SafeSummaryProviderError("synthetic_failure")

            job_service = JobService(repo, job_repo, safe_summary_provider=_FailingProvider())
            queued = job_service.enqueue(
                "safe_summary_build",
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_version_id": chunk.doc_version_id,
                    "summary_prompt_version": "safe_summary.v1",
                    "summary_model": "test-summary-model",
                },
            )

            result = job_service.run_job(queued.job_id)

            self.assertEqual(result.job.status.value, "failed")
            updated = repo.get_chunk(chunk.chunk_id)
            self.assertEqual(updated.summary_status.value, "failed")
            self.assertEqual(updated.summary_error_code, "provider_error:synthetic_failure")
            self.assertEqual(updated.summary_model, "test-summary-model")
            self.assertEqual(updated.summary_retry_count, 1)
            self.assertIsNotNone(updated.summary_last_attempt_at)
            self.assertIsNotNone(updated.summary_last_error_at)
            self.assertIsNotNone(updated.summary_next_retry_at)
            self.assertEqual(job_repo.get_job(queued.job_id).error_message, "provider_error:synthetic_failure")
            queued_jobs = [job for job in job_repo.list_jobs() if job.status.value == "queued"]
            self.assertEqual(len(queued_jobs), 1)
            self.assertIsNotNone(queued_jobs[0].available_at)
            self.assertEqual(queued_jobs[0].payload["retry_attempt"], 1)
            self.assertIsNone(job_service.run_next(job_types=["safe_summary_build"]))

    def test_safe_summary_job_schema_error_does_not_retry(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, job_repo, _job_service, chunk = _build_job_stack(tmp)

            from server.app.jobs import JobService
            from server.app.jobs.safe_summary_provider import SafeSummaryProviderSchemaError

            class _SchemaFailingProvider:
                provider_name = "schema-failing-summary-provider"
                model_name = "schema-failing-model"
                is_ready = True

                def summarize(self, request):
                    raise SafeSummaryProviderSchemaError("invalid_json_response")

            job_service = JobService(repo, job_repo, safe_summary_provider=_SchemaFailingProvider())
            queued = job_service.enqueue("safe_summary_build", {"chunk_id": chunk.chunk_id})

            result = job_service.run_job(queued.job_id)

            self.assertEqual(result.job.status.value, "failed")
            updated = repo.get_chunk(chunk.chunk_id)
            self.assertEqual(updated.summary_status.value, "failed")
            self.assertEqual(updated.summary_error_code, "provider_schema_error:invalid_json_response")
            self.assertIsNone(updated.summary_next_retry_at)
            self.assertEqual(job_repo.list_jobs(status=None, limit=None)[0].job_id, queued.job_id)
            self.assertEqual([job for job in job_repo.list_jobs() if job.status.value == "queued"], [])

    def test_safe_summary_job_falls_back_after_retry_exhaustion(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, job_repo, _job_service, chunk = _build_job_stack(tmp)

            from server.app.jobs import JobService
            from server.app.jobs.safe_summary_provider import SafeSummaryProviderError

            class _AlwaysFailingProvider:
                provider_name = "always-failing-summary-provider"
                model_name = "always-failing-model"
                is_ready = True

                def summarize(self, request):
                    raise SafeSummaryProviderError("still_failing")

            job_service = JobService(repo, job_repo, safe_summary_provider=_AlwaysFailingProvider())
            first_job = job_service.enqueue("safe_summary_build", {"chunk_id": chunk.chunk_id})

            first_result = job_service.run_job(first_job.job_id)
            retry_jobs = [job for job in job_repo.list_jobs() if job.status.value == "queued"]
            second_result = job_service.run_job(retry_jobs[0].job_id)
            retry_jobs = [job for job in job_repo.list_jobs() if job.status.value == "queued"]
            third_result = job_service.run_job(retry_jobs[0].job_id)

            self.assertEqual(first_result.job.status.value, "failed")
            self.assertEqual(second_result.job.status.value, "failed")
            self.assertEqual(third_result.job.status.value, "succeeded")
            self.assertIn("safe_summary_fallback", third_result.notes)
            updated = repo.get_chunk(chunk.chunk_id)
            self.assertEqual(updated.summary_status.value, "fallback")
            self.assertEqual(updated.summary_retry_count, 3)
            self.assertTrue(updated.safe_summary)
            self.assertEqual([job for job in job_repo.list_jobs() if job.status.value == "queued"], [])

    def test_reindex_and_reembed_jobs_complete(self) -> None:
        with TemporaryDirectory() as tmp:
            _repo, _job_repo, job_service, chunk = _build_job_stack(tmp)

            reindex_job = job_service.enqueue("reindex_doc_version", {"doc_version_id": chunk.doc_version_id})
            reembed_job = job_service.enqueue("reembed_doc_version", {"doc_version_id": chunk.doc_version_id})

            reindex_result = job_service.run_next(job_types=["reindex_doc_version"])
            reembed_result = job_service.run_next(job_types=["reembed_doc_version"])

            self.assertEqual(reindex_result.job.job_id, reindex_job.job_id)
            self.assertEqual(reindex_result.job.status.value, "succeeded")
            self.assertEqual(reembed_result.job.job_id, reembed_job.job_id)
            self.assertEqual(reembed_result.job.status.value, "succeeded")
            self.assertIn("vector_store_unavailable", reembed_result.notes)

    def test_reembed_job_populates_vector_store(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, job_repo, vector_store, job_service, chunk = _build_vector_job_stack(tmp)

            reembed_job = job_service.enqueue("reembed_doc_version", {"doc_version_id": chunk.doc_version_id})
            result = job_service.run_job(reembed_job.job_id)

            self.assertEqual(result.job.status.value, "succeeded")
            self.assertIn(f"reembedded_chunks={len(repo.list_chunks_for_doc_version(chunk.doc_version_id))}", result.notes)

            from server.app.core.embeddings import build_text_embedding

            matches = vector_store.query(
                build_text_embedding("tripod post turtle escape"),
                top_k=5,
                where={
                    "doc_version_id": chunk.doc_version_id,
                    "embedding_version_id": "mock-embedding:v1",
                },
            )
            self.assertTrue(matches)
            self.assertEqual(matches[0].chunk_id, chunk.chunk_id)

            wrong_version_matches = vector_store.query(
                build_text_embedding("tripod post turtle escape"),
                top_k=5,
                where={
                    "doc_version_id": chunk.doc_version_id,
                    "embedding_version_id": "other-embedding:v1",
                },
            )
            self.assertEqual(wrong_version_matches, [])

    def test_reembed_job_keeps_old_embedding_versions_isolated(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, _job_repo, vector_store, job_service, chunk = _build_vector_job_stack(tmp)

            from server.app.core.embeddings import build_text_embedding

            first_job = job_service.enqueue("reembed_doc_version", {"doc_version_id": chunk.doc_version_id})
            second_job = job_service.enqueue(
                "reembed_doc_version",
                {
                    "doc_version_id": chunk.doc_version_id,
                    "embedding_version_id": "mock-embedding:v2",
                },
            )

            self.assertEqual(job_service.run_job(first_job.job_id).job.status.value, "succeeded")
            second_result = job_service.run_job(second_job.job_id)

            self.assertEqual(second_result.job.status.value, "succeeded")
            self.assertIn("embedding_version_id=mock-embedding:v2", second_result.notes)
            query_vector = build_text_embedding("tripod post turtle escape")
            matches_v1 = vector_store.query(
                query_vector,
                top_k=5,
                where={
                    "doc_version_id": chunk.doc_version_id,
                    "embedding_version_id": "mock-embedding:v1",
                },
            )
            matches_v2 = vector_store.query(
                query_vector,
                top_k=5,
                where={
                    "doc_version_id": chunk.doc_version_id,
                    "embedding_version_id": "mock-embedding:v2",
                },
            )
            self.assertTrue(matches_v1)
            self.assertTrue(matches_v2)
            self.assertEqual(matches_v1[0].chunk_id, chunk.chunk_id)
            self.assertEqual(matches_v2[0].chunk_id, chunk.chunk_id)

    def test_maintenance_scope_resolves_doc_id_and_all(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, job_repo, job_service, chunk = _build_job_stack(tmp)
            repo.insert_doc_version(repo.get_doc_version(chunk.doc_version_id))

            versions_by_doc, affected_chunks, jobs = job_service.enqueue_reindex_jobs(
                scope="doc_id",
                doc_id=chunk.doc_id,
                rebuild_fts5=True,
                rebuild_chroma=False,
                rebuild_safe_summary=False,
            )

            self.assertEqual([version.doc_version_id for version in versions_by_doc], [chunk.doc_version_id])
            self.assertGreaterEqual(affected_chunks, 1)
            self.assertEqual(len(jobs), 1)
            preview_versions, preview_chunks, dry_jobs = job_service.enqueue_reembed_jobs(
                scope="all",
                embedding_version_id="mock-embedding:v3",
                dry_run=True,
            )
            self.assertTrue(preview_versions)
            self.assertGreaterEqual(preview_chunks, 1)
            self.assertEqual(dry_jobs, [])

    def test_vector_store_persists_hits_across_adapter_recreation(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, _job_repo, vector_store, _job_service, chunk = _build_vector_job_stack(tmp)

            from server.app.core.embeddings import build_text_embedding
            from server.app.jobs import JobService
            from server.app.storage import ChromaVectorStoreAdapter, SQLiteJobRepository

            job_repo = SQLiteJobRepository(repo.store)
            job_service = JobService(repo, job_repo, vector_store=vector_store)
            reembed_job = job_service.enqueue("reembed_doc_version", {"doc_version_id": chunk.doc_version_id})
            result = job_service.run_job(reembed_job.job_id)

            self.assertEqual(result.job.status.value, "succeeded")

            reopened = ChromaVectorStoreAdapter(f"{tmp}/chroma", collection_name="chunks")
            matches = reopened.query(
                build_text_embedding("tripod post turtle escape"),
                top_k=5,
                where={
                    "doc_version_id": chunk.doc_version_id,
                    "embedding_version_id": "mock-embedding:v1",
                },
            )
            self.assertTrue(matches)
            self.assertEqual(matches[0].chunk_id, chunk.chunk_id)


def _build_job_stack(root):
    from server.app.jobs import JobService
    from server.app.storage import SQLiteJobRepository

    repo, _file_store, _ingestion, results = build_ingested_stack(root, include_bjj=True, include_notes=False)
    store = repo.store
    job_repo = SQLiteJobRepository(store)
    chunk = results["bjj"].chunks[0]
    return repo, job_repo, JobService(repo, job_repo), chunk


def _build_vector_job_stack(root):
    from server.app.jobs import JobService
    from server.app.storage import SQLiteJobRepository

    repo, _file_store, vector_store, _ingestion, results = build_ingested_vector_stack(root, include_bjj=True, include_notes=False)
    store = repo.store
    job_repo = SQLiteJobRepository(store)
    chunk = results["bjj"].chunks[0]
    vector_store.delete_doc_version(chunk.doc_version_id)
    return repo, job_repo, vector_store, JobService(repo, job_repo, vector_store=vector_store), chunk
