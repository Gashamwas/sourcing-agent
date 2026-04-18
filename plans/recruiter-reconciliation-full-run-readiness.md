# recruiter-reconciliation-full-run-readiness

Status: draft
Owner: sam
Last updated: 2026-04-17

## Problem

We have a canonical Recruiter-first reconciliation engine (`tools/run_recruiter_identity_resolver.py` → `linkedin/recruiter_identity_resolver.py`) that implements the contract in `GitHub-LinkedIn-Reconciliation-Source-of-Truth.md`, but we do not yet know whether it is ready to process the full GitHub SAVE-family cohort from the completed FDE-NYC run (actual count: **179** saved leads in `output/runs/github/forward_deployed_engineer/2026-04-11T14-17-04-451796+00-00__run-3/saves.jsonl`, commonly rounded to "~210" in conversation; `final_judgments.jsonl` is empty so the fallback path is used).

The only end-to-end live evidence we have is a **5-lead dry run** in `recruiter-reconciliation-live-dryrun-nyc/`, which produced `5× REJECT` with no SAVEs and no MANUAL_REVIEWs. That sample is too small and too REJECT-saturated to establish full-run readiness. We need to decide: what does the 5-lead run actually tell us, what is the narrowest safe next experiment, and which patches (if any) should land before we commit to a 179-lead run.

## Goal

Have a written, agreed-on readiness verdict for the 179-lead full run: either (a) run it as-is, (b) run it after a short prioritized patch list lands, or (c) run a larger staged cohort (e.g. 20–30 leads) first. The plan names the verdict, the patch list, the staged cohort, and the stop conditions.

## Non-goals

- Do **not** redesign the Recruiter-first contract. `GitHub-LinkedIn-Reconciliation-Source-of-Truth.md` is the source of truth; this plan assumes it.
- Do **not** retire `linkedin/reconciliation.py` or `tools/reconcile_github_to_linkedin.py` as part of this plan. Both already emit deprecation/redirection. That cleanup is a separate follow-up.
- Do **not** modify the LinkedIn brief (`brief-forward-deployed-engineer-us-v1.4.json`) or the GitHub brief as part of this plan. If a brief change is warranted, that is a brief-iteration plan, not a reconciliation plan.
- Do **not** touch the browser bootstrap / `connect()` / `require_recruiter_tab` contract unless a concrete regression shows up. Prior debugging session (see `agent-transcripts/2901bdab-…`) already stabilized this; treat it as a fixed boundary.
- Do **not** redo the name normalization or `shared/identity_resolution.py` scorer as part of this plan. Tune it via config constants in `shared/recruiter_ambiguity_resolution.py` only if evidence warrants.

## Assumptions

- The canonical runtime entry point remains `python3 -m tools.run_recruiter_identity_resolver` with `--use-current-search` and a human-prepared Recruiter project + location filter. The v1 contract explicitly forbids the agent from creating projects or clicking location filters, so the full run will always assume human setup.
- The canonical LinkedIn brief for this cohort is `config/Forward-Deployed-Engineer-NYC/brief-forward-deployed-engineer-us-v1.4.json`; `shared/recruiter_brief_resolution.resolve_linkedin_brief_path_for_github_run` will resolve it from the run manifest.
- The canonical input is `saves.jsonl` (179 rows) because `final_judgments.jsonl` is empty on this run; `load_saved_github_reconciliation_batch_with_fallback` handles that.
- `full_judge` / `shared.judger` is the canonical holistic-fit judge and is already initialized from the LinkedIn brief in the entry point.
- The **42 reconciliation-band tests** (`tests/test_recruiter_identity_resolver.py`, `tests/test_recruiter_reconciliation_decision.py`, `tests/test_github_reconciliation_report.py`, `tests/test_recruiter_ambiguity_resolution.py`, `tests/test_recruiter_brief_resolution.py`, `tests/test_recruiter_identity_report.py`, `tests/test_github_reconciliation_input.py`) are green on main as of 2026-04-17. Anything this plan changes must keep them green.
- "~210 leads" in the user ask is conversational shorthand; the real, canonical, on-disk cohort is 179 rows. The plan uses 179 throughout.
- Runtime-state is not directly relevant here (reconciliation reads completed GitHub run artifacts as immutable inputs and writes new artifacts alongside), so `runtime_state.sqlite3` invariants do not constrain this plan.

## Seam

The investigation surface spans three boundaries, and any patch must be attributed to exactly one:

- **Gate layer** (`shared/recruiter_reconciliation_decision.py`): canonical SAVE / MANUAL_REVIEW / REJECT + subreason mapping. Small file, easy to reason about.
- **Ambiguity / identity-open policy** (`shared/recruiter_ambiguity_resolution.py`): the numeric constants (`PLAUSIBLE_MIN_MATCH_CONFIDENCE=0.45`, `SINGLE_STRONG_PLAUSIBLE_MIN_MATCH_CONFIDENCE=0.72`, `STRUCTURAL_ANCHOR_SINGLE_OPEN_MIN_MATCH_CONFIDENCE=0.64`, `SINGLE_STRONG_MIN_GAP_VS_NEXT_RANKED_CARD=0.12`) and the tier-1 / tier-2 "single strong plausible" logic that decides whether we open a profile when there is exactly one plausible card.
- **Orchestration** (`linkedin/recruiter_identity_resolver.py`): controls the order of operations, what happens when extraction fails, and how multi-profile review feeds the gate. High-risk per `.cursor/rules/high-risk-files.mdc` overtones (not listed directly but same family as `linkedin/orchestrator.py`); targeted edits only.

`linkedin/reconciliation.py` and `tools/reconcile_github_to_linkedin.py` are **out of scope** — retired paths.

## Proposed change

This plan is primarily diagnostic + staging, with a small prioritized patch list. The shape:

### Phase 0 — Establish readiness signal from the 5-lead run

Read the 5-lead dry-run artifact (`recruiter-reconciliation-live-dryrun-nyc/recruiter_identity_resolutions_summary.json` plus `recruiter_identity_resolutions.jsonl`) and classify each outcome into one of:

| Classification | Meaning | Action implication |
|---|---|---|
| Correct REJECT | Gate made the right call on a real miss | No patch needed |
| Correct opened-profile REJECT | Gate opened profile, ran full_judge, REJECTed on real fit miss | No patch needed; confirms engine works |
| Suspicious no_plausible_profile | Real LinkedIn match exists but no card cleared `match_confidence >= 0.45` | Investigate scorer and/or `PLAUSIBLE_MIN_MATCH_CONFIDENCE` |
| Suspicious fit_reject | Opened right person, but holistic judge looks too strict vs the LinkedIn brief | Investigate brief ↔ judge interaction (out of this plan; surface as follow-up) |
| Stuck in MANUAL_REVIEW | Would have been MANUAL_REVIEW, not REJECT | Not observed in 5-lead run; re-examine if it appears in the staged cohort |
| Tool failure | extraction_failed / save click failed | Investigate browser / extractor layer |

### Baseline reading of the 5-lead run (pre-phase-0 hypothesis, to be confirmed)

- **`erosika` / Eri Barrett** — `no_plausible_profile`; top card `Eri B.` at 0.35 confidence. Plausible missed match (name variant "Eri B." is likely the same person, a full-stack dev at Plastic Labs in NYC, which is consistent with the GitHub bio). This is the kind of case `PLAUSIBLE_MIN_MATCH_CONFIDENCE` gates out. **Likely false REJECT.**
- **`mldangelo` / Michael** — `no_plausible_profile`; search was just "Michael", top 5 cards all clearly other Michaels. **Correct REJECT; root cause is `build_person_lookup_name` throwing away the surname** when `candidate_name` in `saves.jsonl` is only "Michael". This is a real bug: lookup name should fall back to `github_url`/`username` (`mldangelo` → "Michael D'Angelo") when the scraped name is a single token.
- **`keunwoochoi` / Keunwoo Choi** — single-strong-plausible path, opened profile, holistic REJECT (`fit_reject`, 0.12). The card is clearly the right person (Upstage AI Engineer, Brooklyn NYC, exact name, company overlap). The REJECT is the judge rejecting the fit, not the engine missing. **Correct engine behavior; judge's strictness against research-scientist profiles is a brief-level question.**
- **`Palashio` / Palash Shah** — multi-profile review, 3 plausible Palash Shahs opened, all REJECT, consolidated `fit_reject`. **Correct engine behavior.** Rank-1 card (Self-employed, 14-job resume) is arguably a reach-worthy profile; again, that is a judge/brief question, not an engine question.
- **`Wenyueh` / Wenyue Hua** — single-strong-plausible path, opened profile (Microsoft Research Senior Researcher, NYC, exact name), holistic REJECT (0.10). **Correct engine behavior; judge is being brief-consistent.**

So the 5-lead sample suggests the engine itself is functionally correct in ≥4/5 cases. The dominant observed failure mode is **false REJECT at the `no_plausible_profile` gate** driven by (a) degenerate lookup name ("Michael") and (b) card confidence sitting just under 0.45 for clear same-person cases (`erosika`).

### Phase 1 — Prioritized patch list (narrowest safe slices)

Only patches with P0/P1 priority are in scope for this plan. Anything P2 or lower is named here but deferred.

**P0 – Single-token lookup name fallback** (seam: `linkedin/recruiter_identity_resolver.py` or `shared/identity_resolution.py`; probably the latter)

`build_person_lookup_name(lead.candidate_name, lead.username)` currently passes through "Michael" as the Recruiter query when the GitHub `name` field is a single token. The Recruiter search then devolves into "every Michael in NYC". Change: if the lookup name has one token, fall back to a derivation from `lead.username` (e.g. camelcase/split-on-digits for `mldangelo` → "Michael D'Angelo", with the original single token kept as the first name if parseable). Strict safety rule: never invent characters not present in the source.

Value: converts a class of guaranteed false REJECTs into real name searches, which is the difference between 0 plausible cards and the actual person.

**P0 – Observability: emit pre-gate classification counts per-run**

`write_recruiter_identity_summary` already counts `final_action` and `final_subreason`. Add: counts of `identity_classification` (e.g. `no_results`, `no_confident_match`, `high_confidence_match`, `single_strong_plausible_profile`, `ambiguity_multi_review`) and counts of `opened_profile`. This is the diagnostic dimension we need to triage a 179-lead run without reading every row. Touch: `github/recruiter_identity_report.py`. Tests: `tests/test_github_reconciliation_report.py` / `tests/test_recruiter_identity_report.py`.

**P1 – Plausibility floor sensitivity knob**

`PLAUSIBLE_MIN_MATCH_CONFIDENCE = 0.45` in `shared/recruiter_ambiguity_resolution.py`. The `erosika` / `Eri B.` case lands at 0.35. Before lowering, we need to see how many of the 179 saves land in `[0.30, 0.45)` with exact-or-near-exact name overlap. Do not lower the constant blindly. Either add a per-run config override (CLI flag, plumbed through `RecruiterResolverConfig`) or leave at 0.45 and absorb the miss rate. Decision deferred to after Phase 2 signal.

**P1 – Staged cohort runner**

Add a `--lead-offset` / `--max-leads` contract (max-leads already exists) or a `--sample` strategy so we can run ordered slices of the 179-lead cohort (e.g. leads 0-19, 20-39…) without re-ordering. The current tool already takes `--max-leads`; confirm ordering is deterministic (it is, because `load_saved_github_reconciliation_batch_with_fallback` reads files in deterministic order). Minor: the CLI's `max(args.max_leads, 0)` means `--max-leads 0` silently processes nothing — harmless but worth noting.

**P2 (deferred) – Holistic-fit judge strictness**

The 5-lead run's two opened-profile REJECTs (`keunwoochoi`, `Wenyueh`) are both pure research-scientist profiles rejected for lacking production engineering / enterprise delivery. This is a brief-consistency question, not an engine question. Any change here belongs in a brief-iteration plan, not this one.

**P2 (deferred) – `already_saved_elsewhere` handling**

Not observed in the 5-lead run (`already_saved` was false for all top cards). Covered by existing tests (`tests/test_recruiter_reconciliation_decision.py`). Defer until we see it in a larger cohort.

### Phase 2 — Staged full-run gate

After P0 patches land and tests stay green:

1. Run a **20-lead cohort** (e.g. `--max-leads 20`) with `--dry-run-save`.
2. Read the enriched summary (Phase-1 observability patch) and classify outcomes using the Phase 0 table.
3. Stop conditions (any one triggers pause and re-planning):
   - ≥ 25% of opened-profile REJECTs look like judge strictness issues rather than engine issues (push into brief-iteration plan).
   - ≥ 2 `tool_failure` rows (extraction or save-click failures).
   - Any MANUAL_REVIEW / `tool_failure` cluster that points at a missing browser step.
   - Lookup-name regressions after the P0 single-token fix (sanity: no lead that previously worked now returns no results).
4. If none of the stop conditions fire, proceed to the **full 179-lead run** with `--dry-run-save` first, then a live save run once we confirm no MANUAL_REVIEW cases need human adjudication beforehand.

## Risks

- **Brief ↔ judge strictness is mislabeled as an engine bug.** The research-scientist REJECTs in the 5-lead run look correct given the brief. If we lower plausibility floors or loosen the gate, we will mask a brief question with an engine change. Guard: every change must cite the pre-change and post-change behavior on a named lead, not just "feels right".
- **P0 lookup-name fix is itself a Recruiter-behavior change.** We will be issuing a different search string for some leads. Before / after must be captured, and the before-state (single-token "Michael") must be acknowledged as a known false-REJECT bucket rather than a baseline to preserve.
- **Multi-profile review amplifies LLM judge cost.** Each plausible profile opens and runs `full_judge`; a 179-lead cohort with up to 3 profiles each can mean up to ~500 full-judge calls. Token and rate-limit exposure is real. Observability patch should include per-run counts of full-judge calls.
- **Live Recruiter save clicks.** The 5-lead run used `--dry-run-save`. The first non-dry run is a behavioral change (we are writing to the recruiter's project). First live run must be small (≤ 10 leads) and reviewed manually before any larger cohort.
- **Runtime-state invariants: not applicable here** but worth stating explicitly. Reconciliation does not write to `runtime_state.sqlite3`. Do not add a new canonical state surface as part of this plan.
- **`linkedin/recruiter_identity_resolver.py` is high-risk in the same family as `linkedin/orchestrator.py`.** Keep edits targeted. Avoid "while I'm in there" cleanup.
- **The 5 sample leads are not representative.** They were a smoke test, not a stratified sample. Phase 2 must stratify at least by (a) single-token name, (b) common name, (c) clearly unique name, (d) already_saved in Recruiter.

## Slices

- [x] Slice 1 — Phase 0 triage. Produce `plans/recruiter-reconciliation-full-run-readiness.md#phase-0-triage-notes` (append) classifying each of the 5 dry-run leads per the Phase 0 table, citing card rank + profile URL evidence. No code change.
- [x] Slice 2 — P0: single-token lookup-name fallback. Touch `shared/identity_resolution.py` (or a thin helper consumed by the resolver); add tests in `tests/test_identity_resolution.py` / `tests/test_recruiter_identity_resolver.py`. No behavior change for multi-token names.
- [ ] Slice 3 — P0: observability summary fields. Touch `github/recruiter_identity_report.py`; update `tests/test_recruiter_identity_report.py`. Backfill: re-emit summary on existing `recruiter-reconciliation-live-dryrun-nyc/` artifacts by re-running the writer (no re-run of the browser flow).
- [ ] Slice 4 — Staged 20-lead dry run and classification writeup (append to this plan).
- [ ] Slice 5 — Go/no-go decision on the full 179-lead run, recorded in Decisions below.

Each slice is independently committable. Slices 2 and 3 can go in either order. Slice 4 depends on slices 2 and 3.

## Test strategy

- Narrowest relevant test band (already green as of 2026-04-17):
  - `pytest tests/test_recruiter_identity_resolver.py tests/test_recruiter_reconciliation_decision.py tests/test_github_reconciliation_report.py tests/test_recruiter_ambiguity_resolution.py tests/test_recruiter_brief_resolution.py tests/test_recruiter_identity_report.py tests/test_github_reconciliation_input.py -q` (42 tests).
- Tests to add:
  - `tests/test_identity_resolution.py` — `build_person_lookup_name` with single-token name and derivable username, asserting the fallback-produced lookup name.
  - `tests/test_recruiter_identity_resolver.py` — a new case where `candidate_name="Michael"` and `username="mldangelo"` produces a useful recruiter search string rather than the single token.
  - `tests/test_recruiter_identity_report.py` — assert new identity_classification / opened_profile count fields on the summary JSON.
- Full-suite gate before declaring slice done: `make validate`.

## Open questions

- Should the P0 single-token fallback prefer github-display-derived names (`mldangelo` → "Michael D'Angelo") or stay conservative (e.g. `username` verbatim as a fallback "Michael mldangelo")? The recruiter surface is name-search, so a human-readable derivation is better when safe; but hallucinating apostrophes into a name is not safe. Propose: use `username` as a token splitter only when it produces obvious title-case tokens and does not invent punctuation.
- Do we want to gate the 20-lead staged run behind a manual diff of the enriched summary against the 5-lead dry run before proceeding? (Default: yes.)
- Is there appetite for running a tiny (≤5 lead) *live* non-dry-run before the 20-lead dry run, to check that Recruiter save click behavior still persists correctly? The 5-lead run used `--dry-run-save` throughout. This plan's default is to do all staging dry, then a small live sample, then full.
- Are we confident the brief strictness on research-scientist profiles is intentional, or is that a separate plan we should open in parallel (`plans/linkedin-brief-research-scientist-path.md`)?

## Decisions

- 2026-04-17 — Anchor the plan on the actual 179-lead cohort, not the conversational "~210". — The on-disk `saves.jsonl` is the canonical input; plan numbers should match reality.
- 2026-04-17 — Treat browser bootstrap / `require_recruiter_tab` as a closed boundary. — Prior session stabilized it; reopening it dilutes this plan's scope.
- 2026-04-17 — Keep the plan diagnostic-first. Only ship code patches whose need is demonstrated by a named lead in the 5-lead run or in Phase 2. — Avoids preemptive tuning of the 0.45 / 0.64 / 0.72 thresholds without evidence.

## Phase 0 triage notes

Read of `output/runs/github/forward_deployed_engineer/2026-04-11T14-17-04-451796+00-00__run-3/recruiter-reconciliation-live-dryrun-nyc/{recruiter_identity_resolutions.jsonl,recruiter_identity_resolutions_summary.json}` as of 2026-04-17. Classification uses the Phase 0 table above. Evidence is cited as (card-rank, recruiter profile URL, match_confidence).

Summary counts from the summary JSON: 5 leads, 5× REJECT, `no_plausible_profile × 2` + `fit_reject × 3`, `opened_profile_count = 3`, 0 already-saved top cards, novelty `low × 4`, reachout `unworked × 4`. Derived full-judge call count across the 5 rows is **5** (0 + 0 + 1 + 3 + 1, counting non-extraction-failed plausible profile reviews only).

| # | github_username | candidate_name | query | identity_classification | opened_profile | final_action / subreason | Triage classification | Evidence |
|---|---|---|---|---|---|---|---|---|
| 1 | `erosika` | Eri Barrett | `Eri Barrett` | `no_confident_match` | false | REJECT / `no_plausible_profile` | **Suspicious `no_plausible_profile`** | Top card rank-1 `Eri B.` at 0.35 (`/talent/profile/AEMAACEnWBQBjnIiT7e4vPtROP0SVZO8aKPMyf8?project=2004872562&searchHistoryId=20994760226`), Full-stack Developer at Plastic Labs, New York NY. GitHub bio says "agentic systems builder in NYC"; name `Eri B.` is a plausible LinkedIn first-name + initialized-surname variant of `Eri Barrett`. Gated out because 0.35 sits below `PLAUSIBLE_MIN_MATCH_CONFIDENCE = 0.45`. **Likely false REJECT at the plausibility floor.** Action: P1 (deferred per plan), not a Slice-2 blocker. |
| 2 | `mldangelo` | Michael | `Michael` | `no_confident_match` | false | REJECT / `no_plausible_profile` | **Correct REJECT given the query; degenerate lookup name is the root cause** | Query string was literally the single token `Michael`; top 5 cards were Michael Lorentzen (Sr. Director of Enterprise Sales), Michael Penrose (Recruitment Consultant), Michael Phelan, Michael Guerra, Michael Blake, all 0.35–0.38. GitHub `saves.jsonl` has `name: "Michael"` for `mldangelo`; `build_person_lookup_name("Michael", "mldangelo")` returns `"Michael"`. The gate fired correctly on the cards it was shown; the bug is upstream in the lookup-name derivation. **This is the canonical motivation for Slice 2.** |
| 3 | `keunwoochoi` | Keunwoo Choi | `Keunwoo Choi` | `single_strong_plausible_profile` | true | REJECT / `fit_reject` | **Correct opened-profile REJECT (engine)** | Rank-1 `Keunwoo Choi` at 0.69 (`/talent/profile/AEMAAAueQFABDc8IYTROPO9hWh48JSZ2cSTRlOI?project=2004872562&searchHistoryId=20994760226`), AI Engineer at Upstage · 2025–Present, Brooklyn NY. Exact name + company overlap + title overlap; rank-2 is an unrelated `Richa Namballa` at 0.03 (score gap 0.66 ≫ 0.12 threshold). Engine opened the profile, `full_judge` returned 0.12. Engine behavior is correct; the REJECT is the holistic judge being strict against a research-scientist profile against the FDE brief. **Brief-iteration question, not an engine bug.** |
| 4 | `Palashio` | Palash Shah | `Palash Shah` | `ambiguity_multi_review` | true | REJECT / `fit_reject` | **Correct opened-profile REJECT (engine)** | 3 plausible cards all named `Palash Shah`: rank-1 Self-employed NYC at 0.55 (`/talent/profile/AEMAABSWE_UBSeGPBEpsjtao_VPa3-1_Q2uhvmI`), rank-2 Data Scientist at NYSE at 0.55 (`/talent/profile/AEMAADccm3UBiIoy2hNnLkBikQB8tyteWeHxgK0`), rank-4 at 0.61 (`LinkedIn Member` at rank-3 is opaque and excluded by policy). Multi-profile review opened all three, `full_judge` REJECTed all three, consolidated to `fit_reject`. Engine executed the v1 multi-review contract correctly. Rank-1 in particular (14-job resume, Y Combinator, AI tooling background) is an engine-plausibility success — the REJECT is the judge's call. **Brief-iteration question.** |
| 5 | `Wenyueh` | Wenyue Hua | `Wenyue Hua` | `single_strong_plausible_profile` | true | REJECT / `fit_reject` | **Correct opened-profile REJECT (engine)** | Rank-1 `Wenyue Hua` at 0.69 (`/talent/profile/AEMAACnRlLAB3hn7jrWxPG4w8wqAdsO_Kja2ytE?project=2004872562&searchHistoryId=20994760226`), Senior Researcher at Microsoft · 2025–Present, New York City Metropolitan Area. Exact name + company overlap + title overlap + location overlap; only one plausible card. Engine opened the profile, `full_judge` returned 0.10. **Correct engine behavior; judge being brief-consistent against a pure research-scientist profile.** |

Ratification vs. the plan's pre-phase-0 hypothesis: **the on-disk artifacts ratify the plan's baseline reading without modification**. Every named lead's classification, URL anchor, card confidence, and engine-vs-brief attribution matches what the plan predicted. The 5/5 REJECT pattern decomposes as: 1 engine-layer bug surfaced (Michael/mldangelo → Slice 2), 1 borderline plausibility-floor case deferred to P1 (erosika), and 3 correct engine behaviors where the REJECT is owned by the holistic judge against the FDE brief (keunwoochoi, Palashio, Wenyueh). No tool-failure rows. No MANUAL_REVIEW rows. This matches the plan's conclusion: "the engine itself is functionally correct in ≥4/5 cases."

Stuck-in-MANUAL_REVIEW and Tool-failure categories from the Phase 0 table were not observed in this cohort and will be re-examined in Slice 4's staged 20-lead run.

## Follow-ups (not in this plan)

- Retire `linkedin/reconciliation.py` and `tools/reconcile_github_to_linkedin.py`. They already emit deprecation / redirection. Removal is a standalone cleanup, not a reconciliation-behavior change.
- Brief-consistency review for research-scientist rejections against the FDE LinkedIn brief. Probably a brief-iteration plan (`shared/brief_iteration.py` + `tools/iterate_brief.py`).
- Revisit `PLAUSIBLE_MIN_MATCH_CONFIDENCE = 0.45` after Phase 2 data.
- Consider a "recruiter save persistence verifier" that re-opens the saved profile on a random subset post-run and confirms the pipeline save is still there. Out of scope here; belongs in a Recruiter-observability plan.
- Add run-manifest-style metadata to the reconciliation output directory (tool version, config hash, brief hash) so future full-run artifacts are self-describing without relying on the sibling GitHub run manifest.
