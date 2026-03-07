from __future__ import annotations

import json
import unittest
from tempfile import TemporaryDirectory

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

            from server.app.core import EvalMetricName, EvalRunRequest
            from server.app.evaluation import EvaluationService

            result = EvaluationService(trace_store=trace_store, golden_case_repository=eval_repo).run(
                EvalRunRequest(eval_set_id="eval_suite")
            )

            metrics = {metric.metric.value: metric.value for metric in result.metrics}
            self.assertIn(EvalMetricName.ALLOWED_CITATION_ACCURACY.value, metrics)
            self.assertLess(metrics[EvalMetricName.ALLOWED_CITATION_ACCURACY.value], 1.0)
            self.assertEqual(result.latency_summary.sample_count, 2)
            self.assertEqual(result.cost_summary.sample_count, 2)
            self.assertEqual(len(result.failures), 1)
            self.assertIn("CITATION_OUT_OF_ALLOWED_SET", result.failures[0].failure_tags)
            self.assertTrue(eval_repo.list_eval_runs())

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
