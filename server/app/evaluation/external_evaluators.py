from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

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


@dataclass
class RagasEvaluationCase:
    case_id: str
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str
    domain: str
    trace_id: str


class RagasBackend(Protocol):
    backend_name: str
    model_name: str
    embedding_model_name: str
    is_ready: bool
    missing_dependencies: list[str]
    base_url: str | None

    def score_cases(self, cases: list[RagasEvaluationCase]) -> dict[str, RagasCaseScores]: ...


class LangChainRagasBackend:
    backend_name = "ragas_langchain_openai_v1"

    def __init__(
        self,
        runtime_config: RuntimeConfigSnapshot,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.runtime_config = runtime_config
        self.api_key = resolve_openai_api_key(api_key)
        self.base_url = base_url or resolve_openai_base_url()
        self.model_name = runtime_config.model_routing.base_model
        self.embedding_model_name = runtime_config.model_routing.embedding_model
        self.missing_dependencies = self._resolve_missing_dependencies()

    @property
    def is_ready(self) -> bool:
        return bool(self.api_key and not self.missing_dependencies)

    def score_cases(self, cases: list[RagasEvaluationCase]) -> dict[str, RagasCaseScores]:
        if not self.api_key:
            raise ExternalEvaluatorUnavailableError("missing_openai_api_key")
        if self.missing_dependencies:
            raise ExternalEvaluatorUnavailableError(
                "missing_dependencies:" + ",".join(self.missing_dependencies)
            )
        if not cases:
            return {}
        from datasets import Dataset
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

        llm = ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=0.0,
        )
        embeddings = OpenAIEmbeddings(
            model=self.embedding_model_name,
            api_key=self.api_key,
            base_url=self.base_url,
        )
        scores_by_case: dict[str, RagasCaseScores] = {}
        for case in cases:
            dataset = Dataset.from_list(
                [
                    {
                        "question": case.question,
                        "answer": case.answer,
                        "contexts": case.contexts,
                        "ground_truth": case.ground_truth,
                    }
                ]
            )
            result = evaluate(
                dataset=dataset,
                metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
                llm=llm,
                embeddings=embeddings,
            )
            scores_by_case[case.case_id] = RagasCaseScores(**_extract_ragas_row(result))
        return scores_by_case

    @staticmethod
    def _resolve_missing_dependencies() -> list[str]:
        missing: list[str] = []
        for module_name in ("datasets", "langchain_openai", "ragas"):
            try:
                __import__(module_name)
            except ImportError:
                missing.append(module_name)
        return missing


class RagasExternalEvaluator:
    evaluator_name = "ragas_external_v1"

    def __init__(
        self,
        runtime_config: RuntimeConfigSnapshot,
        backend: RagasBackend | None = None,
    ):
        self.runtime_config = runtime_config
        self.backend = backend or LangChainRagasBackend(runtime_config)

    @property
    def is_ready(self) -> bool:
        return bool(self.backend.is_ready)

    @property
    def missing_dependencies(self) -> list[str]:
        return list(getattr(self.backend, "missing_dependencies", []))

    @property
    def base_url(self) -> str | None:
        return getattr(self.backend, "base_url", None)

    def evaluate(self, golden_cases: list[GoldenCase], traces: list[TraceRecord]) -> EvalStageResult:
        trace_by_id = {trace.trace_id: trace for trace in traces}
        evaluation_cases = [
            _build_ragas_case(case, trace_by_id[case.trace_id])
            for case in golden_cases
            if case.trace_id and case.trace_id in trace_by_id
        ]
        if not evaluation_cases:
            return EvalStageResult(
                status=EvalStageStatus.SKIPPED,
                evaluator=self.evaluator_name,
                reason="no_matching_cases",
                sample_count=0,
            )
        scores_by_case = self.backend.score_cases(evaluation_cases)
        score_rows = [scores_by_case[case.case_id] for case in evaluation_cases if case.case_id in scores_by_case]
        if len(score_rows) != len(evaluation_cases):
            raise ExternalEvaluatorSchemaError("missing_ragas_case_scores")
        metrics = [
            EvalMetricValue(metric=EvalMetricName.FAITHFULNESS, value=_mean(score.faithfulness for score in score_rows)),
            EvalMetricValue(metric=EvalMetricName.ANSWER_RELEVANCY, value=_mean(score.answer_relevancy for score in score_rows)),
            EvalMetricValue(metric=EvalMetricName.CONTEXT_PRECISION, value=_mean(score.context_precision for score in score_rows)),
            EvalMetricValue(metric=EvalMetricName.CONTEXT_RECALL, value=_mean(score.context_recall for score in score_rows)),
        ]
        return EvalStageResult(
            status=EvalStageStatus.SUCCEEDED,
            evaluator=self.evaluator_name,
            sample_count=len(evaluation_cases),
            metrics=metrics,
            details={
                "model": self.backend.model_name,
                "embedding_model": self.backend.embedding_model_name,
                "backend_name": self.backend.backend_name,
                "prompt_version": "ragas.v1",
                "scored_cases": len(evaluation_cases),
            },
        )


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

    @property
    def is_ready(self) -> bool:
        return bool(self.api_key and self.transport is not None)

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


def _build_ragas_case(golden_case: GoldenCase, trace: TraceRecord) -> RagasEvaluationCase:
    return RagasEvaluationCase(
        case_id=golden_case.case_id,
        question=golden_case.query,
        answer=_render_output_text(trace.generation_log.output or {}),
        contexts=_build_ragas_contexts(golden_case, trace),
        ground_truth=_build_ground_truth(golden_case),
        domain=golden_case.domain,
        trace_id=trace.trace_id,
    )


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
        "contexts": _build_ragas_contexts(golden_case, trace),
        "validator_pass": (
            trace.generation_log.validator_report.validator_pass
            if trace.generation_log.validator_report is not None
            else None
        ),
    }


def _build_ragas_contexts(golden_case: GoldenCase, trace: TraceRecord) -> list[str]:
    domain = (golden_case.domain or trace.request_log.domain or "").upper()
    if domain == "NOTES":
        anchor_contexts = _note_anchor_contexts(trace)
        if anchor_contexts:
            return anchor_contexts
    return _bjj_or_generic_contexts(trace)


def _note_anchor_contexts(trace: TraceRecord) -> list[str]:
    output = trace.generation_log.output or {}
    anchors = output.get("anchors", [])
    contexts: list[str] = []
    if not isinstance(anchors, list):
        return contexts
    ordered = sorted(
        (anchor for anchor in anchors if isinstance(anchor, dict)),
        key=lambda anchor: (anchor.get("doc_rank", 99), anchor.get("citation", "")),
    )
    for anchor in ordered:
        anchor_type = anchor.get("anchor_type")
        content = anchor.get("content")
        citation = anchor.get("citation")
        if not isinstance(content, str) or not content.strip():
            continue
        if not isinstance(citation, str):
            citation = ""
        if anchor_type == "raw_excerpt":
            contexts.append(f"raw_excerpt {citation}: {content.strip()}")
        elif anchor_type == "safe_summary":
            contexts.append(f"safe_summary {citation}: {content.strip()}")
    return contexts[:3]


def _bjj_or_generic_contexts(trace: TraceRecord) -> list[str]:
    contexts: list[str] = []
    for item in trace.evidence_log.items:
        if item.safe_summary:
            contexts.append(f"safe_summary {item.doc_version_id}:{item.locator.line_range.start}: {item.safe_summary}")
        elif item.excerpt_snapshot:
            contexts.append(f"excerpt {item.doc_version_id}:{item.locator.line_range.start}: {item.excerpt_snapshot}")
    return contexts[:6]


def _build_ground_truth(golden_case: GoldenCase) -> str:
    parts: list[str] = []
    if golden_case.expected_behavior:
        parts.append(
            "expected_behavior="
            + json.dumps(golden_case.expected_behavior, ensure_ascii=False, sort_keys=True)
        )
    if golden_case.expected_chunk_ids:
        parts.append("expected_chunk_ids=" + ",".join(golden_case.expected_chunk_ids))
    return "\n".join(parts) if parts else golden_case.query


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


def _judge_prompt() -> str:
    return (
        "You are an external judge for retrieval-grounded answers. "
        "Return one JSON object with keys passed (boolean), score (float in [0,1]), and optional notes. "
        "Judge whether the answer satisfies the expected behavior using the query, answer text, citations, contexts, and validator status."
    )


def _extract_ragas_row(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_pandas"):
        frame = result.to_pandas()
        if hasattr(frame, "to_dict"):
            records = frame.to_dict(orient="records")
            if records:
                return records[0]
    if isinstance(result, dict):
        return result
    if hasattr(result, "scores"):
        scores = getattr(result, "scores")
        if isinstance(scores, list) and scores:
            first = scores[0]
            if isinstance(first, dict):
                return first
    raise ExternalEvaluatorSchemaError("invalid_ragas_result")


def _mean(values: Any) -> float:
    collected = list(values)
    return sum(collected) / len(collected) if collected else 0.0
