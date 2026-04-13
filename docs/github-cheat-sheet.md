# GitHub Sourcing Agent — Cheat Sheet

## Prerequisites

1. `GITHUB_TOKEN` in `.env` (needs `read:user`, `read:org`, `repo` scopes)
2. `ANTHROPIC_API_KEY` in `.env` (Opus for evaluation)
3. `OPENAI_API_KEY` in `.env` (GPT-4o-mini for portfolio extraction)
4. A sourcing brief in `config/` (e.g., `config/brief-fdl-colombia-v3.json`)

Check your token works:
```bash
curl -s -H "Authorization: token $(grep GITHUB_TOKEN .env | cut -d= -f2)" https://api.github.com/rate_limit | python3 -m json.tool | head -10
```

---

## Start

**Single pipeline run (direct, no session management):**
```bash
python3 run_github.py --brief config/brief-fdl-colombia-v3.json
```

**Multi-session day cycle (recommended — handles session limits and cooldowns):**
```bash
python3 github/session_orchestrator.py --brief config/brief-fdl-colombia-v3.json
```

**Single session via orchestrator (one session, then stop):**
```bash
python3 github/session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --single-session
```

**Custom mutable state directory:**
```bash
python3 run_github.py --brief config/brief-fdl-colombia-v3.json --state-dir output/state/github/fdl_colombia
```

---

## Stop

| Action | How |
|--------|-----|
| **Graceful stop** — finishes current candidate, saves progress | `Ctrl+C` (once) |
| **Force kill** — immediate exit | `Ctrl+C` (twice) |
| **Graceful stop from another terminal** | `kill $(pgrep -f run_github)` or `kill $(pgrep -f github/session_orchestrator)` |
| **Force kill from another terminal** | `kill -9 $(pgrep -f run_github)` |

`Ctrl+C` once triggers graceful shutdown — the agent finishes the current candidate, saves progress, and exits. Progress is always saved so you can resume.

---

## Resume

**Resume from where you left off:**
```bash
python3 run_github.py --brief config/brief-fdl-colombia-v3.json --resume
```

**Resume via session orchestrator:**
```bash
python3 github/session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --resume
```

Resume picks up from the last saved progress state — candidates already processed are skipped, search channels continue from where they stopped.

---

## Check Status

**Current session budget:**
```bash
python3 run_github.py --status
```

**Or directly via the orchestrator:**
```bash
python3 github/session_orchestrator.py --status
```

Shows: sessions used today, sessions remaining, and whether you're clear to run.

---

## Output Contract

Live GitHub runs write into `output/state/github/<brief-id>/`.
Completed runs are snapshotted into `output/runs/github/<brief-id>/<run-stamp>__run-<id>/`.
CSV exports land in `output/exports/github/<brief-id>/`.

Common live-state files:

| File | Contents |
|------|----------|
| `candidates.jsonl` | All discovered candidates (raw GitHub profiles) |
| `final_judgments.jsonl` | Opus evaluation decisions (SAVE / REJECT / INFERENTIAL_SAVE) |
| `outreach.jsonl` | Generated outreach copy for saved candidates |
| `progress.json` | Session state — search channels, page positions, queues |
| `saved_candidates.csv` | Exported CSV in `output/exports/github/<brief-id>/` |

**Export to CSV manually (if auto-export didn't run):**
```bash
python3 -c "from github.export import export_saved_candidates_csv; export_saved_candidates_csv('output/state/github/<brief-id>', csv_path='output/exports/github/<brief-id>/saved_candidates.csv')"
```

**View saved candidates:**
```bash
cat output/state/github/<brief-id>/final_judgments.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    j = json.loads(line)
    if j.get('decision') in ('SAVE', 'INFERENTIAL_SAVE', 'TRANSFERABLE_SAVE'):
        print(f\"{j.get('username', '?'):20s}  {j.get('decision'):20s}  {j.get('confidence', '?')}\")
"
```

**Count saves vs rejects:**
```bash
cat output/state/github/<brief-id>/final_judgments.jsonl | python3 -c "
import sys, json, collections
c = collections.Counter()
for line in sys.stdin:
    c[json.loads(line).get('decision', 'UNKNOWN')] += 1
for k, v in c.most_common():
    print(f'  {k}: {v}')
"
```

---

## Governor Limits

These are hard limits — no flags, no overrides:

| Limit | Value |
|-------|-------|
| Max session duration | 3 hours |
| Max API calls per session | 4,000 (of 5,000/hr GitHub limit) |
| Max enrichments per session | 500 |
| Max sessions per day | 3 |

The governor auto-stops the session when any limit is hit. Progress is saved.

**State files** (for debugging):
```
~/.sourcing-governor/github/daily_stats.json   # session counters
~/.sourcing-governor/github/sessions.jsonl     # session history log
```

**Reset daily counters** (if stuck or testing):
```bash
rm ~/.sourcing-governor/github/daily_stats.json
```

---

## GitHub API Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| REST API (general) | 5,000 requests | 1 hour |
| Search API (users, repos) | 30 requests | 1 minute |
| Code search | 10 requests | 1 minute |

**Check your remaining quota:**
```bash
curl -s -H "Authorization: token $(grep GITHUB_TOKEN .env | cut -d= -f2)" https://api.github.com/rate_limit
```

The agent's built-in rate limiter handles all of this automatically. You don't need to worry about it unless something looks stuck.

---

## Search Channels

The agent runs 5 search channels per session:

| Channel | What it does |
|---------|-------------|
| `user_search` | GitHub user search by keyword + location |
| `code_search` | Searches code for frontier toolchain imports (trl, axolotl, vllm, etc.) |
| `topic_search` | Searches repos by topic tags (rlhf, llm-training, etc.) |
| `stargazer_mining` | Mines stargazers of discriminating repos (OpenRLHF, SWE-bench, etc.) |
| `graph_expansion` | Follows followers/following of saved candidates |

Strategy is generated by Opus at session start and adapts after each batch.

---

## Pipeline Flow

```
Search → Discover candidate → Enrich (repos, READMEs, contributions)
       → Portfolio extraction (GPT-4o-mini)
       → Facial triage (Opus) → PASS/REJECT
       → Full evaluation (Opus) → SAVE/REJECT/INFERENTIAL_SAVE
       → Outreach generation (Opus) → CSV export
```

---

## Briefs

Available briefs:
```bash
ls config/brief-*.json
```

The brief controls everything — who to look for, what signals matter, how to evaluate. The agent won't run without one.

---

## Troubleshooting

**"Daily session cap reached"**
You've run 3 sessions today. Wait until midnight or reset:
```bash
rm ~/.sourcing-governor/github/daily_stats.json
```

**"GITHUB_TOKEN not set"**
Add to `.env`:
```
GITHUB_TOKEN=ghp_your_token_here
```

**Agent seems stuck / not progressing**
Check the rate limit:
```bash
curl -s -H "Authorization: token $(grep GITHUB_TOKEN .env | cut -d= -f2)" https://api.github.com/rate_limit | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['rate'], indent=2))"
```

If `remaining` is 0, you've hit the hourly limit. The agent should auto-wait, but you can also just wait ~60 minutes.

**Want to start fresh (discard all progress):**
```bash
rm -rf output/state/github/<brief-id> output/runs/github/<brief-id> output/exports/github/<brief-id>
python3 run_github.py --brief config/brief-fdl-colombia-v3.json
```

**Want to keep data but re-evaluate:**
Don't delete `candidates.jsonl` — just delete `final_judgments.jsonl` and `outreach.jsonl`, then resume. The agent will re-evaluate existing candidates.
