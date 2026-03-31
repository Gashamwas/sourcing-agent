"""Tests for LinkedIn session orchestrator resume bookkeeping."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from linkedin.session_orchestrator import (
    _resume_has_pending_work,
)
from shared.governor import SessionGovernor


def test_resume_has_pending_work_when_progress_missing():
    with tempfile.TemporaryDirectory() as td:
        assert _resume_has_pending_work(td) is True


def test_resume_has_pending_work_false_when_queue_exhausted():
    with tempfile.TemporaryDirectory() as td:
        progress_path = Path(td) / "progress.json"
        progress_path.write_text(json.dumps({
            "strings": [
                {"id": 1, "status": "done"},
                {"id": 2, "status": "skipped"},
            ]
        }))

        assert _resume_has_pending_work(td) is False


def test_resume_has_pending_work_true_when_any_string_is_queued():
    with tempfile.TemporaryDirectory() as td:
        progress_path = Path(td) / "progress.json"
        progress_path.write_text(json.dumps({
            "strings": [
                {"id": 1, "status": "done"},
                {"id": 2, "status": "queued"},
            ]
        }))

        assert _resume_has_pending_work(td) is True


def test_resume_has_pending_work_true_when_any_string_is_in_progress():
    with tempfile.TemporaryDirectory() as td:
        progress_path = Path(td) / "progress.json"
        progress_path.write_text(json.dumps({
            "strings": [
                {"id": 1, "status": "done"},
                {"id": 2, "status": "in_progress"},
            ]
        }))

        assert _resume_has_pending_work(td) is True


def test_governor_can_start_session_when_under_caps():
    governor = SessionGovernor()
    with patch("shared.governor.cooldown.get_sessions_today", return_value=0), \
         patch("shared.governor.cooldown.get_profile_opens_24h", return_value=0):
        ok, reason = governor.can_start_session(session_type="linkedin_sourcing")
        assert ok is True
        assert reason == "ok"
