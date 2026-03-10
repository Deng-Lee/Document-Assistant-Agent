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
    RuntimeConfigSnapshot,
    TraceRecord,
    active_model_profile_name,
    build_runtime_config,
)
from server.app.storage import GoldenCaseRepository, TraceStore

from .external_evaluators import (
    ExternalEvaluatorError,
    ExternalEvaluatorSchemaError,
    ExternalEvaluatorUnavailableError,
    OpenAIExternalJudgeEvaluator,
    OpenAIExternalRagasEvaluator,
)
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
        runtime_config: RuntimeConfigSnapshot | None = None,
        ragas_evaluator: OpenAIExternalRagasEvaluator | None = None,
        judge_evaluator: OpenAIExternalJudgeEvaluator | None = None,
    ):
        self.trace_store = trace_store
        self.golden_case_repository = golden_case_repository
        self.repo_root = Path(repo_root).resolve() if repo_root is not None else None
        self.replay_runner = replay_runner
        self.runtime_config = runtime_config or build_runtime_config()
        self.ragas_evaluator = ragas_evaluator or OpenAIExternalRagasEvaluator(self.runtime_config)
        self.judge_evaluator = judge_evaluator or OpenAIExternalJudgeEvaluator(self.runtime_config)
        self.ragas_runner = ragas_runner or self._run_ragas
        self.judge_runner = judge_runner or self._run_judge

    def provider_status(self) -> dict[str, dict[str, object]]:
        return {
            "ragas": _provider_status(self.runtime_config, self.ragas_evaluator),
            "judge": _provider_status(self.runtime_config, self.judge_evaluator),
        }

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
                evaluator=self.ragas_evaluator.evaluator_name,
                reason="no_traces",
                sample_count=0,
            )
        try:
            return self.ragas_evaluator.evaluate(golden_cases, traces)
        except ExternalEvaluatorUnavailableError as exc:
            return EvalStageResult(
                status=EvalStageStatus.FAILED,
                evaluator=self.ragas_evaluator.evaluator_name,
                reason=str(exc),
                sample_count=len(traces),
            )
        except ExternalEvaluatorSchemaError as exc:
            return EvalStageResult(
                status=EvalStageStatus.FAILED,
                evaluator=self.ragas_evaluator.evaluator_name,
                reason=str(exc),
                sample_count=len(traces),
            )
        except ExternalEvaluatorError as exc:
            return EvalStageResult(
                status=EvalStageStatus.FAILED,
                evaluator=self.ragas_evaluator.evaluator_name,
                reason=str(exc),
                sample_count=len(traces),
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
                evaluator=self.judge_evaluator.evaluator_name,
                reason="no_golden_cases",
                sample_count=0,
            )
        try:
            return self.judge_evaluator.evaluate(golden_cases, traces)
        except ExternalEvaluatorUnavailableError as exc:
            return EvalStageResult(
                status=EvalStageStatus.FAILED,
                evaluator=self.judge_evaluator.evaluator_name,
                reason=str(exc),
                sample_count=len(traces),
            )
        except ExternalEvaluatorSchemaError as exc:
            return EvalStageResult(
                status=EvalStageStatus.FAILED,
                evaluator=self.judge_evaluator.evaluator_name,
                reason=str(exc),
                sample_count=len(traces),
            )
        except ExternalEvaluatorError as exc:
            return EvalStageResult(
                status=EvalStageStatus.FAILED,
                evaluator=self.judge_evaluator.evaluator_name,
                reason=str(exc),
                sample_count=len(traces),
            )


def _eval_run_id(eval_set_id: str, model_variant: ModelVariant) -> str:
    payload = f"{eval_set_id}:{model_variant.value}:{datetime.utcnow().isoformat()}"
    return f"eval_{sha1(payload.encode('utf-8')).hexdigest()[:12]}"


def _provider_status(runtime_config: RuntimeConfigSnapshot, evaluator: object) -> dict[str, object]:
    transport = getattr(evaluator, "transport", None)
    return {
        "profile_name": runtime_config.model_routing.profile_name,
        "evaluator_name": getattr(evaluator, "evaluator_name", evaluator.__class__.__name__),
        "configured": bool(getattr(evaluator, "is_ready", False)),
        "base_url": getattr(transport, "base_url", None),
    }
