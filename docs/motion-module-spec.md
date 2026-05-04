# Motion / 3D / VFX Module Spec

Status: draft
Owner: Sam
Last updated: 2026-04-30

The Motion module discovers motion designers, 3D artists, VFX artists, and animation specialists. Cloris evaluates their reels and animation work against a brief-encoded motion rubric using multimodal-LLM evaluation (Gemini 2.5 Pro handles video natively), with the recruiter remaining the arbiter under HITL framing.

Stub spec per `Cloris-Multimodality-Thesis.md` §3 (Tier 1). Promotion to ready-to-implement is gated on Designer Phase 2 commercial validation. Architectural primitives reuse Designer's (`BriefRubric`, asset acquisition layer, multimodal evaluation pass, HITL workspace surface) with motion-specific content swapped in and asset acquisition extended to handle video.

## 1. Target population

Motion designers and 3D / VFX artists with documented professional reels, 4+ years working professionally. Specifically:

- Motion designers in advertising / brand campaigns (kinetic typography, animated brand systems, social-content motion).
- 3D artists in product / marketing visualization (CGI for product launches, automotive, architecture renders).
- VFX artists in film / TV / streaming (compositing, simulation, integration work).
- Animation specialists in explainer / educational content (Mograph-style motion, character animation for broadcast).
- Title designers and trailer editors are adjacent — their work overlaps but the recruiting buyer pool is distinct (Tier 3 in the thesis).

Excluded from v1: pure 2D illustration animators (covered by Game Art / illustration discipline overlap); game-engine real-time motion (Game Art module proper); broadcast TV motion ops who do not maintain reels.

## 2. Buyer persona

- Animation studios (boutique mograph studios, larger animation companies).
- Ad agencies and post houses (especially mid-large agencies hiring for in-house motion teams).
- Streamers and content companies hiring in-house motion teams (Netflix / HBO / A24-distribution-shape buyers for marketing motion).
- Game studios hiring trailer / cinematic motion specialists.
- Brand in-house creative teams at design-forward consumer companies.
- Specialized creative recruiting consultancies covering motion (overlap with Designer recruiting consultancies).

Pricing tier per `Cloris-Product-North-Star.md` §4.6.

## 3. Differentiation thesis

Same architectural pattern as Designer + photography-specific principles swapped for motion-specific. Multimodal-LLM evaluation of reels (video) against rubric: motion timing, kinetic typography craft, easing discipline, technical breakdown quality, integration craft, narrative pacing, range across briefs / styles.

Novelty: no horizontal sourcing tool runs reel-evaluation. Most existing tools surface Vimeo or Behance links and stop there.

## 4. Strategic priority and roadmap fit

Tier 1 of `Cloris-Multimodality-Thesis.md`. Likely the second Tier 1 module after Photographer if Designer validates and Tier 1 expansion proceeds. Build cost ~2-3 weeks with shared primitives — though video evaluation introduces some cost / latency considerations beyond Designer's image-only pattern.

## 5. Data foundation

Pending. Candidate spine sources:

- **Vimeo** — primary motion / animation reel host. API access patterns and ToS posture need verification at build time.
- **Behance** — secondary, motion designers cross-post.
- **Personal portfolio sites** via Google CSE.
- **The Mill / MPC / Framestore credit databases** — high-end VFX studio credit attribution.
- **LinkedIn** — broader motion-design coverage.

## 6. Source-specific brief calibration

Pending. Likely additions:

- Software stack signals (After Effects / Cinema 4D / Houdini / Nuke / Maya — meaningful builder/user discrimination).
- Sub-discipline signals (mograph vs. character animation vs. compositing vs. simulation).
- Style signals (kinetic typography vs. 3D photoreal vs. illustrative motion vs. data viz).
- Reel-pacing signals (top-3 shots showcase work vs. compilation reel).

Default rubric principles draft (overrides default `BriefDesignRubric` discipline weights for motion):

- Motion timing / pacing (the load-bearing principle for motion)
- Kinetic typography craft (when applicable)
- Easing / curves discipline
- Visual storytelling
- Technical execution / integration
- Range across genres

## 7. Evaluation pipeline mapping

Pending — pattern-mirrors Designer's pipeline with video extension. Multimodal evaluation pass extracts representative clips from reels (likely first 30 seconds + 2-3 highlight moments per reel). Cost considerations: video evaluation is more expensive per candidate than image evaluation; per-customer monthly inference budget telemetry necessary.

## 8. State machine fit

No new lifecycle states. New work-unit kind: `MOTION_REEL_QUERY_KIND`.

## 9. Identity disambiguation

Pending. Vimeo username, Behance username, name + studio credits.

## 10. Reconciliation strategy

Motion ↔ LinkedIn via `shared/cross_module_identity/motion_to_linkedin.py`. Most commercial motion designers are LinkedIn-active.

## 11. Save destination

Standard: `["candidate_workspace"]`. Workspace surface needs reel-embed handling — recruiter watches reels inline rather than opening external Vimeo. Surface might be `surface_type: "hitl_motion_review"` or a generalized `hitl_creative_review` variant.

## 12. Build effort estimate

~2-3 weeks if Designer's primitives are clean. Video evaluation extension to the multimodal evaluation pass is the main net-new engineering — likely 3-5 days on top of the discipline-specific rubric authoring and source adapters.

## 13. First-customer demonstration scope

Pending. Plausible demo brief: "Senior motion designer for streaming-content marketing campaigns, with reel depth in kinetic typography and brand-system motion, 5+ years experience, credited work for recognized streaming or entertainment brands."

## 14. Ship-quality scope

Pending.

## 15. Failure modes and edge cases

Pending. Motion-specific concerns:

- Video evaluation cost / latency at scale.
- Long reels (>2 minutes) — evaluation strategy for extended-form work (sample clips vs. summary representations).
- Studio-credit attribution — distinguishing the candidate's individual contribution from team credit on big-studio VFX work.

## 16. Open questions

- Vimeo API access viability for systematic reel evaluation.
- Reel-clip extraction strategy (uniform sampling vs. content-aware highlight detection).
- How to handle reels that are themselves edits of underlying client work (the reel demonstrates editing craft on top of motion work).

## 17. Decisions captured here

- 2026-04-30 — Stub spec created per `Cloris-Multimodality-Thesis.md`. Status: draft. Promotion gated on Designer Phase 2 validation. Video-evaluation extension flagged as net-new engineering relative to Designer's image-only baseline.
