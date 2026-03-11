from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from server.tests.support import create_test_app, dump_result, endpoint_map, make_trace_record


class ObservabilityTests(unittest.TestCase):
    def test_minimal_capture_redacts_raw_query_inputs_and_strips_debug_snapshots(self) -> None:
        from server.app.core import (
            CharRange,
            ChunkMetadataDigest,
            Distance,
            EvidencePack,
            EvidencePackItem,
            GenerationLog,
            LineRange,
            Orientation,
            ProfileSummary,
            RankSignals,
            RuntimeConfigSnapshot,
            SourceLocator,
            TraceCaptureLevel,
        )
        from server.app.observability import TraceRecorder, build_generation_input_snapshot, build_prompt_snapshot

        runtime_config = RuntimeConfigSnapshot(trace_capture_level=TraceCaptureLevel.MINIMAL)
        recorder = TraceRecorder(runtime_config_snapshot=runtime_config)
        evidence_pack = EvidencePack(
            items=[
                EvidencePackItem(
                    evidence_id="chunk_1",
                    doc_id="doc_1",
                    doc_version_id="dv_1",
                    locator=SourceLocator(
                        doc_version_id="dv_1",
                        source_path="bjj.md",
                        line_range=LineRange(start=1, end=4),
                        char_range=CharRange(start=0, end=64),
                    ),
                    safe_summary="safe summary",
                    excerpt_snapshot="raw excerpt that should only survive in debug",
                    metadata_digest=ChunkMetadataDigest(
                        position="turtle",
                        orientation=Orientation.BOTTOM,
                        distance=Distance.CLOSE,
                        goal="escape",
                    ),
                    rank_signals=RankSignals(rrf_rank=1),
                )
            ],
            token_budget=4000,
            per_doc_limit=3,
        )
        input_snapshot = build_generation_input_snapshot(
            task="COACH_BJJ",
            query_original="龟防怎么破解？",
            query_clean="龟防 怎么 破解",
            confirmed_slots={"position": "turtle"},
            coach_clarify_round=1,
            coach_pending_slot="opponent_control",
            profile_summary=ProfileSummary(profile_version_id="profile_seed"),
            frozen_evidence_pack=evidence_pack,
        )
        recorder.set_evidence_log(evidence_pack)
        recorder.set_generation_log(
            GenerationLog(
                provider="mock",
                model="mock-bjj-base",
                prompt_version="bjj.v1",
                prompt_snapshot=build_prompt_snapshot(input_snapshot),
                input_snapshot=input_snapshot,
                output={"mode": "FULL"},
            )
        )
        trace = recorder.to_trace_record()

        self.assertTrue(trace.generation_log.prompt_hash)
        self.assertEqual(trace.generation_log.input_snapshot.query_original, "")
        self.assertEqual(trace.generation_log.input_snapshot.query_clean, "")
        self.assertEqual(trace.generation_log.input_snapshot.coach_pending_slot, "opponent_control")
        self.assertIsNone(trace.generation_log.input_snapshot.profile_summary_snapshot)
        self.assertEqual(trace.generation_log.input_snapshot.profile_version_id, "profile_seed")
        self.assertIsNone(trace.evidence_log.items[0].excerpt_snapshot)
        self.assertIsNone(trace.generation_log.input_snapshot.frozen_evidence_pack.items[0].excerpt_snapshot)
        self.assertIsNone(trace.generation_log.prompt_snapshot.query_original_preview)
        self.assertEqual(trace.generation_log.prompt_snapshot.confirmed_slots_snapshot, {})
        self.assertEqual(trace.generation_log.prompt_snapshot.confirmed_slot_keys, ["position"])
        self.assertTrue(any(event.name == "generation.metadata" for event in trace.events))

    def test_debug_capture_keeps_prompt_and_evidence_snapshots(self) -> None:
        from server.app.core import (
            CharRange,
            ChunkMetadataDigest,
            Distance,
            EvidencePack,
            EvidencePackItem,
            GenerationLog,
            LineRange,
            Orientation,
            ProfileSummary,
            RankSignals,
            RuntimeConfigSnapshot,
            SourceLocator,
            TraceCaptureLevel,
        )
        from server.app.observability import TraceRecorder, build_generation_input_snapshot, build_prompt_snapshot

        runtime_config = RuntimeConfigSnapshot(trace_capture_level=TraceCaptureLevel.DEBUG)
        recorder = TraceRecorder(runtime_config_snapshot=runtime_config)
        evidence_pack = EvidencePack(
            items=[
                EvidencePackItem(
                    evidence_id="chunk_1",
                    doc_id="doc_1",
                    doc_version_id="dv_1",
                    locator=SourceLocator(
                        doc_version_id="dv_1",
                        source_path="bjj.md",
                        line_range=LineRange(start=1, end=4),
                        char_range=CharRange(start=0, end=64),
                    ),
                    safe_summary="safe summary",
                    excerpt_snapshot="debug excerpt survives",
                    metadata_digest=ChunkMetadataDigest(
                        position="turtle",
                        orientation=Orientation.BOTTOM,
                        distance=Distance.CLOSE,
                        goal="escape",
                    ),
                    rank_signals=RankSignals(rrf_rank=1),
                )
            ]
        )
        input_snapshot = build_generation_input_snapshot(
            task="COACH_BJJ",
            query_original="龟防怎么破解？",
            query_clean="龟防 怎么 破解",
            confirmed_slots={"position": "turtle"},
            coach_clarify_round=1,
            coach_pending_slot="opponent_control",
            profile_summary=ProfileSummary(profile_version_id="profile_seed"),
            frozen_evidence_pack=evidence_pack,
        )
        recorder.set_evidence_log(evidence_pack)
        recorder.set_generation_log(
            GenerationLog(
                provider="mock",
                model="mock-bjj-base",
                prompt_version="bjj.v1",
                prompt_snapshot=build_prompt_snapshot(input_snapshot),
                input_snapshot=input_snapshot,
                output={"mode": "FULL"},
            )
        )
        trace = recorder.to_trace_record()

        self.assertEqual(trace.evidence_log.items[0].excerpt_snapshot, "debug excerpt survives")
        self.assertEqual(
            trace.generation_log.input_snapshot.frozen_evidence_pack.items[0].excerpt_snapshot,
            "debug excerpt survives",
        )
        self.assertEqual(trace.generation_log.prompt_snapshot.query_original_preview, "龟防怎么破解？")
        self.assertEqual(trace.generation_log.prompt_snapshot.confirmed_slots_snapshot, {"position": "turtle"})
        self.assertEqual(trace.generation_log.prompt_snapshot.frozen_evidence_ids, ["chunk_1"])

    def test_replay_uses_frozen_generation_input_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            from server.app.api.models import ReplayRequest
            from server.app.core import ProfileSummary
            from server.app.observability import build_generation_input_snapshot, build_prompt_snapshot

            seed_trace = make_trace_record(trace_id="trace_seed")
            frozen_profile = ProfileSummary(profile_version_id="profile_seed", ruleset_default="Gi")
            input_snapshot = build_generation_input_snapshot(
                task=seed_trace.request_log.task,
                query_original="原始问题",
                query_clean="原始问题",
                confirmed_slots=seed_trace.request_log.confirmed_slots,
                coach_clarify_round=1,
                coach_pending_slot="opponent_control",
                profile_summary=frozen_profile,
                frozen_evidence_pack=seed_trace.evidence_log,
            )
            seed_trace.request_log.profile_version_id = frozen_profile.profile_version_id
            seed_trace.generation_log.input_snapshot = input_snapshot
            seed_trace.generation_log.prompt_snapshot = build_prompt_snapshot(input_snapshot)
            seed_trace.generation_log.prompt_hash = None
            app.state.pda.trace_store.write_trace(seed_trace)
            app.state.pda.current_profile = ProfileSummary(profile_version_id="profile_live", ruleset_default="NoGi")

            replay_payload = dump_result(routes["/api/replay/{trace_id}"]("trace_seed", ReplayRequest()))
            replay_trace = dump_result(routes["/api/traces/{trace_id}"](replay_payload["trace_id"]))
            replay_input = app.state.pda.sft_service.resolve_replay_input_snapshot(
                app.state.pda.trace_store.read_trace("trace_seed"),
                app.state.pda.current_profile,
            )

            self.assertEqual(replay_input.profile_summary_snapshot.profile_version_id, "profile_seed")
            self.assertEqual(replay_input.query_original, "原始问题")
            self.assertEqual(replay_trace["generation_log"]["input_snapshot"]["query_original"], "")
            self.assertEqual(replay_trace["generation_log"]["input_snapshot"]["coach_pending_slot"], "opponent_control")
            self.assertTrue(replay_trace["generation_log"]["prompt_hash"])

    def test_replay_rehydrates_redacted_minimal_input_snapshot_from_retrieval_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            from server.app.api.models import ReplayRequest
            from server.app.core import ProfileSummary, RuntimeConfigSnapshot, TraceCaptureLevel
            from server.app.observability import TraceRecorder, build_generation_input_snapshot, build_prompt_snapshot

            seed_trace = make_trace_record(trace_id="trace_minimal_seed")
            frozen_profile = ProfileSummary(profile_version_id="profile_seed", ruleset_default="Gi")
            recorder = TraceRecorder(
                runtime_config_snapshot=RuntimeConfigSnapshot(trace_capture_level=TraceCaptureLevel.MINIMAL),
                trace_id=seed_trace.trace_id,
                conversation_id=seed_trace.conversation_id,
            )
            recorder.set_request_log(seed_trace.request_log)
            recorder.set_retrieval_log(seed_trace.retrieval_log)
            recorder.set_evidence_log(seed_trace.evidence_log)
            input_snapshot = build_generation_input_snapshot(
                task=seed_trace.request_log.task,
                query_original="原始问题",
                query_clean="原始问题",
                confirmed_slots=seed_trace.request_log.confirmed_slots,
                coach_clarify_round=1,
                coach_pending_slot="opponent_control",
                profile_summary=frozen_profile,
                frozen_evidence_pack=seed_trace.evidence_log,
            )
            seed_trace.generation_log.input_snapshot = input_snapshot
            seed_trace.generation_log.prompt_snapshot = build_prompt_snapshot(input_snapshot)
            recorder.set_generation_log(seed_trace.generation_log)
            minimal_trace = recorder.to_trace_record()
            app.state.pda.trace_store.write_trace(minimal_trace)
            app.state.pda.current_profile = ProfileSummary(profile_version_id="profile_live", ruleset_default="NoGi")

            stored_trace = dump_result(routes["/api/traces/{trace_id}"]("trace_minimal_seed"))
            self.assertEqual(stored_trace["generation_log"]["input_snapshot"]["query_original"], "")
            self.assertEqual(stored_trace["generation_log"]["input_snapshot"]["query_clean"], "")

            replay_payload = dump_result(routes["/api/replay/{trace_id}"]("trace_minimal_seed", ReplayRequest()))
            replay_trace = dump_result(routes["/api/traces/{trace_id}"](replay_payload["trace_id"]))
            replay_input = app.state.pda.sft_service.resolve_replay_input_snapshot(
                app.state.pda.trace_store.read_trace("trace_minimal_seed"),
                app.state.pda.current_profile,
            )

            self.assertEqual(replay_input.query_original, "turtle escape")
            self.assertEqual(replay_input.query_clean, "turtle escape")
            self.assertEqual(replay_input.profile_summary_snapshot.profile_version_id, "profile_seed")
            self.assertEqual(replay_trace["generation_log"]["input_snapshot"]["query_original"], "")
