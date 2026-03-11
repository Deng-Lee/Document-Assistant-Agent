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
| `safe_summary` job orchestration | `partial` | 真实 summary provider、`summary_model` / `summary_prompt_version` / `summary_status` / `summary_error_code`、以及 rebuild API 已接上，不再是纯 fallback 占位；但 spec 里要求的显式失败重试与更完整运维闭环还未完全收口。 | [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L367), [server/app/jobs/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/jobs/service.py#L76), [server/app/jobs/safe_summary_provider.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/jobs/safe_summary_provider.py), [server/app/api/app.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/app.py#L260) |
| Maintenance APIs: `safe_summary/rebuild`, `maintenance/reindex`, `maintenance/reembed` | `partial` | 底层 job 类型存在，但 spec 要求的专门 API 入口、`doc_id|all` scope 和运维契约没有落地。现在只有通用 jobs list/run-next，属于入口断层。 | [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L1937), [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L1944), [server/app/api/app.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/app.py#L249), [server/app/jobs/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/jobs/service.py#L67) |
| Retrieval mainline: structured + BM25 + dense + RRF | `done` | 主 hybrid retrieval 方案已落地。 | [server/app/retrieval/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/retrieval/service.py) |
| Cross-encoder reranker | `partial` | `real` profile 主路径现已切到本地 Hugging Face cross-encoder backend，不再是 chat scorer proxy；但默认开发环境尚未安装 `torch/transformers`，因此 readiness 仍是环境层面的未收口。 | [server/app/retrieval/reranker.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/retrieval/reranker.py), [config/model_profiles/real.json](/Users/lee/Documents/AI/Document%20Assistant%20Agent/config/model_profiles/real.json), [pyproject.toml](/Users/lee/Documents/AI/Document%20Assistant%20Agent/pyproject.toml) |
| Orchestrator: probe / plan_check / clarify / one-shot replan | `done` | 主执行链与 fake/real 两条路径都已接入，且有 fallback telemetry。 | [server/app/orchestrator](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/orchestrator) |
| BJJ coach pipeline | `done` | gate、validator、repair/degrade 和输出模式已接通。 | [server/app/agents/bjj_coach](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/agents/bjj_coach) |
| Literary pipeline `top-1 raw_excerpt + top-2/3 safe_summary anchors` | `done` | NOTES 域现已按 spec 生成 top-1 `raw_excerpt` 与 top-2/3 `safe_summary` anchors，并通过 provider-backed generation path 输出文本；`raw_excerpt` 会从持久化 chunk 原文读取并执行注入文本/代码块清洗。 | [IMPLEMENTATION_PLAN.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/IMPLEMENTATION_PLAN.md#L165), [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L1690), [server/app/agents/literary/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/agents/literary/service.py), [server/app/agents/literary/provider.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/agents/literary/provider.py) |
| Observability: trace/span/event and replay | `done` | 主 trace/replay 能力和 minimal/debug capture 已有。 | [server/app/observability](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/observability) |
| Observability strictness: minimal/debug capture semantics | `partial` | 主体是有的，但 `minimal` 目前仍保留完整 `query_original/query_clean` 等 replay 输入；是否满足 spec 所述“最小化留痕”还偏宽。语义基本可用，但未到完全收口。 | [server/app/observability/recorder.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/observability/recorder.py#L179) |
| Replay override metadata | `partial` | 请求 schema 里有 `override_generation_config`，但执行链未消费，也未回写 trace。属于“接口形状在，主语义未落地”。 | [IMPLEMENTATION_PLAN.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/IMPLEMENTATION_PLAN.md#L259), [server/app/api/models.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/models.py#L25), [server/app/api/app.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/app.py#L265) |
| Evaluation hard metrics | `done` | 主硬指标路径已接通。 | [server/app/evaluation/metrics.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/evaluation/metrics.py) |
| Evaluation manual rubric | `done` | 存储、API、聚合结果均已接通。 | [server/app/evaluation/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/evaluation/service.py), [server/app/api/app.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/app.py#L299) |
| RAGAS evaluator | `drift` | 当前实现是 `openai_ragas_proxy_v1`，不是严格意义上的 RAGAS 流程；而且 contexts 构造没有按 spec 区分 NOTES 的 `raw_excerpt` 和 `safe_summary`。不能把这个写成“真实 RAGAS 已完成”。 | [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L2230), [server/app/evaluation/external_evaluators.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/evaluation/external_evaluators.py#L54), [server/app/evaluation/external_evaluators.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/evaluation/external_evaluators.py#L222) |
| LLM-as-judge | `partial` | 已有外部 judge API 调用和结构化结果，但还没有按 spec 形成更细的 error tags / 抽样策略 / 评审分层。主方向有了，验收深度未完全到位。 | [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L2267), [server/app/evaluation/external_evaluators.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/evaluation/external_evaluators.py#L123) |
| SFT export / training / policy replay | `done` | 主训练、注册、激活、policy replay/eval 已接通。 | [server/app/sft/service.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/sft/service.py) |
| SFT readiness in default dev env | `partial` | 代码路径已具备，但默认开发环境依赖未就绪，这仍是环境层面的未收口。 | [FACTS.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/FACTS.md), [server/app/api/__main__.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/__main__.py) |
| Profile persistence and history | `done` | 持久化、启动恢复、history API 已接通。 | [server/app/api/app.py](/Users/lee/Documents/AI/Document%20Assistant%20Agent/server/app/api/app.py#L337) |
| Web frontend baseline | `partial` | Next.js、SSE、contract sync、component test、Playwright 已有；但 spec 点名的 Tailwind + shadcn/ui 当前并未接入，不能说完全等价于原方案。 | [DEV_SPEC.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/DEV_SPEC.md#L64), [web/package.json](/Users/lee/Documents/AI/Document%20Assistant%20Agent/web/package.json#L1) |
| Canonical plan doc baseline accuracy | `drift` | `IMPLEMENTATION_PLAN.md` 的“当前基线”仍写 repo 是 spec-only，和当前仓库事实不符。canonical plan 文档没有随实现同步。 | [IMPLEMENTATION_PLAN.md](/Users/lee/Documents/AI/Document%20Assistant%20Agent/IMPLEMENTATION_PLAN.md#L11) |

## Summary

当前仓库并不是“还有一点点文档没同步”这么简单，而是存在三类差异：

1. `done`
   主链路真实落地，且具备入口和验证。
2. `partial`
   能力部分可用，但还缺 spec 要求的入口、执行语义或验收深度。
3. `drift`
   代码用替代实现取代了原定方案，或者 canonical 文档本身已经失真。

## Implementation Discipline For Next Steps

后续修复时必须遵守：

1. 先修 `drift`，再谈新增能力。
2. 修复时必须优先恢复 spec 原语义，不允许继续用 `proxy/mock/fallback` 充当主功能。
3. 任何功能如果没有真正的 API / runtime / UI / job 入口，就不能标 `done`。
4. 任何功能如果只有 request schema，没有执行语义，也不能标 `done`。
5. 更新实现时必须同步更新 `FACTS.md`、`IMPLEMENTATION_STATUS.md`、本文件，避免 canonical docs 再次漂移。
