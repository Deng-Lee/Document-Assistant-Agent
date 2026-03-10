# QA Doc Contract

## `QA_TEST.md`

Use `QA_TEST.md` as the case source of truth.

For every case, preserve these fields:

- `Case ID`
- `Status`
- `Target`
- `Fixture(s)`
- `Setup command`
- `Test command`
- `Assertion focus`
- `Failure evidence required`

Allowed status values:

- `pending`
- `running`
- `passed`
- `failed`
- `blocked`

## `QA_TEST_PROGRESS.md`

Append one flat log entry per attempt using this exact field set:

- `Module`
- `Case ID`
- `Attempt`
- `Status`
- `Command`
- `Terminal Evidence`
- `Note`
- `Diagnosis`
- `Fix Applied`
- `Re-run Required`

## Writing requirements

- `Terminal Evidence` must include the exact output snippet that justified the status.
- `Note` must include extracted concrete values from the evidence, such as:
  - trace ids
  - eval run ids
  - retrieved evidence ids
  - doc counts
  - error codes
- `Diagnosis` must name one falsifiable failure hypothesis.
- `Fix Applied` must describe the actual change made, or `none`.
- `Re-run Required` must be `yes` or `no`.

## Section completion gate

A module is complete only when:

- every case in that module has a terminal status
- every flagged issue has been rerun after the latest fix
- no open retry remains

If any module contains unresolved `failed` or `blocked` cases, do not advance to the next module silently; record the stop condition explicitly in `QA_TEST_PROGRESS.md`.
