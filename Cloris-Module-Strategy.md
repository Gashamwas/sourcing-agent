# Cloris Module Strategy

Status: living
Owner: Sam
Last updated: 2026-04-30

This document captures the audit synthesis on Cloris's modular extension. Each module's strategic position, target population, buyer persona, commercial viability, differentiation thesis, data foundation reality, and priority ranking is recorded here as the durable strategy artifact. It is the document a customer-development conversation references, the document a build prioritization decision references, and the document the next AI window opens to understand "why these modules in this order."

For the architectural invariants modules must respect, see `Cloris-Architecture-North-Star.md`. For the integration mechanics, see `docs/cloris-module-integration-contract.md`. For per-module specs, see `docs/<module>-module-spec.md` or `docs/<module>-workflow-spec.md`. For the time-sequenced build plan, see `Cloris-Multi-Module-Roadmap.md`. For the 2026-04-30 multimodality module-category thesis (creative-work modules with multimodal-LLM evaluation as a category extending beyond the Designer module), see `Cloris-Multimodality-Thesis.md` — that document is hypothesis territory contingent on Designer's commercial validation but is the primary strategic artifact for thinking about Tier 1 creative-work expansion (Photographer, Motion, Game Art, Architect, etc.).

This document is re-versioned as customer signal arrives. Module assessments are not facts; they are the best-available read on commercial viability and architectural fit at the date in the header.

## 1. The synthesis

Two parallel audits (the primary audit in this Claude Code window and a sibling audit in another window) examined the modular extension question concurrently. They converged on most points and diverged on three. Both audits and the founder's pushback on the divergences are reconciled here.

The shared conclusions are:

- **Modules are discovery layers feeding a single reconciliation surface, not parallel sourcing products with their own save destinations.** The reconciliation contract for GitHub today (`GitHub-LinkedIn-Reconciliation-Source-of-Truth.md`) generalizes to every new module. LinkedIn is the canonical reconciliation surface today; the Cloris-native candidate workspace becomes the canonical reconciliation surface as soon as it ships.
- **The substrate is multi-module-ready at the runtime-state layer.** `shared/runtime_state/store.py:121-205` already source-discriminates everything that matters. No schema refactor is required to add modules.
- **The brief schema, save destination semantics, control plane, and candidate workspace surface have load-bearing single-source assumptions** that break the moment a non-LinkedIn module ships. Foundation work in `plans/multi-module-foundation.md` resolves these.
- **The evaluation pipeline is the strategic asset.** Data acquisition is commodified or commoditizing; calibrated evaluation is not. Every module reinforces or weakens this positioning.

The disagreements were on three modules: Designer, Sales Leadership, and Defense. The founder's pushback resolved each of them. The reconciled view is in this document.

## 2. Module-by-module assessment

Each module is assessed under nine headings: target population, buyer persona, commercial viability, differentiation thesis, data foundation, evaluation pipeline fit, build cost, strategic priority, and the open questions that gate the priority.

### 2.1 Researcher (ML / academic-track)

**Target population.** ML researchers with documented publication record. Specifically: first-author authors at NeurIPS, ICML, ICLR, ACL, EMNLP, COLM, CVPR with 3+ years post-PhD industry or lab experience; research scientists at frontier AI labs with public academic footprints; PhD students in their final year or recent graduates productive on arXiv; staff researchers at national labs whose LinkedIn profiles are sparse but whose Semantic Scholar/OpenAlex/dblp footprint is rich. Excluded: pure academic faculty unlikely to move to industry; applied ML practitioners without publication signal (LinkedIn covers them); Kaggle-only data scientists self-identifying as researchers.

**Buyer personas.** (a) Frontier AI labs and AI-native companies hiring research scientists and research engineers — Anthropic, OpenAI, Google DeepMind, Meta, xAI, Mistral, Cohere, Inflection, Adept, Reka, Magic, Imbue, Sakana, and the tier of growth-stage labs (Together, Modal, Anyscale). (b) AI-focused executive search firms — Daversa, Riviera Partners, ZRG, Heidrick AI practice, True Search AI practice. (c) AI strategy consulting firms building bespoke research teams. (d) Tier-1 universities recruiting industry hires for tenure-track AI faculty (slow buying cycle).

**Commercial viability.** Strongest single module on the list. ~4,000-8,000 named buyers globally; per-seat pricing $1.5K-$4K/month for in-house lab use; firm-level annual pricing $40K-$120K for boutique recruiting; enterprise pricing $100K+ for large search firms or frontier labs. Mis-hire cost in this category is $1M+ in compensation plus 12+ months of lost time, so willingness to pay is high. Competitive landscape: AlphaSights serves expert-network use cases adjacent to this; ScienceIO does academic search for medical only; no direct competitor does brief-driven autonomous evaluation of researchers. Open category.

**Differentiation thesis.** Cloris's calibration-driven evaluation pipeline (`shared/brief_schema.py:179`) is the right substrate. "Builder vs. user" maps to "research scientist who builds vs. applied ML practitioner who consumes research." Non-fit patterns map to "industry-applied work that won't transfer back to research environments." Nobody else has the structured-judgment substrate. The data is open; the calibration is the asset.

**Data foundation reality.** Strongest of any module. **OpenAlex** is the spine — CC0 license, full author identity (display_name, ORCID, last_known_institutions linked to ROR for clean geography, h-index, citation count, paper count, topic embeddings via concepts), free API at 100K calls/day, bulk S3 snapshots for backfill, daily updates, ~250M works and ~90M authors. **Semantic Scholar** for paper similarity, SPECTER2 embeddings, cross-validation of h-index — free API, 1 req/s sustained with free key. **dblp** for ML-conference disambiguation — CC0 data, manually curated, best-in-class CS author IDs. **arXiv** for fresh preprint feed — register as affiliate before launch, polite 1 req/3s rate limit. **PubMed** for the Healthcare extension — free, government, real-time, 10 req/s with API key. Skip: Google Scholar (ban risk, ToS), ResearchGate (Cloudflare-hostile, low-quality scraping).

**Evaluation pipeline fit.** Excellent. The existing four-step structural template (capability mapping → depth test → transferability → decision) applies directly. Snippet evidence is author summary plus top-N papers; full evidence is complete publication record plus abstracts plus affiliation history plus co-author network. The lifecycle (`shared/runtime_state/store.py:62-71`) maps without modification.

**Build cost.** ~4 weeks for a v1 that ingests a researcher brief, queries OpenAlex/dblp/arXiv/Semantic Scholar, runs the existing evaluation pipeline with a `researcher/judgment_templates.py` thin parallel to `github/judgment_templates.py`, produces saves, and reconciles to LinkedIn. Healthcare extension is +1-2 weeks (PubMed adapter + biomedical brief calibration vocabulary).

**Strategic priority.** Build first. Highest commercial viability, best architectural fit, cleanest data foundation, open category to claim. The first non-LinkedIn module that ships also de-risks the integration contract and proves the platform pattern.

**Open questions.** None gating the build. Customer-development can run in parallel with the build because frontier labs are the easiest cohort to validate against (small named buyer pool, accessible network).

### 2.2 OSS Maintainers (GitHub++)

**Target population.** Maintainers of high-impact open-source projects, defined by the cross-product of (a) GitHub commit/review activity on a project, (b) package-registry download counts (npm, PyPI, crates.io, RubyGems, Maven, Go modules), and (c) ecosystem position (OpenSSF Criticality Score, transitive dependency depth in major frameworks). Senior infra/systems/DevTool engineers. The long tail of authors of frameworks frontier labs and infrastructure companies depend on.

**Buyer personas.** (a) Frontier AI labs hiring infrastructure engineers — every lab listed under Researcher, plus cluster of growth-stage AI companies. (b) DevTool companies — Vercel, Replit, Modal, Convex, Linear, Granola. (c) Infrastructure startups — Cloudflare, Fly.io, Supabase, Neon, ClickHouse, Turso. (d) Cluster of OSS-funded companies hiring from their own community.

**Commercial viability.** ~30-50 named enterprise buyers willing to pay $50K-$200K/seat-year because senior systems/infra hiring is the most-constrained recruiting category in tech in 2026. Hiring willingness for this cohort sits at $1M+ comp packages; pricing for a working tool is enterprise-grade. The buyer pool is small in absolute count but commercially dense.

**Differentiation thesis.** Highest of any module on the list. Nobody is doing this. Not GitHub-recruiting products (they search profiles, not maintainer impact). Not Apollo/ZoomInfo (they don't index OSS). Not LinkedIn (impossible to filter for "maintainer of a high-impact library"). The cross-product of GitHub commit activity + package-registry download counts + dependency-graph position is a unique signal nobody has built around.

**Data foundation reality.** Clean. **npm registry API** at registry.npmjs.org and api.npmjs.org/downloads — free, no auth, full maintainer arrays with usernames and emails, monthly download counts per package. **PyPI** at pypi.org/pypi/{package}/json plus **ClickPy** (BigQuery Linehaul mirror) for download stats — 2.65T+ download records indexed, free tier on BigQuery for first 1TB/month. **crates.io API** at crates.io/api/v1 — free, no auth, owners and per-version download counts. **OpenSSF Criticality Score** as a project-level filter — open dataset ranking projects 0-1 by criticality based on commits, contributors, dependents, and release patterns.

**Evaluation pipeline fit.** Excellent — and crucially, the integration is *extension* of the existing GitHub module, not a parallel module. The module spec (`docs/oss-maintainers-module-spec.md`) defines two tiers. Tier 1 is brief-only: write a brief targeting maintainer behavior, run the existing GitHub adapter, get something usable. Tier 2 is full module: add `github/registries/{npm,pypi,crates}.py` adapters, append maintainer-impact evidence to `to_evidence_text()` in `github/schemas.py`, score candidates by package impact. Tier 1 ships in days (brief authoring); Tier 2 in 2-3 weeks.

**Audit disagreement and resolution.** The sibling audit framed this as "this is not a module, it is a brief." That framing is correct for Tier 1 and incorrect for Tier 2. The brief-only approach finds maintainers but cannot distinguish maintainer of a 50M-downloads/month package from maintainer of an unused package — the entire commercial pitch depends on impact ranking, which lives in package registries, not GitHub. Both audits and the founder converged on: ship Tier 1 as a quick win, ship Tier 2 as the commercially differentiated product.

**Build cost.** Tier 1: zero engineering, brief authoring only. Tier 2: ~2-3 weeks atop the existing GitHub module — three registry adapters, maintainer-impact scoring function, brief schema additions for `MaintainerCalibration`, evidence integration via `to_evidence_text()` extension.

**Strategic priority.** Build second after Researcher, in parallel if engineering capacity allows. The differentiated Tier 2 version is the highest commercial-velocity bet on the list — small but high-spend buyer pool, real differentiation, lowest build cost relative to commercial value.

**Open questions.** None gating the build. Customer development with frontier labs and DevTool companies can validate Tier 1 (brief-only output) in week 1.

### 2.3 Healthcare / Life Sciences

**Target population.** Computational biologists and bioinformaticians (PhD or equivalent industry experience, 3-8 years) for biopharma roles; MD-PhDs bridging clinical research and AI; clinical data scientists with biobank or EHR experience; structural biologists with drug discovery focus; epidemiologists for public-health AI applications.

**Buyer personas.** Biopharma companies doing data-science hiring (AstraZeneca, Pfizer, Genentech, Vertex, Regeneron, smaller biotechs); AI-in-healthcare startups; clinical AI companies (Tempus, Flatiron, Insilico, AbridgeAI); academic medical centers building research teams.

**Commercial viability.** Strong and growing. Biopharma's competition for computational scientists is as intense as frontier AI's competition for ML researchers. Per-search pricing $250-$600 for specialist sourcing; firm-level pricing $20K-$80K annual. Competitive landscape is thin — life-sciences candidates are systematically underrepresented in LinkedIn-centric sourcing because their identity lives in publication record more than career history.

**Differentiation thesis.** Same as Researcher. PubMed + OpenAlex evidence-grounded evaluation has no real competition.

**Data foundation reality.** Strong. **PubMed E-utilities** at eutils.ncbi.nlm.nih.gov is the best free biomedical author database that exists — per-author affiliations stored since 2014, ORCID present in post-2017 records, occasionally even author email embedded in `<AffiliationInfo>` strings. Free with API key, 10 req/s. **ClinicalTrials.gov** has a public API for clinical-trial linkage. **OpenAlex** backfills citation counts. **bioRxiv/medRxiv** preprint feeds via cross-links from PubMed.

**Evaluation pipeline fit.** Identical to Researcher. The module is structurally a Researcher variant: same source-adapter interface, same brief schema with biomedical capability vocabulary instead of ML capability vocabulary, same evaluation pipeline.

**Build cost.** ~1-2 weeks as an extension to the Researcher module after Researcher v1 ships. Architecturally, this is `researcher/sources/pubmed.py` plus a biomedical brief template.

**Strategic priority.** Build third. Sub-module of Researcher. Ships ~1-2 weeks after Researcher v1.

**Open questions.** None.

### 2.4 Defense / Physical engineering

**Target population.** Engineers working on defense-relevant systems whose technical depth is documented in voluntarily-published public records. Specifically: PhD and MS engineers with 5+ years experience in radar/EW signal processing, autonomy and perception for contested environments, communications and signal processing, hypersonics or directed-energy systems, RF and microwave engineering, sensor fusion. The defining signals are SBIR/STTR award history, USPTO patent portfolio in defense-adjacent CPC classifications, IEEE/AIAA conference publication record, and DTIC unclassified report authorship.

**Buyer personas.** (a) Defense recruiting firms — FedHired, ClearedJobs.net's recruiter clients, MoxxiSecure, plus boutique cleared-talent firms. (b) Defense primes — Raytheon, Lockheed, Northrop, General Dynamics, Boeing Defense, BAE, L3Harris. (c) Defense-tech startups — Anduril, Shield AI, Rebellion Defense, Hadrian, Hermeus, Castelion, Saronic, Joby Defense. (d) Dual-use AI companies with growing defense programs — Palantir, Scale AI, Sarcos.

**Commercial viability.** Real but slower than Researcher. Defense recruiting market is significant ($500M+ in specialized placement fees annually). Defense primes have 12+ month sales cycles and require security reviews. Defense-tech startups are the highest-energy buyer because their hiring constraint dominates their growth. Pricing: $30K-$80K annual for boutique firms; $100K+ for enterprise. Competitive landscape is thin — relationship-driven recruiting today, no algorithmic surfacing tools that work on public-only data.

**Differentiation thesis.** Strong. Patent-based and SBIR-based sourcing is novel. The data foundation is unique — nobody indexes SBIR PI history or patent inventor records as recruiting signals.

**Data foundation reality.** Stronger than I credited in my original audit. **SBIR.gov API** (api.sbir.gov) is the killer source — free, public, structured records of every federal SBIR/STTR award going back to the early 1980s, with PI name, institution, agency code (DARPA, AFRL, ONR, ARL, etc.), phase, technical abstract, and award amount. There is no civilian analog to this database; the technical abstracts describe what was actually built at a level of detail that LinkedIn never reaches. **USPTO PatentsView/PatentSearch** (post-March-2026 endpoint at data.uspto.gov) — free, government-published, AI-disambiguated inventors, patent classification codes, assignee history, abstracts. **Google Patents Public Datasets on BigQuery** for bulk analytics. **IEEE Xplore metadata API** as enrichment (free key, abstract-level metadata, author affiliations). **DTIC** at discover.dtic.mil for unclassified defense technical reports — degraded since the August 2025 staff cuts but still functional.

**Compliance posture.** ITAR/EAR are real but manageable for *publicly known* information. The constraint is on JD content and candidate communication, not on the candidate database. Don't store program-level details. Don't seek clearance signals; if a candidate has voluntarily disclosed clearance status on LinkedIn, the judger can note it but the module does not search for it. The bigger commercial blocker is procurement: defense recruiting firm and defense prime buyers will require contractual reps and SOC 2-style audit trails. Plan for a 3-6 month commercial preparation cycle on top of the engineering.

**Audit disagreement and resolution.** My original audit said "wait for customer pull, ~5 weeks build." The sibling audit said "build alongside Healthcare in months 5-7, ~3-4 weeks for SBIR + Patents + IEEE adapters." The founder's pushback established that there is a clear public-only build path. Reconciled view: build the engineering alongside Healthcare in months 5-7 (~3-4 weeks for the three adapters as Researcher-module variants), but plan customer development as a parallel 6-12 month workstream. Don't predicate the engineering investment on the commercial cycle being fast.

**Evaluation pipeline fit.** Excellent. Same shape as Researcher. Inventors are like authors. Patents are like papers. Assignees are like employers. SBIR awards are like papers with structured agency context. The evaluation pipeline maps directly.

**Build cost.** ~3-4 weeks as Researcher module variants — `researcher/sources/sbir.py`, `researcher/sources/patents.py`, `researcher/sources/ieee.py`. Plus +1 week for compliance audit shell (immutable evidence logs, audit-trail surface, contractual reps document). Critical: SBIR adapter alone is high-signal enough to validate the module before the others land.

**Strategic priority.** Build fourth. Build alongside Healthcare in months 5-7 because the engineering is light, but treat commercial revenue from this module as a 2027 outcome, not a 2026 one.

**Open questions.** Compliance posture documentation needs IP/export-control review before marketing to non-US customers. Worth a brief legal review before launch but not blocking on the engineering.

### 2.5 Designer (HITL with vision-evaluation enhancement)

**Target population.** Mid-to-senior product designers (2-8 years), brand/visual identity designers, design system leads, motion designers. The commercially relevant cohort: product designers at design-forward tech companies, design system contributors, senior UX designers with mobile product ownership. Entertainment-industry creative hires (key art, motion, brand campaign work) are a related but distinct vertical that probably needs a discipline-specific rubric layer if pursued.

**Buyer personas.** Product companies doing design hiring at scale; design agencies building teams; in-house design teams at consumer companies and design-forward entertainment/media operations; executive search for VP/Head of Design; boutique design recruiting consultancies (Authentic Form & Function, Studio of the Future, Adam Morgan, Major Players, Working Not Working, Folyo, Represent) and creative-staffing firms with heavy design exposure (Aquent/Vitamin T, Creative Circle, 24 Seven Talent, Onward Search, The Creative Group).

**Commercial viability.** Moderate-to-strong, with strategic uniqueness offsetting buyer-pool size. Pricing supportable: $300-$500/seat-month for in-house teams; $15K-$30K annual for boutique design recruiting firms. Smaller buyer pool than the technical modules; mitigated by genuine novelty — no horizontal sourcing tool runs VLM-driven portfolio evaluation, and structural reasons (horizontal tools cannot take taste positions without alienating customer segments) keep them out of this space for 12-18 months minimum after copying starts.

**Differentiation thesis (vision-enhanced HITL).** Two layers compose:

- *Discovery and contextualization.* Cloris finds designers worth a recruiter's eye via text-based evaluation on Behance, LinkedIn, and Google CSE-discovered personal portfolio sites — specialization tags, tool stack as builder/user discriminator, client tier from project descriptions, career trajectory from LinkedIn. Same calibration substrate as the technical modules.
- *Vision evaluation against a brief-encoded design rubric.* On top-N candidates that pass text-evidence evaluation, a vision-language model (Gemini 2.5 Pro) evaluates representative portfolio images against a principle-decomposed rubric (visual hierarchy, typographic refinement, compositional balance, color system coherence, conceptual strength, craft execution, plus discipline-specific extensions). Per-principle scoring + rationale surfaced as senior-associate-level guidance. The recruiter remains the arbiter; vision evaluation accelerates HITL review, does not replace it.

The genuine-novelty argument is load-bearing: VLM-driven design evaluation is approximately uncontested in the recruiting tools market in 2026. Horizontal sourcing tools (HireEZ, SeekOut, Gem, Findem, Eightfold) do not take taste positions on creative work because their architecture and GTM push them toward generic capability, not vertical depth. Specialized design recruiting platforms (Working Not Working, Dribbble Hiring, Folyo) are taste-curated by humans without VLM tooling. The structural mismatch keeps the space empty long after pure novelty fades.

**Audit disagreement and 2026-04-30 reframe.** The original audit recommended skipping Designer because full-vision-only evaluation was too expensive and replaced human taste with model judgment. The 2026-04-29 reframe ships HITL only — text-based discovery + recruiter visual review — but section 5 of this strategy doc flagged the differentiation risk: "Designer pulled in early under HITL framing then never differentiated." The 2026-04-30 reframe resolves that flagged risk: vision evaluation lands as a v1 enhancement *to* HITL (not a replacement for it), preserving recruiter arbitration while addressing the differentiation gap. Trigger for the reframe: founder's empirical confirmation that Gemini 2.5 Pro produces materially useful design analysis at recruiter-tool volume cost (~$10-30/customer/month).

**Data foundation reality.** Same as the 2026-04-29 spec for text-based discovery: **Behance API** for specialization-tagged designer profiles; **LinkedIn** for senior product designers; **Google Programmable Search Engine** for personal portfolio sites on Cargo, Squarespace, Format, Semplice, Awwwards/SiteInspire credit-graph. Skip Dribbble (API gutted), Read.cv (shut down), Instagram/X. New data layer for vision evaluation: **portfolio image acquisition** from Behance project image arrays, Google CSE thumbnail metadata, and direct fetches from personal portfolio sites where ToS permits. Image acquisition is the meaningful new data-engineering investment.

**Evaluation pipeline fit.** Reuses the existing capability/depth/transferability/decision substrate for text evidence. Facial triage stays text-based. Full evaluation produces structured context (portfolio URL, specialization summary, notable project descriptions, tool depth, client tier) plus, on top-N candidates, a vision-evaluation pass producing per-principle scoring against the brief rubric. Candidate workspace renders both as a `surface_type: "hitl_visual_review"` card with vision evaluation as inline editorial commentary. Decision contract unchanged: `SAVE` flagged for HITL review; recruiter's confirmation/rejection is a workspace action.

**Build cost.** ~5-6 weeks at split-attention pace. Text-based pipeline (Behance adapter, Google CSE adapter, brief schema additions, contextualization prompt, HITL workspace surface, identity resolver, tests): ~3-4 weeks per the 2026-04-29 spec. Vision-evaluation additions (rubric schema authoring, default rubric content, image acquisition layer, Gemini integration, structured output, prompt iteration, tests): ~2 weeks.

**Strategic priority.** Build third or fourth. Months 4-6, in parallel with or immediately after Researcher v1. The novelty window (6-12 months before horizontal tools attempt to copy) argues against the prior Phase 5 placement. Behind Researcher, OSS Maintainers Tier 2; ahead of Healthcare, Defense, Sales Leadership.

**Open questions.** Behance API access stability under Adobe ownership (verify at build time). Image acquisition reliability across Behance/Google CSE/personal sites under varying ToS postures. Vision-evaluation prompt iteration cycles before customer-acceptable critique quality (probably 2-3 iteration cycles per discipline; unverified until first customer).

### 2.6 Sales Leadership (LinkedIn workflow configuration)

**Target population.** VPs of Sales, CROs, enterprise AE leaders with verifiable performance at companies in defined growth stages. Specifically: people who built outbound motions from scratch, scaled SDR teams, closed enterprise deals in specific verticals (fintech, healthcare IT, cybersecurity, DevTools, AI infrastructure).

**Buyer personas.** VC-backed companies scaling their first GTM team; PE portfolio companies doing operational turnarounds; executive search firms serving SaaS companies.

**Commercial viability.** Moderate. Large market with high willingness to pay, but evidence sparsity caps differentiation. Pricing in line with the LinkedIn module ($1.5K-$4K/seat-month) but the module-specific value-add over LinkedIn alone is smaller than the technical modules.

**Differentiation thesis.** "Best available automated synthesis of public evidence for sales leadership profiles." Honest framing. Not "evidence-grounded evaluation equivalent to Researcher" — that framing fails because quota attainment data does not exist publicly. The differentiation is in the synthesis quality of inferable signals (company stage during tenure, headcount growth during tenure, industry vertical, GTM motion type, occasional press mentions and award recognition via Perplexity).

**Audit disagreement and resolution.** My original audit said "skip — no differentiation against Apollo + LinkedIn." The sibling audit said "find a way to make it work in some capacity." The founder's pushback was correct: the evidence sparsity problem is real but doesn't justify dismissal; what's available is materially better than unassisted LinkedIn search and worth building cheaply. Reconciled view: build as a LinkedIn workflow configuration in months 7-9, ~2 weeks of engineering, and position honestly — don't put it on the homepage, don't claim Researcher-level evidence quality.

**Data foundation reality.** What exists: company stage during tenure (Crunchbase or LinkedIn-derived), headcount growth during tenure (LinkedIn company pages), industry vertical and GTM motion type (inferable from company history), press mentions and award recognition (Perplexity, occasional), public methodology content (LinkedIn posts, Substack, Sales Hacker, Pavilion). What does not exist: quota attainment, deal history, specific pipeline numbers — all of this is confidential.

**Evaluation pipeline fit.** Reuses the existing LinkedIn pipeline with sales-leadership-specific brief calibration. The DepthDistinction translates: builder = architected and executed the GTM motion (built SDR function, designed territory/comp, scaled team); user = managed a team executing someone else's playbook. Capability areas: GTM architecture, pipeline generation, enterprise closing, team scaling, vertical expertise. Evaluable from trajectory + contextual evidence even without quota data. Confidence bands explicitly lower (0.40-0.70 vs. 0.60-0.95 for technical roles), encoded via `PostSaveModifier` patterns (`shared/brief_schema.py:27-37`).

**Build cost.** ~2 weeks. Not a new source adapter. Components: (a) sales-leadership-specific Perplexity prompt variant in `shared/external_evidence/provider.py` requesting company stage/funding/growth context, (b) pre-built sales leadership brief templates calibrated to GTM-architecture builder/user distinctions, (c) confidence calibration via `PostSaveModifier` in the brief, (d) instructions field guiding contextual-inference vs. direct-evidence interpretation.

**Strategic priority.** Build fifth. Months 7-9. Position as a LinkedIn module configuration, not as a flagship offering.

**Open questions.** None gating the build. Commercial positioning is the open question — if it ships and customers are dissatisfied with the evidence quality, the failure mode is reputation damage to the platform brand.

### 2.7 Exec Search (workflow mode)

**Target population.** Senior executive candidates being evaluated through the LinkedIn module, plus a research-up-front investigation phase that runs before candidate identification.

**Buyer personas.** Executive search firms doing C-suite and SVP placements; in-house talent partners at companies doing exec hiring.

**Commercial viability.** High at the per-placement value level (exec search placements command 25-35% of first-year comp). But this is not a separate module — it is a premium workflow mode of the LinkedIn module.

**Differentiation thesis.** The order-of-operations distinction (investigate market → identify candidates instead of identify candidates → evaluate) is a real workflow feature, not a new source adapter. Existing infrastructure: `market_intelligence/engine.py`, `market_intelligence/research_agent.py`, `market_intelligence/live_advisory.py` already implement Perplexity-based investigative research. The senior-role evaluation infrastructure already exists in the brief schema (`shared/brief_schema.py:454-544`: `is_senior_role`, `seniority_calibration_block`, `executive_builder_block`, three-tier evidence hierarchy, post-evaluation safety net for L7+).

**Audit consensus.** Both audits agreed: this is not a module. It is a LinkedIn workflow mode wiring existing infrastructure into the run-launch flow.

**Data foundation reality.** Existing — `shared/external_evidence/provider.py` for Perplexity, `market_intelligence/` for investigative research, LinkedIn for candidate identification. No new data sources.

**Evaluation pipeline fit.** Existing — the senior-role calibration in `shared/brief_schema.py:454-544` is already wired into `linkedin/judgment_templates.py` for L7+ briefs.

**Build cost.** ~2-3 weeks. (a) API endpoint in `cloris/api.py` triggering `market_intelligence/engine.py` research before launching the LinkedIn worker. (b) UI step in Cloris frontend presenting research output and asking for confirmation before run launch. (c) Pre-built executive brief templates (Head of AI, CTO, VP of Engineering, Chief Data Officer) that pre-populate seniority calibration fields with worked exemplars.

**Strategic priority.** Build alongside Researcher in months 3-4 because the infrastructure exists and the work is mostly UI integration. Lower-effort than I previously estimated due to existing `market_intelligence/`.

**Open questions.** UI design for the research-output review step before run start. The market-intelligence research packet needs a canonical render shape that the recruiter can scan in <2 minutes.

### 2.8 Legal (LinkedIn brief + bar lookup side effect)

**Target population.** Associates (3-8 PQE) and partners at AmLaw 100/200 firms, in-house counsel at mid-to-large companies, federal law clerks transitioning to practice.

**Buyer personas.** Legal search firms (Major Lindsey & Africa, Lateral Link, BCG Attorney Search, boutique firms); in-house legal recruiting at F500 and high-growth tech companies.

**Commercial viability.** Moderate, but differentiation is weaker than the technical modules. Attorney profiles on LinkedIn are unusually rich — legal professionals describe practice areas, deal experience, and bar admissions on LinkedIn with more clarity than most engineers describe technical work. The "module" addition would be bar admission lookup (a verification side effect, not an evaluation system), PACER case involvement (poor signal-to-noise for identifying strong candidates at scale), and Martindale-Hubbell directory search (commercial API, limited value). None of these require a new evaluation pipeline. They require a brief calibrated for legal practice areas plus a bar admission lookup as an optional post-save side effect.

**Audit consensus.** Both audits: not a separate module. Brief templates for the LinkedIn module + a bar admission lookup side effect.

**Build cost.** ~1-2 days for legal brief templates. Bar admission lookup is an additional ~1 week (state-by-state web lookups with no API for most states; rate-limited polite scraping).

**Strategic priority.** Opportunistic. No engineering urgency. Ship if a customer pulls.

### 2.9 Kaggle

**Strategic priority.** Fold into Researcher as an optional enrichment signal, or skip. Kaggle as a standalone 2026 recruiting signal is largely displaced — top-tier ML talent is identified by HuggingFace, paper authorship, model releases, and frontier-toolchain commits, not Kaggle podiums. Useful as a tiebreaker for early-career applied DS hiring; not load-bearing for senior ML hiring.

### 2.10 LinkedIn X-ray (Google site-restricted)

**Strategic priority.** Tactical addition to the existing LinkedIn module, not a separate module. ~1 week. Useful as a fallback discovery surface when LinkedIn Recruiter cannot be used or when the cohort is sparse. Build whenever the LinkedIn module needs it.

## 3. Modules considered and rejected

**Sales Leadership as a flagship offering.** Rejected. Buildable cheaply as a workflow configuration; not credible as a category-defining module due to evidence sparsity. See section 2.6.

**Designer with full vision-only evaluation (no HITL).** Rejected. Visual judgment of creative work is taste-laden enough that human-in-the-loop arbitration must remain — replacing the recruiter with model judgment alienates the taste-curation buyer base and trades the strongest defensibility argument (recruiter taste calibrated via brief) for a weaker one (model judgment). The 2026-04-30 reframe ships vision evaluation as enhancement *to* HITL, not replacement of it. See section 2.5.

**Generic "patent search" or "academic search" modules** that are not tied to specific buyer personas. Rejected. Cloris is positioned as a specialist tool; horizontal modules dilute the differentiation.

**A "module marketplace" pattern** with third-party developers writing modules against a stable contract. Deferred. The contracts will not be cleanly defined until 3-4 modules have shipped. Premature SDK design risks freezing the wrong abstractions.

**Tier 1 multimodal-creative modules beyond Designer** (Photographer, Motion / 3D / VFX, Game Art, Architecture, Fashion design). **Not rejected — promoted to candidate territory 2026-04-30 via `Cloris-Multimodality-Thesis.md`.** Stub specs at `docs/photographer-module-spec.md`, `docs/motion-module-spec.md`, `docs/game-artist-module-spec.md`, `docs/architect-module-spec.md` capture the thinking. Build sequencing for these is contingent on Designer's commercial validation in Phase 2 — if Designer ships and customer pull confirms the multimodality thesis advances, these modules become Phase 3-4 candidates with build cost dramatically reduced by reuse of Designer's architectural primitives (rubric schema, asset acquisition layer, multimodal evaluation pass, HITL workspace surface). If Designer does not validate, these modules stay deferred. See `Cloris-Multimodality-Thesis.md` §3 for tier-list rationale and §6 for sequencing logic.

**Tier 2 audio creative-work modules** (Voiceover, Composer, Sound Design). Same contingency as Tier 1 plus the additional audio-LLM-maturity caveat per `Cloris-Multimodality-Thesis.md` §7. Not stub-specced yet; revisit when Tier 1 validates.

**Tier 3-4 creative-work modules** (Title designers, Frontend visual-eval, Performance hires, Industrial design, AEC drawings, Comedy). Explicitly opportunistic. Don't engineer until customer pull from existing creative-work customer base demands them. Tier 3 Performance-role evaluation has consent / ethics surface area flagged in the thesis doc.

## 4. Strategic priority ranking

Reconciled across both audits and the founder's pushback. Read with the assumption that Researcher and OSS Maintainers Tier 1 ship first, then customer signal drives the next module choice.

1. **Researcher (ML)** — months 3-4. Highest commercial viability; cleanest data foundation; open category.
2. **OSS Maintainers (Tier 1 brief, then Tier 2 module)** — Tier 1 in month 1 as a quick win, Tier 2 in months 3-4 in parallel with Researcher.
3. **Designer (HITL with vision-evaluation enhancement)** — months 4-6, in parallel with or immediately after Researcher v1. Re-sequenced 2026-04-30 from the prior #7/months-9-12 placement. Rationale: VLM-driven portfolio evaluation is approximately uncontested in the recruiting tools market in 2026, and the novelty window (6-12 months before horizontal tools attempt to copy) is finite. Designer is the strongest expression of Cloris's depth-per-population thesis and the module where Cloris becomes a category of one. The prior placement left meaningful strategic value on the table.
4. **Exec Search workflow mode** — months 3-4 alongside Researcher. Existing infrastructure makes this cheap.
5. **Healthcare extension** — months 5-7 after Researcher v1 ships.
6. **Defense module variants (SBIR + Patents + IEEE)** — months 5-7 alongside Healthcare; commercial revenue is a 2027 expectation.
7. **Sales Leadership workflow configuration** — months 7-9. Position honestly.
8. **Legal brief + bar lookup** — opportunistic, no urgency.
9. **Kaggle as Researcher enrichment** — opportunistic, no urgency.
10. **LinkedIn X-ray** — tactical addition, no urgency.

The single biggest mistake in executing this ranking is speculative module building. Recruiting tools serve concentrated buyer markets where 5-10 customers fund the entire roadmap. The ranking above is a prior, not a deterministic schedule — but note that "customer pull" and "customer-asking-as-gate" are different things. For thesis-driven differentiated products in categories that don't yet exist in customers' mental models (Designer module specifically), pre-build customer-asking is a poor signal because customers cannot articulate within frames they haven't seen. Validate via post-demo reactions and revenue, not pre-build interviews.

## 5. Things this strategy is at risk of getting wrong

Captured for explicit visibility so future versions of this document can audit against them.

- **Reconciliation as the bottleneck.** With four modules each producing leads, the reconciliation layer becomes the dominant constraint on platform value. Cross-module identity resolution (`docs/cloris-cross-module-identity-resolution-spec.md`) is the moat; it is also the thing easiest to underbuild. Watch for: candidates appearing as multiple unmerged rows in Run Review; recruiters complaining about duplication; reconciliation latency growing as module count grows.
- **Brief authoring as the choke point.** Multi-module operation means each brief carries calibration for every module it targets. Brief authoring is already the hardest part of the LinkedIn product. With multiple modules, the brief surface balloons. Without aggressive Authoring Loop UX investment, cycle time for non-power-users becomes prohibitive. Watch for: customer complaints about brief authoring friction; brief reuse across roles trending toward zero.
- **Feedback loop staying open.** Cloris's evaluation quality compounds only if the feedback loop closes. Without it, every module ships and forgets; marginal evaluation quality stays static. The loop is the platform's long-term differentiation. Watch for: feedback never reaching the brief; Next Run Learning surface never used.
- **Designer differentiation thin under HITL-only framing — addressed via 2026-04-30 vision-evaluation reframe.** The original concern: HITL-only Designer is light on engineering investment and risks being indistinguishable from generic Behance discovery. The 2026-04-30 reframe addresses this by adding vision evaluation against a brief-encoded design rubric on top of HITL — VLM-driven portfolio analysis is uncontested in the market, structural reasons keep horizontal tools out, and the recruiter remains the arbiter. Residual risk: vision evaluation produces critique that recruiters find shallow or wrong, eroding trust in the module. Watch for: recruiter feedback marking vision-evaluation output as actively unhelpful (vs. just missing); customer churn citing taste mismatch; rubric authoring overhead exceeding what brief authoring can absorb.
- **Defense compliance under-invested.** ITAR is "workflow constraint, not data constraint" for public information, but defense buyers will demand audit trails the platform doesn't have today. Treat the compliance shell as engineering work, not legal work. Watch for: defense procurement stalls citing compliance gaps; non-US marketing accidentally surfacing export-controlled patent classifications.
- **Speculative module #4-5 builds.** Two modules can be funded by 3-5 customers each. The roadmap leaves room for 4-5 modules in 12 months. The temptation to build speculatively because the engineering is tractable is real. The cost is opportunity cost on engineering time that should fund customer development. Watch for: module #4 shipping with zero customer conversations beforehand.

## 6. Decisions captured here

- 2026-04-29 — Researcher first, OSS Maintainers second (Tier 1 brief immediate, Tier 2 module in parallel with Researcher). Reconciled across both audits.
- 2026-04-29 — Designer rescued by HITL framing; ships in months 9-12. Reconciled per founder pushback. *Superseded 2026-04-30; see below.*
- 2026-04-29 — Sales Leadership viable as LinkedIn workflow configuration; ships in months 7-9 with honest positioning. Reconciled per founder pushback.
- 2026-04-29 — Defense module variants (SBIR + Patents + IEEE) ship as Researcher variants in months 5-7; commercial revenue is a 2027 outcome. Reconciled per founder pushback and SBIR data-foundation insight from sibling audit.
- 2026-04-29 — Healthcare ships as Researcher variant, not standalone module, in months 5-7.
- 2026-04-29 — Exec Search ships as LinkedIn workflow mode, not module, alongside Researcher in months 3-4. Existing `market_intelligence/` infrastructure makes this cheap.
- 2026-04-29 — Legal, Kaggle, LinkedIn X-ray are opportunistic additions, not roadmap items.
- 2026-04-29 — Module marketplace SDK pattern is deferred until 3-4 modules have shipped and the contracts are stable.
- **2026-04-30 — Designer reframed: vision evaluation lands as v1 enhancement to HITL (not replacement). Trigger: empirical confirmation Gemini 2.5 Pro produces materially useful design analysis at recruiter-tool volume cost (~$10-30/customer/month). HITL preserved — recruiter remains arbiter; vision provides senior-associate-level rubric-decomposed guidance. Architectural thesis: brief-encoded design rubric carries customer-specific taste; off-the-shelf VLM applies it; no fine-tuning needed.**
- **2026-04-30 — Designer re-sequenced from #7 (months 9-12) to #3 (months 4-6) in parallel with or immediately after Researcher. Rationale: VLM-driven portfolio evaluation is uncontested in the recruiting tools market in 2026 ("less than 0" competing tools); structural reasons keep horizontal incumbents out 12-18 months minimum; novelty window is finite (6-12 months before copying starts). Designer is the strongest expression of Cloris's depth-per-population thesis. Prior placement left strategic value on the table.**
- **2026-04-30 — Default vision model: Gemini 2.5 Pro. Open-weight alternatives (Qwen, Llama) explicitly rejected for this module. Reliability and quality at recruiter-tool volume outweigh marginal cost savings; per-customer monthly inference at frontier-model pricing is a small fraction of seat revenue.**
- **2026-04-30 — Customer-asking-as-gate explicitly rejected for thesis-driven differentiated module decisions. Pre-build interviews for category-creating products are a weak signal (politeness bias, no frame transfer). Validation gate is post-demo reactions and revenue, not pre-build asking. Applies to Designer specifically and to any future module where Cloris is creating a category that doesn't yet exist in customer mental models.**
