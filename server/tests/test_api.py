from __future__ import annotations

import json
import os
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from server.tests.support import create_test_app, dump_result, endpoint_map, make_trace_record, sample_bjj_markdown, sample_notes_markdown


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

    def test_root_route_serves_backend_landing_page_for_next_frontend(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            response = routes["/"]()
            body = response.body.decode("utf-8")
            self.assertIn("Backend API is running", body)
            self.assertIn("npm --prefix web run dev", body)
            self.assertIn("web/package.json", body)
            self.assertIn("/api/health", body)

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
            self.assertTrue(trace_payload["generation_log"]["prompt_hash"])
            self.assertTrue(trace_payload["generation_log"]["input_snapshot"])
            self.assertIn("query_original", trace_payload["generation_log"]["input_snapshot"])
            self.assertIsNone(trace_payload["generation_log"]["prompt_snapshot"]["query_original_preview"])

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
            profile_history = dump_result(routes["/api/profile/history"]())
            self.assertGreaterEqual(len(profile_history["profiles"]), 2)
            self.assertEqual(profile_history["profiles"][0]["profile_version_id"], profile_after["profile_version_id"])
            updated_chat = dump_result(routes["/api/chat/turn"](ChatTurnRequest(user_message="迷宫和镜子还能怎么写？")))
            updated_trace = dump_result(routes["/api/traces/{trace_id}"](updated_chat["trace_id"]))
            self.assertEqual(updated_trace["request_log"]["profile_version_id"], profile_after["profile_version_id"])

    def test_sft_train_endpoint_activates_policy_and_replay_uses_it(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            from server.app.api.models import ReplayRequest, SFTTrainAPIRequest
            from server.app.core import SFTExportRequest
            from server.app.observability import build_generation_input_snapshot, build_prompt_snapshot
            from server.app.core import ProfileSummary

            trace = make_trace_record(trace_id="trace_policy_api")
            input_snapshot = build_generation_input_snapshot(
                task=trace.request_log.task,
                query_original=trace.retrieval_log.retrieval_plan.query_original if trace.retrieval_log.retrieval_plan else "",
                query_clean=trace.retrieval_log.retrieval_plan.query_text if trace.retrieval_log.retrieval_plan else "",
                confirmed_slots=trace.request_log.confirmed_slots,
                coach_clarify_round=trace.generation_log.output.get("reasoning_status", {}).get("coach_clarify_round", 0),
                coach_pending_slot=None,
                profile_summary=ProfileSummary(profile_version_id=trace.request_log.profile_version_id or "profile_test"),
                frozen_evidence_pack=trace.evidence_log,
            )
            trace.generation_log.input_snapshot = input_snapshot
            trace.generation_log.prompt_snapshot = build_prompt_snapshot(input_snapshot)
            app.state.pda.trace_store.write_trace(trace)
            export_payload = dump_result(routes["/api/sft/export"](SFTExportRequest(trace_filter={})))
            export_dir = Path(export_payload["export_path"])
            exported = [json.loads(line) for line in (export_dir / "dataset_export.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            rows = []
            for sample in exported:
                target_output = dict(sample["baseline_output"])
                target_output["observations"][0]["text"] = "api policy tuned observation"
                rows.append(
                    {
                        "trace_id": sample["trace_id"],
                        "input": {
                            "task": sample["profile_summary"].get("task"),
                            "query_original": sample["profile_summary"].get("query_original", ""),
                            "query_clean": sample["profile_summary"].get("query_clean", ""),
                            "confirmed_slots": sample["confirmed_slots"],
                            "coach_pending_slot": sample["profile_summary"].get("coach_pending_slot"),
                            "profile_summary": sample["profile_summary"],
                            "gate_decision": sample["gate_decision"],
                            "coach_clarify_round": sample["coach_clarify_round"],
                            "allowed_evidence_ids": sample["allowed_evidence_ids"],
                            "evidence_pack_selected": sample["evidence_pack_selected"],
                        },
                        "target_output": target_output,
                    }
                )
            train_path = export_dir / "train.jsonl"
            train_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")

            train_payload = dump_result(
                routes["/api/sft/train"](
                    SFTTrainAPIRequest(
                        train_path=str(train_path),
                        output_path=str(Path(tmp) / "policy_ckpt"),
                        base_model="mock-bjj-base",
                        dry_run=False,
                        activate=True,
                    )
                )
            )
            self.assertTrue(train_payload["checkpoint"]["policy_model_ref"].startswith("policy://"))
            self.assertEqual(train_payload["active_policy_ref"], train_payload["checkpoint"]["policy_model_ref"])

            replay_payload = dump_result(
                routes["/api/replay/{trace_id}"]("trace_policy_api", ReplayRequest(model_variant="policy"))
            )
            self.assertIn("api policy tuned observation", json.dumps(replay_payload["final_answer"], ensure_ascii=False))

    def test_profile_persistence_survives_app_restart_and_keeps_history(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_test_app(tmp)
            routes = endpoint_map(app)

            from server.app.api.models import ProfilePatchRequest
            from server.app.api.state import create_app_state

            updated = dump_result(routes["PUT /api/profile"](ProfilePatchRequest(ruleset_default="NoGi")))
            self.assertEqual(updated["ruleset_default"], "NoGi")

            reloaded = create_app_state(tmp)
            self.assertEqual(reloaded.current_profile.profile_version_id, updated["profile_version_id"])
            self.assertEqual(reloaded.current_profile.ruleset_default, "NoGi")
            history = reloaded.profile_repository.list_profiles()
            self.assertGreaterEqual(len(history), 2)
            self.assertEqual(history[0].profile_version_id, updated["profile_version_id"])

    def test_create_app_state_loads_local_env_file(self) -> None:
        keys = ("PDA_MODEL_PROFILE", "PDA_MODEL_PROFILE_CONFIG_DIR", "OPENAI_API_KEY", "OPENAI_BASE_URL")
        original = {key: os.environ.get(key) for key in keys}
        try:
            for key in keys:
                os.environ.pop(key, None)
            os.environ["PDA_MODEL_PROFILE"] = "fake"
            with TemporaryDirectory() as tmp:
                Path(tmp, ".env").write_text(
                    "\n".join(
                        [
                            "PDA_MODEL_PROFILE=real",
                            "OPENAI_API_KEY=test-local-key",
                            "OPENAI_BASE_URL=https://example.invalid/v1",
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )

                from server.app.api.state import create_app_state

                state = create_app_state(tmp)
                self.assertEqual(state.runtime_config.model_routing.profile_name, "real")
                self.assertEqual(state.runtime_config.model_routing.provider, "openai")
                self.assertEqual(os.environ.get("OPENAI_API_KEY"), "test-local-key")
                self.assertEqual(os.environ.get("OPENAI_BASE_URL"), "https://example.invalid/v1")
                provider = state.orchestrator_service.replanner.provider
                self.assertEqual(getattr(provider, "api_key", None), "test-local-key")
                self.assertEqual(getattr(getattr(provider, "transport", None), "base_url", None), "https://example.invalid/v1")
                status = state.orchestrator_service.replanner.provider_status()
                self.assertEqual(status["profile_name"], "real")
                self.assertEqual(status["provider_name"], "OpenAIReplanProvider")
                self.assertTrue(status["configured"])
                self.assertEqual(status["base_url"], "https://example.invalid/v1")
                eval_status = state.evaluation_service.provider_status()
                self.assertEqual(eval_status["ragas"]["evaluator_name"], "openai_ragas_proxy_v1")
                self.assertTrue(eval_status["ragas"]["configured"])
                self.assertEqual(eval_status["ragas"]["base_url"], "https://example.invalid/v1")
                self.assertEqual(eval_status["judge"]["evaluator_name"], "openai_judge_v1")
                self.assertTrue(eval_status["judge"]["configured"])
                self.assertEqual(eval_status["judge"]["base_url"], "https://example.invalid/v1")
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_real_profile_can_be_loaded_from_custom_config_directory(self) -> None:
        keys = ("PDA_MODEL_PROFILE", "PDA_MODEL_PROFILE_CONFIG_DIR")
        original = {key: os.environ.get(key) for key in keys}
        try:
            for key in keys:
                os.environ.pop(key, None)
            with TemporaryDirectory() as tmp:
                config_dir = Path(tmp) / "profile_configs"
                config_dir.mkdir(parents=True)
                (config_dir / "real.json").write_text(
                    json.dumps(
                        {
                            "name": "real",
                            "provider": "openai",
                            "base_model": "qwen-plus",
                            "policy_model": "policy://pending",
                            "embedding_model": "text-embedding-v4",
                            "embedding_version_id": "text-embedding-v4:qwen",
                            "generation": {
                                "bjj": {"temperature": 0.2, "top_p": 0.95, "max_tokens": 1500},
                                "literary": {"temperature": 0.85, "top_p": 0.9, "max_tokens": 1700},
                                "replan": {"temperature": 0.05, "top_p": 1.0, "max_tokens": 700},
                                "safe_summary": {"temperature": 0.0, "top_p": 1.0, "max_tokens": 220},
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                os.environ["PDA_MODEL_PROFILE_CONFIG_DIR"] = str(config_dir)

                from server.app.core import build_runtime_config

                runtime_config = build_runtime_config("real")
                self.assertEqual(runtime_config.model_routing.base_model, "qwen-plus")
                self.assertEqual(runtime_config.model_routing.embedding_model, "text-embedding-v4")
                self.assertEqual(runtime_config.embedding_version_id, "text-embedding-v4:qwen")
                self.assertEqual(runtime_config.generation.replan["max_tokens"], 700)
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_real_profile_missing_config_file_raises_clear_error(self) -> None:
        original = os.environ.get("PDA_MODEL_PROFILE_CONFIG_DIR")
        try:
            with TemporaryDirectory() as tmp:
                os.environ["PDA_MODEL_PROFILE_CONFIG_DIR"] = str(Path(tmp) / "missing_profiles")
                from server.app.core import get_model_profile

                with self.assertRaises(ValueError) as exc:
                    get_model_profile("real")
                self.assertIn("Missing model profile config", str(exc.exception))
        finally:
            if original is None:
                os.environ.pop("PDA_MODEL_PROFILE_CONFIG_DIR", None)
            else:
                os.environ["PDA_MODEL_PROFILE_CONFIG_DIR"] = original
