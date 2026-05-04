# researcher-module-build

> **SUPERSEDED BY** [`plans/researcher-module-spec.md`](researcher-module-spec.md) (2026-05-03). The successor's slice plan engages with the architecture that actually shipped (launcher registry, V2 brief schema, `candidates`-table workspace). This document is preserved for product-strategy context.

Status: superseded
Owner: Sam
Last updated: 2026-04-29

## Problem

Cloris has no module for discovering and evaluating ML researchers. Frontier AI labs and AI-focused executive search firms cannot use Cloris for their primary hiring constraint: surfacing first-author authors at canonical ML venues with structured evaluation against a calibrated brief. Researcher candidates are systematically underrepresented in LinkedIn-only sourcing because the strongest signal — publication record — is not on LinkedIn.

## Goal

After this plan ships, a recruiter authors a researcher brief, runs the Researcher module against OpenAlex / Semantic Scholar / dblp / arXiv, and receives evaluated researcher candidates in the candidate workspace with reconciliation to LinkedIn for actionable outreach.

## Non-goals

- Healthcare extension (PubMed adapter + biomedical brief calibration). That ships in `plans/healthcare-extension-build.md` after this plan completes.
- Cross-module identity resolution beyond researcher↔LinkedIn. The cross-module identity layer's other adapters ship in their respective phases.
- Graph expansion from confirmed saves. V2 of the module if customer signal indicates value.
- OpenReview integration (ICLR submission / reviewer history). V2.
- Standalone Researcher pricing SKU. The module is part of Cloris's platform offering, not a separate product.

## Assumptions

- `plans/multi-module-foundation.md` is complete. Specifically: `target_modules` field, `linkedin_project` default-empty, per-source nested calibration, `cloris/worker.py` parameterization, candidate workspace v1, save destination abstraction, calibration vertical-agnostic refactor.
- OpenAlex API access is stable at 100K calls/day and 10 req/s (CC0 license, free, polite-pool by email). If usage exceeds the polite pool, register for higher quotas via OpenAlex.
- Semantic Scholar free API key is available; ~1 req/s sustained is sufficient for v1.
- arXiv affiliate registration is completed before customer launch.
- Brief authoring tooling does not require module-specific extensions for this plan; existing brief-loader and `shared/brief_iteration.py` cover authoring.

## Seam

New module directory `researcher/` paralleling `linkedin/` and `github/`. Plus surface-level extensions in shared and cloris namespaces.

- `researcher/` — new directory, all required files per `docs/cloris-module-integration-contract.md` §1.
- `researcher/sources/` — sub-directory with one client per source.
- `shared/judger.py` — add `researcher_facial_judge`, `researcher_full_judge`, batch variants.
- `shared/runtime_state/researcher.py` — new bridge.
- `shared/runtime_state/store.py:37-39` — add `RESEARCHER_AUTHOR_QUERY_KIND`.
- `shared/output_paths.py` — add `resolve_researcher_state_dir`, `researcher_state_key`.
- `shared/brief_schema.py` — add `ResearcherCalibration` dataclass; add capability-area extensions (`arxiv_category_signals`, `publication_venue_signals`).
- `shared/brief_loader.py` — hydrate `ResearcherCalibration` from V2 brief JSON.
- `shared/cross_module_identity/researcher_to_linkedin.py` — adapter for researcher↔LinkedIn (uses ORCID, name + affiliation, name + education).
- `cloris/control_plane.py:175` — add `"researcher"` to `_SOURCES`.
- `cloris/control_plane.py:_progress_kind_for_source` — return `RESEARCHER_AUTHOR_QUERY_KIND` for researcher.
- `cloris/models.py:LaunchResponse.source` and `StateDirEntry.source` — widen to include `"researcher"`.
- `cloris/worker.py:_DISPATCH_TABLE` — register `"researcher": "researcher.session_orchestrator"`.

## Proposed change

The plan ships in 8 slices. Slices 1-3 build the data acquisition foundation; Slices 4-5 build the evaluation pipeline; Slices 6-7 integrate with Cloris control plane and reconciliation; Slice 8 is end-to-end customer-launch readiness.

Pattern-mirror approach: the Researcher module follows `github/` directory shape exactly. Each `<file>.py` mirrors `github/<file>.py`'s pattern adapted to publication-record evidence. This minimizes architectural divergence and makes the integration contract verifiable.

## Risks

- **OpenAlex affiliation strings are unnormalized.** Affiliation parsing requires care; strategy formation queries are filtered by ROR institution IDs (clean) but candidate evaluation uses affiliation history (text). Mitigation: normalize affiliations via OpenAlex's parsed affiliation objects when present; treat unnormalized strings as enrichment-only.
- **arXiv affiliate registration lag.** arXiv requires affiliate registration before a commercial product launches against their API. Mitigation: register early (Slice 1); module functional without arXiv (OpenAlex covers arXiv content via DOI cross-references) so a registration delay does not block the build, only the customer-launch.
- **Common-name disambiguation.** "Wei Wang" / "John Smith" identification is hard. The disambiguation pass surfaces ambiguous candidates as `INFERENTIAL_SAVE`; if the rate is high, recruiters experience friction. Mitigation: telemetry on the rate; iteratively refine the disambiguation heuristics based on customer feedback.
- **Researcher-to-LinkedIn reconciliation false positives.** ORCID matches are high-confidence, but `name_plus_affiliation_match` at 0.7-0.9 confidence still produces occasional false positives. Mitigation: surface confidence and resolution method to the recruiter in the workspace; recruiter confirms ambiguous matches.
- **Publication-record evidence prompt fits in context window.** Senior researchers may have 100+ papers. Strategy: full evaluation receives top-N papers (configurable in brief; default 30) plus complete affiliation history. If papers exceed N, the system summarizes the long-tail count.

## Slices

- [ ] **Slice 1** — `researcher/sources/openalex.py`, `researcher/sources/semantic_scholar.py`, `researcher/sources/dblp.py`, `researcher/sources/arxiv.py`. Each is a thin REST client with rate-limited polite-pool semantics. Tests: `tests/test_researcher_sources.py` covers each client against recorded responses.

- [ ] **Slice 2** — `researcher/client.py` (facade over the four source clients). `researcher/schemas.py` (`ResearcherCandidate` dataclass + `to_evidence_text()`, `to_snippet_text()` mirroring `github/schemas.py`'s pattern). Tests: facade dispatching; schema rendering.

- [ ] **Slice 3** — `researcher/acquisition.py` (discovery from OpenAlex by capability area + venue + h-index floor). `researcher/enricher.py` (light-enrich = author summary + top 5 papers; full-enrich = complete publication record + affiliation history + co-author network). Disambiguation pass (filter by geography, capability area, papers-in-window, then Perplexity-augmented for residual ambiguity). Tests: dedup; disambiguation pass on common-name fixtures.

- [ ] **Slice 4** — `researcher/strategy.py` (`form_researcher_strategy` and `adapt_after_batch` mirroring `github/strategy.py:form_github_strategy`). Opus-driven OpenAlex query generation from brief calibration. Tests: strategy formation produces valid OpenAlex queries; adaptation refines queries based on per-batch results.

- [ ] **Slice 5** — `researcher/judgment_templates.py` (`assemble_researcher_facial_system`, `assemble_researcher_full_evaluation_system`, parsers). `shared/judger.py` extension (`researcher_facial_judge`, `researcher_full_judge`, `researcher_facial_judge_batch`). Brief schema additions (`ResearcherCalibration` dataclass, capability-area extensions, facial calibration source patterns). Tests: prompt rendering for ML researcher fixture brief; parser returns valid `OpusDecision` for SAVE/REJECT/INFERENTIAL_SAVE/PARSE_FAILURE cases.

- [ ] **Slice 6** — `researcher/work_units.py` (`ResearcherWorkUnitService` mirroring `github/work_units.py:GitHubWorkUnitService`). `researcher/side_effects.py` (handle SAVE-family decisions; dispatch via `AbstractSaveDestination`). `researcher/governor.py` (rate limits per source, session-duration caps). `researcher/orchestrator.py` (`ResearcherPipeline` mirroring `github/orchestrator.py:GitHubPipeline`). `researcher/session_orchestrator.py`. `shared/runtime_state/researcher.py` (`ResearcherRuntimeStateBridge`). Tests: end-to-end pipeline run against mocked clients; runtime state transitions; resume after interruption.

- [ ] **Slice 7** — `researcher/recruiter_identity_resolver.py` (researcher → LinkedIn bridge). `shared/cross_module_identity/researcher_to_linkedin.py` (adapter with ORCID-match, name-plus-affiliation, name-plus-education, name-plus-publication-evidence resolution methods). Cloris control plane registration (Slices 4-5 of multi-module-foundation; refresh here). Tests: identity resolver against LinkedIn-recruiter mocks; cross-module adapter confidence-band assertions.

- [ ] **Slice 8** — Customer launch readiness: arXiv affiliate registration, polite-pool email registered with OpenAlex, customer-onboarding brief authoring guide updates, demo brief authored and dry-runned end-to-end, telemetry dashboard for facial pass rate / full eval pass rate / reconciliation success rate / save-to-confirmation rate. Tests: smoke run against demo brief produces ≥10 saves with reconciled LinkedIn URLs.

## Test strategy

- Narrowest relevant test band to run first:
  - Slice-by-slice: `pytest tests/test_researcher_<area>.py -q`
  - Cross-cutting: `pytest tests/test_researcher_pipeline.py -q` after Slice 6.
- Tests to add:
  - `tests/test_researcher_sources.py` — per-source REST client coverage.
  - `tests/test_researcher_pipeline.py` — end-to-end pipeline characterization.
  - `tests/test_researcher_runtime_state.py` — state-machine transitions, dedup, resume.
  - `tests/test_researcher_judgment_templates.py` — prompt rendering and parser behavior.
  - `tests/test_researcher_to_linkedin_resolution.py` — cross-module identity adapter.
  - Extend `tests/test_phase0_contracts.py` — `ResearcherCalibration` hydration from V2 brief JSON.
  - Extend `tests/test_cloris_status_aggregation.py` — `"researcher"` source in aggregation.
- Full-suite gate before declaring done: `make validate`.

## Open questions

- Whether Slice 1's OpenAlex polite-pool email registration should happen before or during the build. Decision: register during Slice 1 so the team email is established and OpenAlex can route us to higher quotas if usage demands.
- Whether to ship arXiv as part of v1 or defer to v1.1. Decision: include in v1 because preprint discovery is a meaningful signal source for late-stage PhD students and pre-LinkedIn researchers; the affiliate registration is the only blocker.
- Confidence threshold for auto-applying researcher↔LinkedIn resolution. Currently `≥ 0.85` per `docs/cloris-cross-module-identity-resolution-spec.md`. Decision: stick with 0.85 for v1; revisit after first-customer telemetry.

## Decisions

- 2026-04-29 — Module ships in 8 slices.
- 2026-04-29 — Pattern-mirror `github/` directory shape exactly to minimize architectural divergence.
- 2026-04-29 — V1 includes OpenAlex + Semantic Scholar + dblp + arXiv. PubMed (Healthcare) is a separate plan.
- 2026-04-29 — Disambiguation pass runs before `record_candidate_discovery()`; not a new lifecycle state.
- 2026-04-29 — Researcher-to-LinkedIn reconciliation runs as a post-stage after the run completes; real-time during discovery is a v2 enhancement if necessary.
- 2026-04-29 — Build target is 4 calendar weeks at dedicated focus pace; ~7-8 weeks at split-attention pace.

## Follow-ups (not in this plan)

- Healthcare extension (PubMed + biomedical calibration) — `plans/healthcare-extension-build.md`, ships ~1-2 weeks after this plan completes.
- Defense module variants (SBIR + Patents + IEEE) — `plans/defense-module-build.md`, ships in Phase 3 alongside Healthcare.
- Graph expansion from confirmed saves (`RESEARCHER_VENUE_GRAPH_SEED_KIND`) — V2 enhancement.
- OpenReview integration — V2 enhancement.
- Brief authoring polish for researcher-specific calibration vocabulary — Authoring Loop UX work, parallel workstream.
