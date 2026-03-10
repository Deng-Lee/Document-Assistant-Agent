#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.app.sft.prompting import build_policy_prompt


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _build_example(row: dict[str, Any]) -> tuple[str, str]:
    if "input" not in row or "target_output" not in row:
        raise ValueError("Each row must contain 'input' and 'target_output'.")
    prompt = build_policy_prompt(row["input"])
    assistant = json.dumps(row["target_output"], ensure_ascii=False)
    return prompt, assistant


def train(
    train_path: Path,
    base_model: str,
    out_dir: Path,
    epochs: int,
    lr: float,
    batch_size: int,
    max_seq_len: int,
    lora_r: int,
    lora_alpha: int,
    lora_dropout: float,
    lora_targets: list[str] | None,
    load_in_4bit: bool,
) -> None:
    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, get_peft_model
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            DataCollatorForLanguageModeling,
            Trainer,
            TrainingArguments,
        )
    except Exception as exc:
        raise SystemExit(
            "Missing deps. Install training extras: torch transformers peft accelerate datasets"
            " (and bitsandbytes for 4bit).\n"
            f"Original error: {exc}"
        )

    rows = _read_jsonl(train_path)
    if not rows:
        raise SystemExit("Empty train.jsonl")

    prompts: list[str] = []
    completions: list[str] = []
    for row in rows:
        prompt, completion = _build_example(row)
        prompts.append(prompt)
        completions.append(completion)
    dataset = Dataset.from_dict({"prompt": prompts, "completion": completions})

    tokenizer = AutoTokenizer.from_pretrained(base_model, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model_kwargs: dict[str, Any] = {}
    if load_in_4bit:
        model_kwargs["load_in_4bit"] = True
        model_kwargs["device_map"] = "auto"
    model = AutoModelForCausalLM.from_pretrained(base_model, **model_kwargs)

    if not lora_targets:
        lora_targets = ["q_proj", "k_proj", "v_proj", "o_proj"]

    model = get_peft_model(
        model,
        LoraConfig(
            r=lora_r,
            lora_alpha=lora_alpha,
            lora_dropout=lora_dropout,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=lora_targets,
        ),
    )

    def tokenize(batch: dict[str, list[str]]) -> dict[str, Any]:
        input_ids = []
        labels = []
        attention_mask = []
        for prompt_text, completion_text in zip(batch["prompt"], batch["completion"]):
            prompt_ids = tokenizer(prompt_text, add_special_tokens=False).input_ids
            full = tokenizer(
                prompt_text + completion_text,
                add_special_tokens=False,
                truncation=True,
                max_length=max_seq_len,
            )
            ids = full.input_ids
            label_ids = ids.copy()
            for index in range(min(len(prompt_ids), len(label_ids))):
                label_ids[index] = -100
            input_ids.append(ids)
            labels.append(label_ids)
            attention_mask.append(full.attention_mask)
        return {"input_ids": input_ids, "labels": labels, "attention_mask": attention_mask}

    tokenized = dataset.map(tokenize, batched=True, remove_columns=dataset.column_names)
    out_dir.mkdir(parents=True, exist_ok=True)
    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(out_dir),
            per_device_train_batch_size=batch_size,
            num_train_epochs=epochs,
            learning_rate=lr,
            logging_steps=10,
            save_steps=200,
            save_total_limit=2,
            report_to=[],
            fp16=torch.cuda.is_available() and not load_in_4bit,
        ),
        train_dataset=tokenized,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )
    trainer.train()
    adapter_dir = out_dir / "adapter"
    tokenizer_dir = out_dir / "tokenizer"
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(tokenizer_dir))
    (out_dir / "training_summary.json").write_text(
        json.dumps(
            {
                "backend_name": "hf_lora_qlora_v1",
                "base_model": base_model,
                "row_count": len(rows),
                "epochs": epochs,
                "learning_rate": lr,
                "batch_size": batch_size,
                "max_seq_len": max_seq_len,
                "lora_r": lora_r,
                "lora_alpha": lora_alpha,
                "lora_dropout": lora_dropout,
                "lora_targets": lora_targets,
                "load_in_4bit": load_in_4bit,
                "adapter_path": str(adapter_dir),
                "tokenizer_path": str(tokenizer_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a PDA policy LoRA/QLoRA adapter.")
    parser.add_argument("--train", required=True)
    parser.add_argument("--base_model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--max_seq_len", type=int, default=2048)
    parser.add_argument("--lora_r", type=int, default=16)
    parser.add_argument("--lora_alpha", type=int, default=32)
    parser.add_argument("--lora_dropout", type=float, default=0.05)
    parser.add_argument("--lora_targets", default="")
    parser.add_argument("--load_in_4bit", action="store_true")
    args = parser.parse_args()

    lora_targets = [item.strip() for item in args.lora_targets.split(",") if item.strip()]
    train(
        train_path=Path(args.train).resolve(),
        base_model=args.base_model,
        out_dir=Path(args.out).resolve(),
        epochs=args.epochs,
        lr=args.lr,
        batch_size=args.batch_size,
        max_seq_len=args.max_seq_len,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        lora_targets=lora_targets or None,
        load_in_4bit=args.load_in_4bit,
    )


if __name__ == "__main__":
    main()
