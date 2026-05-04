# designer-module-build

Status: ready-to-implement
Owner: Sam
Last updated: 2026-04-30

## Problem

Cloris has no module for discovering and evaluating visual designers. Design recruiting consultancies, in-house design teams, and design-forward operations cannot use Cloris for one of their primary hiring constraints: surfacing portfolio-strong designers with structured visual evaluation against a calibrated brief. The category is structurally underserved — horizontal sourcing tools cannot take taste positions on creative work, specialized design platforms are taste-curated by humans without VLM tooling, and no recruiting tool in 2026 runs vision-language model evaluation of portfolios. Cloris's depth-per-population architecture and brief authoring methodology are uniquely suited to fill this gap.

## Goal

After this plan ships, a recruiter authors a designer brief (with discipline-tagged rubric calibration), runs the Designer module against Behance / LinkedIn / Google CSE-discovered personal portfolio sites, and receives evaluated designer candidates in the candidate workspace. Each candidate appears as a `surface_type: "hitl_visual_review"` card with text-based contextualization (specialization, tool depth, notable projects, client tier) plus rubric-decomposed vision-evaluation output (per-principle scoring + reasoning from Gemini 2.5 Pro). The recruiter reviews the portfolio URL alongside the structured guidance and confirms / rejects / borderline-flags each candidate.

## Non-goals

- Cross-module identity resolution beyond designer↔LinkedIn. The cross-module identity layer's other adapters ship in their respective phases.
- Production-grade portfolio crawler that fetches and parses arbitrary personal sites. Google CSE thumbnail metadata + Behance project image arrays are sufficient for v1.
- Are.na enrichment for niche/conceptual designers. Phase 5 ship-quality polish work.
- Awwwards / SiteInspire credit-graph integration. Phase 5 ship-quality polish work.
- Live Google CSE strategy adaptation based on which CSE domains produce signal. Phase 5 ship-quality polish work.
- Entertainment-industry-specific rubric variants (production design, key-art-specific brand, title-sequence motion). Defer until first entertainment-industry customer.
- Outreach automation. Out of scope per Cloris product north star.
- Standalone Designer pricing SKU. The module is part of Cloris's platform offering.
- Fine-tuned vision model. The brief-encoded rubric carries per-customer taste; off-the-shelf Gemini 2.5 Pro applies it. Fine-tuning is rejected per `Cloris-Module-Strategy.md` §2.5 and `docs/designer-hitl-module-spec.md` §17.

## Assumptions

- `plans/multi-module-foundation.md` is complete. Specifically: `target_modules` field, `linkedin_project` default-empty, per-source nested calibration, `cloris/worker.py` parameterization, candidate workspace v1, save destination abstraction, calibration vertical-agnostic refactor.
- Behance API access remains stable at ~150 req/hr free tier and the `/v2/projects/{id}` endpoint continues to return module image URLs at the resolutions used. Adobe has progressively restricted Behance APIs; verify before kickoff. If access is restricted, Google CSE fallback must cover the gap.
- Google Programmable Search Engine free tier (100 queries/day per CSE) is sufficient for the demo; paid expansion to ~10K/day is the customer-launch threshold.
- Gemini 2.5 Pro API access via Google AI Studio or Vertex AI is available, with structured-output support and image-input support at expected token volumes.
- LinkedIn module's existing recruiter-identity-resolver pattern extends cleanly to designer↔LinkedIn matching.
- Brief authoring tooling absorbs the new `BriefDesignRubric` schema additions without major Authoring Loop UX investment in this plan; rubric authoring UX polish is a follow-up.

## Seam

New module directory `designer/` paralleling `linkedin/`, `github/`, and (in-flight) `researcher/`. Surface-level extensions in shared and cloris namespaces.

- `designer/` — new directory, all required files per `docs/cloris-module-integration-contract.md` §1.
- `designer/sources/behance.py` — Behance v2 API client.
- `designer/sources/google_cse.py` — Google CSE adapter filtered to portfolio-host domains (`site:cargo.site`, `site:squarespace.com`, `site:format.com`, `site:semplice.com`, `site:awwwards.com`, `site:siteinspire.com`).
- `designer/image_acquisition.py` — Behance project image URL extraction, Google CSE thumbnail metadata, optional direct fetch from personal sites with ToS check, image selection logic (count + resolution).
- `designer/vision_evaluation.py` — Gemini 2.5 Pro client, rubric-loaded prompt templating, structured output schema, per-principle parser, fallback handling.
- `designer/judgment_templates.py` — facial / full evaluation prompts producing structured contextualization output.
- `designer/strategy.py` — Opus-driven Behance + Google CSE query generation from brief calibration.
- `designer/recruiter_identity_resolver.py` — designer ↔ LinkedIn bridge.
- `designer/orchestrator.py`, `designer/session_orchestrator.py`, `designer/work_units.py`, `designer/side_effects.py`, `designer/governor.py` — pattern-mirror `github/` and `researcher/` shapes.
- `shared/judger.py` — add `designer_facial_judge`, `designer_full_judge`, batch variants.
- `shared/runtime_state/designer.py` — new bridge.
- `shared/runtime_state/store.py` — add `DESIGNER_BEHANCE_QUERY_KIND`, `DESIGNER_CSE_QUERY_KIND`.
- `shared/output_paths.py` — add `resolve_designer_state_dir`, `designer_state_key`.
- `shared/brief_schema.py` — add `DesignerCalibration`, `BriefDesignRubric`, `RubricPrinciple`, `CalibrationExemplar`, capability-area extensions (`behance_specialization_signals`, `tool_stack_signals`).
- `shared/brief_loader.py` — hydrate `DesignerCalibration` and `BriefDesignRubric` from V2 brief JSON.
- `shared/cross_module_identity/designer_to_linkedin.py` — adapter for designer ↔ LinkedIn (uses portfolio URL match, name + company match).
- `cloris/control_plane.py:175` — add `"designer"` to `_SOURCES`.
- `cloris/control_plane.py:_progress_kind_for_source` — return `DESIGNER_BEHANCE_QUERY_KIND` for designer.
- `cloris/models.py:LaunchResponse.source` and `StateDirEntry.source` — widen to include `"designer"`.
- `cloris/worker.py:_DISPATCH_TABLE` — register `"designer": "designer.session_orchestrator"`.
- `config/brief-templates/designer/` — pre-built brief templates (per spec §6).
- `config/design-rubrics/` — default rubric assets (per discipline).

## Proposed change

The plan ships in 9 slices. Slices 1-3 build the data acquisition foundation. Slices 4-5 build the rubric authoring + image acquisition layer (the editorial work + image plumbing the vision-evaluation pass depends on). Slices 6-7 build the vision-evaluation pass + integration with text-based judger. Slice 8 wires Cloris control plane and reconciliation. Slice 9 is end-to-end customer-launch readiness.

Pattern-mirror approach: text-based pipeline follows `github/` directory shape exactly, adapted for portfolio evidence. Vision-evaluation pass is a new component (`designer/vision_evaluation.py` + `designer/image_acquisition.py`) without analog in other modules — the only meaningful architectural divergence.

## Risks

- **Behance API access restricted by Adobe mid-build.** Adobe has progressively restricted public APIs. Mitigation: track Behance access status as part of customer-launch readiness; have Google CSE fallback ready before launch; cache profiles aggressively to reduce dependency on real-time API.
- **Vision-evaluation hallucination on unfamiliar visual domains.** Gemini 2.5 Pro can hallucinate about creative work — claim to see things that aren't there, attribute to influences inaccurately. Mitigation: structured output format constrains response shape; recruiter feedback marker on the workspace surface ("Wrong / shallow / Off-rubric") feeds back into rubric refinement; HITL framing means hallucination doesn't cost the recruiter a hire (recruiter still reviews the portfolio).
- **Rubric authoring quality determines vision-evaluation output quality.** Bad rubric → generic critique. Mitigation: ship sharp default rubric authored by Sam (with designer collaborator review where possible); track recruiter feedback on per-principle output and iterate the defaults; expose rubric editing in the brief authoring UX so customers can refine.
- **Image acquisition partial failure rate.** ~5-15% of candidates expected to return insufficient images for vision-evaluation pass (private profiles, removed projects, Cloudflare-protected personal sites). Mitigation: graceful fallback to text-only contextualization when vision pass fails; telemetry tracks failure rate per source.
- **Vision-evaluation API cost spike under high-volume customer.** Per-customer monthly inference estimated at $10-30 at 200-500 evaluations. A high-volume customer (5,000+ evaluations/month) would spike to $100-300. Mitigation: per-customer monthly inference budget telemetry; default cap; conversation with customer if cap is approached.
- **Designer-to-LinkedIn reconciliation false positives on common names.** Mitigation: portfolio URL match is high-confidence (0.95+); name + company match is medium-confidence (0.65-0.8) and surfaced to the recruiter for confirmation; common-name candidates flagged.
- **Discipline-rubric mismatch for entertainment-industry customers.** Default rubric is product/brand/UX-skewed. Entertainment-industry creative needs different weights. Mitigation: ship motion + illustration rubric variants in v1; flag as ship-quality polish for entertainment-specific sub-disciplines if customer pull emerges.

## Slices

- [ ] **Slice 1** — `designer/sources/behance.py`, `designer/sources/google_cse.py`. Each is a thin REST client with rate-limited polite-pool semantics. Behance: developer key auth, `/v2/users/{id}/projects`, `/v2/projects/{id}`, search endpoints. Google CSE: free tier with paid expansion configured. Tests: `tests/test_designer_sources.py` covers each client against recorded responses.

- [ ] **Slice 2** — `designer/client.py` (facade over the two source clients). `designer/schemas.py` (`DesignerCandidate` dataclass + `to_evidence_text()`, `to_snippet_text()` mirroring `github/schemas.py`'s pattern, plus `to_image_acquisition_input()` returning structured project + image URL data for the vision-evaluation pass). Tests: facade dispatching; schema rendering; image input shape validation.

- [ ] **Slice 3** — `designer/acquisition.py` (discovery from Behance by specialization tags + tool stack + project descriptions; Google CSE for personal site enrichment). `designer/enricher.py` (light-enrich = profile + top 5 projects with image URLs; full-enrich = complete published projects + tool stack + LinkedIn integration when matched). Tests: dedup; enrichment producing both text evidence and image acquisition input.

- [ ] **Slice 4** — Brief schema additions (`DesignerCalibration`, `BriefDesignRubric`, `RubricPrinciple`, `CalibrationExemplar` dataclasses) plus capability-area extensions and `shared/brief_loader.py` hydration. **Default rubric authoring (editorial work, ~3 days):** 6 principles × 4 anchor levels × concrete-language definitions; discipline-specific weight overrides for product / brand / motion / illustration / UX. Stored at `config/design-rubrics/default.json` and per-discipline variants. **Default calibration exemplars (editorial work, ~3 days):** 3-5 per discipline, hand-evaluated by Sam (with designer collaborator review where available), shipped at `config/design-rubrics/exemplars/{discipline}/*.json`. Tests: schema hydration; rubric rendering for prompt templating; exemplar loading per discipline.

- [ ] **Slice 5** — `designer/image_acquisition.py`. Behance project image URL extraction (parse `modules` array from `/v2/projects/{id}` response). Google CSE thumbnail extraction (parse `pagemap.cse_thumbnail` metadata). Optional direct-fetch from Cargo / Squarespace / Format / Semplice with ToS check (skip personal sites without permissive ToS). Image selection: up to 8 images per candidate; priority is recent project hero images > top-appreciation hero images > tagged showcase work. Resolution selection: medium resolution to balance quality and token cost. Tests: image URL extraction across source types; selection logic; failure-mode handling (private profiles, removed projects).

- [ ] **Slice 6** — `designer/vision_evaluation.py`. Gemini 2.5 Pro client (Google AI Studio or Vertex AI). Rubric-loaded prompt templating (rubric principles + anchors + discipline weights + calibration exemplars + 8 candidate images + structured-output schema). Structured output parser (per-principle 0-3 score + reasoning + overall verdict + confidence). Fallback handling (rate limit, parser failure, image acquisition failure). Cost telemetry. Tests: prompt rendering; parser against fixture responses; fallback paths.

- [ ] **Slice 7** — `designer/judgment_templates.py` (text-based facial + full evaluation prompts producing structured contextualization output) + `designer/strategy.py` (Opus-driven Behance + Google CSE query generation from brief calibration). `shared/judger.py` extension (`designer_facial_judge`, `designer_full_judge`, batch variants). Integration: full evaluation produces both text contextualization AND triggers vision-evaluation pass on top-N saves; both outputs combined into the candidate workspace card. Pre-built brief templates (5-7 templates per spec §6). Tests: prompt rendering for designer fixture brief; parser returns valid contextualization; vision-evaluation integration end-to-end.

- [ ] **Slice 8** — `designer/work_units.py` (`DesignerWorkUnitService` mirroring `github/work_units.py:GitHubWorkUnitService`). `designer/side_effects.py` (handle SAVE-family decisions; dispatch via `AbstractSaveDestination`). `designer/governor.py` (rate limits per source + Gemini API budget). `designer/orchestrator.py` (`DesignerPipeline` mirroring `github/orchestrator.py:GitHubPipeline`). `designer/session_orchestrator.py`. `shared/runtime_state/designer.py` (`DesignerRuntimeStateBridge`). `designer/recruiter_identity_resolver.py` + `shared/cross_module_identity/designer_to_linkedin.py`. Cloris control plane registration. HITL workspace surface rendering for vision-evaluation block (per-principle scoring layout, recruiter feedback markers). Tests: end-to-end pipeline run against mocked clients; runtime state transitions; resume after interruption; identity resolver against LinkedIn-recruiter mocks.

- [ ] **Slice 9** — Customer launch readiness: Behance developer key registered with appropriate quota tier, Google CSE configured with paid expansion, Gemini 2.5 Pro API access verified, customer-onboarding brief authoring guide updates for rubric authoring, demo brief authored and dry-runned end-to-end (text + vision evaluation producing recruiter-acceptable output on a hand-curated 30-portfolio test set), telemetry dashboard for facial pass rate / full eval pass rate / vision-evaluation pass rate / vision-evaluation feedback marker distribution / reconciliation success rate / save-to-confirmation rate. Tests: smoke run against demo brief produces ≥10 saves with vision evaluation and reconciled LinkedIn URLs.

## Test strategy

- Narrowest relevant test band to run first:
  - Slice-by-slice: `pytest tests/test_designer_<area>.py -q`
  - Cross-cutting: `pytest tests/test_designer_pipeline.py -q` after Slice 8.
- Tests to add:
  - `tests/test_designer_sources.py` — per-source REST client coverage.
  - `tests/test_designer_image_acquisition.py` — image URL extraction across source types.
  - `tests/test_designer_vision_evaluation.py` — prompt rendering, parser, fallback paths.
  - `tests/test_designer_pipeline.py` — end-to-end pipeline characterization (text + vision combined).
  - `tests/test_designer_runtime_state.py` — state-machine transitions, dedup, resume.
  - `tests/test_designer_judgment_templates.py` — prompt rendering and parser behavior.
  - `tests/test_designer_to_linkedin_resolution.py` — cross-module identity adapter.
  - Extend `tests/test_phase0_contracts.py` — `DesignerCalibration` and `BriefDesignRubric` hydration from V2 brief JSON.
  - Extend `tests/test_cloris_status_aggregation.py` — `"designer"` source in aggregation.
- Full-suite gate before declaring done: `make validate`.

## Open questions

- Whether Gemini 2.5 Pro access via Google AI Studio is sufficient or if Vertex AI is required for the structured-output + image-input combination needed. Decision: try Google AI Studio first (simpler integration); fall back to Vertex AI if rate limits or feature gaps require it.
- Confidence threshold for auto-applying designer↔LinkedIn resolution. Currently `≥ 0.85` per `docs/cloris-cross-module-identity-resolution-spec.md`. Decision: stick with 0.85 for v1; revisit after first-customer telemetry.
- Whether to run vision-evaluation on facial-pass candidates or only on full-eval saves. Decision: only on full-eval saves for v1 — running on facial-pass candidates would explode API cost (orders of magnitude more candidates). Revisit if customers want broader vision-evaluation coverage and cost economics support it.
- Whether the rubric authoring UX needs Authoring Loop polish in this plan or is a follow-up. Decision: ship with raw JSON-driven rubric authoring in v1; Authoring Loop UX polish for rubric editing is a Phase 3+ follow-up.

## Decisions

- 2026-04-30 — Module ships in 9 slices.
- 2026-04-30 — Pattern-mirror `github/` and `researcher/` directory shapes for the text-based pipeline; vision-evaluation pass is a net-new component with no analog in other modules.
- 2026-04-30 — V1 includes Behance + Google CSE for discovery, Gemini 2.5 Pro for vision evaluation. Dribbble, Read.cv, Instagram explicitly excluded. Are.na / Awwwards / SiteInspire are Phase 5 polish.
- 2026-04-30 — Vision-evaluation runs only on full-eval saves, not on facial-pass candidates. Cost-driven decision.
- 2026-04-30 — Default vision model: Gemini 2.5 Pro. Open-weight alternatives explicitly rejected for this module.
- 2026-04-30 — Default rubric ships with 6 principles + discipline-specific weight overrides for product / brand / motion / illustration / UX. Editorial work, Sam-authored.
- 2026-04-30 — Build target is 5-6 calendar weeks at split-attention pace; ~40 person-days.

## Follow-ups (not in this plan)

- Are.na enrichment for niche/conceptual designers — Phase 5 ship-quality polish.
- Awwwards / SiteInspire credit-graph integration — Phase 5 ship-quality polish.
- Live Google CSE strategy adaptation based on which CSE domains produce signal — Phase 5 ship-quality polish.
- Personal-site crawler for portfolio depth (beyond CSE-driven discovery) — defer until customer signal indicates need.
- Entertainment-industry-specific rubric variants (production design, key-art-specific brand, title-sequence motion) — defer until first entertainment-industry customer.
- Authoring Loop UX polish for rubric editing — Phase 3+ follow-up.
- Vision-evaluation on facial-pass candidates (broader coverage) — depends on cost economics and customer pull.
- Dribbble re-integration if their public discovery API recovers — opportunistic.
