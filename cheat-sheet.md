# Sourcing Agent — Command Cheat Sheet

**Pre-requisite** — Chrome must be running with CDP:
```bash
./launch-chrome.sh
```

## Start

**Autonomous mode — agent generates its own searches from the brief:**
```bash
python3 session_orchestrator.py --brief config/brief-fdl-colombia-v3.json
```

**With pre-built search strings:**
```bash
python3 session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --search-config config/search-strings-and-filters.json
```

**Single session (one sprint, then stop):**
```bash
python3 session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --single-session
```

**Custom output directory:**
```bash
python3 session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --output-dir output/colombia-run-2
```

**Shortcut script (uses default brief):**
```bash
./run-search.sh                    # full day cycle
./run-search.sh --single-session   # single session
./run-search.sh --status           # check budget
```

## Resume

**Resume from last checkpoint:**
```bash
python3 session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --resume
```

**Restart a specific search string from page 1:**
```bash
python3 session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --restart-string 5
```

## Stop

| Action | How |
|--------|-----|
| **Graceful stop** — finishes current candidate, saves progress | `Ctrl+C` (once) |
| **Graceful stop from another terminal** | `kill $(pgrep -f session_orchestrator)` |
| **Force kill** — immediate exit (for stuck API calls) | `Ctrl+C` (twice) |
| **Force kill from another terminal** | `kill -9 $(pgrep -f session_orchestrator)` |
| **Auto-stop** — hits governor limit or 1 AM cutoff | Automatic |

`kill` (SIGTERM) triggers the same graceful shutdown as Ctrl+C — finishes the current candidate and saves progress before exiting.

## Check Status

**Budget (profile opens remaining, sessions today):**
```bash
python3 session_orchestrator.py --status
```

**Decoy only (passive browsing, no sourcing — for cool-down days):**
```bash
python3 session_orchestrator.py --decoy-only
```

## Standalone Pipeline (no orchestrator)

`run.py` runs the sourcing pipeline directly — no session governor, no decoy agent, no multi-session cycling.

```bash
python3 run.py --brief config/brief-fdl-colombia-v3.json --full-run              # autonomous run
python3 run.py --brief config/brief-fdl-colombia-v3.json --full-run --resume     # resume autonomous run
python3 run.py --brief config/brief-fdl-colombia-v3.json --test-single-page      # process current browser page only
python3 run.py --brief config/brief-fdl-colombia-v3.json --rejudge-from output/snippets.jsonl  # re-evaluate existing snippets (no browser)
```

## Output Files

All output goes to `output/` (or `--output-dir`):

| File | Contents |
|------|----------|
| `progress.json` | Resume checkpoint — current string index, page, completed strings |
| `execution_plan.json` | The strategy Opus generated — all compound Boolean strings with rationales |
| `snippets.jsonl` | Extracted candidate snippets from results pages |
| `facial_judgments.jsonl` | Facial triage decisions (FACIAL_YES / FACIAL_NO) with rationales |
| `final_judgments.jsonl` | Full evaluation decisions (SAVE / REJECT / INFERENTIAL_SAVE / TRANSFERABLE_SAVE) |
| `profile_summaries.jsonl` | Extracted full profile data for candidates that passed facial triage |
| `bias_monitor.json` | Bias control state — alerts fired, decision distributions |
| `run_log.jsonl` | Event log (searches executed, pages processed, errors) |

Governor state lives at `~/.sourcing-governor/`:

| File | Contents |
|------|----------|
| `daily_stats.json` | Rolling 24h profile open timestamps |
| `sessions.jsonl` | Per-session summaries (duration, opens, shutdown reason) |
| `decoy.jsonl` | Decoy activity log |

## Governor Limits

| Limit | Value |
|-------|-------|
| Max session duration | 5 hours |
| Max profile opens / session | 200 |
| Max profile opens / 24h | 400 |
| Max sessions / day | 3 |
| Operating window | ~6:30–7:30 AM to 1:00 AM |
