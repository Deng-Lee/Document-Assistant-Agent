from __future__ import annotations

import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from server.tests.support import activate_test_profile, make_trace_record


class EvaluationAndSFTTests(unittest.TestCase):
    def setUp(self) -> None:
        activate_test_profile("fake")

    def test_evaluation_service_records_failures_and_summaries(self) -> None:
        with TemporaryDirectory() as tmp:
            trace_store, eval_repo = _build_eval_stack(tmp)

            good_trace = make_trace_record(
                trace_id="trace_good",
                latency_ms=120,
                cost_estimate=0.02,
            )
            bad_trace = make_trace_record(
                trace_id="trace_bad",
                latency_ms=260,
                cost_estimate=0.06,
            )
            bad_output = dict(bad_trace.generation_log.output)
            bad_output["citations"] = ["not_allowed"]
            bad_output["drills"] = [{"name": "broken drill"}]
            bad_trace.generation_log.output = bad_output

            trace_store.write_trace(good_trace)
            trace_store.write_trace(bad_trace)
            _write_golden_set(
                tmp,
                "eval_suite",
                [
                    {
                        "case_id": "case_good",
                        "query": "turtle escape",
                        "domain": "BJJ",
                        "trace_id": "trace_good",
                        "expected_behavior": {"required_mode": "FULL", "min_citation_count": 1},
                        "expected_chunk_ids": ["chunk_1"],
                    },
                    {
                        "case_id": "case_bad",
                        "query": "turtle escape",
                        "domain": "BJJ",
                        "trace_id": "trace_bad",
                        "expected_behavior": {"required_mode": "FULL", "min_citation_count": 1},
                        "expected_chunk_ids": ["chunk_1"],
                    },
                ],
            )

            from server.app.core import EvalMetricName, EvalRunRequest
            from server.app.evaluation import EvaluationService

            result = EvaluationService(trace_store=trace_store, golden_case_repository=eval_repo, repo_root=tmp).run(
                EvalRunRequest(eval_set_id="eval_suite")
            )

            metrics = {metric.metric.value: metric.value for metric in result.metrics}
            self.assertIn(EvalMetricName.ALLOWED_CITATION_ACCURACY.value, metrics)
            self.assertLess(metrics[EvalMetricName.ALLOWED_CITATION_ACCURACY.value], 1.0)
            self.assertEqual(result.latency_summary.sample_count, 2)
            self.assertEqual(result.cost_summary.sample_count, 2)
            self.assertEqual(len(result.failures), 1)
            self.assertIn("CITATION_OUT_OF_ALLOWED_SET", result.failures[0].failure_tags)
            self.assertEqual(result.run_status.value, "completed")
            self.assertEqual(result.ragas.status.value, "skipped")
            self.assertEqual(result.judge.status.value, "skipped")
            self.assertEqual(result.golden_case_count, 2)
            self.assertEqual(len(eval_repo.list_golden_cases()), 2)
            self.assertTrue(eval_repo.list_eval_runs())

    def test_evaluation_real_profile_degrades_judge_failures_to_partial(self) -> None:
        with TemporaryDirectory() as tmp:
            activate_test_profile("real")
            trace_store, eval_repo = _build_eval_stack(tmp)
            trace_store.write_trace(make_trace_record(trace_id="trace_real"))
            _write_golden_set(
                tmp,
                "real_suite",
                [
                    {
                        "case_id": "case_real",
                        "query": "turtle escape",
                        "domain": "BJJ",
                        "trace_id": "trace_real",
                        "expected_behavior": {"required_mode": "FULL"},
                        "expected_chunk_ids": ["chunk_1"],
                    }
                ],
            )

            from server.app.core import EvalRunRequest, EvalStageResult, EvalStageStatus
            from server.app.evaluation import EvaluationService

            service = EvaluationService(
                trace_store=trace_store,
                golden_case_repository=eval_repo,
                repo_root=tmp,
                judge_runner=lambda cases, traces: EvalStageResult(
                    status=EvalStageStatus.FAILED,
                    evaluator="heuristic_judge_v1",
                    reason="judge_backend_error",
                    sample_count=len(traces),
                ),
            )
            result = service.run(EvalRunRequest(eval_set_id="real_suite"))

            self.assertEqual(result.run_status.value, "partial")
            self.assertEqual(result.ragas.status.value, "succeeded")
            self.assertEqual(result.judge.status.value, "failed")
            self.assertEqual(result.judge.reason, "judge_backend_error")
            self.assertTrue(any(metric.metric.value == "faithfulness" for metric in result.metrics))

    def test_sft_export_filters_and_builds_train_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            trace_store, _eval_repo = _build_eval_stack(tmp)

            keep_trace = make_trace_record(trace_id="trace_keep")
            drop_trace = make_trace_record(trace_id="trace_drop")
            drop_output = dict(drop_trace.generation_log.output)
            drop_output["reasoning_status"] = dict(drop_output["reasoning_status"])
            drop_output["reasoning_status"]["gate_label"] = "LOW_EVIDENCE"
            drop_trace.generation_log.output = drop_output
            drop_trace.generation_log.validator_report.validator_pass = False

            trace_store.write_trace(keep_trace)
            trace_store.write_trace(drop_trace)

            from server.app.core import ModelVariant, SFTExportRequest, build_runtime_config
            from server.app.sft import SFTService

            service = SFTService(trace_store=trace_store)
            export_dir = f"{tmp}/datasets/sft/v1/test_suite"
            manifest, samples = service.export_dataset(
                request=SFTExportRequest(trace_filter={"gate_label": "HIGH_EVIDENCE"}),
                output_dir=export_dir,
            )

            self.assertEqual(manifest.sample_count, 1)
            self.assertEqual(samples[0].trace_id, "trace_keep")

            train_path = service.build_train_rows(samples, f"{export_dir}/train.jsonl")
            rows = [json.loads(line) for line in train_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["trace_id"], "trace_keep")

            checkpoint = service.register_policy_checkpoint(
                output_dir=f"{tmp}/policy_ckpt",
                base_model=build_runtime_config().model_routing.base_model,
                dataset_manifest=manifest,
            )
            self.assertTrue(checkpoint.policy_model_ref.startswith("policy://"))
            self.assertEqual(
                service.resolve_model_for_variant(build_runtime_config(), ModelVariant.POLICY, checkpoint),
                checkpoint.policy_model_ref,
            )


def _build_eval_stack(root: str):
    from server.app.storage import JSONTraceStore, SQLiteGoldenCaseRepository, SQLiteStore

    store = SQLiteStore(f"{root}/sqlite/app.db")
    store.init_schema()
    return JSONTraceStore(f"{root}/traces"), SQLiteGoldenCaseRepository(store)


def _write_golden_set(root: str, eval_set_id: str, cases: list[dict]) -> None:
    target = Path(root) / "datasets" / "golden" / f"{eval_set_id}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n",
        encoding="utf-8",
    )
