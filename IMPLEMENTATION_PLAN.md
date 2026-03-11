# IMPLEMENTATION_PLAN（实现计划）

## 目标（Objective）
按照 `DEV_SPEC.md` 定义，构建 V1 Personal Document Assistant：一个**可回放（replayable）**、**可本地部署（locally deployable）**的单用户系统，具备：
- 面向 BJJ 训练日志与 Notes 的 Hybrid RAG
- 可审计的 Evidence Pack 与引用纪律（citation discipline）
- Orchestrator 的澄清循环（clarification loop）
- BJJ 与 Literary 两类 Agent
- 端到端可观测性、回放、离线评估，以及 Policy SFT

## 当前基线（Current Baseline）
- 当前仓库已经不再是 `spec-only`：`server/`、`web/`、`scripts/`、`datasets/`、`data/` 等主目录均已落地，后端主链路、Next.js 前端基线、trace/replay、eval、SFT 与测试入口均已接通。
- `DECISIONS.md` 仍是关键决策来源，但本计划文件现在应被视为“对照 DEV_SPEC 的实现基线与收口参考”，而不是 greenfield 脚手架计划。
- `OPEN_QUESTIONS.json` 当前没有阻塞性确认项；未收口能力以 `IMPLEMENTATION_AUDIT.md`、`IMPLEMENTATION_STATUS.md`、`to_do.md` 为准。

## 交付原则（Delivery Principles）
- 仅实现 Phase 1 / V1；除非为可回放性或 validator 安全性所必需，否则推迟 V1.1+ 项。
- 保持模块依赖单向：`core -> storage -> ingestion/retrieval/orchestrator/agents -> observability/evaluation/sft -> api/ui`。
- 所有会影响行为的阈值或 prompt 必须版本化，并写入 `runtime_config_snapshot`。
- 优先使用确定性逻辑处理：路由、gate、校验、回放、评估；仅在 spec 明确要求处使用 LLM。
- 在用户明确请求之前，不要脚手架化或实现缺失目录。

## 构建顺序（Build Order）

### 1. Core Contracts & Schemas（核心契约与 Schema）
范围（Scope）：
- 在 `server/app/core` 中定义权威 schema，用于：
  - runtime config 与 version ids
  - document、doc version、chunk、embedding version、profile version
  - `source_locators`
  - retrieval plan、probe stats、plan check、execution plan
  - Evidence Pack 与 rank signals
  - chat 响应联合类型：`clarify_request | final_answer`
  - BJJ answer JSON modes：`FULL | AMBIGUOUS_FINAL | LOW_EVIDENCE`
  - trace/span/event 的 payload
  - eval case/result 与 SFT export sample
- 定义枚举与错误码：BJJ 校验、gate reasons、clarify slots、task/domain 值、job status。
- 为所有 spec 阈值与版本化 prompt ids 定义 `runtime_config` 默认值。

实现说明（Implementation notes）：
- 使用 Pydantic models，并支持导出 JSON Schema。
- 将 `doc_version_id`、`embedding_version_id`、`prompt_version`、`policy_version`、`trace_capture_level` 视为 trace 链路的必填项。
- 契约由后端拥有（backend-owned）；前端类型应后续由同一源生成或镜像，避免漂移。

验收标准（Acceptance criteria）：
- Chat turn 的输出必须能被表达为**且仅能表达为** `clarify_request` 或 `final_answer` 之一。
- BJJ answer schema 必须编码第 7 章与 `contracts.md` 中的 validator 规则。
- Evidence Pack 契约必须要求：`evidence_id`、`doc_id`、`doc_version_id`、`locator`、`safe_summary`、`metadata_digest`、`rank_signals`。
- Trace 契约必须要求：`runtime_config_snapshot`、`request_log`、`retrieval_log`、`evidence_log`、`generation_log`。

### 2. Storage Adapters（存储适配层）
范围（Scope）：
- 实现以下仓储与适配器接口：
  - SQLite 元信息存储（metadata store）
  - SQLite FTS5 索引
  - raw markdown 快照的 file store
  - Chroma 向量库（按 `embedding_version_id` 隔离）
  - trace store（结构化 logs + 可选 excerpt snapshots）
  - job 状态持久化
- 为 documents、versions、chunks、embeddings、traces、eval runs、profiles、jobs 建立存储 schema 与迁移（migrations）。
- 按 spec 建立单一真相（single-source-of-truth）划分：
  - SQLite：元信息/日志/过滤
  - file store：原始源文件快照
  - Chroma：dense retrieval

实现说明（Implementation notes）：
- 每条 citation 与 locator 都必须绑定到 `doc_version_id`。
- reindex/reembed 必须支持 `doc_version_id | doc_id | all` 的作用域。
- 必须持久化足够的信息，使 Evidence Pack 与 frozen replay 可重建，而无需在线重检索。

验收标准（Acceptance criteria）：
- FTS5 与 Chroma 适配器必须通过稳定的 repository interface 访问，避免把存储细节向上泄漏。
- embedding 数据按 `embedding_version_id` 隔离。
- trace 回读能在不查询在线索引的情况下重建 frozen evidence 集合。
- 运维操作在执行前能枚举受影响的 chunks（用于 dry-run/成本评估）。

### 3. Ingestion + safe_summary Job（导入 + safe_summary 后台任务）
范围（Scope）：
- 实现 markdown loader（换行归一化 + `locator_index` 生成）。
- 实现基于 frontmatter 的 doc type 识别（`BJJ` 或 `notes`）。
- 实现 BJJ 结构化 parser 与 validator（必填字段 + 枚举约束）。
- 实现 NOTES 结构抽取（支持 heading path）。
- 实现 chunking：
  - BJJ：每条训练记录一个 chunk
  - NOTES：语义/段落切分并携带 heading anchors
- 实现基于 loader 产出的 `locator_index` 生成 `source_locators`。
- 实现 raw/clean 双流派生文本：
  - raw snapshot 用于 replay/excerpts
  - clean text 用于 FTS 与 embedding
- 实现 `safe_summary` 后台任务的入队、重试、重建、持久化。

实现说明（Implementation notes）：
- V1 的 BJJ ingestion 是严格且模板驱动的（strict and template-driven）。
- 非法 BJJ 记录必须在索引前失败，并输出结构化错误码。
- 导入必须以足够“原子性”的方式持久化：`DocVersion`、文件快照、chunks 与索引输入，避免半导入版本。

验收标准（Acceptance criteria）：
- `POST /api/ingest/file`、`POST /api/ingest/dir`、`POST /api/record/bjj`、`POST /api/record/notes` 均可产出版本化的 chunk 产物。
- 每个 chunk 都有绑定 `doc_version_id` 的稳定 `source_locators`。
- `safe_summary` 可通过 job 接口按 chunk 重建。
- 缺失 `position`、`orientation`、`distance`、`goal`、`your_action`、`opponent_response` 的 BJJ 记录必须被确定性拒绝。

### 4. Retrieval + Evidence Pack（检索 + Evidence Pack）
范围（Scope）：
- 实现 query parsing → `retrieval_plan`。
- 实现基于 SQLite 字段的 structured filtering。
- 实现基于 FTS5 的 BM25 retrieval。
- 实现基于 Chroma 的 dense retrieval。
- 实现 RRF 融合、按文档多样性（per-document diversity）、token budget 裁剪，以及 rank logging。
- 构建 Evidence Pack：作为下游生成与回放的唯一证据来源。

实现说明（Implementation notes）：
- V1 使用 RRF，而不是 score-weighted fusion。
- V1 在 probe 阶段采用 histogram-only 的 domain scoring。
- 必须记录所有应用侧过滤与 topK 扩张，以确保检索可审计。

验收标准（Acceptance criteria）：
- `POST /api/retrieve` 返回 `retrieval_log` 与 `evidence_pack`，字段满足 core schemas 的契约定义。
- Evidence Pack 对每条 entry 保留 `doc_version_id` 与精确 locator 数据。
- 过滤行为在回放中可见（包含丢弃数量与最终保留 hits）。
- Pack 构建尽量强制 `N_per_doc`、`M_docs`，并做 token-budget-aware 裁剪。

### 5. Orchestrator（probe/replan/clarify）
范围（Scope）：
- 实现对话状态（conversation state），包含：
  - `pending_slot`
  - orchestrator `clarify_round`（最多 2）
  - confirmed slots
  - coach clarify state 命名空间
- 实现 Hard Guard A（写入路径 short-circuit）。
- 实现 pending-slot short-circuit parsing。
- 实现 PROBE retrieval 与 `probe_stats`。
- 实现 `plan_check`。
- 实现 deterministic plan builder。
- 实现一次性 LLM replan（带 schema 校验）+ 确定性 fallback。
- 实现 executor，将控制流交给 retrieval 与 agents。

实现说明（Implementation notes）：
- 按 `DECISIONS.md`，初始默认值为：
  - 最小写入意图前缀词表（minimal write-intent prefix list）
  - `domain_score = p_bjj`
  - `domain_score` 阈值 `0.65 / 0.35`
  - `slot_entropy > 0.6`
  - `evidence_strength < 0.4`
  - 当预算允许时，`MIXED` 先澄清 domain
- 每个用户 turn 最多触发 1 次 LLM（Orchestrator 层）。
- Clarify 必须模板化（template-driven），不能输出自由文本提问。

验收标准（Acceptance criteria）：
- `POST /api/chat/turn` 可返回 Orchestrator 发起的 `clarify_request`，或继续走检索。
- Orchestrator 不得超过 2 轮核心槽位澄清。
- `ExecutionPlan` 必须始终可追溯、schema-valid，并写入 trace。
- LLM replan 失败必须回退到 deterministic planning，并且不能让本轮崩掉。

### 6. Agents（BJJ coach + literary）
范围（Scope）：
- 实现 BJJ Coach pipeline：
  - request semantics
  - evidence summary
  - evidence gate
  - 针对 `opponent_control` 的单槽位战术澄清
  - mode-aware generation
  - validator
  - repair 一次，然后确定性降级（degrade）
- 实现 Literary pipeline：
  - 只消费 NOTES 域检索结果
  - top-1 `raw_excerpt` + top-2/3 `safe_summary` anchors
  - prompt 组装与引用纪律
- 实现 provider 抽象：支持 base vs policy 模型选择。

实现说明（Implementation notes）：
- BJJ Coach 只能消费 retrieval 提供的 frozen Evidence Pack（不得扩大证据域）。
- `coach_clarify_round` 上限为 1。
- Validator 是产品关键路径（product-critical），不是可选清理步骤。

验收标准（Acceptance criteria）：
- BJJ 输出模式必须满足第 7 章策略：
  - `HIGH_EVIDENCE -> FULL`
  - `AMBIGUOUS + 澄清耗尽 -> AMBIGUOUS_FINAL`
  - `LOW_EVIDENCE -> LOW_EVIDENCE`
- BJJ 模式下所有“用户历史”断言必须引用 allowed evidence ids，或标记 generic。
- 最终 BJJ 输出中绝不出现 `followup_question`。
- Literary 最终答案返回文本 + anchors，anchors 必须指向版本化 citations。

### 7. Observability（trace/span/event）
范围（Scope）：
- 实现 trace/span/event 模型与持久化。
- 对导入、record 写入、检索、编排、gate、LLM 调用、validator、jobs 做打点。
- 每个用户可见 trace 必须捕获 `runtime_config_snapshot` 与相关 version ids。
- 实现 trace 详情与 replay 接口。
- 实现 `trace_capture_level`：minimal vs debug 的存储行为。

实现说明（Implementation notes）：
- 默认留存应偏向结构化日志 + locators + summaries。
- prompt body 默认只存 hash/version；仅 debug mode 存更多内容。
- replay 必须支持 frozen evidence 下的 `model_variant=base|policy` 对比。

验收标准（Acceptance criteria）：
- `GET /api/traces/{trace_id}` 能重建请求路径、证据选择、生成输出与 validator 结果。
- `POST /api/replay/{trace_id}` 能在不走在线检索的情况下基于 frozen evidence 重跑生成，避免 drift。
- trace events 必须包含：stage transitions、clarify events、retrieval plan 快照、模型/token/cost 元数据。
- minimal 模式避免存 raw excerpt，同时仍保留 replay 与 citation 审计所需信息。

### 8. Evaluation（frozen replay + metrics + RAGAS + judge）
范围（Scope）：
- 在 `datasets/golden` 下定义 golden set 存储。
- 实现 base/policy variants 的离线 replay runner。
- 从 traces 与 validator reports 直接计算 hard metrics。
- 为 NOTES 与“渲染后的 BJJ 答案”构造 RAGAS 输入。
- 实现可选的 LLM-as-judge 与人工 rubric 集成。
- 提供评测 API 与结果视图。

实现说明（Implementation notes）：
- 默认评测模式为 Frozen Evidence Replay。
- live retrieval replay 是可选且次要的。
- hard metrics 是一等公民（first-class），因为它更贴近产品契约，而不是仅依赖 judge 打分。

验收标准（Acceptance criteria）：
- `POST /api/eval/run` 能执行命名评测集并产生持久化的 `eval_run_id`。
- `GET /api/eval/results` 报告需包含：
  - schema compliance
  - mode-policy consistency
  - allowed citation accuracy
  - citation coverage
  - Plan C branch count
  - drill completeness
  - low-evidence safety proxy
  - latency 与 cost 汇总
- 所有失败输出必须 trace-linkable，便于 drill-down 到底层 replay。

### 9. SFT（dataset export + revision + LoRA/QLoRA training + base/policy replay）
范围（Scope）：
- 实现 trace → dataset 导出到 `datasets/sft/v1/<date>/`。
- 产出 `manifest.json` + JSONL 样本行（包含 runtime snapshot、evidence whitelist、selected evidence、baseline output、validator report）。
- 定义人工修订流程产出 `train.jsonl`。
- 集成 LoRA/QLoRA 训练入口与 policy 产物注册（artifact registration）。
- 将 `policy` variant 接入 replay 与 evaluation。

实现说明（Implementation notes）：
- SFT 训练的是“行为策略（behavior policy）”，不是 BJJ 技术知识。
- 训练输入必须与线上生成输入严格对齐。
- 即使 policy 训练上线，生产环境仍保留 validator 与 fallback。

验收标准（Acceptance criteria）：
- `POST /api/sft/export`（或等价导出管线）产出版本化数据集产物，并保留 `trace_id`。
- 训练可先以 dry-run 模式演练，再进行昂贵训练。
- replay 与 eval 能在 frozen evidence 下对比 `base` vs `policy`。
- 提升与回归都能通过同一条 hard-metric report 路径可视化（与 base 同口径）。

## 跨模块验收标准（Cross-Cutting Acceptance Criteria）
- API 响应契约：
  - Chat turns 返回的必须且仅能是 `clarify_request` 或 `final_answer`。
  - Clarify payload 必须包含：`who`、`slot`、`options`、`template_id`、`round`、`why`。
  - 最终 BJJ answers 必须始终是 schema-valid 的终态对象（terminal objects）。
- Validator 行为：
  - 每个 BJJ final answer 必须运行 validator。
  - 仅允许一次 repair 尝试。
  - 若仍无效，则确定性降级到 `LOW_EVIDENCE`。
- Replay 保证：
  - Frozen evidence replay 不得依赖在线检索。
  - 每次 replay turn 必须包含原始 `runtime_config_snapshot` 与 override 元数据。
  - Citations 必须能基于绑定 `doc_version_id` 的 locators 解析。
- Evaluation 输出：
  - 每次 eval run 必须存储指标、配置、时间戳、模型 variant 与 trace links。
  - 报告必须支持 base/policy 对比，且不改变指标定义。

## 计划确认后的建议执行顺序（Suggested Execution Sequence After Planning Approval）
1. 仅运行 scaffold 的 dry-run。
2. 优先搭建 core contracts 与 storage skeleton。
3. 在 agent 生成之前，把 ingestion 与 retrieval 做到可测试的 baseline。
4. 在 Literary 打磨之前，先打通 orchestrator + BJJ validator 关键链路。
5. 在大规模评测或 SFT 导出之前，先把 traces 与 replay 打通。
6. 最后再生成数据集，跑 LoRA/QLoRA dry-run，并对比 base vs policy。
