# Project Highlights

下面这 10 个亮点，都是能从 `DEV_SPEC.md` 和 `IMPLEMENTATION_PLAN.md` 里直接落到工程实现层的，不是空泛概念。

## 1. 可回放的版本化架构

- `doc_version_id`：每次文档内容变化都生成新版本，引用和回放永远绑定到具体版本，而不是“当前文档”。这样解决了文档更新后 citation 漂移的问题。
- `embedding_version_id`：向量检索结果不是天然稳定的，所以把 embedding 模型和参数版本显式记录下来，并要求 Chroma 按版本隔离。这样可以解释“为什么同一个 query 在不同时间命中变了”。
- `prompt_version`：Prompt 不是隐式常量，而是运行配置的一部分。每次策略调整都能被 trace 捕获，后续 replay 时可以明确区分是 prompt 改了还是模型改了。
- `policy_version`：base 与 policy 模型被当成两个可对比变体，而不是临时切换。这样 SFT 的收益和退化都能在同一条评测链路里量化。
- `runtime_config_snapshot`：每次请求都把关键阈值、版本号、模型名打包进 trace。这个点很重要，因为 Agent 系统的漂移很多不是代码 bug，而是配置漂移，不做快照就没法复盘。
- 面试话术：我把系统里的“变化源”显式版本化了，包含文档、向量、prompt 和 policy。这样任何一次回答都能被重放到当时的运行上下文，而不是只能模糊地说“可能是模型变了”。

## 2. Markdown 导入里的精确定位与双文本流

- `locator_index`：在 Loader 阶段先对整篇 Markdown 扫描出行起始偏移，后续 chunk 只需要记录行号范围就能解析出精确字符偏移。这样避免每个 chunk 重复扫描全文。
- `source_locators`：每个 chunk 都带上 `doc_version + line_start/line_end + char_start/char_end`。它直接支撑了 Evidence Panel 高亮、引用回放、以及 Gate 的可审计性。
- `raw_text` 与 `clean_text` 分离：raw 用来回放和引用，clean 用来做 FTS5 与 embedding。这样既能保证检索效果，又不会破坏原文定位。
- `safe_summary`：chunk 之后增加后台任务，用 LLM 为每个 chunk 生成简短安全摘要。它解决的是在线 probe/replan 阶段不适合直接暴露原文 chunk 的问题。
- 这里特别出色的点在于：不是简单“把 markdown 切块”，而是把“检索文本”和“证据文本”分成两套链路。这样你同时解决了召回效果和证据可核验两个常常冲突的目标。
- 面试话术：我在导入时就把文本分成 raw 和 clean 两条流，检索走 clean，引用走 raw locator。这样系统既能查得准，也能让每条证据回到原文具体位置。

## 3. Hybrid Retrieval 的工程化拆解

- Structured Filter：时间范围、position、orientation、distance、goal、opponent_control 这些条件先在 SQLite 层过滤。这样减少无关 chunk 进入后续 BM25 和向量检索。
- SQLite FTS5：关键词检索不是附属功能，而是专门承担“明确词面表达”的召回，比如位置名、控制点、训练术语。它比纯向量更可解释，也更容易调试。
- Chroma Dense Retrieval：语义检索专门覆盖“说法不同但意思接近”的问题，比如用户没用日志里的原词，但问的是相同技术场景。
- RRF 融合：没有直接做加权求和，而是用 RRF 融合 BM25 和 dense 排名。这样避免了不同分数量纲不一致导致的调参灾难。
- Token-budget trimming：Evidence Pack 不是机械 top-k，而是还考虑每文档限额、去重和 token 预算。这样检索结果才能真正可用于下游生成，而不是只在离线指标上好看。
- 这里的关键不是“用了 hybrid”这个词，而是每条通道都有明确职责，并且融合方法选择了解释性和稳定性都更好的 RRF。
- 面试话术：我的 hybrid retrieval 不是把 BM25 和 embedding 拼在一起，而是把结构过滤、关键词召回、语义召回分层处理，再用 RRF 做稳定融合，这样结果更可解释，也更容易回放。

## 4. Evidence Pack 作为唯一事实边界

- Evidence Pack Contract：每条 evidence 必须包含 `evidence_id/doc_version_id/locator/safe_summary/metadata_digest/rank_signals`。这让检索结果从“若干文本片段”升级成了可审计的数据结构。
- 生成边界控制：BJJ Coach 和 replay 只能消费 retrieval 产出的 frozen evidence pack，不能再自由去扫库。这样可以显著压缩 hallucination 空间。
- Citation Discipline：关于用户过往训练的陈述必须引用 `evidence_id`，否则只能标 `generic=true`。这把“是否有依据”从语言感觉变成了可程序校验的规则。
- Frozen Evidence Replay：评测和 base/policy 对比时固定 evidence pack，不让检索波动干扰生成对比。这个设计是后面 Evaluation 和 SFT 能成立的前提。
- 这个点特别强，因为它把“模型基于证据回答”从一句口号落实成了契约边界、trace 数据和 validator 规则。
- 面试话术：我把 Evidence Pack 定义成生成器唯一能看的事实边界，所有用户历史断言都要落到这个边界里。这样系统的可信度不是靠 prompt 约束，而是靠数据边界和校验器约束。

## 5. Orchestrator 的 Probe + Plan Check + Replan 机制

- Hard Guard：先把写入意图和对话意图分开，避免把 record 请求误送到 RAG 链路。这样可以减少错误路由和无意义的 LLM 调用。
- Pending-slot short-circuit：如果上一轮刚问了某个 slot，下一轮优先按 slot parser 解析，不重新跑整套判断。这样减少无谓 token 成本，也让 Clarify Loop 更稳定。
- PROBE 小检索：在正式生成 retrieval plan 前先做一次轻量检索，只看 safe_summary 和结构信号。它的作用不是回答问题，而是压低“不知道用户到底在问什么”的不确定性。
- `probe_stats`：把 `domain_score`、`slot_entropy`、`time_signal`、`evidence_strength` 这类中间信号显式化。这样下一步决策不是黑箱。
- `plan_check`：不是让 LLM 直接决定一切，而是先根据 probe 信号判断是否需要 replan、clarify 还是直接 retrieve。这个阶段本质上是一个可解释的控制器。
- LLM Replan：只在 probe 信号说明“规则不够”时触发一次 LLM，把 query 与 probe 结果重写成更适合检索的结构化 plan。这样兼顾了确定性与灵活性。
- 这个设计出色的地方在于：你没有走“纯规则”也没有走“纯 agent”，而是用 probe 让 LLM 只在真正有价值的时候介入。
- 面试话术：我把意图识别做成了一个轻量状态机，先用 probe 看证据分布，再决定要不要让 LLM 重规划。这样 LLM 不是全权调度者，而是一个受约束的规划补充器。

## 6. BJJ Coach 的三态 Gate 设计

- `HIGH_EVIDENCE`：当 evidence 数量、位置集中度、域纯度和战术槽位都足够时，允许输出完整 A/B/C + drills。这样生成可以充分个性化。
- `AMBIGUOUS`：证据足以给保底建议，但不足以给精细战术分支时，先输出 Plan A，再追问 `opponent_control`。这是一种“偏实用但保守”的折中。
- `LOW_EVIDENCE`：当命中太少、跑题或证据分散时，不再硬答，而是只输出状态解释、next step 与通用安全框架。这样避免了“看似专业、实则乱答”的风险。
- `reason_codes`：不是只给一个 gate_label，而是把原因拆成 `EVIDENCE_TOO_THIN / OFF_TOPIC / DOC_SCOPE_MIXED / NO_CONCENTRATION / MISSING_CORE_*` 等。这样 UI、trace、eval 和面试讲述都更有抓手。
- `opponent_control` 单槽位追问：BJJ Coach 只追问一个战术槽位，而且最多一轮。这体现了你对用户体验和建议精度的边界控制。
- 这里特别出色的点在于：Gate 不是“模型置信度”的抽象概念，而是由结构化信号驱动的策略状态机。
- 面试话术：我的 BJJ Coach 不是默认输出建议，而是先问一个更本质的问题：当前证据到底够不够支撑这个建议。Gate 决定了系统什么时候该具体，什么时候该保守，什么时候该闭嘴。

## 7. 结构化生成后的 Validator / Repair / Degrade 闭环

- Schema Validation：BJJ 最终输出必须是三态 JSON 之一，而且字段完整、模式一致。这样输出天然可被 UI、eval、SFT 管线消费。
- Policy Validation：不仅校验 JSON 合法性，还校验 `gate_label -> mode` 映射、Plan C 分支数、drill 完整性、citation 白名单等“产品级规则”。
- Repair Pass：如果生成结果不合法，不是直接报错，而是把 validator 错误回灌给模型进行一次修复。这样能提高在线稳定性。
- Deterministic Degrade：如果 repair 后仍失败，系统直接程序化降级成 `LOW_EVIDENCE`。这保证了线上永远有一个可解析、可回放、可评测的输出。
- 这个方案解决的是真实生产问题，而不是 demo 问题。很多 LLM 项目一旦输出格式错了就直接崩，这里你明确设计了“失败后的产品行为”。
- 面试话术：我假设模型一定会偶发出错，所以系统不是“生成成功才工作”，而是“生成失败也有定义好的退化路径”。这比 prompt engineering 更像真正的工程设计。

## 8. Literary Agent 的锚点设计与创作边界

- Dense/Sparse + RRF：Notes 进入 Literary 域后，仍然走完整 retrieval，而不是直接拿大模型闲聊。这样“创作性”仍然建立在用户历史文本上。
- Top-3 文档去重：不是简单 top-3 chunks，而是按 `doc_id` 去重，避免一个文档垄断 prompt。这样更接近“整体风格锚定”。
- Top-1 `raw_excerpt`：保留一小段原始文本来给模型真实文感。这样模型更容易贴近用户的句式、意象和节奏。
- Top-2/3 `safe_summary`：其余位置只放摘要，控制 token，降低 prompt injection 风险，也减少把太多原文直接喂进模型。
- Citation-aware creativity：如果模型说“你在笔记里写过……”，必须引用 anchor；如果是新创作，则明确是延伸或想象。这样避免把生成内容误当成用户事实。
- 这个设计特别好，因为它处理了“风格一致性”和“事实边界”之间的张力，而不是单纯追求更高 temperature。
- 面试话术：Literary 不是简单地把检索片段塞给模型，而是把风格锚点做成了分层输入：一个原文锚点保留文感，其他锚点用摘要控成本和风险，这样创作自由度和可信度能同时成立。

## 9. Trace / Span / Event 级可观测性

- `trace_id`：每次导入、record、chat turn、eval replay 都有贯穿全链路的总 id。这样任何失败都能被完整追踪。
- `span`：对 ingestion、retrieval、orchestrator、LLM、validator、jobs 都做阶段级耗时记录。这样性能优化能定位到具体瓶颈，而不是只看总延迟。
- `event`：记录状态转换、clarify 发起与解决、evidence pack 选取、model call start/end。这样你不仅知道“慢”，还知道“发生了什么”。
- `trace_capture_level`：minimal 只存结构化信息，debug 才存更多裁剪快照。这样平衡了隐私、存储膨胀和调试能力。
- Trace-to-Eval-to-SFT：trace 不是日志终点，而是后续 replay、hard metrics、RAGAS、LLM judge、SFT export 的共同数据来源。这个闭环设计非常工程化。
- 这个亮点强在它不是“加日志”，而是把 observability 设计成后续所有质量迭代的地基。
- 面试话术：我把 trace 设计成了一个中枢数据结构，而不是调试日志。它同时支撑线上排障、离线评估、失败样本定位和 SFT 数据导出，所以整个系统才真正形成了闭环。

## 10. Policy SFT 的数据闭环与训练目标设计

- 训练目标定义：SFT 训练的不是 BJJ 知识，而是输出策略，包括三态模式、引用纪律、Plan C 分支、drill 完整性。这让训练目标与产品问题直接对应。
- 训练输入设计：输入带 `gate_decision`、`coach_clarify_round`、`confirmed_slots`、`allowed_evidence_ids`、`evidence_pack_selected`。这让模型学习的是“给定状态和证据如何输出”，而不是凭空回答。
- 反例修正样本：显式加入假引用、LOW 输出高风险建议、Plan C 分支不足等 bad case -> fixed case。这样训练不是单纯喂正样本，而是在教模型边界。
- Base/Policy Replay：训练完成后不是只看 loss，而是用 frozen evidence 对比 base 和 policy 的 hard metrics。这样改进是产品口径，而不是训练口径。
- `allowed_evidence_ids` 白名单：这是 SFT 里很关键的工程点，它避免模型“学会乱编 evidence_id”。这是很多项目不会想到，但面试官会觉得很扎实的点。
- 这里出色的地方在于：SFT 被定义成一个“行为稳定器”，而不是大而空的“我也做了微调”。
- 面试话术：我的 SFT 不是为了让模型更懂柔术，而是为了让它更稳定地遵守产品协议。训练数据、评估方法和线上 validator 是一套闭环，所以这个微调是可解释、可比较、可回归的。
