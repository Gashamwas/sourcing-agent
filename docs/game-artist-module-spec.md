# Game Artist Module Spec

Status: draft
Owner: Sam
Last updated: 2026-04-30

The Game Artist module discovers game art professionals — concept artists, character designers, environment artists, prop / vehicle artists, and game UI designers. Cloris evaluates their portfolios against a brief-encoded game-art rubric using multimodal-LLM evaluation, with the recruiter remaining the arbiter under HITL framing.

Stub spec per `Cloris-Multimodality-Thesis.md` §3 (Tier 1). Promotion to ready-to-implement is gated on Designer Phase 2 commercial validation. Architectural primitives reuse Designer's with game-art-specific rubric content swapped in.

## 1. Target population

Game art professionals with shipped or studio-credited portfolio depth, 4+ years professional experience. Specifically:

- Concept artists in pre-production (character / environment / vehicle / prop concept work).
- Character designers and modelers (3D character pipeline work).
- Environment artists (3D environment pipeline; world-building art direction).
- Prop / vehicle / hard-surface modelers.
- Game UI designers (in-game UI for AAA / indie).
- Art directors and lead artists (the high-tier outcome).

Excluded from v1: animators (overlap with Motion module); game programmers (existing GitHub module); narrative designers (not art); audio designers (Sound Design module if Tier 2 ships).

## 2. Buyer persona

- AAA studios (Riot, Blizzard, Epic, EA, Ubisoft, Bungie, Naughty Dog, Insomniac, Bethesda — and the cluster of mid-large studios).
- Indie studios with credited shipped titles.
- Animation companies hiring game-adjacent art (Pixar / DreamWorks / Sony Animation occasionally hire game-trained artists).
- Tabletop / board game companies hiring concept and illustration artists.
- Game-recruiting consultancies (boutique firms specializing in game industry placement; real but small market).

Pricing tier varies — game studios are mid-tier ($300-$500/seat-month) but AAA studios may pay enterprise rates for senior / art-director hiring depth.

## 3. Differentiation thesis

Same architectural pattern as Designer + game-art rubric. Multimodal-LLM evaluation of concept-art images / 3D renders / character sheets against rubric: art direction adherence (does the work match a stated style / IP / world brief?), technical quality (anatomy, perspective, render polish, modeling cleanliness), narrative coherence, IP / world consistency across portfolio, range of styles, painterly craft.

Game-industry recruiting is more closed and relationship-driven than tech recruiting; the multimodal-LLM-plus-rubric pattern offers a structured discovery layer that compounds with the relationship-driven part of game recruiting rather than replacing it.

## 4. Strategic priority and roadmap fit

Tier 1 of `Cloris-Multimodality-Thesis.md`. Possibly third or fourth Tier 1 module to ship after Designer validates. Game-industry buyer pool is concentrated and high-spend at AAA tier; smaller spend at indie tier.

## 5. Data foundation

Pending. Candidate spine sources:

- **ArtStation** — primary game-art portfolio host. Acquired by Epic. API access posture under Epic ownership needs verification.
- **Behance** — secondary, game artists cross-post.
- **DeviantArt** — historical game-art community, less commercial-viable now.
- **Personal portfolio sites** via Google CSE.
- **MobyGames / IMDb game database** — credit attribution for shipped titles.
- **LinkedIn** — broader coverage.

ArtStation viability under Epic is the load-bearing data-foundation question.

## 6. Source-specific brief calibration

Pending. Likely additions:

- Software stack signals (Photoshop / Procreate / Maya / ZBrush / Blender / Substance / Unreal / Unity).
- Discipline signals (concept vs. modeling vs. environment vs. UI).
- IP / genre signals (fantasy / sci-fi / stylized / photoreal / etc.).
- Shipped-title credit (how meaningful is the candidate's contribution to titles in their portfolio).
- AAA vs. indie career trajectory.

Default rubric principles draft:

- Art direction adherence
- Technical quality (anatomy, perspective, render quality, modeling cleanliness)
- Narrative / world coherence
- IP / genre fluency
- Range across styles
- Painterly craft / art-direction-level polish

## 7. Evaluation pipeline mapping

Pending — pattern-mirrors Designer.

## 8. State machine fit

No new lifecycle states. New work-unit kind: `GAME_ARTIST_PORTFOLIO_QUERY_KIND`.

## 9. Identity disambiguation

Pending. ArtStation username, MobyGames credit ID, name + studio credits.

## 10. Reconciliation strategy

Game Artist ↔ LinkedIn — coverage varies (senior AAA artists likely; junior indie artists less so).

## 11. Save destination

Standard: `["candidate_workspace"]`. Reuses HITL visual review surface.

## 12. Build effort estimate

~2-3 weeks with clean primitives. ArtStation adapter is the meaningful per-discipline engineering investment.

## 13. First-customer demonstration scope

Pending. Plausible: "Senior environment artist for AAA fantasy RPG, 6+ years, credited shipped titles in fantasy / RPG genre, ZBrush / Maya / Substance / Unreal stack."

## 14. Ship-quality scope

Pending.

## 15. Failure modes and edge cases

Pending. Game-art-specific concerns:

- ArtStation API access under Epic ownership.
- IP / NDA-protected portfolio work — game artists often cannot show shipped work publicly. Discovery surface skews toward concept work and personal projects.
- Distinguishing pre-production concept work from production-final work in portfolios.

## 16. Open questions

- ArtStation API viability and ToS for systematic recruiting use.
- Whether to extend to tabletop / board game art as a sub-discipline or treat separately.
- IP-protected portfolio handling — recruiters in game often work from cleared portfolios with NDA caveats; how does Cloris's evaluation handle "cleared" vs. "personal" project distinctions.

## 17. Decisions captured here

- 2026-04-30 — Stub spec created per `Cloris-Multimodality-Thesis.md`. Status: draft. Promotion gated on Designer Phase 2 validation. ArtStation API viability under Epic ownership flagged as the load-bearing data-foundation question.
