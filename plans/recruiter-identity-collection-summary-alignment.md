# recruiter-identity-collection-summary-alignment

Status: ready-to-implement
Owner: codex
Last updated: 2026-04-27

## Problem
The latest review-fix pass correctly removed `identity_collect` `save_failed` rows from the saved/collected export, but the run summary still reports those rows as `SAVE` because `action_counts` is derived from legacy `final_action`. That leaves the artifacts internally inconsistent:

- `recruiter_reconciliation_saved.jsonl/csv` excludes the row
- `recruiter_identity_resolutions_summary.json` still counts it as `SAVE`

This is misleading for operators who read the summary first.

## Goal
Align summary semantics with the identity-first workflow so `identity_collect` save failures are not presented as successful saves in the headline counts.

## Non-goals

- Do not redesign the canonical row contract in this slice.
- Do not change export filtering again.
- Do not revisit the broader `identity_collect` versus `fit_gated_save` product design.

## Assumptions

- `plans/recruiter-identity-collection-first.md`, `plans/recruiter-identity-collection-followups.md`, and `plans/recruiter-identity-collection-review-fixes.md` remain the canonical prior slices.
- The row-level compatibility fields (`final_action`, `final_subreason`) still need to exist for legacy consumers.
- This slice is about summary interpretation, not row-shape redesign.

## Seam

- `github/recruiter_identity_report.py` owns summary construction and is the primary implementation target.
- `tests/test_recruiter_identity_report.py` should carry most or all of the coverage for this slice.
- Touch `linkedin/recruiter_identity_resolver.py` only if summary alignment cannot be done cleanly in the report layer alone.

## Proposed change

### 1. Make summary action counting mode-aware

Current bug:

- `build_recruiter_identity_summary(...)` always derives `action_counts` from `final_action`.
- In `identity_collect`, confirmed identities still stamp `final_action = "SAVE"` for compatibility even when `project_save_state == "save_failed"`.
- That means a failed Recruiter save can still appear under `action_counts["SAVE"]`.

Required fix:

- Introduce a summary-only action normalization rule in `github/recruiter_identity_report.py`.
- For `identity_collect` rows:
  - `collection_action == "COLLECT"` with `project_save_state in {saved_now, already_saved, dry_run_skipped}` should count as `SAVE`
  - `collection_action == "COLLECT"` with `project_save_state == "save_failed"` should NOT count as `SAVE`
  - the failure should count as `MANUAL_REVIEW` with subreason `tool_failure`, or another equally explicit non-save bucket chosen consistently in this slice
  - `MANUAL_REVIEW` and `REJECT` collection actions should continue to summarize as their obvious action equivalents
- For `fit_gated_save` and legacy rows:
  - keep the current `final_action` / `final_subreason` counting behavior

Implementation preference:

- Do not mutate the row itself in this slice.
- Add a small report-layer helper, e.g. `_summary_action_for_row(...)`, rather than scattering mode checks inline through `build_recruiter_identity_summary(...)`.

### 2. Keep subreason counting aligned with the normalized summary action

Current bug:

- If `action_counts` is normalized but `subreason_counts` still come from raw `final_subreason`, the summary can remain internally inconsistent.

Required fix:

- When a row’s summary action is remapped away from legacy `final_action`, ensure the counted subreason matches that remapped action.
- Minimum acceptable behavior for `identity_collect` `save_failed` rows:
  - action bucket should be non-save
  - subreason bucket should clearly indicate a tool/persistence failure

Implementation preference:

- Use the same helper family that normalizes action counts so action/subreason stay coupled.

### 3. Add a regression test for the exact artifact discrepancy found in review

Required test case:

- an `identity_collect` row with:
  - `collection_action = "COLLECT"`
  - `project_save_state = "save_failed"`
  - `final_action = "SAVE"`
- should:
  - be excluded from the saved export
  - and summarize as a non-save action

Also add/strengthen:

- `identity_collect` `saved_now`, `already_saved`, and `dry_run_skipped` rows still count as `SAVE`
- `fit_gated_save` rows still summarize directly from `final_action`
- `subreason_counts` match the chosen normalized action behavior for `save_failed`

## Risks

- Any mode-aware summary mapping can surprise consumers who currently treat `action_counts` as a thin histogram of raw `final_action`; tests should make the new contract explicit.
- If the report layer introduces a new synthetic summary action/subreason mapping, it must be narrowly scoped to `identity_collect` so legacy reporting remains stable.

## Slices

- [ ] Slice 1: add summary-only action/subreason normalization for `identity_collect` rows in `github/recruiter_identity_report.py`
- [ ] Slice 2: add regression coverage in `tests/test_recruiter_identity_report.py` for `save_failed` summary behavior and legacy preservation

## Test strategy

- Narrowest relevant band first:
  - `pytest tests/test_recruiter_identity_report.py -q`
- Tests to add or strengthen:
  - `identity_collect` `save_failed` row is excluded from saved export and does not count under `action_counts["SAVE"]`
  - `identity_collect` `saved_now`, `already_saved`, `dry_run_skipped` rows still count under `SAVE`
  - `fit_gated_save` and legacy rows keep existing summary behavior
  - `subreason_counts` align with the normalized `save_failed` action bucket
- Full-suite gate before declaring done:
  - `make validate`

## Open questions

- For the normalized summary action of `identity_collect` `save_failed`, prefer `MANUAL_REVIEW/tool_failure` unless the current report conventions strongly favor a different explicit non-save bucket.

## Decisions

- 2026-04-27 — Fix this in the report layer, not by changing the resolver’s compatibility fields.
- 2026-04-27 — Treat summary semantics as mode-aware for `identity_collect`; keep legacy summary behavior unchanged for `fit_gated_save`.

## Follow-ups (not in this plan)

- If summary consumers eventually need both raw compatibility counts and normalized operator-facing counts, consider publishing both explicitly in the summary JSON.
