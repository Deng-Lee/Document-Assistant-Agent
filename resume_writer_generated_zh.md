**Personal Document Assistant Agent（BJJ 训练记录与智能建议系统）** | 个人项目 | 角色：设计并主导实现

**背景**：围绕个人 BJJ 训练记录管理与复盘场景，设计并实现一套面向个人知识库的智能体系统，用于归档训练笔记、支持精准检索，并结合用户长期训练习惯、常见失误与薄弱环节提供结构化建议。针对传统笔记软件“只能存储、难以理解训练上下文、无法形成个性化反馈”的问题，项目将训练记录、文档检索、问答建议、回放评测与策略微调整合到同一条闭环链路中。

**目标**：为解决个人训练记录难检索、经验难沉淀、建议不稳定的问题，目标构建一套偏 Agent 的个人文档助手，支持意图识别与澄清、证据驱动检索、结构化 BJJ 教练建议、可回放评测和 SFT 策略微调，使系统既能回答问题，也能持续吸收用户训练数据并优化行为策略。

**过程**：
- 设计意图识别与编排器链路，先做 `probe + plan_check` 再决定澄清、检索或一次性 LLM replan，将核心澄清轮数限制为 `2` 轮、Coach 追问限制为 `1` 轮，降低原始 query 直接入检索带来的偏航风险。
- 实现面向 BJJ 训练记录的 Agentic RAG，整合 BM25、dense retrieval、RRF 与 cross-encoder rerank，产出冻结 Evidence Pack，并将检索结果交给 BJJ Coach 生成 `HIGH_EVIDENCE / AMBIGUOUS / LOW_EVIDENCE` 三态结构化输出。
- 构建 BJJ Coach 策略协议，要求回答包含 Plan A / Plan B / Plan C、常见错误、训练 drills 与 next step，并通过 validator / repair / degrade 闭环约束引用纪律和输出结构，避免自由生成失控。
- 落地可回放 trace 体系，贯通 ingest、retrieve、orchestrator、generate、evaluate、trace、replay 全链路，记录 runtime config、事件、阶段延迟和 frozen evidence，使问题定位、离线评测与数据导出都基于同一份运行事实。
- 设计以“行为策略”而非“领域知识补充”为目标的 SFT 方案，将 `gate_decision`、`confirmed_slots`、`allowed_evidence_ids`、`frozen_evidence_pack` 等线上真实输入冻结为训练样本，重点强化三态模式稳定性、引用纪律、Plan C 分支完整性与 drills 结构约束。
- 实现 SFT 数据与训练闭环，导出 trace 训练样本并接入 LoRA / QLoRA 训练、validation split、eval loss logging、early stopping 与 adapter inference，构建 `360` 条 BJJ 数据集，其中 `300` 条 FULL 样本、`60` 条边界样本（`LOW_EVIDENCE / AMBIGUOUS_FINAL`），并支持 `base / policy` 在 frozen evidence 下做离线对比评测。
- 采用 Skills 驱动全流程推进实现与验收，将需求拆分为 ingestion、retrieval、evaluation、SFT、frontend 等连续阶段，配套单元测试、smoke tests、contract sync、Playwright e2e 和 QA skill，实现“开发-验证-交付”自动化闭环。

**结果**：项目完成了从 `ingest -> retrieve -> orchestrate -> generate -> trace -> replay -> evaluate -> sft` 的完整闭环，覆盖 `2` 类文档域（BJJ / Notes）、`4` 个前端核心页面（dashboard / chat / traces / evaluation），并形成 `360` 条可直接用于策略微调的数据样本。SFT 侧已具备从 trace 导出、行为约束样本构造、LoRA / QLoRA 训练到 `base / policy` 对比评测的完整链路，而不是只停留在离线训练脚本层。  
**量化指标建议（请按实际联调结果调整）**：可补充为“BJJ 检索命中率提升 `15%~25%`、端到端问答响应时延控制在 `0.8s~1.5s`、结构化回答合规率达到 `90%+`”，用于投递 LLM Application Engineer / Agent Engineer 岗位时强化结果表达。

**技术栈**：Python、FastAPI、SQLite、Chroma、Next.js、React、Qwen、OpenAI-compatible API、RAG、Agentic RAG、Cross-Encoder、Trace/Replay、Offline Evaluation、Manual Rubric、SFT、LoRA / QLoRA、Transformers、PEFT、Vitest、Playwright

## 面试追问预测

1. 你的意图识别为什么不直接交给一个 LLM 分类，而要先做 `probe + plan_check`？
2. BJJ Coach 的 `HIGH_EVIDENCE / AMBIGUOUS / LOW_EVIDENCE` 三态是怎么定义和验证的？
3. 你的 SFT 为什么训练的是行为策略，而不是直接让模型学习柔术知识？
4. trace / replay / evaluation 为什么要共用同一份运行事实？这样做解决了什么问题？
5. Skills 驱动全流程和普通脚本化开发相比，最大的工程收益是什么？
