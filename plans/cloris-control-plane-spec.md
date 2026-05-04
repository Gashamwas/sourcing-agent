# Cloris Control-Plane Spec

Status: in progress
Owner: Codex
Last updated: 2026-04-27

## Problem

`docs/cloris-ui-spec.md` captures the product thesis, visual language, and major surfaces for Cloris, but it intentionally stays clean and does not define the hard runtime/control-plane details required to build the app shell safely.

The review surfaced several unresolved implementation constraints:

- runtime state is fragmented across many per-source/per-brief SQLite files
- detached worker liveness/control needs a contract
- LinkedIn readiness is only partially probeable before a run starts
- `away` mode is neither background-calm nor high-stakes and needs distinct UX handling
- the current pause/stop model is intra-process, not cross-process

## Goal

Write a companion spec that defines the control-plane model Cloris needs:

- product-level read model over many state dirs
- worker lifecycle and liveness contract
- launch / stop / status semantics
- readiness semantics by source
- control-state taxonomy that the UI can trust

## Non-goals

- Implementing the worker or app shell
- Refactoring orchestrators
- Changing runtime-state behavior in this plan
- Rewriting the UI spec

## Assumptions

- `runtime_state.sqlite3` remains canonical inside each source/brief state directory.
- Cloris remains a local desktop product with detached workers.
- The control-plane spec should complement, not replace, `docs/cloris-ui-spec.md`.

## Seam

This spec spans `shared/output_paths.py`, `shared/runtime_state/*`, `linkedin/session_orchestrator.py`, `linkedin/orchestrator.py`, `linkedin/browser.py`, `github/session_orchestrator.py`, `github/orchestrator.py`, and the current brief/preflight surfaces where readiness and authoring claims touch runtime truth.

## Proposed change

Add `docs/cloris-control-plane-spec.md` as the implementation-facing companion to the UI spec, grounded in the current runtime topology and explicit about what exists vs what Cloris must add.

## Risks

- Over-fitting the control plane to today’s orchestrator quirks
- Accidentally turning the doc into an implementation ticket list instead of a stable contract
- Hand-waving the multi-DB aggregation problem again

## Slices

- [ ] Slice 1: Define the canonical runtime topology Cloris must treat as given
- [ ] Slice 2: Define the product-level aggregation and worker-sidecar contracts
- [ ] Slice 3: Define launch/readiness/stop/status semantics
- [ ] Slice 4: Define UI-facing control states, including `away` mode

## Test strategy

- No code behavior changes; verify by file/function citation and consistency with existing orchestrator/runtime paths.

## Open questions

- Whether v1 control plane is LinkedIn-first with GitHub hidden or both sources visible
- Whether pause exists in v1 or only stop/resume

## Decisions

- 2026-04-27 — Keep the UI spec clean; put runtime/control-plane hard edges in a sibling doc.
