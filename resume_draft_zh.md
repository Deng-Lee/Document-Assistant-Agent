# 中文简历初稿

## 基本信息

- 姓名：Lee
- 求职方向：Agent Engineer / RAG Engineer / LLM Application Engineer
- 联系方式：`[手机号]` `|` `[邮箱]` `|` `[GitHub/主页]`
- 所在地：`[城市]`

## 个人简介

聚焦 LLM 应用工程、Agent 系统与 RAG 基础设施实现，能够从规范设计、后端服务、前端接入、评测闭环到 SFT 训练链路完成端到端交付。近期主导实现一个面向 BJJ 教练问答与 Notes 创作检索的 Personal Document Assistant Agent，覆盖 ingestion、hybrid retrieval、orchestrator、trace/replay、offline evaluation、policy SFT 与 Next.js 前端。

## 核心技能

- Python, FastAPI, SQLite, Chroma, Next.js, React
- RAG, Agentic RAG, BM25, Dense Retrieval, Cross-Encoder Rerank
- OpenAI-compatible API, Qwen, Prompt Engineering, Structured Generation
- Trace/Replay, Offline Evaluation, Manual Rubric, RAGAS, LLM-as-Judge
- SFT, LoRA / QLoRA, Transformers, PEFT, Adapter Inference
- Contract Sync, Vitest, Playwright, Smoke Test, End-to-End QA

## 项目经历

### Personal Document Assistant Agent | 个人项目 | `2026`

**背景**：针对个人知识库场景中“训练笔记与随笔分散、关键词搜索不稳定、AI 回答难以审计”的问题，设计并实现面向 BJJ 教练问答与 Notes 创作的个人文档智能体系统。系统目标不是做单次问答 demo，而是构建具备检索编排、证据冻结、回放评测与策略微调能力的完整 Agent 应用。

**目标**：构建一套以结构化证据和可回放 trace 为核心的数据闭环，支持 Hybrid Retrieval、Orchestrator Replan、BJJ Coach / Literary Agent、Offline Evaluation 与 Policy SFT，使同一套系统既能稳定回答问题，也能导出训练数据并完成 base/policy 对比。

**过程**：

- 设计并实现双域文档 ingestion 管线，支持 BJJ 训练记录与 Notes Markdown 解析、快照存储、分块、向量化与安全摘要任务编排，并将 `chunk_size / overlap / embedding / LLM` 等运行参数统一收口到 profile 配置。
- 实现编排驱动的 Agentic RAG 主链路，在正式检索前增加 probe、plan_check 与一次性 LLM replan，结合最多 2 轮核心澄清与 1 轮 Coach 澄清，使 query 能先补槽位再检索，而不是直接把原始问题送入 RAG。
- 构建 Hybrid Retrieval 流程，结合 BM25、dense retrieval、RRF 与真实 Hugging Face cross-encoder rerank，产出冻结 Evidence Pack；同时为 Notes 域实现 top-1 `raw_excerpt` + top-2/3 `safe_summary` anchor 生成链路。
- 为 BJJ Coach 设计 `HIGH_EVIDENCE / AMBIGUOUS / LOW_EVIDENCE` 三态 gate、结构化动作规划协议、validator / repair / degrade 闭环，使输出可验证、可训练、可回放，而不是不可控自由文本。
- 实现 trace/replay/evaluation 基础设施，打通 trace spans、event、runtime config snapshot、frozen replay、hard metrics、external evaluators、manual rubric 三层评测；支持 `base` 与 `policy` 在相同 frozen evidence 下对比。
- 落地完整 SFT 链路：从 trace 导出训练集、生成训练行、注册 policy artifact、LoRA / QLoRA 训练、adapter-backed inference 到 policy replay/eval；构造 `300` 条 BJJ FULL 样本与 `60` 条 `LOW_EVIDENCE / AMBIGUOUS_FINAL` 边界样本，并完成 `train/val` 切分。
- 接入 Next.js App Router 前端，覆盖 dashboard、chat、traces、evaluation 页面，并补齐 frontend contract sync、Vitest 组件测试、Playwright 浏览器级回归与仓库级 test suite 集成。

**结果**：

- 完成从 `ingest -> retrieve -> orchestrate -> generate -> trace -> replay -> evaluate -> sft` 的全链路闭环实现，覆盖 `BJJ` 与 `Notes` 两类文档域。
- 建立可直接用于 policy 微调的数据准备能力，形成 `360` 条 BJJ SFT 数据集，其中包含 `300` 条 FULL 样本与 `60` 条边界降级样本。
- 构建多层质量保障体系，包含后端单元测试、前端组件测试、Playwright e2e、smoke tests 与 contract drift check，支持持续回归而非一次性验证。

**技术栈**：Python、FastAPI、SQLite、Chroma、Next.js、React、Vitest、Playwright、Transformers、PEFT、LoRA/QLoRA、OpenAI-compatible API、Qwen、RAG、Cross-Encoder、Trace/Replay、Offline Evaluation

## 加分亮点

- 将“检索”从静态步骤升级为被 Orchestrator 调度的 Agentic RAG 过程，具备 probe、clarify、replan、retrieve 的状态机语义。
- 将 Observability 与 Replay 合并为主链路能力，而不是事后日志；同一份 trace 同时服务于排障、评测与 SFT 数据导出。
- 将 SFT 定位为“行为策略微调”而非知识补充，训练目标直接对齐引用纪律、三态模式和结构化输出协议。

## 可补充信息

- 教育经历：`[学校 / 专业 / 学历 / 时间]`
- 工作经历：`[公司 / 职位 / 时间 / 关键产出]`
- 开源链接：`[仓库地址]`
- 个人主页：`[博客 / 作品集]`

