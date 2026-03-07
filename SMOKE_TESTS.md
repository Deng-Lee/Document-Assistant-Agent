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

## Maintenance Rule
- If a smoke test is replaced, this document must note:
  - what changed
  - why it changed
  - which old coverage moved or was removed
- If a bug fix adds a new smoke test, append a new dated entry instead of rewriting history.
