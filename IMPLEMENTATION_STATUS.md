# IMPLEMENTATION STATUS

基于当前仓库代码状态，对 `IMPLEMENTATION_PLAN.md` 的完成度做模块级标记。

状态含义：
- `done`：主链路与计划验收语义基本对齐
- `partial`：已有可运行实现，但仍存在关键断裂点
- `missing`：目标能力尚未形成有效实现

## Matrix

| Module | Status | Current Repo State | Remaining Gap |
| --- | --- | --- | --- |
| Core Contracts & Schemas | `done` | core schema、runtime config、trace/eval/sft contracts 已落地 | 无关键断裂点 |
| Storage Adapters | `done` | SQLite、FTS5、filestore、trace store、jobs、profiles、真实 Chroma 已接通 | 无关键断裂点 |
| Ingestion + safe_summary | `partial` | text/file/dir/record ingest、provider-backed safe_summary job、summary metadata、rebuild API 已接通 | 显式失败重试与完整 maintenance 闭环仍未完全收口 |
| Retrieval + Evidence Pack | `partial` | structured + BM25 + dense + RRF + Evidence Pack 已接通，`real` profile 的主 rerank 路径已换成真实 HF cross-encoder backend | 默认开发环境尚未安装 rerank 所需 `torch/transformers`，cross-encoder readiness 仍是环境层面的缺口 |
| Orchestrator | `done` | probe、plan_check、clarify、fake mock replan、real-profile OpenAI-compatible replan provider、fallback telemetry 已接通 | 无关键断裂点 |
| Agents | `done` | BJJ coach、NOTES literary 的 `top-1 raw_excerpt + top-2/3 safe_summary` anchors pipeline、validator-safe path 已可运行 | 无关键断裂点 |
| Observability + Replay | `done` | minimal/debug capture、trace detail、frozen replay 已接通 | 无关键断裂点 |
| Evaluation | `partial` | golden set、frozen replay、hard metrics、真实 RAGAS backend 结构、OpenAI judge、manual rubric、partial-result flow 已接通 | 默认开发环境尚未安装 `.[evaluation]`，且 judge 的细粒度分层/error tags 仍未完全收口 |
| SFT | `done` | dataset export、真实 HF LoRA/QLoRA 训练 runner、policy artifact 注册、adapter-backed policy replay/eval 已接通 | 无关键断裂点 |
| API | `done` | ingest/chat/retrieve/traces/replay/eval/sft/profile API 已有 | 无关键断裂点 |
| Profile Persistence | `done` | SQLite 持久化、启动恢复、history API 已接通 | 无关键断裂点 |
| Web Frontend | `done` | Next.js App Router 前端已接入，并补齐了前后端契约同步、chat SSE/streaming、组件测试，以及 Playwright 浏览器级端到端回归 | 无关键断裂点 |
| Canonical Docs | `partial` | `FACTS.md` 已与当前仓库重新对齐 | 后续每轮实现仍需持续同步状态文档 |

## Highest-Priority Remaining Work

1. 在默认开发环境补齐 `.[training]`、`.[rerank]`、`.[evaluation]` 与 adapter inference 依赖，把 SFT / cross-encoder / RAGAS readiness 从环境层面的 `False` 收敛到 `True`。
2. 继续收口审计清单里剩余的 `partial` 项，尤其是 maintenance API、replay override metadata、judge 分层/error tags。
3. 继续随代码变更维护 `FACTS.md`、`IMPLEMENTATION_STATUS.md` 和 `to_do.md`，避免文档基线再次漂移。

## Notes

- 本文档用于高层完成度判断，不替代更细的未收口说明；细项仍以 `to_do.md` 为准。
- `Vector Store` 已不再是未收口项：当前仓库已使用真实持久化 Chroma 适配。
