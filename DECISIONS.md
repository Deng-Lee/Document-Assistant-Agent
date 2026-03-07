# DECISIONS

## Confirmation Status
- No items in `OPEN_QUESTIONS.json` currently have `requires_confirmation=true`.
- Planning therefore proceeds with documented defaults and explicit assumptions from `DEV_SPEC.md`.

## Assumptions Adopted For Planning

### ASSUMPTION q0001: Write-intent guard vocabulary
- Initial write-intent detection is limited to:
  - `entrypoint == record`
  - user message starts with a minimal explicit verb phrase such as `帮我记录`, `记录一下`, `新增训练`, `写入日志`, `保存这条笔记`
- No fuzzy semantic write-intent classifier in V1.
- If the prefix match is ambiguous, fall back to normal chat orchestration instead of forcing write flow.

### ASSUMPTION q0002: Domain score implementation
- V1 uses histogram-only domain scoring from probe results.
- `domain_score = p_bjj`.
- No `proto_*`, `temp`, or `w_hist` vector-prototype branch in V1.

### ASSUMPTION q0003: Headness proxy and blending
- V1 implements a rank-only proxy for `headness` so replay does not depend on raw model scores.
- Initial proxy uses:
  - normalized gap between fused rank 1 and rank 3
  - top-3 sparse/dense overlap ratio
- Initial blend: `headness = 0.6 * rank_gap + 0.4 * overlap_ratio`.
- Final coefficient tuning is deferred to golden-set grid search.

### ASSUMPTION q0004: Time parsing coverage
- V1 supports:
  - explicit `YYYY-MM-DD`
  - explicit year-month references
  - `最近N天`
  - `本周`, `上周`, `本月`, `上个月`
- Cross-year handling uses calendar arithmetic in server local timezone.
- Richer Chinese relative expressions are deferred to V1.1.

### ASSUMPTION q0005: Domain thresholds
- Initial thresholds remain:
  - `domain_score >= 0.65 => BJJ`
  - `domain_score <= 0.35 => NOTES`
  - otherwise `MIXED`
- Thresholds are configurable in `runtime_config` and must be replay-visible.

### ASSUMPTION q0006: Slot entropy threshold
- Initial `slot_entropy` threshold is `> 0.6`.
- Suggested clarify slot is the maximum `H_norm` among `position`, `orientation`, `goal`.
- Tie-break order is `position > orientation > goal`.

### ASSUMPTION q0007: Evidence strength threshold
- Initial `evidence_strength < 0.4` triggers `need_replan=true`.
- This threshold is configurable in `runtime_config` and evaluated in golden-set replay.

### ASSUMPTION q0008: MIXED product behavior
- If `domain == MIXED` and clarify budget remains, Orchestrator clarifies domain first.
- If clarify budget is exhausted, system retrieves from `ALL` and produces best-effort output under existing guardrails.
- V1 does not implement a dedicated dual-domain combined answer format.

### ASSUMPTION q0009-q0018: Missing scaffold paths
- The repository is treated as greenfield.
- Scaffolding will be introduced only after explicit implementation approval from the user.
- Before applying scaffold, run `scaffold_repo.py --root .` in dry-run mode.
