# Canonical Repo Files

When the target repo contains these files, read them before planning or implementation and treat them as canonical.

## Required read order

1. `FACTS.md`
2. `DEV_SPEC.md`
3. `DECISIONS.md`
4. `OPEN_QUESTIONS.json`
5. `IMPLEMENTATION_PLAN.md`
6. `ARCHITECTURE_RULES.md`

## How to use each file

### `FACTS.md`

Use for:

- current repo baseline
- discovered constraints
- what already exists versus missing

Do not contradict this file without re-checking the repo.

### `DEV_SPEC.md`

Use for:

- source product scope
- behavioral requirements
- domain rules
- non-negotiable outputs and flows

If implementation ideas diverge from this file, stop and ask.

### `DECISIONS.md`

Use for:

- confirmed human choices
- explicit assumptions already accepted for this repo

If this file conflicts with older plan text, prefer the newer confirmed decision only when the conflict is explicit. Otherwise stop and ask.

### `OPEN_QUESTIONS.json`

Use for:

- unresolved questions
- confirmation gates
- areas where assumptions are still risky

If an unresolved item affects the current stage, stop and ask before coding.

### `IMPLEMENTATION_PLAN.md`

Use for:

- module order
- acceptance expectations
- execution sequencing

Do not skip ahead or change build order casually. If reordering is necessary, stop and ask.

### `ARCHITECTURE_RULES.md`

Use for:

- module boundaries
- shared abstractions
- config centralization
- dependency direction
- anti-duplication rules

Treat this file as the implementation guardrail for code structure and reuse decisions.

## Conflict policy

If the canonical files create any of these situations:

- contradictory requirements
- missing data needed for a safe implementation choice
- logic break between planned modules
- unclear acceptance criteria
- unclear test strategy

then:

- stop the current stage
- summarize the exact conflict or gap
- ask for human confirmation

Do not fabricate the missing rule.

## Scope policy

These files constrain the implementation. They do not replace repo inspection.

Always combine them with direct inspection of the actual codebase before making edits.
