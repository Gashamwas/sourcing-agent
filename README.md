# Sourcing Agent

Sourcing Agent is a role-driven sourcing system for LinkedIn Recruiter and GitHub. It takes a structured brief, plans searches, evaluates candidates, adapts as it learns from results, and writes resumable run state so work can continue across sessions.

The repo started as an autonomous search agent, but the current system is broader than that. It now includes the search adapters themselves, a shared runtime layer, operator tooling, end-of-run reporting, market-intelligence generation, and a workflow for turning run learnings back into the next version of a brief.

## What the brief does

The brief is the center of the system. It is where the role-specific judgment lives: what kind of work the team actually needs, where the yes/no boundary sits, which lookalike profiles usually waste time, how the search should open, and what kinds of evidence should matter on LinkedIn and GitHub.

That design choice is deliberate. Recruiting judgment is usually scattered across
intake notes, recruiter memory, search strings, and ad hoc evaluation habits.
Here it is captured in one place and made executable. The result is a role
definition the team can reuse, inspect, and apply consistently across runs.

The loader supports older brief formats as well as the newer structured schema. Newer briefs can also carry an explicit `retrieval_design`, which lets the search open from layered intent instead of a flat list of terms.

## Current system

### LinkedIn

The LinkedIn side of the system connects to a live Chrome session over CDP, works inside LinkedIn Recruiter, generates search strings from the brief, and evaluates candidates in two stages: a lightweight snippet pass followed by a deeper profile review when the snippet looks promising.

The search loop has moved beyond a simple narrow-or-broaden cycle. The current implementation tracks root queries, sibling variants, rescue attempts, and drift over time, then persists that search state in runtime storage. The session orchestrator also manages pacing, resumability, session budgets, and optional decoy activity for safer long-running Recruiter sessions.

### GitHub

The GitHub side uses API-driven search rather than browser automation. It works across several channels, including user search, code search, topic search, repository mining, stargazer mining, and graph expansion from strong candidates. It enriches candidates with repository, contribution, profile, and contact data before running the same kind of structured judgment flow used on LinkedIn.

For saved candidates, the GitHub flow can generate outreach copy and export a CSV for operator use. It also feeds strong candidates back into graph expansion so the search can move outward from real signal instead of staying trapped in the initial query set.

### Shared runtime and reporting

Both adapters now sit on top of a shared execution model. `runtime_state.sqlite3`
is the authoritative record of candidate lifecycle, work-unit status, side
effects, and resume state. Files such as `progress.json` and the stage JSONLs
are still written because they are useful operationally, but they exist as
compatibility and visibility artifacts rather than control-state inputs.

That runtime layer is what makes the rest of the repo possible. It supports resumable runs, projection rebuilds, targeted restarts, run snapshots, structured debriefs, market-intelligence artifacts, and draft brief iteration based on what the search actually learned.

## Repository layout

```text
sourcing-agent/
├── config/                # Role briefs and supporting job-description files
├── linkedin/              # LinkedIn Recruiter adapter, browser automation, search intelligence
├── github/                # GitHub adapter, enrichment, query planning, exports, observability
├── market_intelligence/   # Post-run synthesis, research backends, artifact generation
├── shared/                # Brief loading, schemas, runtime state, execution engine, utilities
├── tools/                 # Runtime admin, brief iteration, market-intel update helpers
├── docs/                  # Runbooks, cheat sheets, architecture notes, archived campaign docs
└── output/                # Mutable state, finalized run snapshots, exports, market intel
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.env .env
```

Fill in the keys you need in `.env`.

- `ANTHROPIC_API_KEY` is required for the higher-judgment steps.
- `OPENAI_API_KEY` or `GOOGLE_API_KEY` is used for lower-cost extraction and synthesis work.
- `GITHUB_TOKEN` is required for GitHub sourcing.
- `PERPLEXITY_API_KEY` is optional and only matters if you want external research during market-intelligence updates.

If you plan to run LinkedIn, start Chrome through the helper script and keep your Recruiter session logged in:

```bash
./launch-chrome.sh
```

## Common commands

These examples use two current briefs that already exist in the repo:

```bash
LINKEDIN_BRIEF=config/Forward-Deployed-Engineer-NYC/brief-forward-deployed-engineer-us-v1.4.json
GITHUB_BRIEF=config/Forward-Deployed-Engineer-NYC/brief-forward-deployed-engineer-us-github-v1.json
```

### LinkedIn runs

Recommended entry point:

```bash
python3 linkedin/session_orchestrator.py --brief "$LINKEDIN_BRIEF"
```

Useful variants:

```bash
python3 linkedin/session_orchestrator.py --brief "$LINKEDIN_BRIEF" --single-session
python3 linkedin/session_orchestrator.py --brief "$LINKEDIN_BRIEF" --resume
python3 linkedin/session_orchestrator.py --brief "$LINKEDIN_BRIEF" --status
python3 linkedin/session_orchestrator.py --brief "$LINKEDIN_BRIEF" --restart-string 12 --resume
python3 linkedin/session_orchestrator.py --decoy-only
```

If you want the direct pipeline without the session orchestrator:

```bash
python3 run_linkedin.py --brief "$LINKEDIN_BRIEF" --full-run
```

### GitHub runs

Recommended entry point:

```bash
python3 run_github.py --brief "$GITHUB_BRIEF"
```

Useful variants:

```bash
python3 run_github.py --brief "$GITHUB_BRIEF" --resume
python3 run_github.py --brief "$GITHUB_BRIEF" --status
python3 github/session_orchestrator.py --brief "$GITHUB_BRIEF" --single-session
python3 github/run.py --brief "$GITHUB_BRIEF"
```

### Post-run workflow

Update market intelligence from a finalized run snapshot:

```bash
python3 tools/update_market_intel.py \
  --brief "$LINKEDIN_BRIEF" \
  --run-dir output/runs/linkedin/<brief-id>/<run-stamp>__run-<id> \
  --mode post_run
```

Draft the next version of a brief from a run report:

```bash
python3 -m tools.iterate_brief \
  --brief "$LINKEDIN_BRIEF" \
  --report output/runs/linkedin/<brief-id>/<run-stamp>__run-<id>/run-report.json \
  --search-memory output/runs/linkedin/<brief-id>/<run-stamp>__run-<id>/search_memory-<brief-id>.json \
  --final-judgments output/runs/linkedin/<brief-id>/<run-stamp>__run-<id>/final_judgments.jsonl \
  --output-dir output
```

### Runtime administration

If a run already has `runtime_state.sqlite3`, use the admin surface instead of editing `progress.json` or JSONL files by hand.

```bash
python3 tools/runtime_state_admin.py \
  --output-dir output/state/linkedin/<brief-id> \
  --source linkedin \
  --brief-id <brief-id> \
  rebuild-projections
```

Other supported admin operations include inspecting orphaned attempts, inspecting stop reasons, replaying side effects, requeueing work units, and restarting a specific LinkedIn string.

## Output model

Live work happens under `output/state/`. Completed runs are copied into immutable snapshots under `output/runs/`. Market-level synthesis lives under `output/market_intelligence/`, and operator-facing exports land under `output/exports/`.

In practice, the layout looks like this:

- `output/state/linkedin/<brief-id>/` for live LinkedIn state
- `output/state/github/<brief-id>/` for live GitHub state
- `output/runs/<source>/<brief-id>/<run-stamp>__run-<id>/` for finalized snapshots
- `output/market_intelligence/<market-key>/` for canonical market-intel artifacts
- `output/exports/<source>/<brief-id>/` for CSVs and other operator-facing outputs

The important implementation detail is that the SQLite runtime store is canonical. Compatibility artifacts are rebuilt from it when needed.

## Testing

The repo has a broad test suite around runtime state, search intelligence, adapter services, market intelligence, brief iteration, and the shared execution layer.

```bash
python3 -m pytest
```

## Notes

This is an internal project. The system is intentionally opinionated because it
is designed to preserve sourcing judgment alongside automation. The newer parts
of the repo reflect that direction: better runtime discipline, clearer operator
tooling, stronger post-run analysis, and a tighter loop between what the search
learns and how the brief evolves.

## License

Private and internal use only.
