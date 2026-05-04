# recruiter-identity-collection-review-fixes

Status: ready-to-implement
Owner: codex
Last updated: 2026-04-27

## Problem
The five-slice follow-up pass closed the original runtime and provenance gaps, but the review still found three defects that make the current artifacts and identity confirmation contract unsafe for live use:

- `identity_collect` rows can enter the "saved/collected" export even when the Recruiter save click failed.
- summary reporting still overcounts `full_judge` calls in `identity_collect`.
- post-open public LinkedIn hint anchoring can falsely confirm identity from any matching `/in/<slug>` text anywhere in the profile body.

## Goal
Patch the remaining correctness issues so exported "saved/collected" cohorts reflect actual Recruiter persistence, summary metrics reflect real evaluator usage, and public LinkedIn hints cannot promote identity confirmation from incidental text alone.

## Non-goals

- Do not redesign the broader `identity_collect` product contract in this slice.
- Do not retune the card scorer or ambiguity thresholds.
- Do not widen the browser extraction surface unless it is strictly required to bind public hint anchoring to a subject-owned identifier.

## Assumptions

- `plans/recruiter-identity-collection-first.md` remains the canonical v1 behavior-change plan.
- `plans/recruiter-identity-collection-followups.md` remains the canonical first stabilization pass.
- This plan is a narrow defect patch on top of the already-landed implementation, not a redesign.
- Existing `output/runs/...` artifacts remain projections and can be regenerated after the fixes land.

## Seam

- `linkedin/recruiter_identity_resolver.py` owns the `identity_collect` save outcome semantics and the public-hint confirmation logic.
- `github/recruiter_identity_report.py` owns the saved-export filter and summary accounting.
- Tests should stay concentrated in `tests/test_recruiter_identity_resolver.py` and `tests/test_recruiter_identity_report.py`.

## Proposed change

### 1. Do not treat `save_failed` identity-collect rows as successfully collected exports

Current bug:

- `_apply_identity_collect_outcome(...)` sets `collection_action = "COLLECT"` as soon as identity is confirmed.
- `_attempt_identity_collect_save(...)` may later set `project_save_state = "save_failed"`.
- `_row_is_saved_export(...)` currently includes every `identity_collect` row with `collection_action == "COLLECT"`, even when the save never persisted.

Required fix:

- Tighten the identity-collect saved-export filter in `github/recruiter_identity_report.py`.
- `identity_collect` rows should appear in `recruiter_reconciliation_saved.jsonl/csv` only when:
  - `collection_action == "COLLECT"`, and
  - `project_save_state` is one of:
    - `saved_now`
    - `already_saved`
    - `dry_run_skipped`
- Exclude `project_save_state == "save_failed"` from the saved export.

Implementation preference:

- Keep `collection_action = "COLLECT"` on the canonical row when identity is confirmed; the row still represents a confirmed identity worth retaining.
- Fix the operational export filter rather than redefining collection semantics.

### 2. Make `full_judge_call_count` mode-aware and evidence-based

Current bug:

- `build_recruiter_identity_summary(...)` increments `full_judge_call_count` for every non-failed `plausible_profile_review`.
- In `identity_collect`, opened-profile reviews now exist even though `full_judge` is never called.

Required fix:

- Change summary accounting in `github/recruiter_identity_report.py` so `full_judge_call_count` only increments for reviews that actually contain fit-evaluation evidence.
- Safe counting rule:
  - count a review only when `holistic_fit_decision` is non-empty
  - and/or `holistic_fit_path` is non-empty
- Do not infer judge usage from review existence alone.

Implementation preference:

- Use row/review contents, not mode assumptions, so legacy rows and mixed historical artifacts still summarize correctly.

### 3. Restrict post-open public LinkedIn hint anchoring to subject-owned identifiers

Current bug:

- `_apply_post_open_public_hint_anchor(...)` scans the entire opened profile innertext for a matching `/in/<slug>`.
- `get_profile_innertext()` returns broad profile body text, so the hinted slug can be matched from incidental references rather than the subject's own public profile identifier.
- Once matched, the candidate gets direct-hint evidence and `compute_post_open_identity_status(...)` upgrades identity to `confirmed`.

Required fix:

- Stop treating arbitrary innertext slug matches as subject-owned identity proof.
- Replace the current "search all profile text" behavior with one of these bounded strategies:

Preferred:

- Extract a subject-owned public LinkedIn URL from a dedicated source that actually belongs to the opened profile, then compare that URL/slug to `linkedin_url_hint`.
- Examples of acceptable sources:
  - a subject profile link/href explicitly associated with the opened card/profile
  - a dedicated extractor field that is known to represent the candidate's own public profile URL

Acceptable fallback if no subject-owned identifier is currently available:

- Disable public `/in/<slug>` anchoring entirely for now.
- Keep surface-time anchoring only for true Recruiter `/talent/profile/...` hints.
- Leave a clear code comment/TODO that public-hint anchoring must wait for subject-owned public profile URL extraction.

This slice must choose one path decisively. Do not keep the current "match any slug in free text" behavior.

## Risks

- Tightening the saved export will reduce saved/collected counts for runs where the click failed; this is desired but may surface discrepancies against prior artifacts.
- Changing `full_judge_call_count` will alter historical summary numbers for identity-collect rows; tests must pin the new interpretation.
- Disabling or narrowing public-hint anchoring may reduce some true positives until a better subject-owned identifier is available; that is preferable to false confirmation.

## Slices

- [ ] Slice 1: tighten identity-collect saved export filtering in `github/recruiter_identity_report.py`.
- [ ] Slice 2: make `full_judge_call_count` count actual holistic-fit evidence, not review presence.
- [ ] Slice 3: replace or disable free-text public LinkedIn hint anchoring in `linkedin/recruiter_identity_resolver.py`.

## Test strategy

- Narrowest relevant band first:
  - `pytest tests/test_recruiter_identity_resolver.py tests/test_recruiter_identity_report.py -q`
- Tests to add or strengthen:
  - identity-collect row with `collection_action == "COLLECT"` and `project_save_state == "save_failed"` is excluded from `recruiter_reconciliation_saved.jsonl`
  - identity-collect rows with `saved_now`, `already_saved`, and `dry_run_skipped` remain included
  - summary `full_judge_call_count` stays `0` for identity-collect opened-profile rows with empty holistic fields
  - summary `full_judge_call_count` still counts real fit-gated reviews with populated holistic fields
  - public `/in/<slug>` hint does not confirm identity from incidental free-text mention if the chosen implementation disables or narrows this path
  - if a subject-owned public URL path is implemented instead, add a positive test proving only that path anchors
- Full-suite gate before declaring done:
  - `make validate`

## Open questions

- If there is already a reliable subject-owned public LinkedIn URL available somewhere in the opened Recruiter surface, prefer using it. If not, disable public-hint anchoring for now rather than guessing from free text.

## Decisions

- 2026-04-27 — Treat `save_failed` as export-negative but keep the canonical row as `COLLECT` — separates identity truth from Recruiter persistence truth.
- 2026-04-27 — Count `full_judge` usage from holistic-fit evidence fields, not from review existence.
- 2026-04-27 — Prefer disabling public free-text slug anchoring over keeping a false-positive confirmation path.

## Follow-ups (not in this plan)

- If public LinkedIn hints remain important, add a first-class extracted subject public profile identifier in a later slice and re-enable post-open anchoring on top of that stronger source.
- Consider splitting "confirmed identity" and "successfully persisted to Recruiter project" into distinct downstream exports if operators need both views regularly.
