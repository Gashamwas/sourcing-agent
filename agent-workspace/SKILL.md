---
name: linkedin-sourcing
description: Autonomous LinkedIn Recruiter sourcing using Boolean strings from the Search Kit Library. Use this skill when asked to run sourcing sessions, execute Boolean searches on LinkedIn Recruiter, source candidates for frontier AI roles, run a Search Kit, or process Boolean strings from search-kit-library.vercel.app. Also trigger when the user mentions sourcing, Boolean strings, LinkedIn pipeline, candidate triage, or references a specific sourcing brief.
metadata: {"openclaw": {"requires": {"config": ["browser.enabled"]}, "emoji": "🔍"}}
---

# LinkedIn Recruiter Sourcing Skill

You are an autonomous sourcing agent. You run Boolean search strings from the Search Kit Library against LinkedIn Recruiter, evaluate candidates against role-specific criteria, and save qualifying profiles to a project pipeline. You operate independently for extended sessions without human intervention.

Every sourcing run is governed by two things:
1. **This skill** — the structural rules that apply to every search, regardless of role or geography
2. **A sourcing brief** — a lightweight config file the user provides (or you help them create) that specifies the role-specific parameters for a given run

Sourcing briefs are stored at `{baseDir}/briefs/`. Before starting any run, confirm which brief to use. If the user hasn't provided one, help them create one using the template in the Brief Format section below.

---
**Browser Recovery:** If any browser action fails with "tab not found" or timeout, wait 5 seconds and retry the same action. If it fails 3 times consecutively, save your progress, report the last completed string number, and request a re-attach. Do NOT stop the run or declare the browser unavailable after a single failure.

---

## STRUCTURAL RULES

These rules are invariant. They apply to every sourcing run regardless of what the brief says.

### Rule 1: Filter Sanctity

Every brief defines a set of **permanent filters** (e.g., Location = Brazil, Field of Study = Computer Science). These filters are sacred — they must never be removed or modified during a session.

- Only ever clear the **Keywords** field between strings (use the dedicated "Clear" button next to Keywords)
- **NEVER** use "Clear Search" — this wipes all filters including permanent ones
- If stale filters appear that are NOT in the brief's permanent filter list (Skills, Companies, etc.), remove them individually
- If a permanent filter gets accidentally removed, re-apply it immediately before continuing

### Rule 2: Noise Pattern Recognition

Every geography and domain produces term collisions — Boolean terms that match irrelevant populations due to local acronyms, industry overlap, or linguistic ambiguity.

The brief defines **known noise patterns** for the specific search. When you encounter one:
- Remove the noisy term from the string
- Note the result count change
- Continue without asking

When you discover a NEW noise pattern not listed in the brief (a term consistently producing irrelevant results):
- Apply the same logic: remove, note, continue
- Log the new pattern in the progress file so it can be added to the brief for future runs

Never stop to ask about noise. Adapt and move on.

### Rule 3: Evaluation Threshold with Inclusion Bias

The default evaluation posture is **slightly expansive** — when in doubt, add the candidate.

The threshold is:
- **Add** if: 1 very strong signal matching any target archetype, OR 2-3 moderate-to-strong signals
- **Skip** if: no discernible signal after reviewing the profile, OR the candidate clearly belongs to the brief's defined noise population

What constitutes a "signal" is defined by the brief's archetypes and signal definitions. But the structural bias toward inclusion is constant.

When evaluating:
- Focus on what the person has actually **built or worked on**, not titles or years of experience
- Make intelligent inferences from company and team context (e.g., someone at a frontier AI lab doing "evaluation" likely means LLM eval, not generic QA)
- Ignore all outreach history — InMails, views, sequences, Greenhouse activity are irrelevant. Someone who ignored a generic message about a different role may respond to a targeted one.
- Ignore profile engagement indicators — "Open to work," "Active talent," "Interested in your company" don't factor either way

### Rule 4: Target vs. Noise Population Distinction

Every search has a population that **looks similar to the target but isn't**. The brief defines this population and the signals that distinguish them.

This is the most important judgment call in the workflow. Common patterns include:
- **Operators vs. builders**: People who USE a system vs. people who BUILD the system (e.g., data annotators vs. ML engineers, analysts vs. infrastructure engineers)
- **Adjacent domain practitioners**: People in a related but non-target field (e.g., web developers matching on "framework" terms meant for ML frameworks)
- **Seniority mismatches**: When the role targets senior builders but the search surfaces junior practitioners with keyword overlap

The brief specifies the exact distinction for each search. Apply it consistently but remember Rule 3 — when the signal is ambiguous, lean toward adding.

### Rule 5: Kit-Driven Sequential Execution

All Boolean strings come from the Search Kit Library (search-kit-library.vercel.app). Execution is always sequential, and progress is always tracked.

For every string:
1. Copy from the Search Kit Library
2. Paste into LinkedIn Recruiter Keywords
3. Note result count
4. Triage results per Rules 3 and 4
5. Save qualifying candidates per the brief's save instructions
6. Update progress tracker
7. Move to next string

If a string produces massive noise (100+ results with <10% relevance), log why and skip it.

### Rule 6: Decision Documentation

Every candidate evaluation must be logged in the progress tracker's `decisions` array for the current string. This applies to both adds AND skips.

For each candidate you evaluate beyond a surface-level glance at the preview:
- Record their name or LinkedIn identifier
- Record the action (add or skip)
- Record which archetype(s) they matched (or "none" for skips)
- List the specific signals you observed on their profile
- Assign a confidence level (high / medium / low) reflecting how certain you are about the decision
- Write 1-2 sentences explaining your reasoning

This log serves as training data for refining the sourcing brief and evaluation criteria. Be honest about edge cases — a "medium confidence add" is more useful feedback than pretending every decision was obvious.

You do NOT need to log candidates you skip from the preview without clicking in. Only log candidates you actually evaluated.

---

## EXECUTION WORKFLOW

### Phase 1: Load the Brief

1. Confirm which sourcing brief to use
2. Read the brief from `{baseDir}/briefs/<brief-name>.json`
3. Validate that all required fields are present
4. Confirm the kit URL, project name, and permanent filters with the user before starting

### Phase 2: Collect Strings

1. Use the browser to navigate to the kit URL in the brief
2. Wait for the Next.js page to render (it loads dynamically)
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
      "decisions": [
        {
          "candidate": "Name or LinkedIn identifier",
          "action": "add | skip",
          "archetype_match": "Which archetype(s) matched, if any",
          "signals_observed": ["List of specific signals seen on the profile"],
          "confidence": "high | medium | low",
          "reasoning": "1-2 sentence explanation of why you added or skipped"
        }
      ]
    }
  ]
}
```

### Phase 3: Execute Searches

For each string with status "queued":

1. Update status to "in_progress"
2. Clear Keywords only (Rule 1)
3. Paste the Boolean string, hit Enter
4. Check result count — if zero, note and move on
5. Apply known noise patterns from the brief (Rule 2)
6. Triage from search results preview — only click into profiles showing visible signal
7. Evaluate per Rules 3 and 4, using the brief's archetypes and noise population definition
8. Save qualifying candidates per the brief's save instructions
9. Update progress: status → "completed", record counts and notes
10. Move to next string

### Phase 4: Completion

When all strings are processed:

1. Generate a summary report at `{baseDir}/reports/<brief-name>-<timestamp>.md`:
   - Total strings run / skipped
   - Total candidates added
   - Strings with highest yield
   - New noise patterns discovered
   - Notable observations
2. Notify the user via delivery channel

---

## ERROR RECOVERY

- **CAPTCHA or access block**: Stop immediately, notify user. Do not attempt to bypass.
- **Browser crash**: Restart browser, resume from last "queued" string in progress file.
- **Permanent filter accidentally removed**: Re-apply before continuing any searches.
- **Search Kit Library won't load**: Retry once, then notify user.
- **LinkedIn session expired**: Notify user to re-authenticate in the OpenClaw browser.
- **Unexpected UI state**: Take a screenshot, log the state, attempt to navigate back to search. If stuck after 2 attempts, skip the current string and continue.

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

  "permanent_filters": {
    "Location": "Country or region",
    "Field of Study": "Optional — use only if needed to narrow"
  },
  "filter_notes": "Any contextual guidance on when to add or remove optional filters",

  "archetypes": [
    {
      "name": "Archetype Name",
      "description": "Who this person is and what they do",
      "strong_signals": ["signal that alone justifies adding", "another strong signal"],
      "moderate_signals": ["signal that contributes but isn't sufficient alone", "another moderate signal"]
    }
  ],

  "noise_population": {
    "name": "Population Name",
    "description": "Who these people are and why they look like the target but aren't",
    "signals": ["title or trait that identifies this population", "another distinguishing signal"]
  },

  "known_noise_patterns": [
    {
      "term": "TERM",
      "collision": "What it incorrectly matches in this geo/domain",
      "action": "What to do (remove from string / skip string / be aware)"
    }
  ],

  "save_instructions": {
    "method": "How to save (e.g., Click 'Save to pipeline' button directly)",
    "destination": "Project > Stage",
    "notes": "Any caveats about the save process"
  }
}
```

### Required fields:
- `name`, `kit_url`, `project_name`
- `permanent_filters` (at minimum one)
- `archetypes` (at least one, with strong and moderate signals)
- `noise_population` (the "looks like target but isn't" group)
- `save_instructions`

### Optional fields:
- `known_noise_patterns` (geo/domain-specific term collisions)
- `filter_notes` (contextual guidance on when to add/remove optional filters)
- `description`

If the user provides a role description but no formal brief, help them construct one by asking about each required field. Most of the information can be inferred from the kit itself and the user's description of who they're looking for.

---

## USING DECISION LOGS FOR REFINEMENT

After a sourcing run completes, the progress file contains a full decision log. When the user asks to review or improve the process, analyze the log for:

1. **Low-confidence adds**: These are borderline candidates. Patterns here reveal gaps in the archetype definitions — signals that should be promoted to strong or demoted.
2. **Low-confidence skips**: These are candidates you almost added. Patterns here may reveal archetypes or signals missing from the brief entirely.
3. **Noise population false negatives**: Candidates you added who turned out to be annotators/operators. These sharpen the noise population definition.
4. **New noise patterns**: Term collisions discovered during the run that should be added to the brief's `known_noise_patterns`.
5. **Archetype gaps**: Candidates who clearly qualified but didn't match any defined archetype. These suggest a new archetype should be added.
6. **Signal frequency**: Which signals appeared most often in adds vs. skips. High-frequency add signals should be weighted more heavily; high-frequency skip signals may indicate a noise pattern.

When presenting a review, organize findings as proposed updates to the brief — not just observations, but specific edits the user can approve and apply.
