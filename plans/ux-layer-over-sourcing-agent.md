# UX Layer Over Sourcing Agent

Status: in progress
Owner: Codex
Last updated: 2026-04-26

## Problem

The repo contains substantial operational complexity across brief schema handling, calibration capture, preflight checks, runtime state, and finalized run artifacts, but there is no customer-facing UX layer that hides those mechanics. We need a repo-grounded map of where that complexity lives and what UI surfaces could wrap it safely.

## Goal

Produce a concrete, code-referenced recommendation for the UX surfaces and shared system layer required to turn the sourcing agent into a simple paying-customer experience.

## Non-goals

- Implementing the UX layer
- Refactoring runtime state, calibration, or brief schema in this plan
- Defining cross-repo platform architecture outside this repo

## Assumptions

- `runtime_state.sqlite3` remains canonical state, with JSON/JSONL projections treated as derived compatibility views.
- The recommended UX should wrap existing repo behavior where possible rather than assuming a ground-up backend rewrite.
- The planned calibration-layer refactor may change the best long-term schema boundary, so recommendations should call out dependency on that work explicitly.

## Seam

This investigation spans the code paths that already own brief authoring/validation (`shared/brief_*`, `shared/schemas.py`, `shared/recruiter_brief_resolution.py`, `tools/iterate_brief.py`), execution/runtime state (`shared/runtime_state/*`, `shared/execution/*`, `linkedin/*`, `github/*`, `shared/preflight.py`), and review artifacts (`linkedin/run_report.py`, `github/reconciliation_report.py`, `output/*`).

## Proposed change

Read the relevant subsystems, identify the real complexity pools, and translate them into UX surfaces plus a shared backend/service layer. Ground every recommendation in actual files/functions and distinguish existing reusable machinery from missing pieces.

## Risks

- Overstating capabilities that only exist as scripts or partial adapters
- Missing runtime-state/projection nuances and recommending a UX that trusts the wrong source
- Treating LinkedIn-specific calibration vocabulary as stable when the planned refactor is likely to move that boundary

## Slices

- [ ] Slice 1: Trace brief/schema/calibration flows and existing authoring tools
- [ ] Slice 2: Trace preflight, execution, runtime-state, and live-session machinery
- [ ] Slice 3: Trace finalized outputs/review artifacts and synthesize recommended UX surfaces

## Test strategy

- No code changes planned; verification is by file/function citation and internal consistency of the investigation.

## Open questions

- How much of the future UX should be source-agnostic vs. explicitly LinkedIn-first?
- Whether the first customer UX is local/operator-hosted or a hosted web product with remote orchestration.

## Decisions

- 2026-04-26 — Use a plan artifact even for an investigation-only task — Required by repo workflow for non-trivial work.

## Follow-ups (not in this plan)

- Define a concrete backend/API shape if the UX direction is approved.
- Convert the investigation into an implementation sequence with slices and test bands.
