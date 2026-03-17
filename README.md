# Autonomous Sourcing Agent

An AI-powered sourcing pipeline that autonomously searches LinkedIn Recruiter, evaluates candidates against role-specific criteria through a multi-model architecture, and runs for hours unattended with built-in safety guardrails and ambient activity generation for anti-detection.

Built during Feb–Mar 2026 for sourcing frontier AI roles (post-training, RL environments, coding agents) across Brazil and Colombia. Produced 69 pipeline candidates across 7 sessions.

## Architecture

```
session_orchestrator.py                    ← Single entry point
├── Session Governor                       ← Hard safety limits (profile caps, time window)
│   ├── 200/session, 400/24h profile caps
│   ├── 3h session duration cap
│   ├── 7 AM – 11 PM operating window (±30 min jitter)
│   └── 3 sessions/day max
│
├── Sourcing Pipeline (orchestrator.py)    ← Main evaluation loop
│   ├── Boolean search entry
│   ├── Results extraction (cheap model)   ← GPT-4o-mini / Gemini Flash
│   ├── Facial judgment (Opus)             ← Snippet-only triage
│   ├── Full profile evaluation (Opus)     ← Deep assessment
│   ├── Two-phase adaptation               ← Scout → Paginate with Opus decisions
│   └── Block-level strategy adjustment    ← Opus reviews and pivots mid-run
│
├── Decoy Agent (decoy/)                   ← Passive LinkedIn.com browsing
│   ├── Feed scrolling (no engagement)
│   ├── Notification checking
│   └── Job browsing
│
└── Multi-Session Cycler
    └── Sprint → Dormant (decoy only) → Sprint → Dormant → Sprint
```

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

Only ~6 of 25 candidates per page pass facial judgment and trigger a profile open. This keeps the profile-open rate low while still evaluating every candidate.

## Anti-Detection

| Layer | Implementation |
|-------|---------------|
| **Browser** | `rebrowser-playwright` CDP connection (Runtime.Enable evasion) to a real Chrome session |
| **Mouse movement** | `python-ghost-cursor` Bézier trajectories with Fitts's Law timing on all clicks (sourcing + decoy) |
| **Scrolling** | Chunked `page.mouse.wheel()` with 40-150px increments and variable inter-chunk delays |
| **Timing** | Log-normal distributions with temporal autocorrelation (`human_timing.py`). No uniform random. |
| **Cadence breaks** | Decoy agent activity bursts replace fixed-interval pauses during active sourcing sessions |
| **Cross-product diversity** | Decoy generates feed, notification, and job browsing activity interleaved with Recruiter sourcing |
| **Session patterns** | Log-normal session durations (median 2h), dormant periods (median 110 min), and inter-burst intervals (median 25-30 min) |
| **Time-of-day** | Operating window start jittered ±30 min per session. Hard cutoff at 11 PM. |

## Safety Governor

Hard limits — constants in `governor.py`, not configurable at runtime:

| Limit | Value |
|-------|-------|
| Max session duration | 3 hours |
| Max profile opens per session | 200 |
| Max profile opens per rolling 24h | 400 |
| Operating window | ~6:30-7:30 AM to 11:00 PM (start jittered, end rigid) |
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
# Full day cycle — autonomous multi-session with dormant periods
python3 session_orchestrator.py \
  --brief config/brief-fdl-brazil-v3.json \
  --search-config config/search-strings-and-filters.json

# Single session — one sprint, then stop
python3 session_orchestrator.py \
  --brief config/brief-fdl-brazil-v3.json \
  --search-config config/search-strings-and-filters.json \
  --single-session

# Decoy only — passive browsing, no sourcing (cool-down days)
python3 session_orchestrator.py --decoy-only

# Or use the shortcut script:
./run-search.sh                    # full day cycle with default brief
./run-search.sh --single-session   # single session
./run-search.sh --status           # check budget
```

### 4. Stop

**Ctrl+C** — graceful shutdown. Finishes current candidate evaluation, saves progress to `output/progress.json`, exits cleanly. The system also auto-stops at the 11 PM hard cutoff.

### Standalone pipeline (no orchestrator)

`run.py` still works for direct pipeline runs without the session governor or decoy agent:

```bash
python3 run.py                                           # interactive mode
python3 run.py --brief config/brief-X.json --full-run    # autonomous run
python3 run.py --brief config/brief-X.json --full-run --resume
python3 run.py --brief config/brief-X.json --test-single-page
```

## File Structure

```
├── session_orchestrator.py   # Entry point — day cycle, decoy interleaving, CLI
├── governor.py               # Hard safety limits, profile open counting
├── cooldown.py               # Persistent 24h rolling window tracker
├── orchestrator.py           # Core sourcing pipeline (search → evaluate → save)
├── browser.py                # Playwright CDP connection, ghost-cursor, DOM ops
├── human_timing.py           # Log-normal delay distributions with autocorrelation
├── config.py                 # Environment/settings loader
├── run.py                    # Standalone CLI entry point (no orchestrator)
│
├── extractors.py             # Cheap-model DOM extraction (snippets + profiles)
├── judger.py                 # Opus facial + full judgment calls
├── judgment_templates.py     # System prompts for Opus evaluation
├── strategy.py               # Opus strategy formation + block-level adaptation
├── kit_extractor.py          # Boolean string extraction from LinkedIn Search Kit
├── preflight.py              # Generate evaluation criteria from JD
├── preflight_v2.py           # V2 preflight with structured brief output
├── bias_controls.py          # Bias monitoring + alerting
│
├── schemas.py                # Data models (CandidateSnippet, Progress, SearchString)
├── storage.py                # JSONL I/O, progress checkpointing
├── llm_clients.py            # API clients (Anthropic, OpenAI, Google)
├── brief_loader.py           # Load and validate sourcing briefs
├── brief_schema.py           # Brief structure validation
│
├── decoy/
│   ├── agent.py              # Decoy agent — tab management, burst execution
│   ├── scheduler.py          # Log-normal burst timing with autocorrelation
│   └── actions/
│       ├── _utils.py         # Shared helpers (ghost_click, human_scroll)
│       ├── feed.py           # Passive feed scrolling
│       ├── notifications.py  # Notification checking
│       └── jobs.py           # Job browsing
│
├── config/                   # Sourcing briefs and search configs
│   ├── brief-fdl-brazil-v3.json
│   ├── search-strings-and-filters.json
│   └── ...
│
├── docs/
│   ├── business-case.html
│   ├── linkedin-recruiter-dom-map.md
│   └── protocol-reference.md
│
├── output/                   # Pipeline output (gitignored)
│   ├── progress.json         # Resume checkpoint
│   ├── snippets.jsonl        # Extracted candidates
│   ├── facial_judgments.jsonl
│   ├── final_judgments.jsonl
│   └── run_log.jsonl
│
├── launch-chrome.sh          # Start Chrome with CDP debugging
├── run-search.sh             # Shortcut for session_orchestrator.py
└── requirements.txt
```

State files at `~/.sourcing-governor/`:
- `daily_stats.json` — rolling 24h profile open timestamps
- `sessions.jsonl` — per-session summaries
- `decoy.jsonl` — decoy activity log

## Results

| Session | Date | Geography | Agent Saves | Pipeline | Accuracy | Pipeline/Hr |
|---------|------|-----------|-------------|----------|----------|-------------|
| S1 | Feb 24 | Brazil | 55 | 10 | 18.2% | 1.2 |
| S4 | Mar 2–3 | Brazil | ~66 | 25 | ~37.9% | 2.7 |
| S5 (named) | Mar 4 | Brazil | 12 | 2 | 16.7% | — |
| S5 (bulk) | Mar 4 | Brazil | 398 | 8 | 2.0% | — |
| S7A Kit | Mar 5 | Brazil | 15 | 15 | 100% | 5.9 |
| S7A Freestyle | Mar 5 | Brazil | 11 | 9 | 81.8% | 6.3 |
| **Total** | | | **~557** | **69** | | |

Session 5 was the failure case — a bloated prompt and removed filters caused the agent to bulk-save 398 annotation workers. The recovery (Sessions 6–7A) produced the system's best results: 100% save accuracy on kit strings, zero evaluation corrections needed.

Full analysis in [`docs/business-case.html`](docs/business-case.html).

## Dependencies

- Python 3.11+
- `rebrowser-playwright` — CDP browser automation with detection evasion
- `python-ghost-cursor` — Bézier mouse trajectory generation
- `anthropic` — Claude Opus for judgment and strategy
- `openai` or `google-generativeai` — cheap model for DOM extraction
- `python-dotenv` — environment config
- Chrome with `--remote-debugging-port=9222`
- LinkedIn Recruiter seat with active session

## License

Private — internal use only.
