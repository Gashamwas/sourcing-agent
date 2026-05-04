# Cloris trial walk — day 1, in persona

A senior recruiter at an A24-tier company sits down with Cloris for the first time. They've been hired to find the Head of Applied AI Lab — Executive Director band, BFSI builder, NYC, post-2022 GenAI evidence, sparse market. They've used six sourcing tools before this one. They have two hours to decide whether to integrate Cloris into their workflow.

This is what those two hours feel like.

I walked it on the dev server at `http://127.0.0.1:8765/`, browser-driven, with the on-disk `Head of Applied AI Lab` brief ([config/brief-head-ai-lab-nyc-v2.json](config/brief-head-ai-lab-nyc-v2.json)) as the imagined hire. Then a focused day-5 supplement to feel where the friction signature shifts. The screenshots and per-step notes live at `/tmp/cloris-trial-walk/`.

Out of scope per the ask: the editorial dead-copy audit just shipped, typography pass, principal-audit findings, in-flight trial-blocking fixes. This is about the lived experience.

## Correction (after spot-check)

The first version of this doc landed on Pattern #2 as an existential — *"Cloris is a list-maker, not a judge"* — based on `0 of 77 candidates have a save_reason`. That claim is **wrong on the existential, right on the surface symptom**.

The substrate IS judging. Every SAVE-class candidate's `terminal_payload_json` carries a `full_decision.rationale` field with substantive editorial prose. Verbatim from one save row in [output/state/linkedin/1957683706-clean-20260413/runtime_state.sqlite3](output/state/linkedin/1957683706-clean-20260413/runtime_state.sqlite3):

> *"Solid enterprise GenAI builder at Mastercard with production RAG/agentic workflow ownership and clean 8-year trajectory, but limited to single internal deployment with no multi-customer delivery, customer-engineering exposure thin, low-confidence save."*

Across the candidates table, **114 / 114 SAVE-class candidates have a `full_decision.rationale`**. Cloris has been writing substantive per-candidate judgment the whole time.

The control plane is reading the wrong key. [cloris/control_plane.py:1179](cloris/control_plane.py:1179):

```python
for key in ("save_reason", "reason"):
    value = payload.get(key)  # ← top-level lookup; nothing here
    if isinstance(value, str) and value.strip():
        save_reason = value.strip()
        break
```

`payload["save_reason"]` and `payload["reason"]` don't exist — the rationale lives at `payload["full_decision"]["rationale"]`. The API returns `save_reason: null` to the frontend, and the candidate detail surface dutifully renders *"No save reason recorded for this candidate yet."* on every save.

**This is a one-line wiring fix at the API layer**, not a strategic retreat from "Cloris should be a judge."

That correction reframes Pattern #1. The headline framing — *every editorial promise needs a substrate-level guarantee* — still holds. But the most-cited example was a wiring bug, not a substrate failure. The substrate kept the promise; the editorial layer just isn't reading from where the substrate wrote. Re-walking the other Pattern #1 examples through the wiring-vs-substrate lens (below) finds the same shape on most of them. The actual high-leverage call is "**wire the editorial layer to the substrate that's already there**," not "shrink the editorial promises until the substrate catches up." Pattern #2 has been rewritten in place; Pattern #1's fix posture has been replaced with the substrate-vs-wiring split.

## The walk

### First load — the home

The page is beautiful. Cream paper, brown header bar, the wordmark `Cloris ╳ Just like Grandma used to make source.` Editorial typography that telegraphs *we care about how this reads*. Fraunces serif, italic display in `Instrument Serif`, mono caps for metadata. The first impression is: this is *designed* in a way the other sourcing tools weren't.

The tagline lands wrong on a senior IC at a marquee company. "Grandma" framing is twee. I notice it, file it, move on.

The home gives me three things to do:

1. **A verb tile bay** at the top: `COMPOSE · DISPATCH · REVIEW · MARKET` (the labels in [VERB_TILES](cloris/frontend/src/lib/copy.ts) — and they read more like internal process taxonomy than recruiter verbs. *DISPATCH*?). Note: by my day-5 visit these had become `WRITE · START · REPORT · MARKET` — a sharp improvement that makes the day-1 labels feel retroactively cute-but-confusing.

2. **A "Start a search" panel** on the left, listing ~25 briefs to pick from. The brief I care about — Head of Applied AI Lab — isn't in the visible window; I'd have to scroll. Two big buttons below the picker (`START SEARCH`, `PULL & RESUME`) are disabled, with no microcopy telling me why. I infer "I have to pick one first." That's the recruiter doing the system's work.

3. **A "Needs attention" panel** in the middle, four cards, all red or yellow. The top one — *my* brief — reads:

```
LINKEDIN · LINKEDIN · #1957683706 ◆       [Lost track]
Head of Applied AI Lab                    [Investigate →]
Cloris lost track.
```

`LINKEDIN · LINKEDIN` is doubled. `#1957683706` is a state-directory pointer that means nothing to a recruiter. `◆` is an unlabeled glyph. And the first label on my brief is **Lost track**, with the prose `Cloris lost track.`

The home page's framing is *Needs attention. These are the briefs that need a hand. **She** keeps them up front.* On day 1, with no orientation, two questions land at once: (a) who is "she," and (b) why is everything red.

There is no positive-state list. No "here's what's running, here's what's healthy." The shape of the home is *only* alarm cards. The product feels chronically wounded before I've done anything.

What I'm thinking when I leave: *OK, I'll click `COMPOSE` to make a brief. That seems like the obvious first step for a trial.*

### Author a brief — the wizard

This is the surface that earns the editorial tone.

`INTAKE — START · Tell me about the role.` Italic deck: *I'll ask a few questions, then read it back so you can sharpen it before I start looking.* CTA: `Begin with Cloris`. Bottom-right: `Resume an earlier draft →` as the escape hatch.

The deal is named clearly: *I'll read it back so you can sharpen it before any search starts.* I exhale. This is going to be a conversation, not a 40-field form.

I walk through chapters 2 through 5. The questions are ones a senior recruiter would naturally answer:

- *What's the role called?* / *What does this role actually deliver — the team and the why?*
- *Walk me through the capabilities that matter — what would the right person be able to do?* (Single open-ended field, with the promise *"Free-form. I'll structure it on the read-back chapter."*)
- *Tell me about people you'd hire today.* / *Anyone who looks similar on paper but isn't right?*
- *Which surfaces should I scan?* (LinkedIn checked. GitHub disabled with italic *— coming with Phase F*. So is Researcher.)

I type substantively: a paragraph about RAG, agentic workflows, eval harnesses, BFSI workflow credibility, ED-band, NYC. Four exemplars (Pratik Shah, Hungjen Wang, Ashish Garg, Bhavish Balhotra). Four anti-patterns (CPAIO, field CTO, trade surveillance, top-tech with no BFSI). Geography hard gates. Quality-over-volume. ~600 words of structured intent. Five minutes of careful typing.

The CTA shifts from `Continue with Cloris` to `Read it back`. Clever — the wizard is signaling we're done with intake.

I click. The next surface is captioned *Cloris's understanding* with the deck *Here's the brief I'd run with. Edit anything that's off — when it reads true, file it.*

Here's what's actually in the form:

- Role title: **Existing Role**
- Capability area: **Product engineering** / *Ships customer-facing systems end-to-end.*
- Building it: *Owns architecture and ships.*
- Using it: *Maintains existing features.*
- Edge cases: *Borderline = full eval.*
- Patterns we're not chasing: empty
- LinkedIn checked

None of the conversational answers I just typed in chapters 2–5 made it through. The "read-back" is reading back placeholder defaults that have nothing to do with what I just spent five minutes saying. (The OnboardingFlow code says it itself: *"D4 will later interpose an LLM synthesis between earlier chapters and the review chapter; the chapter shells already exist."* — see [OnboardingFlow.svelte](cloris/frontend/src/components/OnboardingFlow.svelte). The read-back is theater because the synthesis step doesn't exist yet.)

I click `File this brief` anyway. It errors with *"A brief with this role title already exists. Pick a different title or edit the existing brief from the library."* (Honest error; bottom-of-form placement makes me scroll to find it; no inline rescue affordance.) I rename to `Head of Applied AI Lab` → same error (real brief already exists). Suffix to `Head of Applied AI Lab — Trial Walk` and file. The system creates a brief with URL slug `existing_role` (not anything matching what I typed) and a brief detail surface that is, again, the stub defaults.

The wizard's most-visible promise — *"I'll read it back so you can sharpen it"* — is structurally false on day 1. The "Older brief notes Cloris hasn't promoted yet (1)" drawer doesn't even contain my answers; it has the inherited `linkedin_project_id` from the placeholder brief. **The five chapters of typed intent vanished into a void with no recovery path.**

What I'm thinking when I leave: *the wizard didn't actually do what it said. I'm going to abandon this brief and use the existing Head of Applied AI Lab one, since it's at least populated.*

### The real brief detail (`#/brief/1957683706`)

This surface lands. *Cloris's understanding — last modified Apr 27, 2026.* Three capability areas, each named with `(HARD GATE)` flags where applicable. Building / Using / Edge cases all populated with the real depth-distinction text from the JSON. Seven non-fit patterns spelled out precisely.

This is what the wizard's read-back was supposed to produce. I read it as a recruiter and think: *yes, Cloris understands this role*.

Two cracks: one editorial, one operational.

The editorial crack is *"This brief is in the legacy layout. The next edit will move it into a versioned folder."* I don't know what "legacy layout" or "versioned folder" mean. They're admin vocabulary on a recruiter surface.

The operational crack is *"Cloris doesn't yet know which LinkedIn project to save into."* But the brief's own URL is `1957683706` — the LinkedIn project ID. The data is right there. The surface is lying about its own state.

The brief detail also has **no "Launch a search from this brief" CTA**. The only forward affordance is "Open the workspace for this brief." To launch, I have to leave this page, find the brief in the home picker, click Start search there. The most natural action — *search for people for this brief* — is not on the brief surface.

### Open the workspace

I click *Open the workspace for this brief →*. After ~10 seconds:

```
                      Couldn't load that workspace.
              Network error contacting /api/workspace/1957683706
```

I reload. Same error. I reload again. Same error.

The truth — which I only know because I dropped to the API: the frontend has a hardcoded **5-second** request timeout ([cloris/frontend/src/lib/api.ts:75](cloris/frontend/src/lib/api.ts), `REQUEST_TIMEOUT_MS = 5_000`). The Head of Applied AI Lab workspace API takes ~14 seconds to return — 170KB, 77 saved candidates, the most data-rich workspace in the system. The fetch *always* times out before the data arrives. The recruiter's day-1 view of their flagship brief is a permanent error screen.

The mismatch is jarring. The error heading is in Fraunces serif (*Couldn't load that workspace.*) — voice. The body says *Network error contacting /api/workspace/1957683706* — engineering. There's no retry button, no "this is taking longer than expected — try again?", no partial render. The only way out is `← BACK TO ACTIVE BRIEFS`.

This is the most expensive screen in the day-1 walk. It's the flagship brief that fails. The receipt-style run report sends me to this door, and the door doesn't open.

### Triage candidates

The workspace is unreachable, so I navigate directly to a candidate by URL: `#/candidate/1957683706/3064` (Kiran Nellore — the first save in the Head AI workspace). The single-candidate fetch is small enough to fit under the 5-second timeout, so this surface actually loads.

```
CANDIDATE
LINKEDIN
Cloris flagged this Apr 14, 2026.

Kiran Nellore
Head of Applied AI Lab

[View brief criteria]
YOUR STATUS: Shortlist · Contacted · Parked · Hidden

No save reason recorded for this candidate yet.

DECISION   Inferential save
PROFILE    https://www.linkedin.com/talent/profile/AEMA...
           [URL extends past the right edge of the page]
```

Three things hit me at once.

**One.** The page's `scrollWidth` is **8,893 pixels** on a 1280-wide viewport — measured. A horizontal scrollbar appears. The page visibly breaks because the LinkedIn URL contains a long `highlightedPatternSource` query string (Cloris's match terms baked into the LinkedIn URL) that doesn't wrap. The page is layout-broken because of one URL.

**Two.** *No save reason recorded for this candidate yet.* Cloris saved this person as `Inferential save` but recorded no reasoning. I came here to judge the candidate based on Cloris's read of them — and there is no read.

**Three.** The PROFILE field is a raw URL, not "Open in LinkedIn." Visually it's a long opaque string that wraps and overflows. Squinting at the URL I can see fragments — `Bank%20of%20America`, `Goldman%20Sachs`, `JPMorgan`, `RAG`, `LLM`, `ED` — Cloris's BFSI institution and seniority patterns are visible to me only because they leaked into the URL display, not because anyone decided to surface them.

I check the API directly. Maybe Kiran is special.

Across all 77 saves on the Head of Applied AI Lab brief, **0 of 77 candidates have a `save_reason`.** Every single one is `None`. The `No save reason recorded for this candidate yet.` line isn't a per-candidate gap — it's the structural reality of the workspace.

Cloris saved 77 candidates over April-May for the most-developed brief in the system, and there is no recorded reason for any of them. The triage surface is a list of LinkedIn URLs.

The surface infrastructure is right: stage tags (Shortlist / Contacted / Parked / Hidden), a notes textarea, *How was Cloris's judgment? — Useful / Wrong / Off rubric*, a Reference Slip behind a fold, a "View brief criteria" pop-out. The shape is correct. The substance — the reasoning Cloris is asking me to evaluate — isn't there.

What I'm thinking when I leave: *I have to evaluate every save by clicking the LinkedIn URL and reading the candidate myself. Cloris is a list-maker, not a judge. If I'm going to do all the evaluation work anyway, what is Cloris doing for me that LinkedIn Recruiter Search doesn't already do?*

### Read a run's report

This is the strongest surface in the day-1 walk.

```
RUN REPORT · LINKEDIN

LINKEDIN                                       [Stopped]
Cloris's report — Apr 14, 6:24 AM.

Head of Applied AI Lab

Interrupted. 22 saves, 59 rejects across 505 candidates.

This is the receipt for one run. To act on these candidates, open the workspace.
[Open the workspace for this brief]

Where to start
SAVES   22
  Kiran Nellore               INFERENTIAL SAVE
  Dr. Nate Bachmeier          SAVE
  Robert Huntsman, CFA, FRM   SAVE
  Mike Harmon                 INFERENTIAL SAVE
  Martin Dailerian            SAVE
  + 8 more saves. Open the workspace to review them.

Rejects 59 +     Cloris reads these on the next run to sharpen the calibration.
Filtered 424 +   Cloris reads these on the next run to sharpen the calibration.

Timeline
Started     Apr 14, 2026, 12:57 AM
Ended       Apr 14, 2026, 6:24 AM
Stop reason Lost the browser session

Progress
9 of 16 · 69%

Attempt health
Last success 19 days ago.
View live monitor →
```

This surface knows what it is. It calls itself *a receipt*, says action lives elsewhere, points the recruiter to the workspace. The numbers are clear: 22 / 59 / 505. The deck collapses what happened into one sentence. The Timeline block is plain English (`Lost the browser session`) instead of code (`browser_disconnect_unrecovered`). `Last success 19 days ago.` is honest in a way that hurts to read but earns trust — Cloris is telling me *this brief is broken at the worker level*, not just sleeping. `9 of 16 · 69%` tells me Cloris was working through a planned set of 16 search strings and got 9 done. *Brief edited since this run started.* is a real, useful caveat tucked into the figure footer.

Two cracks on this surface. The header badge says *Stopped*; the deck says *Interrupted*. Two different terms for the same event. And the most-pointed-at link on this page — *Open the workspace* — leads to the broken workspace.

What I'm thinking when I leave: *OK — Cloris CAN summarize a run. The summary is the most useful thing in the product so far. But it's pointing me to a workspace that doesn't load. The lesson is: trust the run report, ignore the workspace until they fix it.*

### The Live Monitor

I click *View live monitor →*. This is a different surface — operational, per-run.

```
RUN #14 · LINKEDIN · 1957683706-CLEAN-20260413
Head of Applied AI Lab
STATUS · INTERRUPTED · browser_disconnect_unrecovered (Lost the browser session)

ATTEMPT HEALTH
TOTAL              0
SUCCEEDED          0
FAILED             0
LAST SUCCESS AGE (S)   1668078.1678090096

ATTEMPTS · 50 OF 1123 MOST RECENT
[ID][STAGE][ATTEMPT][STATUS][FAILURE KIND][STARTED][ENDED]
6564  full  1   failed     http_400   ...
6563  full  1   succeeded  —          ...

EVENTS · 30 OF 3493 MOST RECENT
20413  run_stop_reason       {"status": "interrupted", "stop_reason": "browser_disconnect_unrecovered"}
20410  browser_recovery      {"attempt": 2, "error": "BrowserType.connect_over_cdp: Timeout 30000ms exceeded..."}
20405  attempt_failed        {"failure_kind": "http_400", "failure_reason": "Error code: 400 - {... 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade...'}"}
```

This is for engineers, not recruiters. The framing *Live Monitor* suggests "what's happening RIGHT NOW" but the page is dominated by historical attempts (1,123 of them) and event-bus rows (3,493) with raw JSON payloads.

Two things a recruiter would notice. **An Anthropic API "credit balance too low" error is visible in the events table** — the product I'm trialing is showing me a billing failure for the LLM provider in the operational log. As a recruiter on day 1, this reads as *the product I'm trying to buy ran out of money*. And **`LAST SUCCESS AGE (S)   1668078.1678090096`** — the literal seconds value. The run report gracefully said *Last success 19 days ago.* Same number, two presentations: the editorial surface translated; the monitor didn't.

The contrast within Cloris is sharp: the editorial run report knows its audience; the live monitor uses the same labels and units the engineer who built it would.

### Launch a search

Back to the home picker. Three "Head of Applied AI Lab" entries: one labeled `LinkedIn #existing_role` (the stub I just filed) and two labeled `LinkedIn #1957683706` (the real one, listed twice). On day 1 I'd guess by the number, hover, squint, and pick. I'd be guessing.

I click. The launch panel fills in:

```
Ready: Head of Applied AI Lab

WHERE CLORIS WILL LOOK
Cloris fires one worker per module. Deselect a module to skip it for this launch only.
[ LinkedIn (selected) ] [ GitHub ] [ Researcher (disabled) ]

BEFORE YOU START
LINKEDIN
Cloris can't reach Chrome over CDP.
Run ./launch-chrome.sh --force, open linkedin.com/talent, wait a few seconds, then retry.

[ START SEARCH ]   ← disabled
[ PULL & RESUME ]  ← disabled
```

Two surprises.

**One.** GitHub is *enabled* on the launch panel. In the intake wizard's "Where I should look" chapter — the surface where I declared what Cloris should scan — GitHub was disabled with the italic *— coming with Phase F.* Same product, two surfaces, two opinions about whether GitHub exists.

**Two.** *Cloris can't reach Chrome over CDP. Run `./launch-chrome.sh --force`, open linkedin.com/talent, wait a few seconds, then retry.*

I'm a recruiter. I do not know what CDP is. I do not have a terminal open. I do not know where Cloris's repo lives on disk. The instruction is a developer-onboarding step that ended up on the customer surface. `START SEARCH` is disabled. `PULL & RESUME` is disabled. There is no UI affordance to fix the gate.

The launch beat ends here. I cannot start a search on day 1 without going to the terminal.

### Reflect

I navigate to the Reflection (`#/workspace/1957683706/reflect`). After ~8 seconds:

```
REFLECTION — INTERRUPTED

I lost my train of thought — start the reflection over.

Starting the reflection failed: There isn't enough run evidence yet to reflect on.

[Back to the workspace]
```

The error is *gorgeously* presented. Fraunces serif heading, italic Cloris-voice (*"I lost my train of thought"*), one clear sentence about what failed, one CTA. R18 / R21 in action — voice for the framing, plain operational copy for the reason. This is craft.

But the recruiter can't proceed. *"There isn't enough run evidence yet to reflect on"* — what's evidence? How much is enough? Where do I get more? The error doesn't say. The CTA points back to the broken workspace.

Reading the source ([cloris/frontend/src/lib/reflection/copy.ts](cloris/frontend/src/lib/reflection/copy.ts)) — what I would have seen if it had worked — is the strongest writing in the product. Three gates with consistent voice:

- **Gate 1 — The Read.** Eyebrow `reflection — the read` → H1 *"What I learned from this run."* → italic deck *"This is what I think we should look into next."* → "What I want to find out:" intentions list → steering textarea (*"Anything you want me to add, drop, or steer differently?"*) → CTAs `Looks good, start reading` / `Refine the plan` / `Discard`. With a 3-iteration cap on refinement that telegraphs trust: *"You've refined this three times. Trust the plan and start reading, or discard and try again later."*
- **Reading state.** *"I'm reading the market."* The warmest line in the product: *"You can close this tab — I'll save where I left off."*
- **Gate 2 — The Diff.** *"Here's what I want to change."* → hunk cards with `Currently:` / `Cloris suggests:` / `Why:` → `File the new brief` / `Discard reflection`.

This is the most coherent feature copy in the product. The Reflection knows what it is, who Cloris is, what the recruiter is doing. It's the reason a senior recruiter would integrate the tool.

But on day 1: I can't reach any of it. The reflection requires a finalized `run_dir` under `output/runs/` that the latest interrupted run-14 doesn't have, and the older finalized run dirs crash the reflection backend with a `sqlite3.OperationalError: no such column: facial_borderline_count` — a schema mismatch between older snapshots and the current code. The reflection is theatrically well-designed and structurally unreachable.

What I'm thinking when I leave: *Cloris has a reflection feature, and the marketing was that it learns from each run. But on day 1 I can't get it to work. I'll come back to this later — but later might be never.*

### Refine and second run

Both blocked. The diff doesn't exist (Gate 2 didn't run). The launch is gated by Chrome CDP. **The loop the journey asks me to walk doesn't close.** The inability to close the loop is itself the lived experience.

## Day-5 supplement (focused)

A returning recruiter, five days in. Some surfaces I deliberately skipped on day 1 because I was burned by the wizard and the workspace timeout. Now I'm coming back with familiarity and lower expectations.

The verb tile labels have shifted from `COMPOSE · DISPATCH · REVIEW · MARKET` to `WRITE · START · REPORT · MARKET`. The new labels are dramatically clearer. Day 5 me notices that the product is iterating on plainness — and that day 1 me was paying a tax for the older, more performative names.

The "Investigate →" CTA on the home page expands the card inline (good IA — keeps me anchored). What's inside is `Cloris · Away`, `Pull · ready to pull`, `last mark · Apr 30`, `READ THE REPORT`, `ARCHIVE` (disabled), `REFERENCE SLIP +`. *Away* and *Pull* are operator vocabulary I never learned the meaning of. (And the cloris-frontend rule explicitly says *"Do not expose `away` mode in Cloris v0"* — but it's exposed here. Day 5: I notice the rule and the surface disagree.)

Filed Away (`#/filed`) shows me 3 "Lost track" briefs and 411 archived state directories. As a returning recruiter I now have 411 ghost runs filed away with no guidance on cleanup. The status taxonomy on home (*Stopped / Paused / Lost track*) doesn't match the taxonomy on Filed (*Lost track / Archived state directories*). Two surfaces, two languages for the same thing.

Drafts (`#/drafts`) shows me 6+ identical entries titled *An untitled draft* / *Last on chapter 1 of 6 — Tell me about the role.* They all look the same. (And the wizard itself says *Chapter 1 of 7* — six chapters here, seven there.) These are presented as "things you should pick up or discard" but they're system noise; there's no Discard All.

The Market catalog (`#/market`) shows Head of Applied AI Lab as *Runs 2, Saves 22.* The workspace API (when it returns) says 77 saves total. The run report says 22 saves for run-14. **Three different save counts on three different surfaces for the same brief.** Day 1 I didn't notice. Day 5 I do.

Tools (`#/tools`) is *Cloris's toolbox. Standalone scripts you can run from the UI or the CLI.* The first tool, "Iterate brief," is the same JTBD as the Reflection — and it asks me to type filesystem paths into a UI form. Most other tools are CLI-only operator scripts. This is a developer admin panel.

Settings (`#/settings`) is *What Cloris **knows**. Read-only.* Provider availability with one-line plain-language descriptions of what each provider is for. Honest. Read-only. The second-strongest surface in the product after the run report. It earns trust by *not* obfuscating.

## Friction patterns

Five themes recurred across surfaces. Leverage-ranked.

### 1. The editorial layer doesn't read from where the substrate writes

The headline of the original walk was that Cloris's editorial layer (typography, voice, Cloris-as-character) is built to a high standard, while the operational substrate (worker readiness, timeouts, schema, brief ID stability) is in motion — and that the join between them is loose. That part holds.

Where I was wrong: I read every "promise / payoff gap" as a substrate failure. After spot-checking the most prominent example (Pattern #2 below), it turns out the substrate has been doing the work; the editorial layer just isn't reading from where the substrate writes. The pattern is a **wiring** problem more than a substrate problem. That changes the leverage call sharply.

Re-walking the major Pattern #1 examples through the wiring-vs-substrate lens:

| Symptom | Wiring or substrate? | Verdict |
|---|---|---|
| Wizard "Cloris's understanding" shows stub defaults | Substrate gap. The intake-chapter → `v2_draft` synthesis isn't built ([OnboardingFlow.svelte](cloris/frontend/src/components/OnboardingFlow.svelte) calls it out: *"D4 will later interpose an LLM synthesis between earlier chapters and the review chapter"*). | Promise needs to shrink until D4 lands. |
| Workspace 5s timeout on flagship brief | Pure wiring. `/api/workspace/1957683706` returns 170KB / 77 saves in ~14s. Frontend has a hardcoded `REQUEST_TIMEOUT_MS = 5_000` ([cloris/frontend/src/lib/api.ts:75](cloris/frontend/src/lib/api.ts)). | Bump the timeout (or fix endpoint perf). One config change. |
| Candidate detail "No save reason recorded" | Pure wiring. Substrate has rationale on 114/114 SAVE-class candidates. API at [cloris/control_plane.py:1179](cloris/control_plane.py:1179) reads `payload["save_reason"]` instead of `payload["full_decision"]["rationale"]`. | One-line API fix. (See Pattern #2.) |
| Reflection "no evidence" on flagship brief | Mixed. Latest run-14 didn't finalize (no `run-report.json`) — that's a substrate gap. But the older `legacy-2` run dir DOES have a finalized report with evidence; the UI defaults to the latest run with no affordance to pick "reflect on a past finalized run." Schema drift on older snapshots crashes the backend with `no such column: facial_borderline_count`. | Mostly wiring (run-picker UI affordance + schema migration), partly substrate (worker died before finalizing run-14). |
| Three "Head of Applied AI Lab" entries in the picker | Substrate (data hygiene): the system genuinely has three brief rows with that role title. UI could group/dedupe by `linkedin_project_id` but the duplicates are real. | Substrate cleanup + UI grouping. |

Of five load-bearing examples, **three are pure or mostly wiring**. The substrate has been keeping the promises Cloris makes; the editorial layer just isn't threaded to where the substrate wrote.

The fix posture isn't *"shrink the editorial promises until the substrate catches up"* — it's the inverse on most of these: **wire the editorial layer to the substrate that's already there.** The wizard read-back is the one example where the original "shrink the promise" call still applies (the synthesis layer doesn't exist). For the rest, the substrate work is done; the wires need threading through. That's a much more tractable trial-readiness posture than a strategic retreat.

### 2. The candidate detail surface reads the wrong field

77 saves on the flagship brief. The candidate detail surface — the literal place the recruiter does their job — renders *No save reason recorded for this candidate yet.* on every candidate.

Reading the substrate directly, **114 of 114 SAVE-class candidates have a substantive `full_decision.rationale`** in `terminal_payload_json`. Verbatim from one row:

> *"Insurance-domain CTO building enterprise AI SaaS platform with Anthropic/OpenAI partnerships and 24+ years of BFSI technical leadership — credible executive-builder but insurance-heavy domain, broad CTO scope rather than focused AI lab depth, and GenAI evidence is contextual rather than architecturally specific; low-confidence save."*

That's exactly the kind of judgment a senior recruiter wants to see on the candidate detail surface. It's already in the data. The control plane at [cloris/control_plane.py:1179](cloris/control_plane.py:1179) looks for `payload["save_reason"]` or `payload["reason"]` at the top level of the payload, finds neither (the rationale is one level down at `payload["full_decision"]["rationale"]`), returns `null` to the API consumer, and the UI dutifully shows the *"No save reason recorded"* fallback on every candidate.

**This is the single highest-leverage fix in the product.** A one-line change in the control plane's payload extraction, threaded through the `CandidateDetailResponse.save_reason` field that already exists in [cloris/models.py](cloris/models.py), turns the candidate detail surface from a list of LinkedIn URLs into a stack of substantive Cloris-written judgments. The recruiter's first triage session lands completely differently. The competitor question — *what is Cloris doing for me that LinkedIn Recruiter Search isn't?* — gets a real answer.

(Worth noting: the related `confidence` extraction on the line below [control_plane.py:1184](cloris/control_plane.py:1184) is also looking at top-level `payload["confidence"]`, which similarly doesn't exist — the value lives at `payload["full_decision"]["confidence"]`. Same fix shape; together they restore both the rationale text and the confidence number.)

The original walk's existential framing — *"Cloris is a list-maker, not a judge"* — was wrong. Cloris is judging substantively, on every save, in voice. The editorial layer just isn't reading the judgment.

### 3. Operator vocabulary leaks across every surface

A day-5 inventory of internal-vocabulary leaks I had to learn the meaning of:

`CDP` (`Cloris can't reach Chrome over CDP`). `launch-chrome.sh --force`. `Lost track`. `Cloris · Away`. `Pull · ready to pull`. `Phase F`. `legacy layout` / `versioned folder`. `Reference Slip`. `module` ("Cloris fires one worker per module"). `state directory`. `brief id #1957683706`. `worker missing`. `imported-2026-04-09T21-22-22-384264+00-00__legacy-2`. `runtime_state.sqlite3`.

None of this is wrong as engineer-facing vocabulary. All of it is wrong as recruiter-facing vocabulary. And it isn't quarantined — it's mixed into the editorial surface. Cloris says *"I lost my train of thought"* in one breath and *"contact /api/workspace/1957683706"* in the next. The recruiter has to hold both registers simultaneously.

The fix posture: every recruiter-facing surface needs a vocabulary firewall. Internal vocabulary belongs behind a *Reference Slip*-style fold, not in the body copy. (Cloris already invented the Reference Slip pattern — it just needs to apply it more strictly.)

### 4. Different aggregations, none labeled

Three save counts for the same brief: workspace 77, run report 22, market 22. Verified: the workspace's 77 is the sum across two state directories (47 in `1957683706-clean-20260413` + 30 in `1957683706`) of all SAVE-class candidates ever found for `brief_id=1957683706`. The run report's 22 is run-14 specifically. The market's 22 is the most recent *finalized* run (legacy-2). All three are correct under their definitions; none of them surface their definition. The recruiter sees three numbers for "saves on Head AI" and has no way to tell which one is "real."

Same fix shape elsewhere: chapter count (wizard "1 of 7" vs drafts "1 of 6"); status taxonomy (home "Stopped / Paused / Lost track" vs Filed "Lost track / Archived state directories"); event labels (run report deck *Interrupted* vs badge *Stopped*); time presentation (run report "Last success 19 days ago" vs Live Monitor `LAST SUCCESS AGE (S) 1668078.1678090096`).

This isn't surfaces disagreeing on a single ground truth — it's surfaces showing different valid aggregations without labeling them. Day 1 noise; day 5 paper cuts that compound into a low-trust-in-numbers posture because *which number is the real one?* is never answered.

Fix posture: label the definition next to the number ("22 *this run* / 77 *all time*"), or pick a single canonical aggregation and propagate it. Either lands the trust; both at once is overkill.

### 5. The home is shaped to alarm, not to invite

Four cards on the home: all red or yellow. The first label on my flagship brief is **Lost track**. The microcopy says *Cloris lost track.* The CTA is *Investigate*. Before I've authored anything or run anything, the home tells me Cloris is wounded.

There is no positive-state list. No "here's what's running, here's what's healthy, here's where saves came in this week." The home conflates "what needs your attention" with "what's the state of the product." A returning recruiter on day 5 would want the latter; the new recruiter on day 1 would want both.

The framing *Needs attention. These are the briefs that need a hand. **She** keeps them up front.* answers the question *what does Cloris want me to do* but not *what is Cloris doing for me*. That latter question goes unanswered on the home.

Fix posture: balance the home. A *"What I'm doing right now"* section (live runs, recent saves, fresh signal) sits beside the *"What needs your attention"* section. Cloris's value is also visible.

## The thing you're not seeing

After walking the full journey, the systemic experience defect that's invisible from any single surface is this:

**Cloris is built for a recruiter who is also their own operator.**

Look at every surface that asks the recruiter to *do* something:

- To **launch a search**, the recruiter must run `./launch-chrome.sh --force` in a terminal.
- To **find their brief in the picker**, the recruiter must recognize LinkedIn project IDs as identifiers.
- To **trust the workspace count**, the recruiter must understand the difference between SQLite truth and projection JSON.
- To **reflect on a run**, the recruiter must have a finalized run_dir, which only exists for runs that finished cleanly, which requires the worker not to have crashed.
- To **iterate a brief**, the recruiter must type filesystem paths into a Tools form, OR run a CLI from the terminal.
- To **recover from any error**, the recruiter must read API endpoint paths in error messages and infer what failed.
- To **judge a candidate**, the recruiter must click the LinkedIn URL because Cloris didn't write down a reason.
- To **understand what changed**, the recruiter must learn five different status vocabularies across home / Filed / Brief detail / Run report / Live Monitor.

Each of these, individually, is a small lift. Together, the band of competency required to actually use Cloris on day 1 isn't *senior recruiter*. It's *senior recruiter who is also comfortable in a terminal, who can read SQL schemas, who can pattern-match an OpenAPI path, and who already knows what "CDP" means.*

That population is vanishingly small. The marquee-trial persona — A24-tier senior recruiter — is *not* in it.

The product has been built with the implicit assumption that the user has direct access to the engineer who built it. On day 1, with no engineer next to them, the recruiter will get blocked at the Chrome-CDP gate, the wizard's read-back gap, the workspace timeout, the reflection no-evidence error, or the per-candidate empty reasoning — *each of which has no UI-only recovery path*. They will conclude that Cloris is a beautifully-designed but fundamentally engineer-coupled tool.

Every individual surface looks like the work of someone who cares deeply. The walk reveals that *no one has yet asked: can a recruiter, alone, make this product produce a useful candidate list, a useful reflection, and a refined brief, in 2 hours, without help?* Today's answer is no — and the no isn't visible from any single surface, only from the whole walk.

## What earned trust

The walk is dishonest if it only catalogs friction. Things Cloris does well:

- **The run report.** *"Cloris's report — Apr 14, 6:24 AM. Interrupted. 22 saves, 59 rejects across 505 candidates. This is the receipt for one run. To act on these candidates, open the workspace."* The surface knows what it is, names it, and tells me where the action lives. The Timeline block is plain English. *Last success 19 days ago.* is an honest, painful sentence. Progress is a numerator/denominator. Save-count consistency is internal. This is the model for what every Cloris surface could be.

- **The intake start chapter.** *"I'll ask a few questions, then read it back so you can sharpen it before I start looking."* This single sentence sets the deal precisely. If the rest of the wizard delivered on it, intake would be the strongest feature in the product.

- **The Reflection copy** (read in source). The cleanest, most coherent feature voice in the product. Three gates, each with a clear job. *"You can close this tab — I'll save where I left off."* is the warmest, truest line in the system. The reason a senior recruiter would integrate the tool — *if they could reach it.*

- **The Settings surface.** *"What Cloris **knows**. Read-only."* Honest about what providers it has, what each is for, which are missing. A senior recruiter who cares (some do) gets the answer instantly; one who doesn't can ignore the page. Earns trust by not obfuscating.

- **The error voice.** Even the failures are well-written. *"Couldn't load that workspace."* / *"I lost my train of thought."* / *"Cloris can't reach Chrome over CDP."* — each one keeps the editorial register through the failure. The product fails in voice. That's craft.

## Day-1 vs day-5 friction signature

The shape of friction shifts.

- **Cute copy becomes invisible.** *"Just like Grandma used to make source"* stops registering by visit 5; I scroll past it. Day 1 it was on-key or off-key; day 5 it's wallpaper.

- **Operational vocabulary becomes acquired knowledge.** *Lost track*, *Away*, *ready to pull*, *Reference Slip* — five days in I know what these mean. Day 1 they were noise. The product trains the recruiter into its dialect without ever explaining the dialect.

- **Repetitive errors become accepted.** *I know the workspace doesn't load on Head AI; I read the run report instead. I know reflection doesn't work on this brief; I don't try.* The recruiter develops a workaround for every operational gap, and the gaps become invisible to the recruiter and to the team building the product.

- **Surface inconsistencies become visible.** Three save counts. Two chapter counts. Two status taxonomies. Day 1 these are noise; day 5 they're load-bearing. The recruiter develops a low-trust-in-numbers posture.

- **Duplicates become annoying.** Three Head of Applied AI Lab entries in the picker; six identical untitled drafts; multiple Forward Deployed Engineer entries. Day 1: confusion. Day 5: housework I don't know how to do, with no Discard All.

- **Status pills lose semantic distinction.** Day 1 I read each badge. Day 5 *Lost track / Stopped / Paused* all read as *not running*. The visual treatment doesn't separate them.

The day-5 friction signature is dominated by *trust attrition*: the recruiter learns Cloris's gaps faster than Cloris can plug them, and the product's editorial promises stop landing because they've been falsified by experience.

## Trial-day fix list

The original walk drifted into "shrink the editorial promises" as the leverage call. The substrate spot-check turned that frame inside out. The actually-high-leverage fixes are wiring threads, four of them, day-of-trial small:

1. **Wire the candidate detail surface to `full_decision.rationale`.** [cloris/control_plane.py:1179](cloris/control_plane.py:1179). Change the payload key lookup from `("save_reason", "reason")` to read `payload["full_decision"]["rationale"]` (and `payload["full_decision"]["confidence"]` while you're there). The `CandidateDetailResponse.save_reason` field already exists; it just gets `null` instead of substantive prose. Single highest-leverage change in the product. Turns 77 list entries into 77 substantive judgments.

2. **Bump the frontend request timeout.** [cloris/frontend/src/lib/api.ts:75](cloris/frontend/src/lib/api.ts), `REQUEST_TIMEOUT_MS = 5_000` → ~30000, OR fix what's making the workspace endpoint take 14s on the flagship brief. The current ratio (5s client, 14s server) means first contact with the most-developed brief is a permanent error screen with no retry button.

3. **Wrap the LinkedIn URL on the candidate detail surface.** The page renders 8893px wide on a 1280 viewport because `highlightedPatternSource` doesn't wrap. Either CSS `overflow-wrap: anywhere` on the URL line, or — more interesting — surface the patterns embedded in that URL (`Bank%20of%20America`, `Goldman%20Sachs`, `RAG`, `Executive Director`) as Cloris's match logic in their own panel rather than leaking them as a query string.

4. **Migrate the schema on older finalized run snapshots, OR teach the reflection backend to tolerate missing columns.** The `sqlite3.OperationalError: no such column: facial_borderline_count` in [market_intelligence/engine.py:1697](market_intelligence/engine.py:1697) makes the reflection structurally unreachable on the flagship brief. Combined with the latest run not finalizing, the most-developed feature in voice/IA terms is currently invisible to a trial recruiter. (Bonus: a UI affordance to pick "reflect on a past finalized run" rather than only the auto-detected latest.)

These are not strategic retreats. They're a day's worth of wiring that turns the product from "beautifully designed but doesn't deliver" to "delivers what it promises."

## Bottom line

Cloris on day 1 is a product with a beautifully-designed editorial layer over an operational substrate that's been doing more of the work than the editorial layer is reading. The flagship brief's workspace times out (substrate works, client gives up). The candidate triage surface shows no reasoning (substrate writes substantial reasoning, API reads the wrong key). The reflection is structurally unreachable (older runs have evidence; UI doesn't offer to use them). Only the wizard's read-back is a genuine substrate gap.

Re-walked, the original "Cloris is a list-maker, not a judge" framing was wrong. Cloris IS judging substantively, in voice, on every save — the editorial layer just isn't surfacing it. The single highest-leverage next move is the [control_plane.py:1179](cloris/control_plane.py:1179) wiring fix. After that, re-walk and re-evaluate whether the remaining gaps are wiring or substrate. My guess: most of what's left is wiring too.

What stands from the original walk: the operator-vocabulary leak inventory (`CDP`, `launch-chrome.sh --force`, `Lost track`, `Cloris · Away`, `Phase F`, `imported-2026-04-09T21-22-22-384264+00-00__legacy-2`) is observational and inarguable. The home-shaped-to-alarm observation is a macro-IA call that doesn't change with the substrate spot-check. The number-disagreement pattern is real and small-fix-shaped (label the aggregations). And the central thing-you're-not-seeing — *Cloris is built for a recruiter who is also their own operator* — stands undisturbed: the band-of-competency required to use the product on day 1 with no engineer in the room (terminal commands, schema literacy, API endpoint reading, multiple internal vocabularies) is well outside the marquee A24-tier-recruiter persona.

The strongest surfaces (run report, intake start, Settings, the Reflection copy) are good enough that this product wants to work. After the wiring fixes above, it will land much closer to that.
