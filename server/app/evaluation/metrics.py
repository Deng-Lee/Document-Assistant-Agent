from __future__ import annotations

from statistics import median

from server.app.core import (
    BJJAmbiguousFinalAnswer,
    BJJFullAnswer,
    BJJLowEvidenceAnswer,
    EvalFailure,
    EvalMetricName,
    EvalMetricValue,
    EvalSummary,
    TraceRecord,
)


def compute_eval_metrics(traces: list[TraceRecord]) -> tuple[list[EvalMetricValue], list[EvalFailure], EvalSummary | None, EvalSummary | None]:
    total = len(traces)
    if total == 0:
        return [], [], EvalSummary(sample_count=0), EvalSummary(sample_count=0)

    schema_pass = 0
    mode_policy_pass = 0
    allowed_citation_pass = 0
    citation_coverage_values: list[float] = []
    plan_c_branch_pass = 0
    drill_completeness_pass = 0
    low_evidence_safe_pass = 0
    failures: list[EvalFailure] = []
    latencies: list[float] = []
    costs: list[float] = []

    for trace in traces:
        trace_failures: list[str] = []
        output = trace.generation_log.output or {}
        validator_report = trace.generation_log.validator_report
        evidence_ids = {item.evidence_id for item in trace.evidence_log.items}

        if trace.generation_log.latency_ms is not None:
            latencies.append(float(trace.generation_log.latency_ms))
        if trace.generation_log.cost_estimate is not None:
            costs.append(float(trace.generation_log.cost_estimate))

        if validator_report is not None and validator_report.validator_pass:
            schema_pass += 1
        elif _is_notes_output(output):
            schema_pass += 1
        else:
            trace_failures.append("SCHEMA_INVALID")

        if _mode_policy_consistent(output):
            mode_policy_pass += 1
        else:
            trace_failures.append("MODE_POLICY_INCONSISTENT")

        allowed_ok = _allowed_citation_accuracy(output, evidence_ids)
        if allowed_ok:
            allowed_citation_pass += 1
        else:
            trace_failures.append("CITATION_OUT_OF_ALLOWED_SET")

        citation_coverage = _citation_coverage(output)
        citation_coverage_values.append(citation_coverage)
        if citation_coverage < 1.0 and not _is_notes_output(output):
            trace_failures.append("CITATION_COVERAGE_PARTIAL")

        if _plan_c_branch_count_ok(output):
            plan_c_branch_pass += 1
        elif _requires_branch_metric(output):
            trace_failures.append("PLAN_C_BRANCH_COUNT_LOW")

        if _drill_completeness_ok(output):
            drill_completeness_pass += 1
        elif _requires_drill_metric(output):
            trace_failures.append("DRILL_INCOMPLETE")

        if _low_evidence_safe(output):
            low_evidence_safe_pass += 1
        else:
            trace_failures.append("LOW_EVIDENCE_UNSAFE")

        if trace_failures:
            failures.append(EvalFailure(trace_id=trace.trace_id, failure_tags=trace_failures))

    metrics = [
        EvalMetricValue(metric=EvalMetricName.SCHEMA_COMPLIANCE, value=schema_pass / total),
        EvalMetricValue(metric=EvalMetricName.MODE_POLICY_CONSISTENCY, value=mode_policy_pass / total),
        EvalMetricValue(metric=EvalMetricName.ALLOWED_CITATION_ACCURACY, value=allowed_citation_pass / total),
        EvalMetricValue(metric=EvalMetricName.CITATION_COVERAGE, value=sum(citation_coverage_values) / total),
        EvalMetricValue(metric=EvalMetricName.PLAN_C_BRANCH_COUNT, value=plan_c_branch_pass / total),
        EvalMetricValue(metric=EvalMetricName.DRILL_COMPLETENESS, value=drill_completeness_pass / total),
        EvalMetricValue(metric=EvalMetricName.LOW_EVIDENCE_SAFETY, value=low_evidence_safe_pass / total),
    ]
    return metrics, failures, _build_summary(latencies), _build_summary(costs)


def _mode_policy_consistent(output: dict) -> bool:
    reasoning = output.get("reasoning_status", {})
    gate_label = reasoning.get("gate_label")
    mode = output.get("mode")
    if not gate_label or not mode:
        return _is_notes_output(output)
    mapping = {
        "HIGH_EVIDENCE": "FULL",
        "AMBIGUOUS": "AMBIGUOUS_FINAL",
        "LOW_EVIDENCE": "LOW_EVIDENCE",
    }
    return mapping.get(gate_label) == mode


def _allowed_citation_accuracy(output: dict, evidence_ids: set[str]) -> bool:
    citations = [value for value in output.get("citations", []) if isinstance(value, str)]
    return all(citation in evidence_ids for citation in citations)


def _citation_coverage(output: dict) -> float:
    used_ids = set()
    total_citable = 0
    for key in ("observations", "mistakes", "drills"):
        for item in output.get(key, []) or []:
            if isinstance(item, dict):
                total_citable += 1
                used_ids.update(item.get("evidence_ids", []) or [])

    plans = output.get("plans", {}) or {}
    for key in ("A_baseline", "B_offense"):
        plan = plans.get(key)
        if isinstance(plan, dict) and not plan.get("generic", False):
            total_citable += 1
            used_ids.update(plan.get("evidence_ids", []) or [])
    for branch in (plans.get("C_branch", {}) or {}).get("branches", []) or []:
        if isinstance(branch, dict) and not branch.get("generic", False):
            total_citable += 1
            used_ids.update(branch.get("evidence_ids", []) or [])

    if total_citable == 0:
        return 1.0
    return 1.0 if used_ids else 0.0


def _plan_c_branch_count_ok(output: dict) -> bool:
    plans = output.get("plans", {}) or {}
    branches = (plans.get("C_branch", {}) or {}).get("branches", []) or []
    if not _requires_branch_metric(output):
        return True
    return len(branches) >= 2


def _requires_branch_metric(output: dict) -> bool:
    return output.get("mode") in {"FULL", "AMBIGUOUS_FINAL"}


def _drill_completeness_ok(output: dict) -> bool:
    drills = output.get("drills", []) or []
    if not _requires_drill_metric(output):
        return True
    if not drills:
        return False
    for drill in drills:
        if not isinstance(drill, dict):
            return False
        if not drill.get("dosage") or not drill.get("constraints") or not drill.get("success_criteria"):
            return False
    return True


def _requires_drill_metric(output: dict) -> bool:
    return output.get("mode") in {"FULL", "AMBIGUOUS_FINAL"}


def _low_evidence_safe(output: dict) -> bool:
    if output.get("mode") != "LOW_EVIDENCE":
        return True
    risky_terms = ("submission", "armbar", "triangle", "heel hook", "kneebar", "降服")
    text_fragments: list[str] = []
    for value in output.get("caveats", []) or []:
        if isinstance(value, str):
            text_fragments.append(value.lower())
    for plan_key in ("A_baseline", "B_offense"):
        plan = (output.get("plans", {}) or {}).get(plan_key, {}) or {}
        for step in plan.get("steps", []) or []:
            if isinstance(step, str):
                text_fragments.append(step.lower())
    full_text = " ".join(text_fragments)
    return not any(term.lower() in full_text for term in risky_terms)


def _is_notes_output(output: dict) -> bool:
    return isinstance(output, dict) and "anchors" in output and "mode" not in output


def _build_summary(values: list[float]) -> EvalSummary | None:
    if not values:
        return EvalSummary(sample_count=0)
    ordered = sorted(values)
    return EvalSummary(
        sample_count=len(ordered),
        p50=median(ordered),
        p95=ordered[int(0.95 * (len(ordered) - 1))],
        min=ordered[0],
        max=ordered[-1],
    )
