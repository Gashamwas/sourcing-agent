# Cloris Multi-Module Roadmap

Status: living
Owner: Sam
Last updated: 2026-04-30

This document is the time-sequenced 12-month build plan for evolving Cloris from a LinkedIn-first sourcing product into a multi-module sourcing platform. It inherits priorities from `Cloris-Module-Strategy.md` and architectural invariants from `Cloris-Architecture-North-Star.md`. Implementation plans under `plans/` are the slice-level execution artifacts; this document is the phase-level sequencing. For the multimodality-as-module-category thesis (Tier 1 creative-work modules beyond Designer, contingent on Designer's commercial validation), see `Cloris-Multimodality-Thesis.md` — Tier 1 candidates appear in this roadmap as deferred / contingent items pending the Phase 2 decision gate.

The roadmap is re-versioned quarterly. Decision gates are explicit. Customer signal can collapse or reorder phases at any point — the sequencing below is the prior, not the schedule.

## Roadmap horizon

May 2026 → April 2027. Twelve months. After April 2027 the roadmap is rewritten in light of what shipped, what generated revenue, and what customer signal drove the next priorities.

## Reading the roadmap

Each phase has:

- **Goal** — the outcome that defines success.
- **Slices** — the discrete work blocks, each linked to an implementation plan in `plans/` where one exists.
- **Decision gate** — what the platform learns from this phase that determines what ships next. Gates are framed as customer signal, not engineering completion.
- **Concurrent work** — workstreams that overlap with the phase but are not the phase's primary outcome.

The roadmap assumes solo founder execution with AI-assisted engineering. Calendar estimates account for context-switching, customer-development time, and architectural-correction overhead. Pure engineering time would be ~40-50% of calendar time.

---

## Phase 0: Strategic spine and audit closure (April 29 — May 2, 2026)

**Goal.** The audit synthesis from both Claude windows and the founder's pushback is captured in durable documentation. Future AI windows and contributors can drop into the codebase and find the strategic and architectural picture in two clicks from `docs/cloris-north-star-index.md`.

**Slices.**

1. Strategic spine — `Cloris-Product-North-Star.md`, `Cloris-Architecture-North-Star.md`, `Cloris-Module-Strategy.md`, this roadmap, and `docs/cloris-north-star-index.md`.
2. Integration contract — `docs/cloris-module-integration-contract.md`.
3. Foundation specs — candidate workspace, save destination abstraction, cross-module identity resolution, brief multi-module extensions.
4. Per-module specs — researcher, OSS maintainers, exec search workflow, healthcare, defense, designer HITL, sales leadership, legal.
5. Implementation plans — multi-module foundation, researcher build, OSS maintainers build.

**Decision gate.** None — this phase is documentation only. Gate is: are the documents sufficient to drop a fresh AI window into the codebase and have it answer "what's the next thing to build" without re-reading the entire codebase?

**Concurrent work.** None.

---

## Phase 1: Foundation buildout (May 2026 — June 2026, ~6-8 weeks)

**Goal.** The substrate, brief schema, and Cloris control plane support multi-module operation. The candidate workspace exists. No non-LinkedIn module has shipped yet, but every prerequisite for shipping one is in place.

**Slices** (executed via `plans/multi-module-foundation.md`).

1. **`linkedin_project` field default-empty fix.** `shared/brief_schema.py:190` becomes `linkedin_project: str = ""`. `shared/brief_loader.py` passes through. LinkedIn side effects handle empty gracefully (skip the save-to-pipeline browser action when project is empty). Tests assert non-LinkedIn briefs load without error.
2. **`target_modules: list[str]` field on Brief.** `shared/brief_schema.py` adds the field with default `["linkedin"]`. `shared/brief_loader.py` hydrates it from V2 brief JSON. Cloris UI uses it to filter brief lists and gate launch options.
3. **Per-source nested calibration refactor on `FacialCalibration`.** `shared/brief_schema.py:104-107`'s flat `github_*_patterns` fields move to `FacialCalibration.sources: dict[str, SourceCalibration]`. Compat shim preserves access via the old flat names so existing briefs and code continue to work. Tests assert both old and new access patterns produce the same prompt rendering.
4. **`cloris/worker.py:196` parameterization.** Worker accepts `--source` CLI flag. Dispatch table maps source names to session-orchestrator module paths. Sidecar JSON `source` field is parameterized.
5. **Generic `POST /api/launch/{source}` endpoint** in `cloris/api.py`. `LaunchResponse.source` literal at `cloris/models.py:205` widens to support the registered modules. `cloris/control_plane.py:175` `_SOURCES` widens.
6. **Candidate workspace v1.** Per `docs/cloris-candidate-workspace-spec.md`. New SQLite schema additions for the workspace. New API endpoints for read/write. Cloris UI surface for the workspace (cross-source, brief-scoped, editorial card layout per `docs/cloris-ui-spec.md:271-279`).
7. **`AbstractSaveDestination` interface.** Per `docs/cloris-save-destination-abstraction.md`. `LinkedInRecruiterSaveDestination` (existing behavior, refactored). `CandidateWorkspaceSaveDestination` (new, writes to workspace). Brief declares its save destination(s).
8. **`market_intelligence/` integration into LinkedIn run launch.** Stage 0 investigation pass before strategy formation. UI surface for research-output review before run start.
9. **Calibration vertical-agnostic refactor Slices 2-5** (`plans/calibration-layer-vertical-agnostic.md`). Strip remaining AI-specific lexicon from `linkedin/judgment_templates.py`, `linkedin/strategy.py`, `shared/judger.py`, `shared/preflight*.py`. Required so the substrate is genuinely vertical-agnostic before any non-LinkedIn module ships.
10. **Feedback artifact + run-to-brief pinning.** Required for Next Run Learning surface and for the platform's compounding evaluation quality. Per `docs/cloris-ui-spec.md:386-391`.

**Decision gate.** None of these slices have customer-signal gates; they are platform prerequisites. The gate at the end of Phase 1 is: can a non-LinkedIn module ship to a paying customer without the platform breaking? If yes, proceed to Phase 2. If no, identify the missing piece and add it to Phase 1.

**Concurrent work.** Customer development for Researcher (frontier labs and AI exec search firms — at least 5 named conversations before Phase 2 ships).

---

## Phase 2: Researcher v1 + OSS Maintainers + Designer (June 2026 — September 2026, ~12-14 weeks)

**Goal.** Three non-LinkedIn modules in production. Researcher delivers ML-researcher candidates to at least 3 frontier-lab customers. OSS Maintainers Tier 2 (with registry adapters) delivers maintainer candidates to at least 2 frontier-lab or DevTool customers. Designer (HITL with vision-evaluation enhancement) delivers VLM-evaluated portfolio recommendations to at least 1-2 in-house design teams or design recruiting consultancies.

Note: Designer was re-sequenced from Phase 5 to Phase 2 on 2026-04-30. Rationale: VLM-driven portfolio evaluation is uncontested in the recruiting tools market and the novelty window is finite (6-12 months before horizontal incumbents attempt to copy). The original Phase 5 placement left strategic value on the table. Phase 2 is correspondingly heavier; the timeline extends by ~2-4 weeks.

**Slices.**

1. **OSS Maintainers Tier 1 brief.** Authored at the start of Phase 2 as a quick win. Zero engineering. Brief targets maintainer behavior using existing GitHub adapter capabilities. Ships in week 1; validates customer pull before Tier 2 engineering investment.
2. **Researcher module v1** per `plans/researcher-module-build.md` and `docs/researcher-module-spec.md`. Ships ~weeks 1-4 of Phase 2. Source adapters: OpenAlex (spine), Semantic Scholar, dblp, arXiv. Brief schema additions for `ResearcherCalibration`. New `researcher/judgment_templates.py` plus `shared/judger.py` extensions for `researcher_facial_judge` and `researcher_full_judge`. Reconciliation to LinkedIn via `linkedin/recruiter_identity_resolver.py` extension with researcher-specific identity heuristics (ORCID, name + affiliation, GitHub bridge if linked).
3. **OSS Maintainers Tier 2 full module** per `plans/oss-maintainers-build.md` and `docs/oss-maintainers-module-spec.md`. Ships ~weeks 5-7 of Phase 2 in parallel with Researcher's later weeks. Three registry adapters in `github/registries/{npm,pypi,crates}.py`. Maintainer-impact scoring function. Brief schema additions for `MaintainerCalibration`. Evidence integration via `to_evidence_text()` extension in `github/schemas.py`.
4. **Exec Search workflow mode** per `docs/exec-search-workflow-spec.md`. Ships ~weeks 3-5 of Phase 2 in parallel with Researcher. API endpoint triggering `market_intelligence/engine.py` before run launch. UI step for research output review. Pre-built executive brief templates.
5. **Designer module v1 (HITL with vision-evaluation enhancement)** per `plans/designer-module-build.md` and `docs/designer-hitl-module-spec.md`. Ships ~weeks 6-12 of Phase 2 in parallel with Researcher's customer onboarding and OSS Maintainers Tier 2's later weeks. Behance + LinkedIn + Google CSE adapters. `DesignerCalibration` and `BriefDesignRubric` schema additions. Default rubric authoring (6 principles × 4 anchor levels with discipline overrides). Image acquisition layer. Gemini 2.5 Pro integration with rubric-loaded prompt + structured output. HITL workspace surface (`surface_type: "hitl_visual_review"`). Designer-to-LinkedIn identity resolver. Pre-built brief templates per discipline.
6. **Customer onboarding for Researcher, OSS Maintainers, and Designer.** Founder-led, brief-authoring-assisted. Three frontier-lab customers for Researcher; two for OSS Maintainers; one to two for Designer (in-house design team at a design-forward operation, or a boutique design recruiting consultancy). Each onboarding produces telemetry on brief-authoring friction, evaluation quality, and false-positive rate that feeds Phase 3 priorities.

**Decision gate at end of Phase 2.**

- *If all three modules have at least their target customer counts (Researcher 3+, OSS Maintainers 2+, Designer 1+):* proceed to Phase 3 (cross-module identity + Healthcare extension).
- *If Researcher and OSS Maintainers ship to target but Designer has no customers:* Designer becomes a Phase 3 customer-development priority rather than a Phase 2 commercial module. The novelty thesis still holds but needs longer-cycle buyer education.
- *If Researcher has 1-2 customers but OSS Maintainers has 5+:* reorder Phase 3 to invest in OSS Maintainers expansion (more registries, deeper signals) before Healthcare.
- *If none of the three has paying customers:* halt module work. Spend Phase 3 on customer development and platform polish for the LinkedIn module + Researcher + OSS Maintainers + Designer. Re-evaluate at end of Phase 3.

**Concurrent work.** Customer development for Defense (5-10 named conversations with defense recruiting firms, defense primes, defense-tech startups). Customer development for Designer if buyer pull from Phase 2 launches is thinner than expected.

---

## Phase 3: Cross-module identity + Healthcare + Defense customer development (August 2026 — November 2026, ~10-12 weeks)

**Goal.** Cross-module candidate identity is resolved automatically; Run Review presents persons, not per-source rows. Healthcare module ships as a Researcher variant. Defense customer development is mature enough to gate Phase 4 engineering.

**Slices.**

1. **Cross-module identity resolution layer** per `docs/cloris-cross-module-identity-resolution-spec.md`. New `person` and `person_candidate` tables. New `shared/cross_module_identity/` directory with adapter functions per (source_a, source_b) pair. Run Review surface refactored to person-first. ~4-6 weeks of engineering.
2. **Healthcare extension to Researcher module.** PubMed adapter at `researcher/sources/pubmed.py`. Biomedical brief calibration vocabulary. Ships ~weeks 4-6 of Phase 3 (overlapping with cross-module identity). ~1-2 weeks of engineering.
3. **Defense customer development.** Identify 5-10 named defense recruiting firms, defense primes, defense-tech startups. Run discovery calls. Validate willingness to pay. Specify the compliance shell their procurement teams will require. Document SOC 2-style audit trails the platform will need to produce. **No engineering** for Defense in Phase 3.
4. **Process-pool-level shared governor.** `shared/safety/cross_module_governor.py`. Necessary at module #3+. ~1-2 weeks. LLM API budget coordination across concurrent module workers.
5. **Brief authoring tooling polish.** Multi-module brief authoring is already the choke point. Authoring Loop UX investments per `docs/cloris-ui-spec.md:163-184`. Ongoing.

**Decision gate at end of Phase 3.**

- *If Defense customer development produced 2+ committed customers:* proceed to Phase 4 with Defense build.
- *If Defense customer development produced strong interest but no commitments:* defer Defense engineering to Phase 5; spend Phase 4 on the Sales Leadership workflow and module polish.
- *If Defense customer development produced no traction:* drop Defense from the 2026-2027 roadmap. Spend Phase 4 on the next-highest-priority module per customer signal (likely Sales Leadership and additional Researcher/OSS Maintainers depth).

**Concurrent work.** Sales Leadership workflow customer development (named conversations with sales recruiting firms; validate willingness to pay for "best available public evidence" framing).

---

## Phase 4: Defense module + Sales Leadership workflow (November 2026 — February 2027, ~12-14 weeks)

**Goal.** Defense module ships as Researcher variants (SBIR + Patents + IEEE adapters) with the compliance shell. Sales Leadership ships as a LinkedIn workflow configuration. Both modules have customer onboarding underway.

**Slices** (Defense block — gated on Phase 3 decision gate).

1. **Defense module engineering** per `docs/defense-module-spec.md`. Three new adapters at `researcher/sources/{sbir,patents,ieee}.py`. SBIR.gov adapter ships first as a high-signal validation step. Patent and IEEE adapters follow. Defense-specific brief calibration vocabulary (CPC patent classification codes, SBIR agency codes, IEEE conference venue patterns). ~3-4 weeks.
2. **Compliance audit shell.** Immutable evidence logs, audit-trail surface, contractual reps document. Provenance disclosure visible to recruiter and customer. ~1-2 weeks.
3. **Defense customer onboarding.** Founder-led; expect 6-12 month commercial cycles even with the engineering ready. First 2-3 customers are early adopters tolerant of evolving features.

**Slices** (Sales Leadership block — independent of Defense).

4. **Sales Leadership workflow** per `docs/sales-leadership-workflow-spec.md`. Sales-leadership-specific Perplexity prompt variant in `shared/external_evidence/provider.py`. Pre-built sales leadership brief templates calibrated to GTM-architecture builder/user distinctions. Confidence calibration via `PostSaveModifier` patterns. ~2 weeks.
5. **Sales Leadership customer onboarding.** Position honestly. "Best available automated synthesis of public evidence for sales leadership profiles." Don't lead with this on the platform homepage.

**Concurrent work.** Designer customer development if there's appetite to ship Designer in Phase 5. Otherwise, Phase 4 is the longest phase and the platform's sequence-flexibility window.

**Decision gate at end of Phase 4.**

- *If Defense + Sales Leadership both shipped and have at least 1 paying customer each:* proceed to Phase 5 (Designer + platform investments).
- *If only one shipped successfully:* slot the other into Phase 5; consider whether the Phase 4 failure was customer-side or platform-side and adjust strategy.
- *If neither shipped successfully:* halt module expansion. Spend Phase 5 on platform polish, module #1-3 customer expansion, and feedback-loop maturity.

---

## Phase 5: Platform investments + customer expansion (February 2027 — April 2027, ~8-10 weeks)

**Goal.** The candidate workspace + feedback loop have matured to the point that recruiters demonstrably author better briefs in week 8 than in week 1. The architecture has not regressed; the platform is positioned for 2027 hosted operation if customer demand emerges. Designer ship-quality polish lands here (the v1 module shipped in Phase 2; this is the production-grade hardening).

Note: Designer module v1 was re-sequenced from Phase 5 to Phase 2 on 2026-04-30. The Phase 5 work on Designer is now ship-quality polish (Are.na enrichment, Awwwards credit-graph integration, live Google CSE strategy adaptation, vision-evaluation prompt iteration based on accumulated customer feedback) rather than initial module build.

**Slices.**

1. **Designer ship-quality polish.** Are.na enrichment for niche/conceptual-design briefs. Awwwards/SiteInspire credit-graph integration. Live Google CSE strategy adaptation based on which CSE domains are producing signal. Vision-evaluation prompt iteration per discipline, informed by 6+ months of customer feedback. Outreach polish. ~2-3 weeks.
2. **Feedback-loop maturity investments.** Brief revision proposal quality (Next Run Learning surface). Calibration drift detection. Review-rate-vs-save-rate telemetry per brief. ~2-3 weeks.
3. **Module marketplace contract documentation.** Document the integration contract that has emerged from shipping 4-5 modules. Identify the abstractions that are stable enough to expose as an SDK if commercial demand for third-party modules ever materializes. ~1-2 weeks. Not a marketplace launch — just documentation.
4. **Platform performance and resilience.** Multi-module operation under sustained customer load. Concurrent worker supervision. Failure-recovery audit. ~1-2 weeks.
5. **Q4 2026 / Q1 2027 customer expansion** for the modules that shipped earlier. Customer renewal at the 12-month boundary is the financial gate for funding 2027 work.

**Decision gate at end of Phase 5.**

- *If 8-15 paying customers across two or three commercial tiers:* the platform is ready for 2027 expansion. Decide whether 2027 is "more modules" or "deeper modules" (more depth in the existing Researcher / OSS Maintainers / Defense) based on customer pull.
- *If <8 paying customers:* customer expansion is the 2027 priority, not module expansion. The platform is technically ready but commercially ahead of demand; rebalance toward GTM.

---

## Modules deferred outside the 12-month roadmap

These modules are documented in `docs/` but not on the roadmap above. They ship opportunistically if customer pull emerges, otherwise they wait.

- **Legal** — `docs/legal-brief-and-bar-lookup-spec.md`. LinkedIn brief templates plus a bar admission lookup side effect. Not a full module.
- **Kaggle** — `docs/researcher-module-spec.md` references it as an optional enrichment signal in Researcher. Standalone Kaggle module not roadmapped.
- **LinkedIn X-ray** — tactical addition to LinkedIn module, ~1 week. Build whenever the LinkedIn module has a need.
- **Government / civic-tech** — not in the documentation suite. Customer-development-only at this stage.
- **PE-backed company exec search** — covered by Exec Search workflow mode + Sales Leadership workflow. No separate module.

## Tier 1 multimodal-creative modules — contingent on Designer Phase 2 validation

Per `Cloris-Multimodality-Thesis.md`, these modules are candidate territory once Designer ships and commercially validates in Phase 2. Stub specs capture current thinking; build sequencing is determined by customer pull from Phase 2 creative-work customers, not by speculative engineering schedule. If Designer does not validate, these modules stay deferred indefinitely.

- **Photographer / cinematographer** — `docs/photographer-module-spec.md` (Status: draft). Editorial photo, ad agency DPs, fashion photo. Reuses Designer's architectural primitives (`BriefRubric`, asset acquisition, multimodal evaluation pass, HITL workspace surface) with photography-specific rubric content. Estimated build cost ~2-3 weeks if primitives are clean — most of the engineering is shared with Designer.
- **Motion / 3D / VFX** — `docs/motion-module-spec.md` (Status: draft). Reels (video), animation work, technical breakdowns. Multimodal-LLM handles video natively. Same architectural pattern. Estimated build cost ~2-3 weeks.
- **Game Art / concept art** — `docs/game-artist-module-spec.md` (Status: draft). Character / environment / prop / UI art for games. Buyer pool: AAA studios, indie studios, animation companies. Estimated build cost ~2-3 weeks.
- **Architecture** — `docs/architect-module-spec.md` (Status: draft). Renderings, plans, photography of built work. Buyer pool: architecture firms, real estate developer in-house teams. Estimated build cost ~2-3 weeks.

**Decision gate to promote any Tier 1 module from deferred to active roadmap:** End-of-Phase-2 review confirms (a) Designer has at least 1-2 paying customers, (b) recruiter feedback on Designer's vision-evaluation output is majority "Useful guidance", (c) at least one Phase 2 creative-work customer (or net-new conversation) is asking for the specific Tier 1 discipline. If all three: insert the discipline into Phase 3 or Phase 4 alongside the existing slices. If only (a) and (b): hold all Tier 1 modules in deferred status; spend Phase 3 hardening Designer customer base and refining the architectural primitives. If (a) fails: revert to the pre-thesis roadmap; Tier 1 modules stay deferred indefinitely.

## Tier 2 audio + Tier 3-4 creative-work modules — explicitly opportunistic

Per `Cloris-Multimodality-Thesis.md` §3, Tier 2 (Voiceover, Composer, Sound Design) and Tier 3-4 disciplines have additional gating considerations (audio-LLM maturity for Tier 2; consent / ethics for Tier 3 performance roles; smaller buyer pools for Tier 4). Not stub-specced. Revisit only when Tier 1 has at least two disciplines validating, or when explicit customer pull emerges.

## Decisions captured here

- 2026-04-29 — Phase 0 (this documentation suite) ships May 2, 2026.
- 2026-04-29 — Phase 1 (foundation buildout) is gated on platform-readiness, not customer signal. No non-LinkedIn module ships before Phase 1 completes.
- 2026-04-29 — Phase 2 ships Researcher and OSS Maintainers in parallel. Customer-signal gates at end of Phase 2 determine whether Phase 3 invests in cross-module identity + Healthcare or pivots to OSS Maintainers depth. *Updated 2026-04-30 to add Designer; see below.*
- 2026-04-29 — Defense engineering is gated on Phase 3 customer-development outcome, not on engineering readiness.
- 2026-04-29 — Designer ships in Phase 5 after candidate workspace and feedback loop have matured. *Superseded 2026-04-30; Designer re-sequenced to Phase 2.*
- 2026-04-29 — The roadmap is re-versioned at the end of each phase based on customer signal. Phase ordering is the prior, not a deterministic schedule.
- 2026-04-29 — Module marketplace is documentation-only in 2026-2027. SDK launch is a 2027+ decision pending customer demand.
- **2026-04-30 — Designer re-sequenced from Phase 5 to Phase 2.** Trigger: novelty argument re-evaluated. VLM-driven portfolio evaluation is uncontested in the recruiting tools market in 2026, and the novelty window (6-12 months before horizontal incumbents copy) is finite. The original Phase 5 placement landed Designer when the novelty window was already closing. Phase 2 placement captures the strategic asymmetry while novelty is at peak. Phase 2 timeline extends by ~2-4 weeks; Phase 5 contracts correspondingly (Designer there is now polish, not build).
- **2026-04-30 — Designer v1 ships with vision-evaluation enhancement to HITL.** Vision evaluation is no longer v2-deferred. Default model: Gemini 2.5 Pro. Recruiter remains the arbiter of save/reject; vision evaluation provides senior-associate-level rubric-decomposed guidance. See `docs/designer-hitl-module-spec.md`.
- **2026-04-30 — Customer-asking-as-gate explicitly rejected for thesis-driven differentiated module decisions.** Pre-build interviews for category-creating products are weak signals. Validation gate is post-demo reactions and revenue, not pre-build asking. Applies to Designer specifically; encoded in module re-sequencing rationale here.
- **2026-04-30 — Tier 1 multimodal-creative modules (Photographer, Motion, Game Art, Architect) added to deferred / contingent roadmap section** per `Cloris-Multimodality-Thesis.md`. Stub specs at `docs/{photographer,motion,game-artist,architect}-module-spec.md` in `Status: draft`. Promotion to active roadmap is gated on Designer's Phase 2 commercial validation per the decision gate documented in this doc.
- **2026-04-30 — Tier 2 audio + Tier 3-4 modules explicitly opportunistic.** Not stub-specced; not roadmapped; not engineered until Tier 1 validates and customer pull demands.

## Follow-ups (not in this roadmap)

- Hosted multi-tenant operation. Deferred until at least three modules are commercially validated (per `Cloris-Product-North-Star.md` section 3).
- Outreach automation. Out of scope per product north star.
- Cross-customer benchmarking and analytics. Out of scope.
- Public API for external evaluation. Out of scope (per product north star section 3).
