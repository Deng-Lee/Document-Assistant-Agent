# Policy SFT（V1 必做）Runbook

目标：跑通最小闭环：trace → 数据集 → 人工修订 → LoRA/QLoRA 训练 → base/policy frozen replay 对比。

## 0) 你需要准备什么
- trace 存储（SQLite 或 `data/traces/*.json`）至少包含：gate_label/mode、allowed_evidence_ids、evidence_pack_selected、baseline 输出、validator_report。
- 一份最小 golden set（>=30）用于回放对比。

## 1) 导出数据集（JSONL + manifest）
- 推荐：从 frozen evidence 的 traces 导出（减少检索波动）。
- 命令示例：
  - `python skills/pda-implementer/scripts/export_sft_dataset.py --repo . --out datasets/sft/v1/20260307`

导出产物：
- `dataset_export.jsonl`：每行样本，包含 `trace_id`、`runtime_config_snapshot`、`input`（结构化）、`allowed_evidence_ids`、`evidence_pack_selected`、`baseline_output`、`validator_report`。
- `manifest.json`：导出过滤条件、时间、prompt_version、embedding_version_id、schema_version。

## 2) 人工修订（从 50–100 条起步）
- 从 `dataset_export.jsonl` 复制一份为 `train.jsonl`。
- 每条样本加入/替换 `target_output`：必须是 validator 可通过的最终 JSON。
- 重点修：假引用、Plan C 分支不足、drill 不完整、LOW 不克制、AMBIGUOUS 仍提问。

## 3) 训练（LoRA/QLoRA）
- Dry-run：
  - `python skills/pda-implementer/scripts/train_policy_lora.py --train datasets/sft/v1/20260307/train.jsonl --out data/policy_checkpoints/run_001 --dry-run`
- 真训练：去掉 `--dry-run`，并提供 base model：
  - `python skills/pda-implementer/scripts/train_policy_lora.py --train ... --base_model <HF_MODEL_ID_OR_PATH> --out ...`

注意：V1 的目标是“行为/格式稳定”，不是技术知识。

## 4) 接入与对比
- 系统必须支持 `model_variant=base|policy`：
  - replay 时固定 evidence_pack（Frozen Evidence Replay）
  - 输出对比：schema/citation/branch/drill/safety + latency/cost

## 5) 失败模式（必须监控）
- 假引用：输出 evidence_id 不在 allowed set
- 模式串台：LOW 输出 FULL
- 结构漂移：JSON 不合法/缺字段

在训练集中加入“反例→修正”样本最有效。
