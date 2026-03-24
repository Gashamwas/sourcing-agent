# Autonomous Sourcing Agent

An autonomous system that takes a sourcing brief — a structured encoding of a recruiter's expertise about a role, its target candidate archetypes, and the noise patterns specific to a geography — and executes it against LinkedIn Recruiter for a full workday without human intervention. It writes its own Boolean search strings, evaluates every candidate through a structured claim-and-evidence procedure that distinguishes builders from users, adapts its search strategy in real time based on the signal it's getting, and generates entirely new queries mid-run when it discovers unexpected talent patterns. It does not keyword-match. It synthesizes whole-candidate judgments the way a trained sourcer would: reading career trajectories, inferring depth from verbs and objects in work descriptions, recognizing when methodology transfers across domains even when the domain itself doesn't match.

## How the Agent Works

### The Brief — Recruiting Expertise, Codified

Everything the agent knows about a role lives in a single JSON document: the sourcing brief. The brief is not configuration — it is the recruiter's expertise, codified into a machine-executable policy.

A brief defines **capability areas** with explicit builder/user signal distinctions (did this person *build* a reward model, or did they *use* one via API?), **non-fit patterns** calibrated to the specific labor market (BPO annotation work is the highest-volume noise pattern in Colombia; fintech ML engineers who only do fraud scoring are the trap in Brazil), **employer signal tiers** that encode which company names carry signal and how much (a Research Scientist at Anthropic is a save on employer alone; an ML Engineer at Rappi requires evaluating the actual work described in their bullets), and **facial calibration** that sets expected triage pass-through rates so the bias monitor can detect evaluation drift.

The Colombia brief, for example, defines 7 capability areas (from RL & Post-Training Data Systems to Embodied AI & Simulation), 6 non-fit patterns, 4 employer signal tiers, and a depth distinction that governs every evaluation: "Has done hands-on ML work where data quality, model training, or evaluation methodology was a primary focus" vs. "Uses ML models as components in applications without involvement in how those models are trained, evaluated, or improved."

Swapping roles means swapping briefs. Nothing else changes.

### Strategy Formation — How the Agent Writes Its Own Search Strings

At the start of a run, the agent receives the brief and an optional **kit vocabulary** — a library of Boolean search terms organized by competency domain (Post-Training & RLHF, Agentic Systems, Data Quality & Evaluation, etc.). These kit terms are raw building blocks, not executable queries. The agent synthesizes them into 15-30+ compound Boolean strings in a single planning call, cross-gating terms from multiple competency domains with geography and seniority qualifiers.

It generates two string types. **Type A recall strings** cast broad nets — 500 to 5,000 expected results — by AND-gating 2-3 skill clusters with domain qualifiers. **Type B precision "sniper" strings** use specific tool names, framework names, and benchmark names that only genuine practitioners would have on their profile — SWE-bench, Axolotl, Constitutional AI, TRL, vLLM — producing 20-500 results where nearly every hit is a real builder.

The sequencing is deliberate. Precision strings run early (interleaved with recall strings, not as an afterthought). RL/RLHF strings — the densest, most well-trodden talent pool — are backloaded to the second half. Rationale: thinner capability areas surface more net-new candidates per string, RL practitioners appear incidentally in non-RL strings (someone building RL environments shows up on "simulation" or "agent" queries), and by the time RL strings execute, the adaptation loop has learned from earlier strings' noise patterns, producing more strategic RL searches than the obvious keyword combinations.

Every string is governed by LinkedIn Boolean rules that most sourcers get wrong. LinkedIn has no stemming — "model" does not match "models," "fine-tuning" does not match "fine-tuned" — so the agent includes all morphological variants as separate OR terms. Substring embedding means "reward model" already matches "reward model development," so superstrings are never added. Abbreviations with dominant non-ML meanings are filtered: "IPO" matches Initial Public Offering, "ORM" matches Object-Relational Mapping, "DPO" matches Data Protection Officer — these are only used when paired with their full expansions. Universal infrastructure terms (PyTorch, TensorFlow, Docker, Kubernetes) and buzzwords ("AI-powered," "cutting-edge") are blacklisted as noise.

A human sourcer typically writes 3-5 strings per role. The agent wrote 33 for the Colombia campaign, each more precisely targeted than any individual kit string.

### Evaluation Pipeline

```
LinkedIn Recruiter results page
        │
        ▼
  Scroll to render all cards (virtual scrolling)
        │
        ▼
  Extract snippets ──→ [Cheap Model] ──→ Structured candidate data
        │
        ▼
  Facial judgment ──→ [Opus] ──→ FACIAL_YES / FACIAL_NO
        │                              │
        │ (FACIAL_YES only)            │ (skip — no profile open)
        ▼                              │
  Open profile panel (ghost-cursor)    │
        │                              │
        ▼                              │
  Extract full profile ──→ [Cheap Model]
        │
        ▼
  Final judgment ──→ [Opus] ──→ SAVE / REJECT / INFERENTIAL_SAVE
        │
        ▼
  Save to Recruiter pipeline (if qualifying)
```

### Two-Phase Evaluation — Triage, Then Synthesis

Every candidate on a results page is evaluated. The question is how deeply.

**Facial triage** is the first gate. The agent sees only snippet data — name, headline, current title and company, career history of positions with titles and dates. No job description bullets, no project details. It reads the full career trajectory, not just the current role. Fast exits apply only when the *entire* trajectory clearly indicates work outside scope — every position in IT support, sales, HR, or BPO annotation with nothing else. One relevant-looking position anywhere in the history blocks a fast exit. Ambiguity defaults to YES: the cost of a false positive is one cheap profile extraction; the cost of a false negative is a permanently missed candidate. Expected pass-through is 25-50% depending on the search string and market density.

Only candidates that pass facial triage trigger a profile open. On a typical page of 25 candidates, roughly 6 pass — keeping the profile-open rate low while still evaluating every candidate on the page.

**Full evaluation** follows a four-step structured procedure for each opened profile:

**Step 1 — Capability Mapping.** Map the candidate's actual work (from experience bullets, not just titles) to the brief's capability areas. The result is DIRECT (work falls squarely within an area), ADJACENT (touches but isn't core), or NONE. This is signal, not a gate — NONE does not mean reject.

**Step 2 — Depth Test.** Builder or user? This runs regardless of Step 1 and is the actual guard against permissiveness. The agent reads verbs and objects in the candidate's work descriptions. "Designed, built, fine-tuned, trained, developed a pipeline" are builder verbs. "Deployed, integrated, managed, monitored, used a pre-built model" are application-layer verbs. "Fine-tuned" is a builder verb. "Fine-tuned via API" is a user verb. A candidate whose skills list says "RLHF" but whose bullets describe only API integration does not pass the depth test.

**Step 3 — Transferability** (only when Step 1 found no direct match). "If you took this person's methodology and pointed it at LLM training data instead of their current domain, would the skills apply?" Evaluation framework design in any ML domain transfers — the person knows how to measure model quality; the specific model changes but the methodology of rigorous evaluation is the same. Data curation pipeline design transfers. Custom model training experience transfers. Classical engineering simulation does not. Statistical analysis without model building does not.

**Step 4 — Decision.** State the strongest case for and strongest case against the candidate's relevance, then decide. The decision matrix weighs evidence from all three steps: DIRECT match + BUILDER depth = SAVE (confidence 0.75-0.95). ADJACENT match + BUILDER depth = SAVE (0.55-0.75). No direct match + BUILDER depth + TRANSFERABLE methodology = TRANSFERABLE_SAVE (0.45-0.65). Any match level + USER depth = REJECT. Sparse profile meeting inferential conditions (PhD from a strong program + frontier lab employer + relevant title, but no detailed bullets) = INFERENTIAL_SAVE, passed to the recruiter for manual review.

Employer signal tiers shape these judgments. A Research Scientist at OpenAI or Anthropic is saved on employer and title alone — frontier lab employees doing adjacent work carry transferable depth that doesn't need to be spelled out in LinkedIn bullets. An ML Engineer at a Colombian tech company like Rappi or MercadoLibre is ambiguous on company name alone; the decision depends entirely on what the experience bullets actually describe.

### Within-String Adaptation — Scout, Paginate, Refine

The agent doesn't blindly paginate through every string's results. It treats page 1 as a **scout** — the best results LinkedIn will surface for that query. After evaluating page 1, the agent decides: **paginate** (signal looks good, commit to deeper pagination), **narrow** (too much noise — add AND clauses to focus the search), or **abandon** (the core concept surfaces the wrong population entirely).

During pagination, the agent reviews accumulated statistics after each page — save rate, facial YES rate, duplicate rate, quality trends — and decides: **continue**, **narrow**, **broaden**, **stop**, or **abandon**. Narrowing pushes the current Boolean onto a **refinement stack**; broadening pops it. The agent can navigate the specificity gradient in either direction with full history:

```
Original: ("agentic" OR "LLM agent") AND ("financial services" OR "banking")
  → Narrow: + AND ("production" OR "deployment" OR "enterprise")
    → Narrow again: + AND NOT ("RPA" OR "chatbot")
      → Broaden: revert to first narrowing
```

A minimum pagination depth prevents premature stops — strings with 500+ results must be reviewed for at least 3 pages. This encodes the recruiter insight that absence of saves on page 2 doesn't mean the string is dead; it means page 2 is noisier than page 1, which is expected.

### Block-Level Adaptation — Mid-Run Strategy Pivots

After every batch of ~5 strings, the agent reviews a **BlockReport**: which strings produced saves, which were zero-save noise, what unexpected candidate populations appeared, what terms collided with undesired demographics. Based on this real-time signal, it:

- **Generates new compound strings** targeting signal patterns discovered during execution. "I'm finding data quality engineers through agentic systems strings — let me write a string that targets that intersection directly."
- **Recommends skipping** queued strings that are now redundant with completed ones.
- **Reorders** remaining strings based on observed productivity.
- **Updates noise pattern knowledge** for downstream strings.

This is the formalization of what a recruiter does naturally when they adjust their search strategy mid-session based on who they're actually finding. The difference is that the agent does it with perfect recall of every candidate it has evaluated, every save rate, and every noise collision across every string in the run.

## Bias Controls

Early in the project, the agent saved 398 annotation workers in a single session because the evaluation criteria were too permissive for the population that a broad string surfaced. That failure mode — saving everyone because the cohort *looks* vaguely relevant — is what the bias control system prevents.

Five monitors run continuously during every session:

**Consecutive saves** (threshold configurable per brief, default 5): auto-pauses the string. If you're saving everyone, you're not evaluating — the string is surfacing a population that passes the bar trivially, which means the bar isn't calibrated for this population.

**Save rate spike** (default 60% over a rolling 15-evaluation window): auto-pauses. The string is almost certainly acting as an employer-name net rather than a quality filter.

**Consecutive rejects** (default 20): flags for review. May indicate prompt drift toward avoidance, or simply a dead string where the population doesn't match the role.

**Facial YES rate anomaly**: monitors whether triage pass-through falls within the expected range defined in the brief. Too high means triage isn't filtering; too low means avoidant drift at the triage stage.

**Parse failure rate** (default 3% across 20+ decisions): flags extraction or prompt quality issues at the session level.

All thresholds come from the brief — role-specific calibration, not hardcoded defaults. The Colombia brief sets consecutive saves at 7 and consecutive rejects at 15, reflecting a denser talent market where longer save and reject streaks are expected.

## Anti-Detection

The agent produces browser behavior that is structurally identical to a human sourcer's — not merely randomized, but shaped by the same distributions that govern human interaction timing.

| Layer | Implementation |
|-------|---------------|
| **Browser** | `rebrowser-playwright` CDP connection (Runtime.Enable evasion) to a real Chrome session |
| **Mouse movement** | `python-ghost-cursor` Bezier trajectories with Fitts's Law timing on all clicks (sourcing + decoy) |
| **Scrolling** | Chunked `page.mouse.wheel()` with 40-150px increments and variable inter-chunk delays |
| **Timing** | Log-normal distributions with temporal autocorrelation. No uniform random. |
| **Cadence breaks** | Decoy agent activity bursts replace fixed-interval pauses during active sourcing sessions |
| **Cross-product diversity** | Decoy generates feed, notification, and job browsing activity interleaved with Recruiter sourcing |
| **Session patterns** | Log-normal session durations (median 2h), dormant periods (median 110 min), and inter-burst intervals (median 25-30 min) |
| **Time-of-day** | Operating window start jittered +/-30 min per session. Hard cutoff at 1 AM. |

## Safety Governor

Hard limits — constants in `governor.py`, not configurable at runtime:

| Limit | Value |
|-------|-------|
| Max session duration | 3 hours |
| Max profile opens per session | 200 |
| Max profile opens per rolling 24h | 400 |
| Operating window | ~6:30-7:30 AM to 1:00 AM (start jittered, end rigid) |
| Max sessions per day | 3 |

When any limit is hit, the pipeline finishes its current candidate evaluation, saves progress, and transitions to dormant mode (decoy only) or shuts down.

## Quick Start

### 1. Launch Chrome with CDP

```bash
./launch-chrome.sh
```

This opens Chrome with `--remote-debugging-port=9222` using a persistent profile at `~/.chrome-cdp`. Log into LinkedIn Recruiter once — the session persists across restarts.

### 2. Check your budget

```bash
python3 session_orchestrator.py --status
```

### 3. Run

```bash
# Autonomous search evolution — agent generates its own search strings from the brief
python3 session_orchestrator.py \
  --brief config/brief-fdl-colombia-v3.json

# With a pre-built search config (dumb path — runs strings as-is)
python3 session_orchestrator.py \
  --brief config/brief-fdl-colombia-v3.json \
  --search-config config/search-strings-and-filters.json

# Single session — one sprint, then stop
python3 session_orchestrator.py \
  --brief config/brief-fdl-colombia-v3.json \
  --single-session

# Resume from last saved progress
python3 session_orchestrator.py \
  --brief config/brief-fdl-colombia-v3.json \
  --resume

# Restart a specific string from page 1 (implies --resume)
python3 session_orchestrator.py \
  --brief config/brief-fdl-colombia-v3.json \
  --restart-string 5

# Decoy only — passive browsing, no sourcing (cool-down days)
python3 session_orchestrator.py --decoy-only

# Or use the shortcut script:
./run-search.sh                    # full day cycle with default brief
./run-search.sh --single-session   # single session
./run-search.sh --status           # check budget
```

### 4. Stop

**Ctrl+C** (once) — graceful shutdown. Finishes current candidate evaluation, saves progress to `output/progress.json`, exits cleanly. **Ctrl+C** (twice) — force shutdown for when the agent is stuck in a blocking API call. The system also auto-stops at the 1 AM hard cutoff.

## Dependencies

- Python 3.11+
- `rebrowser-playwright` — CDP browser automation with detection evasion
- `python-ghost-cursor` — Bezier mouse trajectory generation
- `anthropic` — Claude Opus for judgment and strategy
- `openai` or `google-generativeai` — cheap model for DOM extraction
- `python-dotenv` — environment config
- Chrome with `--remote-debugging-port=9222`
- LinkedIn Recruiter seat with active session

## License

Private — internal use only.
