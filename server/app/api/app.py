from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.app.agents.bjj_coach.types import BJJCoachInput
from server.app.core import (
    ChatClarifyTurnResponse,
    ChatFinalTurnResponse,
    ClarifyRequest,
    ClarifySlot,
    ClarifyWho,
    EntryPoint,
    EvalRunRequest,
    GenerationLog,
    LiteraryFinalAnswer,
    ModelVariant,
    ProfileConstraint,
    ProfileSummary,
    RequestLog,
    RetrievalFilters,
    RetrievalLog,
    SFTExportRequest,
    TraceEvent,
    TraceRecord,
)
from server.app.observability import (
    TraceRecorder,
    build_generation_input_snapshot as build_trace_generation_input_snapshot,
    build_prompt_snapshot as build_trace_prompt_snapshot,
)

from .models import (
    BJJRecordRequest,
    ChatTurnRequest,
    EvalRunAPIRequest,
    IngestDirRequest,
    IngestFileRequest,
    IngestTextRequest,
    NotesRecordRequest,
    ProfilePatchRequest,
    ReplayRequest,
    RetrieveRequest,
    RunJobsRequest,
)
from .responses import (
    ChatConversationResponse,
    EvalResultsResponse,
    EvalRunLaunchResponse,
    HealthResponse,
    IngestDirectoryResponse,
    IngestFileResponse,
    IngestTextResponse,
    JobsListResponse,
    ProfileResponse,
    RecordBJJResponse,
    RecordNotesResponse,
    ReplayTraceResponse,
    RetrieveResponse,
    RunJobResponse,
    SFTExportResponse,
    TraceSummaryItem,
    TracesListResponse,
)
from .state import AppState, create_app_state


def create_app(root_dir: str | Path | None = None) -> FastAPI:
    resolved_root = Path(root_dir or Path.cwd()).resolve()
    app = FastAPI(title="Personal Document Assistant API", version="0.1.0")
    app.state.pda = create_app_state(resolved_root)
    ui_root = _repo_root() / "web"
    app.mount("/ui", StaticFiles(directory=ui_root), name="ui")

    @app.get("/", include_in_schema=False)
    def web_shell() -> FileResponse:
        return FileResponse(ui_root / "app" / "index.html")

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.post("/api/ingest/text", response_model=IngestTextResponse)
    def ingest_text(request: IngestTextRequest) -> IngestTextResponse:
        state = _state(app)
        result = state.ingestion_service.ingest_text(
            raw_text=request.markdown_text,
            source_path_hint=request.source_path_hint,
            doc_id=request.doc_id,
        )
        stored_jobs = _store_jobs(state, result.jobs)
        return IngestTextResponse(**_build_ingest_payload(result, stored_jobs))

    @app.post("/api/ingest/file", response_model=IngestFileResponse)
    def ingest_file(request: IngestFileRequest) -> IngestFileResponse:
        state = _state(app)
        resolved_path = _resolve_input_path(state.root_dir, request.path, must_be_dir=False)
        result = state.ingestion_service.ingest_file(resolved_path, doc_id=request.doc_id)
        stored_jobs = _store_jobs(state, result.jobs)
        return IngestFileResponse(**_build_ingest_payload(result, stored_jobs))

    @app.post("/api/ingest/dir", response_model=IngestDirectoryResponse)
    def ingest_dir(request: IngestDirRequest) -> IngestDirectoryResponse:
        state = _state(app)
        resolved_path = _resolve_input_path(state.root_dir, request.path, must_be_dir=True)
        results = state.ingestion_service.ingest_directory(resolved_path, recursive=request.recursive)
        payloads = []
        for result in results:
            payloads.append(
                _build_ingest_payload(
                    result,
                    _store_jobs(state, result.jobs),
                )
            )
        return IngestDirectoryResponse(
            root_path=str(resolved_path),
            recursive=request.recursive,
            imported_count=len(payloads),
            results=payloads,
        )

    @app.post("/api/record/bjj", response_model=RecordBJJResponse)
    def record_bjj(request: BJJRecordRequest) -> RecordBJJResponse:
        state = _state(app)
        result = state.ingestion_service.ingest_text(
            raw_text=request.bjj_markdown,
            source_path_hint="record_bjj.md",
            doc_id=request.doc_id,
        )
        stored_jobs = _store_jobs(state, result.jobs)
        return RecordBJJResponse(
            doc_id=result.document.doc_id,
            doc_version_id=result.doc_version.doc_version_id,
            chunk_id=result.chunks[0].chunk_id if result.chunks else None,
            jobs=stored_jobs,
        )

    @app.post("/api/record/notes", response_model=RecordNotesResponse)
    def record_notes(request: NotesRecordRequest) -> RecordNotesResponse:
        state = _state(app)
        markdown = f"---\ntype: notes\ntitle: Quick Note\n---\n\n{request.notes_text}\n"
        result = state.ingestion_service.ingest_text(
            raw_text=markdown,
            source_path_hint="record_notes.md",
            doc_id=request.doc_id,
        )
        stored_jobs = _store_jobs(state, result.jobs)
        return RecordNotesResponse(
            doc_id=result.document.doc_id,
            doc_version_id=result.doc_version.doc_version_id,
            chunk_ids=[chunk.chunk_id for chunk in result.chunks],
            jobs=stored_jobs,
        )

    @app.post("/api/retrieve", response_model=RetrieveResponse)
    def retrieve(request: RetrieveRequest) -> RetrieveResponse:
        state = _state(app)
        outcome = state.retrieval_service.retrieve(
            query_text=request.query_text,
            filters_hint=request.filters,
            mode=request.mode,
            top_k=request.k,
        )
        return RetrieveResponse(
            trace_id=request.trace_id,
            probe_stats=outcome.probe_stats,
            retrieval_log=outcome.retrieval_log,
            evidence_pack=outcome,
        )

    @app.post("/api/chat/turn")
    def chat_turn(request: ChatTurnRequest):
        state = _state(app)
        conversation = state.get_or_create_conversation(request.conversation_id)
        recorder = TraceRecorder(
            runtime_config_snapshot=state.runtime_config,
            conversation_id=conversation.conversation_id,
        )
        with recorder.span("chat.turn_total", entrypoint="chat"):
            orchestrator_outcome = state.orchestrator_service.route(
                user_message=request.user_message,
                session_state=conversation.state,
                entrypoint=EntryPoint.CHAT,
            )
            conversation.state = _model_copy(orchestrator_outcome.session_state)
            request_log = RequestLog(
                entrypoint="chat",
                domain=orchestrator_outcome.execution_plan.domain.value,
                task=orchestrator_outcome.execution_plan.task.value,
                profile_version_id=state.current_profile.profile_version_id,
                confirmed_slots=conversation.state.slots,
                plan_check=orchestrator_outcome.plan_check,
                execution_plan=orchestrator_outcome.execution_plan,
            )
            recorder.set_request_log(request_log)
            if orchestrator_outcome.probe_stats is not None:
                recorder.set_retrieval_log(RetrievalLog(probe_stats=orchestrator_outcome.probe_stats))
            if orchestrator_outcome.plan_check is not None and (
                orchestrator_outcome.plan_check.need_replan or orchestrator_outcome.llm_replan_invoked
            ):
                recorder.add_event(
                    "orchestrator.replan_llm",
                    invoked=orchestrator_outcome.llm_replan_invoked,
                    result=orchestrator_outcome.llm_replan_result,
                    reason_codes=orchestrator_outcome.plan_check.reason_codes,
                )

            if orchestrator_outcome.execution_plan.next_action.value == "WRITE_FLOW":
                clarify = ClarifyRequest(
                    who=ClarifyWho.ORCHESTRATOR,
                    slot=ClarifySlot.DOMAIN,
                    options=["训练", "写作/阅读"],
                    template_id="REDIRECT_RECORD_V1",
                    round=conversation.state.clarify_round,
                    why="检测到写入意图，建议改走 record 入口。",
                )
                clarify_input = _build_generation_input_snapshot(
                    task=orchestrator_outcome.execution_plan.task.value,
                    query_original=request.user_message,
                    query_clean=request.user_message.strip(),
                    confirmed_slots=conversation.state.slots,
                    coach_clarify_round=conversation.state.coach_clarify_round,
                    coach_pending_slot=conversation.state.coach_pending_slot,
                    profile_summary=state.current_profile,
                )
                recorder.set_generation_log(
                    GenerationLog(
                        provider=state.runtime_config.model_routing.provider,
                        model=state.runtime_config.model_routing.base_model,
                        prompt_version=state.runtime_config.prompt_versions.replan,
                        prompt_snapshot=build_trace_prompt_snapshot(clarify_input),
                        input_snapshot=clarify_input,
                        output=_dump(clarify),
                    )
                )
                recorder.persist(state.trace_store)
                trace_id = recorder.trace_id
                response = ChatClarifyTurnResponse(
                    trace_id=trace_id,
                    conversation_id=conversation.conversation_id,
                    response=clarify,
                )
                conversation.turns.append({"user": request.user_message, "assistant": _dump(response.response)})
                return _dump(response)

            if orchestrator_outcome.execution_plan.next_action.value == "CLARIFY":
                clarify = ClarifyRequest(
                    who=ClarifyWho.ORCHESTRATOR,
                    slot=orchestrator_outcome.execution_plan.clarify.slot,
                    options=orchestrator_outcome.execution_plan.clarify.options,
                    template_id=orchestrator_outcome.execution_plan.clarify.question_template_id,
                    round=conversation.state.clarify_round,
                    why="; ".join(orchestrator_outcome.execution_plan.explain.reason_codes) or "需要补充槽位。",
                )
                recorder.add_event(
                    "clarify.requested",
                    who=clarify.who.value,
                    slot=clarify.slot.value,
                    round=clarify.round,
                )
                clarify_input = _build_generation_input_snapshot(
                    task=orchestrator_outcome.execution_plan.task.value,
                    query_original=request.user_message,
                    query_clean=request.user_message.strip(),
                    confirmed_slots=conversation.state.slots,
                    coach_clarify_round=conversation.state.coach_clarify_round,
                    coach_pending_slot=conversation.state.coach_pending_slot,
                    profile_summary=state.current_profile,
                )
                recorder.set_generation_log(
                    GenerationLog(
                        provider=state.runtime_config.model_routing.provider,
                        model=state.runtime_config.model_routing.base_model,
                        prompt_version=state.runtime_config.prompt_versions.replan,
                        prompt_snapshot=build_trace_prompt_snapshot(clarify_input),
                        input_snapshot=clarify_input,
                        output=_dump(clarify),
                    )
                )
                recorder.persist(state.trace_store)
                trace_id = recorder.trace_id
                response = ChatClarifyTurnResponse(
                    trace_id=trace_id,
                    conversation_id=conversation.conversation_id,
                    response=clarify,
                )
                conversation.turns.append({"user": request.user_message, "assistant": _dump(response.response)})
                return _dump(response)

            retrieval_outcome = state.retrieval_service.retrieve(
                query_text=orchestrator_outcome.execution_plan.retrieval_plan.query_text,
                filters_hint=orchestrator_outcome.execution_plan.retrieval_plan.filters,
                mode="full",
                top_k=orchestrator_outcome.execution_plan.retrieval_plan.top_k,
            )
            recorder.set_retrieval_log(retrieval_outcome.retrieval_log)
            recorder.set_evidence_log(retrieval_outcome)

            final_payload = None
            validator_report = None
            input_snapshot = _build_generation_input_snapshot(
                task=orchestrator_outcome.execution_plan.task.value,
                query_original=request.user_message,
                query_clean=request.user_message.strip(),
                confirmed_slots=conversation.state.slots,
                coach_clarify_round=conversation.state.coach_clarify_round,
                coach_pending_slot=conversation.state.coach_pending_slot,
                profile_summary=state.current_profile,
                frozen_evidence_pack=retrieval_outcome,
            )
            if orchestrator_outcome.execution_plan.task.value == "COACH_BJJ":
                coach_outcome = state.bjj_coach_service.run(
                    BJJCoachInput(
                        query_original=input_snapshot.query_original,
                        query_clean=input_snapshot.query_clean,
                        confirmed_slots=input_snapshot.confirmed_slots,
                        coach_clarify_round=input_snapshot.coach_clarify_round,
                        coach_pending_slot=input_snapshot.coach_pending_slot,
                        profile_summary=input_snapshot.profile_summary_snapshot or state.current_profile,
                    ),
                    evidence_pack=retrieval_outcome,
                )
                if coach_outcome.clarify_request is not None:
                    conversation.state.coach_pending_slot = coach_outcome.clarify_request.slot.value
                    conversation.state.coach_clarify_round = coach_outcome.clarify_request.round
                    clarify_input = _build_generation_input_snapshot(
                        task=orchestrator_outcome.execution_plan.task.value,
                        query_original=request.user_message,
                        query_clean=request.user_message.strip(),
                        confirmed_slots=conversation.state.slots,
                        coach_clarify_round=conversation.state.coach_clarify_round,
                        coach_pending_slot=conversation.state.coach_pending_slot,
                        profile_summary=state.current_profile,
                        frozen_evidence_pack=retrieval_outcome,
                    )
                    recorder.add_event(
                        "clarify.requested",
                        who=coach_outcome.clarify_request.who.value,
                        slot=coach_outcome.clarify_request.slot.value,
                        round=coach_outcome.clarify_request.round,
                    )
                    recorder.set_generation_log(
                        GenerationLog(
                            provider=state.runtime_config.model_routing.provider,
                            model=state.runtime_config.model_routing.base_model,
                            prompt_version=state.runtime_config.prompt_versions.bjj_coach,
                            prompt_snapshot=build_trace_prompt_snapshot(clarify_input),
                            input_snapshot=clarify_input,
                            output=_dump(coach_outcome.clarify_request),
                        )
                    )
                    recorder.persist(state.trace_store)
                    trace_id = recorder.trace_id
                    response = ChatClarifyTurnResponse(
                        trace_id=trace_id,
                        conversation_id=conversation.conversation_id,
                        response=coach_outcome.clarify_request,
                    )
                    conversation.turns.append({"user": request.user_message, "assistant": _dump(response.response)})
                    return _dump(response)
                final_payload = coach_outcome.final_answer
                validator_report = coach_outcome.validator_report
            else:
                literary_outcome = state.literary_service.run(request.user_message, retrieval_outcome)
                final_payload = literary_outcome

            recorder.set_generation_log(
                GenerationLog(
                    provider=state.runtime_config.model_routing.provider,
                    model=state.runtime_config.model_routing.base_model,
                    prompt_version=(
                        state.runtime_config.prompt_versions.bjj_coach
                        if orchestrator_outcome.execution_plan.task.value == "COACH_BJJ"
                        else state.runtime_config.prompt_versions.literary
                    ),
                    prompt_snapshot=build_trace_prompt_snapshot(input_snapshot),
                    input_snapshot=input_snapshot,
                    output=_dump(final_payload),
                    validator_report=validator_report,
                )
            )
            recorder.persist(state.trace_store)
            trace_id = recorder.trace_id
            response = ChatFinalTurnResponse(
                trace_id=trace_id,
                conversation_id=conversation.conversation_id,
                response=final_payload,
            )
            conversation.turns.append({"user": request.user_message, "assistant": _dump(response.response)})
            conversation.state.pending_slot = None
            conversation.state.coach_pending_slot = None
            conversation.state.coach_clarify_round = 0
            return _dump(response)

    @app.get("/api/chat/{conversation_id}", response_model=ChatConversationResponse)
    def get_conversation(conversation_id: str) -> ChatConversationResponse:
        state = _state(app)
        conversation = state.conversations.get(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return ChatConversationResponse(turns=conversation.turns, last_state=conversation.state)

    @app.get("/api/traces", response_model=TracesListResponse)
    def list_traces() -> TracesListResponse:
        state = _state(app)
        traces = []
        for trace_id in state.trace_store.list_trace_ids():
            trace = state.trace_store.read_trace(trace_id)
            output = trace.generation_log.output or {}
            traces.append(
                TraceSummaryItem(
                    trace_id=trace.trace_id,
                    created_at=trace.spans[0].started_at.isoformat() if trace.spans else None,
                    domain=trace.request_log.domain,
                    task=trace.request_log.task,
                    gate_label=output.get("reasoning_status", {}).get("gate_label") if isinstance(output, dict) else None,
                    latency=trace.generation_log.latency_ms,
                    cost=trace.generation_log.cost_estimate,
                    validator_pass=trace.generation_log.validator_report.validator_pass
                    if trace.generation_log.validator_report
                    else None,
                )
            )
        return TracesListResponse(traces=traces)

    @app.get("/api/jobs", response_model=JobsListResponse)
    def list_jobs() -> JobsListResponse:
        state = _state(app)
        return JobsListResponse(jobs=state.job_service.list_jobs())

    @app.post("/api/jobs/run-next", response_model=RunJobResponse)
    def run_next_job(request: RunJobsRequest) -> RunJobResponse:
        state = _state(app)
        result = state.job_service.run_next(job_types=request.job_types or None)
        return RunJobResponse(result=_dump(result))

    @app.get("/api/traces/{trace_id}", response_model=TraceRecord)
    def get_trace(trace_id: str) -> TraceRecord:
        state = _state(app)
        return state.trace_store.read_trace(trace_id)

    @app.post("/api/replay/{trace_id}", response_model=ReplayTraceResponse)
    def replay_trace(trace_id: str, request: ReplayRequest) -> ReplayTraceResponse:
        state = _state(app)
        trace = state.trace_store.read_trace(trace_id)
        variant = ModelVariant(request.model_variant)
        recorder = TraceRecorder(
            runtime_config_snapshot=state.runtime_config.copy(
                update={"policy_version": variant.value}
            ),
            conversation_id=trace.conversation_id,
        )
        recorder.set_request_log(trace.request_log)
        recorder.set_retrieval_log(trace.retrieval_log)
        recorder.set_evidence_log(trace.evidence_log)
        replay_input = _resolve_replay_input_snapshot(trace, state.current_profile)
        replay_evidence = (
            replay_input.frozen_evidence_pack
            if request.use_frozen_evidence and replay_input.frozen_evidence_pack.items
            else trace.evidence_log
        )

        if trace.request_log.task == "COACH_BJJ":
            coach_outcome = state.bjj_coach_service.run(
                BJJCoachInput(
                    query_original=replay_input.query_original,
                    query_clean=replay_input.query_clean,
                    confirmed_slots=replay_input.confirmed_slots,
                    coach_clarify_round=replay_input.coach_clarify_round,
                    coach_pending_slot=replay_input.coach_pending_slot,
                    profile_summary=replay_input.profile_summary_snapshot or state.current_profile,
                ),
                evidence_pack=replay_evidence,
            )
            final_answer = coach_outcome.final_answer
            validator_report = coach_outcome.validator_report
        else:
            final_answer = state.literary_service.run(
                replay_input.query_original,
                replay_evidence,
            )
            validator_report = None

        recorder.set_generation_log(
            GenerationLog(
                provider=state.runtime_config.model_routing.provider,
                model=state.sft_service.resolve_model_for_variant(state.runtime_config, variant),
                prompt_version=trace.generation_log.prompt_version,
                prompt_snapshot=build_trace_prompt_snapshot(replay_input),
                input_snapshot=replay_input,
                output=_dump(final_answer),
                validator_report=validator_report,
            )
        )
        recorder.persist(state.trace_store)
        new_trace_id = recorder.trace_id
        return ReplayTraceResponse(trace_id=new_trace_id, final_answer=final_answer)

    @app.post("/api/eval/run", response_model=EvalRunLaunchResponse)
    def run_eval(request: EvalRunAPIRequest) -> EvalRunLaunchResponse:
        state = _state(app)
        result = state.evaluation_service.run(
            EvalRunRequest(
                eval_set_id=request.eval_set_id,
                model_variant=ModelVariant(request.model_variant),
                use_frozen_evidence=request.use_frozen_evidence,
            ),
            trace_ids=request.trace_ids or None,
        )
        return EvalRunLaunchResponse(eval_run_id=result.eval_run_id)

    @app.get("/api/eval/results", response_model=EvalResultsResponse)
    def get_eval_results() -> EvalResultsResponse:
        state = _state(app)
        return EvalResultsResponse(runs=state.evaluation_service.list_results())

    @app.post("/api/sft/export", response_model=SFTExportResponse)
    def export_sft(request: SFTExportRequest) -> SFTExportResponse:
        state = _state(app)
        export_dir = state.root_dir / "datasets" / "sft" / "v1" / datetime.utcnow().strftime("%Y%m%d")
        manifest, _samples = state.sft_service.export_dataset(request=request, output_dir=export_dir)
        return SFTExportResponse(export_path=str(export_dir), manifest=manifest)

    @app.get("/api/profile", response_model=ProfileResponse)
    def get_profile() -> ProfileResponse:
        state = _state(app)
        return ProfileResponse(**_dump(state.current_profile))

    @app.put("/api/profile", response_model=ProfileResponse)
    def put_profile(request: ProfilePatchRequest) -> ProfileResponse:
        state = _state(app)
        state.current_profile = ProfileSummary(
            profile_version_id=f"profile_{uuid4().hex[:12]}",
            ruleset_default=request.ruleset_default or state.current_profile.ruleset_default,
            injuries=[ProfileConstraint(**item) for item in request.injuries],
            forbidden_actions=[ProfileConstraint(**item) for item in request.forbidden_actions],
            preferences=[ProfileConstraint(**item) for item in request.preferences],
        )
        return ProfileResponse(**_dump(state.current_profile))

    return app


def _state(app: FastAPI) -> AppState:
    return app.state.pda


def _dump(model):
    if model is None:
        return None
    if hasattr(model, "model_dump"):
        return model.model_dump(by_alias=True)
    if hasattr(model, "dict"):
        return model.dict(by_alias=True)
    return model


def _model_copy(model):
    if hasattr(model, "model_copy"):
        return model.model_copy(deep=True)
    return model.copy(deep=True)


def _store_jobs(state: AppState, jobs) -> list:
    return [
        state.job_service.enqueue(job_type=job.job_type, payload=job.payload, job_id=job.job_id)
        for job in jobs
    ]


def _build_ingest_payload(result, stored_jobs) -> dict:
    source_path = result.chunks[0].locator.source_path if result.chunks else None
    return {
        "source_path": source_path,
        "doc_id": result.document.doc_id,
        "doc_version_id": result.doc_version.doc_version_id,
        "chunk_ids": [chunk.chunk_id for chunk in result.chunks],
        "jobs": stored_jobs,
    }


def _build_generation_input_snapshot(
    *,
    task: str | None,
    query_original: str,
    query_clean: str,
    confirmed_slots: dict[str, str],
    coach_clarify_round: int,
    coach_pending_slot: str | None,
    profile_summary: ProfileSummary,
    frozen_evidence_pack=None,
):
    return build_trace_generation_input_snapshot(
        task=task,
        query_original=query_original,
        query_clean=query_clean,
        confirmed_slots=confirmed_slots,
        coach_clarify_round=coach_clarify_round,
        coach_pending_slot=coach_pending_slot,
        profile_summary=_model_copy(profile_summary),
        frozen_evidence_pack=_model_copy(frozen_evidence_pack) if frozen_evidence_pack is not None else None,
    )


def _resolve_replay_input_snapshot(trace: TraceRecord, fallback_profile: ProfileSummary):
    snapshot = trace.generation_log.input_snapshot
    if snapshot is not None:
        return _model_copy(snapshot)
    retrieval_plan = trace.retrieval_log.retrieval_plan
    return _build_generation_input_snapshot(
        task=trace.request_log.task,
        query_original=retrieval_plan.query_original if retrieval_plan is not None else "",
        query_clean=retrieval_plan.query_text if retrieval_plan is not None else "",
        confirmed_slots=trace.request_log.confirmed_slots,
        coach_clarify_round=0,
        coach_pending_slot=None,
        profile_summary=fallback_profile,
        frozen_evidence_pack=trace.evidence_log,
    )


def _resolve_input_path(root_dir: str | Path, raw_path: str, must_be_dir: bool) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path(root_dir) / candidate
    resolved = candidate.resolve()
    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"path not found: {resolved}")
    if must_be_dir and not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"expected directory path: {resolved}")
    if not must_be_dir and not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"expected file path: {resolved}")
    return resolved


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]
