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
            self.assertFalse(outcome.llm_replan_invoked)

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

    def test_mixed_domain_prefers_domain_clarify_before_replan(self) -> None:
        from server.app.core import (
            EvidenceStrength,
            ProbeStats,
            RetrievalFilters,
            RuntimeConfigSnapshot,
            TimeSignal,
        )
        from server.app.orchestrator import ConversationState, OrchestratorService

        service = OrchestratorService(
            _StubRetrievalService(
                ProbeStats(
                    k=2,
                    probe_query_text="最近写作状态很差，也想复盘训练节奏",
                    probe_filters=RetrievalFilters(),
                    doc_type_hist={"BJJ": 1, "NOTES": 1, "p_bjj": 0.5, "p_notes": 0.5},
                    slot_value_hist={"position": {}, "orientation": {}, "goal": {}},
                    slot_entropy=0.0,
                    evidence_strength=EvidenceStrength(value=0.8, headness=0.8, coherence=0.8),
                    time_signal=TimeSignal(value=False),
                )
            ),
            runtime_config=RuntimeConfigSnapshot(),
        )

        outcome = service.route("最近写作状态很差，也想复盘训练节奏", session_state=ConversationState())

        self.assertEqual(outcome.execution_plan.next_action.value, "CLARIFY")
        self.assertEqual(outcome.execution_plan.clarify.slot.value, "domain")
        self.assertFalse(outcome.llm_replan_invoked)

    def test_low_evidence_invokes_mock_replan_once(self) -> None:
        from server.app.core import (
            DocumentType,
            EvidenceStrength,
            ProbeStats,
            RetrievalFilters,
            RuntimeConfigSnapshot,
            TimeSignal,
        )
        from server.app.orchestrator import ConversationState, OrchestratorService

        service = OrchestratorService(
            _StubRetrievalService(
                ProbeStats(
                    k=1,
                    probe_query_text="迷宫和镜子有什么联系",
                    probe_filters=RetrievalFilters(doc_type=DocumentType.NOTES),
                    doc_type_hist={"BJJ": 0, "NOTES": 1, "p_bjj": 0.0, "p_notes": 1.0},
                    slot_value_hist={"position": {}, "orientation": {}, "goal": {}},
                    slot_entropy=0.0,
                    evidence_strength=EvidenceStrength(value=0.1, headness=0.1, coherence=0.1),
                    time_signal=TimeSignal(value=False),
                )
            ),
            runtime_config=RuntimeConfigSnapshot(),
        )

        outcome = service.route("迷宫和镜子有什么联系", session_state=ConversationState())

        self.assertTrue(outcome.llm_replan_invoked)
        self.assertEqual(outcome.llm_replan_result, "success")
        self.assertEqual(outcome.execution_plan.next_action.value, "RETRIEVE")
        self.assertIn("MOCK_REPLAN_USED", outcome.execution_plan.explain.reason_codes)

    def test_replan_failure_falls_back_to_deterministic_builder(self) -> None:
        from server.app.core import (
            DocumentType,
            EvidenceStrength,
            ProbeStats,
            RetrievalFilters,
            RuntimeConfigSnapshot,
            TimeSignal,
        )
        from server.app.orchestrator import ConversationState, OrchestratorReplanner, OrchestratorService, ReplanAttempt

        class _FailingReplanner(OrchestratorReplanner):
            def replan(self, user_message, state, plan_check, probe_stats):
                return ReplanAttempt(invoked=True, result="provider_unavailable", execution_plan=None)

        service = OrchestratorService(
            _StubRetrievalService(
                ProbeStats(
                    k=1,
                    probe_query_text="迷宫和镜子有什么联系",
                    probe_filters=RetrievalFilters(doc_type=DocumentType.NOTES),
                    doc_type_hist={"BJJ": 0, "NOTES": 1, "p_bjj": 0.0, "p_notes": 1.0},
                    slot_value_hist={"position": {}, "orientation": {}, "goal": {}},
                    slot_entropy=0.0,
                    evidence_strength=EvidenceStrength(value=0.1, headness=0.1, coherence=0.1),
                    time_signal=TimeSignal(value=False),
                )
            ),
            runtime_config=RuntimeConfigSnapshot(),
            replanner=_FailingReplanner(RuntimeConfigSnapshot()),
        )

        outcome = service.route("迷宫和镜子有什么联系", session_state=ConversationState())

        self.assertTrue(outcome.llm_replan_invoked)
        self.assertEqual(outcome.llm_replan_result, "provider_unavailable")
        self.assertIn("LLM_REPLAN_DEFERRED_TO_DETERMINISTIC_FALLBACK", outcome.execution_plan.explain.reason_codes)


class _StubRetrievalOutcome:
    def __init__(self, probe_stats):
        self.probe_stats = probe_stats


class _StubRetrievalService:
    def __init__(self, probe_stats):
        self._probe_stats = probe_stats

    def retrieve(self, query_text, filters_hint=None, mode="probe", top_k=None):
        return _StubRetrievalOutcome(self._probe_stats)
