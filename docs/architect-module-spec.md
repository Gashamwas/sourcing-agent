# Architect Module Spec

Status: draft
Owner: Sam
Last updated: 2026-04-30

The Architect module discovers architects, interior architects, and architectural designers with portfolio depth in built work, conceptual studio work, or hospitality / commercial / residential specialization. Cloris evaluates portfolios (renderings, plans, photography of built work) against a brief-encoded architectural rubric using multimodal-LLM evaluation, with the recruiter remaining the arbiter under HITL framing.

Stub spec per `Cloris-Multimodality-Thesis.md` §3 (Tier 1). Promotion to ready-to-implement is gated on Designer Phase 2 commercial validation. Architectural primitives reuse Designer's with architecture-specific rubric content swapped in.

## 1. Target population

Architects and interior architects with documented portfolios of built or conceptual work, 5+ years professional experience post-licensure / post-graduation. Specifically:

- Project architects at recognized firms with documented role in built work.
- Senior designers / associates at boutique studios with conceptual + built portfolio depth.
- Interior architects with hospitality / retail / commercial specialization.
- Specialized practice architects (healthcare, education, mass-timber, performance / acoustic).
- Director-level hires (associate principals, design directors) for senior roles.

Excluded from v1: licensed architects without portfolio infrastructure (some practice architects don't maintain personal portfolios; firm-website inclusion only); urban planners / landscape architects (different evaluation criteria); pure 3D-rendering specialists who are not architects (overlap with Motion / 3D module).

## 2. Buyer persona

- Large architecture firms doing in-house design hiring (Gensler, HOK, SOM, Perkins+Will, AECOM, Skidmore Owings & Merrill, Foster + Partners, etc.).
- Boutique studios building teams (Studio Gang, BIG, MAD, Diller Scofidio + Renfro, Olson Kundig, etc.).
- Real estate developers' in-house design teams (Related, Tishman, Hines).
- Hospitality groups hiring in-house interior architects (Marriott / Hyatt / IHG luxury divisions).
- Architectural recruiting consultancies (boutique market, smaller than design or engineering recruiting).

Pricing tier per `Cloris-Product-North-Star.md` §4.6 — likely lower-mid range; architecture firms have tight per-recruiter spending compared to tech.

## 3. Differentiation thesis

Same architectural pattern. Multimodal-LLM evaluation of architectural portfolios (renderings, plans, sections, photography of built work, model photography) against rubric: spatial logic, material articulation, contextual response, structural integration, environmental thinking, programmatic clarity, drawing craft.

Architecture-recruiting tooling is dominated by job-board platforms (Archinect, AIA Career Center) and relationship-driven boutique firms. No tool runs portfolio evaluation. The pattern fits.

## 4. Strategic priority and roadmap fit

Tier 1 of `Cloris-Multimodality-Thesis.md`. Lower priority within Tier 1 because architectural recruiting buyer-pool spend is thinner than design / motion / game art. Plausibly fourth Tier 1 module to ship if Designer validates strongly and customer-pull from earlier Tier 1 disciplines doesn't fully consume Phase 3-4 capacity.

## 5. Data foundation

Pending. Candidate spine sources:

- **Archinect** — primary architecture community / portfolio platform. Profile coverage uneven but real.
- **Issuu** — portfolio-PDF distribution platform; many architects publish portfolios here.
- **Personal portfolio sites** via Google CSE filtered to architecture portfolio hosts.
- **Firm websites** — many architects' best documentation is on the firm's own website (project pages with credited team).
- **AIA / RIBA membership directories** — credentialing data.
- **LinkedIn** — broad coverage of senior architects.

Built-work documentation is more public than concept-stage work; portfolio depth varies wildly by firm-tier and individual practice.

## 6. Source-specific brief calibration

Pending. Likely additions:

- Software / drawing stack (Revit / Rhino / AutoCAD / SketchUp / Grasshopper).
- Specialization (residential / commercial / hospitality / institutional / mixed-use).
- Materials / structural specialization (mass timber / concrete / steel-fabrication-led).
- Career trajectory (firm-tier progression; project-credit progression from team-member to project-architect to lead).

Default rubric principles draft:

- Spatial logic (legibility of spatial sequence, programmatic resolution)
- Material articulation (depth of material thinking, detailing craft)
- Contextual response (site / urban / cultural context handling)
- Structural / system integration
- Environmental thinking (passive design, sustainability literacy)
- Drawing / representation craft
- Range across project types

## 7. Evaluation pipeline mapping

Pending — pattern-mirrors Designer with architecture-specific image acquisition (renderings + plans + photographs).

## 8. State machine fit

No new lifecycle states. New work-unit kind: `ARCHITECT_PORTFOLIO_QUERY_KIND`.

## 9. Identity disambiguation

Pending. Archinect username, AIA member ID, name + firm credits, name + project credits.

## 10. Reconciliation strategy

Architect ↔ LinkedIn — most senior architects are LinkedIn-active.

## 11. Save destination

Standard: `["candidate_workspace"]`. HITL visual review surface — needs to handle plans / drawings as a distinct asset type (different from photography / renderings) at the rendering layer.

## 12. Build effort estimate

~2-3 weeks with clean primitives. The multi-asset-type handling (plans + sections + renderings + built-work photography) may add ~3-5 days to image acquisition over Designer's pattern.

## 13. First-customer demonstration scope

Pending. Plausible: "Senior project architect for boutique residential studio, 7+ years, mass-timber and adaptive-reuse depth, US East Coast portfolio of built or under-construction work."

## 14. Ship-quality scope

Pending.

## 15. Failure modes and edge cases

Pending. Architecture-specific concerns:

- Team-credit ambiguity — distinguishing the candidate's role on a multi-architect project.
- Conceptual vs. built-work weighting — academic / studio work vs. licensed practice work.
- Renders authored by visualization specialists vs. architects (visualization has its own discipline).
- Public-vs-NDA project handling for recent commercial work.

## 16. Open questions

- Archinect API viability and ToS for systematic recruiting use.
- AIA / RIBA membership data access for credential verification.
- Firm-website scraping ToS posture for project-page team credit attribution.
- Plan / drawing rendering in workspace — how to display non-photographic architectural assets gracefully.

## 17. Decisions captured here

- 2026-04-30 — Stub spec created per `Cloris-Multimodality-Thesis.md`. Status: draft. Promotion gated on Designer Phase 2 validation. Lower Tier 1 priority due to thinner buyer-pool spend; revisit only if Designer + Photographer / Motion / Game Art succession produces a customer pull from the architecture vertical.
