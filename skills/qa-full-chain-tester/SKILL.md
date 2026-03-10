---
name: qa-full-chain-tester
description: Run a strict, serial, adversarial QA workflow against this repo by using the real markdown fixtures under `test/fixtures/` and exercising the full chain across ingest, query, cross-encoder, sft, rerank, evaluate, and trace. Use when Codex must generate concrete QA cases, execute them one by one with terminal evidence, diagnose failures, retry fixes up to 3 times, and keep `QA_TEST.md` plus `QA_TEST_PROGRESS.md` fully synchronized without human intervention.
---

# QA Full-Chain Tester

Run repo QA from real fixture documents, not toy assumptions.

## Start

Read these files first:

- `references/iron-rules.md`
- `references/doc-contract.md`

Then initialize or refresh the canonical QA docs:

```bash
python3 skills/qa-full-chain-tester/scripts/init_qa_docs.py --repo-root . --force
```

This writes:

- `QA_TEST.md`
- `QA_TEST_PROGRESS.md`

## Workflow

1. Refresh `QA_TEST.md` from the current `test/fixtures/` inventory.
2. Execute modules strictly in this order:
   - `ingest`
   - `query`
   - `cross-encoder`
   - `sft`
   - `rerank`
   - `evaluate`
   - `trace`
3. Inside each module, run exactly one case at a time.
4. For each case:
   - run the `Setup command`
   - run the `Test command`
   - capture real terminal output
   - update `QA_TEST.md` status
   - append a new attempt entry to `QA_TEST_PROGRESS.md`
5. If the case fails, diagnose the failure, apply one fix, and rerun the same case.
6. Stop retrying after 3 failed attempts for the same case.
7. Before leaving a module, rerun every case that was marked failing after a fix in that module.
8. Do not enter the next module until the current module is closed according to `references/doc-contract.md`.

## Testing Stance

- Stay hostile to false confidence.
- Prefer commands that prove behavior over code inspection alone.
- Treat missing module wiring, missing metadata, partial outputs, and silent fallback as bugs or blockers until disproved.
- If a module such as `cross-encoder` or `rerank` appears absent, prove the absence with terminal evidence and log it as a blocker; do not hand-wave it away.
- If 10 or more cases pass with no defects found, reassess the assertions before continuing.

## Evidence Rules

- Copy terminal output snippets into `Terminal Evidence`.
- Put concrete extracted values into `Note`.
- Do not write “see previous”, “same as above”, or any cross-reference shorthand.
- Do not infer values that were not printed by a command or returned by a payload.

## Repair Rules

- Make one falsifiable diagnosis per failing attempt.
- Change the smallest thing that can disprove that diagnosis.
- Rerun the same case immediately after the fix.
- If the same case fails 3 times, mark it `blocked`, record why, and stop the module.

## Resource Use

- Use `scripts/init_qa_docs.py` to build the canonical QA plan from `test/fixtures/`.
- Use `references/iron-rules.md` as the non-negotiable execution policy.
- Use `references/doc-contract.md` to validate doc formatting and module completion gates.
