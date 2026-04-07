# Shared Candidate Execution Engine

## Purpose

The sourcing agent now has one shared candidate execution layer for canonical
candidate-stage semantics across GitHub and LinkedIn.

This layer exists to eliminate duplicated lifecycle logic in the adapters while
preserving source-specific planning and acquisition behavior.

## What The Shared Engine Owns

The shared engine lives in `shared/execution/` and owns:

- candidate discovery recording
- stage lifecycle transitions
- attempt creation and finalization
- recoverable vs terminal failure persistence
- dedup-blocking semantics
- projection flush scheduling
- side-effect event recording

The shared runtime service is the only code path that should write canonical
candidate-stage lifecycle state into `RuntimeStateStore`.

## What The Adapters Still Own

GitHub and LinkedIn still own their source-specific outer loops.

Each source now follows the same boundary shape:

- planner
- acquisition
- work-units
- side-effects

GitHub keeps ownership of:

- query planning and adaptation
- search execution and enrichment
- graph expansion behavior
- outreach/export file generation

LinkedIn keeps ownership of:

- browser navigation
- page and block cadence
- strategy/adaptation
- pending-block behavior
- session orchestration

The adapters should call the shared execution layer for candidate-stage work,
but they should not reimplement lifecycle or dedup rules locally.

## Adapter Services

The current boundary-first decomposition is intentionally lightweight.

Planner remains the existing strategy modules:

- `github/strategy.py`
- `linkedin/strategy.py`

Source-owned implementation details now live behind explicit services:

- GitHub:
  - `github/acquisition.py`
  - `github/work_units.py`
  - `github/side_effects.py`
- LinkedIn:
  - `linkedin/acquisition.py`
  - `linkedin/work_units.py`
  - `linkedin/side_effects.py`

These services own source-specific behavior while the orchestrators remain
top-level coordinators.

## Runtime Boundary

Each source now has a runtime-state bridge:

- `shared/runtime_state/github.py`
- `shared/runtime_state/linkedin.py`

Those bridges own source-specific runtime concerns such as:

- run bootstrap and resume
- work-unit hydration and checkpointing
- compatibility projection rebuild triggers
- repair and requeue helpers

They should not own candidate-stage lifecycle semantics beyond delegating into
the shared execution runtime.

## Artifact Ownership

The following files are now projection-owned compatibility artifacts, not
authoritative write targets:

- `progress.json`
- `snippets.jsonl`
- `facial_judgments.jsonl`
- `profile_summaries.jsonl`
- `final_judgments.jsonl`
- `candidate_history-*.jsonl`
- `search_memory-*.json`

They remain on disk because existing tooling still consumes them, but runtime
truth lives in `runtime_state.sqlite3`.

Direct side-effect artifacts still remain direct writes in this phase, such as:

- `run_log.jsonl`
- `outreach.jsonl`
- `saves.jsonl`
- run-report outputs
- bias-monitor checkpoint outputs

## Flush Policy

Projection flushes are intentionally not done on every candidate mutation.

- `progress.json` should flush immediately after resume-affecting mutations.
- Stage/history/search-memory artifacts should flush at work-unit checkpoints,
  shutdown, reconciliation, and admin repair/rebuild flows.
- Startup reconciliation should rebuild projections whenever interrupted
  attempts were repaired.

## Side Effects

Terminal candidate decisions are persisted before side effects run.

Side effects are recorded as durable `side_effect_result` events and do not
change canonical candidate truth. This prevents duplicated saves or outreach
after crash recovery.

Examples:

- LinkedIn save click result
- GitHub outreach generation result
- GitHub CSV/export result

## Invariants

These invariants should remain true:

- `FACIAL_YES` is not dedup-terminal.
- `FACIAL_NO` and `FACIAL_SKIP` are dedup-terminal.
- full-stage save/reject decisions are dedup-terminal.
- recoverable runtime failures land in `failed_retryable`.
- side-effect failures never rewrite the underlying business decision.
- stale or manually edited compatibility artifacts must not alter control flow.

## Guidance For Future Work

When adding a new source, reuse the shared execution runtime for candidate-stage
semantics and add only:

- source-specific planning
- source-specific acquisition
- a runtime-state bridge
- optional source-specific side effects

Do not copy candidate lifecycle, attempt bookkeeping, dedup semantics, or
projection logic into a new adapter.
