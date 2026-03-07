from __future__ import annotations

from datetime import datetime
from hashlib import sha1
from typing import Iterable

from server.app.core import EvalRunRequest, EvalRunResult, ModelVariant, TraceRecord
from server.app.storage import GoldenCaseRepository, TraceStore

from .metrics import compute_eval_metrics


class EvaluationService:
    def __init__(self, trace_store: TraceStore, golden_case_repository: GoldenCaseRepository | None = None):
        self.trace_store = trace_store
        self.golden_case_repository = golden_case_repository

    def run(self, request: EvalRunRequest, trace_ids: list[str] | None = None) -> EvalRunResult:
        traces = self._load_traces(trace_ids)
        metrics, failures, latency_summary, cost_summary = compute_eval_metrics(traces)
        result = EvalRunResult(
            eval_run_id=_eval_run_id(request.eval_set_id, request.model_variant),
            eval_set_id=request.eval_set_id,
            model_variant=request.model_variant,
            created_at=datetime.utcnow(),
            metrics=metrics,
            failures=failures,
            latency_summary=latency_summary,
            cost_summary=cost_summary,
        )
        if self.golden_case_repository is not None:
            self.golden_case_repository.record_eval_run(result)
        return result

    def list_results(self) -> list[EvalRunResult]:
        if self.golden_case_repository is None:
            return []
        return self.golden_case_repository.list_eval_runs()

    def _load_traces(self, trace_ids: list[str] | None = None) -> list[TraceRecord]:
        selected_ids = trace_ids or self.trace_store.list_trace_ids()
        return [self.trace_store.read_trace(trace_id) for trace_id in selected_ids]


def _eval_run_id(eval_set_id: str, model_variant: ModelVariant) -> str:
    payload = f"{eval_set_id}:{model_variant.value}:{datetime.utcnow().isoformat()}"
    return f"eval_{sha1(payload.encode('utf-8')).hexdigest()[:12]}"
