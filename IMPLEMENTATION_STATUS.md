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
| Ingestion + safe_summary | `done` | text/file/dir/record ingest 与 safe_summary job 已可运行 | 无关键断裂点 |
| Retrieval + Evidence Pack | `done` | structured + BM25 + dense + RRF + Evidence Pack 已接通 | 无关键断裂点 |
| Orchestrator | `done` | probe、plan_check、clarify、fake mock replan、real-profile OpenAI-compatible replan provider、fallback telemetry 已接通 | 无关键断裂点 |
| Agents | `done` | BJJ coach、literary、validator-safe path 已可运行 | 无关键断裂点 |
| Observability + Replay | `done` | minimal/debug capture、trace detail、frozen replay 已接通 | 无关键断裂点 |
| Evaluation | `partial` | golden set、frozen replay、hard metrics、OpenAI-compatible external RAGAS/judge、partial-result flow 已接通 | manual rubric 未接入 |
| SFT | `partial` | dataset export、train rows、policy artifact、registry/replay/eval wiring 已接通 | 训练 backend 仍是 `local_policy_memory_v1`，不是真实 LoRA/QLoRA |
| API | `done` | ingest/chat/retrieve/traces/replay/eval/sft/profile API 已有 | 无关键断裂点 |
| Profile Persistence | `done` | SQLite 持久化、启动恢复、history API 已接通 | 无关键断裂点 |
| Web Frontend | `partial` | Next.js App Router 前端已接入，覆盖 dashboard/chat/traces/evaluation 基线，并补了稳定 fixture 与组件测试 | 前后端类型自动同步、SSE/streaming，以及浏览器级端到端回归仍未接入 |
| Canonical Docs | `partial` | `FACTS.md` 已与当前仓库重新对齐 | 后续每轮实现仍需持续同步状态文档 |

## Highest-Priority Remaining Work

1. 把 SFT 的 `local_policy_memory_v1` 升级为真实 LoRA/QLoRA 训练闭环。
2. 补前后端类型自动同步、SSE/streaming 和浏览器级端到端回归。
3. 为 Evaluation 接入 manual rubric。

## Notes

- 本文档用于高层完成度判断，不替代更细的未收口说明；细项仍以 `to_do.md` 为准。
- `Vector Store` 已不再是未收口项：当前仓库已使用真实持久化 Chroma 适配。
