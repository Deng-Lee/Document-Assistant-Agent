from __future__ import annotations

import json
from typing import Any

from pydantic import Field, ValidationError

from server.app.core import (
    EvalMetricName,
    EvalMetricValue,
    EvalStageResult,
    EvalStageStatus,
    GoldenCase,
    PDABaseModel,
    RuntimeConfigSnapshot,
    TraceRecord,
)
from server.app.core.openai_chat import (
    ChatCompletionTransport,
    OpenAIChatCompletionTransport,
    OpenAITransportError,
    extract_chat_completion_text,
    resolve_openai_api_key,
    resolve_openai_base_url,
)


class ExternalEvaluatorError(RuntimeError):
    pass


class ExternalEvaluatorUnavailableError(RuntimeError):
    pass


class ExternalEvaluatorSchemaError(RuntimeError):
    pass


class RagasCaseScores(PDABaseModel):
    faithfulness: float = Field(..., ge=0.0, le=1.0)
    answer_relevancy: float = Field(..., ge=0.0, le=1.0)
    context_precision: float = Field(..., ge=0.0, le=1.0)
    context_recall: float = Field(..., ge=0.0, le=1.0)
    notes: str | None = None


class JudgeCaseScore(PDABaseModel):
    passed: bool
    score: float = Field(..., ge=0.0, le=1.0)
    notes: str | None = None


class OpenAIExternalRagasEvaluator:
    evaluator_name = "openai_ragas_proxy_v1"

    def __init__(
        self,
        runtime_config: RuntimeConfigSnapshot,
        api_key: str | None = None,
        transport: ChatCompletionTransport | None = None,
    ):
        self.runtime_config = runtime_config
        self.api_key = resolve_openai_api_key(api_key)
        self.transport = transport or (
            OpenAIChatCompletionTransport(
                api_key=self.api_key,
                base_url=resolve_openai_base_url(),
            )
            if self.api_key
            else None
        )

    def evaluate(self, golden_cases: list[GoldenCase], traces: list[TraceRecord]) -> EvalStageResult:
        if not self.api_key or self.transport is None:
            raise ExternalEvaluatorUnavailableError("missing_openai_api_key")
        trace_by_id = {trace.trace_id: trace for trace in traces}
        case_scores: list[RagasCaseScores] = []
        case_count = 0
        for case in golden_cases:
            trace = trace_by_id.get(case.trace_id or "")
            if trace is None:
                continue
            case_count += 1
            case_scores.append(self._evaluate_case(case, trace))
        metrics = [
            EvalMetricValue(metric=EvalMetricName.FAITHFULNESS, value=_mean(score.faithfulness for score in case_scores)),
            EvalMetricValue(metric=EvalMetricName.ANSWER_RELEVANCY, value=_mean(score.answer_relevancy for score in case_scores)),
            EvalMetricValue(metric=EvalMetricName.CONTEXT_PRECISION, value=_mean(score.context_precision for score in case_scores)),
            EvalMetricValue(metric=EvalMetricName.CONTEXT_RECALL, value=_mean(score.context_recall for score in case_scores)),
        ]
        return EvalStageResult(
            status=EvalStageStatus.SUCCEEDED,
            evaluator=self.evaluator_name,
            sample_count=case_count,
            metrics=metrics,
            details={
                "model": self.runtime_config.model_routing.base_model,
                "prompt_version": "eval_ragas.v1",
                "scored_cases": case_count,
            },
        )

    def _evaluate_case(self, golden_case: GoldenCase, trace: TraceRecord) -> RagasCaseScores:
        payload = _build_case_payload(golden_case, trace)
        response = _chat_json_request(
            transport=self.transport,
            model=self.runtime_config.model_routing.base_model,
            prompt=_ragas_prompt(),
            payload=payload,
            generation_config=self.runtime_config.generation.replan,
        )
        try:
            return RagasCaseScores(**response)
        except ValidationError as exc:
            raise ExternalEvaluatorSchemaError("invalid_ragas_schema") from exc


class OpenAIExternalJudgeEvaluator:
    evaluator_name = "openai_judge_v1"

    def __init__(
        self,
        runtime_config: RuntimeConfigSnapshot,
        api_key: str | None = None,
        transport: ChatCompletionTransport | None = None,
    ):
        self.runtime_config = runtime_config
        self.api_key = resolve_openai_api_key(api_key)
        self.transport = transport or (
            OpenAIChatCompletionTransport(
                api_key=self.api_key,
                base_url=resolve_openai_base_url(),
            )
            if self.api_key
            else None
        )

    def evaluate(self, golden_cases: list[GoldenCase], traces: list[TraceRecord]) -> EvalStageResult:
        if not self.api_key or self.transport is None:
            raise ExternalEvaluatorUnavailableError("missing_openai_api_key")
        trace_by_id = {trace.trace_id: trace for trace in traces}
        results: list[JudgeCaseScore] = []
        judged = 0
        for case in golden_cases:
            trace = trace_by_id.get(case.trace_id or "")
            if trace is None:
                continue
            judged += 1
            results.append(self._evaluate_case(case, trace))
        passed = sum(1 for item in results if item.passed)
        average_score = _mean(item.score for item in results)
        return EvalStageResult(
            status=EvalStageStatus.SUCCEEDED,
            evaluator=self.evaluator_name,
            sample_count=judged,
            details={
                "model": self.runtime_config.model_routing.base_model,
                "prompt_version": "eval_judge.v1",
                "passed": passed,
                "failed": max(judged - passed, 0),
                "score": average_score,
            },
        )

    def _evaluate_case(self, golden_case: GoldenCase, trace: TraceRecord) -> JudgeCaseScore:
        payload = _build_case_payload(golden_case, trace)
        response = _chat_json_request(
            transport=self.transport,
            model=self.runtime_config.model_routing.base_model,
            prompt=_judge_prompt(),
            payload=payload,
            generation_config=self.runtime_config.generation.replan,
        )
        try:
            return JudgeCaseScore(**response)
        except ValidationError as exc:
            raise ExternalEvaluatorSchemaError("invalid_judge_schema") from exc


def _chat_json_request(
    *,
    transport: ChatCompletionTransport,
    model: str,
    prompt: str,
    payload: dict[str, Any],
    generation_config: dict[str, float | int],
) -> dict[str, Any]:
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "temperature": generation_config.get("temperature", 0.1),
        "top_p": generation_config.get("top_p", 1.0),
        "max_tokens": generation_config.get("max_tokens", 800),
        "response_format": {"type": "json_object"},
    }
    try:
        response = transport.create_chat_completion(request_payload)
        content = extract_chat_completion_text(response)
    except OpenAITransportError as exc:
        raise ExternalEvaluatorError(str(exc)) from exc
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ExternalEvaluatorSchemaError("invalid_json_response") from exc
    if not isinstance(payload, dict):
        raise ExternalEvaluatorSchemaError("json_object_required")
    return payload


def _build_case_payload(golden_case: GoldenCase, trace: TraceRecord) -> dict[str, Any]:
    output = trace.generation_log.output or {}
    return {
        "case_id": golden_case.case_id,
        "query": golden_case.query,
        "domain": golden_case.domain,
        "expected_behavior": golden_case.expected_behavior,
        "expected_chunk_ids": list(golden_case.expected_chunk_ids),
        "trace_id": trace.trace_id,
        "answer_text": _render_output_text(output),
        "citations": list(output.get("citations", []) or []),
        "evidence_ids": [item.evidence_id for item in trace.evidence_log.items],
        "evidence_summaries": [item.safe_summary for item in trace.evidence_log.items],
        "validator_pass": (
            trace.generation_log.validator_report.validator_pass
            if trace.generation_log.validator_report is not None
            else None
        ),
    }


def _render_output_text(output: dict[str, Any]) -> str:
    if "text" in output and isinstance(output["text"], str):
        return output["text"]
    fragments: list[str] = []
    for key in ("caveats", "citations"):
        value = output.get(key, [])
        if isinstance(value, list):
            fragments.extend(str(item) for item in value)
    observations = output.get("observations", [])
    if isinstance(observations, list):
        for item in observations:
            if isinstance(item, dict) and item.get("text"):
                fragments.append(str(item["text"]))
    return " ".join(fragment for fragment in fragments if fragment).strip()


def _ragas_prompt() -> str:
    return (
        "You are an external evaluator. "
        "Return one JSON object with float keys faithfulness, answer_relevancy, context_precision, context_recall in [0,1], plus optional notes. "
        "Use the query, expected chunk ids, citations, evidence ids, evidence summaries, and answer text to score the response."
    )


def _judge_prompt() -> str:
    return (
        "You are an external judge for retrieval-grounded answers. "
        "Return one JSON object with keys passed (boolean), score (float in [0,1]), and optional notes. "
        "Judge whether the answer satisfies the expected behavior using the query, answer text, citations, evidence ids, and validator status."
    )


def _mean(values: Any) -> float:
    collected = list(values)
    return sum(collected) / len(collected) if collected else 0.0
