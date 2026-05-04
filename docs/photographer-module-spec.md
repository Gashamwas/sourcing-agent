# Photographer Module Spec

Status: draft
Owner: Sam
Last updated: 2026-04-30

The Photographer module discovers editorial photographers, ad-agency cinematographers, fashion photographers, documentary cinematographers, and music video DPs. Cloris evaluates their portfolio reels and image sets against a brief-encoded photographic rubric using multimodal-LLM evaluation, with the recruiter remaining the arbiter under the same HITL framing as the Designer module.

This spec is a stub. It captures the thesis-derived thinking from `Cloris-Multimodality-Thesis.md` §3 (Tier 1) without committing to a build-ready design. Promotion from `Status: draft` to `Status: ready-to-implement` requires Designer module Phase 2 commercial validation per the decision gate in `Cloris-Multi-Module-Roadmap.md`. Most of this module's architectural primitives reuse what Designer ships — `BriefRubric`, asset acquisition layer, multimodal evaluation pass, HITL workspace surface — with photography-specific rubric content swapped in. See `docs/designer-hitl-module-spec.md` for the proof-of-concept and `Cloris-Multimodality-Thesis.md` for the broader category framing.

## 1. Target population

Photographers and cinematographers with documented commercial or editorial output, 5+ years working professionally. Specifically:

- Editorial photographers shooting for top-tier publications (Vogue, Vanity Fair, NYT Magazine, The New Yorker, Wired, et al.) plus the mid-tier of editorial print + digital.
- Advertising photographers / DPs with credited work for recognized brands and agencies.
- Fashion photographers with lookbook, campaign, and editorial work for fashion houses or fashion publications.
- Documentary cinematographers with festival-credited features or distributed series work.
- Music video DPs with credited work for label-released videos.

Excluded from v1: wedding / portrait / event photographers (different buyer market, different evaluation criteria); stock photographers; pure smartphone-content creators without commercial portfolio infrastructure; fine-art photographers without commercial exposure (different buyer pool — gallery / curator framing, not recruiting framing).

## 2. Buyer persona

- Editorial photo recruiting consultancies (boutique firms with named photographer rosters).
- Ad agency talent / staffing — Aquent / Vitamin T overlap, plus agency in-house creative recruiting at the larger holding companies.
- Fashion houses (luxury, contemporary, fashion publications) doing in-house creative team hiring.
- Music industry creative teams (label creative departments, music video production companies).
- Production companies hiring DPs for ad / branded-content work.

Pricing tier per `Cloris-Product-North-Star.md` §4.6 (creative-work hiring): $300-$500/seat-month for in-house creative teams; $15K-$30K annual for boutique recruiting firms.

## 3. Differentiation thesis

Same architectural pattern as Designer (per `docs/designer-hitl-module-spec.md` §3 + `Cloris-Multimodality-Thesis.md` §1). Two layers:

- **Text-based narrowing** via existing Behance / Are.na / personal-portfolio discovery, photography-specific vocabulary in the brief (camera systems, lighting setups, post-production stack, publication / brand client tier).
- **Multimodal-LLM evaluation** against a brief-encoded photography rubric: composition, lighting craft, exposure discipline, color story, narrative coherence, editorial voice, range across briefs. Per-principle scoring + reasoning surfaced as senior-associate-level guidance the recruiter reacts to.

The novelty argument from the thesis doc applies directly: no horizontal sourcing tool runs multimodal-LLM evaluation against photography portfolios; specialized photography-recruiting platforms are taste-curated by humans without VLM tooling.

## 4. Strategic priority and roadmap fit

Tier 1 of `Cloris-Multimodality-Thesis.md`. Deferred / contingent on Designer Phase 2 validation per `Cloris-Multi-Module-Roadmap.md`. If Designer ships and validates, Photographer is one of the two natural Tier 1 follow-ups (alongside Motion). Estimated build cost ~2-3 weeks if Designer's primitives are clean — most engineering shared.

## 5. Data foundation

Pending — derives from Designer's data foundation work. Candidate spine sources:

- **Behance** — many editorial / commercial photographers maintain Behance profiles.
- **Personal portfolio sites** via Google CSE filtered to photography portfolio hosts (Squarespace, Format, Cargo, Pixieset, Squarespace, Photoshelter).
- **Are.na** — surprisingly active photographer cohort, especially editorial / conceptual.
- **LinkedIn** — senior commercial / agency photographers.
- **Industry credit databases** — IMDb-Pro for cinematographers; Marketing Stockholm-style ad-credit databases (LBB Online, AdForum) for ad photographers.

Skip: Instagram / TikTok scraping (rate limits + ToS); image-only stock-photo sites (different buyer); pure curation platforms without recruiter-relevant identity data.

Photography-specific data foundation realism research is required before promoting from draft. The Designer spec's data foundation methodology applies; the specific source viability for photography is a Phase 2 customer-development output.

## 6. Source-specific brief calibration

Pending. Likely additions:

- Camera system / kit signals (Phase One, RED, ARRI, etc. — meaningful for high-end commercial / cinematography hiring).
- Publication / agency credit signals (specific magazines, agencies, brands).
- Editorial vs. commercial vs. fashion specialization.
- Lighting style signals (natural-light vs. studio vs. mixed; specific lighting designers' influence).

Brief rubric reuses `BriefRubric` schema from Designer with photography-specific principles. Default principles draft:

- Composition (frame discipline, subject placement, depth)
- Lighting craft (shaping, mood, technical control)
- Exposure / color (technical discipline, color story)
- Editorial voice / narrative (point of view, sequencing across portfolio)
- Range (different briefs / styles / subjects)
- Production craft (technical scale, on-set capability for cinematographers)

## 7. Evaluation pipeline mapping

Pending — pattern-mirrors Designer module per `Cloris-Multimodality-Thesis.md` §4. Asset acquisition handles photography-specific image sources (high-resolution from Behance project images; lower-resolution from CSE thumbnails; reels for cinematographers). Multimodal evaluation pass uses Gemini 2.5 Pro with photography rubric.

## 8. State machine fit

No new lifecycle states required. New work-unit kind: `PHOTOGRAPHER_PORTFOLIO_QUERY_KIND` (or similar). Otherwise reuses platform infrastructure.

## 9. Identity disambiguation

Pending. Likely anchors: portfolio URL, IMDb-Pro ID for cinematographers, name + agency credits.

## 10. Reconciliation strategy

Photographer ↔ LinkedIn via `shared/cross_module_identity/photographer_to_linkedin.py`. Many commercial photographers are LinkedIn-active; many editorial photographers are not. Per-source bias handling.

## 11. Save destination

Standard: `["candidate_workspace"]`. Reuses `surface_type: "hitl_visual_review"` (or a `hitl_visual_review` variant if photography rendering needs differ from design).

## 12. Build effort estimate

~2-3 weeks if Designer's architectural primitives are clean. ~4-5 weeks if primitives need significant refactoring to accommodate photography-specific patterns. The `BriefRubric` generalization (rename from `BriefDesignRubric`) and asset acquisition layer abstraction work happens in Phase 3 alongside this module's build, not before.

## 13. First-customer demonstration scope

Pending — derives from first photographer-recruiting customer's specific brief. Plausible demo brief: "Editorial photographer for Series-B consumer brand's marketing campaign, with portfolio depth in lifestyle / product / portraiture and credited editorial work in the last 24 months."

## 14. Ship-quality scope

Pending.

## 15. Failure modes and edge cases

Pending. Photography-specific concerns to surface:

- High-resolution image acquisition from rights-managed editorial / agency sources.
- Cinematographer reels are video; viability of multimodal-LLM evaluation on long-form video clips at acceptable cost.
- Style / aesthetic match across customer briefs (a customer's "editorial photographer" for a Vogue-shape brief is different from "editorial photographer" for a National Geographic-shape brief).

## 16. Open questions

- Does Are.na have meaningful coverage of professional photographers, or is it predominantly fine-art / conceptual?
- IMDb-Pro API access for cinematographer identity resolution.
- Cost economics of video-based vision evaluation for cinematographer reels (longer than design-portfolio evaluations).

## 17. Decisions captured here

- 2026-04-30 — Stub spec created per `Cloris-Multimodality-Thesis.md`. Status: draft. Promotion to ready-to-implement is gated on Designer Phase 2 validation.
