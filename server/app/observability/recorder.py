from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from hashlib import sha1
from typing import Any, Iterator
from uuid import uuid4

from server.app.core import (
    EvidencePack,
    GenerationLog,
    RequestLog,
    RetrievalLog,
    RuntimeConfigSnapshot,
    TraceCaptureLevel,
    TraceEvent,
    TraceRecord,
    TraceSpan,
)
from server.app.storage import TraceStore


class TraceRecorder:
    """
    Lightweight structured recorder for V1 trace/span/event capture.

    The recorder is intentionally storage-agnostic until `persist()` is called.
    """

    def __init__(
        self,
        runtime_config_snapshot: RuntimeConfigSnapshot,
        trace_id: str | None = None,
        conversation_id: str | None = None,
    ):
        self.runtime_config_snapshot = runtime_config_snapshot
        self.trace_id = trace_id or _trace_id()
        self.conversation_id = conversation_id
        self.request_log = RequestLog(entrypoint="unknown")
        self.retrieval_log = RetrievalLog()
        self.evidence_log = EvidencePack()
        self.generation_log = GenerationLog(
            provider=runtime_config_snapshot.model_routing.provider,
            model=runtime_config_snapshot.model_routing.base_model,
            prompt_version=runtime_config_snapshot.prompt_versions.bjj_coach,
        )
        self.spans: list[TraceSpan] = []
        self.events: list[TraceEvent] = []
        self._open_spans: dict[str, int] = {}

    def set_request_log(self, request_log: RequestLog) -> None:
        self.request_log = request_log

    def set_retrieval_log(self, retrieval_log: RetrievalLog) -> None:
        self.retrieval_log = retrieval_log

    def set_evidence_log(self, evidence_log: EvidencePack) -> None:
        self.evidence_log = self._apply_capture_level(evidence_log)

    def set_generation_log(self, generation_log: GenerationLog) -> None:
        self.generation_log = generation_log

    def add_event(self, name: str, **attributes: Any) -> None:
        self.events.append(
            TraceEvent(
                name=name,
                timestamp=datetime.utcnow(),
                attributes=attributes,
            )
        )

    def add_stage_transition(self, from_stage: str, to_stage: str, **attributes: Any) -> None:
        transition = f"{from_stage}->{to_stage}"
        self.request_log.stage_transitions.append(transition)
        self.add_event(
            "orchestrator.stage_transition",
            from_stage=from_stage,
            to_stage=to_stage,
            **attributes,
        )

    def start_span(self, name: str, **attributes: Any) -> str:
        span_id = f"span_{uuid4().hex[:12]}"
        self.spans.append(
            TraceSpan(
                name=name,
                started_at=datetime.utcnow(),
                attributes=attributes,
            )
        )
        self._open_spans[span_id] = len(self.spans) - 1
        return span_id

    def end_span(self, span_id: str, **attributes: Any) -> None:
        index = self._open_spans.pop(span_id)
        span = self.spans[index]
        ended_at = datetime.utcnow()
        merged_attributes = dict(span.attributes)
        merged_attributes.update(attributes)
        self.spans[index] = TraceSpan(
            name=span.name,
            started_at=span.started_at,
            ended_at=ended_at,
            duration_ms=max(0, int((ended_at - span.started_at).total_seconds() * 1000)),
            attributes=merged_attributes,
        )

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[None]:
        span_id = self.start_span(name, **attributes)
        try:
            yield
        finally:
            self.end_span(span_id)

    def to_trace_record(self) -> TraceRecord:
        return TraceRecord(
            trace_id=self.trace_id,
            conversation_id=self.conversation_id,
            runtime_config_snapshot=self.runtime_config_snapshot,
            request_log=self.request_log,
            retrieval_log=self.retrieval_log,
            evidence_log=self.evidence_log,
            generation_log=self.generation_log,
            spans=self.spans,
            events=self.events,
        )

    def persist(self, trace_store: TraceStore) -> str:
        return trace_store.write_trace(self.to_trace_record())

    def _apply_capture_level(self, evidence_log: EvidencePack) -> EvidencePack:
        if self.runtime_config_snapshot.trace_capture_level == TraceCaptureLevel.DEBUG:
            return evidence_log
        # Minimal mode keeps the structural evidence contract only.
        return EvidencePack(
            items=evidence_log.items,
            token_budget=evidence_log.token_budget,
            per_doc_limit=evidence_log.per_doc_limit,
        )


def _trace_id() -> str:
    return f"trace_{sha1(uuid4().hex.encode('utf-8')).hexdigest()[:12]}"
