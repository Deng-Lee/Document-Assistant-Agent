from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from queue import SimpleQueue
from threading import Thread
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from server.app.agents.bjj_coach.types import BJJCoachInput
from server.app.core import (
    ChatClarifyTurnResponse,
    ChatFinalTurnResponse,
    ChatStreamCompletedEvent,
    ChatStreamFailedEvent,
    ChatStreamProgressEvent,
    ChatStreamStartedEvent,
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
    EvalRubricSubmitRequest,
    IngestDirRequest,
    IngestFileRequest,
    IngestTextRequest,
    MaintenanceReembedRequest,
    MaintenanceReindexRequest,
    NotesRecordRequest,
    ProfilePatchRequest,
    ReplayRequest,
    RetrieveRequest,
    RunJobsRequest,
    SFTTrainAPIRequest,
)
from .responses import (
    ChatConversationResponse,
    EnqueueJobResponse,
    EvalResultsResponse,
    EvalRubricEntriesResponse,
    EvalRubricResponse,
    EvalRunLaunchResponse,
    HealthResponse,
    IngestDirectoryResponse,
    IngestFileResponse,
    IngestTextResponse,
    JobsListResponse,
    MaintenanceEnqueueResponse,
    ProfileHistoryResponse,
    ProfileResponse,
    RecordBJJResponse,
    RecordNotesResponse,
    ReplayTraceResponse,
    RetrieveResponse,
    RunJobResponse,
    SFTExportResponse,
    SFTTrainResponse,
    TraceSummaryItem,
    TracesListResponse,
)
from .state import AppState, create_app_state


def create_app(root_dir: str | Path | None = None) -> FastAPI:
    resolved_root = Path(root_dir or Path.cwd()).resolve()
    app = FastAPI(title="Personal Document Assistant API", version="0.1.0")
    app.state.pda = create_app_state(resolved_root)

    @app.get("/", include_in_schema=False)
    def backend_landing() -> HTMLResponse:
        return HTMLResponse(_backend_landing_page())

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
        return _run_chat_turn(_state(app), request)

    @app.post("/api/chat/stream")
    def chat_stream(request: ChatTurnRequest) -> StreamingResponse:
        state = _state(app)

        def event_stream():
            queue: SimpleQueue[dict | object] = SimpleQueue()
            sentinel = object()

            def emit(event) -> None:
                queue.put(_dump(event))

            def worker() -> None:
                try:
                    _run_chat_turn(state, request, emit_event=emit)
                except Exception as exc:
                    emit(ChatStreamFailedEvent(detail=str(exc)))
                finally:
                    queue.put(sentinel)

            Thread(target=worker, daemon=True).start()
            while True:
                item = queue.get()
                if item is sentinel:
                    break
                yield _encode_sse(item)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

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

    @app.post("/api/chunks/{chunk_id}/safe_summary/rebuild", response_model=EnqueueJobResponse)
    def rebuild_safe_summary(chunk_id: str) -> EnqueueJobResponse:
        state = _state(app)
        chunk = state.document_repository.get_chunk(chunk_id)
        if chunk is None:
            raise HTTPException(status_code=404, detail="chunk not found")
        state.document_repository.update_chunk_summary_state(
            chunk_id,
            safe_summary=chunk.safe_summary or "",
            summary_model=state.runtime_config.model_routing.base_model,
            summary_prompt_version=state.runtime_config.prompt_versions.safe_summary,
            summary_status="pending",
            summary_error_code=None,
        )
        job = state.job_service.enqueue(
            "safe_summary_build",
            {
                "chunk_id": chunk.chunk_id,
                "doc_version_id": chunk.doc_version_id,
                "summary_prompt_version": state.runtime_config.prompt_versions.safe_summary,
                "summary_model": state.runtime_config.model_routing.base_model,
            },
        )
        return EnqueueJobResponse(job=job)

    @app.post("/api/maintenance/reindex", response_model=MaintenanceEnqueueResponse)
    def enqueue_reindex(request: MaintenanceReindexRequest) -> MaintenanceEnqueueResponse:
        state = _state(app)
        try:
            versions, affected_chunks, jobs = state.job_service.enqueue_reindex_jobs(
                scope=request.scope,
                doc_version_id=request.doc_version_id,
                doc_id=request.doc_id,
                rebuild_fts5=request.rebuild_fts5,
                rebuild_chroma=request.rebuild_chroma,
                rebuild_safe_summary=request.rebuild_safe_summary,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return MaintenanceEnqueueResponse(
            scope=request.scope,
            doc_version_ids=[version.doc_version_id for version in versions],
            affected_chunk_count=affected_chunks,
            jobs=jobs,
        )

    @app.post("/api/maintenance/reembed", response_model=MaintenanceEnqueueResponse)
    def enqueue_reembed(request: MaintenanceReembedRequest) -> MaintenanceEnqueueResponse:
        state = _state(app)
        try:
            versions, affected_chunks, jobs = state.job_service.enqueue_reembed_jobs(
                scope=request.scope,
                embedding_version_id=request.embedding_version_id,
                doc_version_id=request.doc_version_id,
                doc_id=request.doc_id,
                dry_run=request.dry_run,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return MaintenanceEnqueueResponse(
            scope=request.scope,
            doc_version_ids=[version.doc_version_id for version in versions],
            affected_chunk_count=affected_chunks,
            jobs=jobs,
            dry_run=request.dry_run,
            embedding_version_id=request.embedding_version_id,
        )

    @app.get("/api/traces/{trace_id}", response_model=TraceRecord)
    def get_trace(trace_id: str) -> TraceRecord:
        state = _state(app)
        return state.trace_store.read_trace(trace_id)

    @app.post("/api/replay/{trace_id}", response_model=ReplayTraceResponse)
    def replay_trace(trace_id: str, request: ReplayRequest) -> ReplayTraceResponse:
        state = _state(app)
        trace = state.trace_store.read_trace(trace_id)
        variant = ModelVariant(request.model_variant)
        replayed_trace, final_answer = state.sft_service.replay_trace(
            source_trace=trace,
            variant=variant,
            runtime_config=state.runtime_config,
            current_profile=state.current_profile,
            bjj_coach_service=state.bjj_coach_service,
            literary_service=state.literary_service,
            use_frozen_evidence=request.use_frozen_evidence,
            override_generation_config=request.override_generation_config,
        )
        return ReplayTraceResponse(trace_id=replayed_trace.trace_id, final_answer=final_answer)

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

    @app.post("/api/eval/rubric", response_model=EvalRubricResponse)
    def submit_eval_rubric(request: EvalRubricSubmitRequest) -> EvalRubricResponse:
        state = _state(app)
        try:
            entry, run = state.evaluation_service.submit_manual_rubric(
                eval_run_id=request.eval_run_id,
                trace_id=request.trace_id,
                reviewer=request.reviewer,
                scores=request.scores,
                notes=request.notes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return EvalRubricResponse(entry=entry, run=run)

    @app.get("/api/eval/rubric/{eval_run_id}", response_model=EvalRubricEntriesResponse)
    def list_eval_rubrics(eval_run_id: str) -> EvalRubricEntriesResponse:
        state = _state(app)
        return EvalRubricEntriesResponse(entries=state.evaluation_service.list_manual_rubrics(eval_run_id))

    @app.post("/api/sft/export", response_model=SFTExportResponse)
    def export_sft(request: SFTExportRequest) -> SFTExportResponse:
        state = _state(app)
        export_dir = state.root_dir / "datasets" / "sft" / "v1" / datetime.utcnow().strftime("%Y%m%d")
        manifest, _samples = state.sft_service.export_dataset(request=request, output_dir=export_dir)
        return SFTExportResponse(export_path=str(export_dir), manifest=manifest)

    @app.post("/api/sft/train", response_model=SFTTrainResponse)
    def train_sft(request: SFTTrainAPIRequest) -> SFTTrainResponse:
        state = _state(app)
        checkpoint = state.sft_service.train_policy(request)
        if request.activate:
            state.runtime_config.model_routing.policy_model = checkpoint.policy_model_ref
        return SFTTrainResponse(
            checkpoint=checkpoint,
            active_policy_ref=state.sft_service.get_active_policy_ref(),
        )

    @app.get("/api/profile", response_model=ProfileResponse)
    def get_profile() -> ProfileResponse:
        state = _state(app)
        return ProfileResponse(**_dump(state.current_profile))

    @app.get("/api/profile/history", response_model=ProfileHistoryResponse)
    def get_profile_history() -> ProfileHistoryResponse:
        state = _state(app)
        return ProfileHistoryResponse(profiles=state.profile_repository.list_profiles())

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
        state.profile_repository.upsert_profile(state.current_profile)
        state.runtime_config.profile_version_id = state.current_profile.profile_version_id
        return ProfileResponse(**_dump(state.current_profile))

    return app


def _run_chat_turn(state: AppState, request: ChatTurnRequest, emit_event=None):
    conversation = state.get_or_create_conversation(request.conversation_id)
    recorder = TraceRecorder(
        runtime_config_snapshot=state.runtime_config,
        conversation_id=conversation.conversation_id,
    )
    _emit_chat_event(
        emit_event,
        ChatStreamStartedEvent(
            conversation_id=conversation.conversation_id,
            message="chat turn accepted",
        ),
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
        _emit_chat_event(
            emit_event,
            ChatStreamProgressEvent(
                conversation_id=conversation.conversation_id,
                stage="orchestrator",
                message=f"next_action={orchestrator_outcome.execution_plan.next_action.value}",
            ),
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
            response = ChatClarifyTurnResponse(
                trace_id=recorder.trace_id,
                conversation_id=conversation.conversation_id,
                response=clarify,
            )
            conversation.turns.append({"user": request.user_message, "assistant": _dump(response.response)})
            payload = _dump(response)
            _emit_chat_event(
                emit_event,
                ChatStreamCompletedEvent(
                    conversation_id=conversation.conversation_id,
                    payload=response,
                ),
            )
            return payload

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
            response = ChatClarifyTurnResponse(
                trace_id=recorder.trace_id,
                conversation_id=conversation.conversation_id,
                response=clarify,
            )
            conversation.turns.append({"user": request.user_message, "assistant": _dump(response.response)})
            payload = _dump(response)
            _emit_chat_event(
                emit_event,
                ChatStreamCompletedEvent(
                    conversation_id=conversation.conversation_id,
                    payload=response,
                ),
            )
            return payload

        retrieval_outcome = state.retrieval_service.retrieve(
            query_text=orchestrator_outcome.execution_plan.retrieval_plan.query_text,
            filters_hint=orchestrator_outcome.execution_plan.retrieval_plan.filters,
            mode="full",
            top_k=orchestrator_outcome.execution_plan.retrieval_plan.top_k,
        )
        recorder.set_retrieval_log(retrieval_outcome.retrieval_log)
        recorder.set_evidence_log(retrieval_outcome)
        _emit_chat_event(
            emit_event,
            ChatStreamProgressEvent(
                conversation_id=conversation.conversation_id,
                stage="retrieval",
                message=f"evidence_items={len(retrieval_outcome.items)}",
            ),
        )

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
                response = ChatClarifyTurnResponse(
                    trace_id=recorder.trace_id,
                    conversation_id=conversation.conversation_id,
                    response=coach_outcome.clarify_request,
                )
                conversation.turns.append({"user": request.user_message, "assistant": _dump(response.response)})
                payload = _dump(response)
                _emit_chat_event(
                    emit_event,
                    ChatStreamCompletedEvent(
                        conversation_id=conversation.conversation_id,
                        payload=response,
                    ),
                )
                return payload
            final_payload = coach_outcome.final_answer
            validator_report = coach_outcome.validator_report
        else:
            final_payload = state.literary_service.run(request.user_message, retrieval_outcome)
        _emit_chat_event(
            emit_event,
            ChatStreamProgressEvent(
                conversation_id=conversation.conversation_id,
                stage="generation",
                message=f"task={orchestrator_outcome.execution_plan.task.value}",
            ),
        )

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
        response = ChatFinalTurnResponse(
            trace_id=recorder.trace_id,
            conversation_id=conversation.conversation_id,
            response=final_payload,
        )
        conversation.turns.append({"user": request.user_message, "assistant": _dump(response.response)})
        conversation.state.pending_slot = None
        conversation.state.coach_pending_slot = None
        conversation.state.coach_clarify_round = 0
        payload = _dump(response)
        _emit_chat_event(
            emit_event,
            ChatStreamCompletedEvent(
                conversation_id=conversation.conversation_id,
                payload=response,
            ),
        )
        return payload


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


def _emit_chat_event(emit_event, event) -> None:
    if emit_event is None:
        return
    emit_event(event)


def _encode_sse(payload: dict) -> str:
    event_name = payload.get("event_type", "message")
    body = json.dumps(payload, ensure_ascii=False)
    return f"event: {event_name}\ndata: {body}\n\n"


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


def _backend_landing_page() -> str:
    frontend_root = _repo_root() / "web"
    package_exists = (frontend_root / "package.json").exists()
    next_hint = "ready" if package_exists else "missing"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Personal Document Assistant Backend</title>
    <style>
      :root {{
        color-scheme: light;
        --ink: #0f172a;
        --muted: #475569;
        --stroke: rgba(15, 23, 42, 0.12);
        --accent: #c2410c;
        --bg: linear-gradient(135deg, #f8fafc 0%, #fef3c7 55%, #fed7aa 100%);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        min-height: 100vh;
        font-family: "Avenir Next", "Segoe UI", sans-serif;
        background: var(--bg);
        color: var(--ink);
        display: grid;
        place-items: center;
        padding: 24px;
      }}
      main {{
        width: min(760px, 100%);
        background: rgba(255, 250, 242, 0.92);
        border: 1px solid var(--stroke);
        border-radius: 28px;
        padding: 32px;
        box-shadow: 0 24px 90px rgba(15, 23, 42, 0.12);
      }}
      h1 {{
        margin: 0 0 12px;
        font-size: clamp(2rem, 4vw, 3rem);
        font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
      }}
      p {{ color: var(--muted); line-height: 1.6; }}
      code {{
        background: rgba(15, 23, 42, 0.08);
        border-radius: 999px;
        padding: 0.2rem 0.55rem;
        font-family: "SFMono-Regular", Consolas, monospace;
      }}
      ul {{ padding-left: 1.15rem; }}
      a {{ color: var(--accent); }}
    </style>
  </head>
  <body>
    <main>
      <p>Personal Document Assistant</p>
      <h1>Backend API is running.</h1>
      <p>
        The repository frontend now lives in the Next.js app under <code>web/</code>.
        Frontend scaffold status: <code>{next_hint}</code>.
      </p>
      <p>
        Start the backend with <code>python3 -m server.app.api</code>, then start the frontend with
        <code>npm --prefix web run dev</code>.
      </p>
      <ul>
        <li>Health check: <a href="/api/health">/api/health</a></li>
        <li>Frontend package: <code>web/package.json</code></li>
        <li>Backend repo root: <code>{_repo_root()}</code></li>
      </ul>
    </main>
  </body>
</html>
"""
