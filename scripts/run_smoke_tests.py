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
        EvidencePack,
        GenerationLog,
        LineRange,
        Orientation,
        ProfileSummary,
        RequestLog,
        RetrievalLog,
        RuntimeConfigSnapshot,
        SourceLocator,
        TraceRecord,
        active_model_profile_name,
        export_contract_schemas,
    )
    from server.app.agents import BJJCoachService, LiteraryService
    from server.app.agents.bjj_coach.types import BJJCoachInput
    from server.app.ingestion import IngestionService
    from server.app.orchestrator import ConversationState, OrchestratorService
    from server.app.retrieval import RetrievalService
    from server.app.storage import JSONTraceStore, LocalFileStore, SQLiteDocumentRepository, SQLiteStore

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
        ingest2 = IngestionService(repo2, file_store2)
        ingest2.ingest_text(rich_bjj_markdown, source_path_hint="bjj_rich.md")
        ingest2.ingest_text(notes_markdown, source_path_hint="notes_again.md")

        retrieval2 = RetrievalService(repo2)
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

    print("all_smoke_tests_ok")


def _utcnow():
    from datetime import datetime

    return datetime.utcnow()


def _date(year: int, month: int, day: int):
    from datetime import date

    return date(year, month, day)


if __name__ == "__main__":
    main()
