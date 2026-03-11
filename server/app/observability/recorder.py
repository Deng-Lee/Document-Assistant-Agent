from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
from hashlib import sha1
from typing import Any, Iterator
from uuid import uuid4

from server.app.core import (
    EvidencePack,
    EvidencePackItem,
    GenerationInputSnapshot,
    GenerationLog,
    PromptSnapshot,
    ProfileSummary,
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
        applied = self._apply_generation_capture_level(generation_log)
        self.generation_log = applied
        self.add_event(
            "generation.metadata",
            provider=applied.provider,
            model=applied.model,
            prompt_version=applied.prompt_version,
            prompt_hash=applied.prompt_hash,
            latency_ms=applied.latency_ms,
            cost_estimate=applied.cost_estimate,
            token_usage=applied.token_usage,
        )

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
        items = [
            EvidencePackItem(
                evidence_id=item.evidence_id,
                doc_id=item.doc_id,
                doc_version_id=item.doc_version_id,
                locator=item.locator,
                safe_summary=item.safe_summary,
                excerpt_snapshot=(
                    item.excerpt_snapshot
                    if self.runtime_config_snapshot.trace_capture_level == TraceCaptureLevel.DEBUG
                    else None
                ),
                metadata_digest=item.metadata_digest,
                rank_signals=item.rank_signals,
            )
            for item in evidence_log.items
        ]
        if self.runtime_config_snapshot.trace_capture_level == TraceCaptureLevel.DEBUG:
            return EvidencePack(
                items=items,
                token_budget=evidence_log.token_budget,
                per_doc_limit=evidence_log.per_doc_limit,
            )
        # Minimal mode keeps the structural evidence contract only.
        return EvidencePack(
            items=items,
            token_budget=evidence_log.token_budget,
            per_doc_limit=evidence_log.per_doc_limit,
        )

    def _apply_generation_capture_level(self, generation_log: GenerationLog) -> GenerationLog:
        input_snapshot = generation_log.input_snapshot
        if input_snapshot is not None:
            input_snapshot = self._sanitize_input_snapshot(input_snapshot)

        prompt_snapshot = generation_log.prompt_snapshot
        if prompt_snapshot is not None:
            prompt_snapshot = self._sanitize_prompt_snapshot(prompt_snapshot)

        prompt_hash = generation_log.prompt_hash or _prompt_hash(
            generation_log.prompt_version,
            prompt_snapshot,
        )
        return GenerationLog(
            provider=generation_log.provider,
            model=generation_log.model,
            prompt_version=generation_log.prompt_version,
            prompt_hash=prompt_hash,
            prompt_snapshot=prompt_snapshot,
            input_snapshot=input_snapshot,
            latency_ms=generation_log.latency_ms,
            token_usage=dict(generation_log.token_usage),
            cost_estimate=generation_log.cost_estimate,
            output=dict(generation_log.output),
            validator_report=generation_log.validator_report,
        )

    def _sanitize_input_snapshot(self, input_snapshot: GenerationInputSnapshot) -> GenerationInputSnapshot:
        if self.runtime_config_snapshot.trace_capture_level == TraceCaptureLevel.DEBUG:
            return GenerationInputSnapshot(
                task=input_snapshot.task,
                query_original=input_snapshot.query_original,
                query_clean=input_snapshot.query_clean,
                confirmed_slots=dict(input_snapshot.confirmed_slots),
                coach_clarify_round=input_snapshot.coach_clarify_round,
                coach_pending_slot=input_snapshot.coach_pending_slot,
                profile_summary_snapshot=input_snapshot.profile_summary_snapshot,
                profile_version_id=input_snapshot.profile_version_id,
                frozen_evidence_pack=self._apply_capture_level(input_snapshot.frozen_evidence_pack),
            )
        return GenerationInputSnapshot(
            task=input_snapshot.task,
            query_original="",
            query_clean="",
            confirmed_slots=dict(input_snapshot.confirmed_slots),
            coach_clarify_round=input_snapshot.coach_clarify_round,
            coach_pending_slot=input_snapshot.coach_pending_slot,
            profile_summary_snapshot=None,
            profile_version_id=input_snapshot.profile_version_id,
            frozen_evidence_pack=self._apply_capture_level(input_snapshot.frozen_evidence_pack),
        )

    def _sanitize_prompt_snapshot(self, prompt_snapshot: PromptSnapshot) -> PromptSnapshot:
        if self.runtime_config_snapshot.trace_capture_level == TraceCaptureLevel.DEBUG:
            return prompt_snapshot
        return PromptSnapshot(
            task=prompt_snapshot.task,
            query_original_hash=prompt_snapshot.query_original_hash,
            query_clean_hash=prompt_snapshot.query_clean_hash,
            confirmed_slot_keys=list(prompt_snapshot.confirmed_slot_keys),
            coach_clarify_round=prompt_snapshot.coach_clarify_round,
            coach_pending_slot=prompt_snapshot.coach_pending_slot,
            profile_version_id=prompt_snapshot.profile_version_id,
            evidence_item_count=prompt_snapshot.evidence_item_count,
        )


def _trace_id() -> str:
    return f"trace_{sha1(uuid4().hex.encode('utf-8')).hexdigest()[:12]}"


def build_generation_input_snapshot(
    *,
    task: str | None,
    query_original: str,
    query_clean: str,
    confirmed_slots: dict[str, str] | None = None,
    coach_clarify_round: int = 0,
    coach_pending_slot: str | None = None,
    profile_summary: ProfileSummary | None = None,
    frozen_evidence_pack: EvidencePack | None = None,
) -> GenerationInputSnapshot:
    return GenerationInputSnapshot(
        task=task,
        query_original=query_original,
        query_clean=query_clean,
        confirmed_slots=dict(confirmed_slots or {}),
        coach_clarify_round=coach_clarify_round,
        coach_pending_slot=coach_pending_slot,
        profile_summary_snapshot=profile_summary,
        profile_version_id=profile_summary.profile_version_id if profile_summary is not None else None,
        frozen_evidence_pack=frozen_evidence_pack or EvidencePack(),
    )


def build_prompt_snapshot(input_snapshot: GenerationInputSnapshot) -> PromptSnapshot:
    return PromptSnapshot(
        task=input_snapshot.task,
        query_original_hash=_fingerprint(input_snapshot.query_original),
        query_clean_hash=_fingerprint(input_snapshot.query_clean),
        confirmed_slot_keys=sorted(input_snapshot.confirmed_slots.keys()),
        coach_clarify_round=input_snapshot.coach_clarify_round,
        coach_pending_slot=input_snapshot.coach_pending_slot,
        profile_version_id=input_snapshot.profile_version_id,
        evidence_item_count=len(input_snapshot.frozen_evidence_pack.items),
        query_original_preview=_preview(input_snapshot.query_original),
        query_clean_preview=_preview(input_snapshot.query_clean),
        confirmed_slots_snapshot=dict(input_snapshot.confirmed_slots),
        frozen_evidence_ids=[item.evidence_id for item in input_snapshot.frozen_evidence_pack.items],
    )


def _fingerprint(value: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    return sha1(normalized.encode("utf-8")).hexdigest()


def _preview(value: str, limit: int = 120) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    return normalized[:limit]


def _prompt_hash(prompt_version: str, prompt_snapshot: PromptSnapshot | None) -> str:
    payload = {
        "prompt_version": prompt_version,
        "prompt_snapshot": _minimal_prompt_payload(prompt_snapshot),
    }
    return sha1(json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")).hexdigest()


def _minimal_prompt_payload(prompt_snapshot: PromptSnapshot | None) -> dict[str, Any]:
    if prompt_snapshot is None:
        return {}
    return {
        "task": prompt_snapshot.task,
        "query_original_hash": prompt_snapshot.query_original_hash,
        "query_clean_hash": prompt_snapshot.query_clean_hash,
        "confirmed_slot_keys": list(prompt_snapshot.confirmed_slot_keys),
        "coach_clarify_round": prompt_snapshot.coach_clarify_round,
        "coach_pending_slot": prompt_snapshot.coach_pending_slot,
        "profile_version_id": prompt_snapshot.profile_version_id,
        "evidence_item_count": prompt_snapshot.evidence_item_count,
    }
