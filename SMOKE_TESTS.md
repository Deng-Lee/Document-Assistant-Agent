# SMOKE_TESTS

## Purpose
This document records the repository smoke tests that have already been executed and defines how future smoke tests must be maintained.

## Execution Rule
- Every new smoke test added during implementation must be:
  - added to `scripts/run_smoke_tests.py`
  - recorded in this document under `Smoke Test Inventory`
  - marked with the module(s) it protects
- Smoke tests should remain:
  - fast
  - deterministic
  - local-only when possible
  - independent from external model/network calls by default

## Model Profile Switching
- The repository now supports two centralized model/settings profiles:
  - fake: [server/app/core/model_profiles/fake.py](/Users/lee/Documents/AI/Document Assistant Agent/server/app/core/model_profiles/fake.py)
  - real: [server/app/core/model_profiles/real.py](/Users/lee/Documents/AI/Document Assistant Agent/server/app/core/model_profiles/real.py)
- Active profile loader:
  - [server/app/core/model_profiles/loader.py](/Users/lee/Documents/AI/Document Assistant Agent/server/app/core/model_profiles/loader.py)
- Environment switch:
  - `PDA_MODEL_PROFILE=fake`
  - `PDA_MODEL_PROFILE=real`
- Standard smoke test entry:
  - `python3 scripts/run_smoke_tests.py --profile fake`
  - `python3 scripts/run_smoke_tests.py --profile real`

Notes:
- Current smoke tests do not call real providers yet, but the profile switch is already wired through runtime config.
- New runtime entrypoints should call `build_runtime_config()` so they inherit the active fake/real profile automatically.

## Smoke Test Inventory

### 2026-03-07: Core Schema Smoke
- Modules:
  - `server/app/core`
- Goal:
  - verify contract schemas can load and export successfully
- Coverage:
  - schema registry export
  - presence of core contract keys such as `trace_record` and `runtime_config_snapshot`
- Result:
  - passed

### 2026-03-07: Storage Smoke
- Modules:
  - `server/app/storage`
- Goal:
  - verify local persistence boundaries are usable
- Coverage:
  - SQLite schema initialization
  - document/doc_version/chunk persistence
  - file snapshot write/read
  - trace JSON write/read
- Result:
  - passed

### 2026-03-07: Ingestion Smoke
- Modules:
  - `server/app/ingestion`
  - `server/app/storage`
- Goal:
  - verify markdown ingest path can parse and persist BJJ and notes documents
- Coverage:
  - frontmatter type recognition
  - BJJ record parsing and chunk creation
  - notes heading-aware chunking
  - safe_summary fallback job generation
- Result:
  - passed

### 2026-03-07: Retrieval Smoke
- Modules:
  - `server/app/retrieval`
  - `server/app/storage`
  - `server/app/ingestion`
- Goal:
  - verify structured/BM25/RRF retrieval can produce Evidence Pack and probe stats
- Coverage:
  - retrieval plan construction
  - structured filter path
  - BM25 path
  - persistent dense vector path
  - RRF fusion
  - Evidence Pack assembly
  - probe stats generation
- Result:
  - passed

### 2026-03-07: Orchestrator Smoke
- Modules:
  - `server/app/orchestrator`
  - `server/app/retrieval`
- Goal:
  - verify orchestration state machine covers the minimum V1 routing paths
- Coverage:
  - `record` entry short-circuit to `WRITE_FLOW`
  - missing-slot clarify path
  - pending-slot resolution and re-entry into planning
- Result:
  - passed

### 2026-03-07: Agents Smoke
- Modules:
  - `server/app/agents/bjj_coach`
  - `server/app/agents/literary`
  - `server/app/retrieval`
- Goal:
  - verify BJJ coach and literary agent both produce terminal outputs against real repository contracts
- Coverage:
  - BJJ gate and deterministic final answer generation
  - BJJ validator pass path
  - literary anchor selection
  - literary final answer generation
- Result:
  - passed

### 2026-03-07: Jobs Smoke
- Modules:
  - `server/app/jobs`
  - `server/app/storage`
  - `server/app/ingestion`
- Goal:
  - verify queued jobs can be persisted, executed, and reflected back into repository state
- Coverage:
  - job enqueue and list
  - `safe_summary_build`
  - `reindex_doc_version`
  - `reembed_doc_version`
  - vector-store repopulation for `reembed_doc_version`
  - chunk `safe_summary` update after job execution
- Result:
  - passed

### 2026-03-07: API Smoke
- Modules:
  - `server/app/api`
  - `server/app/jobs`
  - `server/app/orchestrator`
  - `server/app/retrieval`
  - `server/app/ingestion`
  - `web/app`
  - `web/lib`
- Goal:
  - verify the API layer is wired to the repository services, stateful chat path, and local web shell
- Coverage:
  - app creation and route registration
  - `/`
  - `/api/health`
  - `/api/ingest/text`
  - `/api/ingest/file`
  - `/api/ingest/dir`
  - `/api/jobs`
  - `/api/jobs/run-next`
  - `/api/retrieve`
  - `/api/chat/turn`
  - `/api/traces`
- Notes:
  - current smoke uses registered FastAPI endpoint callables directly instead of `TestClient`, because the local dependency combination has a `starlette`/`httpx` incompatibility in test client construction
- Result:
  - passed

### 2026-03-07: Observability Smoke
- Modules:
  - `server/app/observability`
  - `server/app/storage`
  - `server/app/core`
- Goal:
  - verify trace/span/event capture can be assembled and persisted using the unified recorder
- Coverage:
  - trace recorder span lifecycle
  - structured event capture
  - request/retrieval/evidence/generation log binding
  - JSON trace store write/list/read round trip
- Result:
  - passed

### 2026-03-07: Evaluation Smoke
- Modules:
  - `server/app/evaluation`
  - `server/app/observability`
  - `server/app/storage`
- Goal:
  - verify frozen-trace evaluation can compute hard metrics and persist an eval run
- Coverage:
  - trace loading from trace store
  - hard metric aggregation
  - eval run result creation
  - eval result persistence and listing
- Result:
  - passed

### 2026-03-07: SFT Smoke
- Modules:
  - `server/app/sft`
  - `server/app/observability`
  - `server/app/storage`
- Goal:
  - verify trace-driven SFT export and policy checkpoint metadata path are usable end-to-end
- Coverage:
  - dataset export from frozen trace
  - manifest generation
  - `train.jsonl` conversion
  - policy checkpoint registration
  - base/policy model resolution
- Result:
  - passed

## Maintenance Rule
- If a smoke test is replaced, this document must note:
  - what changed
  - why it changed
  - which old coverage moved or was removed
- If a bug fix adds a new smoke test, append a new dated entry instead of rewriting history.
