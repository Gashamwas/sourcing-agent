# Autonomous Sourcing Agent

An AI agent that autonomously sources candidates on LinkedIn Recruiter — running Boolean searches, evaluating profiles against role-specific criteria, and saving qualifying candidates to a pipeline. It operates for hours without human intervention, reports its reasoning in real time via WhatsApp, and improves its search strategy based on what it finds.

Built during Feb–Mar 2026 for sourcing frontier AI roles (post-training, RL environments, coding agents) across Brazil and Colombia. Produced 69 pipeline candidates across 7 sessions.

## How It Works

```
Search Kit Library ──→ Boolean strings
                           │
Sourcing Brief (JSON) ──→ Role config (archetypes, signals, noise patterns)
                           │
                    ┌──────┴──────┐
                    │  SKILL.md   │  ← Structural rules for every run
                    │  + Brief    │  ← Role-specific evaluation criteria
                    └──────┬──────┘
                           │
                  OpenClaw Agent (Claude Opus)
                           │
              ┌────────────┼────────────┐
              │            │            │
         LinkedIn     Evaluate     Report via
         Recruiter    profiles     WhatsApp
              │            │            │
         Run Boolean   Save/skip   Real-time
         strings       decisions   reasoning
              │            │            │
              └────────────┼────────────┘
                           │
                    Progress logs (JSON)
                    with per-candidate decisions
```

### The Loop

1. Agent loads a **sourcing brief** (role parameters, evaluation criteria, known noise patterns)
2. Navigates to LinkedIn Recruiter, applies permanent filters (geography, field of study)
3. For each Boolean string from the [Search Kit Library](https://search-kit-library.vercel.app):
   - Pastes the string into Keywords, reads result count
   - Triages candidates from preview cards — only clicks into profiles with visible signal
   - Evaluates each profile against the brief's archetypes and noise population definition
   - Saves qualifying candidates to the LinkedIn Recruiter project pipeline
   - Logs every decision (add/skip, archetype match, signals, confidence, reasoning)
   - Reports progress via WhatsApp with per-candidate reasoning
4. When strings fail (noise, zero results), the agent diagnoses why and adapts:
   - Removes noisy terms, logs collision patterns
   - Builds supplementary strings from its own analysis
   - Produces market intelligence as a byproduct (talent nodes, keyword rankings, gap analysis)

### What Makes the Evaluations Work

The agent doesn't just keyword-match. It makes judgment calls that require domain knowledge:

- **Disambiguation:** "Rejection sampling" on a chip design PhD's profile is Monte Carlo simulation, not RLHF. "Multimodal" as a company name building RAG pipelines is application-layer, not model training.
- **Contextual inference:** Someone on Microsoft's internal "Turing" team doing "evaluation" is doing LLM post-training eval, not generic QA.
- **Cross-role mapping:** An Isaac Sim robotics engineer building simulation environments for classical control has directly transferable skills to frontier RL environment design — even though the surface-level keywords don't match.

## Repository Structure

```
├── agent-workspace/           # The agent's "brain"
│   ├── SKILL.md               # Structural rules for all sourcing runs
│   ├── AGENTS.md              # OpenClaw workspace config (memory, safety, comms)
│   ├── briefs/                # Role-specific sourcing configurations
│   │   ├── fdl-brazil-rl-gyms.json
│   │   ├── fdl-brazil-kit-strings.json
│   │   └── fdl-colombia-rl-gyms.json
│   └── progress-sample-redacted.json  # Example progress log (names removed)
│
├── multi-model-pipeline/      # Experimental two-model architecture (Python)
│   ├── orchestrator.py        # Main pipeline loop
│   ├── browser.py             # Playwright browser automation
│   ├── extractors.py          # Cheap-model DOM extraction
│   ├── judger.py              # Opus evaluation calls
│   ├── hard-filters.py        # Pre-screening filters
│   ├── llm-clients.py         # API clients (Anthropic, OpenAI, Google)
│   ├── schemas.py             # Pydantic data models
│   ├── storage.py             # JSONL persistence
│   ├── config.py              # Configuration
│   ├── run.py                 # CLI entry point
│   ├── test-extractors.py     # Extraction tests
│   ├── requirements.txt
│   ├── config.example.env
│   ├── config/                # Brief and rubric configs
│   │   ├── brief-brazil-v2.json
│   │   ├── brief-colombia-v2.json
│   │   ├── evaluation-rubric.json
│   │   └── search-strings-and-filters.json
│   └── README.md
│
└── docs/
    └── business-case.html     # Internal investment case
```

## Key Components

### SKILL.md — The Agent's Rulebook

289 lines of structural rules that apply to every sourcing run regardless of role or geography:

- **Filter sanctity** — permanent filters (location, field of study) are never removed
- **Noise pattern recognition** — adapt to term collisions without stopping to ask
- **Evaluation threshold** — slightly expansive bias (when in doubt, save), but based on what the person *built*, not titles
- **Target vs. noise population** — the critical distinction between builders and operators (e.g., ML engineers vs. data annotators)
- **Decision documentation** — every eval logged with archetype match, signals, confidence, reasoning

This file evolved across 7 sessions. The most important lesson: concise, trust-the-docs instructions outperform verbose, redundant ones. When the prompt bloated from 250 to 700 words and restated rules already in SKILL.md, evaluation quality collapsed (Session 5 — see business case).

### Sourcing Briefs — Role Parameterization

JSON configs that make the agent role-specific without changing the skill:

- **Archetypes** — who you're looking for (e.g., "Lab Post-Training Engineer," "RL Infrastructure Engineer") with strong and moderate signals
- **Noise population** — who looks like the target but isn't (e.g., data annotators with RLHF keywords)
- **Known noise patterns** — term collisions specific to the geography (DPO = Data Protection Officer in Brazil, MBPP = nutrition industry term)
- **Evaluation philosophy** — two paths to qualification (pedigree track vs. direct experience track)
- **Calibration examples** — concrete save/skip/borderline calls the agent can reference

### Multi-Model Pipeline — The Next Architecture

The current system runs everything through Claude Opus — including mechanical browser tasks (clicking, scrolling, reading DOM) that require no judgment. The multi-model pipeline separates concerns:

```
LinkedIn DOM ──→ [Cheap Model: Extract] ──→ [Hard Filters] ──→ [Opus: Evaluate]
```

- **Cheap model** (GPT-4o-mini / Gemini Flash): handles DOM extraction, produces structured JSON snippets
- **Opus**: sees only structured candidate data (~200–1500 tokens vs ~15–20K tokens of raw DOM per page)
- **Estimated cost reduction**: 80–90% of AI spend

Status: architecture designed, code written, not yet tested in production.

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

Session 5 was the failure case — a bloated prompt and removed filters caused the agent to bulk-save 398 annotation workers without evaluating them. The recovery (Sessions 6–7A) produced the system's best results: 100% save accuracy on kit strings, zero evaluation corrections needed.

Full analysis in [`docs/business-case.html`](docs/business-case.html).

## Dependencies

### Current System (OpenClaw-based)
- [OpenClaw](https://www.npmjs.com/package/openclaw) — AI agent framework with browser integration
- Claude Opus (Anthropic API) — evaluation model
- WhatsApp channel — real-time reporting
- LinkedIn Recruiter seat

### Multi-Model Pipeline
- Python 3.11+
- Playwright (browser automation)
- Anthropic API (Opus for judgment)
- OpenAI or Google API (cheap model for extraction)

### Search Kit Library
- Separate repo — generates the Boolean string kits the agent executes
- Live at [search-kit-library.vercel.app](https://search-kit-library.vercel.app)

## Running the Agent (Current System)

```bash
# Install OpenClaw
npm install -g openclaw@latest

# Start the gateway
openclaw gateway --port 18789

# Attach a Chrome tab with LinkedIn Recruiter open
# (click the OpenClaw Browser Relay extension icon)

# Start a sourcing session
openclaw agent --message "Run the linkedin-sourcing skill using fdl-brazil-rl-gyms brief"
```

The agent will:
1. Load the brief and SKILL.md
2. Navigate to the Search Kit Library to collect Boolean strings
3. Apply permanent filters on LinkedIn Recruiter
4. Begin sequential string execution with real-time WhatsApp reporting

## Running the Multi-Model Pipeline

```bash
cd multi-model-pipeline
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp config.example.env .env
# Edit .env with API keys

# Test on a single page
python run.py --brief config/brief-brazil-v2.json --test-single-page

# Full run
python run.py --brief config/brief-brazil-v2.json --search-config config/search-strings-and-filters.json
```

## License

Private — internal use only.
