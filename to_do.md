# TO_DO

本文件统一记录当前仓库中尚未对 `IMPLEMENTATION_PLAN.md` 完成收口的项目。

判定标准不是“有没有代码”，而是：

- 是否满足计划中的功能语义
- 是否达到计划中的模块级验收深度
- 是否已经形成可验证、可回放、可持续维护的闭环

---

## 1. Orchestrator: LLM Replan 未落地

### 当前状态
- `server/app/orchestrator/service.py` 只执行 `probe -> plan_check -> DeterministicPlanBuilder`
- `server/app/orchestrator/plan_builder.py` 在 `need_replan=true` 时，仅追加 reason code:
  - `LLM_REPLAN_DEFERRED_TO_DETERMINISTIC_FALLBACK`

### 执行规则
- `clarify loop` 和 `LLM replan` 是两个不同约束，不能混为一谈。
- `clarify loop` 约束：
  - Orchestrator 核心澄清最多 2 轮
  - 即 `clarify_round <= 2`
- `orchestrator replan` 约束：
  - 每个用户 turn 中，Orchestrator 最多只允许 1 次 LLM replan
  - 即 `llm_replan_calls_per_turn <= 1`
- `whole turn` 约束：
  - 整个用户 turn 内允许出现多次 LLM 调用
  - 但这些额外调用只能来自后续 agent 阶段，例如：
    - BJJ Coach 生成
    - validator repair
    - optional eval/judge
- 因此：
  - “最多 2 轮”指的是 clarify，不是 replan
  - “每轮最多 1 次”指的是 Orchestrator replan，不是整个 turn 的总 LLM 调用数

### 建议执行顺序
1. Orchestrator 先做 deterministic `probe`
2. Orchestrator 做 deterministic `plan_check`
3. 仅当 `need_replan=true` 时，允许执行 1 次 LLM replan
4. 对 replan 输出做 schema validation
5. 如果 replan 失败或不合法，立即回退到 deterministic fallback
6. 若仍需补槽位，进入 clarify
7. clarify 累计最多 2 轮
8. Orchestrator 产出最终 `ExecutionPlan`
9. 然后才进入 retrieval 和具体 agent

### replan 触发规则
- 当前代码里，`need_replan` 的判定位已经存在：
  - `domain == MIXED`
  - `evidence_strength < threshold`
  - `clarify_round >= limit` 且仍缺关键槽位
- 但 V1 不应采用“只要 `need_replan=true` 就立刻调用 LLM”的粗粒度策略。
- 已确认的 V1 触发规则如下：

1. 基础门控
- 只有当 `plan_check.need_replan == true` 时，Orchestrator 才允许进入 replan 分支
- 且同一个用户 turn 内必须满足：
  - `llm_replan_invoked == false`

2. 优先触发 replan 的场景
- `CLARIFY_BUDGET_EXHAUSTED`
  - 即核心澄清已达 2 轮，但仍缺关键槽位
  - 这是最优先的 replan 触发点
- `EVIDENCE_STRENGTH_LOW && need_clarify == false`
  - 即槽位已基本足够，但 probe 没形成明显头部证据
  - 这时适合让 replan 改写检索计划，而不是继续问用户

3. 延后触发 replan 的场景
- `domain == MIXED`
  - 若 `clarify_round < 2`，优先走 deterministic `clarify(domain)`
  - 不应因为 `MIXED` 就立即调用 LLM
  - 只有在以下情况才允许从 `MIXED` 进入 replan：
    - 澄清预算耗尽
    - 或 domain 澄清后仍然无法稳定落到单域

4. 推荐决策顺序
- 若 `plan_check.need_replan == false`：
  - 直接进入 deterministic PlanBuilder
- 若 `clarify_budget_exhausted == true`：
  - 执行 1 次 LLM replan
- 若 `evidence_strength_low == true` 且 `need_clarify == false`：
  - 执行 1 次 LLM replan
- 若 `domain == MIXED` 且 `clarify_round < 2`：
  - 优先 deterministic `clarify(domain)`
- 其他需要保底规划的情况：
  - 执行 1 次 LLM replan

5. 设计理由
- 先用 deterministic clarify，能解决的就不消耗 LLM
- `domain=MIXED` 时直接问用户，通常比让 LLM 猜测更可靠
- `evidence_strength_low` 但槽位完整时，replan 最有价值，因为它可以重写 `query_text` 和 retrieval focus
- 该规则与以下约束兼容：
  - `clarify_round <= 2`
  - `Orchestrator 每个用户 turn 最多 1 次 LLM 调用`

### 建议约束落地
- 在 trace 中单独记录：
  - `clarify_round`
  - `llm_replan_invoked`
  - `llm_replan_result = success | schema_invalid | provider_error | skipped`
- 在代码层显式防止：
  - 单个 turn 里 Orchestrator 重复调用 LLM 多次
  - clarify 超过 2 轮后仍继续追问
- fake profile 下也要有可测试的 deterministic mock replan，避免测试依赖真实模型

### 为什么不能收口
- 计划要求的是：
  - 一次性 LLM replan
  - schema validation
  - deterministic fallback
- 当前只有 deterministic plan builder，没有任何 LLM replan 执行路径，也没有 replan 结果的 schema 校验失败分支。
- 因此当前实现只覆盖了 fallback，不覆盖主路径。

### 需要补上的断裂点
- 增加 replan 输入契约与输出 schema
- 增加一次性 replan provider 调用
- 增加 replan 响应校验
- 增加校验失败后的 deterministic fallback
- 把 replan 决策写入 trace

### 建议讨论点
- 已确认：V1 继续坚持 `Orchestrator 在每个用户 turn 中最多只允许 1 次 LLM 调用（即至多 1 次 replan）`
- replan 是否只在 `need_replan=true` 且 `clarify budget exhausted` 时触发
- 已确认：fake profile 下需要 deterministic mock replan，以保证测试、smoke 和 replay 不依赖真实模型

---

## 2. Evaluation: 只有硬指标，没有完整评测闭环

### 当前状态
- `server/app/evaluation/service.py` 只是读取 trace 并聚合 metrics
- `server/app/evaluation/metrics.py` 只计算本地硬指标

### 为什么不能收口
- 计划要求的 Evaluation 不只是“算指标”，还包括：
  - frozen replay runner
  - golden set 执行
  - RAGAS 输入构造与结果聚合
  - LLM-as-judge
  - manual rubric
  - `base/policy` 对比
- 当前实现没有 replay 执行器，也没有 RAGAS/judge/rubric 的任何管线。
- `use_frozen_evidence` 和 `model_variant` 进入 API 后，并没有在评测路径中真正驱动不同执行分支。

### 需要补上的断裂点
- 定义 eval case loader 与 golden set 读取路径
- 增加 frozen replay runner
- 明确 `base` 与 `policy` 的评测执行入口
- 增加 RAGAS input builder
- 增加 judge runner 和手工 rubric 接口
- 输出 trace-linked 失败钻取视图

### 建议讨论点
- 已确认：V1 允许 RAGAS/judge 仅在 `real` profile 下启用；`fake` profile 下统一跳过，并返回结构化 skip 原因
- 已确认：judge 失败不阻塞 eval run，而是降级为 partial result，并结构化记录失败原因与 run 状态
- 已确认：V1 golden set 先走 repo 文件；API 管理延后

---

## 3. Observability: trace_capture_level 还只是轻量占位

### 当前状态
- `server/app/observability/recorder.py` 里 `minimal/debug` 的差异仅体现在 evidence_log 返回逻辑
- `server/app/core/tracing.py` 有 `prompt_hash`、`token_usage`、`cost_estimate` 字段，但当前没有系统化写入策略

### 为什么不能收口
- 计划里的 observability 收口要求是：
  - minimal/debug 两级采集策略明确
  - prompt 默认 hash/version 化
  - debug 模式下允许更丰富快照
  - minimal 模式仍能支持 replay 与审计
- 当前实现还没有：
  - prompt hash 生成与落盘策略
  - raw excerpt / prompt body 的最小化与 debug 化分层
  - capture level 对 generation/retrieval/request 各层的统一裁剪规则

### 需要补上的断裂点
- 定义 capture policy
- 对 prompt / excerpts / validator artifacts 做分级保存
- 写入 prompt_hash
- 确保 minimal 仍能 frozen replay
- 为 debug 模式加额外 smoke/test

### 建议讨论点
- minimal 模式是否允许保存摘要级 prompt snapshot
- replay 所需的最小 generation input 到底保留哪些字段

---

## 4. SFT: 还没有训练与对比闭环

### 当前状态
- `server/app/sft/service.py` 已支持：
  - dataset export
  - train rows 构造
  - checkpoint manifest 注册
  - model variant 解析
- 但训练本身没有在 repo runtime 中形成闭环

### 为什么不能收口
- 计划要求的是：
  - trace -> dataset
  - 人工修订 train set
  - LoRA/QLoRA 训练
  - policy artifact 注册
  - base/policy replay + eval 对比
- 当前实现只做到了前半段的数据准备和元数据登记。
- 没有训练执行器接入，也没有训练后自动进入 replay/eval 的联动。

### 需要补上的断裂点
- 定义 training runner 接口
- 对接 `train_policy_lora.py` 或等价执行路径
- 训练产物注册到 runtime config / policy registry
- replay/eval 中真正使用训练后的 policy artifact

### 建议讨论点
- V1 的训练是否只要求 dry-run 可验证，还是要求真训练完成
- policy artifact 是本地路径优先，还是抽象成 registry URI

---

## 5. Profile Persistence: 现在只是内存态

### 当前状态
- `server/app/storage/sqlite_schema.py` 已有 `profiles` 表
- `server/app/api/app.py` 的 `/api/profile` 读写 `state.current_profile`
- 当前没有 profile repository / persistence flow

### 为什么不能收口
- 有 schema 不等于能力完成。
- 当前 profile 更新不会写入 SQLite，不支持重启恢复，也不能查询历史版本。
- 所以“版本化 profile”在行为上并不存在，只在数据结构层面占了位。

### 需要补上的断裂点
- 新增 profile repository
- `GET/PUT /api/profile` 接入持久化
- 记录 `created_at` 和当前激活版本
- trace 中稳定引用 `profile_version_id`

### 建议讨论点
- V1 只保留 latest profile，还是允许 profile version history 查询

---

## 6. Vector Store: 目前是 JSON 持久化，不是真实 Chroma 适配

### 当前状态
- `server/app/storage/vector_store.py` 现在实现的是本地 JSON 持久化向量存储
- dense retrieval 与 reembed 已接通

### 为什么不能收口
- 计划要求的是 Chroma persistent adapter。
- 当前实现满足了“向量检索闭环”，但没有完成“真实 Chroma 适配”这一技术目标。
- 这意味着：
  - 没有真实客户端依赖接入
  - 没有 Chroma collection 生命周期管理
  - 没有验证与 Chroma 行为一致

### 需要补上的断裂点
- 引入真实 Chroma adapter
- 保留当前接口，替换底层实现
- 补 doc-version / embedding-version 隔离测试

### 建议讨论点
- 是否保留 JSON adapter 作为 fake/local fallback

---

## 7. Web Frontend: 现在是静态 shell，不是计划中的 Next.js 前端

### 当前状态
- 已有 `web/` 本地静态界面
- FastAPI 会挂载 `/` 和 `/ui`
- 可演示健康检查、文本导入、聊天与 trace 浏览

### 为什么不能收口
- 计划和 spec 中的目标是：
  - Next.js + React
  - 前后端契约对齐
  - 页面/组件/容器分层
- 当前实现只是 demo shell：
  - 没有 Next.js 工程
  - 没有构建链
  - 没有前后端类型同步
  - 没有真正页面级路由结构

### 需要补上的断裂点
- 搭建 Next.js app
- 建立 API client 与类型同步
- 迁移当前 shell 为正式页面与组件

### 建议讨论点
- 是否保留当前静态 shell 作为 fallback/demo 模式

---

## 8. FACTS.md: canonical 文档已过期

### 当前状态
- `FACTS.md` 仍描述 repo 处于 spec-only 阶段
- 实际仓库已经有 server、tests、web shell、pyproject、storage wiring

### 为什么不能收口
- 这是 canonical file。
- 一旦 canonical 文档和真实实现不一致，后续自动化实现、review、交接都会被错误基线污染。
- 这不是功能缺口，但属于项目状态未收口。

### 需要补上的断裂点
- 更新 `FACTS.md`
- 对齐当前 repo baseline、已实现模块、剩余缺口

### 建议讨论点
- 是否顺带补一份完成度矩阵，避免后续再次失真

---

## 建议补口顺序

1. Orchestrator LLM replan
2. Profile persistence
3. Observability capture policy
4. Evaluation frozen replay + golden set
5. SFT training/eval loop
6. Chroma real adapter
7. Next.js frontend
8. FACTS.md 同步

说明：
- 第 1~5 项属于“功能语义没有完成”
- 第 6~7 项属于“技术落地与目标架构仍不一致”
- 第 8 项属于“文档状态未收口”
