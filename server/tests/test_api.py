from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from server.tests.support import create_test_app, dump_result, endpoint_map, sample_bjj_markdown, sample_notes_markdown


class APITests(unittest.TestCase):
    def test_ingest_retrieve_and_jobs_endpoints(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            from server.app.api.models import IngestTextRequest, RetrieveRequest, RunJobsRequest

            ingest_payload = dump_result(
                routes["/api/ingest/text"](
                IngestTextRequest(markdown_text=sample_notes_markdown(), source_path_hint="notes.md")
                )
            )
            self.assertTrue(ingest_payload["doc_id"])
            self.assertTrue(ingest_payload["jobs"])

            job_list = dump_result(routes["/api/jobs"]())
            self.assertGreaterEqual(len(job_list["jobs"]), 1)

            run_job_payload = dump_result(routes["/api/jobs/run-next"](RunJobsRequest(job_types=["safe_summary_build"])))
            self.assertEqual(run_job_payload["result"]["job"]["status"], "succeeded")

            retrieve_payload = dump_result(routes["/api/retrieve"](RetrieveRequest(query_text="maze mirror", mode="full")))
            self.assertGreaterEqual(len(retrieve_payload["evidence_pack"]["items"]), 1)

    def test_ingest_file_and_directory_endpoints(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            import_root = Path(tmp) / "imports"
            nested_root = import_root / "nested"
            nested_root.mkdir(parents=True)
            notes_path = import_root / "notes.md"
            bjj_path = nested_root / "bjj.markdown"
            ignored_path = import_root / "ignore.txt"
            notes_path.write_text(sample_notes_markdown(), encoding="utf-8")
            bjj_path.write_text(sample_bjj_markdown(), encoding="utf-8")
            ignored_path.write_text("ignore me", encoding="utf-8")

            from server.app.api.models import IngestDirRequest, IngestFileRequest

            file_payload = dump_result(routes["/api/ingest/file"](IngestFileRequest(path="imports/notes.md")))
            self.assertEqual(file_payload["source_path"], str(notes_path.resolve()))
            self.assertTrue(file_payload["chunk_ids"])
            self.assertTrue(file_payload["jobs"])

            dir_payload = dump_result(routes["/api/ingest/dir"](IngestDirRequest(path="imports")))
            self.assertEqual(dir_payload["root_path"], str(import_root.resolve()))
            self.assertEqual(dir_payload["imported_count"], 2)
            self.assertEqual(
                [item["source_path"] for item in dir_payload["results"]],
                sorted([str(notes_path.resolve()), str(bjj_path.resolve())]),
            )
            self.assertTrue(all(item["jobs"] for item in dir_payload["results"]))

    def test_root_route_serves_web_shell(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            response = routes["/"]()
            self.assertTrue(str(response.path).endswith("web/app/index.html"))
            self.assertTrue(Path(response.path).exists())
            self.assertTrue((Path(response.path).with_name("app.js")).exists())
            self.assertTrue((Path(response.path).with_name("styles.css")).exists())

    def test_chat_turn_persists_conversation_state(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            from server.app.api.models import ChatTurnRequest, IngestTextRequest

            routes["/api/ingest/text"](
                IngestTextRequest(markdown_text=sample_bjj_markdown(), source_path_hint="bjj.md")
            )
            first_turn = dump_result(
                routes["/api/chat/turn"](
                    ChatTurnRequest(user_message="龟防怎么破解？我总是被人拉回去。")
                )
            )

            self.assertEqual(first_turn["response_type"], "clarify_request")
            conversation_id = first_turn["conversation_id"]
            asked_slot = first_turn["response"]["slot"]
            conversation = dump_result(routes["/api/chat/{conversation_id}"](conversation_id))
            self.assertEqual(conversation["last_state"]["pending_slot"], asked_slot)

            second_turn = dump_result(
                routes["/api/chat/turn"](
                    ChatTurnRequest(conversation_id=conversation_id, user_message="下位")
                )
            )
            self.assertIn(second_turn["response_type"], {"clarify_request", "final_answer"})

            updated = dump_result(routes["/api/chat/{conversation_id}"](conversation_id))
            self.assertEqual(updated["last_state"]["slots"][asked_slot], "下位")
            self.assertEqual(len(updated["turns"]), 2)

    def test_write_intent_redirects_to_record_flow(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            from server.app.api.models import ChatTurnRequest

            response = dump_result(routes["/api/chat/turn"](ChatTurnRequest(user_message="帮我记录一条训练")))

            self.assertEqual(response["response_type"], "clarify_request")
            self.assertEqual(response["response"]["template_id"], "REDIRECT_RECORD_V1")
            traces = dump_result(routes["/api/traces"]())
            self.assertGreaterEqual(len(traces["traces"]), 1)

    def test_replan_trace_event_and_plan_check_are_persisted(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)
            from server.app.core import (
                ClarifyDirective,
                ClarifySlot,
                DomainType,
                ExecutionPlan,
                ExecutionPlanExplain,
                NextAction,
                PlanCheck,
                TaskType,
            )
            from server.app.orchestrator import ConversationState, OrchestratorOutcome
            from server.app.api.models import ChatTurnRequest

            class _ReplanStub:
                def route(self, user_message, session_state=None, entrypoint=None):
                    return OrchestratorOutcome(
                        session_state=session_state or ConversationState(),
                        execution_plan=ExecutionPlan(
                            task=TaskType.MIXED,
                            domain=DomainType.MIXED,
                            slots={},
                            next_action=NextAction.CLARIFY,
                            clarify=ClarifyDirective(
                                slot=ClarifySlot.DOMAIN,
                                question_template_id="ASK_DOMAIN_V1",
                                options=["训练", "写作/阅读"],
                            ),
                            explain=ExecutionPlanExplain(reason_codes=["DOMAIN_UNCLEAR"], probe_used=True),
                        ),
                        plan_check=PlanCheck(
                            domain=DomainType.MIXED,
                            task_hint=TaskType.MIXED,
                            need_replan=True,
                            need_clarify=False,
                            confidence_hint=0.4,
                            reason_codes=["DOMAIN_UNCLEAR"],
                        ),
                        llm_replan_invoked=True,
                        llm_replan_result="success",
                    )

            app.state.pda.orchestrator_service = _ReplanStub()
            response = dump_result(
                routes["/api/chat/turn"](
                    ChatTurnRequest(user_message="最近写作状态很差，也想复盘训练节奏。")
                )
            )

            trace_payload = dump_result(routes["/api/traces/{trace_id}"](response["trace_id"]))
            self.assertIsNotNone(trace_payload["request_log"]["plan_check"])
            replan_events = [event for event in trace_payload["events"] if event["name"] == "orchestrator.replan_llm"]
            self.assertEqual(len(replan_events), 1)
            self.assertTrue(replan_events[0]["attributes"]["invoked"])
            self.assertEqual(replan_events[0]["attributes"]["result"], "success")

    def test_management_endpoints_return_typed_payloads(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            from server.app.api.models import ChatTurnRequest, EvalRunAPIRequest, IngestTextRequest, ProfilePatchRequest, ReplayRequest
            from server.app.core import SFTExportRequest

            routes["/api/ingest/text"](
                IngestTextRequest(markdown_text=sample_bjj_markdown(), source_path_hint="bjj.md")
            )
            chat_response = dump_result(routes["/api/chat/turn"](ChatTurnRequest(user_message="龟防怎么破解？我总是被人拉回去。")))
            trace_id = chat_response["trace_id"]

            traces_payload = dump_result(routes["/api/traces"]())
            self.assertGreaterEqual(len(traces_payload["traces"]), 1)
            self.assertIn(trace_id, {item["trace_id"] for item in traces_payload["traces"]})

            trace_payload = dump_result(routes["/api/traces/{trace_id}"](trace_id))
            self.assertEqual(trace_payload["trace_id"], trace_id)

            replay_payload = dump_result(routes["/api/replay/{trace_id}"](trace_id, ReplayRequest()))
            self.assertTrue(replay_payload["trace_id"])
            self.assertTrue(replay_payload["final_answer"])

            eval_payload = dump_result(routes["/api/eval/run"](EvalRunAPIRequest(eval_set_id="api_eval", trace_ids=[trace_id])))
            self.assertTrue(eval_payload["eval_run_id"])

            eval_results = dump_result(routes["/api/eval/results"]())
            self.assertGreaterEqual(len(eval_results["runs"]), 1)

            sft_payload = dump_result(routes["/api/sft/export"](SFTExportRequest(trace_filter={})))
            self.assertTrue(sft_payload["export_path"])
            self.assertGreaterEqual(sft_payload["manifest"]["sample_count"], 1)

            profile_before = dump_result(routes["GET /api/profile"]())
            self.assertTrue(profile_before["profile_version_id"])
            profile_after = dump_result(
                routes["PUT /api/profile"](ProfilePatchRequest(ruleset_default="NoGi"))
            )
            self.assertEqual(profile_after["ruleset_default"], "NoGi")
