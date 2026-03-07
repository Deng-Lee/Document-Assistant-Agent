# FACTS

## Repo Snapshot
- Repo root contains `DEV_SPEC.md` and the `skills/pda-implementer/` skill assets.
- Existing top-level folders: `.git/`, `skills/`.
- Suggested product folders from `DEV_SPEC.md` do not exist yet: `server/`, `web/`, `datasets/`, `data/`, `scripts/`.

## Already Implemented
- Product specification exists in `DEV_SPEC.md`.
- Skill support assets already exist under `skills/pda-implementer/`:
  - `scripts/extract_open_questions.py`
  - `scripts/scaffold_repo.py`
  - `scripts/export_sft_dataset.py`
  - `scripts/train_policy_lora.py`
  - `scripts/run_eval.py`
  - `scripts/validate_bjj_output.py`
  - reference docs for spec index, contracts, and SFT runbook

## Missing Relative To V1 Spec
- No backend application scaffold (`server/app/...`) is present.
- No frontend scaffold (`web/...`) is present.
- No runtime data directories (`data/sqlite`, `data/chroma`, `data/filestore`, `data/traces`) are present.
- No versioned offline dataset directories (`datasets/golden`, `datasets/sft`) are present.
- No repo-level runtime or dependency configuration is present (`pyproject.toml`, `requirements*.txt`, `package.json`, lockfiles, Dockerfiles` not found).
- No tests, CI config, environment examples, or generated API/type contracts are present.

## Runtime Constraints Discovered
- Python is available enough to run local skill scripts that use the standard library.
- No Python version pin is declared in-repo.
- No Node.js version pin is declared in-repo.
- No dependency manifest is present, so backend/frontend package choices are specified only in `DEV_SPEC.md`, not yet encoded in the repo.
- Network-dependent setup is not yet represented in the repository and should be treated as future implementation work.

## Planning Implication
- This repository is currently in pre-scaffold/spec-only state.
- The next valid artifacts per `pda-implementer` are:
  - `OPEN_QUESTIONS.json`
  - `IMPLEMENTATION_PLAN.md`
- Implementation should assume greenfield scaffolding while preserving the existing skill assets and `DEV_SPEC.md`.
