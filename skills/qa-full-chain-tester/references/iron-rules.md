# Iron Rules

## Execution discipline

- Run the modules strictly in this order:
  1. `ingest`
  2. `query`
  3. `cross-encoder`
  4. `sft`
  5. `rerank`
  6. `evaluate`
  7. `trace`
- Run exactly one test case at a time.
- Do not start the next case until the current case has a terminal result and the docs are updated.
- Do not start the next module until every case in the current module is either:
  - `passed`, or
  - `failed` after exhausting the 3-retry limit with diagnosis recorded.

## Evidence discipline

- Every case must include terminal output evidence copied from the real command execution.
- `Note:` entries must contain real values pulled from terminal output or returned payloads.
- Do not write “same as previous”, “see above”, or any cross-reference shorthand.
- Do not infer hidden behavior from code structure when a terminal command can prove it.
- If a command was not run, record it as not run; do not fabricate evidence.

## Adversarial stance

- Assume the system is broken until evidence says otherwise.
- Target bug discovery, not surface confirmation.
- Treat empty success responses, skipped fields, and vague status lines as suspicious.
- If 10 or more cases pass with no issue found, stop and reassess whether the assertions are too weak.

## Retry and repair policy

- Diagnose every failure before changing code.
- Limit repair retries to 3 attempts per failing case.
- After each fix, rerun the same case before moving on.
- If a case remains failing after 3 attempts, mark it as blocked and stop the module.

## Documentation discipline

- `QA_TEST.md` is the canonical case inventory.
- `QA_TEST_PROGRESS.md` is the canonical execution log.
- Update both documents immediately after every case result.
- Keep language concrete, hostile to ambiguity, and based only on observed evidence.
