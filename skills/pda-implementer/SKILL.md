---
name: pda-implementer
description: "Build and implement the Personal Document Assistant Agent in this repo from DEV_SPEC.md (V1 includes Policy SFT). Use for: (1) generating a decision-complete IMPLEMENTATION_PLAN.md, (2) extracting open questions (待讨论/TBD/TODO) and requesting human confirmation, (3) implementing ingestion/retrieval/orchestrator/agents/observability/evaluation/SFT with replayable traces, (4) exporting SFT datasets and training a LoRA/QLoRA policy model, (5) running offline eval (hard metrics + RAGAS + judge)."
---
# pda-implementer

## Workflow (follow in order)

### 0) Preconditions
- Work inside the repo root (the folder that contains `DEV_SPEC.md`).
- Prefer non-mutating exploration first (`ls`, `rg`, `sed`, reading configs).
- When user confirmation is required:
  - If `request_user_input` tool is available, use it.
  - If not available, ask 1 concise question at a time and proceed with the recommended default if unanswered.

### 1) Environment facts (non-mutating)
Goal: produce a snapshot so plan/implementation is grounded.

Steps:
1. Read `DEV_SPEC.md`.
2. Inspect repo tree and existing code/config (`pyproject.toml` / `requirements.txt` / `package.json`, etc.).
3. Write `FACTS.md` in the repo root containing:
   - existing folders (`server/`, `web/`, `data/`, `datasets/`)
   - what is already implemented vs missing
   - runtime constraints discovered (Python version, Node, etc.)

### 2) Extract decisions and open questions
Goal: produce a decision-complete plan with explicit confirmation gates.

Steps:
1. Run `python skills/pda-implementer/scripts/extract_open_questions.py --repo . --spec DEV_SPEC.md`.
   - Output: `OPEN_QUESTIONS.json` in repo root.
2. Generate `IMPLEMENTATION_PLAN.md` in repo root:
   - Must align with `DEV_SPEC.md` V1 scope.
   - Must list modules in fixed build order:
     1) core contracts & schemas
     2) storage adapters
     3) ingestion + safe_summary job
     4) retrieval + evidence pack
     5) orchestrator (probe/replan/clarify)
     6) agents (BJJ coach + literary)
     7) observability (trace/span/event)
     8) evaluation (frozen replay + metrics + RAGAS + judge)
     9) SFT (dataset export + revision + LoRA/QLoRA training + base/policy replay)
   - Must include acceptance criteria (API response types, validator behavior, replay guarantees, eval outputs).
3. For each item in `OPEN_QUESTIONS.json` that is `requires_confirmation=true`, ask the user to confirm.
   - Record confirmed choices in `DECISIONS.md` (repo root).
   - If user does not answer, proceed with `recommended_default` and mark it as `ASSUMPTION` in `DECISIONS.md`.

### 3) Repo scaffolding (only when user explicitly requests to start implementing)
Goal: create missing folders/files to match the architecture, without overwriting existing work.

Steps:
1. Dry-run scaffold:
   - `python skills/pda-implementer/scripts/scaffold_repo.py --root .`
2. Apply scaffold only after user confirmation:
   - `python skills/pda-implementer/scripts/scaffold_repo.py --root . --apply`

### 4) Implementation loop (module-by-module)
Goal: implement with short feedback cycles; keep traces and eval runnable early.

Rules:
- After each module, run the narrowest possible checks (unit tests, schema validators, minimal API smoke tests).
- Every change that affects behavior must bump a version in runtime config (prompt_version / embedding_version_id / etc.) and be recorded in traces.

### 5) SFT (V1 required)
Goal: run a minimal end-to-end SFT loop.

Steps:
1. Export dataset from traces:
   - `python skills/pda-implementer/scripts/export_sft_dataset.py --repo . --out datasets/sft/v1/<DATE>`
2. Manually revise a small set (start with 50–100) into `train.jsonl`.
3. Train policy LoRA/QLoRA:
   - `python skills/pda-implementer/scripts/train_policy_lora.py --train datasets/sft/v1/<DATE>/train.jsonl --out data/policy_checkpoints/<RUN_ID> --dry-run`
   - Then run without `--dry-run` when environment is ready.
4. Validate improvements via frozen replay + eval report.

## References
- Read `references/spec-index.md` to navigate `DEV_SPEC.md` quickly.
- Read `references/contracts.md` for the canonical JSON contracts used by validators and exports.
- Read `references/sft-runbook.md` for the SFT dataset lifecycle and training/runbook.

## Scripts
- `scripts/extract_open_questions.py`: scan spec + repo for unknowns and missing components.
- `scripts/scaffold_repo.py`: create directory skeleton (dry-run by default).
- `scripts/validate_bjj_output.py`: enforce the BJJ output + gate policy rules from `DEV_SPEC.md`.
- `scripts/export_sft_dataset.py`: export JSONL dataset from traces.
- `scripts/train_policy_lora.py`: LoRA/QLoRA training runner (supports `--dry-run`).
- `scripts/run_eval.py`: compute hard metrics from traces + aggregate reports.
