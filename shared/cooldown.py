"""Persistent rolling-window tracker for profile opens.

Stores timestamped entries in ~/.sourcing-governor/daily_stats.json.
On every read, prunes entries older than the window (default 24h).
Thread-safe via file-level atomic writes.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

GOVERNOR_DIR = Path.home() / ".sourcing-governor"
DAILY_STATS_FILE = GOVERNOR_DIR / "daily_stats.json"
SESSIONS_LOG = GOVERNOR_DIR / "sessions.jsonl"

WINDOW_SECONDS = 24 * 3600  # 24 hours


def _ensure_dir():
    GOVERNOR_DIR.mkdir(parents=True, exist_ok=True)


def _load_raw() -> dict:
    """Load the raw stats file. Returns empty structure if missing/corrupt."""
    _ensure_dir()
    if not DAILY_STATS_FILE.exists():
        return {"profile_opens": [], "sessions_today": []}
    try:
        return json.loads(DAILY_STATS_FILE.read_text())
    except (json.JSONDecodeError, KeyError):
        return {"profile_opens": [], "sessions_today": []}


def _save_raw(data: dict):
    """Atomic write to stats file."""
    _ensure_dir()
    tmp = DAILY_STATS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(DAILY_STATS_FILE)


def _prune(data: dict, now: Optional[float] = None) -> dict:
    """Remove entries older than the rolling window."""
    now = now or time.time()
    cutoff = now - WINDOW_SECONDS
    data["profile_opens"] = [
        ts for ts in data["profile_opens"] if ts > cutoff
    ]
    # Sessions: prune to calendar day
    today = time.strftime("%Y-%m-%d")
    data["sessions_today"] = [
        s for s in data.get("sessions_today", [])
        if s.get("date") == today
    ]
    return data


def _pid_is_alive(pid: int | None) -> bool:
    """Best-effort liveness check for a local process id."""
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _reason_counts_toward_cap(reason: str) -> bool:
    """Return True when a finished session should consume a daily slot."""
    normalized = (reason or "").strip().lower()
    if not normalized or normalized == "unknown":
        return False
    if normalized.startswith("interrupted:"):
        return False
    if normalized.startswith("error:"):
        return False
    return True


def _entry_counts_toward_cap(entry: dict) -> bool:
    """Backfill cap-counting behavior for old and new session entries."""
    if "counts_toward_cap" in entry:
        return bool(entry.get("counts_toward_cap"))
    return entry.get("profile_opens", 0) > 0 and _reason_counts_toward_cap(entry.get("reason", ""))


def _reconcile_stale_sessions(data: dict, now: Optional[float] = None) -> bool:
    """Close orphaned in-progress sessions so they stop consuming slots forever."""
    now = now or time.time()
    changed = False
    for entry in data.get("sessions_today", []):
        if "end_ts" in entry:
            inferred = _entry_counts_toward_cap(entry)
            if entry.get("counts_toward_cap") != inferred:
                entry["counts_toward_cap"] = inferred
                changed = True
            continue

        pid = entry.get("pid")
        if pid is not None and _pid_is_alive(pid):
            continue

        entry["end_ts"] = now
        entry.setdefault("profile_opens", 0)
        entry["reason"] = entry.get("reason") or "interrupted: stale_session"
        entry["counts_toward_cap"] = False
        changed = True

    return changed


def _load_current_data(now: Optional[float] = None) -> dict:
    """Load, prune, reconcile, and persist the live governor snapshot."""
    data = _prune(_load_raw(), now=now)
    changed = _reconcile_stale_sessions(data, now=now)
    if changed:
        _save_raw(data)
    return data


def get_profile_opens_24h() -> int:
    """Count profile opens in the rolling 24h window."""
    data = _prune(_load_raw())
    _save_raw(data)
    return len(data["profile_opens"])


def record_profile_open():
    """Record a single profile open with current timestamp."""
    data = _prune(_load_raw())
    data["profile_opens"].append(time.time())
    _save_raw(data)


def get_sessions_today(session_type: Optional[str] = None) -> int:
    """Count sessions that currently occupy a daily sourcing slot."""
    data = _load_current_data()
    count = 0
    for entry in data["sessions_today"]:
        if session_type and entry.get("session_type") != session_type:
            continue
        if "end_ts" not in entry:
            count += 1
            continue
        if _entry_counts_toward_cap(entry):
            count += 1
    return count


def record_session_start(session_type: str = "linkedin_sourcing") -> int:
    """Record a new session start. Returns session number for today."""
    data = _load_current_data()
    today = time.strftime("%Y-%m-%d")
    session_num = max((entry.get("session_num", 0) for entry in data["sessions_today"]), default=0) + 1
    data["sessions_today"].append({
        "date": today,
        "session_num": session_num,
        "session_type": session_type,
        "start_ts": time.time(),
        "pid": os.getpid(),
    })
    _save_raw(data)
    return session_num


def record_session_end(
    session_num: int,
    profile_opens: int,
    reason: str,
    stats: dict,
    counts_toward_cap: Optional[bool] = None,
):
    """Update the session entry in daily_stats and append to sessions log."""
    # Update the daily_stats entry with completion info
    data = _load_current_data()
    today = time.strftime("%Y-%m-%d")
    session_entry = None
    if counts_toward_cap is None:
        counts_toward_cap = profile_opens > 0 and _reason_counts_toward_cap(reason)
    for entry in data["sessions_today"]:
        if entry["session_num"] == session_num and entry.get("date") == today:
            entry["end_ts"] = time.time()
            entry["profile_opens"] = profile_opens
            entry["reason"] = reason
            entry["counts_toward_cap"] = counts_toward_cap
            session_entry = entry
            break
    _save_raw(data)

    # Also append to sessions log for historical record
    _ensure_dir()
    log_entry = {
        "session_type": session_entry.get("session_type", "unknown") if session_entry else "unknown",
        "start_time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(session_entry["start_ts"])) if session_entry and "start_ts" in session_entry else None,
        "end_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "shutdown_reason": reason,
        "counts_toward_cap": counts_toward_cap,
        "profile_opens_count": profile_opens,
        "saves_count": stats.get("saved", 0) if stats else 0,
    }
    with open(SESSIONS_LOG, "a") as f:
        f.write(json.dumps(log_entry) + "\n")


def print_status():
    """Print current 24h stats for --status flag."""
    from shared.governor import MAX_SESSIONS_PER_DAY

    opens_24h = get_profile_opens_24h()
    sessions = get_sessions_today()

    print(f"Profile opens (rolling 24h): {opens_24h}/400")
    print(f"Sessions today: {sessions}/{MAX_SESSIONS_PER_DAY}")
    print("Time-of-day window: DISABLED (24h operation)")
    print(f"Current time: {time.strftime('%I:%M %p')}")

    if opens_24h >= 400:
        print("\n⚠ 24h profile open cap reached. No sourcing sessions available.")
    elif sessions >= MAX_SESSIONS_PER_DAY:
        print("\n⚠ Daily session cap reached. No more sourcing sessions today.")
    else:
        remaining = 400 - opens_24h
        print(f"\n✓ Ready to source. {remaining} profile opens remaining in 24h budget.")
