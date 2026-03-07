# DEV_SPEC 快速索引（给 pda-implementer 用）

目标：让 agent 在不把整份 spec 全量塞进上下文的情况下，快速定位关键章节。

## 常用定位命令（在 repo root 执行）

- 查“待讨论 / TBD / TODO”（不确定点）：
  - `rg -n "待讨论|TBD|TODO|color:#dc2626" DEV_SPEC.md`

- 查 Ingestion（导入/切分/locators/safe_summary）：
  - `rg -n "^## 3\\." DEV_SPEC.md`

- 查 Storage（SQLite/FTS5/Chroma/FileStore/职责）：
  - `rg -n "^## 4\\." DEV_SPEC.md`

- 查 Retrieval（structured + BM25 + dense + RRF + EvidencePack）：
  - `rg -n "^## 5\\." DEV_SPEC.md`

- 查 Orchestrator（Guard/Probe/Plan_check/Replan/Clarify）：
  - `rg -n "^## 6\\." DEV_SPEC.md`

- 查 BJJ Coach（Gate 三态、Validator、repair/degrade、Prompt 模板）：
  - `rg -n "^## 7\\." DEV_SPEC.md`

- 查 Literary（anchors：top-1 excerpt + top-2/3 safe_summary）：
  - `rg -n "^## 8\\." DEV_SPEC.md`

- 查 API（/chat/turn、/replay、/sft/export、/maintenance/reindex 等）：
  - `rg -n "^## 9\\." DEV_SPEC.md`

- 查 Tracing（trace/span/event、留存策略、capture_level）：
  - `rg -n "^## 10\\." DEV_SPEC.md`

- 查 Web UI（Home/Chat/Traces/Eval 交互与澄清 UI）：
  - `rg -n "^## 11\\." DEV_SPEC.md`

- 查 Evaluation（RAGAS + hard metrics + judge + rubric）：
  - `rg -n "^## 12\\." DEV_SPEC.md`

- 查 SFT（Policy SFT，V1 必做）：
  - `rg -n "^## 13\\." DEV_SPEC.md`

## 实施顺序（与 spec 一致）
1) contracts/schemas → 2) storage → 3) ingestion → 4) retrieval → 5) orchestrator → 6) agents → 7) observability → 8) evaluation → 9) SFT
