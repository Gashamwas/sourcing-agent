# Researcher Module Spec

Status: ready-to-implement
Owner: Sam
Last updated: 2026-05-03
Supersedes: [`docs/researcher-module-spec.md`](../docs/researcher-module-spec.md), [`plans/researcher-module-build.md`](researcher-module-build.md) (both 2026-04-29; both reference architecture that did not ship — see "Why the existing artifacts are stale" below)

The Researcher module discovers and evaluates ML researchers using academic publication records as the primary evidence layer. It is the first non-LinkedIn discovery module Cloris ships and the de-risking case for the platform's modular extension pattern.

This is the canonical spec. The two prior artifacts are preserved for product-strategy context but are superseded by this document.

## What this spec produces

A canonical spec + sliced build plan, Linear-feedable: 8 slices, each one PR. Each slice has scope / files touched / test plan / rollback. The full-suite gate is `make validate`.

## Why the existing artifacts are stale

The 2026-04-29 plans assume `plans/multi-module-foundation.md` is complete in the shape that plan described. It isn't — what actually shipped is **better but different**:

- **No `cloris/worker.py:_DISPATCH_TABLE`.** Source dispatch lives in [`cloris/launchers/__init__.py`](../cloris/launchers/__init__.py) (the `LAUNCHERS` dict at line 223), which the existing build plan does not mention. Adding a source = single-line append + 4 callables, not editing a worker dispatch table.
- **No `linkedin_project: str = ""` default-empty.** Replaced by `source_config.linkedin.project_id` nested in [`shared/brief_v2_schema.py:179-189`](../shared/brief_v2_schema.py) — and the V2 schema **already lists `"researcher"` as a recognized source-config key** (currently empty frozenset; we populate it in Slice 1).
- **No `SourceCalibration` / `FacialCalibration.sources` refactor.** Per-source signals live in `source_config.<source>` plus additive fields on `CapabilityArea`. The V2 brief schema is its own module ([`shared/brief_v2_schema.py`](../shared/brief_v2_schema.py)) — separate from the legacy [`shared/brief_schema.py`](../shared/brief_schema.py).
- **No separate `workspace_entries` / `workspace_review_events` tables.** The workspace surface aggregates from the existing `candidates` table where `terminal_decision IN ('SAVE', 'INFERENTIAL_SAVE', 'TRANSFERABLE_SAVE', 'SIGNAL_SAVE')` — see [`shared/runtime_state/read_models.py:631-636`](../shared/runtime_state/read_models.py).
- **No `AbstractSaveDestination` interface shipped.** Saves are still per-module side effects; cross-source unification happens via the post-hoc identity layer ([`shared/identity_resolution_service.py`](../shared/identity_resolution_service.py)).

This spec engages with the architecture that exists, not the one a 2-week-old plan proposed.

## Defended opinions

1. **OpenAlex is the spine.** Earlier framing listed Semantic Scholar / OpenReview / arXiv but omitted OpenAlex. OpenAlex wins on every dimension that matters: CC0 license, 100K calls/day at 10 req/s polite pool, 250M+ works, 90M+ authors with ROR-IDed institutions and ORCID, h-index + citation count + topic concepts on the author object, MAG/Crossref/PubMed/ORCID-merged identity discipline. Semantic Scholar's free pool is 1 req/s sustained and S2AND author disambiguation is weaker on common names. Semantic Scholar enriches (paper similarity, h-index cross-validation); arXiv supplies preprint discovery; OpenReview is interesting for peer-review evidence but defer to v2; Google Scholar is a non-starter (scrape-fragile, ToS exposure). This is the one place evidence pushes back on the user's framing — evidence is decisive.

2. **No researcher-specific search-string layer.** LinkedIn has `SearchString` because the recruiter sees + composes Booleans manually. Researcher queries are OpenAlex API parameters (`topic_concepts`, `venue_filter`, `min_year`, `min_citations`, `ror_country_filter`) — not human-readable. The `work_unit.payload_json` carries query params directly; no separate rendered-string layer. Maintain `work_unit.kind="researcher_author_query"` + `source_unit_id=str(query.id)` so runtime-state primitives work uniformly.

3. **Identity strategy: ORCID-when-present + `openalex:{author_id}` composite-fallback.** ORCID coverage is partial (~30-40% of ML researchers). Use as primary anchor when present; otherwise `identity_key=f"openalex:{author_id}"` — leverages OpenAlex's S2AND-disambiguated IDs. Do **not** fork the candidate identity layer. The `(brief_id, source, identity_key)` UNIQUE constraint at [`shared/runtime_state/store.py:182`](../shared/runtime_state/store.py) accepts any string; the existing identity store ([`shared/runtime_state/identity_store.py`](../shared/runtime_state/identity_store.py)) is source-agnostic at the schema level. Cross-source resolution to LinkedIn is Phase 3 (the `_extract_signals` matching in [`shared/identity_resolution_service.py:133-164`](../shared/identity_resolution_service.py) is currently linkedin/github branching; researcher↔LinkedIn lands later).

4. **Cloris workspace is the only save destination.** Researchers without LinkedIn profiles can't be saved to LinkedIn Recruiter. Every saved researcher is a `candidates` row with SAVE-class `terminal_decision`; no external `side_effects` rows. The launcher registry's `save_destination_blocker_fn` returns `None` for researcher (no per-brief destination input needed; workspace is always available). Card UI tolerates the shape — [`CandidateCard.svelte`](../cloris/frontend/src/components/CandidateCard.svelte) does NOT render `profile_url` at row level; renders `display_name` + `terminal_decision` + `save_reason` + `last_seen_at`. The TS `Source` literal at [`cloris/frontend/src/lib/types.ts:8`](../cloris/frontend/src/lib/types.ts) and the Pydantic `CandidateCardSummary.source` at [`cloris/models.py:586`](../cloris/models.py) MUST widen to include `"researcher"` (Slice 1).

5. **No reflection polish in v1.** [`market_intelligence/briefing_polish.py`](../market_intelligence/briefing_polish.py) consumes `PlannerResult`; the planner ([`market_intelligence/engine.py`](../market_intelligence/engine.py)) is LinkedIn-shaped today. A researcher planner is a separate Phase 3 deliverable. v1 ships with no post-run reflection; the recruiter sees workspace cards directly. Brief-polish at intake time IS extended (Slice 7) — that's intake, not reflection.

6. **Evaluator must populate `full_decision.rationale` + `full_decision.confidence` exactly.** The decision contract is non-negotiable — [`shared/runtime_state/read_models.py:742-806`](../shared/runtime_state/read_models.py) reads from this path and the candidate-detail + workspace surfaces depend on it. The researcher full-evaluator produces an `OpusDecision`-shaped dict written under `terminal_payload_json["full_decision"]` via the existing `SharedExecutionRuntime._build_stage_payload` path at [`shared/execution/runtime.py:339-357`](../shared/execution/runtime.py). No fork.

7. **Recruiter never types a floor at intake.** h-index varies wildly by field (theory ~5, NLP ~10, biomedical ~12); no universal-correct value, and most recruiters hiring researchers don't know the field's conventions. Asking them to type "8" into an `h_index_floor` text input is database UX masquerading as a brief. Layered resolution instead:
   - **Universal minimum** (always applies): `papers_in_window ≥ 1` in last 36 months, `h_index ≥ 3`. Excludes zero-publication candidates only — the deterministic gate's job is budget control on obvious garbage, not editorial selection.
   - **Discipline default** (when recruiter picks a discipline): overrides universal with field-appropriate values from `researcher/discipline_defaults.py` lookup (e.g., `nlp` → h_index ≥ 10, papers_in_window ≥ 3 in 24 months; `theory` → h_index ≥ 5, papers_in_window ≥ 2 in 48 months — theory cites less, slower).
   - **Explicit override** (when recruiter types a number — power-user path, not surfaced by default): wins over discipline default.
   - The wizard surfaces the resolved floor in editorial language: "I'll skip authors with fewer than 3 first-author papers in the last 24 months — based on your discipline. Tighten?" Not "h_index_floor: ___".
   - Discipline picker is a discrete dropdown in the where_to_look chapter (single-select: `ml_general | nlp | vision | rl | systems | theory | biomedical | other`). Empty/`other` → universal minimum applies.
   - Defended: this is the same "engineer mental model ≠ user mental model" pattern the workspace card cleanup chased — operational copy, recruiter-priority hierarchy, hide diagnostics.
   - Exemplar-derived floor suggestion (Cloris looks up the recruiter's named exemplars in OpenAlex, takes 30th-percentile h-index, suggests as the floor) is an obvious upgrade path but ships as a deferred v1.5 enhancement — see "Future enhancements" below. Discipline defaults close 80% of the gap; exemplar-derived is the polish layer.

## Sliced build plan (8 PRs, dependency-ordered)

### Slice 1 — Schema + launcher entry (foundation; compiles, runs nothing)
- Populate `SOURCE_CONFIG_RECOGNIZED_KEYS_BY_SOURCE["researcher"]` at [`shared/brief_v2_schema.py:185`](../shared/brief_v2_schema.py) with `{"research_topics", "conference_allowlist", "discipline", "h_index_floor", "papers_in_window_floor", "papers_in_window_months"}`. Currently empty frozenset. The floor fields are optional power-user overrides; `discipline` is the load-bearing field per Opinion 7. Recognized discipline values documented in spec: `ml_general | nlp | vision | rl | systems | theory | biomedical | other`.
- Add `researcher_state_key` + `resolve_researcher_state_dir` helpers in [`shared/output_paths.py`](../shared/output_paths.py) mirroring `linkedin_state_key` (line 199) and `resolve_linkedin_state_dir` (line 275).
- Add `_researcher_state_key`, `_researcher_state_dir`, `_researcher_orchestrator_argv`, and `_researcher_save_destination_blocker` (returns `None` — workspace is always available) in [`cloris/launchers/__init__.py`](../cloris/launchers/__init__.py); append `"researcher"` entry to `LAUNCHERS` dict at line 223.
- Add `RESEARCHER_AUTHOR_QUERY_KIND = "researcher_author_query"` constant in [`shared/runtime_state/store.py`](../shared/runtime_state/store.py) mirroring `LINKEDIN_STRING_KIND` at line 39.
- Append `"researcher"` to `_SOURCES` tuple at [`cloris/control_plane.py:193`](../cloris/control_plane.py); add researcher entry to `SOURCES` registry at [`cloris/frontend/src/lib/sources.ts:37-40`](../cloris/frontend/src/lib/sources.ts) (must mirror `_SOURCES` per the file's own contract); add `elif source == "researcher":` to the in-process dispatch at [`cloris/worker.py:295-302`](../cloris/worker.py) (frozen-app `Cloris.app` requires explicit elif — registry import-by-name doesn't survive PyInstaller freezing).
- Stub `researcher/__init__.py` and `researcher/session_orchestrator.py` (`main()` exits 0 — Slice 6 wires it).
- Widen `Source` TS literal at [`cloris/frontend/src/lib/types.ts:8`](../cloris/frontend/src/lib/types.ts) and `CandidateCardSummary.source` Pydantic literal at [`cloris/models.py:586`](../cloris/models.py) to include `"researcher"`.
- Tests: launcher registry membership; brief V2 schema validates `target_modules=["researcher"]` brief with `source_config.researcher.research_topics=[...]`; workspace API doesn't crash on a researcher candidate row.
- Rollback: revert launcher entry + source-literal widening; researcher target_modules briefs become un-launchable (422). Database rows already written stay readable.

### Slice 2 — OpenAlex + Semantic Scholar + arXiv source clients (read-only HTTP)
- New `researcher/sources/openalex.py` — author search by `topic_concept` + `venue` + `min_year` + `min_citations` + `ror_country`; pagination via `cursor`; polite-pool email parameter.
- New `researcher/sources/semantic_scholar.py` — paper similarity (SPECTER2) + h-index cross-validation. Free API key.
- New `researcher/sources/arxiv.py` — preprint feed by `cs.LG` / `cs.CL` / `cs.AI` category + author. Atom-based; 1 req / 3 sec.
- Each is a thin REST client routed through [`shared/rate_limiter.py`](../shared/rate_limiter.py).
- No orchestration; just HTTP wrappers that return parsed dicts.
- Tests: recorded-cassette tests per source; rate-limit honoring asserted.
- Rollback: delete `researcher/sources/`. No callers yet.
- Defer: OpenReview (v2 — peer-review evidence is interesting but adds rate-limit complexity); Google Scholar (never — scrape-fragile, ToS exposure); dblp (v2 — useful for CS author disambiguation but OpenAlex covers ML conferences well enough for v1); PubMed (Healthcare extension).

### Slice 3 — Brief → query generator (`researcher/strategy.py`)
- `researcher/strategy.py:form_strategy(brief, prior_data) -> ExecutionPlan` mirroring [`linkedin/strategy.py:form_strategy`](../linkedin/strategy.py) at line 660-700. Opus call producing `ExecutionPlan` with researcher-specific query objects.
- Researcher query schema: `{topic_concepts: [...], venue_filter: [...], min_year: int, min_citations: int, ror_country_filter: [...]}`. One `ExecutionPlan` = N queries; each becomes one work_unit `kind="researcher_author_query"`.
- Brief blocks consumed: `capability_areas` (topic mapping), `source_config.researcher.research_topics` (additive prompt context), `source_config.researcher.conference_allowlist` (venue filter seed), `source_config.researcher.h_index_floor` + `papers_in_window_floor` (deterministic gates passed through to acquisition).
- Tests: prompt rendering for ML researcher fixture brief; query JSON validates against an OpenAlex query schema.
- Rollback: delete `researcher/strategy.py`. No callers yet.

### Slice 4 — Acquisition + identity disambiguation (`researcher/acquisition.py`, `researcher/identity.py`)
- `researcher/acquisition.py` — execute one query against OpenAlex, paginate, dedup by `author_id`, hand off to disambiguation.
- `researcher/identity.py` — disambiguation pass: filter by `ror_country` (geography), filter by `topic_concept` (capability-area overlap), filter by `papers_in_window_floor`. ORCID-anchored when available (`identity_key=f"orcid:{orcid}"`); otherwise `identity_key=f"openalex:{author_id}"`. Common-name collisions (≥2 candidates remain post-filter) flagged for `INFERENTIAL_SAVE` with manual-review note.
- New `researcher/schemas.py` — `ResearcherCandidate` dataclass: `author_id, orcid, name, affiliations, top_papers, h_index, citation_count, papers_in_window`. Plus `ResearcherSnippet` for facial input (name + current affiliation + top 5 papers + h-index + arXiv categories — analogous to LinkedIn's `CandidateSnippet` at `shared/schemas.py`).
- Tests: dedup; disambiguation pass on common-name fixtures (e.g., "Wei Wang" with multiple OpenAlex IDs); identity_key generation deterministic across runs.
- Rollback: orchestrator never instantiates the acquirer; acquisition surface unused.

### Slice 5 — Evaluation pipeline (`researcher/judgment_templates.py`, `shared/judger.py` extension)
- `researcher/judgment_templates.py` — facial + full templates mirroring [`linkedin/judgment_templates.py:assemble_facial_system`](../linkedin/judgment_templates.py) at line 452 + `assemble_full_evaluation_system` at line 478.
- Brief blocks consumed by the evaluator: `capability_areas` (capability mapping), `depth_distinction` (builder vs user — translates to "publishes original research" vs "applies research to product"), `non_fit_patterns`, `source_config.researcher.research_topics`, `source_config.researcher.conference_allowlist` (venue prestige in path/match_type).
- Pre-LLM deterministic gates: read floors via `researcher.discipline_defaults.resolve_floors(source_config.researcher)` — returns `{h_index_floor, papers_in_window_floor, papers_in_window_months}` resolved per Opinion 7 (explicit override → discipline default → universal minimum). Then: `h_index < resolved.h_index_floor` → fast-exit `FACIAL_NO`; `papers_in_window < resolved.papers_in_window_floor` → fast-exit `FACIAL_NO`. The resolver is the SINGLE place that knows the layered priority — gate sites just call it.
- `shared/judger.py` extension: `researcher_facial_judge_batch(snippets, brief)`, `researcher_full_judge(candidate, brief)` — both produce `OpusDecision` ([`shared/schemas.py:340-354`](../shared/schemas.py)) with `stage`, `decision`, `path`, `confidence`, `rationale`, `candidate_name`, `profile_url` (=ORCID URL or OpenAlex author URL), `post_save_modifier`, `novelty_value`, `value_rationale`. Decision enum: `SAVE | INFERENTIAL_SAVE | TRANSFERABLE_SAVE | REJECT | FACIAL_YES | FACIAL_NO | FACIAL_BORDERLINE`.
- Fast-exit `FACIAL_NO` rationale must be recruiter-readable: "Skipped — only 1 paper in last 36 months, below the field-default minimum of 3" (NOT "papers_in_window=1 < papers_in_window_floor=3"). Engineer vocab in the rationale leaks into the workspace card per `extract_save_reason_and_confidence` contract.
- Tests: facial prompt renders without engineer-vocab leak; full prompt produces OpusDecision-shaped output; `terminal_payload_json` round-trip via `extract_save_reason_and_confidence` returns the rationale + confidence written; resolver returns universal minimum when discipline absent; resolver returns discipline default when discipline picked; resolver returns explicit override when present.
- Rollback: orchestrator never calls evaluators; evaluation surface unused.

### Slice 6 — Orchestrator + runtime state bridge
- `researcher/orchestrator.py` — `ResearcherPipeline.run(brief, output_dir, resume)`; loops over `Progress.queries`, dispatches to acquirer + evaluator, tracks per-query stats. Mirrors [`linkedin/orchestrator.py`](../linkedin/orchestrator.py)'s `_process_string` shape but for OpenAlex queries.
- `researcher/session_orchestrator.py` — CLI entry point; accepts `--brief`, `--state-dir`, `--resume`. Argv shape matches `_researcher_orchestrator_argv` from Slice 1.
- `shared/runtime_state/researcher.py` — runtime bridge mirroring [`shared/runtime_state/linkedin.py`](../shared/runtime_state/linkedin.py) at line 188+: `record_candidate_discovery`, `start_stage_attempt`, `finish_stage_success`, `begin_candidate_side_effect` (no-op for v1; saves stay in `candidates` table). `identity_key` resolution per Slice 4.
- Resume semantics: re-read `work_units WHERE status IN ('queued', 'in_progress')`; pagination cursor in `checkpoint_json` (mirrors LinkedIn's pages_reviewed pattern at [`shared/runtime_state/linkedin_progress_sync.py:62-67`](../shared/runtime_state/linkedin_progress_sync.py) inside the `upsert_work_unit` checkpoint dict).
- Tests: end-to-end pipeline run against mocked OpenAlex; runtime state transitions; resume after interruption (kill mid-query, restart, no duplicate work).
- Rollback: revert Slice 6; Slice 1's stub orchestrator remains in place; runs do nothing.

### Slice 7 — Brief polish backend extension + discipline defaults (intake-time preservation + layered floors)
- New `researcher/discipline_defaults.py` — small lookup table per Opinion 7. Public surface: `UNIVERSAL_MINIMUM = {h_index_floor: 3, papers_in_window_floor: 1, papers_in_window_months: 36}`; `DISCIPLINE_DEFAULTS: dict[str, dict[str, int]]` covering the eight recognized disciplines (initial values: `nlp` → h≥10/p≥3/24mo, `ml_general` → h≥8/p≥3/24mo, `vision` → h≥9/p≥3/24mo, `rl` → h≥7/p≥3/24mo, `systems` → h≥6/p≥2/36mo, `theory` → h≥5/p≥2/48mo, `biomedical` → h≥12/p≥4/24mo, `other` → universal); `resolve_floors(source_config_researcher: dict) -> dict` implementing the layered priority. Spec calls these "first-pass values to be calibrated post-trial."
- Extend [`market_intelligence/brief_polish.py`](../market_intelligence/brief_polish.py) cascade with **`_research_topics_drift` route** (function-named, NOT number-claimed — parallel module threads append `_target_projects_drift`, `_design_rubric_drift`, `_confidentiality_class_drift` at the next position; standard git rebase resolves order). If input had `source_config.researcher.{research_topics, conference_allowlist, discipline}` or any explicit floor override, output MUST preserve them character-for-character. Mirrors `_path3_drift` for LinkedIn project_id at [`market_intelligence/brief_polish.py:605`](../market_intelligence/brief_polish.py). Discipline + explicit floors are recruiter-authoritative — the LLM is not allowed to "improve" them. Append the route call after `_role_title_drift` (line 503-513) and the helper after `_role_title_drift` helper (line 627-640). Extend `_scannable_text_fields` at line 550-581 to exclude `source_config.researcher` (mirroring its existing exclusion of `source_config` and `role_title`).
- Extend `BriefPolishBackend.polish` system prompt at [`market_intelligence/brief_polish.py:719`](../market_intelligence/brief_polish.py) to document the new preservation rule alongside the existing role_title + source_config.linkedin contracts.
- Extend `HeuristicBriefPolishBackend.polish` at [`market_intelligence/brief_polish.py:181`](../market_intelligence/brief_polish.py) to seed `source_config.researcher.{research_topics, conference_allowlist, discipline}` from chapter captures (parallel to Path 3 LinkedIn promotion at line 233-242). Heuristic does NOT seed explicit floors — those resolve at evaluation time via `discipline_defaults.resolve_floors`.
- Intake wizard: add to [`cloris/frontend/src/components/OnboardingFlow.svelte`](../cloris/frontend/src/components/OnboardingFlow.svelte)'s where_to_look chapter (line 804+):
  - `where_to_look.research_topics` — free-text textarea ("What research areas matter?")
  - `where_to_look.conference_allowlist` — multi-select chip input pre-populated with `["NeurIPS", "ICML", "ICLR", "ACL", "EMNLP", "CVPR", "COLM", "TMLR"]`; recruiter adds/removes
  - `where_to_look.discipline` — single-select dropdown (the eight values from `discipline_defaults`); placeholder "What field?" with a "Cloris will pick a sensible bar based on field defaults — you can tighten later" hint below
  - The wizard does NOT surface raw `h_index_floor` / `papers_in_window_floor` text inputs in v1. Power-user override is via direct brief JSON edit only — surfacing the inputs on the brief-detail page is a v1.5 polish.
- After the wizard's review step, the Reference Slip surfaces the resolved floors in editorial language (e.g., "I'll skip authors with fewer than 3 first-author papers in the last 24 months — based on NLP defaults"). This is what the recruiter sees, NOT raw numbers in form fields.
- Tests: brief polish preserves `discipline` + `research_topics` + explicit floors across LLM call; heuristic seeds `source_config.researcher` when chapter captures present; `_research_topics_drift` cascade route fires when LLM drops any preserved field; `discipline_defaults.resolve_floors` returns correct layered priority; wizard discipline picker renders all eight values.
- Rollback: revert `_research_topics_drift` route + discipline picker UI; brief polish forgets researcher source_config fields. `discipline_defaults` module stays (it's read by Slice 5's gate logic). Heuristic falls back to passing them through unmodified — degraded but acceptable.

### Slice 8 — End-to-end smoke against a real brief
- Author a researcher brief at `config/<role>/brief.json` for a frontier-lab role (Head of Applied AI Lab is the live role per the workspace; `config/head_of_applied_ai_lab/brief.json` is the reference). target_modules=["researcher"], capability_areas grounded in post-training / inference / agent infra, source_config.researcher.research_topics + conference_allowlist + h_index_floor + papers_in_window_floor populated.
- Run `python -m researcher.session_orchestrator --brief <path> --state-dir <path>` against the live brief.
- Verify: ≥10 SAVE-class candidates land in `runtime_state.sqlite3:candidates` with `terminal_payload_json` carrying `full_decision.rationale` + `full_decision.confidence`.
- Verify: workspace surface (`/api/workspace/<brief_id>`) returns researcher cards with `display_name` + `save_reason` + `confidence` populated.
- Verify: workspace card UI renders cleanly without LinkedIn-specific assumptions.
- Document any rough edges in spec's "Known v1 sharp edges" section (do NOT silently paper over).
- Tests: smoke fixture exercising full flow against a recorded OpenAlex response.
- Rollback: nothing; this slice is observation-only of the prior 7.

## Failure modes

1. **Rate-limit exhaustion** — OpenAlex polite pool is 100K calls/day, 10 req/s. A typical brief generates ~50-200 queries × 50 candidates each = 5-10K calls. Comfortable headroom. Risk: aggressive expansion or many concurrent briefs. Mitigation: shared `shared/rate_limiter.py` per source; module-level governor with daily budget; `governor_limit_reached` stop reason on exhaustion.
2. **Ambiguous identity** — Common names ("Wei Wang", "John Smith"). Disambiguation pass uses geography + topic concepts + papers-in-window. If ≥2 candidates remain post-filter, flag as `INFERENTIAL_SAVE` with manual-review note in rationale. Honest about uncertainty.
3. **Brief-author mismatch (recruiter exemplars aren't research-active)** — Recruiter listed a famous research scientist who's been at a startup 3 years and not publishing. Brief polish + intake wizard can't catch this; planner adaptation would (Phase 3). v1 mitigation: facial triage surfaces "no recent publications" as `FACIAL_NO` with rationale; recruiter sees rejection and updates the brief. Acceptable.
4. **Low-volume failure (sub-field with five qualified people on Earth)** — Strategy formation produces N queries; each returns 0 results; pipeline stops with `governor_stop_reason="empty_search_results"`. Recruiter sees "I scanned X queries, found Y candidates; consider broadening." This is a feature, not a bug — surface honestly via the workspace.
5. **OpenAlex affiliation lag** — Affiliation strings lag real-life by 6-24 months. v1 surfaces last-known affiliation; cross-source resolution to LinkedIn (Phase 3) would update with current employer. Acceptable for v1; document in spec.
6. **Multiple OpenAlex author IDs for same person** — S2AND disambiguation imperfection. Detected when two candidates share ORCID or publication set ≥80% overlap; merge at ingest. Workspace shows merged person with both IDs noted.
7. **"What number do I type for h-index?"** — Recruiter doesn't know the field's conventions. Layered resolution per Opinion 7 closes the gap: universal minimum applies always; discipline picker (single dropdown) overrides with field-appropriate values; explicit override is power-user-only and not surfaced in the wizard. The recruiter never sees a raw number input unless they go looking for one.
8. **Discipline default values are wrong for a sub-field** — e.g., `nlp` default of h≥10 might be too aggressive for a niche NLP sub-area or too lenient for mainline LLM research. Mitigation: telemetry on facial-no rate per discipline post-trial; spec calls discipline values "first-pass, calibrate post-trial"; values are a one-line edit in `researcher/discipline_defaults.py` once we have signal. Don't over-engineer the resolution layer before we have data.

## Future enhancements (deferred from v1)

- **Exemplar-derived floor suggestion.** At intake, after the recruiter authors the lookalikes chapter (`lookalikes.exemplars_prose`), Cloris extracts named entities, looks them up in OpenAlex synchronously during the brief polish step, and computes the 30th-percentile h-index across the matched authors. Wizard shows "Based on your exemplars (Smith, Jones, Wang), I'd suggest h-index ≥ 8 — does that feel right?" with accept/edit affordances. Better UX than discipline defaults when exemplars are present. Deferred because: (a) requires synchronous OpenAlex call from the wizard backend (new code path; today the wizard is LLM-only), (b) entity extraction from free-text exemplars adds an LLM call, (c) discipline defaults close 80% of the gap and we should ship them first to learn whether the floor mechanism is even the right shape. Revisit after first-customer trial.
- **Surfacing power-user floor overrides on brief-detail page.** v1 only exposes overrides via direct brief JSON edit. Once trial signal indicates recruiters want more control, surface the resolved floor in the brief-detail page with an "override" affordance (slider + text input). Not in v1 to keep the wizard surface tight.
- **Per-capability-area floors.** A multi-capability brief (e.g., "post-training researchers AND inference systems researchers") may want different floors per capability. v1 uses a single brief-level floor; v2 could move floors onto `CapabilityArea`. Defer until trial shows the gap.

## Out of scope (explicit)

- Multi-source weighted scoring (LinkedIn + Researcher signals merged) — Phase 3.
- Confidential search — adds OAuth/API-key handling per source; defer.
- Researcher save destinations beyond Cloris workspace — no LinkedIn Recruiter for researchers without LinkedIn URL; punted.
- Reflection polish — needs researcher planner; Phase 3.
- Cross-source identity resolution to LinkedIn — Phase 3 (the shared identity layer is ready at the schema level; the matching logic in `shared/identity_resolution_service.py:_extract_signals` needs a third branch when this lands).
- OpenReview, dblp, Google Scholar — defer to v2 / never (Google Scholar).
- Healthcare extension (PubMed) — separate plan after v1 ships.

## Cross-thread coordination

- **Brief polish backend extends, doesn't fork.** Slice 7 adds `_research_topics_drift` cascade route alongside `_path3_drift` (LinkedIn project_id) and `_role_title_drift` — all preservation contracts share the same cascade structure at [`market_intelligence/brief_polish.py:441-513`](../market_intelligence/brief_polish.py). Function-named, not number-claimed.
- **Intake wizard configuration.** Researcher's `research_topics` + `conference_allowlist` are captured in the wizard's where_to_look chapter alongside `target_modules` and `linkedin_project_id`. Same in-product discipline as Path 3 — no JSON file editing.
- **Runtime state schema is unchanged.** No new columns on `candidates`; `terminal_payload_json` carries researcher-specific shape (paper titles, citation counts, ORCID, h-index) inside the same blob. Read models stay source-agnostic.
- **Shared collision files** with parallel module threads (Designer, OSS Maintainers, Executive Search): `cloris/launchers/__init__.py` LAUNCHERS dict, `cloris/control_plane.py:193` `_SOURCES`, `cloris/frontend/src/lib/sources.ts` SOURCES, `cloris/frontend/src/lib/types.ts:8` `Source`, `cloris/models.py:586` `CandidateCardSummary.source`, `cloris/worker.py:295` dispatch, `shared/runtime_state/store.py:37-39` work-unit kinds, `shared/brief_v2_schema.py:185-188` `SOURCE_CONFIG_RECOGNIZED_KEYS_BY_SOURCE`, `market_intelligence/brief_polish.py` cascade. Discipline: append; never reorder. Standard git rebase on file conflicts.
