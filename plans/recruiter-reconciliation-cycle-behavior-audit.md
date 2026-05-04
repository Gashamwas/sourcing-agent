# Recruiter reconciliation cycle behavior audit

Status: ready-to-implement
Owner: Codex
Last updated: 2026-04-27

## Problem

The identity-collection resolver still has evaluation-era search behavior. In a
pre-filtered Recruiter project/search, it can keep typing enriched keyword
queries such as name plus location/title terms after the visible result list has
already surfaced a sole initialized-surname candidate that should be opened for
identity confirmation.

Primary seams: `tools/run_recruiter_identity_resolver.py`,
`github/reconciliation_input.py`, `shared/identity_resolution.py`,
`linkedin/recruiter_identity_resolver.py`, and `linkedin/browser.py`.

## Goal

Document the current end-to-end behavior and patch the workflow so
`identity_collect` acts as collection-first identity resolution: find plausible
same-person Recruiter profiles, open when needed to confirm identity, and save
confirmed identities without fit evaluation.

## Non-goals

- Do not change runtime-state storage, resume semantics, or `output/` by hand.
- Do not reintroduce `full_judge` into `identity_collect`.
- Do not solve public LinkedIn `/in/<slug>` anchoring until subject-owned URL
  extraction exists.
- Do not broaden scope outside this repo or this reconciliation workflow.

## Assumptions

- Live runs use `--workflow-mode identity_collect`, the CLI default.
- The operator may use `--use-current-search` after manually applying Recruiter
  project/search filters such as location.
- In a fixed-location current search, GitHub location should not be repeated as
  a keyword Boolean unless explicitly opted in.
- GitHub synthesized headlines/bio text can help after profile read, but should
  not be first-pass Recruiter keyword constraints.
- A sole initialized-surname result can be the correct identity even when the
  Recruiter card hides the full last name.

## Current cycle

| Step | Current behavior | Risk for identity collection |
| --- | --- | --- |
| 1. Prepare inputs | Operator selects GitHub output and may manually prepare Recruiter search/project filters. | Manual filter state is assumed, not verified. |
| 2. Parse CLI | `--workflow-mode identity_collect` is default; `--use-current-search` attaches to current Recruiter search. | Workflow mode changes judging/saving, but not enough of query strategy. |
| 3. Build hints | `build_identity_hints` maps GitHub name, username, company, location, and title. Title comes from synthesized headline, bio, or judgment title. | Generated/source text can become Recruiter keyword constraints. |
| 4. Write metadata | Runner records workflow mode, paths, lead window, dry-run, location label, browser URL, and version marker. | Metadata does not enforce UI filters. |
| 5. Attach/prep browser | `use_existing_search` stores `search_location` and calls `go_back_to_results`; `prepare_search` can apply limited filters. | Current-search mode does not inspect active filters or suppress redundant keywords. |
| 6. Start lead wrapper | Each lead runs under timeout; browser recovery retries once; second failure emits `tool_failure`. | Good resilience; not the source of this bug. |
| 7. Build resolver row | `resolve_lead` derives `lookup_name`, creates `query_plan`, initializes row and `queries_tried`. | `queries_tried` currently reflects planned queries, not necessarily the safest intended search behavior. |
| 8. Build query plan | `_build_query_plan` delegates to `build_candidate_lookup_queries`: name+company, name+location, name+company+location, name+title, bare name; then maybe synthesized lookup fallback. | Enriched queries come before bare name and include location/title. |
| 9. Type keyword query | `_multi_query_lookup` calls `browser.enter_search_string`, which clears and fills the Recruiter sidebar Keywords textarea. | Every attempted query mutates the operator-prepared search. |
| 10. Read cards | `_read_top_candidates` snapshots visible cards up to `max_cards` and scores each against hints. | Visible sole result can be scored below high-confidence because the surname is initialized. |
| 11. Deduplicate/early-exit | `_multi_query_lookup` dedupes by Recruiter URL and exits only on score >= 0.9, `high_confidence_match`, or no new URLs after prior URLs existed. | There is no early stop for "one initialized-surname card worth opening." |
| 12. Apply direct hint | `_apply_direct_hint_anchor` only works for Recruiter `/talent/profile/...` hints. | Public `/in/<slug>` hints cannot currently rescue identity. |
| 13. Choose surface match | `choose_best_match` selects/classifies the kept scored set, then plausible candidates are filtered. | Plausibility thresholds are stricter than "worth opening to confirm." |
| 14. Decide open path | Multiple plausible, one strong plausible, high-confidence, or sole initialized-surname branches can open profiles. | Sole initialized-surname branch runs after full multi-query lookup, so it cannot stop bad fallback queries. |
| 15. Replay/focus/open | Before opening/saving, the resolver may replay the candidate's surfaced query and focus the card. | Provenance safety can restore an enriched query that should not have been used. |
| 16. Read profile | Opened profile is read in two phases: extract status/text/summary, then compute identity status. | This part aligns with identity collection. |
| 17. Confirm identity | `compute_post_open_identity_status` returns `confirmed`, `ambiguous`, `no_match`, or `tool_failure`. | Exact-name and direct Recruiter hint paths are strong; public hint path is disabled. |
| 18. Save/collect | Confirmed `identity_collect` rows get `collection_action = COLLECT` and a `project_save_state`. | Correct; save failure is now separated from identity truth. |
| 19. Write artifacts | Runner writes row, latest projections, summary, and collected export. | Reporting is mostly aligned after recent summary/export fixes. |

## Failure mechanism

The initialized-surname rescue is positioned too late. `resolve_lead` first
executes `_multi_query_lookup`; only after it returns does the resolver call
`_sole_candidate_merits_identity_confirmation_open`.

If the first query surfaces one initialized-surname card that should be opened,
but the card does not score high enough for existing early exits, the resolver
continues to later queries. Those later queries can include GitHub location or
title tokens even when Recruiter filters already encode location and the title
is a synthesized/source phrase. The agent is therefore following current code,
but current code is not compatible with the core identity-collection ambition.

## Risk inventory

- `identity_collect` inherits an enriched multi-query plan from older
  reconciliation behavior instead of a collection-first query policy.
- `build_candidate_lookup_queries` treats GitHub location as a keyword
  constraint even in fixed-location current-search runs.
- `build_candidate_lookup_queries` treats synthesized headline/bio text as
  title tokens, which can inject sourcing terms into Recruiter keywords.
- Bare quoted name is last in the shared query builder, not first.
- The sole initialized-surname branch protects final classification, not query
  behavior.
- Early exits do not include "one visible initialized-surname candidate worth
  opening."
- `search_location` is metadata only; it does not verify or govern UI filter
  state.
- Query replay is useful for safe opening/saving but can amplify a bad query
  plan.
- Public LinkedIn hints are disabled, so only Recruiter talent-profile hints can
  anchor identity directly.
- `max_cards` limits ambiguity awareness to the visible/read card slice.

## Proposed slices

- [ ] Slice 1: Add an identity-collection query policy.
  - Default `identity_collect` to name-first behavior.
  - Suppress GitHub-derived location/title keyword queries when
    `--use-current-search` or fixed `search_location` is active.
  - Keep enriched query behavior for `fit_gated_save` or explicit opt-in.

- [ ] Slice 2: Stop after a sole initialized-surname surface.
  - Pass the expected lead name into `_multi_query_lookup` or a small helper.
  - After each query, if exactly one card surfaced and it satisfies
    initialized-surname compatibility, stop immediately.
  - Let the existing open path confirm identity post-open.

- [ ] Slice 3: Make bare-name first for `identity_collect`.
  - Start with quoted lookup/candidate name.
  - Only try enriched fallbacks after no results, or behind an explicit query
    expansion policy.

- [ ] Slice 4: Make query provenance honest.
  - Keep `queries_tried` to attempted queries only, or add a separate planned
    query/debug field.
  - Record stop reasons such as `single_surface_name_variant_stop` or
    `identity_collect_name_first_policy`.

- [ ] Slice 5: Add regression tests for the screenshot-shaped case.
  - First query surfaces one initialized-surname card.
  - Later title/location queries would erase or distract from that card.
  - Assert the resolver opens the first card and does not type fallback
    title/location queries.

## Test strategy

- Narrowest relevant band:
  - `pytest tests/test_recruiter_identity_resolver.py tests/test_run_recruiter_identity_resolver.py -q`
- Add/strengthen:
  - Resolver test for stop-before-fallback initialized-surname behavior.
  - Query-policy test proving synthesized headline/location terms are not
    first-pass `identity_collect` keywords in current-search mode.
  - Runner/config test only if a CLI flag or metadata field is added.
- Full gate before done:
  - `make validate`

## Open questions

- Should enriched expansion be completely disabled in `identity_collect`, or
  allowed only after bare-name no-results?
- Should query policy be CLI-configurable, resolver-configurable, or derived
  strictly from `workflow_mode` plus current-search state?
- Should current-search attach inspect active company/location filters before
  deciding which hint dimensions to suppress?

## Decisions

- 2026-04-27 - Treat current behavior as code-expected but
  workflow-incompatible. The resolver is following its query plan; the query
  plan no longer matches identity collection in a pre-filtered Recruiter search.
- 2026-04-27 - Prioritize name-first and stop-early changes over another score
  threshold tweak. The bug is unnecessary search mutation before open, not only
  final scoring.

## Follow-ups not in this plan

- Add safe subject-owned public LinkedIn URL extraction before re-enabling
  public `/in/<slug>` anchoring.
- Add a current-search browser-state audit that records visible active filters
  at attach time.
- Add a dry-run query-plan preview command before browser automation starts.
