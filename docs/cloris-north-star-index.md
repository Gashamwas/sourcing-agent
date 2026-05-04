# Cloris North Star Index

Status: living
Owner: Sam
Last updated: 2026-04-30

This is the entry point to the Cloris multi-module documentation suite. Every other strategic doc, spec, and plan in the suite is listed here with a one-line description of what it answers. A fresh contributor or AI window opening this document cold can answer "what is Cloris", "what are the modules", "what's the next thing to build", and "how do I add a new module" within two clicks each.

The index is grouped by audience and document type. Read top-down for breadth; jump to a specific cluster for depth.

## For the founder and strategic operators

Read these to understand what Cloris is, who it's for, and what it commits to.

- **[`Cloris-Product-North-Star.md`](../Cloris-Product-North-Star.md)** — what Cloris is, who buys, what wins, what's out of scope. The strategic spine. Start here if you've never seen this codebase.
- **[`Cloris-Module-Strategy.md`](../Cloris-Module-Strategy.md)** — module-by-module strategic assessment with target population, buyer persona, commercial viability, differentiation thesis, and priority ranking. The audit synthesis as durable strategy.
- **[`Cloris-Multi-Module-Roadmap.md`](../Cloris-Multi-Module-Roadmap.md)** — 12-month sequenced build plan with phase-level decision gates. The time-bound execution view of the strategy.
- **[`Cloris-Multimodality-Thesis.md`](../Cloris-Multimodality-Thesis.md)** — multimodality-as-module-category thesis articulated 2026-04-30. Designer module is the proof-of-concept; Tier 1 creative-work modules (Photographer, Motion, Game Art, Architect) are contingent on Designer validation. Status: thesis, not customer-validated strategy. Read this for the broader strategic framing of multimodal-LLM-plus-rubric evaluation across creative-work hiring disciplines.

## For engineers and technical contributors

Read these to understand how Cloris works under the hood and how new modules plug in.

- **[`Cloris-Architecture-North-Star.md`](../Cloris-Architecture-North-Star.md)** — platform invariants, contracts that should never break, substrate shape, lifecycle, worker model. The architectural spine.
- **[`docs/cloris-module-integration-contract.md`](cloris-module-integration-contract.md)** — the SDK. Every new module's required directory layout, exports, registrations. The "how do I add a new module" answer.
- **[`docs/cloris-ui-spec.md`](cloris-ui-spec.md)** — Cloris UI surfaces, voice, design tokens, visual system. Pre-existing canonical doc; the strategic suite references it but does not replace it.
- **[`docs/cloris-control-plane-spec.md`](cloris-control-plane-spec.md)** — control-plane semantics: launch, stop, status, readiness. Pre-existing.
- **[`docs/shared-candidate-execution-engine.md`](shared-candidate-execution-engine.md)** — execution engine internals. Pre-existing.

## Foundation specs (prerequisites for any non-LinkedIn module shipping)

Read these to understand the cross-cutting platform investments that gate module expansion.

- **[`docs/cloris-candidate-workspace-spec.md`](cloris-candidate-workspace-spec.md)** — the Cloris-native saved-candidate workspace. The destination for non-LinkedIn module saves. Single most important Phase 1 deliverable.
- **[`docs/cloris-save-destination-abstraction.md`](cloris-save-destination-abstraction.md)** — `AbstractSaveDestination` interface separating "how a save is recorded" from "what a save means."
- **[`docs/cloris-cross-module-identity-resolution-spec.md`](cloris-cross-module-identity-resolution-spec.md)** — `person` table + `person_candidate` linking + per-source-pair adapter algorithms. The reconciliation moat.
- **[`docs/cloris-brief-multi-module-extensions.md`](cloris-brief-multi-module-extensions.md)** — concrete brief schema changes: `linkedin_project` default-empty, `target_modules` field, per-source nested calibration.

## Per-module specs

Read the module spec for any module you're working on, considering, or trying to understand. Specs follow the shape defined by [`docs/cloris-module-template.md`](cloris-module-template.md).

**Build-now / build-soon (Phase 2-3 of the roadmap):**

- **[`docs/researcher-module-spec.md`](researcher-module-spec.md)** — Researcher module (ML researchers). OpenAlex spine + Semantic Scholar + dblp + arXiv. Highest-priority module.
- **[`docs/oss-maintainers-module-spec.md`](oss-maintainers-module-spec.md)** — OSS Maintainers as GitHub++ extension with npm/PyPI/crates.io adapters. Two-tier ship: brief-only quick win, then full module.
- **[`docs/exec-search-workflow-spec.md`](exec-search-workflow-spec.md)** — Exec Search as LinkedIn workflow mode wiring `market_intelligence/` into run launch. Not a separate module.
- **[`docs/healthcare-extension-spec.md`](healthcare-extension-spec.md)** — Healthcare/Life Sciences as Researcher variant with PubMed adapter.

**Build-now / build-soon (Phase 2 of the roadmap, re-sequenced 2026-04-30):**

- **[`docs/designer-hitl-module-spec.md`](designer-hitl-module-spec.md)** — Designer module under HITL framing with vision-evaluation enhancement (added 2026-04-30 v1 reframe). Re-sequenced from Phase 5 to Phase 2 per `Cloris-Multimodality-Thesis.md`.

**Build-later (Phase 4-5 of the roadmap):**

- **[`docs/defense-module-spec.md`](defense-module-spec.md)** — Defense engineering module as Researcher variants (SBIR + Patents + IEEE). Compliance posture documented.
- **[`docs/sales-leadership-workflow-spec.md`](sales-leadership-workflow-spec.md)** — Sales Leadership as LinkedIn workflow configuration with sales-specific Perplexity prompting and lower confidence bands.
- **[`docs/legal-brief-and-bar-lookup-spec.md`](legal-brief-and-bar-lookup-spec.md)** — Legal as LinkedIn brief templates plus bar admission lookup side effect. Not a full module.

**Tier 1 multimodal-creative module stubs (Status: draft, contingent on Designer Phase 2 validation per `Cloris-Multimodality-Thesis.md`):**

- **[`docs/photographer-module-spec.md`](photographer-module-spec.md)** — Photographer / cinematographer module stub. Editorial photo, ad agency DPs, fashion photo. Reuses Designer's architectural primitives.
- **[`docs/motion-module-spec.md`](motion-module-spec.md)** — Motion / 3D / VFX module stub. Reels and animation work. Multimodal-LLM handles video natively.
- **[`docs/game-artist-module-spec.md`](game-artist-module-spec.md)** — Game Art / concept art module stub. Character / environment / prop art for games. Buyer pool: AAA studios, indie, animation.
- **[`docs/architect-module-spec.md`](architect-module-spec.md)** — Architecture module stub. Renderings, plans, photography of built work. Buyer pool: architecture firms, real estate developer in-house teams.

## Implementation plans (time-bound, slice-based)

Read these to understand what's actively being built. Each plan follows `plans/_template.md`.

- **[`plans/multi-module-foundation.md`](../plans/multi-module-foundation.md)** — Phase 1 buildout: brief schema fixes, control plane parameterization, candidate workspace v1, save destination abstraction, calibration vertical-agnostic completion.
- **[`plans/researcher-module-build.md`](../plans/researcher-module-build.md)** — Researcher module v1 implementation. Slices map to spec sections.
- **[`plans/oss-maintainers-build.md`](../plans/oss-maintainers-build.md)** — OSS Maintainers two-phase build: brief-only quick win, then full module with registry adapters.
- **[`plans/designer-module-build.md`](../plans/designer-module-build.md)** — Designer module v1 implementation (added 2026-04-30). 9 slices including text-based pipeline + brief-encoded design rubric + image acquisition + Gemini 2.5 Pro vision evaluation + HITL workspace surface.

## Adjacent pre-existing docs to reference (not part of the suite, but load-bearing)

These are not new artifacts of this documentation suite. They are pre-existing docs that the suite references rather than duplicates.

- **[`Sourcing-Agent-2nd-Gen-Roadmap.md`](../Sourcing-Agent-2nd-Gen-Roadmap.md)** — the completed runtime/state migration roadmap. Historical context for the architecture.
- **[`GitHub-LinkedIn-Reconciliation-Source-of-Truth.md`](../GitHub-LinkedIn-Reconciliation-Source-of-Truth.md)** — the reconciliation contract. Frames every module as upstream of the canonical workspace.
- **[`plans/calibration-layer-vertical-agnostic.md`](../plans/calibration-layer-vertical-agnostic.md)** — the in-flight refactor making the substrate vertical-agnostic. Phase 1 prerequisite.
- **[`REVIEWED_CANDIDATE_MEMORY_AND_HITL_OUTREACH_ROADMAP.md`](../REVIEWED_CANDIDATE_MEMORY_AND_HITL_OUTREACH_ROADMAP.md)** and the related M0_M1 spec at the repo root — pre-existing candidate workspace and HITL outreach design context.
- **[`plans/perplexity-evidence-augmentation.md`](../plans/perplexity-evidence-augmentation.md)** — pre-existing infrastructure used by the Sales Leadership and Exec Search workflow specs.
- **[`AGENTS.md`](../AGENTS.md)**, **[`CODEX.md`](../CODEX.md)**, **[`CREW.md`](../CREW.md)** — repo-level instructions and workflow conventions.

## Common questions and where they answer

- *What is Cloris?* — `Cloris-Product-North-Star.md` §1-2.
- *Why these modules?* — `Cloris-Module-Strategy.md` §2.
- *In what order?* — `Cloris-Multi-Module-Roadmap.md`.
- *How do I add a new module?* — `docs/cloris-module-integration-contract.md`.
- *What's the next thing to build?* — `Cloris-Multi-Module-Roadmap.md` Phase 1 + `plans/multi-module-foundation.md`.
- *Where does a candidate save go?* — `docs/cloris-candidate-workspace-spec.md` + `docs/cloris-save-destination-abstraction.md`.
- *How does Cloris know it's the same person across modules?* — `docs/cloris-cross-module-identity-resolution-spec.md`.
- *Why this brief schema?* — `Cloris-Architecture-North-Star.md` §3 + `docs/cloris-brief-multi-module-extensions.md`.
- *What does the UI look like?* — `docs/cloris-ui-spec.md` (pre-existing).
- *What's the multimodality / creative-work category thesis?* — `Cloris-Multimodality-Thesis.md`. Designer is the proof-of-concept; Tier 1 stubs at `docs/{photographer,motion,game-artist,architect}-module-spec.md` are contingent on Designer's Phase 2 validation.

## Maintenance

This index is updated whenever a doc in the suite is added, renamed, or removed. The other living documents (the four root strategic docs) are re-versioned as customer signal arrives. Per-module specs are updated when the module's strategy or implementation changes. Implementation plans are updated as slices ship.

Document drift between this index and the actual filesystem is a defect. If you find a doc listed here that doesn't exist or a doc on disk that's not listed here, fix the index.
