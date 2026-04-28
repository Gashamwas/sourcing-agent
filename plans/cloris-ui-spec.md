# Cloris UI Spec

Status: in progress
Owner: Codex
Last updated: 2026-04-27

## Problem

We have a settled product direction for Cloris as the standalone sourcing product, plus a settled desktop form factor (`FastAPI` + `pywebview` + detached Python worker), but no durable repo artifact that translates those decisions into a UI/UX spec the implementation can follow.

## Goal

Write a concise, implementation-oriented UI spec for Cloris that locks:

- product thesis and boundary
- visual system and voice rules
- screen set / information architecture
- app-process and worker-process posture as it affects UX
- operational-state rules for calm vs high-stakes moments

## Non-goals

- Implementing the desktop app
- Building frontend components
- Refactoring runtime state beyond referencing required prerequisites
- Re-opening the broader-OS vs sourcing-only product decision

## Assumptions

- Cloris is the sourcing product, not a shell for other recruiting tools.
- `runtime_state.sqlite3` remains canonical for live sourcing state.
- The desktop shell is local-first and Python-first.
- `docs/cloris-ui-spec.md` is the repo-local visual/voice source of truth, and the repo runtime model constrains how that voice appears in operational states.

## Seam

This spec sits across the current sourcing entrypoints (`linkedin/run.py`, `linkedin/session_orchestrator.py`, `github/session_orchestrator.py`), canonical runtime state (`shared/runtime_state/store.py`, `shared/runtime_state/lock.py`), brief/review machinery (`shared/preflight_v2.py`, `shared/brief_iteration.py`), and the Cloris frontend implementation under `cloris/frontend/`.

## Proposed change

Add a product/UI spec in `docs/cloris-ui-spec.md` that implementation work can treat as the frontend and interaction source of truth for milestone-one Cloris work.

## Risks

- Writing a beautiful but operationally vague spec that ignores runtime realities
- Letting the spec drift back into generic dashboard conventions
- Under-specifying voice restrictions in urgent or broken states

## Slices

- [ ] Slice 1: Lock product thesis, boundary, and frontend form factor
- [ ] Slice 2: Define visual primitives and voice policy in `docs/cloris-ui-spec.md`
- [ ] Slice 3: Define screen set and UI state model over current runtime semantics
- [ ] Slice 4: Capture implementation-facing constraints and prerequisites

## Test strategy

- No code behavior changes; verify by repo-grounded citations and internal consistency with the settled architecture.

## Open questions

- Whether the first shipping shell includes OS notifications or keeps all ambient-state surfacing inside the window
- Whether GitHub launches are in v1 UI or LinkedIn-first with GitHub hidden behind an advanced/source toggle

## Decisions

- 2026-04-27 — Spec artifact goes in `docs/`; plan artifact stays in `plans/`.
- 2026-04-27 — Treat Cloris as the standalone sourcing product for this repo.
