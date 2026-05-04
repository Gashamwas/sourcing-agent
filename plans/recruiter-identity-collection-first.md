# recruiter-identity-collection-first

Status: ready-to-implement
Owner: codex
Last updated: 2026-04-27

## Problem
The current GitHub→LinkedIn Recruiter resolver is built as a fit-gated save flow, not an identity-collection flow. In practice that means the system can find the right Recruiter profile, open it, and still drop it from saved outputs because the brief-specific fit gate or engagement gate failed. The same workflow also has adjacent runtime/design issues: silent wrong-brief selection, single-query literal search, weak run provenance, and no recovery path for hung browser actions.

## Goal
Add an explicit identity-collection-first mode to the canonical Recruiter resolver so operators can collect identity-confirmed Recruiter profiles into the current project without any holistic-fit requirement, while preserving the legacy fit-gated path behind an explicit mode.

## Non-goals

- Do not remove the existing fit-gated reconciliation behavior.
- Do not redesign the underlying name/company/title/location scorer in this slice.
- Do not auto-collect unresolved same-name ambiguity cases.
- Do not refactor the older `linkedin/reconciliation.py` flow wholesale; reuse its lookup helpers only where needed.

## Assumptions
- `tools/run_recruiter_identity_resolver.py` is the intended operator entrypoint for this workflow.
- The new default operator behavior for this runner should be identity-first collection.
- Identity-confirmed profiles should still be collected when they are already saved, already worked, or not a fit for the current brief; those states become annotations, not blockers.
- `output/runs/...` remains artifact-only. No canonical runtime-state migration is required for this slice.
- Resume safety for this tool is file-artifact-based, so output metadata must become stricter before more live runs.

## Seam
The seam is the Recruiter-first resolution stack:
- `tools/run_recruiter_identity_resolver.py` owns CLI shape, run metadata, resume semantics, and per-lead orchestration.
- `linkedin/recruiter_identity_resolver.py` owns search/query behavior, card triage, profile-open logic, identity confirmation, fit invocation, and save attempts.
- `shared/recruiter_identity_schemas.py` and `github/recruiter_identity_report.py` define the artifact contract.
- `shared/recruiter_brief_resolution.py` owns LinkedIn brief auto-selection and must stop silently choosing the wrong version.

This should be implemented as a narrow behavioral change plus schema/report expansion, not a broad subsystem rewrite.

## Proposed change

### 1. Add explicit workflow modes
Add `--workflow-mode` to `tools/run_recruiter_identity_resolver.py` with exactly two values:
- `identity_collect`
- `fit_gated_save`
Defaults:
- Default this runner to `identity_collect`.
- Preserve the current save-gated behavior only when `workflow_mode == "fit_gated_save"`.
Execution rules:
- In `identity_collect`, do not require a LinkedIn brief or judger initialization.
- In `fit_gated_save`, keep the current brief/judger requirement.
- Record `workflow_mode` in every row and in run metadata.

### 2. Split identity confirmation from fit/save gating
Rework `linkedin/recruiter_identity_resolver.py` so profile-open handling becomes a two-step process:
1. Confirm identity.
2. Optionally evaluate fit and/or save, depending on mode.
Add these canonical row-level fields in `shared/recruiter_identity_schemas.py`:
- `workflow_mode: str`
- `identity_status: str`
- `identity_subreason: str`
- `collection_action: str`
- `collection_subreason: str`
- `project_save_state: str`
- `queries_tried: list[str]`
- `resolved_query: str`
Field semantics:
- `identity_status` values: `confirmed`, `ambiguous`, `no_match`, `tool_failure`
- `collection_action` values: `COLLECT`, `MANUAL_REVIEW`, `REJECT`
- `project_save_state` values: `saved_now`, `already_saved`, `dry_run_skipped`, `save_failed`, `not_attempted`
Legacy compatibility:
- Keep `final_action` and `final_subreason` on the schema for `fit_gated_save`.
- In `identity_collect`, they are compatibility fields only and must not drive export filtering or summary interpretation.

### 3. Reuse bounded multi-query lookup instead of single literal search
The Recruiter-first resolver should stop relying on a single `lookup_name` query. Port the bounded query strategy from `linkedin/reconciliation.py` into the Recruiter-first path:
- Build `queries_tried` from `build_candidate_lookup_queries(...)`.
- Search queries in bounded order, reusing the existing name/company/location/title query variants.
- If a direct LinkedIn hint exists, treat it as an identity anchor in the Recruiter-first path.
- Deduplicate surfaced candidates across queries by profile URL, keeping the highest-confidence card and the query that produced it.
- Set `resolved_query` to the query that surfaced the selected/opened profile.

Do not remove the recent narrow fixes:

- single-token lookup fallback from GitHub username
- sole initialized-surname rescue-open behavior

### 4. Add explicit post-open identity confirmation
Opening a profile must no longer imply confirmed identity.
After `extract_profile_from_innertext(...)`, compute an explicit post-open identity result:
- `confirmed` when one of these is true:
  - exact normalized profile name match, or
  - direct LinkedIn hint confirms the opened profile, or
  - exact/near-exact card name plus at least one structural overlap from company/title/location between the opened profile and GitHub hints
- `ambiguous` when the opened profile is plausible but not confirmed
- `no_match` when the opened profile contradicts the GitHub identity
- `tool_failure` when extraction/open/read failed
Mode behavior:
- In `identity_collect`:
  - never call `full_judge`
  - if `identity_status == confirmed`, set `collection_action = COLLECT`
  - attempt `save_candidate()` unless the profile is already saved
  - novelty, reachout, and current-brief fit are annotations only
- In `fit_gated_save`:
  - only run `decide_final_reconciliation_action(...)` after `identity_status == confirmed`
  - if identity is not confirmed, return the equivalent manual/no-match result without invoking fit

### 5. Make multi-profile ambiguity identity-first
Keep the existing multi-profile open/review path, but change its decision order:
- First identify which reviewed profiles are `identity_status == confirmed`.
- If exactly one confirmed identity exists:
  - `identity_collect`: collect that profile
  - `fit_gated_save`: run the existing fit/engagement gate on that confirmed profile
- If zero confirmed identities exist:
  - return `collection_action = MANUAL_REVIEW` or `REJECT` based on ambiguity/no-match outcome
- If more than one confirmed identity exists:
  - return `collection_action = MANUAL_REVIEW` with an identity ambiguity subreason

Do not keep the current "exactly one SAVE gate wins" rule as the primary ambiguity resolver in this mode.

### 6. Fix brief selection and strengthen provenance
`shared/recruiter_brief_resolution.py` must stop using lexicographic sibling choice.
Replacement behavior:
- Parse matching LinkedIn sibling brief filenames for numeric version suffixes.
- Prefer the highest numeric version among matching siblings.
- If multiple candidates tie, or the version cannot be compared safely, fail closed and require `--linkedin-brief`.
Run metadata in `tools/run_recruiter_identity_resolver.py` must additionally capture:
- `workflow_mode`
- `project_url`
- `max_cards`
- `skip_profile_open`
- `linkedin_brief_path` when present
- actual Recruiter URL after search preparation / attach
- lightweight code-version marker if available

Resume validation must fail if any of those values differ.

### 7. Add recovery and timeout handling
The current resolver loop can hang indefinitely on browser-side waits. Add per-lead protection in the runner:
- wrap each `resolver.resolve_lead(...)` call in a timeout
- on timeout or recoverable browser error:
  - call `browser.check_and_recover()` once
  - retry the current lead once
  - if the retry fails, append a row with `identity_status = tool_failure` and `collection_action = MANUAL_REVIEW`
- continue the run after recording the failure row

Do not attempt a broad browser-layer refactor in this slice; reuse the existing recovery hook already used by `linkedin/orchestrator.py`.

## Risks
- The schema/report contract is the real behavioral seam. If exports keep filtering on legacy `final_action == "SAVE"`, the new mode will look broken even if runtime behavior is correct.
- Post-open identity confirmation is a new decision point. Keep it conservative and test-driven so the Eri-style fix does not turn into broad false positives.
- Resume validation will become stricter; that is intentional, but any existing partially-complete output dirs may need fresh directories.
- `linkedin/recruiter_identity_resolver.py` is already policy-heavy. Prefer extraction of helper functions over large inline branching growth.
- The brief-selection fix changes existing implicit behavior; tests must cover real multi-version sibling cases before relying on it.

## Slices

- [ ] Slice 1: Add `workflow_mode`, expanded run metadata, stricter resume validation, and CLI tests in `tools/run_recruiter_identity_resolver.py`.
- [ ] Slice 2: Expand `RecruiterIdentityResolution` and report writers for mode-aware identity/collection artifacts.
- [ ] Slice 3: Port bounded multi-query lookup plus direct-hint anchoring into `linkedin/recruiter_identity_resolver.py`, recording `queries_tried` and `resolved_query`.
- [ ] Slice 4: Add explicit post-open identity confirmation and implement `identity_collect` behavior without any `full_judge` call.
- [ ] Slice 5: Rework multi-profile ambiguity to pick confirmed identities first, then apply mode-specific next steps.
- [ ] Slice 6: Replace lexicographic brief selection with version-aware/fail-closed resolution and add focused tests.
- [ ] Slice 7: Add per-lead timeout/recovery behavior and failure-row continuation semantics.

## Test strategy
- Narrowest relevant test band to run first:
  - `pytest tests/test_run_recruiter_identity_resolver.py tests/test_recruiter_identity_resolver.py tests/test_recruiter_identity_report.py tests/test_recruiter_brief_resolution.py -q`
- Tests to add/strengthen:
  - `tests/test_run_recruiter_identity_resolver.py`
    - default `workflow_mode == "identity_collect"`
    - run metadata mismatch on mode/provenance differences
    - timeout/retry/failure-row continuation
  - `tests/test_recruiter_identity_resolver.py`
    - confirmed identity collects without `full_judge`
    - sole initialized-surname rescue open collects after post-open confirmation
    - partial-name wrong-person case does not collect
    - already-saved and already-worked confirmed identities still collect, with annotation-only save state
    - multi-query recovery case where first literal query misses and a later bounded query finds the profile
    - multi-profile case with one confirmed identity and one fit-better non-match does not pick by fit
  - `tests/test_recruiter_identity_report.py`
    - mode-aware summary counts for `identity_status`, `collection_action`, `project_save_state`
    - collected export is not filtered by legacy `final_action`
  - `tests/test_recruiter_brief_resolution.py`
    - real sibling set with `v1` and `v1.4` resolves to `v1.4`
    - ambiguous/unparseable sibling sets fail closed
- Full-suite gate before declaring done:
  - `make validate`

## Open questions
None. This plan is decision-complete for a surgical v1.

## Decisions
- 2026-04-27 — Add explicit `identity_collect` and `fit_gated_save` modes instead of replacing the old flow — preserves backward compatibility while correcting the operator workflow.
- 2026-04-27 — Default this runner to `identity_collect` — this is the intended operational behavior for the GitHub→Recruiter collection pass.
- 2026-04-27 — Collect confirmed identities regardless of fit or engagement state — fit and novelty become annotations in this workflow, not blockers.
- 2026-04-27 — Keep the slice surgical — reuse older lookup helpers, but do not merge the old and new subsystems in one pass.

## Follow-ups (not in this plan)

- Revisit the underlying name scorer and thresholds after the new identity/fit boundary is in place.
- Consider unifying `linkedin/reconciliation.py` and `linkedin/recruiter_identity_resolver.py` behind one shared identity lookup engine after this v1 lands.
- Revisit artifact naming and downstream consumers once the new collection mode is proven on a staged live run.
