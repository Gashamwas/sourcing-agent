# Designer HITL Module Spec

Status: ready-to-implement
Owner: Sam
Last updated: 2026-04-30

The Designer module discovers visual designers (product designers, UX/UI designers, brand designers, design system leads, motion designers) using text-based signals — tool stacks, specialization tags, project descriptions, client tier — surfaces their portfolios for human visual review, and produces rubric-decomposed vision-language-model evaluation as senior-associate-level guidance. Cloris's job is discovery, contextualization, and structured visual analysis against a brief-encoded design rubric. The recruiter's job is final visual judgment. This is the "HITL" (human-in-the-loop) framing — recruiter as arbiter, model as guidance — that distinguishes this module from both a generic Behance-discovery product and a vision-evaluation-replaces-recruiter product.

This spec follows the shape in `docs/cloris-module-template.md`. For the strategic context — including the original audit's "skip Designer" recommendation, the 2026-04-29 founder pushback that reframed it as HITL, and the 2026-04-30 reframe adding vision-evaluation as a v1 enhancement — see `Cloris-Module-Strategy.md` §2.5.

## 1. Target population

Mid-to-senior product designers (2-8 years) and senior UX designers, plus brand/visual identity designers, design system leads, and motion designers. The commercially relevant cohort:

- Product designers at design-forward consumer or B2B SaaS companies (Figma, Linear, Notion, Stripe, Square — and the mid-tier of design-aware product companies).
- Design system contributors at scale (sole or lead authors of internal design systems at recognized product companies).
- Senior UX designers with mobile product ownership (iOS/Android shipped products).
- Brand and visual identity designers with documented agency or in-house client work at recognized brands.

Excluded: junior designers without portfolio depth; pure illustration designers (different buyer); industrial product designers (different recruiting market); designers whose primary identity is on Instagram/TikTok rather than portfolio platforms (Cloris cannot index Instagram cleanly).

## 2. Buyer persona

- Product companies doing design hiring at scale.
- Design agencies building teams.
- Executive search for VP/Head of Design (the higher-tier outcome).
- In-house design teams at consumer companies and design-forward B2B.

Pricing supportable: $300-$500/seat-month for in-house teams; $15K-$30K annual for boutique design recruiting firms. Lower than the technical modules due to smaller buyer pool and higher price sensitivity.

Why these buyers cannot solve the problem with existing tools: LinkedIn search for designers surfaces too many false positives (everyone calls themselves a "designer"). Behance's own search returns chronologically-sorted projects, not designer-fit-evaluated candidates. Dribbble's API has been gutted for discovery. The category has no autonomous evaluation tool because evaluation has been conflated with visual judgment. The HITL framing — Cloris narrows the funnel; recruiter does visual judgment — is the unmet need.

## 3. Differentiation thesis

Two layers compose the differentiation. Each does work no other tool in the recruiting market runs.

**Layer 1: Text-based narrowing.** Cloris reduces the discovery funnel from "millions of designers" to "tens of designers worth visual review for this brief" using text-based evaluation:

- Tool stack as builder/user discriminator. "Figma design system authoring with constraints and variables" vs. "Figma wireframing for one-off screens" — same builder/user distinction the technical modules use, applied to design tooling. The brief encodes this via `CapabilityArea.builder_signals` and `user_signals`.
- Specialization tags from Behance taxonomy. "Product Design", "Interaction Design", "Design Systems" are real signals; "Graphic Design" is too broad.
- Client tier from project descriptions. Designer worked for Figma, Stripe, Apple, IDEO → different quality bar than designer with regional-client portfolio.
- Career trajectory from LinkedIn. Senior product designer at Linear → high-signal candidate; design generalist at unknown agencies → lower signal.

**Layer 2: Vision-language-model rubric evaluation (added 2026-04-30).** On top-N candidates that pass text-evidence evaluation, Gemini 2.5 Pro evaluates representative portfolio images against a brief-encoded design rubric. Per-principle scoring (visual hierarchy, typographic refinement, compositional balance, color system coherence, conceptual strength, craft execution, plus discipline-specific principles for motion / illustration / UX) plus structured rationale, surfaced in the candidate workspace as senior-associate-level guidance the recruiter reacts to during HITL review.

This second layer is genuinely novel in the recruiting tools market. Horizontal sourcing tools (HireEZ, SeekOut, Gem, Findem, Eightfold) do not run vision-language models against creative work because their architecture and GTM push them toward generic capability, not vertical depth. Specialized design platforms (Working Not Working, Dribbble Hiring, Folyo) are taste-curated by humans without VLM tooling. The structural mismatch keeps horizontal tools out of this space for 12-18 months minimum after copying starts; pure novelty has a 6-12 month window before that copying begins.

The recruiter remains the arbiter. Vision evaluation accelerates HITL review (moves the recruiter's portfolio review time from "manual taste evaluation against an internal rubric" to "react to structured rubric-decomposed analysis"); it does not replace recruiter judgment. The brief carries customer-specific taste calibration via the rubric's discipline weights, anchor definitions, and exemplar portfolios — no fine-tuning required.

## 4. Strategic priority and roadmap fit

Priority **#3** in `Cloris-Module-Strategy.md` §4. Re-sequenced 2026-04-30 from prior #7 placement; rationale captured in §2.5 of the strategy doc and §17 of this spec.

Roadmap fit: Phase 2 (June-September 2026, in parallel with Researcher v1 and OSS Maintainers Tier 2). Per `Cloris-Multi-Module-Roadmap.md`. Prerequisites:

- Candidate workspace v1 shipped (Phase 1) — required because the HITL surface relies on it.
- `target_modules` field, per-source nested calibration, save destination abstraction, calibration vertical-agnostic refactor — all Phase 1 platform prerequisites.
- Researcher v1 customer onboarding overlapping with Designer build is fine; the modules don't share the same buyer pool.

The novelty argument is load-bearing in this priority placement. VLM-driven portfolio evaluation is approximately uncontested in the recruiting tools market in 2026 ("less than 0" competing tools, per founder framing); horizontal incumbents are structurally constrained from entering for 12-18 months minimum after copying starts. The pure-novelty window (6-12 months before copying begins) is the period of maximum strategic asymmetry. The original Phase 5 placement (months 9-12) landed Designer when the novelty window was already closing.

## 5. Data foundation

### 5.1 Behance API (anchor)

API: `behance.net/v2/`. Free with developer API key. OAuth-gated user-data endpoints; public discovery endpoints for projects and users with appropriate scopes.

Coverage: ~30M designer profiles; specialization-tagged. Project metadata includes tools array, fields (specialization taxonomy), tags, country, appreciation/follower counts.

Identity quality: real names where designers choose to display them; location at country-level; portfolio URL; social links (Instagram, Twitter, personal site) when designers add them.

Rate limits: 150 req/hr free tier. Restrictive for high-volume sweeps; tractable for targeted discovery queries.

ToS: developer terms permit commercial use under standard developer agreement.

Verdict: anchor source. Verify current 2026 access policy before build kickoff.

### 5.2 LinkedIn (existing module)

LinkedIn covers senior product designers well — they list tool stacks, specializations, and portfolio URLs (Behance/Dribbble/personal sites) directly on their profiles. The Designer module integrates with LinkedIn discovery as a secondary source for candidates whose Behance presence is weak but LinkedIn presence is strong. For senior designers (Head of Design, Design Director), LinkedIn is often the better discovery surface than Behance.

The integration: a Designer-targeted brief enables LinkedIn discovery (`target_modules: ["linkedin", "designer"]`) and Cloris runs both modules. Behance findings and LinkedIn findings dedup at the cross-module identity layer.

### 5.3 Personal portfolio sites (via Google Programmable Search Engine)

Per Cloris's external research, Google CSE is the realistic foundation for discovering portfolios on Cargo, Squarespace, Format, Semplice, and personal sites. Free 100 queries/day per CSE; $5/1000 thereafter, capped at 10K/day.

The Designer module includes a Google CSE adapter that complements Behance for the long-tail of designers whose primary portfolio is on a personal site.

### 5.4 Sources considered and rejected

- **Dribbble v2 API.** Functionally gutted post-v2 — `GET /user/shots` returns only the auth'd user's own shots; no public search; no tag filter. Use only for designers who voluntarily authenticate and grant access, which is rare for sourcing. Skip as a discovery surface.
- **Read.cv / Hello.cv.** Read.cv shut down May 2025; Hello.cv is a `.cv` domain hosting service without social-network features. Not a discovery surface.
- **Cargo.site direct.** No API; use Google CSE filtered to `site:cargo.site` instead.
- **Are.na.** API is functional. Niche source for conceptual designers/researchers, not mainstream product designers. Add as a v2 enrichment source if customer signal indicates need.
- **Awwwards / SiteInspire scraping.** Credit-graph sources; useful but Cloudflare-hostile for systematic scraping. Use Google CSE filtered to these domains rather than direct scraping.
- **Instagram / X.** Rate limits and ToS make commercial sourcing unviable.

## 6. Source-specific brief calibration

**Capability area extensions** (`shared/brief_schema.py:CapabilityArea`):

- `behance_specialization_signals: list[str]` — e.g., `["Product Design", "Design Systems", "UX/UI Design"]`.
- `tool_stack_signals: list[str]` — e.g., `["Figma", "Sketch", "Principle", "Framer", "Origami Studio"]`.

**Module-level calibration** (`shared/brief_schema.py:DesignerCalibration`):

```python
@dataclass
class DesignerCalibration:
    behance_specialization_focus: list[str] = field(default_factory=list)
    tool_stack_required: list[str] = field(default_factory=list)
    portfolio_url_required: bool = True
    project_count_floor: int = 0
    appreciation_velocity_floor: int = 0  # avg appreciations per project
    require_published_clients: bool = False  # named-client signal in project descriptions
```

**Facial calibration source-specific patterns** (`FacialCalibration.sources["designer"]`):

```python
SourceCalibration(
    fast_exit_patterns=[
        "All projects are graphic-design only with no product or system work",
        "Tool stack is exclusively Photoshop / Illustrator with no Figma/Sketch",
        "Project descriptions are all hobby/concept with no shipped-product evidence",
    ],
    portfolio_yes_patterns=[
        "Project descriptions mention specific shipped products at recognized companies",
        "Tool stack includes design-system tools (Figma constraints/variables, Storybook, Tokens Studio)",
        "Specialization tags match brief target with multiple recent projects",
    ],
    portfolio_ambiguous_patterns=[
        "Strong tool stack but project descriptions are vague or client-redacted",
        "Specialization match but career stage unclear from profile alone",
    ],
    portfolio_no_patterns=[
        "Junior-level project descriptions only; no progression evident",
        "Tool stack predates current product-design industry standards",
    ],
)
```

**Design rubric (added 2026-04-30, drives the vision-evaluation layer).** The brief encodes a principle-decomposed rubric the vision evaluation pass references. Stored as `BriefDesignRubric` in `shared/brief_schema.py`:

```python
@dataclass
class RubricPrinciple:
    name: str  # e.g., "visual_hierarchy", "typographic_refinement"
    description: str  # one-line definition
    anchors: dict[str, str]  # keys: "bad", "okay", "good", "excellent"; values: 1-2 sentence definitions in concrete language
    weight: float = 1.0  # discipline-specific weight; 0.0 to skip principle for this discipline

@dataclass
class CalibrationExemplar:
    portfolio_url: str
    discipline: str  # "brand", "product", "motion", "illustration", "ux", etc.
    verdict: str  # "yes" | "no" | "borderline"
    per_principle_reasoning: dict[str, str]  # principle_name -> 1-2 sentence reasoning
    overall_reasoning: str

@dataclass
class BriefDesignRubric:
    principles: list[RubricPrinciple] = field(default_factory=list)
    discipline_weight_overrides: dict[str, dict[str, float]] = field(default_factory=dict)
    calibration_exemplars: list[CalibrationExemplar] = field(default_factory=list)
```

Default rubric (six principles) ships with the module and is overridable per-customer:

1. **Visual hierarchy** — information priority, primary/secondary/tertiary distinction, scanability.
2. **Typographic refinement** — type pairing, scale system, weight discipline, kerning/leading/tracking precision, hierarchy through type.
3. **Compositional balance** — spatial relationships, grid systems, negative space, alignment, optical balance.
4. **Color system coherence** — palette discipline, color story, accessibility, restraint, distinctiveness.
5. **Conceptual strength** — does the design solve the brief problem; originality vs. competent execution of established patterns.
6. **Craft execution** — pixel-level precision, attention to detail, polish, consistency across surfaces.

Discipline-specific extensions (weight other principles or add new ones):

- *Motion designers*: timing/pacing, kinetic typography, easing curves. Hierarchy weighted lower; typographic refinement weighted lower.
- *Illustration*: line quality, shape language, narrative clarity, character / world consistency. Conceptual strength weighted higher.
- *UX*: interaction model clarity, state coverage, accessibility-first thinking. Visual polish weighted lower (process artifacts over polished comps).
- *Brand*: conceptual strength weighted higher; system coherence across applications added as a principle.

Calibration exemplars (3-5 per discipline) ship as defaults and are overridden per-customer during brief authoring. Each exemplar has a portfolio URL, discipline tag, yes/no/borderline verdict, per-principle reasoning, and overall reasoning. The vision evaluation pass references these in its prompt as taste-anchoring examples — the rubric anchors define what bad/okay/good/excellent look like in the abstract; the calibration exemplars instantiate the customer's actual taste against real portfolios.

The rubric is the per-customer taste calibration mechanism that lets a single off-the-shelf VLM (Gemini 2.5 Pro) approximate per-customer taste without fine-tuning. It compounds with the existing brief authoring methodology rather than replacing it.

Pre-built brief templates (`config/brief-templates/designer/`):

- `senior-product-designer-saas.json`
- `design-system-lead.json`
- `senior-ux-mobile-product.json`
- `head-of-design-growth-stage.json`
- `brand-designer-agency.json`
- `motion-designer-marketing.json` (added 2026-04-30 to support entertainment-industry-relevant briefs)
- `art-director-campaign.json` (added 2026-04-30 to support entertainment-industry-relevant briefs)

Each template ships with default rubric principles, discipline-specific weights, and 3-5 calibration exemplars curated for the role archetype.

## 7. Evaluation pipeline mapping

**Snippet evidence** (text-based, light). Designer summary:

```
Name: Jane Doe
Behance: behance.net/janedoe (2,400 followers; 18 published projects)
Specialization tags: Product Design, UX/UI Design, Design Systems
Tool stack (self-reported): Figma, Principle, Storybook, Tokens Studio
Location: New York, NY (USA)
Top 3 projects:
  - "Linear redesign concept" (Product Design; 380 appreciations; 2024)
  - "Notion design system audit" (Design Systems; 220 appreciations; 2024)
  - "Stripe checkout interaction study" (Interaction Design; 150 appreciations; 2023)
Portfolio URL: cargo.site/janedoe
LinkedIn (when matched): Senior Product Designer at Linear, 2022-present
```

**Full evidence** (text-based, deep). All published Behance project descriptions, complete tool stack, location, social links, optional Google CSE-discovered personal portfolio site content, LinkedIn integration when matched.

**Vision-evaluation pass** (added 2026-04-30, top-N candidates only). For candidates that pass full text-evidence evaluation, the module runs a vision-evaluation pass against the brief-encoded design rubric.

- Image acquisition: up to 8 representative images per candidate. Sources: Behance project image arrays (the project metadata returned by `/v2/projects/{id}` includes module image URLs at multiple resolutions); Google CSE thumbnail metadata for personal portfolio sites; direct fetches from Cargo/Squarespace/Format/Semplice where ToS permits. Selection priority: most recent project's hero images > top-appreciation projects' hero images > project images explicitly tagged as showcase work.
- Vision model: Gemini 2.5 Pro (per `~/.claude/projects/-Users-sam-vangelos-Projects-recruiting-tools-sourcing-agent/memory/feedback_frontier_models_over_cost.md` — frontier reliability prioritized over marginal cost savings; per-customer monthly inference at this volume is ~$10-30, not breaking unit economics).
- Prompt structure: rubric principles (with anchors) + brief calibration exemplars + 8 candidate images + structured-output schema requesting per-principle 0-3 score + 1-2 sentence reasoning per principle + overall verdict + confidence. Reasoning is written in the voice of a senior design director critiquing a portfolio review — substantive, specific, principle-grounded.
- Cost: ~$0.02-0.10 per candidate at expected token volumes (varies with image count and model pricing). Recurring per-evaluation cost capped via image-count limit and resolution selection.
- Fallback: if vision-evaluation pass fails (image acquisition failed, model rate-limited, output failed parser), the candidate still proceeds to HITL review with text-only contextualization. Vision evaluation is an enhancement, not a blocker.

**Contextualization output** (instead of standard SAVE rationale). For HITL surface:

```
Specialization summary: Product designer with explicit design-system depth, currently at Linear. Tool stack and project descriptions match brief target.
Tool depth: Figma (constraints/variables/tokens explicit), Storybook integration, design-token authoring evidence.
Notable projects: Linear product redesign concept (apparent personal project, not Linear-paid); Notion design system audit (paid client); Stripe checkout study (concept).
Client tier: at Linear currently; prior Stripe and Notion client work in concept format.
Portfolio URL for review: cargo.site/janedoe

Visual evaluation (Gemini 2.5 Pro, against brief rubric):
- Visual hierarchy: 3/3 — Strong information priority across projects; clear primary/secondary distinction in the Notion audit and Stripe study.
- Typographic refinement: 2/3 — Type pairings are competent and consistent; kerning shows attention but not the precision of awarded brand work.
- Compositional balance: 3/3 — Confident use of negative space; clear grid systems in product work.
- Color system coherence: 2/3 — Restrained palette use; color stories well-controlled but not particularly distinctive.
- Conceptual strength: 2/3 — Solves stated brief problems; less evident original synthesis vs. execution of established patterns.
- Craft execution: 3/3 — Pixel-level precision evident throughout; no rough edges in interaction details.
Overall: high-craft product designer with design-system depth; conceptual originality is the area to probe in interview. Confidence: high.
```

**Decision contract.** `SAVE` decisions are mapped to `surface_type = "hitl_visual_review"` in the workspace entry's terminal payload. The recruiter's review action in the workspace is the actual save/reject decision (not Cloris's). The decision pipeline records the SAVE → recruiter-confirmed, SAVE → recruiter-rejected, or SAVE → recruiter-borderline transition via the `workspace_review_events` mechanism per `docs/cloris-candidate-workspace-spec.md` §3.2.

The vision-evaluation output is presented inline with the contextualization output as editorial guidance the recruiter reacts to. It is not a vote that overrides recruiter judgment; the workspace UI surfaces it as senior-associate commentary, not as a Cloris-side save/reject signal.

`REJECT` decisions remain Cloris-decided when text signals clearly indicate non-fit (e.g., wrong specialization, missing tool stack).

`INFERENTIAL_SAVE` for sparse-profile candidates with strong client-tier or LinkedIn signal but thin Behance presence.

## 8. State machine fit

Existing lifecycle. Work-unit kind: `DESIGNER_BEHANCE_QUERY_KIND = "designer_behance_query"` for Behance-driven discovery; existing `LINKEDIN_STRING_KIND` for LinkedIn-driven discovery on multi-module designer briefs.

The HITL semantics do not require new lifecycle states. The candidate reaches `full_terminal` with terminal_decision `SAVE` and surface_type `hitl_visual_review`; the recruiter's confirmation/rejection is a workspace action, not a state-machine transition.

## 9. Identity disambiguation

Behance usernames are unique within Behance; LinkedIn URLs are unique within LinkedIn. Cross-source matching uses portfolio URL (when LinkedIn lists Behance link) or name + location. Common-name handling within Behance is rare due to Behance's smaller designer cohort vs. global researcher cohort.

Multiple Behance accounts for the same person (personal vs. professional) handled at reconciliation time via portfolio URL cross-reference.

## 10. Reconciliation strategy

Designer candidates reconcile to LinkedIn via `designer/recruiter_identity_resolver.py` plus `shared/cross_module_identity/designer_to_linkedin.py`.

Resolution methods:

1. `behance_url_in_linkedin_profile` (confidence 0.95-1.0).
2. `portfolio_url_match` (confidence 0.85-0.95).
3. `name_plus_company_plus_specialization_match` (confidence 0.65-0.8).

Designers without LinkedIn (some indie designers, some students, some privacy-aware designers) stay per-source. Recruiter outreaches via Behance message or portfolio-site contact form.

## 11. Save destination

Standard: `["candidate_workspace"]`. The workspace's `surface_type = "hitl_visual_review"` rendering displays:

- Portfolio URL prominently (as a primary action button).
- Specialization summary, tool depth, notable projects (the contextualization output).
- **Visual evaluation block** (added 2026-04-30): per-principle scoring + reasoning from the vision-evaluation pass, rendered as editorial commentary alongside the portfolio URL. Visually distinct from the text-based contextualization (lighter border / subtle background tint) so the recruiter can tell at a glance which signal is which. Falls through gracefully when vision-evaluation pass produced no output (display only the text-based contextualization).
- "Pending Visual Review" status indicator per `docs/cloris-ui-spec.md:267-268`.
- Recruiter actions: "Confirm after review", "Reject after review", "Borderline", "Open portfolio".
- Optional recruiter feedback marker on the vision-evaluation block: "Useful guidance" / "Wrong / shallow" / "Off-rubric." Captured into the brief's calibration feedback for future-run rubric refinement.

Outreach generation at `designer/outreach.py`. Outreach copy references specific projects from the candidate's Behance, suggests a portfolio call, signals the role's design-craft expectations. Vision-evaluation per-principle observations are NOT included in outreach copy directly (would feel parasocial / surveillance-y to the candidate); the recruiter chooses which observations to humanize into outreach naturally.

## 12. Build effort estimate

Total: **5-6 weeks** at split-attention pace. Updated 2026-04-30 to include vision-evaluation pass.

Text-based pipeline (per the 2026-04-29 baseline):

- Behance API client at `designer/sources/behance.py`: 5 days.
- Google CSE adapter at `designer/sources/google_cse.py`: 3 days. Filters to portfolio-host domains.
- `designer/strategy.py`: 3 days.
- `designer/judgment_templates.py` with contextualization-output prompt variant: 4 days. The prompt explicitly produces structured context rather than SAVE/REJECT rationale.
- Brief schema additions (`DesignerCalibration`, capability-area extensions, facial calibration source patterns): 1 day.
- Pre-built brief templates: 2 days (5 templates × ~half-day each).
- HITL workspace surface integration (`surface_type = "hitl_visual_review"` rendering): 3 days. New visual treatment in candidate workspace.
- `designer/recruiter_identity_resolver.py`: 2 days.
- Tests for text-based pipeline: 3 days.

Vision-evaluation pass (added 2026-04-30):

- `BriefDesignRubric` schema additions (`RubricPrinciple`, `CalibrationExemplar`, `BriefDesignRubric` dataclasses) plus `shared/brief_loader.py` hydration: 1 day.
- Default rubric authoring (6 principles × 4 anchor levels × concrete-language definitions; discipline-specific weight overrides for motion / illustration / UX / brand): 3 days. **Editorial work, not engineering — Sam-authored, ideally with a designer collaborator's review.**
- 3-5 calibration exemplar portfolios per discipline, hand-evaluated with structured per-principle reasoning, shipped as defaults: 3 days. Editorial.
- Image acquisition layer (`designer/image_acquisition.py`): Behance project image URL extraction, Google CSE thumbnail URL extraction, optional direct fetch from personal sites with ToS check, image-count and resolution selection logic: 3 days.
- `designer/vision_evaluation.py`: Gemini 2.5 Pro client, rubric-loaded prompt templating, structured output schema, per-principle parser, fallback handling: 3 days.
- Workspace surface rendering for vision-evaluation block (per-principle scoring layout, editorial commentary, recruiter feedback markers): 2 days.
- Tests for vision-evaluation pipeline: 2 days.

Total: ~40 person-days = ~5-6 calendar weeks at split-attention pace.

Two of the longer line items are editorial (default rubric authoring + calibration exemplars), not engineering. They can run in parallel with engineering work where Sam's hours are split between rubric-authoring evenings and engineering work during peak hours.

## 13. First-customer demonstration scope

Demo brief: "Senior product designer with explicit design-system experience for a Series-B B2B SaaS in product analytics. 4-7 years experience, design-system tools (Figma constraints/variables/tokens, Storybook), shipped product evidence at recognized SaaS or consumer companies, US East Coast or remote-US."

What the module produces: Behance discovery surfaces ~80-200 candidates matching specialization + tool stack; LinkedIn discovery surfaces ~50-150 candidates matching capability-area calibration; cross-source dedup produces ~100-200 unified candidates. Facial triage narrows to ~30-60. Full evaluation produces ~15-30 saves, all flagged `hitl_visual_review`. Vision-evaluation pass runs on the top ~15-30 saves, producing per-principle rubric scoring + reasoning. Recruiter reviews each portfolio URL alongside the vision-evaluation guidance in 3-7 minutes (down from 5-10 minutes for text-only contextualization, because the rubric-decomposed analysis structures the recruiter's review).

The vision-evaluation guidance is the demonstrable differentiator. A recruiter walking into a Cloris demo and seeing "here's a portfolio + Cloris's per-principle analysis of how this designer's work measures against your brief's design rubric" reacts qualitatively differently than to "here's a portfolio + Cloris's text summary of the designer's specialization tags." The first is senior-associate-level output the recruiter has never seen from a sourcing tool. The second is a slightly nicer version of what existing tools already do.

For an entertainment-industry buyer (e.g., A24-shape buyer hiring an art director or motion designer for marketing campaigns), the demo brief shifts to that role archetype, the rubric weights shift to motion/illustration/conceptual-strength priorities, and the calibration exemplars come from awards-validated entertainment-industry creative work (D&AD, Cannes Lions, AICP, AICE).

## 14. Ship-quality scope

Beyond the demo: Are.na enrichment for niche/conceptual-design briefs; Awwwards credit-graph integration for site-discoverable designers; live Google CSE strategy that adapts based on which CSE domains are producing signal; designer-specific outreach polish.

## 15. Failure modes and edge cases

- **Behance rate limit exhaustion.** 150/hr free tier exhausted on a high-volume run. Strategy: cache per-designer profiles; spread queries across multiple developer keys (within ToS); fall back to Google CSE when Behance is rate-limited.
- **Designer with strong Behance presence but Behance profile is private/locked.** Skip; surface to brief-author as a calibration miss.
- **Tool stack self-reporting noise.** Some designers list every tool they've ever opened, regardless of depth. Strategy: cross-reference tool list against project description language; designers who mention specific tool features in projects (e.g., "used Figma variables for theme switching") have deeper tool depth than designers who just list "Figma" without project context.
- **Misaligned client tier signal.** A designer's project says "Stripe checkout study" but it was a personal exploration, not Stripe-paid client work. Strategy: the contextualization output flags concept-vs-paid distinction explicitly; recruiter judges from the visual review.
- **Adobe restricting Behance access mid-build.** Adobe has progressively restricted public APIs. Mitigation: track Behance API access status as part of customer-launch readiness; have Google CSE fallback ready.

## 16. Open questions

- **Vision-evaluation prompt iteration cycles.** Default rubric and prompt structure ship with the module. Open: how many customer-driven iteration cycles are needed before vision evaluation produces consistently useful guidance for a given customer's taste? Probably 2-3 cycles in initial onboarding, but unverified until first customer. Worth tracking explicitly: the recruiter feedback marker on the vision-evaluation block ("Useful" / "Wrong / shallow" / "Off-rubric") feeds this.
- **Discipline coverage scope at v1.** Default rubric covers product / brand / motion / illustration / UX. Entertainment-industry-specific disciplines (production design, key-art-specific brand, title-sequence motion) might warrant their own rubric variants. Defer specific entertainment-industry rubric authoring until first entertainment-industry customer.
- **Image acquisition reliability across sources.** Behance image arrays are clean (returned by API). Google CSE thumbnails are reliable but lower-resolution. Personal-site direct fetch varies wildly by site implementation and ToS. Failure rate estimate: 5-15% of candidates return insufficient images for vision-evaluation pass. Acceptable at launch; monitor and improve based on telemetry.
- **Dribbble re-integration if their API recovers.** Currently impossible; if Dribbble reopens public discovery in 2026/2027, add as a v2 source.
- **Personal-site crawler for portfolio depth.** Beyond CSE-driven discovery, an actual crawler that fetches portfolio sites and extracts project metadata. Adds engineering and infrastructure cost; defer until customer signal indicates need.
- **Behance API access stability under Adobe ownership.** Adobe has progressively restricted public APIs. Mitigation: Google CSE fallback ready; cache Behance profiles aggressively. Verify access policy at build time and re-verify quarterly.

## 17. Decisions captured here

- 2026-04-29 — Designer is a HITL module: Cloris discovers and contextualizes; recruiter does visual judgment. *Updated 2026-04-30: vision-evaluation enhancement added on top of HITL framing; recruiter remains arbiter.*
- 2026-04-29 — Behance + LinkedIn + Google CSE are the v1 data foundation. Dribbble, Read.cv, Instagram explicitly excluded.
- 2026-04-29 — `surface_type = "hitl_visual_review"` reuses existing `SAVE` decision plumbing; no new decision types invented.
- 2026-04-29 — Designer ships in Phase 5 after candidate workspace and Researcher/OSS Maintainers commercial validation. *Superseded 2026-04-30; see below.*
- 2026-04-29 — V1 build target is 4-5 calendar weeks at split-attention pace. *Updated 2026-04-30 to 5-6 weeks to incorporate vision-evaluation pass.*
- **2026-04-30 — Vision-evaluation pass added as v1 enhancement to HITL.** Trigger: empirical confirmation that Gemini 2.5 Pro produces materially useful design analysis at recruiter-tool volume cost (~$10-30/customer/month). HITL preserved — recruiter remains arbiter of save/reject; vision provides senior-associate-level rubric-decomposed guidance the recruiter reacts to. Architectural thesis: brief-encoded design rubric carries customer-specific taste; off-the-shelf VLM applies it; no fine-tuning required.
- **2026-04-30 — Default vision model: Gemini 2.5 Pro.** Open-weight alternatives (Qwen2.5-VL, Llama vision variants) explicitly rejected for this module per `~/.claude/projects/-Users-sam-vangelos-Projects-recruiting-tools-sourcing-agent/memory/feedback_frontier_models_over_cost.md` — frontier reliability and quality at recruiter-tool volume outweigh marginal cost savings.
- **2026-04-30 — Designer re-sequenced from Phase 5 to Phase 2.** Per `Cloris-Multi-Module-Roadmap.md` updates. Rationale: VLM-driven portfolio evaluation is uncontested in the recruiting tools market in 2026 ("less than 0" competing tools); structural reasons keep horizontal incumbents out for 12-18 months minimum after copying starts; pure novelty has a 6-12 month window; original Phase 5 placement landed Designer when novelty window was already closing.
- **2026-04-30 — Brief design rubric is the per-customer taste calibration mechanism.** No fine-tuning. The `BriefDesignRubric` dataclass (principles, anchors, discipline weight overrides, calibration exemplars) is the asset; the model is a swappable backend.
- **2026-04-30 — Customer-asking-as-gate is the wrong gate for this module.** Pre-build customer interviews for category-creating products are weak signals because customers cannot articulate within frames they haven't seen (no recruiter is going to say "I want vision-model portfolio evaluation against a brief-encoded rubric" before they see one). The right gate is post-demo reactions and revenue, not pre-build asking. Encoded in the strategic-priority placement and roadmap re-sequencing.
