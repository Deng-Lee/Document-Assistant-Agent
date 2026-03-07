from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path


def activate_test_profile(profile_name: str = "fake") -> None:
    os.environ["PDA_MODEL_PROFILE"] = profile_name
    from server.app.core import set_active_model_profile

    set_active_model_profile(profile_name)


def endpoint_map(app) -> dict[str, object]:
    return {getattr(route, "path", None): route.endpoint for route in app.routes if hasattr(route, "path")}


def sample_bjj_markdown() -> str:
    return """---\n""" + "\n".join(
        [
            "type: BJJ",
            "title: Training Log",
            "---",
            "",
            "## 2026-03-04",
            "- position: turtle",
            "- orientation: 下位",
            "- distance: 近距离",
            "- goal: escape",
            "- your_action: tripod post",
            "- opponent_response: pulled me back to turtle",
            "- opponent_control: 袖子",
            "- your_adjustment: inside elbow recovery",
            "- notes: head position was late",
            "",
            "## 2026-03-05",
            "- position: turtle",
            "- orientation: 下位",
            "- distance: 近距离",
            "- goal: escape",
            "- your_action: elbow-knee frame",
            "- opponent_response: chased back exposure",
            "- opponent_control: 袖子",
            "- your_adjustment: hip angle reset",
            "- notes: needed earlier head position",
            "",
            "## 2026-03-06",
            "- position: turtle",
            "- orientation: 下位",
            "- distance: 近距离",
            "- goal: escape",
            "- your_action: hand fight first",
            "- opponent_response: stayed heavy on top",
            "- opponent_control: 袖子",
            "- your_adjustment: return to base",
            "- notes: success improved",
        ]
    ) + "\n"


def sample_notes_markdown() -> str:
    return """---\n""" + "\n".join(
        [
            "type: notes",
            "title: Reading Notes",
            "---",
            "",
            "# Borges",
            "",
            "Memory is not a warehouse.",
            "It is a staging ground.",
            "",
            "## Fragments",
            "",
            "A library can be a maze and a mirror.",
        ]
    ) + "\n"


def create_test_app(root_dir: str | Path):
    activate_test_profile("fake")
    from server.app.api import create_app

    return create_app(root_dir)


def build_ingested_stack(root: str | Path, include_bjj: bool = True, include_notes: bool = True):
    activate_test_profile("fake")
    from server.app.ingestion import IngestionService
    from server.app.storage import LocalFileStore, SQLiteDocumentRepository, SQLiteStore

    root_path = Path(root)
    repo = SQLiteDocumentRepository(SQLiteStore(root_path / "sqlite" / "app.db"))
    file_store = LocalFileStore(root_path / "filestore")
    ingestion = IngestionService(repo, file_store)
    results = {}
    if include_bjj:
        results["bjj"] = ingestion.ingest_text(sample_bjj_markdown(), source_path_hint="bjj.md")
    if include_notes:
        results["notes"] = ingestion.ingest_text(sample_notes_markdown(), source_path_hint="notes.md")
    return repo, file_store, ingestion, results


def make_trace_record(
    trace_id: str = "trace_1",
    mode: str = "FULL",
    gate_label: str = "HIGH_EVIDENCE",
    evidence_ids: list[str] | None = None,
    validator_pass: bool = True,
    domain: str = "BJJ",
    task: str = "COACH_BJJ",
    query_text: str = "turtle escape",
    latency_ms: int | None = None,
    cost_estimate: float | None = None,
):
    activate_test_profile("fake")
    from server.app.core import (
        BJJAssumptions,
        BJJBranchPlan,
        BJJDrill,
        BJJFullAnswer,
        BJJMistake,
        BJJNextStep,
        BJJObservation,
        BJJPlanBlock,
        BJJPlanBranch,
        BJJPlanCollection,
        BJJReasoningStatus,
        BJJValidatorReport,
        ChunkMetadataDigest,
        Distance,
        EvidencePack,
        EvidencePackItem,
        GenerationLog,
        LineRange,
        NextStepType,
        Orientation,
        RankSignals,
        RequestLog,
        RetrievalFilters,
        RetrievalLog,
        RetrievalPlan,
        RuntimeConfigSnapshot,
        SourceLocator,
        TraceRecord,
    )

    resolved_evidence_ids = evidence_ids or ["chunk_1", "chunk_2", "chunk_3"]
    evidence_pack = EvidencePack(
        items=[
            EvidencePackItem(
                evidence_id=evidence_id,
                doc_id=f"doc_{index}",
                doc_version_id="dv_1",
                locator=SourceLocator(
                    doc_version_id="dv_1",
                    source_path="bjj.md",
                    line_range=LineRange(start=index, end=index + 1),
                    char_range={"start": index * 10, "end": index * 10 + 8},
                ),
                safe_summary=f"summary {index}",
                metadata_digest=ChunkMetadataDigest(
                    date=date(2026, 3, min(index, 28)),
                    position="turtle",
                    orientation=Orientation.BOTTOM,
                    distance=Distance.CLOSE,
                    goal="escape",
                ),
                rank_signals=RankSignals(structured_filter_applied=True, rrf_rank=index),
            )
            for index, evidence_id in enumerate(resolved_evidence_ids, start=1)
        ]
    )
    output = BJJFullAnswer(
        mode=mode,
        assumptions=BJJAssumptions(
            confirmed_slots={"position": "turtle", "orientation": "下位", "goal": "escape"},
            opponent_control="袖子",
        ),
        reasoning_status=BJJReasoningStatus(
            gate_label=gate_label,
            reason_codes=["TEST_TRACE"],
            coach_clarify_round=0,
        ),
        caveats=["keep your head safe"],
        observations=[BJJObservation(text="control the first post", evidence_ids=resolved_evidence_ids[:1])],
        plans=BJJPlanCollection(
            A_baseline=BJJPlanBlock(
                title="baseline",
                preconditions=["opponent stays heavy"],
                steps=["post and square"],
                evidence_ids=resolved_evidence_ids[:1],
            ),
            B_offense=BJJPlanBlock(
                title="offense",
                preconditions=["head clears first"],
                steps=["recover elbow line"],
                evidence_ids=resolved_evidence_ids[1:2],
            ),
            C_branch=BJJBranchPlan(
                branches=[
                    BJJPlanBranch(**{"if": "opponent drags wrist", "then": ["switch post"], "evidence_ids": resolved_evidence_ids[:1]}),
                    BJJPlanBranch(**{"if": "opponent circles behind", "then": ["build base"], "evidence_ids": resolved_evidence_ids[1:2]}),
                ]
            ),
        ),
        mistakes=[BJJMistake(text="late head position", fix="hide your head", evidence_ids=resolved_evidence_ids[:1])],
        drills=[
            BJJDrill(
                name="turtle stand-up reps",
                start={"position": "turtle", "orientation": "下位", "distance": "近距离"},
                opponent_control="袖子",
                goal="escape",
                dosage="3x2min",
                constraints=["no diving forward"],
                success_criteria=["clear one shoulder line"],
                evidence_ids=resolved_evidence_ids[:1],
            )
        ],
        next_step=BJJNextStep(type=NextStepType.NONE, message="review the sequence"),
        citations=resolved_evidence_ids[:2],
    )
    generation_log = GenerationLog(
        provider="mock",
        model="mock-bjj-base",
        prompt_version="bjj.v1",
        latency_ms=latency_ms,
        cost_estimate=cost_estimate,
        output=_model_to_dict(output),
        validator_report=BJJValidatorReport(validator_pass=validator_pass),
    )
    return TraceRecord(
        trace_id=trace_id,
        conversation_id="conv_test",
        runtime_config_snapshot=RuntimeConfigSnapshot(),
        request_log=RequestLog(
            entrypoint="chat",
            domain=domain,
            task=task,
            profile_version_id="profile_test",
            confirmed_slots={"position": "turtle", "orientation": "下位", "goal": "escape"},
        ),
        retrieval_log=RetrievalLog(
            retrieval_plan=RetrievalPlan(
                doc_type="BJJ",
                filters=RetrievalFilters(),
                query_original=query_text,
                query_text=query_text,
                top_k=12,
                per_doc_limit=3,
                token_budget=4000,
            )
        ),
        evidence_log=evidence_pack,
        generation_log=generation_log,
        spans=[],
        events=[],
    )


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump(by_alias=True)
    return model.dict(by_alias=True)
