# Stage Card Template

Use this exact structure before each stage:

```md
Stage: <one-sentence stage text>
Acceptance:
- <observable acceptance criterion>
- <observable acceptance criterion>
Test:
- <exact command or exact manual verification path>
- <exact command or exact smoke path>
```

Rules:

- Keep `Stage:` to one sentence and make it the exact future commit message.
- Write acceptance as outcomes, not implementation steps.
- Write tests as executable commands whenever possible.
- Include smoke coverage when the stage affects a user-facing or top-level workflow.
- Do not start coding until the stage card is defined.
- Treat the stage card as mandatory, not optional.
- If any acceptance item or test item cannot be stated clearly, stop and ask before coding.
- If an unresolved question affects the stage, do not write a fake acceptance or fake test; stop and ask.

Use this completion gate after implementation:

```md
Result:
- acceptance met
- tests passed
- smoke passed
- commit pushed
```

Do not mark `commit pushed` unless the commit and remote push both succeeded.
