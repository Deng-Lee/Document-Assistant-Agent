from __future__ import annotations

import json
import unittest
from pathlib import Path
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
            self.assertEqual(result.manual_rubric.status.value, "skipped")
            self.assertEqual(result.manual_rubric.reason, "not_reviewed")
            self.assertEqual(result.golden_case_count, 2)
            self.assertEqual(len(eval_repo.list_golden_cases()), 2)
            self.assertTrue(eval_repo.list_eval_runs())

    def test_evaluation_manual_rubric_is_stored_and_aggregated(self) -> None:
        with TemporaryDirectory() as tmp:
            trace_store, eval_repo = _build_eval_stack(tmp)
            trace_store.write_trace(make_trace_record(trace_id="trace_manual"))
            _write_golden_set(
                tmp,
                "manual_suite",
                [
                    {
                        "case_id": "case_manual",
                        "query": "turtle escape",
                        "domain": "BJJ",
                        "trace_id": "trace_manual",
                        "expected_behavior": {"required_mode": "FULL"},
                        "expected_chunk_ids": ["chunk_1"],
                    }
                ],
            )

            from server.app.core import EvalRunRequest, ManualRubricScore
            from server.app.evaluation import EvaluationService

            service = EvaluationService(trace_store=trace_store, golden_case_repository=eval_repo, repo_root=tmp)
            result = service.run(EvalRunRequest(eval_set_id="manual_suite"))
            entry, updated = service.submit_manual_rubric(
                eval_run_id=result.eval_run_id,
                trace_id="trace_manual",
                reviewer="lee",
                scores=[
                    ManualRubricScore(dimension="ab_distinctness", score=3),
                    ManualRubricScore(dimension="drill_executability", score=2),
                    ManualRubricScore(dimension="caveat_reasonableness", score=3),
                ],
                notes="good baseline",
            )

            self.assertEqual(entry.eval_run_id, result.eval_run_id)
            self.assertEqual(updated.manual_rubric.status.value, "succeeded")
            self.assertEqual(updated.manual_rubric.details["reviewed_trace_count"], 1)
            self.assertEqual(updated.manual_rubric.details["trace_coverage"], 1.0)
            self.assertEqual(updated.manual_rubric.details["dimension_averages"]["ab_distinctness"], 3.0)
            self.assertEqual(len(service.list_manual_rubrics(result.eval_run_id)), 1)
            stored = eval_repo.get_eval_run(result.eval_run_id)
            self.assertIsNotNone(stored)
            self.assertEqual(stored.manual_rubric.status.value, "succeeded")

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

            from server.app.core import EvalMetricName, EvalMetricValue, EvalRunRequest, EvalStageResult, EvalStageStatus
            from server.app.evaluation import EvaluationService

            service = EvaluationService(
                trace_store=trace_store,
                golden_case_repository=eval_repo,
                repo_root=tmp,
                ragas_runner=lambda cases, traces: EvalStageResult(
                    status=EvalStageStatus.SUCCEEDED,
                    evaluator="ragas_external_v1",
                    sample_count=len(traces),
                    metrics=[
                        EvalMetricValue(metric=EvalMetricName.FAITHFULNESS, value=0.9),
                        EvalMetricValue(metric=EvalMetricName.ANSWER_RELEVANCY, value=0.8),
                        EvalMetricValue(metric=EvalMetricName.CONTEXT_PRECISION, value=0.7),
                        EvalMetricValue(metric=EvalMetricName.CONTEXT_RECALL, value=0.6),
                    ],
                ),
                judge_runner=lambda cases, traces: EvalStageResult(
                    status=EvalStageStatus.FAILED,
                    evaluator="openai_judge_v1",
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

    def test_evaluation_real_profile_uses_external_evaluators(self) -> None:
        with TemporaryDirectory() as tmp:
            activate_test_profile("real")
            trace_store, eval_repo = _build_eval_stack(tmp)
            trace_store.write_trace(make_trace_record(trace_id="trace_ext"))
            _write_golden_set(
                tmp,
                "external_suite",
                [
                    {
                        "case_id": "case_ext",
                        "query": "turtle escape",
                        "domain": "BJJ",
                        "trace_id": "trace_ext",
                        "expected_behavior": {"required_mode": "FULL", "min_citation_count": 1},
                        "expected_chunk_ids": ["chunk_1"],
                    }
                ],
            )

            from server.app.core import EvalRunRequest, build_runtime_config
            from server.app.evaluation import EvaluationService, OpenAIExternalJudgeEvaluator, RagasExternalEvaluator

            runtime_config = build_runtime_config("real")
            ragas_backend = _StubRagasBackend(
                model_name=runtime_config.model_routing.base_model,
                embedding_model_name=runtime_config.model_routing.embedding_model,
                response_map={
                    "case_ext": {
                        "faithfulness": 0.91,
                        "answer_relevancy": 0.83,
                        "context_precision": 0.79,
                        "context_recall": 0.88,
                    }
                },
                base_url="https://example.invalid/v1",
            )
            service = EvaluationService(
                trace_store=trace_store,
                golden_case_repository=eval_repo,
                repo_root=tmp,
                runtime_config=runtime_config,
                ragas_evaluator=RagasExternalEvaluator(runtime_config=runtime_config, backend=ragas_backend),
                judge_evaluator=OpenAIExternalJudgeEvaluator(
                    runtime_config=runtime_config,
                    api_key="test-key",
                    transport=_StubEvalTransport(
                        {
                            "choices": [
                                {
                                    "message": {
                                        "content": '{"passed":true,"rubric_score":5,"score":0.87,"error_tags":[],"notes":"good"}'
                                    }
                                }
                            ]
                        }
                    ),
                ),
            )

            result = service.run(EvalRunRequest(eval_set_id="external_suite"))

            self.assertEqual(result.run_status.value, "completed")
            self.assertEqual(result.ragas.status.value, "succeeded")
            self.assertEqual(result.ragas.evaluator, "ragas_external_v1")
            self.assertEqual(result.judge.status.value, "succeeded")
            self.assertEqual(result.judge.evaluator, "openai_judge_v1")
            metrics = {metric.metric.value: metric.value for metric in result.metrics}
            self.assertEqual(metrics["faithfulness"], 0.91)
            self.assertEqual(metrics["answer_relevancy"], 0.83)
            self.assertEqual(result.judge.details["score"], 0.87)
            self.assertEqual(result.judge.details["rubric_score_average"], 5.0)
            self.assertEqual(result.judge.details["sample_strategy"], "stratified_priority_v1")
            self.assertEqual(result.judge.details["tag_counts"], {})
            status = service.provider_status()
            self.assertEqual(status["ragas"]["evaluator_name"], "ragas_external_v1")
            self.assertTrue(status["ragas"]["configured"])
            self.assertEqual(status["judge"]["evaluator_name"], "openai_judge_v1")
            self.assertTrue(status["judge"]["configured"])

    def test_judge_uses_stratified_sampling_and_aggregates_error_tags(self) -> None:
        with TemporaryDirectory() as tmp:
            activate_test_profile("real")
            trace_store, eval_repo = _build_eval_stack(tmp)
            validator_fail = make_trace_record(trace_id="trace_validator_fail", validator_pass=False)
            ambiguous = make_trace_record(trace_id="trace_ambiguous")
            ambiguous.request_log.confirmed_slots["position"] = "half_guard"
            ambiguous_output = dict(ambiguous.generation_log.output)
            ambiguous_output["mode"] = "AMBIGUOUS_FINAL"
            ambiguous_output["reasoning_status"] = dict(ambiguous_output["reasoning_status"])
            ambiguous_output["reasoning_status"]["gate_label"] = "AMBIGUOUS"
            ambiguous.generation_log.output = ambiguous_output
            turtle_a = make_trace_record(trace_id="trace_turtle_a")
            turtle_b = make_trace_record(trace_id="trace_turtle_b")
            mount = make_trace_record(trace_id="trace_mount")
            mount.request_log.confirmed_slots["position"] = "mount"
            for trace in (validator_fail, ambiguous, turtle_a, turtle_b, mount):
                trace_store.write_trace(trace)
            _write_golden_set(
                tmp,
                "judge_sampling_suite",
                [
                    {"case_id": "case_validator_fail", "query": "turtle escape", "domain": "BJJ", "trace_id": "trace_validator_fail", "expected_behavior": {"required_mode": "FULL"}, "expected_chunk_ids": ["chunk_1"]},
                    {"case_id": "case_ambiguous", "query": "turtle escape", "domain": "BJJ", "trace_id": "trace_ambiguous", "expected_behavior": {"required_mode": "AMBIGUOUS_FINAL"}, "expected_chunk_ids": ["chunk_1"]},
                    {"case_id": "case_turtle_a", "query": "turtle escape", "domain": "BJJ", "trace_id": "trace_turtle_a", "expected_behavior": {"required_mode": "FULL"}, "expected_chunk_ids": ["chunk_1"]},
                    {"case_id": "case_turtle_b", "query": "turtle escape", "domain": "BJJ", "trace_id": "trace_turtle_b", "expected_behavior": {"required_mode": "FULL"}, "expected_chunk_ids": ["chunk_1"]},
                    {"case_id": "case_mount", "query": "mount escape", "domain": "BJJ", "trace_id": "trace_mount", "expected_behavior": {"required_mode": "FULL"}, "expected_chunk_ids": ["chunk_1"]},
                ],
            )

            from server.app.core import EvalRunRequest, EvalStageResult, EvalStageStatus, build_runtime_config
            from server.app.evaluation import EvaluationService, OpenAIExternalJudgeEvaluator

            runtime_config = build_runtime_config("real")

            def _judge_response(payload):
                body = json.loads(payload["messages"][-1]["content"])
                case_id = body["case_id"]
                response_map = {
                    "case_validator_fail": '{"passed":false,"rubric_score":2,"error_tags":["VALIDATOR_FAIL","DRILL_INCOMPLETE"],"notes":"validator mismatch"}',
                    "case_ambiguous": '{"passed":false,"rubric_score":3,"error_tags":["AMBIGUOUS_MODE_MISMATCH"],"notes":"boundary mismatch"}',
                    "case_turtle_a": '{"passed":true,"rubric_score":4,"error_tags":[],"notes":"acceptable"}',
                    "case_turtle_b": '{"passed":true,"rubric_score":5,"error_tags":[],"notes":"strong"}',
                    "case_mount": '{"passed":true,"rubric_score":5,"error_tags":[],"notes":"not sampled"}',
                }
                return {"choices": [{"message": {"content": response_map[case_id]}}]}

            transport = _StubEvalTransport(_judge_response)
            service = EvaluationService(
                trace_store=trace_store,
                golden_case_repository=eval_repo,
                repo_root=tmp,
                runtime_config=runtime_config,
                ragas_runner=lambda cases, traces: EvalStageResult(
                    status=EvalStageStatus.SKIPPED,
                    evaluator="ragas_external_v1",
                    reason="not_under_test",
                    sample_count=0,
                ),
                judge_evaluator=OpenAIExternalJudgeEvaluator(
                    runtime_config=runtime_config,
                    api_key="test-key",
                    transport=transport,
                    max_sample_cases=3,
                    frequent_position_top_n=1,
                ),
            )

            result = service.run(EvalRunRequest(eval_set_id="judge_sampling_suite"))

            self.assertEqual(result.judge.status.value, "succeeded")
            self.assertEqual(result.judge.sample_count, 3)
            self.assertEqual(result.judge.details["eligible_case_count"], 5)
            self.assertEqual(result.judge.details["omitted_case_count"], 2)
            self.assertEqual(result.judge.details["strata_counts"]["validator_fail"], 1)
            self.assertEqual(result.judge.details["strata_counts"]["ambiguous_final"], 1)
            self.assertEqual(result.judge.details["strata_counts"]["frequent_position"], 2)
            self.assertEqual(result.judge.details["tag_counts"]["VALIDATOR_FAIL"], 1)
            self.assertEqual(result.judge.details["tag_counts"]["DRILL_INCOMPLETE"], 1)
            self.assertEqual(result.judge.details["tag_counts"]["AMBIGUOUS_MODE_MISMATCH"], 1)
            self.assertEqual(result.judge.details["top_positions"], ["turtle"])
            self.assertIn("case_validator_fail", result.judge.details["judged_case_ids"])
            self.assertIn("case_ambiguous", result.judge.details["judged_case_ids"])
            self.assertEqual(len(transport.calls), 3)
            self.assertNotIn("case_mount", result.judge.details["judged_case_ids"])

    def test_evaluation_real_profile_provider_unavailable_marks_run_partial(self) -> None:
        with TemporaryDirectory() as tmp:
            activate_test_profile("real")
            trace_store, eval_repo = _build_eval_stack(tmp)
            trace_store.write_trace(make_trace_record(trace_id="trace_missing_key"))
            _write_golden_set(
                tmp,
                "missing_key_suite",
                [
                    {
                        "case_id": "case_missing_key",
                        "query": "turtle escape",
                        "domain": "BJJ",
                        "trace_id": "trace_missing_key",
                        "expected_behavior": {"required_mode": "FULL"},
                        "expected_chunk_ids": ["chunk_1"],
                    }
                ],
            )

            from server.app.core import EvalRunRequest, build_runtime_config
            from server.app.evaluation import EvaluationService, OpenAIExternalJudgeEvaluator, RagasExternalEvaluator

            runtime_config = build_runtime_config("real")
            service = EvaluationService(
                trace_store=trace_store,
                golden_case_repository=eval_repo,
                repo_root=tmp,
                runtime_config=runtime_config,
                ragas_evaluator=RagasExternalEvaluator(
                    runtime_config=runtime_config,
                    backend=_UnavailableRagasBackend(
                        model_name=runtime_config.model_routing.base_model,
                        embedding_model_name=runtime_config.model_routing.embedding_model,
                        reason="missing_openai_api_key",
                    ),
                ),
                judge_evaluator=OpenAIExternalJudgeEvaluator(runtime_config=runtime_config, api_key=None, transport=None),
            )

            result = service.run(EvalRunRequest(eval_set_id="missing_key_suite"))

            self.assertEqual(result.run_status.value, "partial")
            self.assertEqual(result.ragas.status.value, "failed")
            self.assertEqual(result.ragas.reason, "missing_openai_api_key")
            self.assertEqual(result.judge.status.value, "failed")
            self.assertEqual(result.judge.reason, "missing_openai_api_key")

    def test_ragas_contexts_use_note_anchor_contract(self) -> None:
        from server.app.core import (
            EvidencePack,
            EvidencePackItem,
            EvalRunRequest,
            EvalStageResult,
            EvalStageStatus,
            GenerationLog,
            LineRange,
            RankSignals,
            RequestLog,
            RetrievalLog,
            RuntimeConfigSnapshot,
            SourceLocator,
            TraceRecord,
        )
        from server.app.core import ChunkMetadataDigest
        from server.app.evaluation import EvaluationService, RagasExternalEvaluator

        with TemporaryDirectory() as tmp:
            activate_test_profile("real")
            trace_store, eval_repo = _build_eval_stack(tmp)
            trace = TraceRecord(
                trace_id="trace_notes",
                conversation_id="conv_notes",
                runtime_config_snapshot=RuntimeConfigSnapshot(),
                request_log=RequestLog(entrypoint="chat", domain="NOTES", task="COACH_LITERARY"),
                retrieval_log=RetrievalLog(),
                evidence_log=EvidencePack(
                    items=[
                        EvidencePackItem(
                            evidence_id="chunk_notes_1",
                            doc_id="doc_notes_1",
                            doc_version_id="dv_notes_1",
                            locator=SourceLocator(
                                doc_version_id="dv_notes_1",
                                source_path="notes.md",
                                line_range=LineRange(start=3, end=5),
                                char_range={"start": 20, "end": 80},
                            ),
                            safe_summary="图书馆像镜子一样折回到迷宫。",
                            metadata_digest=ChunkMetadataDigest(heading_path=["Maze Draft"]),
                            rank_signals=RankSignals(rrf_rank=1),
                        )
                    ]
                ),
                generation_log=GenerationLog(
                    provider="mock",
                    model="mock-literary-base",
                    prompt_version="literary.v1",
                    output={
                        "text": "把镜子写成第二座图书馆。",
                        "anchors": [
                            {
                                "anchor_type": "raw_excerpt",
                                "doc_rank": 1,
                                "evidence_id": "chunk_notes_1",
                                "doc_version_id": "dv_notes_1",
                                "locator": {
                                    "doc_version_id": "dv_notes_1",
                                    "source_path": "notes.md",
                                    "line_range": {"start": 3, "end": 5},
                                    "char_range": {"start": 20, "end": 80},
                                },
                                "citation": "dv_notes_1:3",
                                "content": "A library can be a maze and a mirror.",
                                "heading_path": ["Maze Draft"],
                            },
                            {
                                "anchor_type": "safe_summary",
                                "doc_rank": 2,
                                "evidence_id": "chunk_notes_2",
                                "doc_version_id": "dv_notes_2",
                                "locator": {
                                    "doc_version_id": "dv_notes_2",
                                    "source_path": "notes-2.md",
                                    "line_range": {"start": 7, "end": 9},
                                    "char_range": {"start": 81, "end": 140},
                                },
                                "citation": "dv_notes_2:7",
                                "content": "雨夜里的街道像第二份档案。",
                                "heading_path": ["Night Walk"],
                            },
                        ],
                    },
                ),
            )
            trace_store.write_trace(trace)
            _write_golden_set(
                tmp,
                "notes_suite",
                [
                    {
                        "case_id": "case_notes",
                        "query": "继续写迷宫和镜子",
                        "domain": "NOTES",
                        "trace_id": "trace_notes",
                        "expected_behavior": {"must_reference_anchor": True},
                        "expected_chunk_ids": ["chunk_notes_1"],
                    }
                ],
            )
            backend = _StubRagasBackend(
                model_name="qwen-plus",
                embedding_model_name="text-embedding-v4",
                response_map={
                    "case_notes": {
                        "faithfulness": 0.75,
                        "answer_relevancy": 0.88,
                        "context_precision": 0.91,
                        "context_recall": 0.73,
                    }
                },
            )
            service = EvaluationService(
                trace_store=trace_store,
                golden_case_repository=eval_repo,
                repo_root=tmp,
                runtime_config=RuntimeConfigSnapshot(),
                ragas_evaluator=RagasExternalEvaluator(runtime_config=RuntimeConfigSnapshot(), backend=backend),
                judge_runner=lambda cases, traces: EvalStageResult(
                    status=EvalStageStatus.SKIPPED,
                    evaluator="openai_judge_v1",
                    reason="not_under_test",
                    sample_count=0,
                ),
            )

            result = service.run(EvalRunRequest(eval_set_id="notes_suite"))

            self.assertEqual(result.ragas.status.value, "succeeded")
            self.assertEqual(backend.calls[0].contexts[0], "raw_excerpt dv_notes_1:3: A library can be a maze and a mirror.")
            self.assertEqual(backend.calls[0].contexts[1], "safe_summary dv_notes_2:7: 雨夜里的街道像第二份档案。")

    def test_sft_export_filters_and_builds_train_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            trace_store, _eval_repo = _build_eval_stack(tmp)

            keep_trace = make_trace_record(trace_id="trace_keep")
            _attach_input_snapshot(keep_trace)
            drop_trace = make_trace_record(trace_id="trace_drop")
            _attach_input_snapshot(drop_trace)
            drop_output = dict(drop_trace.generation_log.output)
            drop_output["reasoning_status"] = dict(drop_output["reasoning_status"])
            drop_output["reasoning_status"]["gate_label"] = "LOW_EVIDENCE"
            drop_trace.generation_log.output = drop_output
            drop_trace.generation_log.validator_report.validator_pass = False

            trace_store.write_trace(keep_trace)
            trace_store.write_trace(drop_trace)

            from server.app.core import ModelVariant, SFTExportRequest, build_runtime_config
            from server.app.sft import SFTService

            inference_backend = _StubInferenceBackend()
            service = SFTService(
                trace_store=trace_store,
                policy_root=f"{tmp}/policies",
                training_backend=_StubTrainingBackend(),
                inference_backend=inference_backend,
            )
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
            self.assertEqual(rows[0]["input"]["task"], "COACH_BJJ")
            self.assertIn("query_original", rows[0]["input"])

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

    def test_sft_training_registers_policy_and_replays_policy_variant(self) -> None:
        with TemporaryDirectory() as tmp:
            trace_store, eval_repo = _build_eval_stack(tmp)
            trace = make_trace_record(trace_id="trace_policy")
            _attach_input_snapshot(trace)
            trace_store.write_trace(trace)
            _write_golden_set(
                tmp,
                "policy_suite",
                [
                    {
                        "case_id": "case_policy",
                        "query": "turtle escape",
                        "domain": "BJJ",
                        "trace_id": "trace_policy",
                        "expected_behavior": {"required_mode": "FULL", "response_contains": ["policy tuned"]},
                        "expected_chunk_ids": ["chunk_1"],
                    }
                ],
            )

            from server.app.agents import BJJCoachService, LiteraryService
            from server.app.core import EvalRunRequest, ModelVariant, PolicyTrainRequest, SFTExportRequest, ProfileSummary, build_runtime_config
            from server.app.evaluation import EvaluationService
            from server.app.sft import SFTService

            runtime_config = build_runtime_config()
            inference_backend = _StubInferenceBackend()
            service = SFTService(
                trace_store=trace_store,
                policy_root=f"{tmp}/policies",
                training_backend=_StubTrainingBackend(),
                inference_backend=inference_backend,
            )
            export_dir = Path(tmp) / "datasets" / "sft" / "v1" / "policy_suite"
            manifest, samples = service.export_dataset(
                request=SFTExportRequest(trace_filter={"gate_label": "HIGH_EVIDENCE"}),
                output_dir=export_dir,
            )
            tuned_output = json.loads(json.dumps(samples[0].baseline_output))
            tuned_output["observations"][0]["text"] = "policy tuned observation"
            samples[0].target_output = tuned_output
            train_path = service.build_train_rows(samples, export_dir / "train.jsonl", prefer_target_output=True)

            checkpoint = service.train_policy(
                PolicyTrainRequest(
                    train_path=str(train_path),
                    output_path=str(Path(tmp) / "policy_ckpt"),
                    base_model=runtime_config.model_routing.base_model,
                    dry_run=False,
                    activate=True,
                ),
                dataset_manifest=manifest,
            )

            policy_dir = Path(tmp) / "policy_ckpt"
            self.assertTrue((policy_dir / "policy_artifact.json").exists())
            self.assertEqual(service.get_active_policy_ref(), checkpoint.policy_model_ref)
            self.assertEqual(checkpoint.training_backend, "hf_lora_qlora_v1")
            artifact = json.loads((policy_dir / "policy_artifact.json").read_text(encoding="utf-8"))
            self.assertEqual(artifact["schema_version"], "hf_lora_qlora_v1")
            self.assertTrue((policy_dir / "adapter").exists())
            self.assertTrue((policy_dir / "tokenizer").exists())
            self.assertEqual(service.training_backend_status()["backend_name"], "hf_lora_qlora_v1")
            self.assertEqual(service.inference_backend_status()["backend_name"], "hf_lora_qlora_inference_v1")
            replayed_trace, final_answer = service.replay_trace(
                source_trace=trace,
                variant=ModelVariant.POLICY,
                runtime_config=runtime_config,
                current_profile=ProfileSummary(profile_version_id="profile_default"),
                bjj_coach_service=BJJCoachService(runtime_config=runtime_config),
                literary_service=LiteraryService(),
            )

            self.assertEqual(final_answer.observations[0].text, "policy tuned observation")
            self.assertEqual(replayed_trace.generation_log.model, checkpoint.policy_model_ref)
            self.assertGreaterEqual(len(inference_backend.calls), 1)

            eval_service = EvaluationService(
                trace_store=trace_store,
                golden_case_repository=eval_repo,
                repo_root=tmp,
                replay_runner=lambda traces, variant, use_frozen_evidence: service.replay_eval_traces(
                    traces=traces,
                    variant=variant,
                    runtime_config=runtime_config,
                    current_profile=ProfileSummary(profile_version_id="profile_default"),
                    bjj_coach_service=BJJCoachService(runtime_config=runtime_config),
                    literary_service=LiteraryService(),
                    use_frozen_evidence=use_frozen_evidence,
                ),
            )
            result = eval_service.run(
                EvalRunRequest(eval_set_id="policy_suite", model_variant=ModelVariant.POLICY),
                trace_ids=["trace_policy"],
            )
            policy_trace = trace_store.read_trace(result.source_trace_ids[0])
            self.assertNotEqual(policy_trace.trace_id, "trace_policy")
            self.assertEqual(policy_trace.generation_log.model, checkpoint.policy_model_ref)
            self.assertIn("policy tuned", policy_trace.generation_log.output["observations"][0]["text"])


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


def _attach_input_snapshot(trace) -> None:
    from server.app.observability import build_generation_input_snapshot, build_prompt_snapshot
    from server.app.core import ProfileSummary

    input_snapshot = build_generation_input_snapshot(
        task=trace.request_log.task,
        query_original=trace.retrieval_log.retrieval_plan.query_original if trace.retrieval_log.retrieval_plan else "",
        query_clean=trace.retrieval_log.retrieval_plan.query_text if trace.retrieval_log.retrieval_plan else "",
        confirmed_slots=trace.request_log.confirmed_slots,
        coach_clarify_round=trace.generation_log.output.get("reasoning_status", {}).get("coach_clarify_round", 0),
        coach_pending_slot=None,
        profile_summary=ProfileSummary(profile_version_id=trace.request_log.profile_version_id or "profile_test"),
        frozen_evidence_pack=trace.evidence_log,
    )
    trace.generation_log.input_snapshot = input_snapshot
    trace.generation_log.prompt_snapshot = build_prompt_snapshot(input_snapshot)


class _StubEvalTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create_chat_completion(self, payload):
        self.calls.append(payload)
        if callable(self.response):
            return self.response(payload)
        return self.response


class _StubRagasBackend:
    backend_name = "ragas_langchain_openai_v1"
    is_ready = True
    missing_dependencies: list[str] = []

    def __init__(
        self,
        *,
        model_name: str,
        embedding_model_name: str,
        response_map: dict[str, dict[str, float]],
        base_url: str | None = None,
    ):
        self.model_name = model_name
        self.embedding_model_name = embedding_model_name
        self.response_map = response_map
        self.base_url = base_url
        self.calls = []

    def score_cases(self, cases):
        from server.app.evaluation.external_evaluators import RagasCaseScores

        self.calls.extend(cases)
        return {
            case.case_id: RagasCaseScores(**self.response_map[case.case_id])
            for case in cases
        }


class _UnavailableRagasBackend:
    backend_name = "ragas_langchain_openai_v1"
    is_ready = False
    missing_dependencies: list[str] = []
    base_url = None

    def __init__(self, *, model_name: str, embedding_model_name: str, reason: str):
        self.model_name = model_name
        self.embedding_model_name = embedding_model_name
        self.reason = reason

    def score_cases(self, cases):
        from server.app.evaluation.external_evaluators import ExternalEvaluatorUnavailableError

        raise ExternalEvaluatorUnavailableError(self.reason)


class _StubTrainingBackend:
    backend_name = "hf_lora_qlora_v1"

    def run(self, request):
        from server.app.sft.training_backend import PolicyTrainingArtifact

        output_dir = Path(request.output_path)
        adapter_dir = output_dir / "adapter"
        tokenizer_dir = output_dir / "tokenizer"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        tokenizer_dir.mkdir(parents=True, exist_ok=True)
        (adapter_dir / "adapter_config.json").write_text('{"stub":true}\n', encoding="utf-8")
        (tokenizer_dir / "tokenizer_config.json").write_text('{"stub":true}\n', encoding="utf-8")
        summary_path = output_dir / "training_summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "backend_name": self.backend_name,
                    "base_model": request.base_model,
                    "load_in_4bit": request.load_in_4bit,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return PolicyTrainingArtifact(
            backend_name=self.backend_name,
            schema_version=self.backend_name,
            adapter_path=str(adapter_dir),
            tokenizer_path=str(tokenizer_dir),
            training_summary_path=str(summary_path),
            metadata={"runner": "stub"},
        )

    def status(self):
        return {
            "backend_name": self.backend_name,
            "script_path": "/tmp/stub-train-policy-lora.py",
            "script_exists": True,
            "configured": True,
            "missing_dependencies": [],
            "qlora_supported": True,
            "required_modules": {},
            "optional_modules": {"bitsandbytes": True},
        }


class _StubInferenceBackend:
    backend_name = "hf_lora_qlora_inference_v1"

    def __init__(self):
        self.calls = []

    def generate(self, artifact, input_payload, max_new_tokens=1024):
        from server.app.sft.inference_backend import PolicyInferenceResult

        self.calls.append(
            {
                "policy_model_ref": artifact.get("policy_model_ref"),
                "max_new_tokens": max_new_tokens,
                "task": input_payload.get("task"),
            }
        )
        signature = _artifact_signature(input_payload)
        learned = artifact.get("examples", {}).get(signature)
        if learned is None:
            raise RuntimeError("missing_stub_example")
        return PolicyInferenceResult(
            output=learned["target_output"],
            token_usage={"prompt_tokens": 12, "completion_tokens": 34},
            metadata={"runner": "stub_inference"},
        )

    def status(self):
        return {
            "backend_name": self.backend_name,
            "configured": True,
            "missing_dependencies": [],
            "required_modules": {},
        }


def _artifact_signature(input_payload: dict) -> str:
    import hashlib

    return hashlib.sha1(json.dumps(input_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
