from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from server.tests.support import create_test_app, endpoint_map, sample_bjj_markdown, sample_notes_markdown


class APITests(unittest.TestCase):
    def test_ingest_retrieve_and_jobs_endpoints(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            from server.app.api.models import IngestTextRequest, RetrieveRequest, RunJobsRequest

            ingest_payload = routes["/api/ingest/text"](
                IngestTextRequest(markdown_text=sample_notes_markdown(), source_path_hint="notes.md")
            )
            self.assertTrue(ingest_payload["doc_id"])
            self.assertTrue(ingest_payload["jobs"])

            job_list = routes["/api/jobs"]()
            self.assertGreaterEqual(len(job_list["jobs"]), 1)

            run_job_payload = routes["/api/jobs/run-next"](RunJobsRequest(job_types=["safe_summary_build"]))
            self.assertEqual(run_job_payload["result"]["job"]["status"], "succeeded")

            retrieve_payload = routes["/api/retrieve"](RetrieveRequest(query_text="maze mirror", mode="full"))
            self.assertGreaterEqual(len(retrieve_payload["evidence_pack"]["items"]), 1)

    def test_chat_turn_persists_conversation_state(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            from server.app.api.models import ChatTurnRequest, IngestTextRequest

            routes["/api/ingest/text"](
                IngestTextRequest(markdown_text=sample_bjj_markdown(), source_path_hint="bjj.md")
            )
            first_turn = routes["/api/chat/turn"](
                ChatTurnRequest(user_message="龟防怎么破解？我总是被人拉回去。")
            )

            self.assertEqual(first_turn["response_type"], "clarify_request")
            conversation_id = first_turn["conversation_id"]
            asked_slot = first_turn["response"]["slot"]
            conversation = routes["/api/chat/{conversation_id}"](conversation_id)
            self.assertEqual(conversation["last_state"]["pending_slot"], asked_slot)

            second_turn = routes["/api/chat/turn"](
                ChatTurnRequest(conversation_id=conversation_id, user_message="下位")
            )
            self.assertIn(second_turn["response_type"], {"clarify_request", "final_answer"})

            updated = routes["/api/chat/{conversation_id}"](conversation_id)
            self.assertEqual(updated["last_state"]["slots"][asked_slot], "下位")
            self.assertEqual(len(updated["turns"]), 2)

    def test_write_intent_redirects_to_record_flow(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            from server.app.api.models import ChatTurnRequest

            response = routes["/api/chat/turn"](ChatTurnRequest(user_message="帮我记录一条训练"))

            self.assertEqual(response["response_type"], "clarify_request")
            self.assertEqual(response["response"]["template_id"], "REDIRECT_RECORD_V1")
            traces = routes["/api/traces"]()
            self.assertGreaterEqual(len(traces["traces"]), 1)
