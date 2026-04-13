# Sourcing Agent — Command Cheat Sheet

**Pre-requisite** — Chrome must be running with CDP:
```bash
./launch-chrome.sh
```

## Start

**Autonomous mode — agent generates its own searches from the brief:**
```bash
python3 linkedin/session_orchestrator.py --brief config/brief-fdl-colombia-v3.json
```

**With pre-built search strings:**
```bash
python3 linkedin/session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --search-config config/search-strings-and-filters.json
```

**Single session (one sprint, then stop):**
```bash
python3 linkedin/session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --single-session
```

**Custom mutable state directory:**
```bash
python3 linkedin/session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --state-dir output/state/linkedin/fdl_colombia
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
python3 linkedin/session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --resume
```

**Restart a specific search string from page 1:**
```bash
python3 linkedin/session_orchestrator.py --brief config/brief-fdl-colombia-v3.json --restart-string 5 --resume
```

## Stop

| Action | How |
|--------|-----|
| **Graceful stop** — finishes current candidate, saves progress | `Ctrl+C` (once) |
| **Graceful stop from another terminal** | `kill $(pgrep -f 'linkedin/session_orchestrator.py')` |
| **Force kill** — immediate exit (for stuck API calls) | `Ctrl+C` (twice) |
| **Force kill from another terminal** | `kill -9 $(pgrep -f 'linkedin/session_orchestrator.py')` |
| **Auto-stop** — hits governor limit or 1 AM cutoff | Automatic |

`kill` (SIGTERM) triggers the same graceful shutdown as Ctrl+C — finishes the current candidate and saves progress before exiting.

## Check Status

**Budget (profile opens remaining, sessions today):**
```bash
python3 linkedin/session_orchestrator.py --status
```

**Decoy only (passive browsing, no sourcing — for cool-down days):**
```bash
python3 linkedin/session_orchestrator.py --decoy-only
```

## Standalone Pipeline (no orchestrator)

`run_linkedin.py` runs the sourcing pipeline directly — no session governor, no decoy agent, no multi-session cycling.

```bash
python3 run_linkedin.py --brief config/brief-fdl-colombia-v3.json --full-run              # autonomous run
python3 run_linkedin.py --brief config/brief-fdl-colombia-v3.json --full-run --resume     # resume autonomous run
python3 run_linkedin.py --brief config/brief-fdl-colombia-v3.json --test-single-page      # process current browser page only
python3 run_linkedin.py --brief config/brief-fdl-colombia-v3.json --rejudge-from output/state/linkedin/<brief-id>/snippets.jsonl  # re-evaluate existing snippets (no browser)
```

## Output Contract

Live runs write into a mutable `state_dir` under `output/state/linkedin/<brief-id>/`.
Completed runs are snapshotted into immutable `run_dir` directories under
`output/runs/linkedin/<brief-id>/<run-stamp>__run-<id>/`.
Market intel should only ever point at a finalized `run_dir`.

Common live-state files:

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

Market-intel inputs are frozen per completed run inside `run_dir`, including:

| File | Contents |
|------|----------|
| `run-report-input.json` | Structured debrief input packet |
| `run-report.json` | Final LinkedIn run report |
| `run-report.md` | Human-readable report |
| `market-intel-research-input.json` | Bounded structured packet fed to market-intel research |
| `run-manifest.json` | Snapshot metadata, provenance, and artifact inventory |

Update market intel from a finalized run snapshot:

```bash
python3 tools/update_market_intel.py \
  --brief config/brief-fdl-colombia-v3.json \
  --run-dir output/runs/linkedin/<brief-id>/<run-stamp>__run-<id> \
  --mode post_run
```

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
