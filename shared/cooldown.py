"""Persistent rolling-window tracker for profile opens.

Stores timestamped entries in ~/.sourcing-governor/daily_stats.json.
On every read, prunes entries older than the window (default 24h).
Thread-safe via file-level atomic writes.
"""

import json
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
    """Count sourcing sessions today that did actual work or are still running.

    Sessions with profile_opens == 0 and an end_ts (i.e., aborted launches)
    don't count against the daily cap. If session_type is provided, only
    count sessions of that type.
    """
    data = _prune(_load_raw())
    count = 0
    for entry in data["sessions_today"]:
        if session_type and entry.get("session_type") != session_type:
            continue
        has_ended = "end_ts" in entry
        did_work = entry.get("profile_opens", 0) > 0
        still_running = not has_ended
        if did_work or still_running:
            count += 1
    return count


def record_session_start(session_type: str = "linkedin_sourcing") -> int:
    """Record a new session start. Returns session number for today."""
    data = _prune(_load_raw())
    today = time.strftime("%Y-%m-%d")
    session_num = len(data["sessions_today"]) + 1
    data["sessions_today"].append({
        "date": today,
        "session_num": session_num,
        "session_type": session_type,
        "start_ts": time.time(),
    })
    _save_raw(data)
    return session_num


def record_session_end(session_num: int, profile_opens: int, reason: str, stats: dict):
    """Update the session entry in daily_stats and append to sessions log."""
    # Update the daily_stats entry with completion info
    data = _load_raw()
    today = time.strftime("%Y-%m-%d")
    session_entry = None
    for entry in data["sessions_today"]:
        if entry["session_num"] == session_num and entry.get("date") == today:
            entry["end_ts"] = time.time()
            entry["profile_opens"] = profile_opens
            entry["reason"] = reason
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
        "profile_opens_count": profile_opens,
        "saves_count": stats.get("saved", 0) if stats else 0,
    }
    with open(SESSIONS_LOG, "a") as f:
        f.write(json.dumps(log_entry) + "\n")


def print_status():
    """Print current 24h stats for --status flag."""
    opens_24h = get_profile_opens_24h()
    sessions = get_sessions_today()
    now_hour = int(time.strftime("%H"))
    in_window = 7 <= now_hour < 23

    print(f"Profile opens (rolling 24h): {opens_24h}/400")
    print(f"Sessions today: {sessions}/3")
    print(f"Time-of-day window: {'OPEN (7 AM - 11 PM)' if in_window else 'CLOSED'}")
    print(f"Current time: {time.strftime('%I:%M %p')}")

    if opens_24h >= 400:
        print("\n⚠ 24h profile open cap reached. No sourcing sessions available.")
    elif sessions >= 3:
        print("\n⚠ Daily session cap reached. No more sourcing sessions today.")
    elif not in_window:
        print(f"\n⚠ Outside operating window. Next window opens at 7:00 AM.")
    else:
        remaining = 400 - opens_24h
        print(f"\n✓ Ready to source. {remaining} profile opens remaining in 24h budget.")
