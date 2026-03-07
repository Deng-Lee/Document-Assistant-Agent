#!/usr/bin/env python3
from __future__ import annotations

import argparse
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

    from server.app.core import (
        CharRange,
        ChunkMetadataDigest,
        ChunkRecord,
        ChunkType,
        Distance,
        DocumentRecord,
        DocumentType,
        DocVersionRecord,
        EntryPoint,
        EvalRunRequest,
        EvidencePack,
        GenerationLog,
        LineRange,
        ModelVariant,
        Orientation,
        ProfileSummary,
        RequestLog,
        RetrievalLog,
        RuntimeConfigSnapshot,
        SFTExportRequest,
        SourceLocator,
        TraceRecord,
        active_model_profile_name,
        export_contract_schemas,
    )
    from server.app.agents import BJJCoachService, LiteraryService
    from server.app.agents.bjj_coach.types import BJJCoachInput
    from server.app.api import create_app
    from server.app.api.models import (
        ChatTurnRequest,
        EvalRunAPIRequest,
        IngestDirRequest,
        IngestFileRequest,
        IngestTextRequest,
        ReplayRequest,
        RetrieveRequest,
        RunJobsRequest,
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
        print("retrieval_smoke_ok")

        orchestrator = OrchestratorService(retrieval)
        write_outcome = orchestrator.route("帮我记录一条训练", entrypoint=EntryPoint.RECORD)
        assert write_outcome.execution_plan.next_action.value == "WRITE_FLOW"

        clarify_outcome = orchestrator.route("龟防怎么破解？我总是被人拉回去。")
        assert clarify_outcome.execution_plan.next_action.value == "CLARIFY"
        assert clarify_outcome.session_state.pending_slot is not None

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
        ui_shell = api_routes["/"]()
        assert Path(ui_shell.path).name == "index.html"
        assert Path(ui_shell.path).exists()
        assert (Path(ui_shell.path).with_name("app.js")).exists()
        assert (Path(ui_shell.path).with_name("styles.css")).exists()
        assert (repo_root / "web" / "lib" / "api.js").exists()
        assert (repo_root / "web" / "components" / "renderers.js").exists()

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

        api_chat = _to_dict(api_routes["/api/chat/turn"](ChatTurnRequest(user_message="迷宫和镜子有什么联系？")))
        assert api_chat["response_type"] == "final_answer"
        assert api_chat["conversation_id"]

        api_jobs = _to_dict(api_routes["/api/jobs"]())
        assert api_jobs["jobs"]
        api_run_job = _to_dict(api_routes["/api/jobs/run-next"](RunJobsRequest(job_types=["safe_summary_build"])))
        assert api_run_job["result"]["job"]["status"] == "succeeded"

        api_traces = _to_dict(api_routes["/api/traces"]())
        assert api_traces["traces"]
        api_trace = _to_dict(api_routes["/api/traces/{trace_id}"](api_chat["trace_id"]))
        assert api_trace["trace_id"] == api_chat["trace_id"]
        api_replay = _to_dict(api_routes["/api/replay/{trace_id}"](api_chat["trace_id"], ReplayRequest()))
        assert api_replay["trace_id"]
        api_eval = _to_dict(api_routes["/api/eval/run"](EvalRunAPIRequest(eval_set_id="api_smoke_eval", trace_ids=[api_chat["trace_id"]])))
        assert api_eval["eval_run_id"]
        api_eval_results = _to_dict(api_routes["/api/eval/results"]())
        assert api_eval_results["runs"]
        api_sft = _to_dict(api_routes["/api/sft/export"](SFTExportRequest(trace_filter={})))
        assert api_sft["manifest"]["sample_count"] >= 1
        api_profile = _to_dict(api_routes["GET /api/profile"]())
        assert api_profile["profile_version_id"]
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
        evaluation = EvaluationService(trace_store=trace_store2, golden_case_repository=eval_repo)
        eval_result = evaluation.run(
            EvalRunRequest(eval_set_id="smoke_eval", model_variant=ModelVariant.BASE),
            trace_ids=[recorder.trace_id],
        )
        assert eval_result.metrics
        assert evaluation.list_results()
        print("evaluation_smoke_ok")

        sft = SFTService(trace_store=trace_store2)
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

        train_path = sft.build_train_rows(samples, dataset_dir / "train.jsonl")
        assert train_path.exists()
        checkpoint = sft.register_policy_checkpoint(
            output_dir=root / "data" / "policy_checkpoints" / "smoke_run",
            base_model=orchestrator.runtime_config.model_routing.base_model,
            dataset_manifest=manifest,
        )
        train_request = sft.build_policy_train_request(train_path, root / "data" / "policy_checkpoints" / "smoke_run", dry_run=True)
        assert checkpoint.policy_model_ref.startswith("policy://")
        assert train_request.dry_run is True
        assert sft.resolve_model_for_variant(orchestrator.runtime_config, ModelVariant.BASE) == orchestrator.runtime_config.model_routing.base_model
        assert sft.resolve_model_for_variant(orchestrator.runtime_config, ModelVariant.POLICY, checkpoint) == checkpoint.policy_model_ref
        print("sft_smoke_ok")

    print("all_smoke_tests_ok")


def _utcnow():
    from datetime import datetime

    return datetime.utcnow()


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


if __name__ == "__main__":
    main()
