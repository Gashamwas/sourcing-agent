# Cloris Module Spec Template

Status: living
Owner: Sam
Last updated: 2026-04-29

This is the authoring template for Cloris module specs. Every module spec in `docs/<module>-module-spec.md` (or `docs/<module>-workflow-spec.md` for workflow-only modules) follows this shape so reviewers know where to find each piece, comparisons across modules work, and the integration contract (`docs/cloris-module-integration-contract.md`) is verifiable.

Copy this template to a new module spec file and fill in each section. Sections are ordered by reading priority — readers should be able to stop after the first three sections and have a clear picture of what the module is for.

---

# <Module Name> Module Spec

Status: draft | ready-to-implement | shipped
Owner: <name>
Last updated: <YYYY-MM-DD>

## 1. Target population

The narrowest defensible characterization of who this module finds. One paragraph.

Be specific. "Researchers" is too vague; "ML researchers with 3+ years post-PhD industry experience and first-author publications at NeurIPS/ICML/ICLR/EMNLP within the last 24 months" is the level of specificity required. Include:

- Career stage / years of experience.
- Publication or output record (papers, patents, packages, portfolios — whatever's relevant).
- Current affiliation tier or trajectory.
- What's *excluded* — specific edge cases that look adjacent but aren't a fit.

## 2. Buyer persona

Who buys this module and why. One paragraph.

- Buyer types (recruiting firm subtype, in-house team type, agency type).
- Estimated buyer pool size (named buyers, not market estimates).
- Why this buyer cannot solve the discovery problem with existing tools (LinkedIn alone, Apollo, ZoomInfo, etc.).
- Pricing range supportable by buyer economics.

## 3. Differentiation thesis

What makes Cloris's version of this module materially better than what exists. One paragraph.

If the answer is "we have data nobody else has," check that claim against the data foundation reality (section 5). Most often the differentiation is "we evaluate the data well, calibrated to the role, at scale" rather than "we have the data."

If there is no clear differentiation, say so explicitly. The module is either a low-priority build or shouldn't be built.

## 4. Strategic priority and roadmap fit

Cite `Cloris-Module-Strategy.md` ranking. Cite `Cloris-Multi-Module-Roadmap.md` phase. Specify any prerequisites (foundation work, other modules, customer development) that gate the build.

## 5. Data foundation

Per source the module pulls from, document:

- **API status as of the spec date.** Free / paid / paid-enterprise. Auth required. Rate limits. Coverage and freshness.
- **Identity quality.** What identity data the source surfaces — name, affiliation, ORCID/handle, email, geography. How reliable each is.
- **ToS posture for commercial recruiting use.** Quote the source's relevant policy if possible.
- **Detection or scraping risk** if any portion of acquisition is non-API.
- **Verdict.** Whether to use the source as anchor / enrichment / not-at-all.

If the module pulls from multiple sources, list each. Lead with the spine source (the one most candidates come from). Group enrichment sources after.

End the section with: an explicit list of sources considered and rejected, with reasons. Forecloses future debate.

## 6. Source-specific brief calibration

What new fields the brief schema needs to support this module's calibration. Cross-reference `docs/cloris-brief-multi-module-extensions.md` so the schema-level changes are tracked there, not duplicated here.

For each new field:

- Field name and type.
- What the field encodes (e.g., "h-index floor below which the candidate is rejected without further evaluation").
- Default value when not configured (typically empty/zero so the field is inert).

If the module needs a module-level calibration dataclass (e.g., `ResearcherCalibration`), note it here and reference the schema spec.

## 7. Evaluation pipeline mapping

How the existing capability/depth/transferability/decision procedure applies to this module's candidates.

- **What's the snippet evidence** (light evidence used for facial triage)?
- **What's the full evidence** (deep evidence used for full evaluation)?
- **How does the brief's `depth_distinction` translate to this domain?** (E.g., for Researcher: builder = active researcher publishing original work; user = industry-applied person citing research.)
- **What's the decision contract?** Standard `SAVE`/`REJECT` plus the `INFERENTIAL_SAVE`/`TRANSFERABLE_SAVE`/`SIGNAL_SAVE` family, or does the module need a non-standard surface type (e.g., Designer's `hitl_visual_review`)?

## 8. State machine fit

Confirm the existing lifecycle (`shared/runtime_state/store.py:62-71`) maps onto this module's pipeline. If the module needs new lifecycle states, surface them explicitly with rationale — most modules will not.

Document the work-unit `KIND` constant the module declares.

## 9. Identity disambiguation

Within the module's data sources, how does the module distinguish two candidates with the same name? What identity anchors are available (ORCID, GitHub username, patent inventor key, etc.)?

If the module's source naturally produces ambiguous identities (common-name collisions on arXiv, etc.), document the disambiguation strategy: light Perplexity lookup, manual flag for review, etc.

## 10. Reconciliation strategy

How candidates from this module reconcile to LinkedIn (the canonical reconciliation surface) and to other modules.

Cross-reference `docs/cloris-cross-module-identity-resolution-spec.md` for the `<module>_to_linkedin.py` adapter. Document the resolution methods the adapter uses and the confidence bands.

If the module produces candidates that don't have LinkedIn equivalents (e.g., academic researchers who aren't on LinkedIn), document the fallback — the candidate stays per-source in the workspace until manually resolved or LinkedIn-discovered later.

## 11. Save destination

Which `AbstractSaveDestination`(s) the module uses. Default for non-LinkedIn modules is `["candidate_workspace"]`. LinkedIn module uses `["linkedin_recruiter", "candidate_workspace"]`. If the module needs a custom destination (CSV export, webhook), document and reference `docs/cloris-save-destination-abstraction.md`.

Document any module-specific outreach generation (e.g., `<module>/outreach.py`).

## 12. Build effort estimate

Calendar-time estimate, including realistic context-switching and customer-development overhead. Don't hedge — give a number.

Break down by phase:

- Source adapter(s): N weeks.
- Brief schema additions: N days.
- Evaluation templates and judger integration: N days.
- Side-effects / save destination integration: N days.
- Recruiter identity resolver: N days.
- Tests: N days.
- Total: N weeks.

## 13. First-customer demonstration scope

The minimum viable version that demonstrates the module to a first customer. One paragraph describing the demo brief, what the module produces, and what the customer sees.

Be honest about what's not in the demo: which features land later, which evidence sources are deferred, what UI polish is missing.

## 14. Ship-quality scope

The version that's ready for paying customers. Beyond the demo: handles concurrent briefs, identity-disambiguation resilience, audit trails, integration with Cloris UI surfaces, Stop/Resume/Repair support, telemetry.

## 15. Failure modes and edge cases

Specific failure modes for this module and how the system handles them:

- Source API outage / rate limit exhaustion.
- Identity ambiguity beyond automatic resolution.
- Source-specific data quality issues (stale affiliations, common-name collisions, etc.).
- Compliance edge cases (export control, ToS posture, ITAR for Defense).

Each failure mode lists: the trigger, the user-visible symptom, and the system response.

## 16. Open questions

Questions to resolve before implementation or early in it. A `?` here is a red flag if the module is marked `ready-to-implement`.

## 17. Decisions captured here

Append-only list of decisions made during spec authoring. Each entry: `YYYY-MM-DD — <decision> — <why>`.

---

## Notes on using this template

- **Section length.** Most sections are 1-3 paragraphs. Section 5 (data foundation) is typically the longest and may need subsection headers per source. Section 7 (evaluation pipeline mapping) and 12 (build effort) are typically the most rigorous.
- **Cross-referencing.** Cite `Cloris-Architecture-North-Star.md`, `Cloris-Module-Strategy.md`, `docs/cloris-module-integration-contract.md`, `docs/cloris-brief-multi-module-extensions.md`, and `docs/cloris-cross-module-identity-resolution-spec.md` rather than restating their content.
- **Voice.** Direct, prescriptive, file:line citations where the code is the authority. Match the voice of `docs/cloris-ui-spec.md` and `docs/cloris-control-plane-spec.md`. No marketing language.
- **Living document.** Module specs are re-versioned as the module's strategy or implementation evolves. Specs in `Status: shipped` reflect the as-built module; specs in `Status: ready-to-implement` reflect the design before build.
