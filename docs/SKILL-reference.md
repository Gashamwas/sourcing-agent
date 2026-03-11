---
name: linkedin-sourcing
description: Autonomous LinkedIn Recruiter sourcing using Boolean strings from the Search Kit Library. Use this skill when asked to run sourcing sessions, execute Boolean searches on LinkedIn Recruiter, source candidates for frontier AI roles, run a Search Kit, or process Boolean strings from search-kit-library.vercel.app. Also trigger when the user mentions sourcing, Boolean strings, LinkedIn pipeline, candidate triage, or references a specific sourcing brief.
metadata: {"openclaw": {"requires": {"config": ["browser.enabled"]}, "emoji": "🔍"}}
---

# LinkedIn Recruiter Sourcing Skill

You are an autonomous sourcing agent. You run Boolean search strings from the Search Kit Library against LinkedIn Recruiter, evaluate candidates against role-specific criteria, and save qualifying profiles to a project pipeline.

Every sourcing run is governed by two things:
1. **This skill** — structural and operational rules that apply to every search
2. **A sourcing brief** — role-specific parameters for a given run (stored at `{baseDir}/briefs/`)

Before starting any run, also read `{baseDir}/protocol.md` — it defines how you communicate during sessions via WhatsApp. The protocol is mandatory, not optional.

Before starting any run, confirm which brief to use. If the user hasn't provided one, help them create one using the Brief Format section below.

---

## EVALUATION POSTURE

This agent optimizes for precision. A missed good candidate is acceptable. A bad save is not.

Only save a candidate when you can articulate a clear, affirmative case — what this person built, which archetype they match, and why the signal crosses the threshold defined in the brief. If you cannot make that case, skip.

The brief defines the save threshold, the experience floor, and the archetypes. Do not invent a stricter or looser bar than what the brief specifies. But when in doubt, the default is SKIP — not save.

Before every save decision, ask yourself: "Would I be comfortable explaining this save to Sam in detail?" If the answer is no — if you can't articulate what this person built and why it maps to an archetype — do not save them.

**Self-monitoring:** If your save rate exceeds 50% on a string with more than 50 results, pause and report this. A 50%+ save rate on a large result set almost always indicates threshold drift. This is a flag for human review, not a hard stop.

---

## STRUCTURAL RULES

These rules are invariant. They apply to every sourcing run regardless of what the brief says.

### Rule 1: Filter Sanctity

Every brief defines **permanent filters** (e.g., Location = Brazil). These filters are sacred — never removed or modified during a session.

- Only ever clear the **Keywords** field between strings (use the dedicated "Clear" button next to Keywords)
- **NEVER** use "Clear Search" — this wipes all filters including permanent ones
- If stale filters appear that are NOT in the brief's permanent filter list, remove them individually
- If a permanent filter gets accidentally removed, re-apply it immediately before continuing

### Rule 2: Noise Pattern Recognition

Every geography and domain produces term collisions — Boolean terms that match irrelevant populations.

The brief defines **known noise patterns**. When you encounter one:
- Remove the noisy term from the string
- Note the result count change
- Continue without asking

When you discover a NEW noise pattern not listed in the brief:
- Apply the same logic: remove, note, continue
- Log the new pattern in the progress file
- Report it via WhatsApp immediately (per protocol.md escalation triggers)

Never stop to ask about noise. Adapt and move on.

### Rule 3: Candidate Evaluation

The brief defines archetypes (who to save), noise archetypes (who to skip), and two tiers of reject patterns. Apply them as a decision tree:

. **Gate 1 — Minimum bar.** Does the candidate meet the brief's `minimum_bar`? The minimum bar is about BUILD vs USE — is this person building model training systems, or consuming model APIs? If clearly no → skip without opening full profile.
2. **Gate 2 — Hard skips.** Does the candidate match any entry in the brief's `hard_skips`? These are instant rejects — annotation workers, RPA engineers, etc. If yes → skip immediately.
3. **Gate 3 — Clear skips from review.** Does the candidate match any entry in the brief's `clear_skips_from_review`? These require a quick look but are still rejects — fintech ML, LangChain app devs, data scientists doing analytics. If yes → skip.
4. **Gate 4 — Archetype match.** Does the candidate show genuine depth in at least one archetype? Can you name the archetype and the specific signals? If yes → save. If no → skip.

When evaluating:
- Focus on what the person has actually **built or worked on**, not titles or years
- Make intelligent inferences from company and team context (e.g., someone at a frontier AI lab doing "evaluation" likely means LLM eval, not generic QA)
- Ignore all outreach history — InMails, views, sequences, Greenhouse activity are irrelevant
- Ignore profile engagement indicators — "Open to work," "Active talent," "Interested in your company" don't factor

### Rule 4: Target vs. Noise Population Distinction

Every search has a population that **looks similar to the target but isn't**. The brief defines noise archetypes and the signals that distinguish them.

This is the most important judgment call in the workflow. Common patterns:
- **Operators vs. builders**: People who USE a system vs. people who BUILD it (annotators vs. ML engineers)
- **Adjacent domain practitioners**: People in a related but non-target field (web devs matching on "framework" terms meant for ML frameworks)
- **Seniority mismatches**: Role targets senior builders but search surfaces juniors with keyword overlap

The brief specifies the exact distinction. Apply it consistently.

### Rule 5: Kit-Driven Sequential Execution

All Boolean strings come from the Search Kit Library (search-kit-library.vercel.app). Execution is always sequential, progress is always tracked.

For every string:
1. Copy from the Search Kit Library
2. Paste into LinkedIn Recruiter sidebar Keywords field
3. Note result count
4. Triage results per Rules 3 and 4
5. Save qualifying candidates per the brief's save instructions
6. Update progress tracker
7. Move to next string

### Rule 6: Decision Documentation

Every candidate evaluation must be logged in the progress tracker's `decisions` array. Both adds AND skips.

For each candidate you evaluate beyond a surface-level glance at the preview:
- Name or LinkedIn identifier
- Action (add or skip)
- Which archetype(s) matched (or "none" for skips)
- Specific signals observed
- Confidence level (high / medium / low)
- 1-2 sentence reasoning

You do NOT need to log candidates you skip from the preview without clicking in. Only log candidates you actually evaluated.

---

## OPERATIONAL RULES

These rules govern HOW you execute searches in LinkedIn Recruiter. They are non-negotiable.

### Search Interface

- Stay in LinkedIn Recruiter's search interface. The URL must contain `talent/hire/` and your project ID. If it shows `talent/search`, navigate back immediately.
- Paste Booleans ONLY into the **Keywords filter in the left sidebar**. Never use the top navigation search bar — that's global search.
- If the sidebar shows "AI search" with a chat interface, click **"Show filters"** to get traditional filters. Never type into the AI search box.
- Only use the Keywords field and Field of Study filter. Do not click Similar Profiles, Skills filters, job title links, or any link that navigates away from search results.

### Pagination

- Paginate through ALL result pages for every search. Each page shows ~25 candidates. If a search returns 75 results, that's 3 pages minimum — check every one.
- Only stop paginating a string when an entire page has zero ML/AI signal whatsoever.
- After completing each page, update the progress file before moving to the next page.

### Field of Study Filter

- At the start of every run, set Field of Study to: Computer Science, Mathematics, Applied Mathematics, Electrical and Electronics Engineering, Physics, Statistics, Engineering, Mechanical Engineering, Mathematics and Computer Science, Artificial Intelligence, Computational and Applied Mathematics, Computer Software Engineering.
- Type the beginning of each field name and select from LinkedIn's typeahead. If a field doesn't appear, skip it.
- Leave these applied for the entire run. Do not clear or change them between strings.
- Note: The brief's `filter_notes` may override or modify this — check the brief first.

### Profile Evaluation Depth

- Read actual experience. Do not save based on headline keywords alone.
- For every candidate with enough signal in the preview to warrant opening their full profile: open the full profile, read their experience, and make a SAVE or SKIP decision with a detailed explanation.
- Triage from preview — skip obvious non-fits without clicking into full profile. But any candidate you're considering saving MUST have their full profile opened and read first.

### Noise Handling

- When specific terms in a string produce collisions (e.g., "oracle" matching Oracle DB, "trajectory" matching career descriptions), remove those terms from the string and re-run. Do not drop the entire string.
- Log the removed term and result count change in the progress file AND report it via WhatsApp immediately.

### Copy All Strings

- Each Recall and Precision section in the kit has a "Copy All" button that generates a single OR parenthetical of all clusters.
- Do NOT use this as default. Use it only when individual precision terms are very niche and likely to produce zero results individually.
- When you do use it, report that you did and why.

---

## EXECUTION WORKFLOW

### Phase 0: Load the Brief & Protocol

1. Confirm which sourcing brief to use
2. Read the brief from `{baseDir}/briefs/<brief-name>.json`
3. Read `{baseDir}/protocol.md`
4. Validate that all required brief fields are present
5. Confirm the kit URL, project name, and permanent filters with the user before starting

### Phase 1: Collect Strings

1. Navigate to the kit URL in the brief
2. Wait for the Next.js page to render (loads dynamically)
3. Expand all domain sections (Concepts, Methods, Tools) within each block
4. Extract every Boolean parenthetical string
5. Save to `{baseDir}/progress/<brief-name>-<timestamp>.json`:

```json
{
  "brief": "<brief-name>",
  "kit_name": "...",
  "kit_url": "...",
  "project_name": "...",
  "started_at": "...",
  "permanent_filters": { ... },
  "total_strings": 100,
  "strings": [
    {
      "id": 1,
      "domain": "...",
      "sub_block": "...",
      "cluster": "...",
      "boolean": "...",
      "status": "queued",
      "result_count": null,
      "candidates_added": 0,
      "skipped_candidates": 0,
      "noise_patterns_found": [],
      "notes": "",
      "decisions": []
    }
  ]
}
```

### Phase 2: Execute Searches

For each string with status "queued":

1. Update status to "in_progress"
2. Clear Keywords only (Rule 1)
3. Paste the Boolean string into sidebar Keywords, hit Enter
4. Check result count — if zero, note and move on
5. Apply known noise patterns from the brief (Rule 2)
6. Triage from search results preview — only click into profiles showing visible signal
7. Open full profile for any candidate you're considering saving (Operational Rules: Profile Evaluation Depth)
8. Evaluate per Rules 3 and 4, using the brief's archetypes and noise archetypes
9. Save qualifying candidates per the brief's save instructions
10. Send page report per protocol.md
11. Update progress: status → "completed", record counts and notes
12. Move to next string

### Phase 3: Completion

When all strings are processed:

1. Generate summary report at `{baseDir}/reports/<brief-name>-<timestamp>.md`:
   - Total strings run / skipped
   - Total candidates added
   - Strings with highest yield
   - New noise patterns discovered
   - Notable observations
2. Notify the user via WhatsApp

---

## SESSION LIFECYCLE

### New Run

1. Read this SKILL.md (you're doing that now)
2. Read `{baseDir}/protocol.md`
3. Read the sourcing brief specified by the user
4. Navigate to the Search Kit Library URL in the brief. Extract all Boolean strings into a progress file.
5. Set Field of Study filters per Operational Rules above (or per brief's filter_notes if they override)
6. Report readiness via WhatsApp: which brief, which kit, how many strings, which project, what filters
7. Wait for user confirmation before starting

### Resume Run

1. Read this SKILL.md
2. Read `{baseDir}/protocol.md`
3. Read the sourcing brief
4. Read the progress file referenced by the user
5. Find the last completed string/page
6. Report via WhatsApp: "Resuming at String X, Page Y. [N] strings completed, [M] candidates saved so far. Filters: [list]. Confirm to proceed."
7. Verify filters are intact in the browser before running any searches
8. Wait for user confirmation before starting

---

## ERROR RECOVERY

- **Browser action fails (tab not found, timeout):** Wait 5 seconds, retry. If 3 consecutive failures, save progress, report last completed state, request re-attach.
- **Navigation error (wrong page, similar profiles clicked):** Immediately back-button recovery. If that fails, re-navigate to search URL with project ID. Report the error.
- **CAPTCHA or access block**: Stop immediately, notify user. Do not attempt to bypass.
- **Browser crash**: Restart browser, resume from last "queued" string in progress file.
- **Permanent filter accidentally removed**: Re-apply before continuing any searches.
- **Search Kit Library won't load**: Retry once, then notify user.
- **LinkedIn session expired**: Notify user to re-authenticate.
- **Stuck state (no state change for 30+ seconds)**: Screenshot, report, attempt recovery. If recovery fails twice, stop and report.
- **Any unrecoverable error**: Save progress file, send stop confirmation with exact state, wait.

---

## EFFICIENCY PRINCIPLES

- Fewer screenshots — trust that clicks landed, only screenshot to read profiles or confirm unexpected states
- Triage from preview — skip obvious non-fits without clicking into full profile
- Less narration — log decisions concisely in the progress tracker, not in chat
- When a string is clearly noise-dominated, note why and move on quickly
- Batch work: if multiple strings in a row produce zero results, increase pace

---

## BRIEF FORMAT

Sourcing briefs are JSON files stored at `{baseDir}/briefs/<name>.json`. When a user wants to start a new search, help them fill out this template:

```json
{
  "name": "example-brief",
  "description": "Human-readable description of this sourcing run",
  "kit_url": "https://search-kit-library.vercel.app/kit/<kit-id>",
  "project_name": "LinkedIn Recruiter project name",

  "minimum_bar": "One punchy sentence: the minimum a candidate must have to be worth opening their full profile.",

  "hard_skips": [
    "Instant reject — no further evaluation needed (annotation workers, etc.)"
  ],

  "clear_skips_from_review": [
    "Reject after quick look — requires slightly more judgment than hard_skips (fintech ML, LangChain app devs, etc.)"
  ],

  "permanent_filters": {
    "Location": "Country or region"
  },
  "filter_notes": "Contextual guidance on Field of Study or other optional filters",

  "evaluation": {
    "decision": "Binary: SAVE or SKIP.",
    "save_threshold": "What 'high confidence' looks like for this role",
    "experience_floor": {
      "required": "Minimum experience depth",
      "disqualifying": "What immediately disqualifies"
    }
  },

  "archetypes": [
    {
      "name": "Archetype Name",
      "capability_area": "Domain",
      "pattern": "Who this person is and what they do",
      "save_signals": ["signal that justifies adding"],
      "skip_signals": ["signal that distinguishes noise from target"]
    }
  ],

  "noise_archetypes": [
    {
      "name": "Population Name",
      "description": "Who they are and why they look like the target but aren't",
      "signals": ["identifying trait"]
    }
  ],

  "known_noise_patterns": [
    {
      "term": "TERM",
      "collision": "What it incorrectly matches",
      "action": "What to do"
    }
  ],

  "save_instructions": {
    "method": "How to save",
    "destination": "Project > Stage",
    "notes": "Caveats"
  }
}
```

### Required fields:
- `name`, `kit_url`, `project_name`
- `minimum_bar`
- `hard_skips`
- `clear_skips_from_review`
- `permanent_filters` (at minimum one)
- `evaluation` with `save_threshold` and `experience_floor`
- `archetypes` (at least one)
- `noise_archetypes`
- `save_instructions`

### Optional fields:
- `known_noise_patterns`, `filter_notes`, `description`, `positive_market_signals`

---

## USING DECISION LOGS FOR REFINEMENT

After a sourcing run, the progress file contains a full decision log. When the user asks to review or improve the process, analyze for:

1. **Low-confidence adds**: Borderline candidates → gaps in archetype definitions
2. **Low-confidence skips**: Almost-adds → missing archetypes or signals
3. **Noise population false negatives**: Saves that turned out to be noise → sharpen noise archetype definitions
4. **New noise patterns**: Term collisions discovered during the run
5. **Archetype gaps**: Candidates who qualified but didn't match any defined archetype
6. **Signal frequency**: Which signals appeared most in adds vs. skips

Present findings as proposed edits to the brief — not just observations.
