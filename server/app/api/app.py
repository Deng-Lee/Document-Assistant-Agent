from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException

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
)
from server.app.observability import TraceRecorder

from .models import (
    BJJRecordRequest,
    ChatTurnRequest,
    EvalRunAPIRequest,
    IngestTextRequest,
    NotesRecordRequest,
    ProfilePatchRequest,
    ReplayRequest,
    RetrieveRequest,
    RunJobsRequest,
)
from .responses import (
    ChatConversationResponse,
    HealthResponse,
    IngestTextResponse,
    JobsListResponse,
    RecordBJJResponse,
    RecordNotesResponse,
    RetrieveResponse,
    RunJobResponse,
)
from .state import AppState, create_app_state


def create_app(root_dir: str | Path | None = None) -> FastAPI:
    resolved_root = Path(root_dir or Path.cwd()).resolve()
    app = FastAPI(title="Personal Document Assistant API", version="0.1.0")
    app.state.pda = create_app_state(resolved_root)

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
        return IngestTextResponse(
            doc_id=result.document.doc_id,
            doc_version_id=result.doc_version.doc_version_id,
            chunk_ids=[chunk.chunk_id for chunk in result.chunks],
            jobs=stored_jobs,
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
                execution_plan=orchestrator_outcome.execution_plan,
            )
            recorder.set_request_log(request_log)
            if orchestrator_outcome.probe_stats is not None:
                recorder.set_retrieval_log(RetrievalLog(probe_stats=orchestrator_outcome.probe_stats))

            if orchestrator_outcome.execution_plan.next_action.value == "WRITE_FLOW":
                clarify = ClarifyRequest(
                    who=ClarifyWho.ORCHESTRATOR,
                    slot=ClarifySlot.DOMAIN,
                    options=["训练", "写作/阅读"],
                    template_id="REDIRECT_RECORD_V1",
                    round=conversation.state.clarify_round,
                    why="检测到写入意图，建议改走 record 入口。",
                )
                recorder.set_generation_log(
                    GenerationLog(
                        provider=state.runtime_config.model_routing.provider,
                        model=state.runtime_config.model_routing.base_model,
                        prompt_version=state.runtime_config.prompt_versions.replan,
                        output=_dump(clarify),
                    )
                )
                trace_id = recorder.persist(state.trace_store)
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
                recorder.set_generation_log(
                    GenerationLog(
                        provider=state.runtime_config.model_routing.provider,
                        model=state.runtime_config.model_routing.base_model,
                        prompt_version=state.runtime_config.prompt_versions.replan,
                        output=_dump(clarify),
                    )
                )
                trace_id = recorder.persist(state.trace_store)
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
            if orchestrator_outcome.execution_plan.task.value == "COACH_BJJ":
                coach_outcome = state.bjj_coach_service.run(
                    BJJCoachInput(
                        query_original=request.user_message,
                        query_clean=request.user_message.strip(),
                        confirmed_slots=conversation.state.slots,
                        coach_clarify_round=conversation.state.coach_clarify_round,
                        coach_pending_slot=conversation.state.coach_pending_slot,
                        profile_summary=state.current_profile,
                    ),
                    evidence_pack=retrieval_outcome,
                )
                if coach_outcome.clarify_request is not None:
                    conversation.state.coach_pending_slot = coach_outcome.clarify_request.slot.value
                    conversation.state.coach_clarify_round = coach_outcome.clarify_request.round
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
                            output=_dump(coach_outcome.clarify_request),
                        )
                    )
                    trace_id = recorder.persist(state.trace_store)
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
                    output=_dump(final_payload),
                    validator_report=validator_report,
                )
            )
            trace_id = recorder.persist(state.trace_store)
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

    @app.get("/api/traces")
    def list_traces() -> dict:
        state = _state(app)
        traces = []
        for trace_id in state.trace_store.list_trace_ids():
            trace = state.trace_store.read_trace(trace_id)
            output = trace.generation_log.output or {}
            traces.append(
                {
                    "trace_id": trace.trace_id,
                    "created_at": trace.spans[0].started_at.isoformat() if trace.spans else None,
                    "domain": trace.request_log.domain,
                    "task": trace.request_log.task,
                    "gate_label": output.get("reasoning_status", {}).get("gate_label") if isinstance(output, dict) else None,
                    "latency": trace.generation_log.latency_ms,
                    "cost": trace.generation_log.cost_estimate,
                    "validator_pass": trace.generation_log.validator_report.validator_pass
                    if trace.generation_log.validator_report
                    else None,
                }
            )
        return {"traces": traces}

    @app.get("/api/jobs", response_model=JobsListResponse)
    def list_jobs() -> JobsListResponse:
        state = _state(app)
        return JobsListResponse(jobs=state.job_service.list_jobs())

    @app.post("/api/jobs/run-next", response_model=RunJobResponse)
    def run_next_job(request: RunJobsRequest) -> RunJobResponse:
        state = _state(app)
        result = state.job_service.run_next(job_types=request.job_types or None)
        return RunJobResponse(result=_dump(result))

    @app.get("/api/traces/{trace_id}")
    def get_trace(trace_id: str) -> dict:
        state = _state(app)
        trace = state.trace_store.read_trace(trace_id)
        return _dump(trace)

    @app.post("/api/replay/{trace_id}")
    def replay_trace(trace_id: str, request: ReplayRequest) -> dict:
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

        if trace.request_log.task == "COACH_BJJ":
            coach_outcome = state.bjj_coach_service.run(
                BJJCoachInput(
                    query_original=trace.retrieval_log.retrieval_plan.query_original if trace.retrieval_log.retrieval_plan else "",
                    query_clean=trace.retrieval_log.retrieval_plan.query_text if trace.retrieval_log.retrieval_plan else "",
                    confirmed_slots=trace.request_log.confirmed_slots,
                    profile_summary=state.current_profile,
                ),
                evidence_pack=trace.evidence_log,
            )
            final_answer = coach_outcome.final_answer
            validator_report = coach_outcome.validator_report
        else:
            final_answer = state.literary_service.run(
                trace.retrieval_log.retrieval_plan.query_original if trace.retrieval_log.retrieval_plan else "",
                trace.evidence_log,
            )
            validator_report = None

        recorder.set_generation_log(
            GenerationLog(
                provider=state.runtime_config.model_routing.provider,
                model=state.sft_service.resolve_model_for_variant(state.runtime_config, variant),
                prompt_version=trace.generation_log.prompt_version,
                output=_dump(final_answer),
                validator_report=validator_report,
            )
        )
        new_trace_id = recorder.persist(state.trace_store)
        return {
            "trace_id": new_trace_id,
            "final_answer": _dump(final_answer),
        }

    @app.post("/api/eval/run")
    def run_eval(request: EvalRunAPIRequest) -> dict:
        state = _state(app)
        result = state.evaluation_service.run(
            EvalRunRequest(
                eval_set_id=request.eval_set_id,
                model_variant=ModelVariant(request.model_variant),
                use_frozen_evidence=request.use_frozen_evidence,
            ),
            trace_ids=request.trace_ids or None,
        )
        return {"eval_run_id": result.eval_run_id}

    @app.get("/api/eval/results")
    def get_eval_results() -> dict:
        state = _state(app)
        return {"runs": [_dump(result) for result in state.evaluation_service.list_results()]}

    @app.post("/api/sft/export")
    def export_sft(request: SFTExportRequest) -> dict:
        state = _state(app)
        export_dir = state.root_dir / "datasets" / "sft" / "v1" / datetime.utcnow().strftime("%Y%m%d")
        manifest, _samples = state.sft_service.export_dataset(request=request, output_dir=export_dir)
        return {
            "export_path": str(export_dir),
            "manifest": _dump(manifest),
        }

    @app.get("/api/profile")
    def get_profile() -> dict:
        state = _state(app)
        return _dump(state.current_profile)

    @app.put("/api/profile")
    def put_profile(request: ProfilePatchRequest) -> dict:
        state = _state(app)
        state.current_profile = ProfileSummary(
            profile_version_id=f"profile_{uuid4().hex[:12]}",
            ruleset_default=request.ruleset_default or state.current_profile.ruleset_default,
            injuries=[ProfileConstraint(**item) for item in request.injuries],
            forbidden_actions=[ProfileConstraint(**item) for item in request.forbidden_actions],
            preferences=[ProfileConstraint(**item) for item in request.preferences],
        )
        return _dump(state.current_profile)

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
