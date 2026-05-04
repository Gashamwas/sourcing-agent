# boundary-auditor-subagents

Status: shipped
Owner: Codex
Last updated: 2026-04-24

## Problem

The repo had an implementer and a runtime-state diagnostic, but several other
load-bearing coexistence boundaries still depended on ad hoc human memory:
brief judgment vs search guidance, shared execution vs source-owned behavior,
and internal run evidence vs external research in market intelligence.

## Goal

Add three narrow read-only boundary-auditor subagents that make those seams more
legible without adding generic "smart helper" ceremony.

## Non-goals

- Add generic architecture or debugging agents.
- Replace plans/specs with subagents.
- Introduce runtime behavior changes.
- Recreate the TA Ops repo wholesale.

## Assumptions

- The best subagent candidates are repeated judgment tasks with a concrete
  artifact as output.
- Brief drift, execution-boundary drift, and market-intel provenance drift are
  frequent enough to justify dedicated auditors.
- These agents should stay read-only to preserve trust and avoid accidental
  authority creep.

## Seam

- `.cursor/agents/`
- `AGENTS.md`
- `docs/cursor-codex-workflow.md`

## Proposed change

1. Add `brief-boundary-auditor` for evaluation vs search-guidance discipline.
2. Add `execution-boundary-auditor` for shared-execution vs adapter-ownership
   discipline.
3. Add `market-intel-provenance-auditor` for internal-vs-external evidence
   discipline.
4. Update repo routing docs so the new agents are discoverable and scoped
   correctly.

## Risks

- too many subagents creating decision fatigue
- duplicated doctrine between subagent prompts and repo docs
- an auditor becoming a pseudo-implementer by accident

## Slices

- [x] Slice 1: add three new read-only auditor subagents
- [x] Slice 2: route AGENTS.md toward the new agents
- [x] Slice 3: route docs/cursor-codex-workflow.md toward the new agents

## Test strategy

- Documentation/config-only change; no runtime test band required
- Review for overlap, drift, and whether each agent has a concrete output
  contract

## Open questions

- Is there enough repeated market-intelligence artifact review to justify a
  fourth agent later for candidate-level evidence provenance once external
  evidence augmentation ships?
- Should any of these auditors eventually gain standard issue templates under
  `docs/` for human review outside Cursor?

## Decisions

- 2026-04-24 — Keep all three new auditors read-only — preserves trust and
  prevents authority creep
- 2026-04-24 — Add only agents that protect a coexistence boundary — avoids
  generic helper sprawl

## Follow-ups (not in this plan)

- Review whether the README should link to the workflow doc once the scaffolding
  stabilizes.
