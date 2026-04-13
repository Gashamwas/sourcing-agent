"""Tests for LinkedIn session orchestrator resume bookkeeping."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from linkedin.session_orchestrator import (
    _classify_session_exception,
    _parse_restart_strings_arg,
    _resume_has_pending_work,
)
from shared.governor import SessionGovernor
from shared.output_paths import resolve_linkedin_state_dir


def _write_minimal_brief(path: Path, *, project_id: str) -> None:
    path.write_text(
        json.dumps(
            {
                "role_title": "Test Role",
                "linkedin_project": "Test Project",
                "linkedin_project_id": project_id,
                "search_priorities": ["One good lane"],
                "capability_areas": [
                    {
                        "name": "Technical leadership",
                        "description": "Builder requirement",
                        "builder_signals": ["Built it"],
                        "user_signals": ["Did not build it"],
                        "key_terms": ["builder"],
                    }
                ],
                "location": "New York City",
            }
        )
    )


def test_resume_has_pending_work_when_progress_missing():
    with tempfile.TemporaryDirectory() as td:
        brief_path = Path(td) / "brief.json"
        project_id = f"missing-{Path(td).name}"
        _write_minimal_brief(brief_path, project_id=project_id)
        assert _resume_has_pending_work(str(brief_path)) is True


def test_resume_has_pending_work_false_when_queue_exhausted_in_derived_state_dir():
    with tempfile.TemporaryDirectory() as td:
        brief_path = Path(td) / "brief.json"
        project_id = f"exhausted-{Path(td).name}"
        _write_minimal_brief(brief_path, project_id=project_id)
        progress_path = resolve_linkedin_state_dir(brief_path=brief_path) / "progress.json"
        progress_path.write_text(json.dumps({
            "strings": [
                {"id": 1, "status": "done"},
                {"id": 2, "status": "skipped"},
            ]
        }))

        assert _resume_has_pending_work(str(brief_path)) is False


def test_resume_has_pending_work_false_when_queue_exhausted_with_explicit_output_dir():
    with tempfile.TemporaryDirectory() as td:
        brief_path = Path(td) / "brief.json"
        project_id = f"explicit-{Path(td).name}"
        _write_minimal_brief(brief_path, project_id=project_id)
        output_dir = Path(td) / "custom-state"
        progress_path = resolve_linkedin_state_dir(
            brief_path=brief_path,
            state_dir=output_dir,
        ) / "progress.json"
        progress_path.write_text(json.dumps({
            "strings": [
                {"id": 1, "status": "done"},
                {"id": 2, "status": "skipped"},
            ]
        }))

        assert _resume_has_pending_work(str(brief_path), str(output_dir)) is False


def test_resume_has_pending_work_true_when_any_string_is_queued_in_derived_state_dir():
    with tempfile.TemporaryDirectory() as td:
        brief_path = Path(td) / "brief.json"
        project_id = f"queued-{Path(td).name}"
        _write_minimal_brief(brief_path, project_id=project_id)
        progress_path = resolve_linkedin_state_dir(brief_path=brief_path) / "progress.json"
        progress_path.write_text(json.dumps({
            "strings": [
                {"id": 1, "status": "done"},
                {"id": 2, "status": "queued"},
            ]
        }))

        assert _resume_has_pending_work(str(brief_path)) is True


def test_resume_has_pending_work_true_when_any_string_is_in_progress_in_derived_state_dir():
    with tempfile.TemporaryDirectory() as td:
        brief_path = Path(td) / "brief.json"
        project_id = f"in-progress-{Path(td).name}"
        _write_minimal_brief(brief_path, project_id=project_id)
        progress_path = resolve_linkedin_state_dir(brief_path=brief_path) / "progress.json"
        progress_path.write_text(json.dumps({
            "strings": [
                {"id": 1, "status": "done"},
                {"id": 2, "status": "in_progress"},
            ]
        }))

        assert _resume_has_pending_work(str(brief_path)) is True


def test_resume_has_pending_work_true_when_block_adaptation_is_pending_in_derived_state_dir():
    with tempfile.TemporaryDirectory() as td:
        brief_path = Path(td) / "brief.json"
        project_id = f"pending-block-{Path(td).name}"
        _write_minimal_brief(brief_path, project_id=project_id)
        progress_path = resolve_linkedin_state_dir(brief_path=brief_path) / "progress.json"
        progress_path.write_text(json.dumps({
            "strings": [
                {"id": 1, "status": "done"},
                {"id": 2, "status": "skipped"},
            ],
            "pending_block_name": "Compound Batch 1",
            "pending_block_string_ids": [1],
        }))

        assert _resume_has_pending_work(str(brief_path)) is True


def test_governor_can_start_session_when_under_caps():
    governor = SessionGovernor()
    with patch("shared.governor.cooldown.get_sessions_today", return_value=0), \
         patch("shared.governor.cooldown.get_profile_opens_24h", return_value=0):
        ok, reason = governor.can_start_session(session_type="linkedin_sourcing")
        assert ok is True
        assert reason == "ok"


def test_classify_session_exception_distinguishes_interrupts_from_errors():
    assert _classify_session_exception(KeyboardInterrupt()) == "interrupted: KeyboardInterrupt"
    assert _classify_session_exception(NameError("boom")) == "error: NameError"


def test_parse_restart_strings_arg_parses_csv():
    assert _parse_restart_strings_arg("4, 11,12,16,27") == [4, 11, 12, 16, 27]


def test_parse_restart_strings_arg_ignores_empty_chunks():
    assert _parse_restart_strings_arg("4,, 11, ,27") == [4, 11, 27]
