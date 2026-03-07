# 核心契约（摘要版）

本文件只放“实现必须对齐”的关键 I/O 契约摘要；权威来源始终是 repo 内的 `DEV_SPEC.md`。

## 1) Chat Turn 响应类型（必须二选一）
- `clarify_request`
  - 结构化：`who`（ORCHESTRATOR/BJJ_COACH）、`slot`、`options[]`、`template_id`、`round`、`why`
- `final_answer`
  - BJJ：三态 JSON（FULL / AMBIGUOUS_FINAL / LOW_EVIDENCE）
  - Literary：自由文本 + `anchors[]`（doc_version + locator + citation）

## 2) Evidence Pack（生成与回放的唯一证据来源）
每条 evidence 至少包含：
- `evidence_id`（建议=chunk_id）
- `doc_id`, `doc_version_id`
- `locator`（source_locators：行号范围 + 字符偏移；绑定 doc_version）
- `safe_summary`
- `metadata_digest`（BJJ：date/position/orientation/distance/goal/opponent_control 等）
- `rank_signals`（rank，不依赖 raw 分数）

## 3) BJJ Coach 输出 JSON（Validator 约束）
### mode=FULL
- `reasoning_status.gate_label=HIGH_EVIDENCE`
- observations 3–5，每条必须有 evidence_ids
- Plan C branches >= 2
- `citations` = 全文 evidence_ids 去重并集

### mode=AMBIGUOUS_FINAL
- `reasoning_status.gate_label=AMBIGUOUS` 且 `coach_clarify_round=1`
- `caveats` 非空
- Plan A 必须完整；Plan B/C 可 generic
- `next_step.type=RECORD_SUGGESTION`

### mode=LOW_EVIDENCE
- `reasoning_status.gate_label=LOW_EVIDENCE`
- `caveats` 必须包含 4 段（Status/Reason/Next/Fallback）
- drills 为空；plans 保持 generic

### 全模式通用
- 禁止 `followup_question`
- 引用纪律：关于用户历史必须引用 evidence_ids；无证据则 generic=true
- citations 白名单：输出 evidence_ids 必须属于 allowed set（用于 SFT/评测）

## 4) Trace（用于回放、评测、SFT 导出）
每个 trace 至少应包含：
- runtime_config_snapshot（doc/embedding/prompt/policy/profile version + 阈值配置）
- request_log（stage transitions、clarify 记录）
- retrieval_log + evidence_log（冻结 evidence_pack）
- generation_log（model config、token/cost、output、validator_report）
