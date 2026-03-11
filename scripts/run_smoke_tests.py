#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run repository smoke tests.")
    parser.add_argument(
        "--profile",
        choices=["fake", "real"],
        default=os.getenv("PDA_MODEL_PROFILE", "fake"),
        help="Model/settings profile to activate before imports.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ["PDA_MODEL_PROFILE"] = args.profile
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    frontend_package = repo_root / "web" / "package.json"
    frontend_config = repo_root / "web" / "next.config.mjs"
    frontend_routes = [
        repo_root / "web" / "app" / "layout.js",
        repo_root / "web" / "app" / "page.js",
        repo_root / "web" / "app" / "chat" / "page.js",
        repo_root / "web" / "app" / "traces" / "page.js",
        repo_root / "web" / "app" / "evaluation" / "page.js",
        repo_root / "web" / "components" / "dashboard-client.jsx",
        repo_root / "web" / "components" / "chat-client.jsx",
        repo_root / "web" / "components" / "traces-client.jsx",
        repo_root / "web" / "components" / "evaluation-client.jsx",
        repo_root / "web" / "lib" / "api.js",
        repo_root / "web" / "lib" / "chat-stream.js",
    ]
    package_payload = json.loads(frontend_package.read_text(encoding="utf-8"))
    assert package_payload["dependencies"]["next"]
    assert package_payload["scripts"]["build"] == "next build"
    assert frontend_config.exists()
    for route_path in frontend_routes:
        assert route_path.exists(), f"missing frontend path: {route_path}"
    print("frontend_smoke_ok")

    original_profile = os.environ.get("PDA_MODEL_PROFILE")
    original_api_key = os.environ.get("OPENAI_API_KEY")
    original_base_url = os.environ.get("OPENAI_BASE_URL")
    try:
        with TemporaryDirectory() as tmp_real:
            real_root = Path(tmp_real)
            (real_root / ".env").write_text(
                "\n".join(
                    [
                        "PDA_MODEL_PROFILE=real",
                        "OPENAI_API_KEY=smoke-real-key",
                        "OPENAI_BASE_URL=https://smoke.example.invalid/v1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            os.environ.pop("PDA_MODEL_PROFILE", None)
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("OPENAI_BASE_URL", None)
            from server.app.api.state import create_app_state

            real_state = create_app_state(real_root)
            retrieval_status = real_state.retrieval_service.provider_status()
            assert retrieval_status["profile_name"] == "real"
            assert retrieval_status["provider_name"] == "HFCrossEncoderReranker"
            assert retrieval_status["configured"] is False
            assert retrieval_status["model"] == "BAAI/bge-reranker-base"
            assert retrieval_status["base_url"] is None
            assert "torch" in retrieval_status["missing_dependencies"]
            assert "transformers" in retrieval_status["missing_dependencies"]
            print("real_retrieval_reranker_smoke_ok")
            replan_status = real_state.orchestrator_service.replanner.provider_status()
            assert replan_status["profile_name"] == "real"
            assert replan_status["provider_name"] == "OpenAIReplanProvider"
            assert replan_status["configured"] is True
            assert replan_status["base_url"] == "https://smoke.example.invalid/v1"
            print("real_replan_provider_smoke_ok")
            evaluation_status = real_state.evaluation_service.provider_status()
            assert evaluation_status["ragas"]["profile_name"] == "real"
            assert evaluation_status["ragas"]["evaluator_name"] == "ragas_external_v1"
            assert evaluation_status["ragas"]["configured"] is False
            assert evaluation_status["ragas"]["base_url"] == "https://smoke.example.invalid/v1"
            assert "ragas" in evaluation_status["ragas"]["missing_dependencies"]
            assert evaluation_status["judge"]["profile_name"] == "real"
            assert evaluation_status["judge"]["evaluator_name"] == "openai_judge_v1"
            assert evaluation_status["judge"]["configured"] is True
            assert evaluation_status["judge"]["base_url"] == "https://smoke.example.invalid/v1"
            print("real_eval_provider_smoke_ok")
            sft_status = real_state.sft_service.training_backend_status()
            assert sft_status["backend_name"] == "hf_lora_qlora_v1"
            assert sft_status["script_exists"] is True
            assert sft_status["script_path"].endswith("scripts/train_policy_lora.py")
            print("real_sft_backend_smoke_ok")
            sft_inference_status = real_state.sft_service.inference_backend_status()
            assert sft_inference_status["backend_name"] == "hf_lora_qlora_inference_v1"
            assert "missing_dependencies" in sft_inference_status
            print("real_sft_inference_backend_smoke_ok")
    finally:
        if original_profile is None:
            os.environ.pop("PDA_MODEL_PROFILE", None)
        else:
            os.environ["PDA_MODEL_PROFILE"] = original_profile
        if original_api_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = original_api_key
        if original_base_url is None:
            os.environ.pop("OPENAI_BASE_URL", None)
        else:
            os.environ["OPENAI_BASE_URL"] = original_base_url

    from server.app.core import (
        ClarifyDirective,
        ClarifySlot,
        CharRange,
        ChunkMetadataDigest,
        ChunkRecord,
        ChunkType,
        Distance,
        DomainType,
        DocumentRecord,
        DocumentType,
        DocVersionRecord,
        EntryPoint,
        EvalRunRequest,
        EvidenceStrength,
        EvidencePack,
        GenerationLog,
        LineRange,
        ModelVariant,
        Orientation,
        PlanCheck,
        ProfileSummary,
        RequestLog,
        RetrievalLog,
        RetrievalFilters,
        ProbeStats,
        RuntimeConfigSnapshot,
        SFTExportRequest,
        SourceLocator,
        TaskType,
        TimeSignal,
        TraceRecord,
        ExecutionPlan,
        ExecutionPlanExplain,
        NextAction,
        active_model_profile_name,
        export_contract_schemas,
    )
    from server.app.agents import BJJCoachService, LiteraryService
    from server.app.agents.bjj_coach.types import BJJCoachInput
    from server.app.api import create_app
    from server.app.api.models import (
        ChatTurnRequest,
        EvalRunAPIRequest,
        EvalRubricSubmitRequest,
        IngestDirRequest,
        IngestFileRequest,
        IngestTextRequest,
        ProfilePatchRequest,
        ReplayRequest,
        RetrieveRequest,
        RunJobsRequest,
        SFTTrainAPIRequest,
    )
    from server.app.evaluation import EvaluationService
    from server.app.ingestion import IngestionService
    from server.app.jobs import JobService
    from server.app.observability import TraceRecorder
    from server.app.orchestrator import ConversationState, OrchestratorService
    from server.app.retrieval import RetrievalService
    from server.app.sft import SFTService
    from server.app.storage import (
        ChromaVectorStoreAdapter,
        JSONTraceStore,
        LocalFileStore,
        SQLiteDocumentRepository,
        SQLiteGoldenCaseRepository,
        SQLiteJobRepository,
        SQLiteStore,
    )

    print(f"active_profile={active_model_profile_name()}")

    schemas = export_contract_schemas()
    assert "trace_record" in schemas
    assert "runtime_config_snapshot" in schemas
    print("core_schema_smoke_ok")

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = SQLiteDocumentRepository(SQLiteStore(root / "sqlite" / "app.db"))
        file_store = LocalFileStore(root / "filestore")
        trace_store = JSONTraceStore(root / "traces")
        repo.init_schema()

        document = DocumentRecord(
            doc_id="doc_1",
            doc_type=DocumentType.BJJ,
            title="BJJ Log",
            latest_version_id="dv_1",
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        version = DocVersionRecord(
            doc_version_id="dv_1",
            doc_id="doc_1",
            content_hash="hash",
            ingest_time=_utcnow(),
            source_path="logs.md",
            size_bytes=128,
        )
        chunk = ChunkRecord(
            chunk_id="chunk_1",
            doc_id="doc_1",
            doc_version_id="dv_1",
            doc_type=DocumentType.BJJ,
            chunk_type=ChunkType.BJJ_RECORD,
            locator=SourceLocator(
                doc_version_id="dv_1",
                source_path="logs.md",
                line_range=LineRange(start=1, end=8),
                char_range=CharRange(start=0, end=120),
            ),
            metadata_digest=ChunkMetadataDigest(
                date=_date(2026, 3, 4),
                position="turtle",
                orientation=Orientation.BOTTOM,
                distance=Distance.CLOSE,
                goal="escape",
            ),
            clean_search_text="turtle escape",
        )
        repo.upsert_document(document)
        repo.insert_doc_version(version)
        repo.insert_chunk(chunk)
        assert repo.list_chunks_for_doc_version("dv_1")[0].chunk_id == "chunk_1"

        snapshot_ref = file_store.write_markdown_snapshot("doc_1", "dv_1", "# test")
        assert file_store.read_markdown_snapshot(snapshot_ref) == "# test"

        trace = TraceRecord(
            trace_id="trace_1",
            runtime_config_snapshot=RuntimeConfigSnapshot(),
            request_log=RequestLog(entrypoint="chat"),
            retrieval_log=RetrievalLog(),
            evidence_log=EvidencePack(),
            generation_log=GenerationLog(provider="mock", model="mock-bjj-base", prompt_version="bjj.v1"),
        )
        trace_store.write_trace(trace)
        assert trace_store.read_trace("trace_1").trace_id == "trace_1"
        print("storage_smoke_ok")

    bjj_markdown = """---\n"""
    bjj_markdown += "type: BJJ\n"
    bjj_markdown += "title: Training Log\n"
    bjj_markdown += "---\n\n"
    bjj_markdown += "## 2026-03-04\n"
    bjj_markdown += "- position: turtle\n"
    bjj_markdown += "- orientation: 下位\n"
    bjj_markdown += "- distance: 近距离\n"
    bjj_markdown += "- goal: escape\n"
    bjj_markdown += "- your_action: tripod post\n"
    bjj_markdown += "- opponent_response: pulled me back to turtle\n"
    bjj_markdown += "- opponent_control: 袖子\n"
    bjj_markdown += "- your_adjustment: inside elbow recovery\n"
    bjj_markdown += "- notes: head position was late\n"

    notes_markdown = """---\n"""
    notes_markdown += "type: notes\n"
    notes_markdown += "title: Reading Notes\n"
    notes_markdown += "---\n\n"
    notes_markdown += "# Borges\n\n"
    notes_markdown += "Memory is not a warehouse.\n"
    notes_markdown += "It is a staging ground.\n\n"
    notes_markdown += "## Fragments\n\n"
    notes_markdown += "A library can be a maze and a mirror.\n"

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = SQLiteDocumentRepository(SQLiteStore(root / "sqlite" / "app.db"))
        file_store = LocalFileStore(root / "filestore")
        ingestion = IngestionService(repo, file_store)

        bjj_result = ingestion.ingest_text(bjj_markdown, source_path_hint="bjj.md")
        notes_result = ingestion.ingest_text(notes_markdown, source_path_hint="notes.md")

        assert bjj_result.document.doc_type == DocumentType.BJJ
        assert len(bjj_result.chunks) == 1
        assert bjj_result.chunks[0].metadata_digest.position == "turtle"
        assert notes_result.document.doc_type == DocumentType.NOTES
        assert len(notes_result.chunks) >= 1
        assert notes_result.chunks[0].metadata_digest.heading_path[0] == "Borges"
        print("ingestion_smoke_ok")

        retrieval = RetrievalService(repo)
        retrieval_outcome = retrieval.retrieve("turtle 下位 逃脱", mode="probe")
        assert len(retrieval_outcome.items) >= 1
        assert retrieval_outcome.probe_stats is not None
        assert retrieval_outcome.probe_stats.doc_type_hist["BJJ"] >= 1
        assert retrieval_outcome.retrieval_log.rerank_applied is True
        assert any(item.rank_signals.cross_encoder_score is not None for item in retrieval_outcome.items)
        print("retrieval_smoke_ok")

        orchestrator = OrchestratorService(retrieval)
        write_outcome = orchestrator.route("帮我记录一条训练", entrypoint=EntryPoint.RECORD)
        assert write_outcome.execution_plan.next_action.value == "WRITE_FLOW"

        clarify_outcome = orchestrator.route("龟防怎么破解？我总是被人拉回去。")
        assert clarify_outcome.execution_plan.next_action.value == "CLARIFY"
        assert clarify_outcome.session_state.pending_slot is not None
        assert clarify_outcome.llm_replan_invoked is False

        follow_up = orchestrator.route(
            "下位",
            session_state=ConversationState(
                pending_slot=clarify_outcome.session_state.pending_slot,
                clarify_round=clarify_outcome.session_state.clarify_round,
                slots={"position": "turtle", "goal": "escape"},
            ),
        )
        assert follow_up.session_state.pending_slot is None
        assert follow_up.execution_plan.next_action.value in {"RETRIEVE", "CLARIFY"}

        mixed_outcome = OrchestratorService(
            _SmokeRetrievalService(
                ProbeStats(
                    k=2,
                    probe_query_text="最近写作状态很差，也想复盘训练节奏。",
                    probe_filters=RetrievalFilters(),
                    doc_type_hist={"BJJ": 1, "NOTES": 1, "p_bjj": 0.5, "p_notes": 0.5},
                    slot_value_hist={"position": {}, "orientation": {}, "goal": {}},
                    slot_entropy=0.0,
                    evidence_strength=EvidenceStrength(value=0.8, headness=0.8, coherence=0.8),
                    time_signal=TimeSignal(value=False),
                )
            )
        ).route("最近写作状态很差，也想复盘训练节奏。")
        assert mixed_outcome.execution_plan.next_action.value == "CLARIFY"
        assert mixed_outcome.execution_plan.clarify.slot.value == "domain"
        assert mixed_outcome.llm_replan_invoked is False
        print("orchestrator_smoke_ok")

        rich_bjj_markdown = """---\n"""
        rich_bjj_markdown += "type: BJJ\n"
        rich_bjj_markdown += "title: Rich Training Log\n"
        rich_bjj_markdown += "---\n\n"
        for day, action, response, adjustment, note in (
            ("2026-03-04", "tripod post", "pulled me back to turtle", "inside elbow recovery", "head position was late"),
            ("2026-03-05", "elbow-knee frame", "chased back exposure", "hip angle reset", "needed earlier head position"),
            ("2026-03-06", "hand fight first", "stayed heavy on top", "return to base", "success improved"),
        ):
            rich_bjj_markdown += f"## {day}\n"
            rich_bjj_markdown += "- position: turtle\n"
            rich_bjj_markdown += "- orientation: 下位\n"
            rich_bjj_markdown += "- distance: 近距离\n"
            rich_bjj_markdown += "- goal: escape\n"
            rich_bjj_markdown += f"- your_action: {action}\n"
            rich_bjj_markdown += f"- opponent_response: {response}\n"
            rich_bjj_markdown += "- opponent_control: 袖子\n"
            rich_bjj_markdown += f"- your_adjustment: {adjustment}\n"
            rich_bjj_markdown += f"- notes: {note}\n\n"

        repo2 = SQLiteDocumentRepository(SQLiteStore(root / "sqlite_agents" / "app.db"))
        file_store2 = LocalFileStore(root / "filestore_agents")
        vector_store2 = ChromaVectorStoreAdapter(root / "chroma_agents", collection_name="chunks")
        ingest2 = IngestionService(repo2, file_store2, vector_store=vector_store2)
        ingest2.ingest_text(rich_bjj_markdown, source_path_hint="bjj_rich.md")
        ingest2.ingest_text(notes_markdown, source_path_hint="notes_again.md")

        retrieval2 = RetrievalService(repo2, vector_store=vector_store2)
        bjj_outcome = retrieval2.retrieve("turtle 下位 逃脱", mode="full")
        coach = BJJCoachService()
        coach_result = coach.run(
            BJJCoachInput(
                query_original="turtle 下位怎么逃脱？",
                query_clean="turtle 下位 怎么 逃脱",
                confirmed_slots={
                    "position": "turtle",
                    "orientation": "下位",
                    "goal": "escape",
                    "opponent_control": "袖子",
                },
                profile_summary=ProfileSummary(profile_version_id="profile_1"),
            ),
            evidence_pack=EvidencePack(items=bjj_outcome.items),
        )
        assert coach_result.final_answer is not None
        assert coach_result.validator_report.validator_pass is True

        notes_outcome = retrieval2.retrieve("迷宫和镜子", mode="full")
        literary = LiteraryService()
        literary_result = literary.run("迷宫和镜子", EvidencePack(items=notes_outcome.items))
        assert literary_result.anchors
        assert "迷宫和镜子" in literary_result.text
        print("agents_smoke_ok")

        job_repo = SQLiteJobRepository(repo2.store)
        jobs = JobService(repo2, job_repo, vector_store=vector_store2)
        first_chunk = repo2.list_chunks()[0]
        repo2.update_chunk_safe_summary(first_chunk.chunk_id, "")
        queued_safe_summary = jobs.enqueue(
            "safe_summary_build",
            {
                "chunk_id": first_chunk.chunk_id,
                "doc_version_id": first_chunk.doc_version_id,
                "summary_prompt_version": "safe_summary.v1",
            },
        )
        queued_reindex = jobs.enqueue("reindex_doc_version", {"doc_version_id": first_chunk.doc_version_id})
        queued_reembed = jobs.enqueue("reembed_doc_version", {"doc_version_id": first_chunk.doc_version_id})
        assert job_repo.list_jobs(status=None, limit=None)
        safe_summary_result = jobs.run_job(queued_safe_summary.job_id)
        reindex_result = jobs.run_job(queued_reindex.job_id)
        reembed_result = jobs.run_job(queued_reembed.job_id)
        assert safe_summary_result.job.status.value == "succeeded"
        assert repo2.get_chunk(first_chunk.chunk_id).safe_summary
        assert reindex_result.job.status.value == "succeeded"
        assert reembed_result.job.status.value == "succeeded"
        assert any(note.startswith("reembedded_chunks=") for note in reembed_result.notes)
        print("jobs_smoke_ok")

        api_root = root / "api_app"
        api_app = create_app(api_root)
        original_orchestrator_service = api_app.state.pda.orchestrator_service
        class _APIReplanStub:
            def route(self, user_message, session_state=None, entrypoint=None):
                return {
                    "session_state": session_state or ConversationState(),
                    "execution_plan": ExecutionPlan(
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
                    "plan_check": PlanCheck(
                        domain=DomainType.MIXED,
                        task_hint=TaskType.MIXED,
                        need_replan=True,
                        need_clarify=False,
                        confidence_hint=0.4,
                        reason_codes=["DOMAIN_UNCLEAR"],
                    ),
                    "probe_stats": None,
                    "llm_replan_invoked": True,
                    "llm_replan_result": "success",
                }
        from server.app.orchestrator import OrchestratorOutcome

        class _APIReplanOutcomeStub:
            def route(self, user_message, session_state=None, entrypoint=None):
                return OrchestratorOutcome(**_APIReplanStub().route(user_message, session_state, entrypoint))

        api_routes = {}
        for route in api_app.routes:
            if not hasattr(route, "path") or not hasattr(route, "endpoint"):
                continue
            path = getattr(route, "path", None)
            if path and path not in api_routes:
                api_routes[path] = route.endpoint
            for method in sorted(getattr(route, "methods", set()) or set()):
                if path:
                    api_routes[f"{method} {path}"] = route.endpoint
        health_payload = _to_dict(api_routes["/api/health"]())
        assert health_payload["status"] == "ok"
        landing = api_routes["/"]()
        landing_body = landing.body.decode("utf-8")
        assert "Backend API is running" in landing_body
        assert "npm --prefix web run dev" in landing_body
        assert "web/package.json" in landing_body

        api_ingest = _to_dict(
            api_routes["/api/ingest/text"](
                IngestTextRequest(markdown_text=notes_markdown, source_path_hint="api_notes.md")
            )
        )
        assert api_ingest["doc_id"]
        assert api_ingest["chunk_ids"]
        assert api_ingest["jobs"]

        imports_root = api_root / "imports"
        nested_imports = imports_root / "nested"
        nested_imports.mkdir(parents=True, exist_ok=True)
        file_ingest_path = imports_root / "api_notes.md"
        dir_ingest_path = nested_imports / "api_bjj.markdown"
        file_ingest_path.write_text(notes_markdown, encoding="utf-8")
        dir_ingest_path.write_text(bjj_markdown, encoding="utf-8")

        api_ingest_file = _to_dict(api_routes["/api/ingest/file"](IngestFileRequest(path="imports/api_notes.md")))
        assert api_ingest_file["source_path"] == str(file_ingest_path.resolve())
        assert api_ingest_file["chunk_ids"]

        api_ingest_dir = _to_dict(api_routes["/api/ingest/dir"](IngestDirRequest(path="imports")))
        assert api_ingest_dir["imported_count"] == 2
        assert [item["source_path"] for item in api_ingest_dir["results"]] == [
            str(file_ingest_path.resolve()),
            str(dir_ingest_path.resolve()),
        ]

        api_retrieve = _to_dict(api_routes["/api/retrieve"](RetrieveRequest(query_text="maze mirror", mode="full")))
        assert api_retrieve["evidence_pack"]["items"]
        assert api_retrieve["retrieval_log"]["dense_count"] >= 1

        api_app.state.pda.orchestrator_service = _APIReplanOutcomeStub()
        api_replan_chat = _to_dict(api_routes["/api/chat/turn"](ChatTurnRequest(user_message="最近写作状态很差，也想复盘训练节奏。")))
        api_replan_trace = _to_dict(api_routes["/api/traces/{trace_id}"](api_replan_chat["trace_id"]))
        assert api_replan_trace["request_log"]["plan_check"] is not None
        assert any(event["name"] == "orchestrator.replan_llm" for event in api_replan_trace["events"])
        api_app.state.pda.orchestrator_service = original_orchestrator_service

        api_chat = _to_dict(api_routes["/api/chat/turn"](ChatTurnRequest(user_message="迷宫和镜子有什么联系？")))
        assert api_chat["response_type"] == "final_answer"
        assert api_chat["conversation_id"]
        stream_response = api_routes["/api/chat/stream"](
            ChatTurnRequest(user_message="我在下位 turtle 被对手抓袖子，想 escape，应该怎么做？")
        )
        assert stream_response.media_type == "text/event-stream"
        stream_body = asyncio.run(_collect_streaming_body(stream_response))
        assert '"event_type": "started"' in stream_body or '"event_type":"started"' in stream_body
        assert '"event_type": "completed"' in stream_body or '"event_type":"completed"' in stream_body

        api_jobs = _to_dict(api_routes["/api/jobs"]())
        assert api_jobs["jobs"]
        api_run_job = _to_dict(api_routes["/api/jobs/run-next"](RunJobsRequest(job_types=["safe_summary_build"])))
        assert api_run_job["result"]["job"]["status"] == "succeeded"

        api_traces = _to_dict(api_routes["/api/traces"]())
        assert api_traces["traces"]
        api_trace = _to_dict(api_routes["/api/traces/{trace_id}"](api_chat["trace_id"]))
        assert api_trace["trace_id"] == api_chat["trace_id"]
        assert api_trace["generation_log"]["prompt_hash"]
        assert api_trace["generation_log"]["input_snapshot"]["query_original"]
        assert api_trace["generation_log"]["prompt_snapshot"]["query_original_preview"] is None
        api_replay = _to_dict(api_routes["/api/replay/{trace_id}"](api_chat["trace_id"], ReplayRequest()))
        assert api_replay["trace_id"]
        api_eval = _to_dict(api_routes["/api/eval/run"](EvalRunAPIRequest(eval_set_id="api_smoke_eval", trace_ids=[api_chat["trace_id"]])))
        assert api_eval["eval_run_id"]
        api_eval_results = _to_dict(api_routes["/api/eval/results"]())
        assert api_eval_results["runs"]
        api_rubric = _to_dict(
            api_routes["/api/eval/rubric"](
                EvalRubricSubmitRequest(
                    eval_run_id=api_eval["eval_run_id"],
                    trace_id=api_chat["trace_id"],
                    reviewer="smoke",
                    scores=[
                        {"dimension": "ab_distinctness", "score": 3},
                        {"dimension": "drill_executability", "score": 2},
                    ],
                    notes="smoke rubric",
                )
            )
        )
        assert api_rubric["run"]["manual_rubric"]["status"] == "succeeded"
        api_rubric_entries = _to_dict(api_routes["/api/eval/rubric/{eval_run_id}"](api_eval["eval_run_id"]))
        assert api_rubric_entries["entries"]
        print("evaluation_manual_rubric_smoke_ok")
        api_sft = _to_dict(api_routes["/api/sft/export"](SFTExportRequest(trace_filter={})))
        assert api_sft["manifest"]["sample_count"] >= 1
        api_sft_dir = Path(api_sft["export_path"])
        api_exported = [json.loads(line) for line in (api_sft_dir / "dataset_export.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        api_rows = []
        for sample in api_exported:
            if not isinstance(sample.get("baseline_output"), dict) or not sample["baseline_output"].get("observations"):
                continue
            target_output = json.loads(json.dumps(sample["baseline_output"]))
            target_output["observations"][0]["text"] = "api smoke policy tuned observation"
            api_rows.append(
                {
                    "trace_id": sample["trace_id"],
                    "input": {
                        "task": sample["profile_summary"].get("task"),
                        "query_original": sample["profile_summary"].get("query_original", ""),
                        "query_clean": sample["profile_summary"].get("query_clean", ""),
                        "confirmed_slots": sample["confirmed_slots"],
                        "coach_clarify_round": sample["coach_clarify_round"],
                        "coach_pending_slot": sample["profile_summary"].get("coach_pending_slot"),
                        "profile_version_id": sample["profile_summary"].get("profile_version_id"),
                        "profile_summary_snapshot": {
                            "profile_version_id": sample["profile_summary"].get("profile_version_id"),
                            "ruleset_default": sample["profile_summary"].get("ruleset_default", "Gi"),
                            "injuries": sample["profile_summary"].get("injuries", []),
                            "forbidden_actions": sample["profile_summary"].get("forbidden_actions", []),
                            "preferences": sample["profile_summary"].get("preferences", []),
                        },
                        "frozen_evidence_pack": {"items": sample["evidence_pack_selected"]},
                        "prompt_version": sample.get("prompt_version"),
                        "prompt_hash": sample.get("prompt_hash"),
                        "baseline_output": sample["baseline_output"],
                    },
                    "target_output": target_output,
                }
            )
        if api_rows:
            api_train_path = api_sft_dir / "train.jsonl"
            api_train_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in api_rows) + "\n", encoding="utf-8")
            api_sft_train = _to_dict(
                api_routes["/api/sft/train"](
                    SFTTrainAPIRequest(
                        train_path=str(api_train_path),
                        output_path=str(api_root / "policy_ckpt"),
                        base_model="mock-bjj-base",
                        dry_run=False,
                        activate=True,
                    )
                )
            )
            assert api_sft_train["checkpoint"]["policy_model_ref"].startswith("policy://")
            api_policy_replay = _to_dict(api_routes["/api/replay/{trace_id}"](api_chat["trace_id"], ReplayRequest(model_variant="policy")))
            assert api_policy_replay["trace_id"]
        api_profile = _to_dict(api_routes["GET /api/profile"]())
        assert api_profile["profile_version_id"]
        api_profile_updated = _to_dict(api_routes["PUT /api/profile"](ProfilePatchRequest(ruleset_default="NoGi")))
        assert api_profile_updated["ruleset_default"] == "NoGi"
        api_profile_history = _to_dict(api_routes["/api/profile/history"]())
        assert len(api_profile_history["profiles"]) >= 2
        from server.app.api.state import create_app_state
        reloaded_state = create_app_state(api_root)
        assert reloaded_state.current_profile.profile_version_id == api_profile_updated["profile_version_id"]
        assert reloaded_state.current_profile.ruleset_default == "NoGi"
        print("api_smoke_ok")

        trace_store2 = JSONTraceStore(root / "traces_observability")
        recorder = TraceRecorder(runtime_config_snapshot=orchestrator.runtime_config, conversation_id="conv_1")
        with recorder.span("chat.turn_total", entrypoint="chat"):
            recorder.set_request_log(
                RequestLog(
                    entrypoint="chat",
                    domain=clarify_outcome.execution_plan.domain.value,
                    task=clarify_outcome.execution_plan.task.value,
                    confirmed_slots=follow_up.session_state.slots,
                    execution_plan=follow_up.execution_plan,
                )
            )
            recorder.add_stage_transition("start", "probe", need_probe=True)
            recorder.set_retrieval_log(retrieval_outcome.retrieval_log)
            recorder.set_evidence_log(EvidencePack(items=bjj_outcome.items))
            recorder.set_generation_log(
                GenerationLog(
                    provider=orchestrator.runtime_config.model_routing.provider,
                    model=orchestrator.runtime_config.model_routing.base_model,
                    prompt_version=orchestrator.runtime_config.prompt_versions.bjj_coach,
                    output=_to_dict(coach_result.final_answer),
                    validator_report=coach_result.validator_report,
                )
            )
            recorder.add_event("evidence.pack_selected", evidence_ids=[item.evidence_id for item in bjj_outcome.items])
        trace_path = recorder.persist(trace_store2)
        assert Path(trace_path).exists()
        assert recorder.trace_id in trace_store2.list_trace_ids()
        loaded_trace = trace_store2.read_trace(recorder.trace_id)
        assert loaded_trace.trace_id == recorder.trace_id
        assert loaded_trace.events
        assert loaded_trace.spans
        print("observability_smoke_ok")

        eval_repo = SQLiteGoldenCaseRepository(repo2.store)
        golden_dir = root / "datasets" / "golden"
        golden_dir.mkdir(parents=True, exist_ok=True)
        (golden_dir / "smoke_eval.jsonl").write_text(
            (
                '{"case_id":"smoke_case","query":"turtle escape","domain":"BJJ","trace_id":"'
                + recorder.trace_id
                + '","expected_behavior":{"required_mode":"FULL","min_citation_count":1},"expected_chunk_ids":["'
                + bjj_outcome.items[0].evidence_id
                + '"]}\n'
            ),
            encoding="utf-8",
        )
        evaluation = EvaluationService(trace_store=trace_store2, golden_case_repository=eval_repo, repo_root=root)
        eval_result = evaluation.run(
            EvalRunRequest(eval_set_id="smoke_eval", model_variant=ModelVariant.BASE),
        )
        assert eval_result.metrics
        assert eval_result.golden_case_count == 1
        assert eval_result.ragas.status.value == "skipped"
        assert eval_result.judge.status.value == "skipped"
        assert evaluation.list_results()
        print("evaluation_smoke_ok")

        sft = SFTService(
            trace_store=trace_store2,
            policy_root=root / "data" / "policies",
            training_backend=_SmokeTrainingBackend(),
            inference_backend=_SmokeInferenceBackend(),
        )
        dataset_dir = root / "datasets" / "sft" / "v1" / "smoke"
        manifest, samples = sft.export_dataset(
            request=SFTExportRequest(trace_filter={}, format="jsonl"),
            output_dir=dataset_dir,
            trace_ids=[recorder.trace_id],
        )
        assert manifest.sample_count == 1
        assert samples
        assert (dataset_dir / "dataset_export.jsonl").exists()
        assert (dataset_dir / "manifest.json").exists()
        samples[0].target_output = json.loads(json.dumps(samples[0].baseline_output))
        samples[0].target_output["observations"][0]["text"] = "smoke policy tuned observation"
        train_path = sft.build_train_rows(samples, dataset_dir / "train.jsonl", prefer_target_output=True)
        assert train_path.exists()
        train_request = sft.build_policy_train_request(train_path, root / "data" / "policy_checkpoints" / "smoke_run", dry_run=False)
        checkpoint = sft.train_policy(train_request, dataset_manifest=manifest)
        assert checkpoint.policy_model_ref.startswith("policy://")
        assert checkpoint.training_backend == "hf_lora_qlora_v1"
        assert sft.get_active_policy_ref() == checkpoint.policy_model_ref
        artifact_payload = json.loads((root / "data" / "policy_checkpoints" / "smoke_run" / "policy_artifact.json").read_text(encoding="utf-8"))
        assert artifact_payload["schema_version"] == "hf_lora_qlora_v1"
        assert artifact_payload["adapter_path"].endswith("/adapter")
        assert artifact_payload["tokenizer_path"].endswith("/tokenizer")
        replayed_trace, replayed_answer = sft.replay_trace(
            source_trace=loaded_trace,
            variant=ModelVariant.POLICY,
            runtime_config=orchestrator.runtime_config,
            current_profile=ProfileSummary(profile_version_id="profile_default"),
            bjj_coach_service=coach,
            literary_service=literary,
        )
        assert replayed_trace.generation_log.model == checkpoint.policy_model_ref
        assert replayed_answer.observations[0].text == "smoke policy tuned observation"
        policy_eval = EvaluationService(
            trace_store=trace_store2,
            golden_case_repository=eval_repo,
            repo_root=root,
            replay_runner=lambda traces, variant, use_frozen_evidence: sft.replay_eval_traces(
                traces=traces,
                variant=variant,
                runtime_config=orchestrator.runtime_config,
                current_profile=ProfileSummary(profile_version_id="profile_default"),
                bjj_coach_service=coach,
                literary_service=literary,
                use_frozen_evidence=use_frozen_evidence,
            ),
        )
        policy_eval_result = policy_eval.run(
            EvalRunRequest(eval_set_id="smoke_eval", model_variant=ModelVariant.POLICY),
            trace_ids=[recorder.trace_id],
        )
        assert policy_eval_result.source_trace_ids
        assert trace_store2.read_trace(policy_eval_result.source_trace_ids[0]).generation_log.model == checkpoint.policy_model_ref
        print("sft_smoke_ok")

    print("all_smoke_tests_ok")


def _utcnow():
    from datetime import datetime

    return datetime.utcnow()


class _SmokeTrainingBackend:
    backend_name = "hf_lora_qlora_v1"

    def run(self, request):
        from server.app.sft.training_backend import PolicyTrainingArtifact

        output_dir = Path(request.output_path)
        adapter_dir = output_dir / "adapter"
        tokenizer_dir = output_dir / "tokenizer"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        tokenizer_dir.mkdir(parents=True, exist_ok=True)
        (adapter_dir / "adapter_config.json").write_text('{"smoke":true}\n', encoding="utf-8")
        (tokenizer_dir / "tokenizer_config.json").write_text('{"smoke":true}\n', encoding="utf-8")
        summary_path = output_dir / "training_summary.json"
        summary_path.write_text('{"backend":"smoke_stub"}\n', encoding="utf-8")
        return PolicyTrainingArtifact(
            backend_name=self.backend_name,
            schema_version=self.backend_name,
            adapter_path=str(adapter_dir),
            tokenizer_path=str(tokenizer_dir),
            training_summary_path=str(summary_path),
            metadata={"runner": "smoke_stub"},
        )

    def status(self):
        return {
            "backend_name": self.backend_name,
            "script_path": "/tmp/smoke-train-policy-lora.py",
            "script_exists": True,
            "configured": True,
            "missing_dependencies": [],
            "qlora_supported": True,
            "required_modules": {},
            "optional_modules": {"bitsandbytes": True},
        }


class _SmokeInferenceBackend:
    backend_name = "hf_lora_qlora_inference_v1"

    def run_signature(self, input_payload):
        import hashlib

        return hashlib.sha1(json.dumps(input_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def generate(self, artifact, input_payload, max_new_tokens=1024):
        from server.app.sft.inference_backend import PolicyInferenceResult

        signature = self.run_signature(input_payload)
        learned = artifact["examples"][signature]
        return PolicyInferenceResult(
            output=learned["target_output"],
            token_usage={"prompt_tokens": 11, "completion_tokens": 22},
            metadata={"runner": "smoke_inference_stub", "max_new_tokens": max_new_tokens},
        )

    def status(self):
        return {
            "backend_name": self.backend_name,
            "configured": True,
            "missing_dependencies": [],
            "required_modules": {},
        }


def _date(year: int, month: int, day: int):
    from datetime import date

    return date(year, month, day)


def _to_dict(model):
    if model is None:
        return {}
    if hasattr(model, "model_dump"):
        return model.model_dump(by_alias=True)
    if hasattr(model, "dict"):
        return model.dict(by_alias=True)
    return dict(model)


class _SmokeRetrievalOutcome:
    def __init__(self, probe_stats):
        self.probe_stats = probe_stats


class _SmokeRetrievalService:
    def __init__(self, probe_stats):
        self._probe_stats = probe_stats

    def retrieve(self, query_text, filters_hint=None, mode="probe", top_k=None):
        return _SmokeRetrievalOutcome(self._probe_stats)


async def _collect_streaming_body(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(chunk)
    return "".join(chunks)


if __name__ == "__main__":
    main()
