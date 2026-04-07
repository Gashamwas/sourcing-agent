import json

import shared.cooldown as cooldown


def _configure_governor_paths(monkeypatch, tmp_path):
    governor_dir = tmp_path / "governor"
    monkeypatch.setattr(cooldown, "GOVERNOR_DIR", governor_dir)
    monkeypatch.setattr(cooldown, "DAILY_STATS_FILE", governor_dir / "daily_stats.json")
    monkeypatch.setattr(cooldown, "SESSIONS_LOG", governor_dir / "sessions.jsonl")
    return governor_dir


def test_get_sessions_today_excludes_interrupted_sessions_from_daily_cap(monkeypatch, tmp_path):
    _configure_governor_paths(monkeypatch, tmp_path)

    today = "2026-04-05"
    cooldown._save_raw({
        "profile_opens": [],
        "sessions_today": [
            {
                "date": today,
                "session_num": 1,
                "session_type": "linkedin_sourcing",
                "start_ts": 1,
                "end_ts": 2,
                "profile_opens": 64,
                "reason": "session_duration (3.7h)",
            },
            {
                "date": today,
                "session_num": 2,
                "session_type": "linkedin_sourcing",
                "start_ts": 3,
                "end_ts": 4,
                "profile_opens": 2,
                "reason": "interrupted: KeyboardInterrupt",
            },
        ],
    })

    monkeypatch.setattr(cooldown.time, "strftime", lambda fmt, *args: today if fmt == "%Y-%m-%d" else "12:00 PM")

    assert cooldown.get_sessions_today(session_type="linkedin_sourcing") == 1


def test_get_sessions_today_closes_stale_pidless_sessions(monkeypatch, tmp_path):
    _configure_governor_paths(monkeypatch, tmp_path)

    today = "2026-04-05"
    cooldown._save_raw({
        "profile_opens": [],
        "sessions_today": [
            {
                "date": today,
                "session_num": 3,
                "session_type": "linkedin_sourcing",
                "start_ts": 10,
            },
        ],
    })

    monkeypatch.setattr(cooldown.time, "strftime", lambda fmt, *args: today if fmt == "%Y-%m-%d" else "12:00 PM")
    monkeypatch.setattr(cooldown.time, "time", lambda: 20)

    assert cooldown.get_sessions_today(session_type="linkedin_sourcing") == 0

    data = json.loads(cooldown.DAILY_STATS_FILE.read_text())
    entry = data["sessions_today"][0]
    assert entry["end_ts"] == 20
    assert entry["reason"] == "interrupted: stale_session"
    assert entry["counts_toward_cap"] is False


def test_record_session_end_marks_keyboard_interrupt_as_not_counting(monkeypatch, tmp_path):
    _configure_governor_paths(monkeypatch, tmp_path)

    today = "2026-04-05"
    monkeypatch.setattr(cooldown.time, "strftime", lambda fmt, *args: today if fmt == "%Y-%m-%d" else "12:00 PM")
    monkeypatch.setattr(cooldown.os, "getpid", lambda: 12345)

    session_num = cooldown.record_session_start()
    cooldown.record_session_end(
        session_num=session_num,
        profile_opens=5,
        reason="interrupted: KeyboardInterrupt",
        stats={"saved": 0},
    )

    data = json.loads(cooldown.DAILY_STATS_FILE.read_text())
    entry = data["sessions_today"][0]
    assert entry["counts_toward_cap"] is False

    log_entry = json.loads(cooldown.SESSIONS_LOG.read_text().splitlines()[-1])
    assert log_entry["counts_toward_cap"] is False
