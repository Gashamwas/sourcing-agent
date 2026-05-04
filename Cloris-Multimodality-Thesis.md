# Cloris Multimodality Thesis

Status: thesis
Owner: Sam
Last updated: 2026-04-30

This document captures a strategic thesis that emerged from the 2026-04-30 reframe of the Designer module: **the multimodal-LLM-plus-brief-encoded-rubric pattern that powers the Designer module is not Designer-specific. It is a module category — creative-work modules that evaluate non-textual work product against a brief-encoded rubric with HITL recruiter arbitration.** If the thesis holds, Cloris's positioning expands from "the editorial sourcing platform that happens to do design" to "the depth-evaluation platform for creative-work hiring."

This is a thesis, not customer-validated strategy. The Status header reflects that. The Designer module ships in Phase 2 as the proof-of-concept; subsequent modules in this category are contingent on Designer's commercial validation. This doc captures the unifying frame, the tier-list of discipline candidates, the architectural primitives that compose across modules, and the conditions under which the thesis becomes load-bearing for Cloris's strategy versus a curiosity that doesn't extend.

For the strategic spine see `Cloris-Product-North-Star.md`. For module-by-module assessment see `Cloris-Module-Strategy.md`. For the time-bound roadmap see `Cloris-Multi-Module-Roadmap.md`. For the proof-of-concept module spec that initiated this thesis see `docs/designer-hitl-module-spec.md`.

## 1. The thesis

The recruiting tools market — horizontal sourcing platforms (HireEZ, SeekOut, Gem, Findem, Eightfold) and specialized creative-work platforms (Working Not Working, Dribbble Hiring, Folyo, Authentic Form & Function) — does not run multimodal-LLM evaluation against work product as part of sourcing. Horizontal tools cannot take taste positions on creative work without alienating chunks of their customer base; their architecture and GTM push them toward generic capability, not vertical depth. Specialized creative-work platforms are taste-curated by humans without VLM tooling. The structural mismatch keeps the space empty even as the underlying technology (frontier multimodal models — Gemini 2.5 Pro, Claude with vision, GPT-4o) became viable in 2024-2025.

Cloris's depth-per-population architecture (modules as discovery layers feeding a single reconciliation surface, brief-encoded calibration carrying customer-specific taste, evaluation as the durable substrate per `Cloris-Product-North-Star.md` §6) is uniquely suited to this gap. Specifically:

- **The brief authoring methodology** translates customer taste into structured criteria + exemplar examples. For taste-laden creative evaluation, this is the calibration mechanism that lets a single off-the-shelf multimodal model approximate per-customer taste without fine-tuning. The brief carries the taste; the model applies it.
- **The HITL framing** preserves recruiter arbitration. Multimodal evaluation provides senior-associate-level guidance the recruiter reacts to; it does not replace recruiter judgment. This is structurally important because (a) creative taste is contestable enough that no single model verdict should be final, and (b) horizontal incumbents cannot replicate this framing without restructuring their GTM.
- **The closed feedback loop** improves rubric calibration over weeks of use. Recruiter feedback markers on multimodal evaluation output feed brief revision proposals; the rubric sharpens against the customer's actual taste over time.

Apply this pattern to a discipline where work product is non-textual and existing tools cannot evaluate it, and the result is a module category, not a single module.

## 2. The unifying frame

A creative-work module is one in which:

1. The candidate's evaluable signal is **non-textual work product** (visual, video, audio, multimodal). LinkedIn profiles + GitHub repos are textual signals; portfolios + reels + audio samples + composition recordings are not.
2. **Existing tools do not evaluate the non-textual signal at all.** They surface it (link to the portfolio, embed the reel, list the SoundCloud) but produce no structured evaluation of it. The recruiter does the evaluation manually.
3. **A multimodal model + brief-encoded rubric can produce meaningful evaluation** of the work product against role-specific criteria. The criteria are taste-laden (different customers want different things), so the brief carries the taste calibration.
4. **HITL framing is the right architecture.** The recruiter remains the arbiter. The model produces senior-associate-level guidance the recruiter reacts to. This is not a "the model decides" architecture; it is a "the model accelerates the recruiter's evaluation by structuring the analysis they would have done manually" architecture.

The pattern composes across disciplines. Each module instantiates the same architectural primitives (rubric schema, evaluable-asset acquisition layer, multimodal evaluation pass, HITL workspace surface, per-discipline calibration exemplars) with discipline-specific rubric content, source adapters, and evaluation weights. Designer is the first instance; Photographer, Motion Designer, Game Artist, Architect, Voiceover, Composer follow with the same plumbing.

## 3. Discipline tiers

Discipline candidates ordered by strategic fit. Tier 1 is the Designer-pattern direct extension; Tier 4 is speculative.

### Tier 1 — Visual creative-work, similar to Designer

Visual portfolios, image-or-video work product, taste-laden recruiting, vision-LLM applies cleanly. The Designer module's architectural primitives port with discipline-specific rubric content swapped in.

- **Photographer / cinematographer.** Editorial photo, fashion photo, ad agency DPs, documentary cinematographers, music video DPs. Portfolios are images and reels. Rubric: composition, lighting craft, exposure discipline, color story, narrative coherence, editorial voice, range across briefs. Buyer pool: editorial photo recruiting (boutique firms exist), ad agency staffing (Aquent / Vitamin T / Onward Search overlap), fashion brands (Condé Nast / Hearst / boutique fashion houses), music industry (label creative teams, music video production companies).
- **Motion / 3D / VFX.** Reels (video), animation work, technical breakdowns. Multimodal-LLM handles video natively. Rubric: motion timing, kinetic typography, easing discipline, technical breakdown quality, integration craft, narrative pacing, range. Buyer pool: studios, post houses, ad agencies, game companies, streamers (Netflix / A24-as-distributor / HBO creative teams), explainer-video studios.
- **Game art / concept art / character design.** Concept art portfolios, character / environment / prop / UI work for games. Rubric: art direction adherence, technical quality (rendering, anatomy, perspective), narrative coherence, IP consistency, range of styles, painterly craft. Buyer pool: AAA studios (Riot, Blizzard, Epic, EA, Ubisoft), indie studios, animation companies (Pixar / DreamWorks / Sony Animation hire freelancers and staff), tabletop / board game art directors.
- **Architecture.** Renderings, plans, sections, photography of built work, model photography. Rubric: spatial logic, material articulation, contextual response, structural integration, environmental thinking, programmatic clarity. Buyer pool: architecture firms doing in-house design hiring (HOK / Gensler / SOM / boutique studios), real estate developers' in-house design teams, hospitality groups hiring interior architects.
- **Fashion design.** Lookbook portfolios, garment construction photos, mood boards, technical flats. Rubric: silhouette discipline, color story, material understanding, season coherence, conceptual originality, technical execution. Buyer pool: fashion brands (luxury, contemporary, streetwear), fashion-recruiting consultancies (24 Seven Talent skews fashion-heavy), fast-fashion design departments.

### Tier 2 — Audio creative-work, requires audio-LLM treatment

Audio reels, recorded performances, composition portfolios. Multimodal-LLM with audio-input support (Gemini handles audio; Claude is text-only for audio). Per-discipline rubric vocabulary is meaningful — sound is taste-laden in a parallel way to visual.

- **Voiceover / voice acting.** Audio reels. Rubric: tonal range, emotional accuracy, character distinction, mic technique, vocal health, accent / language fluency. Buyer pool: animation studios, ad agencies, audiobook publishers, e-learning companies, podcast networks, gaming studios. Real industry with dedicated recruiting (Atlas Talent, Voice Talent Productions, dedicated VO agents).
- **Composers / music for media.** Composition portfolios (audio + scores). Rubric: harmonic language, orchestration sensibility, emotional range, genre fluency, thematic development, dramatic pacing. Buyer pool: TV/film music supervisors, ad agencies, game audio directors, streaming-content teams.
- **Sound designers.** SFX portfolios, ambience work, foley reels. Rubric: layering sophistication, frequency balance, emotional impact, technical polish, range across genres. Buyer pool: game studios (game audio is a specialized hire), film post production (sound design houses), VR/AR studios.

### Tier 3 — Multimodal / video, more speculative buyer dynamics

Disciplines where the work product is multimodal but the recruiting market is less concentrated or the framing introduces ethical / consent considerations.

- **Title designers / trailer editors.** Title sequences (video), trailer cuts (video). Highly editorial work product. Rubric: editorial pacing, kinetic typography craft, music sync, narrative compression, brand fluency. Buyer pool: film/TV/streaming creative departments, ad agencies, dedicated trailer houses (Buddha Jones / Aspect / Mocean).
- **Frontend developers (visual output).** Live demos of deployed sites. Multimodal-LLM evaluates rendered behavior + interaction quality, not just code. Bridges the existing GitHub module + the Designer pattern. Could be a meaningful enhancement to engineering hiring (extend `github/` module rather than build standalone) or a separate "Web Designer" module. Rubric: visual hierarchy in deployed UI, interaction craft, accessibility implementation, performance, framework idiom mastery.
- **Performance hires with self-submitted demos.** Sales reps submitting recorded discovery calls or demos, communicators submitting recorded talks, instructors submitting lecture clips. Rubric: discovery technique / value articulation / presence / clarity. **Ethical caveat:** must be self-submitted, not scraped. Different framing than scraped portfolios. Buyer pool: enterprise sales recruiting, executive communications hiring, education / training organizations.

### Tier 4 — Specialized, smaller buyer pools

Disciplines with concentrated value but smaller buyer concentrations or specialized data foundation challenges.

- **Industrial / product (physical) design.** Photography of physical products, CAD renderings, prototype documentation. Rubric: form language, material understanding, manufacturing awareness, ergonomic thinking, prototyping rigor. Buyer pool: hardware companies, consumer-product brands, design consultancies (IDEO / Frog / Smart Design have in-house teams).
- **Architectural / engineering technical drawings.** CAD output, BIM models, blueprints. More technical than aesthetic. Buyer pool: AEC firms, large engineering consultancies. Specialized recruiting market.
- **Comedy / performance.** Stand-up sets, sketch reels, improv tape. Highly subjective; emerging algorithmic-evaluation territory. Buyer pool: TV / streaming comedy development, talent agencies (CAA / WME / Gersh comedy desks).

## 4. Architectural primitives that compose across modules

If the thesis holds, the Designer module's build is not a one-off — it is the platform infrastructure for the broader category. The following primitives, built once for Designer, port directly to Tier 1 and Tier 2 modules with discipline-specific content swapped in:

**4.1 `BriefDesignRubric` schema (generalize to `BriefRubric`).**
The `RubricPrinciple`, `CalibrationExemplar`, and `BriefRubric` dataclasses (per `docs/designer-hitl-module-spec.md` §6) are not design-specific. The principle structure (named principle + bad/okay/good/excellent anchors + per-discipline weight) generalizes to any rubric-decomposed evaluation domain. Photographer rubric uses photography principles; Composer rubric uses composition principles; same schema. The schema lives at `shared/brief_schema.py` and is referenced by every multimodal-creative module.

**4.2 Asset acquisition layer.**
Designer's `image_acquisition.py` extracts portfolio images from Behance / Google CSE / personal sites. Photographer uses the same image-acquisition primitives against editorial-photo / portfolio-host source adapters. Motion module uses video-acquisition primitives (extract reel clips from Vimeo / Behance / personal sites). Composer module uses audio-acquisition primitives (extract from SoundCloud / personal sites / Spotify-for-creators). The acquisition layer per discipline is a thin adapter; the orchestration logic (how-many-assets, resolution-selection, fallback-handling) is shared infrastructure.

**4.3 Multimodal evaluation pass.**
Designer's `vision_evaluation.py` runs Gemini 2.5 Pro with rubric-loaded prompt + structured-output schema. Pattern-mirror for video, audio, multimodal evaluations: `motion/video_evaluation.py`, `composer/audio_evaluation.py`. Same structured output (per-principle scoring + reasoning + overall verdict + confidence), same fallback handling, same cost telemetry. Discipline-specific prompts; shared infrastructure.

**4.4 HITL workspace surface (`surface_type: "hitl_visual_review"` generalized).**
The candidate-workspace card type Designer introduces — text contextualization + rubric-decomposed evaluation block + portfolio URL primary action + recruiter feedback markers — generalizes. Rename to `surface_type: "hitl_creative_review"` or split into `hitl_visual_review` / `hitl_audio_review` / `hitl_video_review` if the rendering needs differ enough. The schema and the workspace UX patterns are shared.

**4.5 Per-discipline rubric assets.**
Default rubric content per discipline lives at `config/creative-rubrics/{discipline}/`. Each discipline ships with default principles, anchor definitions, discipline weights, and 3-5 calibration exemplars. Customer briefs override per-customer. Authoring these defaults is editorial work, not engineering work; sequence them by buyer demand, not by engineering convenience.

**4.6 Closed feedback loop integration.**
Recruiter feedback markers on multimodal evaluation output ("Useful guidance" / "Wrong / shallow" / "Off-rubric") feed brief revision proposals (per `docs/cloris-ui-spec.md` §235-249). Same Next Run Learning surface. Rubric calibration sharpens over weeks of use. The closed loop is platform-level; per-discipline modules inherit it without bespoke loop infrastructure.

## 5. Strategic implications

If this thesis holds, three strategic implications follow.

### 5.1 TAM expansion

The single-module Designer TAM (per `Cloris-Module-Strategy.md` §2.5) covers in-house design teams, design recruiting consultancies, executive search for design leadership. ~30-100 boutique firms + larger creative staffing ops + several hundred named in-house buyers globally.

The category TAM compounds across disciplines. Photographer adds editorial photo recruiting + ad agency DP staffing + fashion houses; Motion adds animation studios + post houses + game audio; Game Art adds game studios; Architect adds architecture firms + real estate developer in-house teams; Composer adds music supervision + game audio; etc. The aggregate creative-work-hiring market — counting in-house creative teams, specialized recruiting consultancies, agency / studio / publisher / brand creative departments — is plausibly 5-10x the single-module Designer TAM. Plenty of overlap (creative-staffing firms cover multiple disciplines), but the buyer concentration is real.

### 5.2 Positioning shift

`Cloris-Product-North-Star.md` §7 currently positions Cloris as "a premium specialist tool" with the differentiation surface "evidence-grounded autonomous evaluation against a structured role definition." That framing is correct and remains the spine.

If the multimodality thesis ships, a second positioning becomes available: **Cloris as the depth-evaluation platform for creative-work hiring.** Distinct from "the editorial sourcing platform that happens to do design." Different brand surface to creative-industry buyers. Different conversation with Authentic Form & Function vs. with Anthropic. The product north star doesn't shift; the GTM surface gains a second face.

The implication for buyer development: when LinkedIn / Researcher / OSS Maintainers conversations happen, lead with "evidence-grounded autonomous sourcing." When Designer / Photographer / Motion / future-creative-module conversations happen, lead with "depth multimodal evaluation no other tool runs." Same product; different leading face by buyer.

### 5.3 Competitive dynamics

Pure first-mover novelty has a 6-12 month window per discipline before horizontal incumbents notice the multimodal-creative-evaluation pattern and try to copy. After copying starts, the structural moat (Cloris can take taste positions; horizontals cannot without restructuring their GTM) holds for 12-18 months minimum. After that, the moat compounds via the brief authoring methodology + closed feedback loop — competitors building the same pattern from scratch in 2027 will not have Cloris's calibration data.

Implication for sequencing: plant flags fast in the highest-value disciplines while novelty is at peak. Designer first (Phase 2). If Designer commercially validates, Photographer and Motion in Phase 3 or 4. Each new discipline in the category is cheaper to ship than the previous one because the architectural primitives are reused. A four-discipline category (Designer + Photographer + Motion + Game Art or Architect) by month 12 is the version of Cloris that becomes hard to displace in creative-work hiring.

## 6. Sequencing logic

The thesis is contingent on Designer module commercial validation. Until Designer ships and a customer pays, the broader category is hypothesis. With that gating in mind, the sequencing logic:

**Phase 2 — Designer ships as proof-of-concept** (per `Cloris-Multi-Module-Roadmap.md`). The build hardens the architectural primitives (`BriefRubric`, asset acquisition, multimodal evaluation pass, HITL workspace surface). First creative-work customer onboards. Telemetry on rubric authoring friction, vision-evaluation feedback markers, and recruiter time-to-decide on portfolio cards.

**Phase 2 decision gate** — Does Designer have at least 1-2 paying customers (in-house design team OR boutique design recruiting firm)? Are recruiters marking vision-evaluation output as "Useful guidance" >50% of the time? Is rubric authoring friction tractable? If yes to all three, the thesis advances to candidate territory and Phase 3 considers Tier 1 expansion. If no, the thesis stays hypothesis and Phase 3 priorities revert to non-creative modules.

**Phase 3 — Tier 1 candidate expansion if thesis advances.** Photographer and Motion are the natural next two — same buyer pool concentration as Designer (creative-recruiting firms + in-house creative teams), same vision/video evaluation pattern, primitives reuse cleanly from Designer. Build cost per discipline drops to 2-3 weeks because most engineering is shared. Sequence by buyer signal: which creative-recruiting customer relationship from Phase 2 wants Photographer next vs. Motion next? Customer pull determines order.

**Phase 4-5 — Further Tier 1 + Tier 2 if commercial validation continues.** Game Art and Architecture extend Tier 1; Voiceover and Composer open Tier 2 (audio-LLM, different evaluation primitive but same architectural pattern). By Phase 5, a 4-6 discipline creative-work category is plausible if commercial validation tracks.

**Tier 3-4 disciplines** are explicitly opportunistic. Don't engineer for Tier 3-4 unless customer pull from existing creative-work customer base demands them.

## 7. Where the pattern breaks

Honest accounting of the thesis's load-bearing assumptions and where they may fail.

**Audio-LLM maturity is behind vision-LLM.** Gemini 2.5 Pro handles audio input but the editorial nuance (musical taste, voice quality, mix discipline) is harder than visual taste. Tier 2 disciplines (VO, Composer, Sound Design) may need more iteration cycles per customer than Tier 1, or may need to wait for next-generation audio models. Plan for this; don't promise customers Tier 2 readiness on the same timeline as Tier 1.

**Performance-role hires raise consent / ethics questions.** Scraped recorded behavior is different from scraped portfolio work. Sales-rep / communicator / performer self-submitted-demo framing required. Don't extend the pattern to scraped video of candidates without explicit consent — the legal and ethical surface area is meaningful.

**Pre-portfolio creative hires don't fit the pattern.** Junior creative roles (entry-level designers, recent graduates, career-changers) often lack evaluable portfolios. The Designer module skews mid-to-senior for this reason. If creative-work expansion targets junior pools, a different sourcing pattern is required (educational signal, mentorship signal, learning trajectory) — outside this thesis.

**Discipline-specific rubric authoring is editorial work, not engineering work.** The architectural primitives port; the rubric content does not. Each new discipline requires Sam (or a domain-credible collaborator) to author 6-8 principles with anchors and 3-5 exemplar portfolios. That is real labor, not zero-marginal-cost. Buyer pull justifies the labor; speculative discipline-rubric authoring is wasted effort.

**The novelty-window-as-strategic-asset argument may overestimate horizontal incumbents' inertia.** If SeekOut or HireEZ ship a "VLM creative evaluation" feature in 6 months instead of 12-18, the strategic asymmetry compresses. Mitigation: ship Designer fast, plant Photographer / Motion flags fast, accumulate brief authoring + feedback-loop calibration data fast. The structural moat compounds with usage; the novelty advantage is temporal.

**Buyer concentration in creative-recruiting is thinner than in technical recruiting.** Frontier labs are a 30-50 named buyer pool with $50K-$200K willingness to pay each. Creative-recruiting consultancies are a 30-100 named buyer pool with $15K-$30K willingness to pay each. The unit economics per creative-work customer are lower than per Researcher customer. The category-level math justifies the investment only if multiple disciplines ship; a single creative-work module by itself does not justify the architectural infrastructure investment, but the category does.

## 8. Things this thesis is at risk of getting wrong

Captured for explicit visibility so future versions of this document can audit against them.

- **Treating thesis as strategy.** This document is hypothesis territory. Until Designer commercially validates, "Cloris is the depth-evaluation platform for creative-work hiring" is a possibility, not a positioning. Don't lead with category positioning in conversations with Phase 2 buyers; lead with the proof-of-concept (Designer module's specific value to that buyer). Save the category framing for Phase 3+ when the thesis has empirical support.
- **Architectural primitives drifting per-module.** If each new creative-work module accumulates discipline-specific assumptions in shared primitives (`BriefRubric`, asset acquisition, multimodal evaluation pass), the category-level reusability erodes. Watch for: the second creative-work module (Photographer) requiring substantive changes to the primitives Designer built; rubric schema accumulating discipline-specific fields rather than discipline being a parameter; multimodal evaluation pass having Designer-specific assumptions baked in. Refactor toward shared primitives ruthlessly during Phase 3.
- **Discipline-rubric authoring becoming the bottleneck.** If shipping a new creative-work module requires 1-2 weeks of rubric authoring with a domain-credible collaborator, the category-level cadence slows. Watch for: Sam authoring rubrics solo without designer / photographer / motion-director input; rubrics that recruiters mark "Off-rubric" majority of the time; discipline-rubric authoring becoming a bigger time investment than the engineering for the module.
- **Customer pull driving Tier 1 vs Tier 3 confusion.** A single Tier 3 customer asking for Performance / Sales-rep evaluation could pull Cloris into ethical / consent surface area the platform isn't ready for. Watch for: speculative customer requests in Tier 3 territory generating engineering investment before Tier 1 saturates; ethical / legal surface area expanding without explicit framing in the product.
- **Overspending on Designer's primitive infrastructure.** The "build Designer's primitives so they generalize" instinct is correct strategically but easy to over-engineer. If Designer ships in 8 weeks instead of 5-6 because every primitive is being designed for Photographer + Motion + Composer + every speculative discipline, the proof-of-concept slips and the thesis can't validate. Watch for: refactoring Designer's image_acquisition layer into a generic asset_acquisition layer before any second module exists; rubric schema accumulating fields nobody uses yet "in case." Build for Designer's actual needs; refactor for generalization when the second module's needs make the right shape obvious.
- **Cloris brand drift toward "AI for creatives."** The product north star explicitly anti-positions against "AI-powered sourcing" framing. Creative-work expansion makes "AI for design hiring" / "AI for creative recruiting" tempting marketing language. It is wrong. The framing remains: depth-evaluation against a customer-calibrated brief, in a category where existing tools don't evaluate at all. The "AI" is incidental infrastructure; the rubric + recruiter arbitration is the proposition.
- **Customer-asking-as-gate creeping back in.** Per `~/.claude/projects/-Users-sam-vangelos-Projects-recruiting-tools-sourcing-agent/memory/feedback_thesis_driven_not_customer_asking.md`, pre-build customer-asking is a weak gate for category-creating products. The temptation under thesis-territory work is to ask "but has any creative-recruiting customer asked for Photographer module?" and gate accordingly. The right gate is post-Designer-demo reactions and Designer revenue, then thesis-validation by post-Photographer-demo reactions and Photographer revenue. Do not require pre-build asks before stubbing speculative discipline specs or planning architectural primitives that compose.

## 9. Decisions captured here

- **2026-04-30 — Multimodality-as-module-category thesis articulated and codified as a peer to the existing north-star docs.** Status: thesis, not validated strategy. Designer module is the proof-of-concept; subsequent modules are contingent on Designer's commercial validation.
- **2026-04-30 — Architectural primitives that compose across modules identified.** `BriefRubric` schema, asset acquisition layer, multimodal evaluation pass, HITL workspace surface, per-discipline rubric assets, closed feedback loop integration. Designer's build hardens these for category-level reuse; refactoring toward shared primitives is explicit Phase 3+ work.
- **2026-04-30 — Discipline tier-list captured as priority prior.** Tier 1 (Photographer, Motion, Game Art, Architecture, Fashion); Tier 2 (Voiceover, Composer, Sound Design); Tier 3 (Title designers, Frontend visual eval, Performance hires); Tier 4 (Industrial design, AEC drawings, Comedy). Customer pull from Phase 2 creative-work customers determines actual sequencing within Tier 1.
- **2026-04-30 — Stub specs at `Status: draft` created for Tier 1 disciplines (Photographer, Motion, Game Art, Architect)** to capture thinking while fresh. Specs are not build-ready; they are durable thinking artifacts for future activation.
- **2026-04-30 — Strategic positioning shift acknowledged but deferred.** Cloris's differentiation surface (per `Cloris-Product-North-Star.md` §7) gains a second face — "depth-evaluation platform for creative-work hiring" — contingent on the thesis advancing past Phase 2. Don't lead with category positioning in Phase 2 buyer conversations; lead with Designer-specific value.
- **2026-04-30 — Tier 3 ethical / consent surface area explicitly flagged.** Performance-role evaluation requires self-submitted-demo framing, not scraped recordings. Out of scope for Phase 2-3; revisit only if customer pull demands it.
