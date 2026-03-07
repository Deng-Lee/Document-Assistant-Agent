# ARCHITECTURE_RULES

## Purpose
This document defines the repository-level engineering rules for implementing the Personal Document Assistant. These rules apply to backend, frontend, jobs, evaluation, replay, and SFT-related code.

## Primary Goals
- Keep the codebase highly structured by functional module.
- Centralize configuration and versioned runtime behavior.
- Eliminate repeated logic through stable shared abstractions.
- Preserve replayability, auditability, and evaluability as first-class constraints.

## 1. Module Structure
- Organize code by business function first, not by technical artifact type alone.
- Follow the planned module boundaries:
  - `core`
  - `storage`
  - `ingestion`
  - `retrieval`
  - `orchestrator`
  - `agents`
  - `observability`
  - `evaluation`
  - `sft`
  - `api`
- Each module must have a clear responsibility and a narrow public surface.
- Avoid “misc”, “helpers”, or “common” dumping grounds with mixed responsibilities.
- New files and symbols must be named after their actual domain purpose.

## 2. Dependency Direction
- Dependencies must flow in one direction:
  - `core -> storage -> ingestion/retrieval/orchestrator/agents -> api`
  - `observability`, `evaluation`, and `sft` may depend on stable lower-layer contracts, but lower layers must not depend on them.
- Do not introduce circular imports or bidirectional service dependencies.
- Storage implementations must remain behind adapter/repository interfaces.
- Business logic must not directly embed SQLite-, Chroma-, or provider-specific details unless that code lives inside the relevant adapter layer.

## 3. Contract-First Development
- Define schemas, DTOs, enums, and interfaces before implementing behavior.
- Shared contracts must live in `server/app/core`.
- Frontend-facing types must be generated from or strictly aligned with backend contracts.
- Any API payload, trace payload, validator report, Evidence Pack shape, or replay input must be represented as an explicit schema.
- Do not pass anonymous dicts across module boundaries when a named contract should exist.

## 4. Configuration Rules
- Configuration must be centrally managed, not scattered through module code.
- Separate these concerns:
  - application settings
  - environment-specific settings
  - runtime behavior configuration
  - version identifiers
- All behavior-affecting thresholds, prompt versions, policy selections, embedding versions, and capture levels must be part of a unified runtime configuration model.
- Avoid hard-coded thresholds and magic numbers inside business logic.
- Default values must be defined in one place and reused everywhere.
- Any change that can affect replay, evaluation, or output behavior must be trace-visible through `runtime_config_snapshot`.

## 5. Reuse and Shared Abstractions
- Extract shared code only when the abstraction is stable and clearly improves maintainability.
- Prefer shared utilities for:
  - config loading
  - structured logging / trace emission
  - schema validation
  - error translation
  - citation / locator helpers
  - pagination, filtering, and serialization helpers
- Do not duplicate business rules across orchestrator, agents, evaluation, and replay paths.
- If the same rule appears in multiple places, move it into a single reusable function or service.
- Avoid over-abstraction that hides domain intent or makes debugging harder.

## 6. State Machine Discipline
- Multi-step behavior must be modeled explicitly, not implicitly.
- This is mandatory for:
  - orchestrator clarify flow
  - coach clarify flow
  - replay execution
  - job lifecycle
  - validator repair / degrade flow
- State transitions must be representable as structured data and trace events.
- Round limits and failure fallbacks must be enforced in code, not left to prompt behavior.

## 7. Validation and Error Handling
- Every externally visible structured output must be validated before return or persistence.
- Use typed exceptions and stable error codes instead of string-matching errors.
- Error responses must be machine-readable where possible.
- Degrade paths must be deterministic and testable.
- Validation logic must not be duplicated in multiple endpoints; keep it in shared validators/services.
- Repair attempts must be bounded and explicit.

## 8. Replayability and Auditability
- Replayability is a product requirement, not a debug convenience.
- Every user-visible decision path must preserve enough structure for replay.
- Evidence-based generation must consume explicit Evidence Pack inputs only.
- All citations must bind to `doc_version_id` and stable locators.
- Frozen replay must not depend on live retrieval state.
- Any feature that breaks traceability or replay consistency is architecturally invalid for V1.

## 9. Observability by Default
- Core workflows must emit trace/span/event data from the first implementation, not as a later enhancement.
- Logging must be structured and keyed by trace identifiers and domain identifiers.
- Avoid free-form logs when structured events are more appropriate.
- Metrics and trace payloads should be designed for both debugging and offline evaluation.
- Prompt and model behavior should be tracked through metadata, version ids, and hashes rather than uncontrolled raw logging.

## 10. Testing Rules
- Every module must be designed for isolated unit testing.
- Critical cross-module flows must have integration tests.
- Validators, gate logic, state transitions, retrieval plan construction, and replay guarantees must all have direct tests.
- Prefer deterministic test fixtures and frozen inputs over network-dependent test behavior.
- Bug fixes should include a regression test whenever practical.

## 11. API and Frontend Rules
- API handlers should be thin orchestration layers, not the home of core business logic.
- Frontend components should be split into:
  - domain-aware containers
  - reusable presentational components
  - API/client utilities
- Reusable UI patterns must be extracted when stable, especially for:
  - Evidence display
  - trace visualization
  - clarify interactions
  - form validation feedback
- Keep frontend state contracts aligned with backend schema names and semantics.

## 12. Data and Storage Rules
- Treat data stores as implementation details behind interfaces.
- Avoid coupling query logic, domain rules, and storage serialization in one function.
- Persist enough metadata to support:
  - replay
  - maintenance operations
  - evaluation
  - SFT export
- All versioned entities must be explicit and queryable.
- Maintenance paths such as reindex and reembed must be scoped, auditable, and ideally dry-runnable.

## 13. Code Organization Rules
- Keep functions and classes small enough to have a single obvious responsibility.
- Prefer composition over inheritance unless inheritance meaningfully models the domain.
- Public functions should expose intent in their names and parameter types.
- Comments should explain non-obvious constraints or invariants, not restate code mechanically.
- Avoid hidden side effects across module boundaries.

## 14. Implementation Priorities
- Build the smallest valid V1 closed loop before optional enhancements.
- Prioritize:
  1. contracts
  2. storage foundations
  3. ingestion
  4. retrieval
  5. orchestrator
  6. BJJ validator-safe generation path
  7. observability and replay
  8. evaluation
  9. SFT
- Do not prebuild V1.1 or V2 abstractions unless required by V1 correctness.

## 15. Change Management
- Any behavior-affecting change must be evaluated for:
  - schema impact
  - trace impact
  - replay impact
  - evaluation impact
  - SFT dataset impact
- If a change affects outputs, thresholds, prompt assembly, retrieval logic, or validator policy, it must be reflected in versioned runtime configuration.
- Prefer incremental, testable changes over broad rewrites.

## 16. Non-Negotiable Rules
- No duplicated business rules across modules.
- No scattered magic numbers.
- No hidden cross-layer dependencies.
- No output generation without schema validation.
- No evidence-based answer without explicit evidence traceability.
- No feature that bypasses replay, trace, or evaluation requirements for V1.
