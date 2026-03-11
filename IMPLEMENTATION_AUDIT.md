# IMPLEMENTATION AUDIT

本文件用于严格对照 [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md) 与 [IMPLEMENTATION_PLAN.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/IMPLEMENTATION_PLAN.md)，判断当前仓库哪些模块已经真实收口，哪些只是部分实现，哪些已经出现方案漂移。

## Audit Rules

以下规则是本仓库后续实现和状态判断的硬约束：

1. 必须严格按照 `DEV_SPEC.md` 和 `IMPLEMENTATION_PLAN.md` 中给定的方案实现。
2. 不得把 `placeholder`、`proxy`、`mock`、`fake`、`heuristic`、`surrogate` 形态记为主功能已完成。
3. 不得使用 `fallback` 代替主功能后仍将状态标为 `done`。
4. 不得只实现底层能力而不提供 API / runtime / UI / job 入口；存在入口断层时，状态不得标为 `done`。
5. 只有当“主功能语义、调用入口、trace/eval 可见性、测试覆盖”同时到位时，才能标记为 `done`。

状态定义：

- `done`
  主功能语义已按 spec 落地，且有实际入口与验证。
- `partial`
  已有可运行实现，但仍缺主功能的一部分，或只打通了部分入口。
- `drift`
  当前实现和 spec/plan 的目标能力明显不一致，或以替代方案代替了原定主功能。

## Strict Checklist

| Module / Capability | Status | Audit Note | Evidence |
| --- | --- | --- | --- |
| Core contracts: chat/evidence/trace/eval/sft schemas | `done` | 主契约和 JSON schema 已存在，核心 API shape 基本符合计划。 | [server/app/core](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/core) |
| Storage foundations: SQLite/FTS5/FileStore/Chroma/TraceStore | `done` | 主存储链路已接通，Chroma 也已替代 JSON adapter。 | [server/app/storage](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/storage) |
| Ingestion: file/dir/text/record flows | `done` | 主导入入口和 chunk/version/locator 写入已打通。 | [server/app/ingestion](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/ingestion), [server/app/api/app.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/app.py) |
| `safe_summary` job orchestration | `done` | 真实 summary provider、`summary_model` / `summary_prompt_version` / `summary_status` / `summary_error_code`、显式 `FAILED` 状态、retry 元数据、自动重试、指数退避，以及单 chunk rebuild、失败项查询、批量 retry 运维入口均已接上；retryable 错误会保留失败 attempt job 并自动排入下一次重试，重试耗尽后才落 `FALLBACK`。 | [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L367), [server/app/jobs/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/jobs/service.py#L76), [server/app/jobs/safe_summary_provider.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/jobs/safe_summary_provider.py), [server/app/api/app.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/app.py#L260) |
| Maintenance APIs: `safe_summary/rebuild`, `maintenance/reindex`, `maintenance/reembed` | `done` | 专门 API 入口、`doc_version_id | doc_id | all` scope、reindex flags、reembed `embedding_version_id` 与 dry-run 均已接通；reembed 也已按目标 `embedding_version_id` 保留旧版本隔离。 | [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L1937), [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L1944), [server/app/api/app.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/app.py), [server/app/jobs/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/jobs/service.py) |
| Retrieval mainline: structured + BM25 + dense + RRF | `done` | 主 hybrid retrieval 方案已落地。 | [server/app/retrieval/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/retrieval/service.py) |
| Cross-encoder reranker | `done` | `real` profile 主路径现已切到本地 Hugging Face cross-encoder backend，且 `torch/transformers` 已提升为默认开发环境依赖，不再把 cross-encoder 主路径压成 `.[rerank]` 可选安装。现有本地解释器如未重装依赖仍需执行环境同步，但这已不再是 repo manifest 层面的缺口。 | [server/app/retrieval/reranker.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/retrieval/reranker.py), [config/model_profiles/real.json](/Users/lee/Documents/AI/Document%20Assistant%20Agent/config/model_profiles/real.json), [pyproject.toml](/Users/lee/Documents/AI/Document%20Assistant%20Agent/pyproject.toml), [server/tests/test_project_metadata.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/tests/test_project_metadata.py) |
| Orchestrator: probe / plan_check / clarify / one-shot replan | `done` | 主执行链与 fake/real 两条路径都已接入，且有 fallback telemetry。 | [server/app/orchestrator](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/orchestrator) |
| BJJ coach pipeline | `done` | gate、validator、repair/degrade 和输出模式已接通。 | [server/app/agents/bjj_coach](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/agents/bjj_coach) |
| Literary pipeline `top-1 raw_excerpt + top-2/3 safe_summary anchors` | `done` | NOTES 域现已按 spec 生成 top-1 `raw_excerpt` 与 top-2/3 `safe_summary` anchors，并通过 provider-backed generation path 输出文本；`raw_excerpt` 会从持久化 chunk 原文读取并执行注入文本/代码块清洗。 | [IMPLEMENTATION_PLAN.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/IMPLEMENTATION_PLAN.md#L165), [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L1690), [server/app/agents/literary/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/agents/literary/service.py), [server/app/agents/literary/provider.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/agents/literary/provider.py) |
| Observability: trace/span/event and replay | `done` | 主 trace/replay 能力和 minimal/debug capture 已有。 | [server/app/observability](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/observability) |
| Observability strictness: minimal/debug capture semantics | `done` | `minimal` 现已只保留结构化 replay 因子与 `safe_summary` 证据，不再在 `generation_log.input_snapshot` 中持久化原始 `query_original/query_clean`；`debug` 仍保留 prompt preview 与 excerpt snapshot。replay 则会从 structural logs 复水缺失 query，因此严格留痕与可回放两者都已收口。 | [server/app/observability/recorder.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/observability/recorder.py#L179), [server/app/sft/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/sft/service.py#L444), [server/tests/test_observability.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/tests/test_observability.py) |
| Replay override metadata | `done` | `override_generation_config` 现在会真正作用于 replay 的 `runtime_config_snapshot.generation`，并写回 `request_log.override_generation_config` 与 replay trace event，不再只是 request schema 占位。 | [IMPLEMENTATION_PLAN.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/IMPLEMENTATION_PLAN.md#L259), [server/app/api/models.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/models.py#L25), [server/app/api/app.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/app.py#L338), [server/app/sft/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/sft/service.py) |
| Evaluation hard metrics | `done` | 主硬指标路径已接通。 | [server/app/evaluation/metrics.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/evaluation/metrics.py) |
| Evaluation manual rubric | `done` | 存储、API、聚合结果均已接通。 | [server/app/evaluation/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/evaluation/service.py), [server/app/api/app.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/app.py#L299) |
| RAGAS evaluator | `done` | `real` profile 主路径现已切到真实 RAGAS backend 结构，并按 spec 为 NOTES 优先构造 `top-1 raw_excerpt / top-2/3 safe_summary` contexts；`datasets/langchain-openai/ragas` 也已纳入默认开发环境依赖，不再把真实 RAGAS 主路径压成 `.[evaluation]` 可选安装。现有本地解释器如未重装依赖仍需执行环境同步，但这已不再是 repo manifest 层面的缺口。 | [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L2230), [server/app/evaluation/external_evaluators.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/evaluation/external_evaluators.py), [pyproject.toml](/Users/lee/Documents/AI/Document%20Assistant%20Agent/pyproject.toml), [server/tests/test_project_metadata.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/tests/test_project_metadata.py) |
| LLM-as-judge | `done` | judge 现已按 spec 采用固定模型/固定 prompt 版本、结构化 `rubric_score + error_tags` 输出，并在执行前做分层抽样，优先覆盖 validator fail、`AMBIGUOUS_FINAL` 边界态和高频 position；聚合结果中也会返回 strata/tag 统计与 sampled case 明细。 | [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L2267), [server/app/evaluation/external_evaluators.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/evaluation/external_evaluators.py), [server/tests/test_evaluation_sft.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/tests/test_evaluation_sft.py) |
| SFT export / training / policy replay | `done` | 主训练、注册、激活、policy replay/eval 已接通。 | [server/app/sft/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/sft/service.py) |
| SFT readiness in default dev env | `partial` | 代码路径已具备，但默认开发环境依赖未就绪，这仍是环境层面的未收口。 | [FACTS.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/FACTS.md), [server/app/api/__main__.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/__main__.py) |
| Profile persistence and history | `done` | 持久化、启动恢复、history API 已接通。 | [server/app/api/app.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/app.py#L337) |
| Web frontend baseline | `partial` | Next.js、SSE、contract sync、component test、Playwright 已有；但 spec 点名的 Tailwind + shadcn/ui 当前并未接入，不能说完全等价于原方案。 | [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L64), [web/package.json](/Users/lee/Documents/AI/Document%20Assistant%20Agent/web/package.json#L1) |
| Canonical plan doc baseline accuracy | `done` | `IMPLEMENTATION_PLAN.md` 的 current baseline 已改写为当前真实仓库状态，不再把 repo 误写成 `spec-only`。 | [IMPLEMENTATION_PLAN.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/IMPLEMENTATION_PLAN.md#L11) |

## Summary

当前仓库的主链路已经大面积收口，但审计视角下仍需区分三类状态：

1. `done`
   主链路真实落地，且具备入口和验证。
2. `partial`
   能力部分可用，但还缺 spec 要求的入口、执行语义或验收深度。
3. `drift`
   代码用替代实现取代了原定方案，或者 canonical 文档本身已经失真。

截至当前版本，本清单中的原 `drift` 项已全部被处理并重新标记；当前剩余未收口项均为 `partial`，不得因为“已有 fallback / readiness check / 局部入口”而上调为 `done`。

## Remaining Work

以下内容仍未达到 `DEV_SPEC.md` 与 `IMPLEMENTATION_PLAN.md` 要求的完全收口标准，后续必须继续按原方案补齐：

1. SFT readiness in default dev env
   SFT 主链路代码已完成，但默认开发环境未装 `.[training]` 与 adapter inference 依赖；环境 readiness 仍未收口。
2. Web frontend baseline
   Next.js 主链路已完成，但 `DEV_SPEC.md` 点名的 Tailwind + shadcn/ui 方案仍未严格对齐，不能把当前前端形态视为和原方案完全一致。

## Implementation Discipline For Next Steps

后续修复时必须遵守：

1. 当前如无新增 `drift`，优先收口现有 `partial`；一旦出现新的 `drift`，必须先恢复 spec 原语义，再谈新增能力。
2. 修复时必须优先恢复 spec 原语义，不允许继续用 `proxy/mock/fallback` 充当主功能。
3. 任何功能如果没有真正的 API / runtime / UI / job 入口，就不能标 `done`。
4. 任何功能如果只有 request schema，没有执行语义，也不能标 `done`。
5. 更新实现时必须同步更新 `FACTS.md`、`IMPLEMENTATION_STATUS.md`、本文件，避免 canonical docs 再次漂移。
