# <topic>

Status: draft | in progress | blocked | ready-to-implement | shipped
Owner: <name>
Last updated: <YYYY-MM-DD>

## Problem

One to three sentences. What is actually wrong or missing today? Cite files/paths where relevant.

## Goal

One sentence. What will be true after this work ships?

## Non-goals

Bullet list of things this plan will *not* address, even if adjacent. Use this to prevent scope creep during implementation.

## Assumptions

Bullet list of things we are taking as given about data, APIs, config, or prior state. Each assumption should be something that, if wrong, would materially change the plan.

## Seam

Where in the code does the change happen? Name the owning file(s) and the boundary being modified. Prefer "behavior-preserving extraction" over "new abstraction" when feasible.

## Proposed change

The shape of the intervention. Not code — just enough structure for a reviewer to spot problems. If there are multiple plausible approaches, list them and say which one wins and why.

## Risks

What could go wrong? Think:
- runtime-state invariants
- projection/canonical disagreement
- high-risk files (see `.cursor/rules/high-risk-files.mdc`)
- behavior changes disguised as refactors
- test coverage gaps

## Slices

Break the work into independently-reviewable slices. Each slice should be committable on its own.

- [ ] Slice 1: ...
- [ ] Slice 2: ...
- [ ] Slice 3: ...

## Test strategy

- Narrowest relevant test band to run first:
  - `pytest tests/<file>.py -q`
- Tests to add/strengthen:
  - ...
- Full-suite gate before declaring done: `make validate` (or `python tools/run_validation.py default`)

## Open questions

Questions to resolve before implementation (or early in it). A `?` here is a red flag if this plan is marked `ready-to-implement`.

## Decisions

Decisions made during planning, with brief rationale. Append as the plan evolves; do not overwrite.

- YYYY-MM-DD — <decision> — <why>

## Follow-ups (not in this plan)

Adjacent work surfaced during planning that we deliberately deferred. One-line each.
