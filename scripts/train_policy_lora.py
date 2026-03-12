#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random
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


def _split_examples(
    prompts: list[str],
    completions: list[str],
    validation_split: float,
    seed: int = 42,
) -> tuple[dict[str, list[str]], dict[str, list[str]] | None]:
    if len(prompts) != len(completions):
        raise ValueError("prompt/completion length mismatch")
    row_count = len(prompts)
    train_payload = {"prompt": prompts, "completion": completions}
    if row_count < 2 or validation_split <= 0.0:
        return train_payload, None
    validation_count = int(round(row_count * validation_split))
    validation_count = max(1, validation_count)
    validation_count = min(validation_count, row_count - 1)
    indices = list(range(row_count))
    random.Random(seed).shuffle(indices)
    validation_indices = set(indices[:validation_count])
    train_prompts: list[str] = []
    train_completions: list[str] = []
    eval_prompts: list[str] = []
    eval_completions: list[str] = []
    for index, (prompt, completion) in enumerate(zip(prompts, completions)):
        if index in validation_indices:
            eval_prompts.append(prompt)
            eval_completions.append(completion)
        else:
            train_prompts.append(prompt)
            train_completions.append(completion)
    return (
        {"prompt": train_prompts, "completion": train_completions},
        {"prompt": eval_prompts, "completion": eval_completions},
    )


def _extract_loss_history(log_history: list[dict[str, Any]], loss_key: str) -> list[dict[str, float]]:
    curve: list[dict[str, float]] = []
    for item in log_history:
        if loss_key not in item:
            continue
        curve.append(
            {
                "step": float(item.get("step", 0)),
                "epoch": float(item.get("epoch", 0.0)),
                loss_key: float(item[loss_key]),
            }
        )
    return curve


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
    validation_split: float,
    eval_steps: int,
    early_stopping_patience: int,
    early_stopping_threshold: float,
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
            EarlyStoppingCallback,
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
    train_payload, eval_payload = _split_examples(prompts, completions, validation_split=validation_split)
    dataset = Dataset.from_dict(train_payload)
    eval_dataset = Dataset.from_dict(eval_payload) if eval_payload is not None else None

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
    tokenized_eval = (
        eval_dataset.map(tokenize, batched=True, remove_columns=eval_dataset.column_names)
        if eval_dataset is not None
        else None
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    evaluation_enabled = tokenized_eval is not None and len(tokenized_eval) > 0
    training_args_kwargs: dict[str, Any] = {
        "output_dir": str(out_dir),
        "per_device_train_batch_size": batch_size,
        "per_device_eval_batch_size": batch_size,
        "num_train_epochs": epochs,
        "learning_rate": lr,
        "logging_steps": 1,
        "save_total_limit": 2,
        "report_to": [],
        "fp16": torch.cuda.is_available() and not load_in_4bit,
        "evaluation_strategy": "steps" if evaluation_enabled else "no",
        "save_strategy": "steps" if evaluation_enabled else "epoch",
        "load_best_model_at_end": evaluation_enabled,
    }
    if evaluation_enabled:
        training_args_kwargs.update(
            {
                "eval_steps": eval_steps,
                "save_steps": eval_steps,
                "metric_for_best_model": "eval_loss",
                "greater_is_better": False,
            }
        )
    training_args = TrainingArguments(**training_args_kwargs)
    callbacks = []
    if evaluation_enabled and early_stopping_patience > 0:
        callbacks.append(
            EarlyStoppingCallback(
                early_stopping_patience=early_stopping_patience,
                early_stopping_threshold=early_stopping_threshold,
            )
        )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized,
        eval_dataset=tokenized_eval,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
        callbacks=callbacks,
    )
    train_result = trainer.train()
    adapter_dir = out_dir / "adapter"
    tokenizer_dir = out_dir / "tokenizer"
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(tokenizer_dir))
    best_eval_loss = (
        float(trainer.state.best_metric)
        if evaluation_enabled and trainer.state.best_metric is not None
        else None
    )
    expected_train_steps = math.ceil(max(len(tokenized), 1) / batch_size) * epochs
    stopped_early = bool(
        evaluation_enabled
        and early_stopping_patience > 0
        and trainer.state.global_step < expected_train_steps
    )
    log_history = trainer.state.log_history
    (out_dir / "training_summary.json").write_text(
        json.dumps(
            {
                "backend_name": "hf_lora_qlora_v1",
                "base_model": base_model,
                "row_count": len(rows),
                "train_row_count": len(train_payload["prompt"]),
                "validation_row_count": len(eval_payload["prompt"]) if eval_payload is not None else 0,
                "evaluation_enabled": evaluation_enabled,
                "epochs": epochs,
                "learning_rate": lr,
                "batch_size": batch_size,
                "max_seq_len": max_seq_len,
                "lora_r": lora_r,
                "lora_alpha": lora_alpha,
                "lora_dropout": lora_dropout,
                "lora_targets": lora_targets,
                "validation_split": validation_split,
                "eval_steps": eval_steps,
                "early_stopping_patience": early_stopping_patience,
                "early_stopping_threshold": early_stopping_threshold,
                "best_eval_loss": best_eval_loss,
                "best_model_checkpoint": trainer.state.best_model_checkpoint,
                "stopped_early": stopped_early,
                "global_step": trainer.state.global_step,
                "expected_train_steps": expected_train_steps,
                "training_loss": float(train_result.training_loss),
                "train_loss_curve": _extract_loss_history(log_history, "loss"),
                "eval_loss_curve": _extract_loss_history(log_history, "eval_loss"),
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
    parser.add_argument("--validation_split", type=float, default=0.1)
    parser.add_argument("--eval_steps", type=int, default=10)
    parser.add_argument("--early_stopping_patience", type=int, default=2)
    parser.add_argument("--early_stopping_threshold", type=float, default=0.0)
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
        validation_split=args.validation_split,
        eval_steps=args.eval_steps,
        early_stopping_patience=args.early_stopping_patience,
        early_stopping_threshold=args.early_stopping_threshold,
        load_in_4bit=args.load_in_4bit,
    )


if __name__ == "__main__":
    main()
