# calibration-layer-vertical-agnostic

Status: ready-to-implement
Owner: Codex
Last updated: 2026-04-26

## Problem

The repo's core runtime and retrieval architecture is largely vertical-agnostic, but the calibration layer is not. Domain-specific AI/ML/BFSI vocabulary is still embedded in prompt text, novelty heuristics, search-memory inference, preflight authoring, and a few adapter heuristics across `linkedin/judgment_templates.py`, `linkedin/strategy.py`, `shared/brief_schema.py`, `shared/search_memory.py`, `shared/preflight*.py`, `shared/judger.py`, and selected adapter code.

## Goal

Make the LinkedIn calibration surface fully brief-driven so a new vertical is introduced by authoring a brief, not by changing code.

## Non-goals

- Making the GitHub adapter fully generic for non-code roles in the same slice.
- Reworking runtime-state, execution-runtime, or retrieval-design architecture.
- Replacing the dual-brief compatibility bridge (`shared/brief_loader.py`) with a single brief model.
- Editing existing brief configs in this planning slice.

## Assumptions

- New vertical launches will use the V2 structured brief path, not legacy old-format briefs.
- Strategy/search-memory consumers can keep using `shared.brief_loader.Brief` if the new calibration fields are mirrored onto the compat object.
- Existing AI briefs should preserve near-parity after migration because the required vocabulary already exists in code constants and prompt prose.
- GitHub sourcing can be treated as optional for non-technical roles; removing silent AI defaults there is sufficient for this slice.

## Seam

The seam is the calibration contract between the brief and its consumers.

- Schema and formatting: `shared/brief_schema.py`
- Compat bridge and validation: `shared/brief_loader.py`
- LinkedIn judgment prompts: `linkedin/judgment_templates.py`
- Strategy formation and adaptation: `linkedin/strategy.py`
- Search-family memory metadata: `shared/search_memory.py`
- Legacy prompt path: `shared/judger.py`
- Brief authoring prompts: `shared/preflight.py`, `shared/preflight_v2.py`
- Adapter heuristics that still assume AI roles: `linkedin/orchestrator.py`, `github/orchestrator.py`, `github/judgment_templates.py`

## Proposed change

Extend the V2 brief schema with the missing calibration vocabulary, keep the structural procedures intact, and move every remaining domain lexicon out of code and into the brief or into neutral infrastructure text.

Recommended approach:

- Add new brief fields for domain depth vocabulary, transferability examples, novelty-bucketing patterns, Boolean-planning examples, abbreviation collisions, blacklist categories, senior-role taxonomy, and domain-lane hints.
- Mirror the strategy-relevant fields onto the compat `shared.brief_loader.Brief` so `linkedin/strategy.py` can remain incremental rather than being rewritten around `_new_brief`.
- Refactor `linkedin/judgment_templates.py` to keep procedure but replace embedded AI examples and lexicon with brief-driven blocks or neutral prose.
- Refactor both strategy prompts in `linkedin/strategy.py` and remove module-level AI/FDE constants. `_opening_priority()` should score against brief-provided canonical and edge-case patterns.
- Simplify `shared/search_memory.py` so it trusts explicit strategy metadata rather than re-inferring novelty/domain from hardcoded BFSI/AI anchors.
- Remove or quarantine legacy AI-biased prompt generation in `shared/judger.py`; V2 flows must never fall back to the old prompt builders.
- Make preflight prompts neutral and stop falling back from V2 preflight into the older AI-specific preflight path.
- Strip silent AI defaults from GitHub prompt assembly and GitHub prefilters; if GitHub calibration is missing, the behavior should be explicit and reviewable rather than silently AI-biased.

Why this wins:

- It follows the existing architecture instead of fighting it.
- It keeps high-risk runtime-state code untouched.
- It allows migration in slices with parity checks instead of a risky model unification.

## Risks

- `shared/brief_loader.py` is the bridge between old and new brief models; schema drift here can create inconsistent behavior between strategy and judgment.
- `linkedin/strategy.py` and `linkedin/orchestrator.py` are policy-heavy and have many tests; prompt-shape changes can create output drift.
- `shared/search_memory.py` affects stored family projections; heuristic removal must preserve artifact shape and resume safety.
- Deleting legacy prompt builders in `shared/judger.py` before legacy brief callers are handled would break old-format runs.
- Preflight changes can make JD-only flows noisier if validation is weak or operator review expectations are unclear.

## Slices

- [ ] Slice 1: Extend `shared/brief_schema.py` with the new calibration fields and formatting helpers; extend `shared/brief_loader.py` to hydrate and validate them and mirror strategy-relevant values onto the compat brief.
- [ ] Slice 2: Refactor `linkedin/judgment_templates.py`, `linkedin/strategy.py`, and `shared/search_memory.py` to consume the new brief surface and remove hardcoded AI/BFSI constants and examples.
- [ ] Slice 3: Quarantine remaining legacy leaks in `shared/judger.py`, `shared/preflight.py`, `shared/preflight_v2.py`, and `linkedin/orchestrator.py`; make V2 flows impossible to route through AI-specific fallback text.
- [ ] Slice 4: Remove silent AI defaults from GitHub prompt assembly and GitHub bio/prefilter heuristics; require explicit brief calibration or neutral behavior.
- [ ] Slice 5: Migrate active V2 briefs, add a non-AI fixture brief, and run parity plus leakage tests.

## Test strategy

- Narrowest relevant test band to run first:
  - `pytest tests/test_extractors.py tests/test_linkedin_strategy.py tests/test_search_memory.py -q`
- Tests to add/strengthen:
  - Prompt-assembly tests proving non-AI briefs render with no leaked AI vocabulary.
  - Loader validation tests for the new calibration fields and temporary warning/final hard-fail behavior.
  - Strategy tests for brief-driven novelty bucketing and adaptation prompt assembly.
  - Preflight prompt tests ensuring no hardcoded frontier/ML examples remain.
  - GitHub tests ensuring missing calibration produces explicit neutral behavior, not AI defaults.
- Full-suite gate before declaring done:
  - `make validate`

## Open questions

- None for the LinkedIn/shared slice. For GitHub, the implementation should treat “fully generic GitHub evaluation for non-code roles” as deferred and only remove silent AI defaults now.

## Decisions

- 2026-04-26 — Keep the dual-brief bridge for this refactor — rewriting strategy and orchestration around a single brief model is higher-risk than mirroring the new calibration fields onto the compat brief.
- 2026-04-26 — Search-memory heuristics should become passive/metadata-driven rather than brief-classifying strings via hardcoded finance/AI terms — strategy already owns novelty classification.
- 2026-04-26 — Final state should fail loudly for incomplete V2 calibration, but rollout should stage through warnings while active V2 briefs are migrated.
- 2026-04-26 — GitHub genericity is not a prerequisite for LinkedIn vertical-agnosticity, but GitHub AI defaults must stop firing silently.

## Follow-ups (not in this plan)

- Migrate remaining old-format briefs to V2 so `shared/judger.py` legacy prompt builders can be deleted completely.
- Decide whether the product should expose source-adapter policy explicitly in the brief (for example, disabling GitHub for non-code roles).
- Audit `shared/brief_iteration.py` and related authoring/reporting tools for BFSI/GenAI-specific assumptions after the runtime slice lands.
