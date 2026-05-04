# Cloris surface design rules

## Why this exists

The Phase B run report (`#/run/<source>/<state_key>/<run_id>`) shipped working but visually clunky and structurally flat. This document captures the specific defects observed in that surface and abstracts them into a small set of rules that govern every Cloris surface from here forward — Phase C (Candidate Workspace), Phase D (brief library + authoring), and beyond.

The rules are deliberately short and binding. They sit alongside the existing voice rules in `/Users/sam.vangelos/Downloads/cloris.html` and `docs/cloris-copy-bank.md` but address layout / IA / information density rather than tone.

When a new surface is being designed, every rule below should be a yes/no checkbox in the implementation plan. A surface that fails any rule is not shippable.

---

## Section 1 — Defects observed (Phase B run report)

Screenshot reference: `~/Pictures/Screenshots/PICS1/Screenshot 2026-04-29 at 5.25.*.png` (seven screenshots, scrolled top to bottom).

> **Note (2026-04-30)**: D1 originally cited the run at `linkedin/2015831122/3` as the canonical example. That state directory has since been archived and the link returns 404. The defect descriptions below remain accurate as a historical record; current examples can be captured from a fresh `make audit-ui` walk under `output/audits/<timestamp>/`. Future PRs that archive a referenced run should update this doc.

### D1 — Title is a raw numeric brief id

The page headline reads `2015831122`. Backend gave us `brief_role_title=null`, `brief_id="2015831122"`. The component fell through to `brief_id` and rendered the LinkedIn-internal numeric search id as the recruiter-facing title. The title should never be a number.

### D2 — Operational metadata in the editorial header

The Timeline section is an 8-field 2-column grid: Started / Ended / Mode / Stop Reason / Resumed From / Brief / Run id / Output. Half of those are diagnostic (Brief, Run id, Output, Mode). Half are narrative (Started, Ended, Stop Reason, Resumed From). Everything renders at the same weight, so the eye reads "table" rather than "she paused on a daily limit at 11:48 PM."

### D3 — Filesystem path leaks into the report

The OUTPUT field renders `/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/output/state/linkedin/research_engineer_colombia_2015831122` and wraps to three lines, breaking the rhythm of the grid. A filesystem path is developer-facing data; it does not belong in a recruiter-facing report.

### D4 — Decisions histogram presents all outcomes as equal

The "Decisions" section reads `Total 227 · Facial No 159 · Reject 66 · Inferential Save 1 · Transferable Save 1`. There are zero saves. There is one inferential save. There are 159 facial-no decisions (filtering noise the recruiter did not ask to see). The histogram lists them in arbitrary insertion order and gives equal visual weight to "1 inferential save" and "159 facial no" — so the recruiter has to hunt to find that there's effectively nothing worth reviewing.

### D5 — One flat 200-row candidate list with no editorial layer

The "Candidates" section renders ~200 candidate names in a single ordered list with a decision label on the right (`REJECT`, `FACIAL NO`, `—`). The first three names have `—` (no terminal decision); the next ~70 are REJECTs; the next ~150 are FACIAL NOs. The list has no grouping, no prioritization, no "what should I look at" anchor, and no editorial summary. A recruiter scrolling this list cannot find the saves because there are none, but also cannot tell that quickly — they just scroll for a long time and conclude nothing happened.

### D6 — Sections render even when they have nothing to say

The "Attempt Health" section reads `last success: 17 hours ago · attempts in window: 0 · succeeded: 0 · failed: 0`. The window has no data. The section still renders, taking up vertical space and a hairline rule, just to tell the user "there is nothing here."

### D7 — Three uppercase registers stacked

The header eyebrow `§ RUN REPORT · LINKEDIN`, the section title `TIMELINE`, and the field labels `STARTED`, `ENDED`, `MODE`, `STOP REASON` are all mono-caps in close vertical proximity. The eye registers competing screams; nothing reads as the actual page title until the serif `2015831122` (which is the wrong title anyway).

### D8 — Section titles compete with body data

`PROGRESS` (mono caps eyebrow) renders directly above `3 OF 38 · 21%` (also mono caps body). The body text is supposed to be the answer; the eyebrow is supposed to be the label. Both at the same weight makes the answer feel like another label.

### D9 — No editorial summary at the top

The page opens with timeline metadata. There is no "tl;dr" — no sentence telling the recruiter what happened. A recruiter who lands on this surface should know within one second: did she find anything? where should I start? Today they have to read the whole report to figure that out.

### D10 — `—` em-dashes as filler in the candidate list

The right column of the candidate list renders `—` for any candidate with no terminal decision (the first three rows in the screenshot). The em-dash is fine as a placeholder in the card grid where it occupies a known field; in a long list it reads as a sequence of meaningless punctuation marks down the right edge before the meaningful labels start.

### D11 — Information that should be one click away is rendered inline

The Run id, Output dir, raw Brief id, full timestamps, file paths — all of these are diagnostic. They are the developer-facing equivalent of the Reference Slip on the homescreen card. We invented the Reference Slip for exactly this reason and then immediately stopped using the pattern when we built a new surface.

---

## Section 2 — Rules (binding, going forward)

Each rule is ordered by violation cost. Failures higher in the list are more visible / more brand-damaging.

### R1 — Editorial > Database

**Rule**: Every surface answers a question the user actually asks. It is not a flat dump of fields available in the response payload.

**Test**: For every section, write the one-sentence question it answers. If you can't, the section shouldn't be there.

**Examples**:
- "Did Cloris find anything?" — Decisions summary.
- "Where should I start reviewing?" — Saves list.
- "What happened during the run?" — Narrative timeline (1–2 sentences in prose, not 8 fields).
- "Where is the raw state stored?" — Reference Slip (collapsed).

### R2 — Names are recruiter-facing, never raw IDs

**Rule**: A page title, a card title, a list-row primary label is never a numeric ID, content hash, UUID, or filesystem path.

**Fallback chain for any "title" derivation**:
1. Backend-supplied human label (`brief_role_title`, `display_name`).
2. Humanized state_key / directory slug (`research_engineer_colombia` → "Research Engineer Colombia").
3. Source-typed generic ("LinkedIn search", "GitHub search").
4. Never: a numeric id or hash.

**Where raw IDs go**: Reference Slip / Catalog row only. Never primary text.

### R3 — Reference Slip pattern is universal

**Rule**: Every surface has a single collapsed "Reference Slip" / "Catalog" section that holds:
- Raw IDs (run id, brief id, candidate id).
- Filesystem paths.
- Wire-literal status / stop reason / failure kinds.
- Internal timestamps in absolute mono format.
- Anything else a developer needs but a recruiter doesn't.

The slip is collapsed by default. It opens with `+` and closes with `−` (existing pattern from `StateDirRow.svelte`).

**Anti-pattern**: rendering a "Brief" row with the value `2015831122` in the editorial body. That row goes in the Reference Slip.

### R4 — Hierarchy by recruiter priority, not by data structure

**Rule**: When a section displays multiple items, sort and visually weight by what the recruiter cares about first.

**For decision counts**: Save (and inferential / transferable / signal saves) are the headline. Reject is secondary. Facial-No / parse_failure / no-decision are noise — surface them as a single "filtered out" count, never as separate histogram bars.

**For candidate lists**: Saves first (with full visual weight), then Borderline / Inferential, then Reject (collapsed by default), then noise (collapsed by default with a count).

**For timeline / progress / attempt health**: lead with the answer (e.g. "Hit the daily limit at 11:48 PM after 3 saves and 38 candidates evaluated"), then diagnostic detail below.

### R5 — Lists need editorial layers

**Rule**: A list with N > ~10 items always has:

1. **A meaningful default sort** — most important first.
2. **Visual grouping** by category, with section labels.
3. **A count at each group header** (`Saves · 3`, `Rejects · 66`).
4. **Default-collapsed groups for low-priority / noise** with "show 159 facial-no" expand affordance.
5. **A summary line above the list** that lets the user skip the scroll if there's nothing for them ("Nothing to review yet — Cloris filtered every result.").

**Anti-pattern**: a single ordered list of 200 names with a decision label on the right. That's a database table, not an editorial report.

### R6 — Don't render a section that has nothing to say

**Rule**: If the data behind a section is empty / zero / null, the section is omitted entirely. Empty-state placeholders are for the *page* (the run has no candidates yet) — not for *every individual section* when one of them is empty.

**Test**: Walk every section of the surface with empty data. Each section should either be absent or be a deliberate, designed empty state with a useful sentence — never a row of zeros.

### R7 — One uppercase register per visual region

**Rule**: Inside a single section, mono-caps appears once. Either the section title is mono-caps (and body labels are sentence-case serif), or the section title is serif (and body labels are mono-caps). Never both.

**Spec evidence**: the Cloris brand one-pager uses mono-caps for eyebrow `§ 01`, then serif for the title `What Cloris actually is`, then sentence-case prose. Three registers, one per layer. No layer has two registers stacked.

### R8 — Strategic restraint over completeness

**Rule**: A surface ships the smallest amount of information that lets the user complete the journey it's for. Anything else lives in the Reference Slip or a future deeper view.

**Test**: For every field on the surface, ask "would the user fail their task without this?" If no, move it to Reference Slip or remove it.

**Concrete bias**: when in doubt, hide. Adding a field requires justifying its presence. The default is absence.

### R9 — No raw filesystem paths in editorial surfaces

**Rule**: `/Users/...` paths, `output/state/...` paths, and any other absolute path do not appear in editorial body text. Ever.

**Where they go**: Reference Slip, with a humanized label ("State directory · `research_engineer_colombia`") and the full path on hover or in a clipboard copy action.

### R10 — Lead with the headline, then the detail

**Rule**: Every editorial surface opens with one or two sentences (or a small set of headline numbers) that summarize the answer. The detail comes underneath.

**Run report opening should read**:
> *Limit reached. She found 0 saves and rejected 66 candidates before the daily quota cut her off. Started 7:58 PM, paused 11:48 PM.*

Not:
> [grid of 8 metadata fields]

### R11 — Density rhythms

**Rule**: A surface alternates dense and breathing sections. A page that's all 2-column grids, or all paragraph prose, or all lists, reads as monotone. Targets:

- Open with prose / a headline (breathing).
- A small grid or summary stat (dense).
- A hairline rule (breathing).
- A list (dense, but visually grouped).
- A Reference Slip footer (collapsed; dense if opened).

**Smell**: scrolling the page, every screen looks the same. That means no rhythm.

### R12 — Cap default visible items

**Rule**: Lists default to 5–10 visible items with a "show all N" expand. The page is navigable in 3 seconds; the deep dive is opt-in.

**Bias**: under-show by default, over-show on request.

### R13 — Overflow is a content problem, not a CSS problem

**Rule**: When content (a path, a hash, a long stop_reason) wraps awkwardly inside a cell, the fix is to remove that content from the editorial body — not to add `word-break: break-all` to the cell.

**Test**: at 1280px width, every editorial body row fits on one or two lines. If it doesn't, the content is too long and belongs elsewhere.

### R14 — Editorial verbs over operational verbs in user-facing copy

**Rule**: Section titles, link text, and call-to-action verbs are recruiter-language, not wire-literal.

**Examples** (good → bad):
- "Read the report" → "Run summary"
- "Catch a brief up on the market" → "Update market intelligence"
- "Pick up where I left off" → "Resume execution"

**Already lives in `docs/cloris-copy-bank.md`** — this rule re-states for layout/IA reviewers.

### R15 — Use the existing primitives

**Rule**: Before adding a new component, check if a primitive already covers it.

| Need | Existing primitive |
|---|---|
| Click-to-expand details with raw IDs | Reference Slip (`StateDirRow.svelte`) |
| CREATING loader — Cloris is making something | `Refining.svelte` (sewing; "Stitching something special…" — see R19) |
| SEARCHING loader — Cloris is fetching something that exists | `Finding.svelte` (glasses; "Looking for my glasses…" — see R19) |
| WAITING loader — recruiter is waiting for an opaque, leavable backend op | `Monitoring.svelte` (CRT TV; "Waiting for Matlock…" — see R19) |
| INITIALIZING loader — Cloris is firing up / setting up | `Learning.svelte` (kettle; "Firing up the kettle…" — see R19) |
| Rotating caption strip (used by all four loaders) | `RotatingCaption.svelte` |
| Typeset specimen wrapper (label cuts the border) | `SpecimenFrame.svelte` |
| Section title typographic duo (head + italic accent) | `DisplayTitle.svelte` |
| Editorial deck paragraph below a DisplayTitle | `.section-deck` (`components.css`) |
| Marginalia eyebrow + title layout | `.section-head` + `.section-num` (`components.css`) |
| Short typeset section divider hairline (56px) | `.section-rule` (`components.css`) |
| Homescreen verb strip (chapter-header band) | `RunningFolio.svelte` |
| Status pill (working / completed / stalled / no-record) | `.card-status--*` (`components.css`) |
| Editorial section eyebrow (legacy stacked layout) | `.homescreen-section-eyebrow` (`§ COMPOSE` / `§ MARKET` etc.) — superseded by `.section-num` for new surfaces |
| Editorial back link | `.homescreen-look-through` |
| Wood hairline section divider | `border-bottom: 1px solid var(--wood)` on a header |
| In-motion mini-list capped at 5 | `Homescreen.svelte` mini-list pattern |

If the new surface needs a primitive that doesn't exist, add it to this table when you build it.

**Canonical primitive bank**: `/Users/sam.vangelos/Downloads/cloris-components.html` is the brand-spec component lab — twenty named specimens (toast, ledger, empty state, recipe-card stat, postcard, snickerdoodle tray, Matlock badge, etc.) ordered along a restraint spectrum. Before designing a new primitive, look there first; the in-repo table above is what we've shipped, the lab is what's been designed.

### R16 — Spec palette (binding)

**Rule** (re-stated from earlier slices):
- Cream / linen / wood / ink: paper + type.
- Mustard: warm secondary accent.
- Terracotta (peach): emotional accent + primary CTA.
- Blue (`--blue-pencil*`): annotation only — focus rings, dividers, selected-card border. **Never a background. Never a CTA.**

### R17 — Mono-caps minimum 14px (revised 2026-04-30)

**Rule** (revised from 12px floor): mono-caps text floor is **14px (`0.875rem`)** for any element that conveys meaning. Below that is parsing-friction territory on desktop, especially when the element is doing semantic work (status pill, field label, eyebrow, ribbon count). The original 12px floor was set when mono-caps appeared sparingly in marginalia; once the typography expanded across status pills, ribbon counts, and field labels, the floor had to rise.

Decorative micro-labels with no functional payload should be removed (per R22), not made small.

When mono-caps text MUST be small (rare — diagnostic Reference Slip values when nothing else fits), prefer dropping the uppercase transform and using mono sentence-case at 14px. Sentence-case mono parses at small sizes; uppercase mono does not.

### R18 — Voice posture: Cloris is the subject

**Rule** (re-stated from `docs/cloris-copy-bank.md`):
- Cloris narrates her own work; she does not address the user.
- "She paused on the daily limit" beats "Your run hit the governor." beats "RUN PAUSED."
- High-stakes / error states drop character entirely. Editorial voice survives only in calm and ambient surfaces.

### R19 — Four-kind loader contract (revised 2026-05-03)

**Rule**: Every loader on every surface communicates one of four kinds of work. Pick the kind from what Cloris is actually doing — never by aesthetic, never at random. The graphic AND the caption together do semantic work; the recruiter learns the kind from both halves working as a pair.

| Kind             | Component    | Motion graphic | Anchor caption                |
| ---------------- | ------------ | -------------- | ----------------------------- |
| **CREATING**     | `Refining`   | sewing needles + yarn | "Stitching something special…" |
| **SEARCHING**    | `Finding`    | glasses + magnifier   | "Looking for my glasses…"      |
| **WAITING**      | `Monitoring` | CRT TV         | "Waiting for Matlock…"        |
| **INITIALIZING** | `Learning`   | kettle + steam | "Firing up the kettle…"       |

Pick the kind:

- **CREATING** = Cloris is *making* something. A sourcing run in flight, a brief iterating, a brief diff being synthesized, a market artifact rebuilding.
- **SEARCHING** = Cloris is *fetching* something that already exists. Run report load, brief detail load, workspace load, candidate load, settings index, identity-reconciliation list, route redirect resolution. Most loaders are this kind.
- **WAITING** = the recruiter is genuinely *waiting* for an opaque, leavable backend operation. Long market-research synthesis, slow LLM calls the user can walk away from. The recruiter mental model is "she's on it, I can come back later."
- **INITIALIZING** = Cloris is *firing up* / *setting up*. Reflection-session boot, intake boot, app launch splash, anything with a "she's just getting going" beat.

The four components are visually interchangeable at a call site (same sizes, same frame ground, same caption contract) so the choice is editorial, not structural. A surface that uses Refining for a fetch reads *"Cloris is making your data"* — wrong. A surface that uses Finding for an active run reads *"Cloris is hunting"* when she should be making — also wrong.

`RotatingCaption` is shared by all four — three short captions on a ~1.6s cross-fade read more like a moment with Cloris than a frozen string. Reduced-motion holds the first caption.

**Captions**: each component bakes its anchor caption in as the default. Most call sites just write `<Finding size="medium" />` (or the right component for the kind) and the anchor renders. Long-running surfaces can pass a small rotating set in the same kind register (`loaderRotatingInitializing`, `loaderRotatingWaiting` in `lib/copy.ts`) so the wait reads as a moment, not a frozen string. Per-site override is allowed but discouraged — the four anchors are the contract. Voice register at all times; no operational "Loading…" copy in any loader caption.

**Min-display**: the default loader posture is "appears only as long as the operation actually runs." `stickyTrue` (`lib/minDisplay.svelte.ts`) is opt-in with a defended `minMs` and a code comment citing the actual latency distribution of the operation behind it. The Phase G follow-up audit retired the 4-second default floor — it gated ~14 fast localhost fetches behind ceremony that didn't earn its place. If you reach for `stickyTrue` again, both halves must hold: (1) the loader graphic carries narrative weight that genuinely needs N seconds to be readable, AND (2) the operation latency is provably sub-N. If either fails, no floor.

**Empty states are not loaders.** The "she's idle" or "no items yet" case should not borrow a loader graphic to fill space — using the CREATING graphic for an idle state lies about what Cloris is doing. The right move is a static `EmptyState` primitive (see component-lab specimen 08); for now a small number of empty-state surfaces still use `Refining` decoratively as a placeholder. These are tracked for migration; new empty states should not adopt the pattern.

**Anti-patterns**:

- Random graphic dispatch on every mount (the recruiter sees a different loader for the same operation across reloads — the graphic does no semantic work, it's wallpaper).
- Using one component for every kind of work (semantic mismatch on every surface that isn't that kind).
- Using the CREATING graphic for an empty state (lies about what Cloris is doing).
- Re-adding `stickyTrue` across the app to "make loaders feel weighty" (the audit already rejected this; the loader's job is to indicate the operation, not pad it).
- Collapsing the four kinds into two ("retrieval vs production") — the WAITING and INITIALIZING beats need their own register, and recruiters do read them differently.

### R21 — Operational copy is plain product language; voice copy is character (added 2026-04-30; loader caveat added 2026-05-03)

**Rule**: Two registers, separated by purpose.

- **Operational copy** is what the user reads to *understand the product*: nav labels, status pills, ribbon counts, action buttons, error messages. It must be plain product language a first-time recruiter would understand without onboarding. **No metaphors that obscure function. No character voice. No design-identity language masquerading as product taxonomy.**
- **Voice copy** is what makes Cloris feel like a person: italic footnotes inside specimen frames, deck paragraphs under DisplayTitle, success confirmations ("Cloris is on it."), splash captions, **and loader captions (per R19 revised)**. Voice copy is bonus, not load-bearing.

The two NEVER overlap with one carve-out: **loader captions are voice-register per-kind anchors, not operational per-site strings.** A loader is communicating "Cloris is doing one of four kinds of work" — the kind is conveyed by both the graphic AND the caption together. R19 (revised) names the four anchors: "Stitching something special…" (CREATING), "Looking for my glasses…" (SEARCHING), "Waiting for Matlock…" (WAITING), "Firing up the kettle…" (INITIALIZING). The original R21 example "Loading the run…" (operational) is no longer the ideal — that's the SEARCHING anchor's job now. Outside the loader carve-out, the rule still binds: nav tabs, status pills, error messages, and other operational chrome stay plain.

A nav tab is still operational ("Active" / "Paused"), not metaphor ("Front of File" / "Filed Away"). Voice belongs in voice-copy zones; operational belongs everywhere else.

**Test**: a recruiter who has never seen Cloris before should be able to navigate the homescreen and read a run report without consulting documentation. The loader captions are part of the editorial register the recruiter reads as voice — they don't need to be operational because the loader's job is registered by the graphic + caption pair, not by the literal string.

### R22 — Eyebrows are labels, not ornaments (added 2026-04-30)

**Rule**: Glyphs (§ / ¶ / † / decorative typographic ornaments) earn their place only when they convey semantic meaning.

- Eyebrows are functional mono-caps labels (indicating section type or context). They render as plain words: "COMPOSE" / "DISPATCH" / "DO" / "FRONT" / "RUN REPORT". No § prefix.
- Decorative glyphs that don't convey meaning are removed. Section markers can use no glyph at all, or a peach left-rule, or some other quiet device — but not a borrowed-from-print typographic ornament that reads as noise to a UI user.
- The same rule applies inside running prose: don't sprinkle § / ¶ / † through paragraphs as decoration. They're either content (a real footnote anchor) or they're absent.

**Test**: a screen reader should make sense of every eyebrow. If the eyebrow only works as decoration (it'd read as "section sign COMPOSE" and confuse the user), the eyebrow is wrong.

### R23 — Information has one canonical home; redundancy must justify itself (added 2026-04-30)

**Rule**: Every fact appears once unless restating earns its place.

- The save count, reject count, status, candidate total each have ONE primary location.
- A second restatement is allowed if it serves a clearly different purpose at a clearly different scale. The classic example: a tl;dr summary sentence ("Limit reached. 2 saves across 227 candidates.") is allowed to restate counts that the structural histogram below also shows, because the tl;dr is the *answer* and the histogram is the *evidence*.
- "Where to start" sentences plus group headers carrying the same count is NOT a justified restatement (they're at the same scale); pick one.
- The default is restraint.

**Test**: walk the surface top-to-bottom. For every restated fact, name the rationale. If the rationale is "structural completeness" or "the data is also available here," remove the restatement.

### R24 — One canonical wording per state (added 2026-04-30)

**Rule**: Status and action labels live in one source of truth (`lib/state.ts` for state-kind labels, `lib/copy.ts` for action labels). No raw API enums leak into editorial body text.

- `clorisStateLabel(kind)` is the canonical source for pill text and any narrative reference to a state-kind.
- Run-report `statusLabel(r)` mirrors `clorisStateLabel` and they should not drift.
- Raw values like `governor_limit_reached` (API enum) never reach the user — they're routed through a presentation function (`clorisStopReasonLabel()` or similar) that returns plain English.
- Action verbs ("Stop", "Resume", "Read the report") live in `copy.ts`. Hardcoded duplicates in components are violations.

**Test**: grep the codebase for `.replace(/_/g, " ")` on status fields → zero matches. Grep for raw enum values in JSX/markup → zero matches.

### R25 — Reserved (added 2026-04-30; placeholder for future principle)

(Slot reserved as principles accumulate. R20 is reserved for "dark surface used at most once per page" pending wood-deep masthead acceptance review.)

### R26 — Editorial bylines (added 2026-05-02)

**Rule**: Every editorial surface signs Cloris's work at the head. Bylines render as Instrument Serif italic in `--ink-meta`, single line, dated when a date is available. The byline frames the surface as Cloris's dispatch — not the system's read-out, not a passive status header. Surfaces already bylined within their content (e.g. MarketDetail's "Cloris's read" stanza) don't double-byline.

Sites that carry a byline today: RunReportPage (`runReportByline`), Workspace (`workspaceByline`), CandidateDetail (`candidateDetailByline`, omitted when `first_seen_at` is null), StateDirRow card stack (`cardByline`, only on actionable states — `paused` / `interrupted` / `lost-track` / `stalled`).

Byline copy lives in `src/lib/copy.ts` as functions, not constants — each byline depends on dynamic data the component passes in.

**Anti-pattern**: A status read-out at the top of an editorial page that doesn't acknowledge Cloris as the author ("Run completed at…" instead of "Cloris's report — Apr 28, 7:58 PM"). An empty byline element rendered when no date is available — skip the element entirely instead.

### R27 — Headline density vs. article density (added 2026-05-02)

**Rule**: Stacks of cards (homescreen Needs Attention, brief library, run-report grouped candidates) are read as headlines: scannable, dense, one foveal hit per row. Detail pages (candidate detail, brief detail, market detail, run report body) are read as articles: full editorial register, breathing room, longer voice prose.

Cards do not adopt article density; articles do not collapse to headline density. The Two-Register Card is the headline pattern; SpecimenFrame surfaces are the article pattern. Density and voice scale with the surface's reading mode.

**Example**: A paused card carries a one-line byline ("Cloris paused — your call.") not a paragraph of italic Cloris voice. A candidate detail page carries a byline, section rules, voice prose, and full-width fields — it breathes.

**Anti-pattern**: A stack card with a paragraph of italic Cloris voice (article density on a headline surface), or a candidate detail that strips its byline + section rule + voice prose to "fit more above the fold" (headline density on an article surface).

### R28 — Dual-nav coexistence (added 2026-05-02)

**Rule**: The verb strip on the homescreen (DISPATCH, RESUME, COMPOSE, REVIEW, MARKET) is Cloris's action vocabulary — verbs she does *for* the recruiter. The masthead nav (BRIEFS, MARKET, MONITOR, TOOLS, SETTINGS) is system surface navigation — places the recruiter goes.

Both can name the same destination when the destination has both a Cloris-action framing AND a system-surface framing. MARKET is the canonical example: the verb tile uses Cloris's verb form ("Learn about the market") and the masthead uses the noun form ("MARKET"). The duplication is intentional and load-bearing — it preserves the dual mental model of "what Cloris does" vs "where the recruiter goes."

**Anti-pattern**: Using the same verb form in both navs (collapses the register split). Removing one of the navs to "deduplicate" (loses the dual mental model the rule formalizes).

Apply this to every new surface PR before it ships:

- [ ] **R1**. Each section answers a one-sentence question. List those questions in the plan.
- [ ] **R2**. No raw IDs / hashes / paths in any title or list-row primary label. Fallback chain documented.
- [ ] **R3**. Reference Slip exists and holds all diagnostic data.
- [ ] **R4**. Lists and histograms ordered by recruiter priority, not data-structure order.
- [ ] **R5**. Lists with >10 items have grouping, counts, default-collapsed noise.
- [ ] **R6**. Empty / zero sections are omitted, not rendered as zeros.
- [ ] **R7**. One mono-caps register per section.
- [ ] **R8**. Every field justified; bias toward absence.
- [ ] **R9**. Zero `/Users/...` or `output/state/...` paths in editorial body.
- [ ] **R10**. Headline / tl;dr at the top of the surface.
- [ ] **R11**. Density rhythm — alternating dense / breathing sections.
- [ ] **R12**. Default-visible items capped at 5–10.
- [ ] **R13**. Nothing wraps awkwardly at 1280px.
- [ ] **R14**. Section titles + link text in recruiter language, not wire literals.
- [ ] **R15**. Reused existing primitives where possible; new primitives added to §3.R15 table.
- [ ] **R16**. Palette discipline: terracotta accents, blue annotation-only.
- [ ] **R17**. Mono-caps ≥ 14px (revised 2026-04-30 from 12px floor).
- [ ] **R18**. Voice posture: Cloris is the subject, not the user.
- [ ] **R19**. Loader matches the kind of work: `Refining` (CREATING) / `Finding` (SEARCHING) / `Monitoring` (WAITING) / `Learning` (INITIALIZING). No random graphic dispatch. Anchor caption from `lib/copy.ts` (or a kind-aligned rotating set for long surfaces). No default min-display floor; `stickyTrue` is opt-in with a defended `minMs` and a code comment.
- [ ] **R21**. Operational copy is plain product language; voice copy is character. No mixing.
- [ ] **R22**. Eyebrows are labels, not ornaments. No decorative § / ¶ glyphs.
- [ ] **R23**. Every fact appears once unless restatement is justified by purpose + scale.
- [ ] **R24**. One canonical wording per state, sourced from `lib/state.ts` / `lib/copy.ts`. No raw API enums in editorial body.
- [ ] **R26**. Editorial bylines on every editorial surface. Instrument Serif italic `--ink-meta`, dated, Cloris-as-author.
- [ ] **R27**. Headline density on stacks; article density on detail pages. Never cross.
- [ ] **R28**. Dual-nav coexistence: verb strip = Cloris's actions; masthead = system surfaces. Both can name the same destination.

---

## Section 4 — Run report refactor (concrete fix list)

Direct application of the rules to the Phase B surface that generated this document. Tracked as the next implementation slice (task #36 — *Apply editorial rules to RunReportPage*).

### Header
- **R2, R10**: Title falls back to humanized state_key when brief_role_title is null and brief_id is numeric. (`research_engineer_colombia` → "Research Engineer Colombia".)
- **R10**: Add a tl;dr line directly under the title — *"Limit reached. 0 saves, 66 rejects across 227 candidates. Started Apr 28, 7:58 PM; paused 11:48 PM."*
- **R8**: Drop the source label from the eyebrow if it's already in the URL / state.

### Timeline section
- **R1, R8**: Reduce from 8 fields to 3 (Started / Ended / Stop reason). Mode and Resumed-from collapse into a single sentence ("Resumed from run #2"). Run id / Brief id / Output dir → Reference Slip.
- **R3**: Run id, Output dir, raw Brief id move to a Reference Slip footer.
- **R7**: Section title in serif sentence-case ("Timeline"), field labels stay mono-caps. Or vice versa. Pick one.

### Progress section
- **R6**: If `work_unit_progress.kind !== "counts"` or all counts are zero, omit the section.
- **R8**: When shown, render *one* number-ful line ("3 of 38 done · 29 queued") plus the bar. Drop the queued / in_progress / done / skipped / error sub-grid — that's diagnostic, lives in the Reference Slip.

### Attempt health section
- **R6**: If `total_attempts_in_window === 0`, omit. Replace with a one-line note inside the Reference Slip ("Last success 17 hours ago.").
- **R8**: When shown, render a single sentence ("Last success 12 minutes ago. 9 of 12 recent attempts failed — rate limited.") not a 5-cell field grid.

### Decisions section
- **R4, R5**: Reorder by recruiter priority: Save → Inferential / Transferable / Signal Save → Reject → "Filtered" (one bucket including Facial No, parse failures, etc.). Surface the noise count as a single grouped number ("Filtered: 159"), not five rows.
- **R10**: Lead with the headline number ("0 saves") in a real heading, with the rest as supporting detail.

### Candidates section
- **R5**: Group by decision class:
  - **Saves** (Save / Inferential Save / Transferable Save / Signal Save) — full list, no cap, full visual weight.
  - **Borderline** (Facial Borderline) — full list, slightly muted.
  - **Rejects** — collapsed-by-default with "Show 66 rejects" affordance.
  - **Filtered** — collapsed-by-default with "Show 159 filtered" affordance. Noise.
- **R10**: Section opens with "Where to start: Cloris saved nothing in this run. Most recent rejects below."
- **R12**: Within each group, default to first 10 visible with "Show all N" expand.
- **R8**: Drop the right-edge `—` em-dash for candidates without terminal decisions. Either omit them or surface a meaningful state ("In progress").

### Reference Slip (new on this surface)
- Add at the bottom of the report, collapsed by default.
- Fields: Run id (`#3`), Brief id (`2015831122`), Brief content hash, Output directory (full path), State directory, Resumed-from chain (raw IDs).

---

## Section 5 — How this document evolves

- This doc is the binding rule set; PRs that violate any rule must either fix the violation or amend this doc with the new rule.
- New patterns / primitives / palette decisions discovered in future slices get appended in their relevant section.
- Per-surface defect lists (Section 1) accumulate as we build — each new surface's first review pass produces a defect list that informs Section 4-style fixes.
- Section 4 (run report refactor) is consumed as the implementation lands; once shipped it's deleted from this doc and replaced by the next surface's refactor list.
