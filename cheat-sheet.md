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
| **Force kill** — immediate exit (for stuck API calls) | `Ctrl+C` (twice) |
| **Auto-stop** — hits governor limit or 1 AM cutoff | Automatic |

## Other

**Decoy only (passive browsing, no sourcing):**
```bash
python3 session_orchestrator.py --decoy-only
```

**Check budget (profile opens remaining, sessions today):**
```bash
python3 session_orchestrator.py --status
```

## Governor Limits

| Limit | Value |
|-------|-------|
| Max session duration | 3 hours |
| Max profile opens / session | 200 |
| Max profile opens / 24h | 400 |
| Max sessions / day | 3 |
| Operating window | ~6:30–7:30 AM to 1:00 AM |
