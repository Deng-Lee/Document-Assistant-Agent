# QA_TEST

Canonical adversarial QA plan generated from `test/fixtures/`.

## Fixture Inventory

- BJJ fixtures: 6
- Notes fixtures: 5

## Module: ingest

### Case ID: ingest-bjj-single
- Status: pending
- Target: Verify a single BJJ markdown ingests cleanly and produces chunks/jobs.
- Fixture(s): test/fixtures/bjj/bjj_closed_guard_arm_drag.md
- Setup command: `python3 -m server.app.api --host 127.0.0.1 --port 8000`
- Test command: `curl -s -X POST http://127.0.0.1:8000/api/ingest/file -H 'Content-Type: application/json' -d '{"path":"test/fixtures/bjj/bjj_closed_guard_arm_drag.md"}'`
- Assertion focus: doc_id/doc_version_id/chunk_ids/jobs are present and non-empty.
- Failure evidence required: Capture the raw response body and any server-side validation errors.

### Case ID: ingest-mixed-directory
- Status: pending
- Target: Verify recursive directory ingest handles both BJJ and notes fixtures without silent skips.
- Fixture(s): test/fixtures
- Setup command: `python3 -m server.app.api --host 127.0.0.1 --port 8000`
- Test command: `curl -s -X POST http://127.0.0.1:8000/api/ingest/dir -H 'Content-Type: application/json' -d '{"path":"test/fixtures","recursive":true}'`
- Assertion focus: imported_count matches actual markdown count and each result includes source_path/jobs.
- Failure evidence required: Capture the full JSON result and compare it against fixture inventory counts.

## Module: query

### Case ID: query-bjj-retrieval
- Status: pending
- Target: Probe whether BJJ retrieval pulls the correct turtle/escape evidence from real fixture text.
- Fixture(s): test/fixtures/bjj/bjj_closed_guard_arm_drag.md
- Setup command: `curl -s -X POST http://127.0.0.1:8000/api/ingest/dir -H 'Content-Type: application/json' -d '{"path":"test/fixtures","recursive":true}'`
- Test command: `curl -s -X POST http://127.0.0.1:8000/api/retrieve -H 'Content-Type: application/json' -d '{"query_text":"我在 turtle 下位被抓袖子时怎么逃脱？","mode":"full"}'`
- Assertion focus: Evidence pack contains BJJ evidence with matching turtle/escape metadata, not note fragments.
- Failure evidence required: Record evidence ids, doc_type, and summaries exactly as returned by the endpoint.

### Case ID: query-notes-retrieval
- Status: pending
- Target: Probe whether notes retrieval surfaces literary material instead of BJJ logs.
- Fixture(s): test/fixtures/notes/notes_body_learning.md
- Setup command: `curl -s -X POST http://127.0.0.1:8000/api/ingest/dir -H 'Content-Type: application/json' -d '{"path":"test/fixtures","recursive":true}'`
- Test command: `curl -s -X POST http://127.0.0.1:8000/api/retrieve -H 'Content-Type: application/json' -d '{"query_text":"Borges, mirrors, and memory","mode":"full"}'`
- Assertion focus: Returned evidence belongs to notes fixtures and carries relevant textual summaries.
- Failure evidence required: Paste the raw evidence pack and identify any domain bleed-through.

## Module: cross-encoder

### Case ID: cross-encoder-presence
- Status: pending
- Target: Determine whether a true cross-encoder stage exists and can be invoked from the repo.
- Fixture(s): test/fixtures
- Setup command: `rg -n "cross-encoder|cross_encoder|rerank" server scripts web`
- Test command: `python3 -m server.app.api --check`
- Assertion focus: Expect an explicit runnable path or record a blocker that the module is absent.
- Failure evidence required: Quote the exact terminal lines proving presence or absence; do not infer capabilities.

## Module: sft

### Case ID: sft-export-and-trainability
- Status: pending
- Target: Verify the repo can export SFT data and expose a real trainable request path from fixture-derived traces.
- Fixture(s): test/fixtures/bjj/bjj_closed_guard_arm_drag.md
- Setup command: `curl -s -X POST http://127.0.0.1:8000/api/ingest/dir -H 'Content-Type: application/json' -d '{"path":"test/fixtures","recursive":true}'`
- Test command: `python3 -m server.app.api --check`
- Assertion focus: Training backend readiness, export path, and required dependency gaps are explicit and reproducible.
- Failure evidence required: Record missing dependencies, backend status, and any export/train errors verbatim.

## Module: rerank

### Case ID: rerank-ordering-behavior
- Status: pending
- Target: Verify reranking changes or preserves ordering for a mixed-domain retrieval in a defensible way.
- Fixture(s): test/fixtures
- Setup command: `curl -s -X POST http://127.0.0.1:8000/api/ingest/dir -H 'Content-Type: application/json' -d '{"path":"test/fixtures","recursive":true}'`
- Test command: `curl -s -X POST http://127.0.0.1:8000/api/retrieve -H 'Content-Type: application/json' -d '{"query_text":"escape and memory","mode":"full"}'`
- Assertion focus: Ordering, ranks, and module notes expose rerank behavior instead of opaque results.
- Failure evidence required: Capture the returned rank signals or the absence of rerank metadata exactly.

## Module: evaluate

### Case ID: evaluate-base-run
- Status: pending
- Target: Run an eval pass on fixture-derived traces and verify metrics, external stages, and manual rubric defaults are explicit.
- Fixture(s): test/fixtures
- Setup command: `python3 -m server.app.api --check`
- Test command: `python3 scripts/run_smoke_tests.py --profile fake`
- Assertion focus: Evaluation output must expose run_status, hard metrics, and stage status without silent skips.
- Failure evidence required: Paste the exact smoke/eval output lines and any eval result JSON used in diagnosis.

## Module: trace

### Case ID: trace-persistence-and-replay
- Status: pending
- Target: Verify trace detail and replay expose enough real evidence to debug a fixture-based run.
- Fixture(s): test/fixtures
- Setup command: `python3 -m server.app.api --check`
- Test command: `curl -s http://127.0.0.1:8000/api/traces`
- Assertion focus: Traces exist, trace detail is retrievable, and replay can be invoked against a concrete trace id.
- Failure evidence required: Capture raw trace ids, trace detail payloads, and replay responses from terminal output.
