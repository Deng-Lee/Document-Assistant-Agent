from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from server.tests.support import activate_test_profile, build_ingested_stack


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
            self.assertTrue(repo.get_chunk(chunk.chunk_id).safe_summary)
            self.assertEqual(job_repo.get_job(queued.job_id).status.value, "succeeded")

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


def _build_job_stack(root):
    from server.app.jobs import JobService
    from server.app.storage import SQLiteJobRepository

    repo, _file_store, _ingestion, results = build_ingested_stack(root, include_bjj=True, include_notes=False)
    store = repo.store
    job_repo = SQLiteJobRepository(store)
    chunk = results["bjj"].chunks[0]
    return repo, job_repo, JobService(repo, job_repo), chunk
