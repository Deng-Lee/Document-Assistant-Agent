from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from server.app.core import RerankerConfig, RuntimeConfigSnapshot
from server.tests.support import activate_test_profile, build_ingested_stack, build_ingested_vector_stack


class _UnavailableReranker:
    provider_name = "unavailable-reranker"
    model_name = "stub-reranker"
    is_ready = False

    def rerank(self, query_text, candidates):
        from server.app.retrieval.reranker import CrossEncoderUnavailableError

        raise CrossEncoderUnavailableError("missing_api_key")


class _StubHFBackend:
    model_name = "stub-local-cross-encoder"
    is_ready = True
    missing_dependencies: list[str] = []

    def score(self, query_text, candidates):
        return {
            candidate.chunk_id: 0.99 if "tripod post" in candidate.text.lower() else 0.25
            for candidate in candidates
        }


class RetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        activate_test_profile("fake")

    def test_query_parser_infers_bjj_and_recent_date_range(self) -> None:
        from server.app.core import DocumentType
        from server.app.retrieval import QueryParser

        plan = QueryParser().parse("最近 7 天的龟防训练记录", top_k=5)

        self.assertEqual(plan.filters.doc_type, DocumentType.BJJ)
        self.assertIsNotNone(plan.filters.date_range)
        self.assertEqual(plan.filters.date_range.expression, "最近 7 天")
        self.assertEqual(plan.top_k, 5)

    def test_retrieval_respects_structured_filters_and_probe_stats(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, _file_store, _ingestion, _results = build_ingested_stack(tmp, include_bjj=True, include_notes=True)

            from server.app.core import DocumentType, RetrievalFilters
            from server.app.retrieval import RetrievalService

            outcome = RetrievalService(repo).retrieve(
                query_text="turtle 下位 逃脱",
                filters_hint=RetrievalFilters(doc_type=DocumentType.BJJ, position="turtle", goal="escape"),
                mode="probe",
            )

            self.assertGreaterEqual(len(outcome.items), 1)
            self.assertIsNotNone(outcome.probe_stats)
            self.assertGreaterEqual(outcome.probe_stats.doc_type_hist["BJJ"], 1)
            self.assertEqual(outcome.probe_stats.doc_type_hist["NOTES"], 0)
            self.assertEqual(outcome.retrieval_log.retrieval_plan.filters.position, "turtle")
            self.assertTrue(all(item.metadata_digest.goal == "escape" for item in outcome.items))

    def test_dense_retrieval_contributes_rank_signals(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, _file_store, vector_store, _ingestion, _results = build_ingested_vector_stack(
                tmp,
                include_bjj=True,
                include_notes=True,
            )

            from server.app.retrieval import RetrievalService

            outcome = RetrievalService(repo, vector_store=vector_store).retrieve(
                query_text="tripod post inside elbow recovery",
                mode="full",
            )

            self.assertGreaterEqual(outcome.retrieval_log.dense_count, 1)
            self.assertTrue(any(item.rank_signals.dense_rank is not None for item in outcome.items))

    def test_fake_profile_cross_encoder_reranks_and_exposes_scores(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, _file_store, _ingestion, _results = build_ingested_stack(tmp, include_bjj=True, include_notes=False)

            from server.app.retrieval import RetrievalService

            outcome = RetrievalService(repo).retrieve(
                query_text="tripod post inside elbow recovery",
                mode="full",
                top_k=3,
            )

            self.assertTrue(outcome.retrieval_log.rerank_applied)
            self.assertEqual(outcome.retrieval_log.rerank_status, "success")
            self.assertEqual(outcome.retrieval_log.rerank_provider_name, "deterministic_mock_cross_encoder_v1")
            self.assertTrue(any(item.rank_signals.cross_encoder_score is not None for item in outcome.items))
            self.assertEqual(str(outcome.items[0].metadata_digest.date), "2026-03-04")

    def test_real_profile_hf_cross_encoder_reranks_candidates(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, _file_store, _ingestion, _results = build_ingested_stack(tmp, include_bjj=True, include_notes=False)

            from server.app.retrieval import RetrievalService
            from server.app.retrieval.reranker import HFCrossEncoderReranker

            runtime_config = RuntimeConfigSnapshot(
                reranker=RerankerConfig(
                    enabled=True,
                    provider="huggingface",
                    model="stub-local-cross-encoder",
                    candidate_pool_multiplier=3,
                    max_candidates=24,
                )
            )
            outcome = RetrievalService(
                repo,
                runtime_config=runtime_config,
                reranker=HFCrossEncoderReranker(runtime_config, backend=_StubHFBackend()),
            ).retrieve(
                query_text="tripod post inside elbow recovery",
                mode="full",
                top_k=3,
            )

            self.assertTrue(outcome.retrieval_log.rerank_applied)
            self.assertEqual(outcome.retrieval_log.rerank_status, "success")
            self.assertEqual(outcome.retrieval_log.rerank_provider_name, "hf_cross_encoder_v1")
            self.assertEqual(outcome.retrieval_log.rerank_model, "stub-local-cross-encoder")
            self.assertGreater(outcome.items[0].rank_signals.cross_encoder_score, 0.9)
            self.assertEqual(str(outcome.items[0].metadata_digest.date), "2026-03-04")

    def test_reranker_provider_unavailable_falls_back_without_scores(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, _file_store, _ingestion, _results = build_ingested_stack(tmp, include_bjj=True, include_notes=False)

            from server.app.retrieval import RetrievalService

            runtime_config = RuntimeConfigSnapshot(
                reranker=RerankerConfig(
                    enabled=True,
                    provider="openai",
                    model="stub-reranker",
                    candidate_pool_multiplier=3,
                    max_candidates=24,
                )
            )
            outcome = RetrievalService(
                repo,
                runtime_config=runtime_config,
                reranker=_UnavailableReranker(),
            ).retrieve(
                query_text="tripod post inside elbow recovery",
                mode="full",
                top_k=3,
            )

            self.assertFalse(outcome.retrieval_log.rerank_applied)
            self.assertEqual(outcome.retrieval_log.rerank_status, "provider_unavailable")
            self.assertEqual(outcome.retrieval_log.rerank_provider_name, "unavailable-reranker")
            self.assertTrue(all(item.rank_signals.cross_encoder_score is None for item in outcome.items))
