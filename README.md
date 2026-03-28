# Autonomous Sourcing Agents

Two autonomous agents — one for LinkedIn Recruiter, one for GitHub — that take a sourcing brief and execute it without human intervention. The brief is not configuration. It is the recruiter's expertise about a role, its target candidate archetypes, and the noise patterns specific to a geography, codified into a machine-executable policy. The agents write their own search strategies, evaluate every candidate through structured claim-and-evidence procedures that distinguish builders from users, adapt in real time based on the signal they're getting, and generate entirely new queries mid-run when they discover unexpected talent patterns.

They do not keyword-match. They synthesize whole-candidate judgments the way a trained sourcer would: reading career trajectories, inferring depth from verbs and objects in work descriptions, recognizing when methodology transfers across domains even when the domain itself doesn't match.

```
┌─────────────────────────────────────────────────────────────────┐
│                        SOURCING BRIEF                           │
│  Capability areas · Depth distinction · Non-fit patterns        │
│  Employer signal tiers · Facial calibration · Bias controls     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
   ┌──────────────────┐     ┌──────────────────────┐
   │  LINKEDIN AGENT   │     │    GITHUB AGENT       │
   │                   │     │                       │
   │  Boolean strings  │     │  Multi-channel search │
   │  Browser auto.    │     │  REST API queries     │
   │  Recruiter UI     │     │  Code/repo/org mining │
   │  Ghost-cursor     │     │  Graph expansion      │
   │  Decoy system     │     │  Stargazer mining     │
   └────────┬──────────┘     └──────────┬────────────┘
            │                           │
            └────────────┬──────────────┘
                         ▼
          ┌──────────────────────────┐
          │    SHARED INFRASTRUCTURE  │
          │                          │
          │  Judgment chain           │
          │  Bias monitoring          │
          │  Brief schema             │
          │  Session governor          │
          │  Human timing simulation  │
          │  LLM dispatch             │
          └──────────────────────────┘
```

---

## The Brief — Recruiting Expertise, Codified

Everything both agents know about a role lives in a single JSON document. A brief defines **capability areas** with explicit builder/user signal distinctions (did this person *build* a reward model, or did they *use* one via API?), **non-fit patterns** calibrated to the specific labor market (BPO annotation work is the highest-volume noise pattern in Colombia; fintech ML engineers who only do fraud scoring are the trap in Brazil), **employer signal tiers** that encode which company names carry signal and how much, and **facial calibration** that sets expected triage pass-through rates so the bias monitor can detect evaluation drift.

The **depth distinction** is the single most important calibration in the brief. It governs every evaluation across both agents: "Has done hands-on ML work where data quality, model training, or evaluation methodology was a primary focus" vs. "Uses ML models as components in applications without involvement in how those models are trained, evaluated, or improved." Builder vs. user. This distinction is role-specific — the boundary shifts depending on what the role actually needs.

The Colombia brief defines 7 capability areas (from RL & Post-Training Data Systems to Embodied AI & Simulation), 6 non-fit patterns, 4 employer signal tiers, and inferential save rules for sparse profiles with strong priors. Swapping roles means swapping briefs. Nothing else changes.

---

## LinkedIn Agent

### Strategy Formation

The agent receives the brief and an optional **kit vocabulary** — Boolean search terms organized by competency domain. Kit terms are raw building blocks, not executable queries. The agent synthesizes them into 15-30+ compound Boolean strings in a single planning call.

Two string types. **Type A recall strings** cast broad nets — 500 to 5,000 expected results — by AND-gating skill clusters with geography and seniority qualifiers. **Type B precision "sniper" strings** use specific tool names, framework names, and benchmark names that only genuine practitioners would have on their profile — SWE-bench, Axolotl, Constitutional AI, TRL, vLLM — producing 20-500 results where nearly every hit is a real builder.

The sequencing is deliberate. Precision strings run early. RL/RLHF strings — the densest, most well-trodden talent pool — are backloaded. Rationale: thinner capability areas surface more net-new candidates per string, RL practitioners appear incidentally in non-RL strings, and by the time RL strings execute, the adaptation loop has learned from earlier noise patterns.

Every string is governed by LinkedIn Boolean rules that most sourcers get wrong. LinkedIn has no stemming — "model" does not match "models," "fine-tuning" does not match "fine-tuned" — so the agent includes all morphological variants. Substring embedding means superstrings are never added. Abbreviations with dominant non-ML meanings are filtered: "DPO" matches Data Protection Officer, "IPO" matches Initial Public Offering — these are only used paired with their full expansions.

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
  Full judgment ──→ [Opus] ──→ SAVE / REJECT / INFERENTIAL_SAVE
        │
        ▼
  Save to Recruiter pipeline (if qualifying)
```

**Facial triage** reads the full career trajectory from snippet data alone — name, headline, positions with titles and dates. Fast exits apply only when the *entire* trajectory clearly indicates work outside scope. One relevant-looking position anywhere in the history blocks a fast exit. Ambiguity defaults to YES: the cost of a false positive is one cheap profile extraction; the cost of a false negative is a permanently missed candidate. Expected pass-through is 25-50%.

**Full evaluation** follows a four-step structured procedure:

1. **Capability Mapping.** Map actual work (from experience bullets, not titles) to the brief's capability areas. Result: DIRECT, ADJACENT, or NONE.
2. **Depth Test.** Builder or user? Reads verbs and objects. "Designed, built, fine-tuned, trained" are builder verbs. "Deployed, integrated, managed, used a pre-built model" are user verbs. "Fine-tuned" is a builder verb. "Fine-tuned via API" is a user verb.
3. **Transferability** (when no direct capability match). Would this person's methodology apply if pointed at the target domain? Evaluation framework design transfers. Data curation pipeline design transfers. Classical engineering simulation does not.
4. **Decision.** Strongest case for and against, then decide. DIRECT + BUILDER = SAVE. ADJACENT + BUILDER = SAVE. No match + BUILDER + TRANSFERABLE = TRANSFERABLE_SAVE. Any match + USER = REJECT.

### Within-String Adaptation

The agent treats page 1 as a scout. After evaluating it, the agent decides: **paginate** (signal looks good), **narrow** (too much noise — add AND clauses), or **abandon** (wrong population entirely). During pagination, accumulated statistics after each page drive decisions: **continue**, **narrow**, **broaden**, **stop**, or **abandon**.

Narrowing pushes the current Boolean onto a refinement stack; broadening pops it. The agent navigates the specificity gradient in either direction with full history:

```
Original: ("agentic" OR "LLM agent") AND ("financial services" OR "banking")
  → Narrow: + AND ("production" OR "deployment" OR "enterprise")
    → Narrow again: + AND NOT ("RPA" OR "chatbot")
      → Broaden: revert to first narrowing
```

### Block-Level Adaptation

After every batch of strings, the agent reviews a **BlockReport** — which strings produced saves, which were zero-save noise, what unexpected populations appeared, what terms collided with undesired demographics. It generates new compound strings targeting discovered signal patterns, recommends skipping redundant queued strings, reorders remaining strings by observed productivity, and updates noise pattern knowledge.

This is the formalization of what a recruiter does naturally when adjusting search strategy mid-session based on who they're actually finding. The difference is perfect recall of every candidate evaluated, every save rate, and every noise collision across every string.

### Decoy System & Anti-Detection

The agent produces browser behavior structurally identical to a human sourcer's — not merely randomized, but shaped by the same distributions that govern human interaction timing.

A **decoy agent** runs in a separate browser tab, generating ambient LinkedIn activity (feed scrolling, notification checking, job browsing) that obscures sourcing as an isolated behavior. It operates during sourcing sessions (interleave bursts every ~30 minutes) and between sessions (dormant-mode bursts every ~25 minutes). All timing follows log-normal distributions with temporal autocorrelation — the statistical signature of human attention patterns, not the entropy profile of automation.

| Layer | Implementation |
|-------|---------------|
| **Browser** | `rebrowser-playwright` CDP connection to a real Chrome session |
| **Mouse** | `python-ghost-cursor` Bezier trajectories with Fitts's Law timing |
| **Scrolling** | Chunked wheel events, 40-150px increments, variable delays |
| **Timing** | Log-normal distributions with autocorrelation. No uniform random. |
| **Sessions** | Log-normal durations (median ~4h), dormant periods (median ~110 min) |
| **Time-of-day** | Operating window jittered ±30 min per session. Hard cutoff at 1 AM. |

---

## GitHub Agent

The GitHub agent operates on a fundamentally different information surface. LinkedIn gives you career trajectories and self-described experience bullets. GitHub gives you code — what people actually built, the tools they chose, the repositories they contributed to, and who they collaborate with. The evaluation challenge is different: LinkedIn candidates over-describe; GitHub candidates under-describe. A GitHub profile might have no bio, no company, and no README, but the commit history in a fork of `trl` tells you everything the brief needs to know.

### Multi-Channel Search Strategy

Where the LinkedIn agent writes Boolean strings against a single search interface, the GitHub agent operates across 7 distinct search channels, each surfacing candidates through different signal:

| Channel | What it finds | Example |
|---------|--------------|---------|
| **User Search** | Profiles by bio, location, language | `language:python location:Brazil followers:>50` |
| **Code Search** | People who wrote specific imports | `"from trl import" language:python` |
| **Topic Search** | Repos tagged with discriminating topics | `topic:reinforcement-learning stars:>20` |
| **Repo Mining** | Contributors to frontier repositories | All committers to OpenRLHF, vLLM, Axolotl |
| **Org Exploration** | Members of known AI organizations | Anthropic, DeepMind, Cohere org members |
| **Stargazer Mining** | People who starred niche repos | Who starred a Constitutional AI implementation? |
| **Graph Expansion** | Social connections of seed experts | Followers/following of known practitioners |

The agent generates 15-30+ queries across these channels in a single strategy call, then validates and repairs each query's syntax before execution (`github/query_validator.py` strips natural language filler, converts prose to API syntax, and deduplicates against executed queries).

### Frontier Toolchain Fingerprinting

The key innovation in the GitHub agent is **code-level signal extraction**. Instead of relying on how people describe themselves, it finds what they actually imported:

```python
# These imports are fingerprints — only practitioners write them
"from trl import PPOTrainer"          # Post-training / RLHF
"from axolotl.utils import"           # Fine-tuning infrastructure
"from swebench import"                # Code agent evaluation
"from vllm import LLM"                # Inference optimization
"from constitutional_ai import"       # Alignment research
```

The cheap model reads repository descriptions and README content, then classifies each repo as **builder** (custom training loop, RLHF pipeline, novel architecture) or **user** (fork with minimal changes, tutorial notebook, API wrapper). This distinction — the same builder/user depth test from the brief — operates on code artifacts instead of self-reported experience bullets.

### Enrichment Pipeline

```
GitHub search result (username)
        │
        ▼
  Light enrich ──→ Profile + geo-gate against brief's permanent filters
        │
        │ (passes geo-filter)
        ▼
  Full enrich ──→ Top repos + languages + README content
        │          + frontier repo contributions (forks, commits)
        │          + personal website crawl
        │          + arXiv paper extraction
        │          + contact discovery (email, social links)
        │
        ▼
  [Cheap Model] ──→ Portfolio synthesis (toolchain, ML signal strength)
        │
        ▼
  Facial judgment ──→ [Opus] ──→ FACIAL_YES / FACIAL_NO
        │
        │ (FACIAL_YES only)
        ▼
  Full judgment ──→ [Opus] ──→ SAVE / REJECT / INFERENTIAL_SAVE
        │
        ▼
  Priority-ranked save + outreach generation
```

**Graph expansion** captures practitioners invisible to keyword search — people working at small startups, maintaining side projects, or in academic labs with no public profile text. Seed with known frontier experts, mine their social graph, evaluate the connections.

### Adaptation

After every batch of queries, the agent compiles results — strings run, saves produced, zero-save strings, observed noise patterns — and asks Opus to generate new queries targeting discovered signal. The same adaptive loop as the LinkedIn agent, but across 7 search channels instead of one.

**Exhaustion detection** (`github/query_validator.py`) tracks per-channel saturation. When a channel stops producing net-new candidates, the agent shifts budget to channels that are still productive rather than grinding through diminishing returns.

---

## Shared Infrastructure

### Judgment Chain

Both agents use the same three-layer evaluation framework, but with platform-specific templates:

| Layer | LinkedIn | GitHub |
|-------|----------|--------|
| **Facial triage** | Career trajectory from snippet | Portfolio text from enrichment |
| **Full evaluation** | Experience bullets + work history | Repo analysis + code signals + contributions |
| **Post-save modifiers** | Secondary confidence boosts | Priority ranking for outreach |

The judgment templates (`linkedin/judgment_templates.py`, `github/judgment_templates.py`) encode the same recruiting logic — capability mapping, depth testing, transferability assessment — but read different evidence. A LinkedIn candidate's depth shows in their bullet points ("fine-tuned a reward model on 50K human preference pairs"). A GitHub candidate's depth shows in their code ("authored `reward_model.py` with custom loss function, not a fork").

### Bias Monitoring

Five monitors run continuously during every session:

| Monitor | Trigger | Action |
|---------|---------|--------|
| **Consecutive saves** | N≥5 (configurable per brief) | Pause string |
| **Save rate spike** | >60% over rolling 15 evaluations | Pause string |
| **Consecutive rejects** | N≥20 | Flag for review |
| **Facial YES rate anomaly** | Outside brief's expected range | Flag drift |
| **Parse failure rate** | ≥3% across 20+ decisions | Flag extraction issue |

These thresholds come from the brief — role-specific calibration, not hardcoded defaults. The Colombia brief sets consecutive saves at 7 and consecutive rejects at 15, reflecting a denser talent market.

Early in the project, the LinkedIn agent saved 398 annotation workers in a single session because the evaluation criteria were too permissive for the population a broad string surfaced. That failure mode — saving everyone because the cohort *looks* vaguely relevant — is what the bias control system prevents.

### Session Governor

Hard limits enforced across both agents:

| Limit | LinkedIn | GitHub |
|-------|----------|--------|
| Max session duration | 3.5-5h (log-normal) | Configurable |
| Max profile opens / session | 200 | N/A (API-based) |
| Max profile opens / 24h | 400 | N/A |
| API rate limiting | N/A | Token bucket per endpoint |
| Operating window | ~7 AM - 1 AM (jittered) | Unrestricted |
| Max sessions / day | 3 | Unrestricted |

The LinkedIn governor enforces limits that prevent account-level risk. The GitHub governor enforces API rate limits that prevent token exhaustion. Different constraints, same pattern: cooperative shutdown at safe checkpoints, never mid-evaluation.

### Human Timing Simulation

All delays across both agents follow log-normal distributions with temporal autocorrelation — consecutive delays are correlated, matching the clustering pattern of human attention shifts. Uniform random delays are detectable by entropy classifiers; log-normal is not. Parameters: μ≈1.5, σ≈0.8 → median ~4.5s, with a long tail up to ~30s.

---

## Architecture

```
sourcing-agent/
├── config/                  # Sourcing briefs (one per role)
├── github/                  # GitHub agent
│   ├── orchestrator.py      # Pipeline: strategy → search → enrich → evaluate → save
│   ├── strategy.py          # Multi-channel query generation + adaptation
│   ├── enricher.py          # Profile + repo + website + paper enrichment
│   ├── client.py            # GitHub REST API client with rate limiting
│   ├── query_validator.py   # Syntax repair, dedup, exhaustion tracking
│   ├── outreach.py          # Personalized message generation
│   ├── judgment_templates.py # GitHub-specific evaluation prompts
│   ├── governor.py          # API rate limit enforcement
│   ├── observability/       # Session metrics, strategy tracking, reporting
│   └── session_orchestrator.py
├── linkedin/                # LinkedIn agent
│   ├── orchestrator.py      # Pipeline: strategy → scroll → extract → evaluate → save
│   ├── browser.py           # Playwright automation + ghost-cursor + scrolling
│   ├── strategy.py          # Boolean string synthesis + adaptation
│   ├── judgment_templates.py # LinkedIn-specific evaluation prompts
│   └── session_orchestrator.py  # Multi-session cycling + decoy interleaving
├── decoy/                   # Ambient browsing noise generator
│   ├── agent.py             # Activity burst execution
│   ├── scheduler.py         # Log-normal inter-burst timing
│   └── actions/             # Feed, jobs, notifications browsing
├── shared/                  # Cross-agent infrastructure
│   ├── judger.py            # Judgment dispatch (facial/full × linkedin/github)
│   ├── bias_controls.py     # Decision recording + anomaly detection
│   ├── governor.py          # Session limits + time-of-day gating
│   ├── brief_loader.py      # Brief normalization (V1/V2)
│   ├── brief_schema.py      # Capability areas, depth distinction, employer tiers
│   ├── schemas.py           # CandidateSnippet, ProfileSummary, OpusDecision
│   ├── llm_clients.py       # Opus + cheap model dispatch
│   ├── human_timing.py      # Log-normal delays + autocorrelation
│   ├── config.py            # Environment + behavioral parameters
│   └── storage.py           # JSONL append, dedup, event logging
└── output/                  # Run artifacts (candidates, logs, progress)
```

---

## Quick Start

### LinkedIn Agent

```bash
# Launch Chrome with CDP
./launch-chrome.sh

# Check 24h budget
python3 linkedin/session_orchestrator.py --status

# Full day cycle — agent writes its own search strings
python3 linkedin/session_orchestrator.py --brief config/brief-fdl-colombia-v3.json

# Single session
python3 linkedin/session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --single-session

# Resume from saved progress
python3 linkedin/session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --resume

# Decoy only (cool-down days)
python3 linkedin/session_orchestrator.py --decoy-only
```

### GitHub Agent

```bash
# Full autonomous run
python3 run_github.py --brief config/brief-fdl-colombia-v3.json

# Resume from saved progress
python3 run_github.py --brief config/brief-fdl-colombia-v3.json --resume
```

### Stop

**Ctrl+C** once — graceful shutdown. Finishes current evaluation, saves progress, exits cleanly. **Ctrl+C** twice — force shutdown. Both agents auto-stop at governor limits.

---

## Dependencies

- Python 3.11+
- `rebrowser-playwright` — CDP browser automation with detection evasion
- `python-ghost-cursor` — Bezier mouse trajectory generation
- `anthropic` — Claude Opus for judgment and strategy
- `openai` or `google-generativeai` — cheap model for extraction and synthesis
- `python-dotenv` — environment config
- Chrome with `--remote-debugging-port=9222` (LinkedIn agent)
- GitHub personal access token (GitHub agent)
- LinkedIn Recruiter seat with active session (LinkedIn agent)

## License

Private — internal use only.
