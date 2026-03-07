from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from server.tests.support import activate_test_profile, build_ingested_stack


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
