# IMPLEMENTATION_PLAN

## Objective
Build the V1 Personal Document Assistant defined in `DEV_SPEC.md` as a replayable, locally deployable single-user system with:
- Hybrid RAG over BJJ logs and notes
- auditable Evidence Pack and citation discipline
- Orchestrator clarification loop
- BJJ and Literary agents
- end-to-end observability, replay, offline evaluation, and Policy SFT

## Current Baseline
- Repository is in spec-only state; no `server/`, `web/`, `datasets/`, or `data/` scaffold exists yet.
- Planning assumptions are recorded in `DECISIONS.md`.
- No blocking confirmation items were found in `OPEN_QUESTIONS.json`.

## Delivery Principles
- Implement Phase 1 / V1 only; defer V1.1+ items unless they are required for replayability or validator safety.
- Keep module dependencies one-way: `core -> storage -> ingestion/retrieval/orchestrator/agents -> observability/evaluation/sft -> api/ui`.
- Every behavior-affecting threshold or prompt must be versioned and captured in `runtime_config_snapshot`.
- Prefer deterministic logic for routing, gating, validation, replay, and evaluation; use LLMs only where the spec explicitly requires them.
- Do not scaffold or implement missing directories until explicitly requested by the user.

## Build Order

### 1. Core Contracts & Schemas
Scope:
- Define canonical schemas in `server/app/core` for:
  - runtime config and version ids
  - document, doc version, chunk, embedding version, profile version
  - `source_locators`
  - retrieval plan, probe stats, plan check, execution plan
  - Evidence Pack and rank signals
  - chat response union: `clarify_request | final_answer`
  - BJJ answer JSON modes: `FULL | AMBIGUOUS_FINAL | LOW_EVIDENCE`
  - trace/span/event payloads
  - eval case/result and SFT export sample
- Define enums and error codes for BJJ validation, gate reasons, clarify slots, task/domain values, and job status.
- Define `runtime_config` defaults for all spec thresholds and versioned prompt ids.

Implementation notes:
- Use Pydantic models plus JSON Schema export.
- Treat `doc_version_id`, `embedding_version_id`, `prompt_version`, `policy_version`, and `trace_capture_level` as required on the trace path.
- Keep contracts backend-owned; frontend types should be generated or mirrored from the same source later.

Acceptance criteria:
- Chat turn output is representable as exactly one of `clarify_request` or `final_answer`.
- BJJ answer schema encodes the validator rules from Chapter 7 and `contracts.md`.
- Evidence Pack contract requires `evidence_id`, `doc_id`, `doc_version_id`, `locator`, `safe_summary`, `metadata_digest`, and `rank_signals`.
- Trace contract requires `runtime_config_snapshot`, `request_log`, `retrieval_log`, `evidence_log`, and `generation_log`.

### 2. Storage Adapters
Scope:
- Implement repository and adapter interfaces for:
  - SQLite metadata store
  - SQLite FTS5 index
  - file store for raw markdown snapshots
  - Chroma vector store with `embedding_version_id` isolation
  - trace store for structural logs and optional excerpt snapshots
  - job state persistence
- Create storage schema and migrations for documents, versions, chunks, embeddings, traces, eval runs, profiles, and jobs.
- Establish the single-source-of-truth split from the spec:
  - SQLite for metadata/logging/filtering
  - file store for raw source snapshots
  - Chroma for dense retrieval

Implementation notes:
- Bind every citation and locator to `doc_version_id`.
- Design reindex/reembed operations at `doc_version_id | doc_id | all` scope.
- Persist enough metadata to rebuild Evidence Pack and frozen replay without live re-retrieval.

Acceptance criteria:
- FTS5 and Chroma adapters can be addressed through stable repository interfaces instead of leaking storage-specific logic upward.
- Embedding data is isolated by `embedding_version_id`.
- Trace retrieval can reconstruct a frozen evidence set without querying live indexes.
- Maintenance operations can enumerate impacted chunks before execution.

### 3. Ingestion + safe_summary Job
Scope:
- Implement markdown loader with newline normalization and `locator_index` generation.
- Implement frontmatter-based doc type recognition (`BJJ` or `notes`).
- Implement BJJ structured parser and validator for mandatory fields and enum constraints.
- Implement NOTES structure extraction with heading path support.
- Implement chunking:
  - BJJ: one training record per chunk
  - NOTES: semantic/section chunking with heading anchors
- Implement `source_locators` resolution from loader-produced `locator_index`.
- Implement raw/clean dual-flow text derivation:
  - raw snapshot for replay/excerpts
  - clean text for FTS and embedding
- Implement `safe_summary` background job enqueue, retry, rebuild, and persistence.

Implementation notes:
- BJJ ingestion is strict and template-driven in V1.
- Invalid BJJ records must fail before indexing and emit structured error codes.
- Ingestion must persist `DocVersion`, file snapshot, chunks, and index inputs atomically enough to avoid half-ingested versions.

Acceptance criteria:
- `POST /api/ingest/file`, `POST /api/ingest/dir`, `POST /api/record/bjj`, and `POST /api/record/notes` can all produce versioned chunk artifacts.
- Every chunk has stable `source_locators` backed by `doc_version_id`.
- `safe_summary` can be rebuilt per chunk through a job interface.
- BJJ records with missing `position`, `orientation`, `distance`, `goal`, `your_action`, or `opponent_response` are rejected deterministically.

### 4. Retrieval + Evidence Pack
Scope:
- Implement query parsing into `retrieval_plan`.
- Implement structured filtering over SQLite fields.
- Implement BM25 retrieval over FTS5.
- Implement dense retrieval over Chroma.
- Implement RRF fusion, per-document diversity, token-budget trimming, and rank logging.
- Build Evidence Pack as the only evidence source for downstream generation and replay.

Implementation notes:
- V1 uses RRF rather than score-weighted fusion.
- V1 uses histogram-only domain scoring during probe.
- Log all application-side filtering and topK expansion so retrieval stays auditable.

Acceptance criteria:
- `POST /api/retrieve` returns `retrieval_log` and `evidence_pack` with the contract fields defined in core schemas.
- Evidence Pack preserves `doc_version_id` and precise locator data for every entry.
- Filtering behavior is replay-visible, including discarded counts and final surviving hits.
- Pack building enforces `N_per_doc`, `M_docs` when possible, and token-budget-aware trimming.

### 5. Orchestrator (probe/replan/clarify)
Scope:
- Implement conversation state for:
  - `pending_slot`
  - orchestrator `clarify_round` up to 2
  - confirmed slots
  - coach clarify state namespace
- Implement Hard Guard A for write-path short-circuit.
- Implement pending-slot short-circuit parsing.
- Implement PROBE retrieval and `probe_stats`.
- Implement `plan_check`.
- Implement deterministic plan builder.
- Implement one-shot LLM replan with schema validation and deterministic fallback.
- Implement executor handoff into retrieval and agents.

Implementation notes:
- Per `DECISIONS.md`, initial defaults are:
  - minimal write-intent prefix list
  - `domain_score = p_bjj`
  - `domain_score` thresholds `0.65 / 0.35`
  - `slot_entropy > 0.6`
  - `evidence_strength < 0.4`
  - `MIXED` clarifies domain first when budget remains
- Orchestrator may invoke at most one LLM per user turn.
- Clarify responses must be template-driven, not free-form natural-language prompts.

Acceptance criteria:
- `POST /api/chat/turn` can return either an orchestrator-originated `clarify_request` or proceed to retrieval.
- Orchestrator never exceeds 2 core clarify rounds.
- `ExecutionPlan` is always traceable, schema-valid, and stored in the trace.
- LLM replan failure falls back to deterministic planning without breaking the turn.

### 6. Agents (BJJ coach + literary)
Scope:
- Implement BJJ Coach pipeline:
  - request semantics
  - evidence summary
  - evidence gate
  - single-slot tactical clarification for `opponent_control`
  - mode-aware generation
  - validator
  - repair once, then degrade deterministically
- Implement Literary pipeline:
  - NOTES-only retrieval consumption
  - top-1 `raw_excerpt` + top-2/3 `safe_summary` anchors
  - prompt assembly with citation discipline
- Implement provider abstraction for base vs policy model selection.

Implementation notes:
- BJJ Coach may only consume the frozen Evidence Pack supplied by retrieval.
- `coach_clarify_round` is capped at 1.
- Validator is product-critical, not optional cleanup.

Acceptance criteria:
- BJJ output modes satisfy the Chapter 7 policy:
  - `HIGH_EVIDENCE -> FULL`
  - `AMBIGUOUS + clarify exhausted -> AMBIGUOUS_FINAL`
  - `LOW_EVIDENCE -> LOW_EVIDENCE`
- All user-history claims in BJJ mode cite allowed evidence ids or are marked generic.
- `followup_question` never appears in final BJJ output.
- Literary final answers return text plus anchors that point back to versioned citations.

### 7. Observability (trace/span/event)
Scope:
- Implement trace/span/event models and persistence.
- Instrument ingestion, record write, retrieval, orchestration, gate, LLM calls, validator, and jobs.
- Capture `runtime_config_snapshot` and relevant version ids on every user-visible trace.
- Implement trace detail and replay endpoints.
- Implement `trace_capture_level` behavior for minimal vs debug storage.

Implementation notes:
- Default retention should favor structural logs plus locators and summaries.
- Prompt bodies should be hashed/versioned by default; only debug-mode snapshots store more content.
- Replay must support `model_variant=base|policy` on frozen evidence.

Acceptance criteria:
- `GET /api/traces/{trace_id}` can reconstruct request path, evidence selection, generation output, and validator result.
- `POST /api/replay/{trace_id}` can re-run generation against frozen evidence without live retrieval drift.
- Trace events include stage transitions, clarify events, retrieval plan snapshots, and model/token/cost metadata.
- Minimal mode avoids raw excerpt storage while preserving replay and citation auditing.

### 8. Evaluation (frozen replay + metrics + RAGAS + judge)
Scope:
- Define golden set storage under `datasets/golden`.
- Implement offline replay runner for base/policy variants.
- Implement hard metrics directly from traces and validator reports.
- Implement RAGAS input construction for NOTES and rendered BJJ answers.
- Implement optional LLM-as-judge and manual rubric integration.
- Expose evaluation APIs and result views.

Implementation notes:
- Frozen Evidence Replay is the default evaluation mode.
- Live retrieval replay is optional and secondary.
- Hard metrics are first-class because they reflect the product contract better than judge-only scoring.

Acceptance criteria:
- `POST /api/eval/run` can execute a named evaluation set and produce a persistent `eval_run_id`.
- `GET /api/eval/results` reports:
  - schema compliance
  - mode-policy consistency
  - allowed citation accuracy
  - citation coverage
  - Plan C branch count
  - drill completeness
  - low-evidence safety proxy
  - latency and cost summaries
- Failure outputs are trace-linked so a user can drill down into the underlying replay.

### 9. SFT (dataset export + revision + LoRA/QLoRA training + base/policy replay)
Scope:
- Implement trace-to-dataset export under `datasets/sft/v1/<date>/`.
- Emit `manifest.json` plus JSONL sample rows containing runtime snapshot, evidence whitelist, selected evidence, baseline output, and validator report.
- Define manual revision workflow producing `train.jsonl`.
- Integrate LoRA/QLoRA training entrypoint and policy artifact registration.
- Wire `policy` variant into replay and evaluation.

Implementation notes:
- SFT trains behavior policy, not BJJ knowledge.
- Training input must stay aligned with online generation inputs.
- Validator and fallback remain in production even after policy training.

Acceptance criteria:
- `POST /api/sft/export` or equivalent export pipeline emits versioned dataset artifacts with `trace_id` preserved.
- Training can be exercised in dry-run mode before any expensive run.
- Replays and evals can compare `base` vs `policy` on frozen evidence.
- Improvement and regression are visible through the same hard-metric report path used for base.

## Cross-Cutting Acceptance Criteria
- API response contract:
  - Chat turns return exactly one of `clarify_request` or `final_answer`.
  - Clarify payloads include `who`, `slot`, `options`, `template_id`, `round`, and `why`.
  - Final BJJ answers are always schema-valid terminal objects.
- Validator behavior:
  - Run on every BJJ final answer.
  - Attempt one repair pass only.
  - If still invalid, degrade to deterministic `LOW_EVIDENCE`.
- Replay guarantees:
  - Frozen evidence replay must not depend on live retrieval.
  - Every replayed turn includes the original `runtime_config_snapshot` plus override metadata.
  - Citations always resolve against `doc_version_id`-bound locators.
- Evaluation outputs:
  - Each eval run stores metrics, configuration, timestamp, model variant, and trace links.
  - Reports must support base/policy comparison without changing the metric definitions.

## Suggested Execution Sequence After Planning Approval
1. Run scaffold dry-run only.
2. Create core contracts and storage skeleton first.
3. Bring ingestion and retrieval to a testable baseline before any agent generation.
4. Add orchestrator and BJJ validator path before Literary polish.
5. Enable traces and replay before large-scale evaluation or SFT export.
6. Only then generate datasets, run LoRA/QLoRA dry-run, and compare base vs policy.
