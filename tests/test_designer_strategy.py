"""Designer Slice 2 — query formation from V2 brief.

Pins the contract for :func:`designer.strategy.form_designer_strategy`:

- Walks `capability_areas`, emits one Behance query per area as a baseline.
- Appends `behance_specialization_signals` as their own queries.
- Cross-products top spec signals × top tool signals up to the per-
  capability cap.
- Dedups by `(source, query_text.lower())`.
- Threads `discipline` from the dominant rubric calibration exemplar.
- Threads geography → ISO country code into `extra_filters` when the
  brief carries a recognizable geography string.
- Slice-2 returns Behance-only queries; CSE branch is a no-op.

Determinism matters: re-running the strategy on the same brief MUST
yield the same queries in the same order so work-unit IDs stay stable
across resumes.
"""

from __future__ import annotations

from designer.schemas import DesignerSearchQuery
from designer.strategy import (
    BEHANCE_SORT_PRIMARY,
    MAX_QUERIES_PER_CAPABILITY_AREA,
    form_designer_strategy,
)


def _brief_with_one_capability_area() -> dict:
    return {
        "role_title": "Senior product designer",
        "capability_areas": [
            {
                "name": "Design systems",
                "description": "Builds and maintains design systems.",
                "behance_specialization_signals": [
                    "design systems",
                    "component library",
                ],
                "tool_stack_signals": ["Figma", "Storybook"],
            }
        ],
        "depth_distinction": {
            "builder_definition": "Owns the design system end-to-end.",
            "user_definition": "Consumes the system without authoring it.",
            "edge_case_guidance": "Borderline = consuming + extending.",
        },
    }


def _brief_with_calibration_exemplars(
    *exemplar_disciplines: str,
) -> dict:
    brief = _brief_with_one_capability_area()
    brief["design_rubric"] = {
        "calibration_exemplars": [
            {
                "portfolio_url": f"https://example.com/p{idx}",
                "discipline": discipline,
                "verdict": "yes",
                "per_principle_reasoning": {},
                "overall_reasoning": "fixture",
            }
            for idx, discipline in enumerate(exemplar_disciplines)
        ]
    }
    return brief


def test_strategy_emits_baseline_query_for_capability_area_name() -> None:
    queries = form_designer_strategy(_brief_with_one_capability_area())
    # Baseline query is the capability-area name itself.
    baseline = [q for q in queries if q.query_text == "Design systems"]
    assert len(baseline) == 1
    assert baseline[0].source == "behance"
    assert baseline[0].sort == BEHANCE_SORT_PRIMARY
    assert baseline[0].capability_area_name == "Design systems"


def test_strategy_emits_one_query_per_specialization_signal() -> None:
    queries = form_designer_strategy(_brief_with_one_capability_area())
    query_texts = {q.query_text for q in queries}
    assert "design systems" in query_texts  # specialization signal (lowercased input)
    assert "component library" in query_texts


def test_strategy_emits_signal_x_tool_combinations() -> None:
    queries = form_designer_strategy(_brief_with_one_capability_area())
    query_texts = {q.query_text for q in queries}
    assert "design systems Figma" in query_texts
    assert "design systems Storybook" in query_texts
    assert "component library Figma" in query_texts
    assert "component library Storybook" in query_texts


def test_strategy_caps_queries_per_capability_area() -> None:
    """A pathologically broad capability area must not emit more than
    `MAX_QUERIES_PER_CAPABILITY_AREA` queries."""

    brief = {
        "role_title": "Senior designer",
        "capability_areas": [
            {
                "name": "Broad area",
                "description": "Many signals.",
                "behance_specialization_signals": [f"signal_{i}" for i in range(8)],
                "tool_stack_signals": [f"tool_{i}" for i in range(8)],
            }
        ],
        "depth_distinction": {"builder_definition": "x", "user_definition": "y", "edge_case_guidance": "z"},
    }
    queries = form_designer_strategy(brief)
    queries_for_area = [q for q in queries if q.capability_area_name == "Broad area"]
    assert len(queries_for_area) <= MAX_QUERIES_PER_CAPABILITY_AREA


def test_strategy_dedups_duplicate_query_text() -> None:
    """If two capability areas surface the same specialization signal,
    only one query goes out — work-unit dedup at the strategy layer."""

    brief = {
        "role_title": "Designer",
        "capability_areas": [
            {
                "name": "Area A",
                "description": "first",
                "behance_specialization_signals": ["overlap signal"],
            },
            {
                "name": "Area B",
                "description": "second",
                "behance_specialization_signals": ["overlap signal"],
            },
        ],
        "depth_distinction": {"builder_definition": "x", "user_definition": "y", "edge_case_guidance": "z"},
    }
    queries = form_designer_strategy(brief)
    overlap_queries = [q for q in queries if q.query_text == "overlap signal"]
    assert len(overlap_queries) == 1


def test_strategy_threads_dominant_discipline_from_calibration_exemplars() -> None:
    brief = _brief_with_calibration_exemplars("product", "product", "product", "brand")
    queries = form_designer_strategy(brief)
    # Every query carries the dominant discipline (product).
    for query in queries:
        assert query.discipline == "product"


def test_strategy_handles_no_calibration_exemplars() -> None:
    queries = form_designer_strategy(_brief_with_one_capability_area())
    for query in queries:
        assert query.discipline == ""


def test_strategy_threads_geography_iso_code_into_extra_filters() -> None:
    brief = _brief_with_one_capability_area()
    brief["geography"] = "US"
    queries = form_designer_strategy(brief)
    for query in queries:
        assert query.extra_filters.get("country") == "US"


def test_strategy_translates_natural_language_geography() -> None:
    brief = _brief_with_one_capability_area()
    brief["geography"] = "United Kingdom"
    queries = form_designer_strategy(brief)
    for query in queries:
        assert query.extra_filters.get("country") == "GB"


def test_strategy_omits_country_filter_for_unknown_geography() -> None:
    brief = _brief_with_one_capability_area()
    brief["geography"] = "Outer Space"
    queries = form_designer_strategy(brief)
    for query in queries:
        assert "country" not in query.extra_filters


def test_strategy_is_deterministic_across_runs() -> None:
    """Same brief in → same queries (and same order) out. Required for
    work-unit ID stability across resume."""

    brief = _brief_with_one_capability_area()
    first = form_designer_strategy(brief)
    second = form_designer_strategy(brief)
    assert first == second


def test_strategy_returns_empty_for_brief_without_capability_areas() -> None:
    brief = {
        "role_title": "Designer",
        "depth_distinction": {"builder_definition": "x", "user_definition": "y", "edge_case_guidance": "z"},
    }
    assert form_designer_strategy(brief) == []


def test_strategy_handles_empty_signals_lists_gracefully() -> None:
    brief = {
        "role_title": "Designer",
        "capability_areas": [
            {
                "name": "Bare area",
                "description": "no signals",
                "behance_specialization_signals": [],
                "tool_stack_signals": [],
            }
        ],
        "depth_distinction": {"builder_definition": "x", "user_definition": "y", "edge_case_guidance": "z"},
    }
    queries = form_designer_strategy(brief)
    # Just the baseline capability-area-name query.
    assert len(queries) == 1
    assert queries[0].query_text == "Bare area"


def test_strategy_skips_unsupported_sources() -> None:
    """`form_designer_strategy(..., sources=("google_cse",))` is a no-op
    in Slice 2 — Slice 3 wires the CSE branch."""

    queries = form_designer_strategy(
        _brief_with_one_capability_area(),
        sources=("google_cse",),
    )
    assert queries == []
