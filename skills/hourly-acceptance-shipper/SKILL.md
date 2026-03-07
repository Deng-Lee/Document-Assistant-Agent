---
name: hourly-acceptance-shipper
description: Implement a repo in autonomous, roughly 1-hour acceptance-sized increments that each define acceptance criteria and test method before coding, then run tests, smoke checks, commit with a one-line summary, push to the remote branch, and continue to the next increment until the full task is complete. Use when the user wants continuous staged delivery with strict verification and automatic git shipping after each successful increment.
---
# hourly-acceptance-shipper

## Workflow

Follow this skill when the user wants end-to-end implementation without pausing after every change and expects each small phase to be verifiable, committable, and pushed automatically.

### 0) Load mandatory repo references first

Before planning or coding, check whether the repo contains the canonical project documents listed in [references/repo-canonical-files.md](references/repo-canonical-files.md).

If these files exist, read them in the required order and treat them as authoritative for:

- architecture
- scope
- implementation sequence
- accepted decisions
- allowed assumptions
- open questions

If any of these files conflict, are incomplete, or leave a logic gap that affects implementation:

- do not invent a resolution
- do not silently choose a plausible default
- stop and ask for human confirmation

### 1) Establish the delivery lane

- Inspect the repo, current branch, upstream branch, and test entrypoints before changing code.
- Verify whether the repo already has:
  - unit/integration tests
  - a smoke test entrypoint
  - lint or compile checks
  - an existing git upstream
- Prefer extending the existing test and smoke paths instead of creating parallel ones.
- If no upstream remote or no push target exists, continue implementation locally but stop before the first push and report the blocker clearly.

### 2) Split work into acceptance-sized stages

- Break the requested work into stages that are each approximately 1 hour of implementation effort.
- Make every stage independently shippable.
- If a stage is too large to verify inside one cycle, split it before coding.
- If a stage has no clear testable outcome, redefine it until it does.
- Before starting each stage, produce a stage card using the format in [references/stage-card.md](references/stage-card.md).
- Do not start implementation for a stage until its stage card has been written explicitly.

### 3) Stage execution rules

For every stage, in this exact order:

1. State the one-line stage text.
2. State the acceptance criteria.
3. State the test method.
4. Write the stage card in the exact reference format.
5. Implement the stage.
6. Add or update tests for the new behavior.
7. Add or update smoke coverage when the behavior changes a top-level workflow.
8. Run the narrowest useful checks first.
9. Run the relevant smoke path before shipping.
10. If all checks pass and there is no unresolved issue, commit and push.
11. Move directly to the next stage.

The one-line stage text must be:

- one sentence
- concrete
- scoped to one stage only
- suitable as a git commit message without edits

### 4) Verification gate

Do not commit or push a stage unless all of the following are true:

- the stage acceptance criteria are satisfied
- the declared test method has been executed
- new or changed tests pass
- relevant smoke checks pass
- there is no known unresolved bug, blocker, or TODO required for the stage to be considered complete
- there is no unresolved open question, ambiguous requirement, or architecture conflict affecting the stage

The following conditions are hard blockers for commit and push:

- unresolved item in `OPEN_QUESTIONS.json` affecting the stage
- contradiction between canonical repo files
- missing requirement detail that changes implementation behavior
- logic break between the current stage and the planned next stage
- failed or skipped test declared in the stage card
- failed or skipped relevant smoke check

If verification fails:

- fix the issue inside the same stage if feasible
- otherwise stop automatic progression
- report the exact failing check or blocker
- do not commit partial work for that stage

### 5) Git shipping rules

When a stage is green:

- if stage acceptance, tests, and smoke all pass and there is no blocker, execute `git add`, `git commit`, and `git push` directly without asking for extra user confirmation
- use the one-line stage text as the commit message exactly
- do not prepend ticket ids, prefixes, or extra commentary unless the user explicitly asked for them
- commit only the completed stage
- push immediately after the commit

Use this sequence:

- inspect canonical repo files and unresolved questions relevant to the stage
- inspect `git status --short`
- inspect current branch and upstream
- inspect the exact verification commands that just passed
- `git add -A`
- `git commit -m "<stage text>"`
- `git push` if upstream already exists
- otherwise `git push -u origin <current-branch>` if `origin` exists

Do not reorder or skip this sequence unless the user explicitly overrides it.

If any of `git add`, `git commit`, or `git push` requires permission elevation:

- stop automatic execution
- send a user message asking for confirmation before attempting the elevated git action

If push is blocked by auth, remote policy, or missing upstream:

- stop and report the exact push blocker
- do not silently skip the push if the user asked for remote shipping

### 6) Automatic continuation

- After a successful push, continue directly to the next stage without asking for confirmation.
- Repeat until the requested scope is complete.
- Stop only when:
  - the full task is finished
  - a real blocker prevents safe continuation
  - the user redirects the work

### 7) Completion conditions

Finish only when all planned stages are complete and the final stage has also passed tests, smoke checks, commit, and push.

At the end, report:

- the list of stage commit texts in order
- the final verification commands that passed
- any residual risks that were intentionally deferred

## Operating constraints

- Treat the canonical repo files in [references/repo-canonical-files.md](references/repo-canonical-files.md) as stronger than generic coding instincts.
- Do not invent requirements, implementation details, or missing logic when the canonical files are ambiguous.
- If `OPEN_QUESTIONS.json` still contains unresolved items that affect the current stage, stop and ask before coding.
- If `DECISIONS.md` conflicts with `DEV_SPEC.md` or `IMPLEMENTATION_PLAN.md`, stop and ask which source to honor.
- If a stage cannot be stated as a concrete stage card with acceptance and tests, do not start the stage.
- If a blocker appears mid-stage, do not commit partial progress under a completed-sounding message.
- Keep stages behavior-first, not file-first.
- Prefer modifying existing structure over introducing parallel abstractions.
- Keep config centralized and reuse shared helpers instead of duplicating implementation.
- Treat tests and smoke checks as part of the stage, not follow-up work.
- Never leave a stage in a state where the commit message overstates what is actually verified.
- Never batch multiple stages into one commit.

## Reference

- Read [references/stage-card.md](references/stage-card.md) before writing the first stage card.
- Read [references/repo-canonical-files.md](references/repo-canonical-files.md) before planning or coding in a repo that contains those files.
