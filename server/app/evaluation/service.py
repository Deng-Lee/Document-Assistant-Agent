from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Any

from server.app.core import (
    EvalMetricName,
    EvalMetricValue,
    EvalRunRequest,
    EvalRunResult,
    EvalRunStatus,
    EvalStageResult,
    EvalStageStatus,
    GoldenCase,
    ModelVariant,
    TraceRecord,
    active_model_profile_name,
)
from server.app.storage import GoldenCaseRepository, TraceStore

from .loader import load_golden_cases
from .metrics import compute_eval_metrics


class EvaluationService:
    def __init__(
        self,
        trace_store: TraceStore,
        golden_case_repository: GoldenCaseRepository | None = None,
        repo_root: str | Path | None = None,
        replay_runner: Callable[[list[TraceRecord], ModelVariant, bool], list[TraceRecord]] | None = None,
        ragas_runner: Callable[[list[GoldenCase], list[TraceRecord]], EvalStageResult] | None = None,
        judge_runner: Callable[[list[GoldenCase], list[TraceRecord]], EvalStageResult] | None = None,
    ):
        self.trace_store = trace_store
        self.golden_case_repository = golden_case_repository
        self.repo_root = Path(repo_root).resolve() if repo_root is not None else None
        self.replay_runner = replay_runner
        self.ragas_runner = ragas_runner or self._run_ragas
        self.judge_runner = judge_runner or self._run_judge

    def run(self, request: EvalRunRequest, trace_ids: list[str] | None = None) -> EvalRunResult:
        golden_cases = self._load_golden_cases(request.eval_set_id)
        traces = self._load_traces(trace_ids, golden_cases)
        if request.model_variant != ModelVariant.BASE and self.replay_runner is not None:
            traces = self.replay_runner(traces, request.model_variant, request.use_frozen_evidence)
        metrics, failures, latency_summary, cost_summary = compute_eval_metrics(traces)
        ragas = self.ragas_runner(golden_cases, traces)
        judge = self.judge_runner(golden_cases, traces)
        metrics.extend(ragas.metrics)
        run_status = EvalRunStatus.PARTIAL if any(stage.status == EvalStageStatus.FAILED for stage in (ragas, judge)) else EvalRunStatus.COMPLETED
        result = EvalRunResult(
            eval_run_id=_eval_run_id(request.eval_set_id, request.model_variant),
            eval_set_id=request.eval_set_id,
            model_variant=request.model_variant,
            created_at=datetime.utcnow(),
            run_status=run_status,
            golden_case_count=len(golden_cases),
            source_trace_ids=[trace.trace_id for trace in traces],
            metrics=metrics,
            failures=failures,
            latency_summary=latency_summary,
            cost_summary=cost_summary,
            ragas=ragas,
            judge=judge,
        )
        if self.golden_case_repository is not None:
            self.golden_case_repository.record_eval_run(result)
        return result

    def list_results(self) -> list[EvalRunResult]:
        if self.golden_case_repository is None:
            return []
        return self.golden_case_repository.list_eval_runs()

    def _load_traces(self, trace_ids: list[str] | None = None, golden_cases: list[GoldenCase] | None = None) -> list[TraceRecord]:
        selected_ids = trace_ids or [case.trace_id for case in (golden_cases or []) if case.trace_id] or self.trace_store.list_trace_ids()
        return [self.trace_store.read_trace(trace_id) for trace_id in selected_ids]

    def _load_golden_cases(self, eval_set_id: str) -> list[GoldenCase]:
        if self.repo_root is None:
            return []
        cases = load_golden_cases(self.repo_root, eval_set_id)
        if self.golden_case_repository is not None:
            for case in cases:
                self.golden_case_repository.upsert_golden_case(case)
        return cases

    def _run_ragas(self, golden_cases: list[GoldenCase], traces: list[TraceRecord]) -> EvalStageResult:
        profile = active_model_profile_name()
        if profile != "real":
            return EvalStageResult(
                status=EvalStageStatus.SKIPPED,
                evaluator="surrogate_ragas_v1",
                reason="not_enabled_for_profile",
                sample_count=len(traces),
            )
        if not traces:
            return EvalStageResult(
                status=EvalStageStatus.SKIPPED,
                evaluator="surrogate_ragas_v1",
                reason="no_traces",
                sample_count=0,
            )
        trace_by_id = {trace.trace_id: trace for trace in traces}
        faithfulness: list[float] = []
        answer_relevancy: list[float] = []
        context_precision: list[float] = []
        context_recall: list[float] = []
        for case in golden_cases or []:
            trace = trace_by_id.get(case.trace_id or "")
            if trace is None:
                continue
            output = trace.generation_log.output or {}
            citations = set(output.get("citations", []) or [])
            evidence_ids = {item.evidence_id for item in trace.evidence_log.items}
            expected_ids = set(case.expected_chunk_ids)
            faithfulness.append(1.0 if citations.issubset(evidence_ids) else 0.0)
            answer_relevancy.append(_lexical_overlap(case.query, _output_text(output)))
            context_precision.append(_precision(evidence_ids, expected_ids))
            context_recall.append(_recall(evidence_ids, expected_ids))
        metric_values = [
            EvalMetricValue(metric=EvalMetricName.FAITHFULNESS, value=_mean_or_zero(faithfulness)),
            EvalMetricValue(metric=EvalMetricName.ANSWER_RELEVANCY, value=_mean_or_zero(answer_relevancy)),
            EvalMetricValue(metric=EvalMetricName.CONTEXT_PRECISION, value=_mean_or_zero(context_precision)),
            EvalMetricValue(metric=EvalMetricName.CONTEXT_RECALL, value=_mean_or_zero(context_recall)),
        ]
        return EvalStageResult(
            status=EvalStageStatus.SUCCEEDED,
            evaluator="surrogate_ragas_v1",
            sample_count=len(traces),
            metrics=metric_values,
            details={"golden_cases_with_trace": sum(1 for case in golden_cases if case.trace_id)},
        )

    def _run_judge(self, golden_cases: list[GoldenCase], traces: list[TraceRecord]) -> EvalStageResult:
        profile = active_model_profile_name()
        if profile != "real":
            return EvalStageResult(
                status=EvalStageStatus.SKIPPED,
                evaluator="heuristic_judge_v1",
                reason="not_enabled_for_profile",
                sample_count=len(traces),
            )
        if not golden_cases:
            return EvalStageResult(
                status=EvalStageStatus.SKIPPED,
                evaluator="heuristic_judge_v1",
                reason="no_golden_cases",
                sample_count=0,
            )
        trace_by_id = {trace.trace_id: trace for trace in traces}
        judged = 0
        passed = 0
        for case in golden_cases:
            trace = trace_by_id.get(case.trace_id or "")
            if trace is None:
                continue
            judged += 1
            if _judge_case(case, trace):
                passed += 1
        return EvalStageResult(
            status=EvalStageStatus.SUCCEEDED,
            evaluator="heuristic_judge_v1",
            sample_count=judged,
            details={
                "passed": passed,
                "failed": max(judged - passed, 0),
                "score": (passed / judged) if judged else 0.0,
            },
        )


def _eval_run_id(eval_set_id: str, model_variant: ModelVariant) -> str:
    payload = f"{eval_set_id}:{model_variant.value}:{datetime.utcnow().isoformat()}"
    return f"eval_{sha1(payload.encode('utf-8')).hexdigest()[:12]}"


def _output_text(output: dict[str, Any]) -> str:
    if "text" in output and isinstance(output["text"], str):
        return output["text"]
    fragments: list[str] = []
    for key in ("caveats", "citations"):
        value = output.get(key, [])
        if isinstance(value, list):
            fragments.extend(str(item) for item in value)
    return " ".join(fragments)


def _tokenize(text: str) -> set[str]:
    return {token.strip().lower() for token in text.replace(":", " ").replace("/", " ").split() if token.strip()}


def _lexical_overlap(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


def _precision(actual: set[str], expected: set[str]) -> float:
    if not actual:
        return 0.0 if expected else 1.0
    if not expected:
        return 1.0
    return len(actual & expected) / len(actual)


def _recall(actual: set[str], expected: set[str]) -> float:
    if not expected:
        return 1.0
    return len(actual & expected) / len(expected)


def _mean_or_zero(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _judge_case(case: GoldenCase, trace: TraceRecord) -> bool:
    output = trace.generation_log.output or {}
    expected = case.expected_behavior or {}
    if expected.get("required_mode") and output.get("mode") != expected["required_mode"]:
        return False
    required_terms = expected.get("response_contains", []) or []
    rendered = _output_text(output).lower()
    if any(term.lower() not in rendered for term in required_terms):
        return False
    min_citations = int(expected.get("min_citation_count", 0) or 0)
    citations = output.get("citations", []) or []
    return len(citations) >= min_citations
