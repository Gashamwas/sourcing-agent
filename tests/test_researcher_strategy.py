"""Researcher module Slice 3 — strategy formation coverage.

`form_strategy(brief, prior_data) -> ExecutionPlan` produces queries
shaped per Researcher Module Spec Opinion 2 (NOT Boolean strings —
OpenAlex API parameters). Tests verify:

- Prompt assembly pulls in capability areas + source_config.researcher.
- LLM output is normalized: missing keys default; non-dict entries
  dropped; venue_filter falls back to conference_allowlist seed.
- The injected ``llm_caller`` is called with both the system + user
  prompts (no real Opus call from tests).
- The query schema matches :data:`RESEARCHER_QUERY_SCHEMA_KEYS`.
"""

from __future__ import annotations

from types import SimpleNamespace

from researcher.strategy import (
    RESEARCHER_QUERY_SCHEMA_KEYS,
    form_strategy,
)


def _capability(name: str, description: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, description=description)


def _stub_brief(
    *,
    role_title: str = "Frontier-lab Researcher",
    role_summary: str = "Original research on RLHF + agent infra.",
    capability_areas: list | None = None,
    source_config_researcher: dict | None = None,
) -> SimpleNamespace:
    """Build a minimal Brief-shape for testing strategy formation."""

    new_brief: dict = {}
    if source_config_researcher is not None:
        new_brief["source_config"] = {"researcher": source_config_researcher}
    return SimpleNamespace(
        role_title=role_title,
        role_summary=role_summary,
        capability_areas=capability_areas
        or [
            _capability(
                "Post-training research",
                "Publishes original work on RLHF / DPO / SFT.",
            ),
            _capability(
                "Agent infrastructure",
                "Designs reasoning + tool-use systems.",
            ),
        ],
        _new_brief=new_brief,
    )


def _stub_llm_response() -> dict:
    return {
        "strategy_rationale": "Cover post-training and inference axes via NeurIPS + ICML.",
        "generated_strings": [
            {
                "id": 1,
                "name": "RLHF · NeurIPS",
                "topic_concepts": ["C2778407487"],
                "venue_filter": ["NeurIPS"],
                "min_year": 2023,
                "min_citations": 20,
                "ror_country_filter": ["US", "GB"],
            },
            {
                "id": 2,
                "name": "Agent infra · ICML",
                "topic_concepts": ["C41008148", "C99498"],
                "venue_filter": ["ICML"],
                "min_year": 2023,
                "min_citations": 10,
                "ror_country_filter": [],
            },
            {
                "topic_concepts": ["C9000"],  # Missing id, name, venue_filter
            },
        ],
        "coverage_gaps": [],
        "architecture": "concept_first",
        "architecture_rationale": "Concept-first because brief names topics, not venues.",
    }


# ---------------------------------------------------------------------------
# Plan construction
# ---------------------------------------------------------------------------


def test_form_strategy_calls_llm_with_system_and_user_prompts() -> None:
    captured: dict = {}

    def llm_caller(system: str, user: str) -> dict:
        captured["system"] = system
        captured["user"] = user
        return _stub_llm_response()

    brief = _stub_brief(
        source_config_researcher={
            "research_topics": ["RLHF", "agent infrastructure"],
            "conference_allowlist": ["NeurIPS", "ICML", "ICLR"],
            "discipline": "nlp",
        }
    )
    plan = form_strategy(brief, llm_caller=llm_caller)

    assert "system" in captured and "user" in captured
    assert "RLHF, agent infrastructure" in captured["system"]
    assert "NeurIPS, ICML, ICLR" in captured["system"]
    assert "nlp" in captured["system"]
    # Capability areas appear by name in the system prompt.
    assert "Post-training research" in captured["system"]
    assert "Agent infrastructure" in captured["system"]
    # Output schema keys appear in the user prompt's contract.
    for key in RESEARCHER_QUERY_SCHEMA_KEYS:
        assert key in captured["user"]
    assert plan.strategy_rationale.startswith("Cover post-training")


def test_form_strategy_normalizes_query_dicts() -> None:
    brief = _stub_brief(
        source_config_researcher={
            "conference_allowlist": ["NeurIPS", "ICML"],
        }
    )
    plan = form_strategy(brief, llm_caller=lambda _s, _u: _stub_llm_response())

    queries = plan.generated_strings
    assert len(queries) == 3

    first = queries[0]
    assert first["id"] == 1
    assert first["name"] == "RLHF · NeurIPS"
    assert first["boolean"] == ""  # Spec Opinion 2: no Boolean for researcher.
    assert first["topic_concepts"] == ["C2778407487"]
    assert first["venue_filter"] == ["NeurIPS"]
    assert first["min_year"] == 2023
    assert first["min_citations"] == 20
    assert first["ror_country_filter"] == ["US", "GB"]

    third = queries[2]
    # Missing id auto-assigned from index.
    assert third["id"] == 3
    # Missing venue_filter falls back to conference_allowlist seed.
    assert third["venue_filter"] == ["NeurIPS", "ICML"]
    # Missing min_year / min_citations default to 0.
    assert third["min_year"] == 0
    assert third["min_citations"] == 0
    # Auto-named when LLM didn't supply.
    assert third["name"]


def test_form_strategy_handles_missing_generated_strings() -> None:
    brief = _stub_brief()
    plan = form_strategy(
        brief,
        llm_caller=lambda _s, _u: {"strategy_rationale": "no plan"},
    )
    assert plan.strategy_rationale == "no plan"
    assert plan.generated_strings == []


def test_form_strategy_drops_non_dict_query_entries() -> None:
    brief = _stub_brief()
    plan = form_strategy(
        brief,
        llm_caller=lambda _s, _u: {
            "generated_strings": [
                {"topic_concepts": ["C1"]},
                "not a dict",
                None,
                {"topic_concepts": ["C2"]},
            ]
        },
    )
    assert len(plan.generated_strings) == 2
    assert plan.generated_strings[0]["topic_concepts"] == ["C1"]
    assert plan.generated_strings[1]["topic_concepts"] == ["C2"]


def test_form_strategy_with_no_source_config_uses_empty_seed() -> None:
    """A brief without source_config.researcher should still produce a
    plan; the venue_filter just won't have a fallback seed.
    """

    brief = _stub_brief(source_config_researcher=None)
    plan = form_strategy(
        brief,
        llm_caller=lambda _s, _u: {
            "generated_strings": [{"topic_concepts": ["C1"]}]
        },
    )
    assert plan.generated_strings[0]["venue_filter"] == []


def test_form_strategy_passes_prior_run_data_into_user_prompt() -> None:
    captured_user: dict = {}

    def llm_caller(system: str, user: str) -> dict:
        captured_user["text"] = user
        return _stub_llm_response()

    brief = _stub_brief()
    form_strategy(
        brief,
        prior_data={
            "queries_explored": 7,
            "high_yield_venues": ["NeurIPS"],
        },
        llm_caller=llm_caller,
    )
    assert "queries explored: 7" in captured_user["text"]
    assert "high-yield venues: ['NeurIPS']" in captured_user["text"]


def test_form_strategy_prior_data_none_emits_fresh_marker() -> None:
    captured_user: dict = {}

    def llm_caller(system: str, user: str) -> dict:
        captured_user["text"] = user
        return _stub_llm_response()

    form_strategy(_stub_brief(), llm_caller=llm_caller)
    assert "fresh strategy" in captured_user["text"]
