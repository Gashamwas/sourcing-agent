"""Tests for LinkedIn input backend selection and wiring."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from linkedin.input_backends import (
    AwayInputBackend,
    ConcurrentInputBackend,
    create_input_backend,
    normalize_input_mode,
)


def test_normalize_input_mode_aliases():
    assert normalize_input_mode("concurrent") == "concurrent"
    assert normalize_input_mode("ghost-cursor") == "concurrent"
    assert normalize_input_mode("takeover") == "away"
    assert normalize_input_mode("afk") == "away"


def test_create_input_backend_concurrent():
    backend = create_input_backend("concurrent")
    assert isinstance(backend, ConcurrentInputBackend)


def test_create_input_backend_away():
    with patch("linkedin.input_backends._CoreGraphicsBridge", return_value=MagicMock()):
        backend = create_input_backend("away")
    assert isinstance(backend, AwayInputBackend)


def test_away_input_backend_press_key_returns_false_for_unknown_key():
    fake_bridge = MagicMock()
    with patch("linkedin.input_backends._CoreGraphicsBridge", return_value=fake_bridge):
        backend = AwayInputBackend()

    page = MagicMock()
    handled = asyncio.run(backend.press_key(page, "ArrowDown"))
    assert handled is False
    fake_bridge.post_key.assert_not_called()


def test_pipeline_passes_input_mode_to_browser():
    with tempfile.TemporaryDirectory() as td, \
         patch("linkedin.orchestrator.load_brief") as mock_brief, \
         patch("linkedin.orchestrator.init_judger"), \
         patch("linkedin.orchestrator.LinkedInBrowser") as mock_browser:
        brief = MagicMock()
        brief.id = "test"
        brief.linkedin_project_id = "test-project"
        brief.has_v2_schema = False
        brief.employer_blacklist = []
        mock_brief.return_value = brief

        brief_path = Path(td) / "brief.json"
        brief_path.write_text('{"id": "test"}')

        from linkedin.orchestrator import Pipeline

        Pipeline(brief_path=str(brief_path), output_dir=td, input_mode="away")

        mock_browser.assert_called_once_with(input_mode="away")
