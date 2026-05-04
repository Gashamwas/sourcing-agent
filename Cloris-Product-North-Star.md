# Cloris Product North Star

Status: living
Owner: Sam
Last updated: 2026-04-30

This document defines what Cloris is, who it is for, what it commits to, and what it explicitly will not become. It is the strategic spine for every other document in the Cloris north-star suite. Implementation specs and roadmaps inherit their priorities from here.

For implementation-facing UX rules see `docs/cloris-ui-spec.md`. For runtime/control-plane semantics see `docs/cloris-control-plane-spec.md`. For the architectural invariants this product depends on see `Cloris-Architecture-North-Star.md`. For the modular extension strategy see `Cloris-Module-Strategy.md`. For the multimodality module-category thesis (creative-work modules with multimodal-LLM evaluation, hypothesis territory contingent on Designer module validation) see `Cloris-Multimodality-Thesis.md`.

## 1. Product thesis

Cloris is an evidence-grounded autonomous sourcing platform.

The product thesis is a single sentence: **Cloris does the boring part of sourcing in the background so the recruiter can do the judgment part.** The thesis is taken verbatim from `docs/cloris-ui-spec.md:14-16` and is non-negotiable. Every product decision in this suite either reinforces that thesis or is rejected.

Three commitments follow from the thesis and bind every surface of the product:

- One agent with specialized surfaces, one shared data layer, one closed loop. Every Cloris UI surface (`docs/cloris-ui-spec.md:163-251`) reads from and writes to the same substrate. There is no parallel state, no hidden derived store, no "in this surface only" data.
- The boring operational work runs in the background. The recruiter is not asked to supervise Cloris. The default emotional tone is calm, not vigilant. The live monitor exists but is not the home (`docs/cloris-ui-spec.md:339-350`).
- The judgment work goes back to humans. Cloris's role is to surface candidates with the evidence and rationale a recruiter needs to decide; the human decides. This is not a softening of autonomy — it is the autonomy contract. Cloris is autonomous about *finding and evaluating*; recruiters are autonomous about *acting*.

## 2. What Cloris is

Cloris is a local desktop product (`pywebview` + FastAPI + Svelte + detached Python worker) that runs autonomous sourcing against one or more discovery surfaces, evaluates discovered candidates against a structured brief using a calibrated judgment pipeline, and reconciles the resulting saves into a single recruiter-actionable workspace.

The components that make Cloris what it is:

- **Briefs as the role contract.** A V2 brief (`shared/brief_schema.py:179-260`) is the single source of truth for what a role is. Capability areas, depth distinction, non-fit patterns, employer signal rules, calibration vocabulary — all of it lives in the brief, not in code. Swapping roles means swapping briefs.
- **A calibrated evaluation pipeline.** The four-step structural template (capability mapping → depth test → transferability → decision) is paradigm-neutral. It applies to LinkedIn snippets today and will apply to publication records, patent abstracts, and portfolio context tomorrow without structural change. The substrate is in `shared/judger.py` and per-source `judgment_templates.py` files.
- **A canonical runtime substrate.** `runtime_state.sqlite3` per state directory is the durable source of truth (`shared/runtime_state/store.py:73-243`). Stage JSONLs and progress files are projections, not control state (`Sourcing-Agent-2nd-Gen-Roadmap.md:381-393`).
- **Multi-source discovery feeding a single reconciliation surface.** Each discovery module (LinkedIn, GitHub, Researcher, etc.) produces leads. Reconciliation aggregates leads into a person-first candidate workspace where the recruiter works. LinkedIn is the canonical reconciliation surface today (`GitHub-LinkedIn-Reconciliation-Source-of-Truth.md:54-83`); the saved-candidate workspace inside Cloris is the canonical reconciliation surface for tomorrow.
- **A closed feedback loop.** Recruiter feedback on saves and rejects feeds into the next brief revision (`docs/cloris-ui-spec.md:235-249`). Cloris gets better with use, not worse.

## 3. What Cloris is not

These boundaries are explicit and durable. Pressure to expand any of them should be referred back to this document.

- Cloris is not a broader recruiting OS. It is a sourcing product. ATS, calendar coordination, offer management, candidate communications, analytics dashboards — all out of scope (`docs/cloris-ui-spec.md:393-402`, `AGENTS.md:23-33`).
- Cloris is not a hosted multi-tenant SaaS in v1. It is a local desktop product. Hosted operation is not on the roadmap until at least three modules are commercially validated.
- Cloris is not a candidate database product. It does not sell access to candidate records. It surfaces candidates against a customer's brief, in the customer's local environment.
- Cloris is not an outreach automation product. Outreach copy generation exists as a side-effect convenience (`github/outreach.py`); sequenced outreach campaigns, automated email sending, drip campaigns — not the product.
- Cloris does not sell evaluation as a service. The evaluation pipeline is internal to the sourcing loop. There is no "judge this candidate" API for external use.

## 4. Buyer personas

Cloris addresses concentrated, high-spend recruiting buyer markets where (a) discovery is genuinely constrained, (b) evaluation depth justifies premium pricing, and (c) the customer is willing to operate a local desktop product.

The buyer personas, in commercial order:

**4.1 Frontier AI labs and AI-native companies hiring researchers and senior engineers.**
The dominant buyer for the Researcher and OSS Maintainers modules. ~30-50 named labs and growth-stage AI companies, each willing to pay enterprise rates ($50K-$200K+/seat-year) because the talent constraint dominates their hiring economics. Specific examples (not exhaustive): Anthropic, OpenAI, Google DeepMind, Meta, xAI, Mistral, Cohere, Inflection, Adept, Reka, Magic, Imbue, Sakana, Together, Modal, Anyscale, Cresta, plus the cluster of DevTool and infrastructure companies hiring from the same cohort (Vercel, Replit, Convex, Linear, Cloudflare, Fly.io, Supabase, Neon).

**4.2 AI-focused executive search firms.**
Daversa, Riviera Partners, ZRG's AI practice, Heidrick & Struggles's AI practice, True Search's AI practice, plus boutique AI search firms. Buyers of the Researcher module and the Exec Search workflow mode. Premium per-search pricing ($300-600 supplemental on placement work; $40K-$120K firm-level annual licenses).

**4.3 Boutique technical recruiting firms.**
Specialized firms doing deep work in narrow technical verticals (defense engineering, biotech computational science, infrastructure systems). Smaller buyer pool (~30-80 firms per vertical) but each willing to pay $20K-$60K annual for tooling that materially improves their placement velocity.

**4.4 In-house technical talent teams at growth-stage and frontier-grade companies.**
Companies hiring 10+ specialized technical roles per year where existing recruiter-tooling stacks fail at the discovery layer. Mid-tier pricing ($1.5K-$4K/seat-month).

**4.5 Defense recruiting firms and defense primes.**
The Defense module's buyer pool. Slow sales cycles (12+ months), security-review-heavy procurement, but enterprise-grade contracts when they close.

**4.6 Creative-work hiring buyers (Designer module + multimodality thesis territory).**
Boutique design recruiting consultancies (Authentic Form & Function, Studio of the Future, Adam Morgan, Major Players, Working Not Working, Folyo, Represent), creative-staffing firms with heavy design exposure (Aquent / Vitamin T, Creative Circle, 24 Seven Talent, Onward Search, The Creative Group), in-house design / creative teams at design-forward consumer companies, design-aesthetic-led entertainment / media operations (A24-shape buyers), agency / studio / publisher creative departments. Pricing tier $300-$500/seat-month for in-house teams; $15K-$30K annual for boutique recruiting firms. Smaller per-buyer willingness-to-pay than the technical modules; offset by genuine novelty (no horizontal sourcing tool runs multimodal-LLM evaluation against creative work product) and category breadth if `Cloris-Multimodality-Thesis.md` advances past Phase 2 validation.

What is *not* a Cloris buyer:

- Generalist staffing firms operating at high volume across roles. The product is calibrated for depth, not throughput.
- High-volume entry-level recruiting (early-career, hourly, gig). Wrong evaluation paradigm.
- Sales recruiting as a primary use case (covered as a LinkedIn workflow configuration, not as a flagship offering — see `docs/sales-leadership-workflow-spec.md` and `Cloris-Module-Strategy.md`).

## 5. Modules as discovery layers, not parallel products

A defining commitment of Cloris's product architecture: **modules are discovery surfaces feeding a single reconciliation workspace, not parallel sourcing products with their own save destinations.**

The reconciliation contract is set in `GitHub-LinkedIn-Reconciliation-Source-of-Truth.md`: "GitHub sourcing is an upstream screening stage, not the full hiring loop... The canonical fit standard for reconciliation is the LinkedIn brief." The same logic generalizes. Researcher findings reconcile into the candidate workspace. OSS Maintainer findings reconcile into the candidate workspace. Patent inventor findings reconcile into the candidate workspace.

The implication: Cloris is not "Cloris for LinkedIn + Cloris for GitHub + Cloris for Researchers + ..." It is one product whose surface area widens as new discovery surfaces are added. The recruiter authors a brief, selects which discovery surfaces to run, and reviews aggregated candidates in the workspace. The complexity of multi-module discovery is hidden inside the platform; the user-facing surface stays unified.

This commitment forecloses some superficially attractive product directions:

- Cloris does not sell "Researcher only" as a separate product SKU. Researcher is a module of Cloris.
- Cloris does not allow modules to define their own save destinations outside the workspace. Save lands in one place.
- Cloris does not maintain parallel candidate databases per module. The candidate workspace is per-brief and cross-module.

## 6. Evaluation as the durable substrate

The single most important strategic asset Cloris has built is the calibrated evaluation pipeline. It is more important than any single module.

The four-step structural procedure — capability mapping, depth test, transferability test, decision — is encoded in `linkedin/judgment_templates.py` and reused as the structural template for every source-specific judgment template. The brief schema (`shared/brief_schema.py`) carries the role-specific calibration vocabulary that the procedure consumes. The vertical-agnostic refactor (`plans/calibration-layer-vertical-agnostic.md`) is moving the last AI-vocabulary leakage out of code so the substrate works cleanly across verticals.

Why this is the durable asset, and not the data acquisition surface:

- Data acquisition surfaces are commodified or commoditizing. OpenAlex is CC0. PubMed is government data. USPTO PatentSearch is free. GitHub's API is public. The proprietary asset is not "we have data others don't" — the data is open. The proprietary asset is "we evaluate that data the way an experienced recruiter would, calibrated to your role, at scale."
- Evaluation quality compounds with feedback. Discovery quality plateaus once your data sources are good; evaluation quality continues to improve as recruiters tell Cloris what was a good save and what was a miss (`docs/cloris-ui-spec.md:235-249`, `shared/brief_iteration.py`). This is the only source of long-term commercial defensibility in the product.
- Brief calibration is the work the customer cannot easily replicate. A frontier lab can pay an engineer to write a Semantic Scholar query. They cannot easily build the calibrated brief that distinguishes "research scientist who builds" from "applied ML practitioner who consumes research." That calibration takes recruiter judgment, evaluation feedback loops, and a working substrate. Cloris owns the substrate.

The substrate extends naturally to multimodal evaluation (vision, video, audio) against rubric-encoded brief calibration. The 2026-04-30 reframe of the Designer module ships this as v1 — Gemini 2.5 Pro evaluates portfolio images against a brief-encoded design rubric, with the recruiter remaining the arbiter under HITL framing. The multimodal extension is not a separate substrate; it is the same calibrated-evaluation pipeline applied to non-textual evidence. See `docs/designer-hitl-module-spec.md` for the proof-of-concept, `Cloris-Multimodality-Thesis.md` for the broader category implications across creative-work hiring.

The product's commercial pitch is not "we have data" or "we have AI." It is: "we evaluate candidate evidence against your role with the discipline of a senior recruiter and the breadth of an autonomous platform." Every module reinforces or weakens that pitch. Multimodal-creative modules reinforce it by extending evaluation depth into work product that no other tool evaluates.

## 7. Commercial positioning

Cloris is positioned as a premium specialist tool, not a generalist sourcing platform.

- **Pricing tier:** $1.5K-$4K/seat-month for in-house technical teams; $300-$500/seat-month for in-house creative-work teams; $20K-$60K annual for boutique recruiting firms; $50K-$200K+ annual for enterprise (frontier labs, large recruiting firms, defense primes). The platform is not designed to compete on price with $80-$200/seat-month tools (Otta, Workable, Hire.io). It competes on evaluation quality and on access to populations those tools cannot find.
- **Sales motion:** founder-led, customer-development-first. Specifically not self-serve PLG in v1. Each customer is onboarded with brief-authoring assistance.
- **Differentiation surface (always lead with this):** "Cloris evaluates candidate evidence against your structured role definition. It will not surface someone who looks adjacent and isn't, and it will surface people whose profile understates their actual depth — both of which generic search tools fail at."
- **Second face for creative-work hiring conversations** (contingent on `Cloris-Multimodality-Thesis.md` advancing past Phase 2 validation): "Cloris runs multimodal evaluation against creative work product — portfolios, reels, audio samples — calibrated to your taste via the brief. No other recruiting tool does this. The recruiter is still the arbiter; the model is the senior associate doing the structured first pass." Lead with this in Designer / Photographer / Motion / future-creative-module conversations once those modules ship. Do not lead with this in Researcher / OSS Maintainers / technical-recruiting conversations — wrong category for those buyers.
- **Anti-positioning:** Cloris is not "AI-powered sourcing" or "the LinkedIn killer" or "ATS for the modern recruiter" or "AI for creatives." Avoid that vocabulary entirely. It signals the wrong category and attracts the wrong buyers. The multimodality work is incidental infrastructure to the proposition, not the proposition itself; the proposition remains depth-evaluation against a customer-calibrated brief.

## 8. Voice and brand commitments

Cloris's voice and visual system are documented in `docs/cloris-ui-spec.md` (sections 4-5, 8). They are non-negotiable and apply across product, marketing, and customer-facing communication.

The commitments that bind product decisions:

- Editorial, not dashboard. Cloris does not look like SaaS chrome (`docs/cloris-ui-spec.md:96-120`).
- The user-facing voice is sparse and exists at transitions, not inside focused work. High-stakes states drop the voice entirely (`docs/cloris-ui-spec.md:107-128`).
- Cloris is a person, not a product mascot. The voice is "let me find my glasses," not "don't forget to take a break, dear" (`docs/cloris-ui-spec.md:99-104`).
- Status messages and error copy are part of the design system. Every empty state, error, and transition gets the same care as the visual surface.

## 9. The closed loop is the product

Cloris's evaluation quality compounds only if the feedback loop closes. This is the single longest-pole product investment.

The loop:

1. Brief is authored (Authoring Loop surface, `docs/cloris-ui-spec.md:163-184`).
2. Run executes against discovery modules; saves and rejects accumulate.
3. Recruiter reviews saves in the candidate workspace, marks correct/incorrect, adds feedback.
4. Feedback drives a brief revision proposal (Next Run Learning surface, `docs/cloris-ui-spec.md:235-249`).
5. Recruiter approves the revision; next run uses the revised brief.

Without the loop, Cloris is a one-shot discovery tool whose evaluation quality is fixed at brief-authoring time. With the loop, evaluation quality improves over weeks of use until Cloris is materially better at the role than a senior recruiter could be in week one. The loop is the long-term moat.

The infrastructure prerequisites for the loop (per `docs/cloris-ui-spec.md:386-391`):

- A first-class feedback artifact table in `runtime_state.sqlite3`.
- Run-to-brief pinning so feedback can be tied to the exact brief revision that produced a candidate.
- The candidate workspace itself (described in `docs/cloris-candidate-workspace-spec.md`).
- Brief-iteration tooling (`shared/brief_iteration.py:862-910`).

The first three of these are explicit prerequisites for shipping any non-LinkedIn module to a paying customer. See `Cloris-Multi-Module-Roadmap.md` for sequencing.

## 10. Year-2 picture (what success looks like)

By April 2027, the product is judged successful if:

- Cloris has 8-15 paying customers across two or three commercial tiers (frontier labs, AI exec search firms, boutique technical recruiting).
- The Researcher module has shipped, has at least 3 lab customers, and is producing evaluable researcher candidates that recruiters consistently move forward.
- The OSS Maintainers module (or its full registry-adapter form) has shipped, with at least 2 frontier-lab customers using it for infrastructure-engineer hiring.
- The candidate workspace exists, the feedback loop is closed, and recruiters are demonstrably authoring better briefs in week 8 than they did in week 1 — with telemetry showing the improvement.
- At least one additional module (Healthcare, Defense, or Sales Leadership workflow) has shipped or is in active customer development.
- Cross-module identity resolution is live and the workspace presents candidates as people, not as per-source rows.
- The architecture has not regressed: `runtime_state.sqlite3` is still canonical, briefs are still vertical-agnostic, the substrate still feels like a framework that absorbs new modules rather than a codebase that copies an orchestrator.

The product is judged unsuccessful if:

- Modules ship but produce candidates that no customer actually works (discovery without evaluation quality).
- Cloris loses its specialist positioning and starts competing with general-purpose sourcing tools.
- The feedback loop never closes and Cloris becomes a one-shot tool.
- The substrate accumulates source-specific assumptions to the point that adding a new module requires architectural negotiation rather than following the integration contract.

## 11. Decisions captured here

- 2026-04-29 — Modules are discovery layers reconciling to a single workspace; not parallel products. Forecloses per-module SKUs and per-module save destinations. See section 5.
- 2026-04-29 — Evaluation pipeline is the strategic asset. Data acquisition is commoditized; calibrated evaluation is not. Pricing and positioning lead with evaluation quality. See section 6.
- 2026-04-29 — Closed feedback loop is the long-term moat and the longest-pole product investment. Candidate workspace + feedback artifact + run-to-brief pinning are prerequisites for shipping any non-LinkedIn module to paying customers. See section 9.
- 2026-04-29 — Cloris is a local desktop product in v1. Hosted multi-tenant operation is deferred until at least three modules are commercially validated. See section 3.
- **2026-04-30 — Evaluation substrate extends to multimodal evidence (vision, video, audio).** Designer module ships this as v1 proof-of-concept under HITL framing (recruiter as arbiter; multimodal model as senior-associate guidance). See section 6 and `docs/designer-hitl-module-spec.md`.
- **2026-04-30 — Creative-work hiring is added as the sixth buyer persona** (§4.6). Smaller per-buyer willingness-to-pay than technical modules; offset by genuine novelty and category breadth contingent on multimodality thesis advancing. See `Cloris-Multimodality-Thesis.md`.
- **2026-04-30 — Differentiation surface gains a second face** (§7) for creative-work conversations: "multimodal evaluation against a customer-calibrated brief, no other recruiting tool runs this." Used contingent on Designer commercial validation; not used in technical-recruiting conversations. The product north star (single agent, single substrate, evaluation-as-asset, closed loop) is unchanged; the GTM surface gains a face.
