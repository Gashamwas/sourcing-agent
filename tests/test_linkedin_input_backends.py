"""Tests for LinkedIn input backend selection and wiring."""

import asyncio
import random
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

from shared import config
from linkedin.input_backends import (
    AwayInputBackend,
    ConcurrentInputBackend,
    TypingPlan,
    TypingStep,
    build_boolean_typing_plan,
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


def test_build_boolean_typing_plan_short_strings_have_no_typos():
    plan = build_boolean_typing_plan("foo AND bar", rng=random.Random(7))
    assert plan.typo_count == 0
    assert all(step.kind != "backspace" for step in plan.steps)


def test_build_boolean_typing_plan_skips_boolean_operators_and_slows_after_correction():
    text = "ALPHABRAVO AND CHARLIEDELTA"
    operator_start = text.index("AND")
    operator_range = range(operator_start, operator_start + 3)

    with patch.object(config, "LINKEDIN_SEARCH_TYPING_MEDIUM_TYPO_PROBABILITY", 1.0), patch.object(
        config,
        "LINKEDIN_SEARCH_TYPING_LONG_TYPO_PROBABILITY",
        1.0,
    ), patch.object(
        config,
        "LINKEDIN_SEARCH_TYPING_SECOND_TYPO_PROBABILITY",
        0.0,
    ), patch.object(config, "LINKEDIN_SEARCH_TYPING_CHAR_MIN_SECONDS", 0.06), patch.object(
        config,
        "LINKEDIN_SEARCH_TYPING_CHAR_MAX_SECONDS",
        0.06,
    ):
        plan = build_boolean_typing_plan(text, rng=random.Random(3))

    assert plan.typo_count == 1
    assert all(idx not in operator_range for idx in plan.typo_positions)
    backspace_index = next(i for i, step in enumerate(plan.steps) if step.kind == "backspace")
    following_chars = [
        step for step in plan.steps[backspace_index + 1 :]
        if step.kind == "char" and not step.is_correction
    ][:4]
    assert len(following_chars) == 4
    assert all(step.delay_seconds > 0.06 for step in following_chars)


def test_concurrent_input_backend_types_character_by_character():
    backend = ConcurrentInputBackend()
    page = MagicMock()
    page.keyboard.type = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.insert_text = AsyncMock()
    locator = MagicMock()
    plan = TypingPlan(
        steps=[
            TypingStep(kind="char", value="A", delay_seconds=0.0, source_index=0),
            TypingStep(kind="backspace", delay_seconds=0.0, source_index=0),
            TypingStep(kind="pause", delay_seconds=0.0, source_index=0),
            TypingStep(kind="char", value="b", delay_seconds=0.0, source_index=1),
        ],
        typo_positions=(0,),
    )

    result = asyncio.run(backend.type_text(page, locator, "Ab", plan=plan))

    assert result.transport == "playwright_keyboard"
    assert result.typo_count == 1
    page.keyboard.type.assert_has_awaits([call("A", delay=0), call("b", delay=0)])
    page.keyboard.press.assert_awaited_once_with("Backspace")
    page.keyboard.insert_text.assert_not_awaited()


def test_away_input_backend_supports_combo_and_boolean_ascii_chars():
    fake_bridge = MagicMock()
    with patch("linkedin.input_backends._CoreGraphicsBridge", return_value=fake_bridge), patch(
        "linkedin.input_backends.asyncio.sleep",
        new=AsyncMock(),
    ):
        backend = AwayInputBackend()
        page = MagicMock()
        page.keyboard.insert_text = AsyncMock()
        plan = TypingPlan(
            steps=[
                TypingStep(kind="char", value="(", delay_seconds=0.0, source_index=0),
                TypingStep(kind="char", value="&", delay_seconds=0.0, source_index=1),
                TypingStep(kind="backspace", delay_seconds=0.0, source_index=1),
            ],
            typo_positions=(1,),
        )
        combo_handled = asyncio.run(backend.press_combo(page, "Meta+A"))
        result = asyncio.run(backend.type_text(page, MagicMock(), "(&", plan=plan))

    assert combo_handled is True
    assert result.transport == "coregraphics_keyboard"
    assert result.fallback_char_count == 0
    assert fake_bridge.post_key.call_count > 0
    page.keyboard.insert_text.assert_not_awaited()


def test_away_input_backend_records_single_char_fallback():
    fake_bridge = MagicMock()
    with patch("linkedin.input_backends._CoreGraphicsBridge", return_value=fake_bridge), patch(
        "linkedin.input_backends.asyncio.sleep",
        new=AsyncMock(),
    ):
        backend = AwayInputBackend()
        page = MagicMock()
        page.keyboard.insert_text = AsyncMock()
        plan = TypingPlan(
            steps=[TypingStep(kind="char", value="é", delay_seconds=0.0, source_index=0)]
        )
        result = asyncio.run(backend.type_text(page, MagicMock(), "é", plan=plan))

    assert result.fallback_char_count == 1
    page.keyboard.insert_text.assert_awaited_once_with("é")


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
