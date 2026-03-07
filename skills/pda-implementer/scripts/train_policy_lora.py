#!/usr/bin/env python3
import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SYSTEM_PROMPT = (
    "You are a Brazilian Jiu-Jitsu (BJJ) coach assistant. "
    "You output a single valid JSON object following the provided schema. "
    "You do not ask questions. You must follow allowed_evidence_ids."
)


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
    inp = row["input"]
    tgt = row["target_output"]
    user = json.dumps(inp, ensure_ascii=False)
    assistant = json.dumps(tgt, ensure_ascii=False)
    prompt = f"{SYSTEM_PROMPT}\n\nINPUT_JSON:\n{user}\n\nOUTPUT_JSON:\n"
    return prompt, assistant


def dry_run(train_path: Path) -> None:
    rows = _read_jsonl(train_path)
    if not rows:
        raise SystemExit("Empty train.jsonl")

    # minimal checks
    missing = 0
    for r in rows:
        if "input" not in r or "target_output" not in r:
            missing += 1
    print(f"rows: {len(rows)}")
    print(f"missing input/target_output: {missing}")

    # quick sample print
    prompt, assistant = _build_example(rows[0])
    print("\n--- sample prompt (truncated) ---")
    print(prompt[:600])
    print("\n--- sample assistant json (truncated) ---")
    print(assistant[:600])


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
    except Exception as e:
        raise SystemExit(
            "Missing deps. Install: transformers peft datasets accelerate (and bitsandbytes for 4bit).\n"
            f"Original error: {e}"
        )

    rows = _read_jsonl(train_path)
    prompts = []
    completions = []
    for r in rows:
        p, c = _build_example(r)
        prompts.append(p)
        completions.append(c)

    ds = Dataset.from_dict({"prompt": prompts, "completion": completions})

    tokenizer = AutoTokenizer.from_pretrained(base_model, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model_kwargs: dict[str, Any] = {}
    if load_in_4bit:
        model_kwargs.update(
            {
                "load_in_4bit": True,
                "device_map": "auto",
            }
        )

    model = AutoModelForCausalLM.from_pretrained(base_model, **model_kwargs)

    # LoRA targets heuristic
    if lora_targets is None or len(lora_targets) == 0:
        # common transformer naming
        guess = ["q_proj", "k_proj", "v_proj", "o_proj"]
        lora_targets = guess

    peft_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=lora_targets,
    )
    model = get_peft_model(model, peft_config)

    def tokenize(batch: dict[str, list[str]]) -> dict[str, Any]:
        input_ids = []
        labels = []
        attention_mask = []
        for p_text, c_text in zip(batch["prompt"], batch["completion"]):
            full = p_text + c_text
            p_ids = tokenizer(p_text, add_special_tokens=False).input_ids
            f = tokenizer(full, add_special_tokens=False, truncation=True, max_length=max_seq_len)
            ids = f.input_ids
            # labels: ignore prompt tokens
            lab = ids.copy()
            prompt_len = min(len(p_ids), len(lab))
            for i in range(prompt_len):
                lab[i] = -100
            input_ids.append(ids)
            labels.append(lab)
            attention_mask.append(f.attention_mask)
        return {"input_ids": input_ids, "labels": labels, "attention_mask": attention_mask}

    tokenized = ds.map(tokenize, batched=True, remove_columns=ds.column_names)

    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    out_dir.mkdir(parents=True, exist_ok=True)

    args = TrainingArguments(
        output_dir=str(out_dir),
        per_device_train_batch_size=batch_size,
        num_train_epochs=epochs,
        learning_rate=lr,
        logging_steps=10,
        save_steps=200,
        save_total_limit=2,
        report_to=[],
        fp16=torch.cuda.is_available() and not load_in_4bit,
    )

    trainer = Trainer(model=model, args=args, train_dataset=tokenized, data_collator=data_collator)
    trainer.train()

    # Save adapter
    model.save_pretrained(str(out_dir / "adapter"))
    tokenizer.save_pretrained(str(out_dir / "tokenizer"))
    print(f"Saved adapter to: {out_dir / 'adapter'}")


def main() -> None:
    p = argparse.ArgumentParser(description="Train a policy LoRA/QLoRA model for PDA BJJ Coach outputs.")
    p.add_argument("--train", required=True, help="Path to train.jsonl (must contain input + target_output)")
    p.add_argument("--base_model", default="", help="HF model id or local path")
    p.add_argument("--out", required=True, help="Output directory")
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--batch_size", type=int, default=1)
    p.add_argument("--max_seq_len", type=int, default=2048)
    p.add_argument("--lora_r", type=int, default=16)
    p.add_argument("--lora_alpha", type=int, default=32)
    p.add_argument("--lora_dropout", type=float, default=0.05)
    p.add_argument("--lora_targets", default="", help="Comma-separated target module names (optional)")
    p.add_argument("--load_in_4bit", action="store_true", help="Use 4-bit loading (requires bitsandbytes)")
    p.add_argument("--dry-run", action="store_true", help="Validate dataset and print a sample, do not train")
    args = p.parse_args()

    train_path = Path(args.train).resolve()
    out_dir = Path(args.out).resolve()

    if args.dry_run:
        dry_run(train_path)
        return

    if not args.base_model:
        raise SystemExit("--base_model is required unless --dry-run")

    lora_targets = [x.strip() for x in args.lora_targets.split(",") if x.strip()] if args.lora_targets else None

    train(
        train_path=train_path,
        base_model=args.base_model,
        out_dir=out_dir,
        epochs=args.epochs,
        lr=args.lr,
        batch_size=args.batch_size,
        max_seq_len=args.max_seq_len,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        lora_targets=lora_targets,
        load_in_4bit=args.load_in_4bit,
    )


if __name__ == "__main__":
    main()
