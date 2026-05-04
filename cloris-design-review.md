# Cloris Design Review

## Scope
This review covers the frontend surfaces of the Cloris sourcing agent (`cloris/frontend/src/components/*`). The audit evaluates the implementation against the binding rules defined in `docs/cloris-surface-design-rules.md` and `docs/cloris-ui-spec.md`.

## Built vs Partial vs Aspirational
The frontend is largely built and functional, with a clear separation of concerns and adherence to the Svelte + hand-written CSS mandate. The core surfaces (Homescreen, Workspace, Run Report, Candidate Detail, Brief Detail, Market Detail) are implemented and successfully avoid generic SaaS dashboard patterns in favor of the specified editorial primitives (`SpecimenFrame`, `DisplayTitle`, `AmbientBanner`).

However, several components exhibit drift from the design rules, specifically around the loader primitives and dual-nav coexistence.

## Cross-cutting Concerns

### Design-System Fidelity & Primitives
- **R28 (Dual-nav coexistence)**: `AmbientBanner.svelte` violates R28. The masthead nav only includes `Monitor`, `Tools`, and `Settings`. It is missing `Briefs` and `Market`, which are explicitly required by the rule to preserve the dual mental model ("what Cloris does" vs "where the recruiter goes").
- **R26 (Editorial bylines)**: `MarketDetail.svelte` is an editorial surface ("Cloris's read") but lacks the `cloris-byline` element required by R26. It has a `section-deck market-detail-tldr` but no byline signing Cloris's work at the head.

### Information Architecture (IA)
- **R8 / R23 (Restraint and Canonical Home)**: In `CandidateDetail.svelte`, the backlink falls back to `#/'` if `source_run` is missing, rather than attempting to route back to the workspace or brief. This is a minor IA gap but acceptable for legacy data.
- **R27 (Headline vs. Article Density)**: The surfaces correctly apply the density rules. `Briefs.svelte` and `Homescreen.svelte` use headline density for stacks of cards, while `RunReportPage.svelte`, `CandidateDetail.svelte`, and `MarketDetail.svelte` use article density with breathing room and voice prose.

### Voice and Copy
- **R18 / R21 (Voice posture and Operational copy)**: The application correctly separates operational copy from character voice. Error states like "Couldn't load the run" in `RunReportPage.svelte` use plain product language without inappropriate character voice, adhering to R21.

## Code / UX Quality (Structural)
The structural quality of the Svelte components is high. The use of `$state` and `$derived` from Svelte 5 is consistent, and the separation of copy into `lib/copy.ts` prevents hardcoded strings from drifting. The fallback chains for titles (e.g., `resolveRecruiterTitleFromKey`) are well-implemented to prevent raw IDs from leaking into the UI (R2).

## The Thing You're Not Seeing
The most critical issue is the fragmentation of the loader primitives and their interaction with the copy rules. Because `Finding.svelte` ignores the `captions` prop in favor of its built-in grandmotherly quips (e.g., "Looking for my glasses…"), surfaces like `RunReportPage` and `Workspace` are passing operational loading messages (e.g., "Loading the run…") that are silently dropped. This directly violates R21, which states that loaders inside operational fetches must read as plain operational copy, not character voice.

## Prioritized Next Moves

1. **Reconcile Loaders with R21 (High Leverage, Low Effort)**
   - Determine if R21 should be updated to allow character voice in loaders, or if `Finding.svelte` should be updated to display the operational `captions` prop alongside the random animations.
2. **Fix Masthead Nav in `AmbientBanner.svelte` (High Leverage, Low Effort)**
   - Add `Briefs` and `Market` to the masthead nav to comply with R28 and restore the dual-nav mental model.
3. **Add Editorial Byline to `MarketDetail.svelte` (Medium Leverage, Low Effort)**
   - Add a `cloris-byline` element to the header of `MarketDetail.svelte` to comply with R26.