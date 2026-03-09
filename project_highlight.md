# Project Highlights

下面是按 `RAG / Agent / 工程 / SFT` 四类重组后的 12 个项目亮点，均可直接从 `DEV_SPEC.md` 和 `IMPLEMENTATION_PLAN.md` 落到工程实现层，不是空泛概念。

## RAG

### 1. 从静态 Hybrid Retrieval 升级为编排驱动的 Agentic RAG

- Probe 小检索：系统不会直接拿用户原始 query 去做最终检索，而是先做一次轻量 probe，只读取 `safe_summary` 和结构信号，用来判断当前问题更像 BJJ 还是 Notes、是否带时间意图、槽位是否缺失、证据是否足够集中。
- `probe_stats`：probe 不只是“试搜一下”，而是产出 `domain_score`、`slot_entropy`、`time_signal`、`evidence_strength` 等中间信号。这样后续决策有明确依据，而不是靠模型拍脑袋判断。
- Plan Check：系统根据 probe 信号决定下一步是直接检索、先澄清，还是触发一次 LLM replan。这里检索已经不是固定流水线，而是被状态机调度的一部分。
- Clarification Loop：当 query 缺少关键槽位时，系统不会硬搜，而是先向用户补齐 `position / orientation / goal / date_range` 等信息，再重新进入检索。也就是说，query 是可以被交互式完善的。
- Retrieval Plan：真正进入 Hybrid Retrieval 的不是原始问题，而是经过 slot merge、probe 判断、必要时 query rewrite 后的结构化 `retrieval_plan`。这样 structured filter、BM25、dense retrieval 的输入更稳定。
- Evidence Pack：检索的最终产物不是“若干文本片段”，而是冻结的、可审计的 Evidence Pack。下游 BJJ Coach 和 Literary Agent 只能基于它生成，这让检索结果真正进入了 Agent 决策闭环。
- 这个亮点最关键的地方在于：系统里的“检索”不是一次性动作，而是一个被编排器调度、可被澄清和重规划驱动的过程。这正是 Agentic RAG 与传统 RAG 的本质区别。
- 面试话术：我把传统的“问题进来就检索”改造成了一个 state-driven 的 Agentic RAG 流程，先 probe、再判断是否澄清或重规划，最后才进入正式检索和证据打包。这样检索不再是静态步骤，而是整个智能体决策过程的一部分。

## Agent

### 2. Orchestrator 不是分类器，而是带 Probe 的编排器

- Hard Guard：优先分流写入和对话，避免把 record 请求误入 RAG 链路。
- Pending-slot short-circuit：若上一轮刚问过 slot，优先走 slot parser，不重复跑整套意图识别。
- PROBE：在正式检索前做一次轻量证据探测，不是为了回答问题，而是为了降低意图与域判断的不确定性。
- `probe_stats`：显式产出 `domain_score`、`slot_entropy`、`time_signal`、`evidence_strength` 等中间信号，使后续决策可解释。
- 这个点体现的是 Agent 设计能力：不是简单“让 LLM 识别意图”，而是让系统先通过证据分布建立上下文，再让模型只在必要时参与。
- 面试话术：我把意图识别做成了一个轻量编排器，先 probe 证据，再决定是否需要 LLM 参与规划。这样 LLM 不负责拍脑袋分类，而是基于系统信号做受控规划。

### 3. Plan Check + Replan：把 LLM 放在“该用的地方”

- `plan_check`：根据 probe 信号判断接下来是 clarify、retrieve 还是 replan。
- LLM Replan：只在规则不足时触发一次，把用户 query 改写成更适合检索和执行的结构化计划。
- Deterministic fallback：LLM replan 失败时回退到确定性流程，不让 turn 崩掉。
- 这里解决的是纯规则太僵、纯 LLM 太飘的问题。你实际上做的是“LLM 受状态机约束”的半自治编排。
- 面试话术：我没有让 LLM 全权决定下一步，而是先用 plan_check 筛掉大部分可确定场景，只在证据不足以支持规则决策时才调用一次重规划。

### 4. Clarification Loop 不是泛泛追问，而是分层追问体系

- Orchestrator Clarify：负责核心槽位，最多两轮，解决的是“检索无法聚焦”的问题。
- BJJ Coach Clarify：只问 `opponent_control`，最多一轮，解决的是“建议可执行性不足”的问题。
- 追问不是开放式自然语言，而是模板化、结构化的 `clarify_request`。
- 这说明你理解了一个关键点：不同阶段问问题的目的不一样，不能混成一个“统一追问模块”。
- 面试话术：我把澄清分成了两层，前层为检索补槽位，后层为战术建议补关键信息。这样每次提问都有明确目标，而不是为了“多轮对话”而多轮对话。

### 5. BJJ Coach 的 Gate 是一个策略状态机，不是置信度标签

- `HIGH_EVIDENCE / AMBIGUOUS / LOW_EVIDENCE` 不是感性标签，而是由结构化证据信号驱动。
- `HIGH_EVIDENCE` 允许输出完整 A/B/C 和 drills。
- `AMBIGUOUS` 先给 Plan A，再追问一次战术槽位，体现保守但实用的策略。
- `LOW_EVIDENCE` 明确拒绝深度建议，只给 next step 和通用安全框架。
- `reason_codes`：把不确定原因拆成 `EVIDENCE_TOO_THIN / OFF_TOPIC / DOC_SCOPE_MIXED / NO_CONCENTRATION / MISSING_CORE_*` 等，使 gate 可解释、可记录、可评估。
- 这个设计体现的是 Agent 策略设计能力：不是让模型在所有情况下都尽量回答，而是先判断是否应该回答、该回答到什么粒度。
- 面试话术：我的 Coach 先做 gate，再做生成。也就是说系统先判断“有没有资格给这个建议”，而不是默认让模型输出再事后补救。

### 6. BJJ Coach 输出不是自由生成，而是被产品协议约束的动作规划

- Plan A：低风险、低前置、目标对齐。
- Plan B：高收益，但必须写清前置条件和退出条件。
- Plan C：必须是 if-then 分支，至少两条分支。
- Drills：不是泛泛建议，而是必须有 dosage、constraints、success_criteria。
- 这里做的不是“让模型写得像教练”，而是把教练建议产品化成一个结构协议，便于前端渲染、评测和 SFT。
- 面试话术：我把教练回答从自由文本改造成了结构化动作建议协议，因为只有这样，输出才能被验证、比较、复盘，而不是只看起来像是专业回答。

### 7. Literary Agent 体现了“不同域用不同 Agent 策略”

- Notes 域没有套用 BJJ 的 Gate/JSON/追问逻辑，而是走“检索 anchors + 创作生成”的轻量链路。
- top-1 `raw_excerpt` 负责保留文风，top-2/3 `safe_summary` 负责控制 token 和风险。
- 如果提及用户写过的内容，仍要求基于 anchor 引用，避免把创作内容伪装成用户事实。
- 这个亮点体现的是 Agent 系统设计能力：不是“一个万能 agent 处理所有领域”，而是按任务和风险特征定制策略。
- 面试话术：我没有把 Literary 做成 BJJ Coach 的弱化版，而是给它单独设计了更轻、更自由的生成链路，因为两个域的风险结构和交互目标完全不同。

## 工程

### 8. 可回放性与可观测性被合并成主链路能力

- `trace_id` 贯穿导入、record、chat、replay、eval。
- `span` 把延迟拆分到 ingestion、retrieval、orchestrator、LLM、validator、jobs 各阶段。
- `event` 记录状态机流转、clarify 发起与结束、evidence pack 选取、model call 前后等关键事件。
- `runtime_config_snapshot` 记录版本、阈值、模型配置，让 replay 不只回放输出，还能回放运行条件。
- 这个亮点最强的地方在于：trace 不只是排障用日志，而是后续 replay、evaluation、SFT export 的统一数据基座。
- 面试话术：我把 replay 和 observability 设计成了一套统一的 trace 体系，不只是为了 debug，而是为了让评测、失败定位和 SFT 数据导出都基于同一份运行事实。

### 9. 结构化生成的可靠性闭环

- 强 schema：BJJ 输出必须是合法终态 JSON。
- Validator：除了 JSON 合法性，还校验 gate-mode 映射、引用纪律、Plan C 分支数、drill 完整性。
- Repair：失败后给模型一次定向修复机会。
- Degrade：修复仍失败则降级到可解析、可回放、可评测的 `LOW_EVIDENCE`。
- 这个点体现的是你不是把 LLM 当“会出结果的函数”，而是当“有错误率的子系统”，并为它设计了完整的容错路径。
- 面试话术：我默认模型会出错，所以设计了 validator、repair 和 degrade 三段式闭环。这样系统稳定性来自控制流程，而不是来自我相信模型这次会输出正确 JSON。

## SFT

### 10. SFT 训练目标是“行为策略”，不是领域知识

- 训练目标直接对齐产品问题：三态模式稳定、引用纪律、Plan C 分支、drill 完整性。
- 输入不是长原文，而是 `gate_decision + confirmed_slots + allowed_evidence_ids + evidence_pack_selected`，保证训练形态与线上一致。
- 这说明你理解 SFT 的正确作用：不是补知识库，而是固化策略和输出协议。
- 面试话术：我的 SFT 不是为了让模型更懂柔术，而是为了让它更稳定地执行产品协议，本质上是在训练一个 policy generator，而不是知识专家。

### 11. SFT 数据集设计体现了“可控生成”思维

- `allowed_evidence_ids` 白名单：强限制模型可引用的证据集合，防止“学会编引用”。
- 反例修正样本：把假引用、LOW 模式乱答、Plan C 分支不足这些错误行为显式纳入训练集。
- trace 到 dataset 的导出保留 `trace_id` 和 `validator_report`，让训练样本可以回溯到线上失败案例。
- 这个点很扎实，因为很多人会说“我做了微调”，但不会说自己是怎么避免模型学坏的。
- 面试话术：我在 SFT 里专门做了 evidence 白名单和反例修正样本，不只是喂正确答案，而是显式训练模型不要犯产品层面的错误。

### 12. SFT 评估不是看训练 loss，而是看 base/policy 在线口径对比

- base 和 policy 在 frozen evidence 下对比同一组 hard metrics，而不是只看训练指标。
- 评估口径直接复用线上指标：schema compliance、allowed citation accuracy、Plan C branch count、drill completeness、low-evidence safety proxy。
- 这样训练收益能直接映射到产品质量，而不是停留在模型训练视角。
- 面试话术：我没有用训练 loss 来证明微调有效，而是让 policy 和 base 走同一套 replay 和产品指标，这样提升和退化都能直接对应到系统行为。
