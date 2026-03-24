"""Tests for judger prompt generation and brief loading.

Run with: python -m pytest test_extractors.py -v
"""

import json
import importlib
from pathlib import Path

from shared.schemas import CandidateSnippet
from shared.judger import _build_facial_system, _build_full_system
from shared.brief_loader import load_brief, Brief


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

BRAZIL_BRIEF_PATH = str(Path(__file__).parent.parent / "config" / "brief-brazil-real.json")
HEAD_AI_BRIEF_PATH = str(Path(__file__).parent.parent / "config" / "brief-head-ai-lab-real.json")

BRAZIL_BRIEF = load_brief(BRAZIL_BRIEF_PATH)
HEAD_AI_BRIEF = load_brief(HEAD_AI_BRIEF_PATH)


def _make_snippet(**kwargs) -> CandidateSnippet:
    defaults = {
        "name": "Test Person",
        "headline": "",
        "current_title": "",
        "current_company": "",
        "location": "Sao Paulo, Brazil",
        "education_snippet": "",
        "profile_url": "/talent/profile/test",
        "source_string_id": 1,
        "source_string_name": "test",
        "page": 1,
        "result_rank": 1,
    }
    defaults.update(kwargs)
    return CandidateSnippet(**defaults)


# ---------------------------------------------------------------------------
# Task 1: Confirm hard_filters is gone
# ---------------------------------------------------------------------------

def test_orchestrator_does_not_import_hard_filters():
    """Verify orchestrator.py has no reference to hard_filters."""
    source = (Path(__file__).parent.parent / "linkedin" / "orchestrator.py").read_text()
    assert "hard_filters" not in source
    assert "hard_filter" not in source


def test_hard_filters_module_deleted():
    """Verify hard_filters.py no longer exists."""
    assert not (Path(__file__).parent.parent / "hard_filters.py").exists()


# ---------------------------------------------------------------------------
# Judger prompt generation from brief
# ---------------------------------------------------------------------------

def test_facial_prompt_includes_brazil_brief_content():
    prompt = _build_facial_system(BRAZIL_BRIEF)
    assert "fdl-brazil" in prompt.lower() or "frontier data lead" in prompt.lower()
    assert "Post-Training Data Engineer" in prompt
    assert "Coding Agent Evaluator" in prompt
    assert "Annotation Worker" in prompt
    assert "minimum_bar" in prompt.lower() or "BUILDING model training" in prompt


def test_full_prompt_includes_brazil_brief_content():
    prompt = _build_full_system(BRAZIL_BRIEF)
    assert "Post-Training Data Engineer" in prompt
    assert "save_signals" in prompt.lower() or "Save signals" in prompt
    assert "caution signals" in prompt.lower() or "Caution signals" in prompt
    assert "Fintech ML Engineer" in prompt
    assert "experience_floor" in prompt.lower() or "Experience Floor" in prompt


def test_facial_prompt_includes_head_ai_brief():
    """Proves the system is brief-agnostic — different brief, different prompt."""
    prompt = _build_facial_system(HEAD_AI_BRIEF)
    assert "head" in prompt.lower() or "applied ai" in prompt.lower()
    # This brief has different structure — should still build without error


def test_full_prompt_includes_head_ai_brief():
    prompt = _build_full_system(HEAD_AI_BRIEF)
    # Head AI brief has clear_skips_from_review as dicts with "pattern" and "reason"
    assert "Solutions Architect" in prompt or "solutions architect" in prompt.lower()


def test_prompts_not_hardcoded():
    """Ensure prompts don't contain the old hardcoded role description."""
    facial = _build_facial_system(BRAZIL_BRIEF)
    full = _build_full_system(BRAZIL_BRIEF)
    # These phrases were in the old hardcoded prompts
    assert "partner with researchers at OpenAI, Anthropic, and DeepMind" not in full
    assert "MSc/PhD from strong research institution" not in full


# ---------------------------------------------------------------------------
# Brief loader tests (Task 3)
# ---------------------------------------------------------------------------

def test_brazil_brief_loads():
    brief = load_brief(BRAZIL_BRIEF_PATH)
    assert isinstance(brief, Brief)
    assert brief.id == "fdl-brazil"
    assert "Frontier Data Lead" in brief.role_description
    assert brief.kit_url.startswith("https://search-kit-library.vercel.app/kit/")
    assert len(brief.archetypes) >= 5
    assert brief.archetypes[0]["name"] == "Post-Training Data Engineer"
    assert brief.permanent_filters.get("Location") == "Brazil"


def test_head_ai_brief_loads():
    brief = load_brief(HEAD_AI_BRIEF_PATH)
    assert isinstance(brief, Brief)
    assert brief.id == "head-applied-ai-lab-nyc"
    assert "mini-cto" in brief.role_description.lower() or "applied ai" in brief.role_description.lower()
    assert brief.kit_url.startswith("https://search-kit-library.vercel.app/kit/")
    assert brief.linkedin_project == "Head of Applied AI Lab"
    assert brief.linkedin_project_id == "1957683706"


def test_both_briefs_have_kit_url():
    brazil = load_brief(BRAZIL_BRIEF_PATH)
    head_ai = load_brief(HEAD_AI_BRIEF_PATH)
    assert brazil.kit_url.startswith("https://")
    assert head_ai.kit_url.startswith("https://")
    assert "search-kit-library" in brazil.kit_url
    assert "search-kit-library" in head_ai.kit_url


def test_both_briefs_archetypes_normalized():
    brazil = load_brief(BRAZIL_BRIEF_PATH)
    head_ai = load_brief(HEAD_AI_BRIEF_PATH)

    for brief in [brazil, head_ai]:
        assert isinstance(brief.archetypes, list)
        assert len(brief.archetypes) > 0
        for arch in brief.archetypes:
            assert "name" in arch
            assert "pattern" in arch


def test_clear_skips_flattened():
    """Head of AI Lab brief has dicts; Brazil has strings. Both should flatten."""
    brazil = load_brief(BRAZIL_BRIEF_PATH)
    head_ai = load_brief(HEAD_AI_BRIEF_PATH)

    for brief in [brazil, head_ai]:
        assert isinstance(brief.clear_skips_from_review, list)
        for item in brief.clear_skips_from_review:
            assert isinstance(item, str)


def test_minimum_bar_is_string():
    """minimum_bar should always be a string (Head AI Lab has it as dict)."""
    brazil = load_brief(BRAZIL_BRIEF_PATH)
    head_ai = load_brief(HEAD_AI_BRIEF_PATH)
    assert isinstance(brazil.minimum_bar, str)
    assert isinstance(head_ai.minimum_bar, str)
    assert len(brazil.minimum_bar) > 50
    assert len(head_ai.minimum_bar) > 50


def test_raw_dict_preserved():
    brazil = load_brief(BRAZIL_BRIEF_PATH)
    assert brazil.raw.get("name") == "fdl-brazil"
    head_ai = load_brief(HEAD_AI_BRIEF_PATH)
    assert head_ai.raw.get("brief_id") == "head-applied-ai-lab-nyc"


def test_pipeline_import_works():
    """Verify orchestrator module imports cleanly."""
    from linkedin.orchestrator import Pipeline
    assert Pipeline is not None
