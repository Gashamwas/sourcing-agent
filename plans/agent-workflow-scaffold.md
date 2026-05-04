# agent-workflow-scaffold

Status: shipped
Owner: Codex
Last updated: 2026-04-24

## Problem

The repo already had a strong `plans/` convention, scoped Cursor rules, and a
spec-first implementer, but it lacked the explicit identity/routing layer that
made the TA Ops repo feel productive. The missing pieces were an always-on
identity guard, a repo-local Codex/Cursor workflow doc, and one narrow read-only
diagnostic subagent.

## Goal

Add the minimal workflow scaffolding that makes Codex/Cursor handoffs and
subagent usage more legible without importing unnecessary ceremony.

## Non-goals

- Recreate the TA Ops repo wholesale.
- Add multiple generic subagents.
- Rewrite repo architecture docs.
- Change any runtime behavior.

## Assumptions

- The highest-value missing layer is identity/routing, not another implementer.
- A runtime-state diagnostic subagent is the most repeated narrow read-only job
  in this repo.
- The new scaffolding should reinforce the existing `plans/` workflow rather
  than replace it.

## Seam

- `AGENTS.md`
- `.cursor/rules/`
- `.cursor/agents/`
- `docs/`

## Proposed change

1. Add an always-on `sourcing-agent` identity guard rule.
2. Add a sourcing-specific `docs/cursor-codex-workflow.md`.
3. Update `AGENTS.md` to explicitly route users toward Plan mode,
   `sourcing-implementer`, and the new read-only diagnostic subagent.
4. Add `runtime-state-auditor` as a narrow, output-driven read-only subagent.

## Risks

- creating duplicate canon across docs
- over-prescribing workflow where simple work does not need it
- adding a subagent that becomes ceremony rather than leverage

## Slices

- [x] Slice 1: add always-on identity guard
- [x] Slice 2: add workflow doc
- [x] Slice 3: update AGENTS routing
- [x] Slice 4: add runtime-state diagnostic subagent

## Test strategy

- Documentation/config-only change; no runtime test band required
- Review for overlap, drift, and repo fit

## Open questions

- Should this repo also gain a prose/voice rule, or is that unnecessary
  ceremony here?
- Is a second narrow read-only subagent warranted later for market-intelligence
  artifact diagnostics?

## Decisions

- 2026-04-24 — Port only the high-signal pieces from TA Ops — preserves the
  useful structure without copying its ceremony
- 2026-04-24 — First narrow diagnostic subagent is runtime-state-focused — this
  repo's most repeated read-only diagnostic job is canonical/projection confusion

## Follow-ups (not in this plan)

- Review whether `README.md` should link to the workflow doc.
- Consider archiving this plan if the scaffolding remains stable.
