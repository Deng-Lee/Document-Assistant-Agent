from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from server.tests.support import activate_test_profile, build_ingested_stack


class OrchestratorServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        activate_test_profile("fake")

    def test_missing_core_slot_requests_clarify(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, _file_store, _ingestion, _results = build_ingested_stack(tmp, include_bjj=True, include_notes=False)
            from server.app.retrieval import RetrievalService

            retrieval_service = RetrievalService(repo)
            self.assertGreaterEqual(len(repo.list_chunks()), 1)

            from server.app.orchestrator import OrchestratorService

            outcome = OrchestratorService(retrieval_service).route("龟防怎么破解？我总是被人拉回去。")

            self.assertEqual(outcome.execution_plan.next_action.value, "CLARIFY")
            self.assertIsNotNone(outcome.session_state.pending_slot)
            self.assertIn("MISSING_CORE_", " ".join(outcome.execution_plan.explain.reason_codes))

    def test_pending_slot_resolution_updates_state(self) -> None:
        with TemporaryDirectory() as tmp:
            repo, _file_store, _ingestion, _results = build_ingested_stack(tmp, include_bjj=True, include_notes=False)
            from server.app.retrieval import RetrievalService

            retrieval_service = RetrievalService(repo)

            from server.app.orchestrator import ConversationState, OrchestratorService
            from server.app.core import ClarifySlot

            initial_state = ConversationState(
                pending_slot=ClarifySlot.ORIENTATION,
                clarify_round=1,
                slots={"position": "turtle", "goal": "escape"},
            )
            outcome = OrchestratorService(retrieval_service).route("下位", session_state=initial_state)

            self.assertIsNone(outcome.session_state.pending_slot)
            self.assertEqual(outcome.session_state.slots["orientation"], "下位")
            self.assertIn(outcome.execution_plan.next_action.value, {"RETRIEVE", "CLARIFY"})
