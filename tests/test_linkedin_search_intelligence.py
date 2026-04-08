"""LinkedIn search-intelligence and mutation-executor regressions."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from linkedin.search_intelligence import (
    LinkedInPageInsights,
    LinkedInSearchVariant,
    LinkedInStructuredFilters,
    bootstrap_experiment_state,
    result_window_for_count,
)
from linkedin.search_mutation import LinkedInSearchMutationExecutor
from shared.schemas import SearchString


def _make_pipeline(output_dir: str):
    with patch("linkedin.orchestrator.load_brief") as mock_brief, \
         patch("linkedin.orchestrator.init_judger"), \
         patch("linkedin.orchestrator.LinkedInBrowser"):
        brief = MagicMock()
        brief.id = "test"
        brief.linkedin_project_id = "test-project"
        brief.has_v2_schema = False
        brief.employer_blacklist = []
        mock_brief.return_value = brief

        brief_path = Path(output_dir) / "brief.json"
        brief_path.write_text('{"id": "test"}')

        from linkedin.orchestrator import Pipeline

        return Pipeline(brief_path=str(brief_path), output_dir=output_dir)


def test_result_window_for_count_matches_policy():
    assert result_window_for_count(7500) == (200, 1200)
    assert result_window_for_count(3200) == (150, 800)
    assert result_window_for_count(900) == (75, 400)
    assert result_window_for_count(200) is None


def test_bootstrap_experiment_state_preserves_legacy_refinement_shadow():
    search_string = SearchString(
        id=7,
        name="RL builders",
        boolean="bar",
        original_boolean="foo",
        refinement_stack=["foo"],
        phase="paginate",
    )

    state = bootstrap_experiment_state(search_string)

    assert state.intent.root_boolean == "foo"
    assert state.active_variant.boolean == "bar"
    assert state.committed_variant_id == state.active_variant_id
    assert search_string.boolean == "bar"
    assert search_string.refinement_stack == ["foo"]


def test_search_mutation_executor_rejects_non_empty_experimental_filters(tmp_path):
    pipeline = _make_pipeline(str(tmp_path))
    search_string = SearchString(id=3, name="builders", boolean="foo")
    state = bootstrap_experiment_state(search_string)
    variant = LinkedInSearchVariant(
        variant_id="precision-1",
        parent_variant_id="root",
        root_string_id=3,
        boolean="foo AND bar",
        variant_kind="precision",
        structured_filters=LinkedInStructuredFilters(titles=["Staff Engineer"]),
    )

    result = asyncio.run(
        LinkedInSearchMutationExecutor(pipeline).apply_variant(
            search_string=search_string,
            experiment_state=state,
            variant=variant,
        )
    )

    assert result.applied is False
    assert result.blocked_reason == "experimental_structured_filters_not_supported"


def test_search_mutation_executor_applies_keyword_variant(tmp_path):
    pipeline = _make_pipeline(str(tmp_path))
    pipeline.browser.go_back_to_results = AsyncMock()
    pipeline.browser.enter_search_string = AsyncMock()
    pipeline.browser.get_results_count_text = AsyncMock(return_value="220")
    pipeline.browser.get_results_count = AsyncMock(return_value=220)
    pipeline.browser.get_card_snapshot = AsyncMock(return_value={"name": "Ada", "url": "/talent/profile/ada"})

    search_string = SearchString(id=3, name="builders", boolean="foo")
    state = bootstrap_experiment_state(search_string)
    variant = LinkedInSearchVariant(
        variant_id="precision-1",
        parent_variant_id="root",
        root_string_id=3,
        boolean="foo AND bar",
        variant_kind="precision",
        target_result_min=75,
        target_result_max=400,
    )
    state.begin_experiment_round([variant])

    with patch("linkedin.search_mutation.human_delay_correlated", return_value=0):
        result = asyncio.run(
            LinkedInSearchMutationExecutor(pipeline).apply_variant(
                search_string=search_string,
                experiment_state=state,
                variant=variant,
            )
        )

    assert result.applied is True
    assert result.result_count == 220
    assert state.active_variant_id == "precision-1"
    assert pipeline._search_mutation_budget_used == 1
    pipeline.browser.enter_search_string.assert_awaited_once_with("foo AND bar")


def test_experiment_state_tracks_family_totals_and_drift_snapshots():
    search_string = SearchString(id=11, name="builders", boolean="foo")
    state = bootstrap_experiment_state(search_string)
    state.commit_variant("root")

    page1 = LinkedInPageInsights(
        page=1,
        result_count=1800,
        result_window="150-800",
        title_clusters=[{"label": "machine learning engineer", "count": 4}],
        company_clusters=[{"label": "OpenAI", "count": 2}],
        signal_anchors=["ML engineer at OpenAI", "Research engineer at Anthropic"],
    )
    state.record_variant_metrics(page_num=1, result_count=1800, page_stats={"candidates": 4, "facial_yes": 2, "saves": 1}, page_insights=page1)
    state.record_family_page_metrics(page_num=1, result_count=1800, page_stats={"candidates": 4, "facial_yes": 2, "saves": 1}, page_insights=page1)

    page3 = LinkedInPageInsights(
        page=3,
        result_count=1800,
        result_window="150-800",
        title_clusters=[{"label": "product manager", "count": 5}],
        company_clusters=[{"label": "BigCo", "count": 3}],
        noise_anchors=["Product manager at BigCo", "Program manager at BankCorp"],
        dominant_non_fit_patterns=["product-heavy profiles dominate recent pages"],
        glance_action="reformulate",
    )
    state.record_variant_metrics(page_num=3, result_count=1800, page_stats={"candidates": 5, "facial_no": 4}, page_insights=page3)
    state.record_family_page_metrics(page_num=3, result_count=1800, page_stats={"candidates": 5, "facial_no": 4}, page_insights=page3)

    summary = state.metrics_summary()

    assert summary["family_pages_reviewed_total"] == 2
    assert summary["family_candidates_total"] == 9
    assert summary["family_signal_total"] == 3
    assert summary["family_saves_total"] == 1
    assert summary["active_variant_pages_reviewed"] == 3
    assert state.early_signal_snapshot is not None
    assert state.recent_noise_snapshot is not None
    assert state.early_signal_snapshot.signal_anchors[0] == "ML engineer at OpenAI"
    assert state.recent_noise_snapshot.noise_anchors[0] == "Product manager at BigCo"


def test_search_mutation_executor_blocks_second_drift_attempt(tmp_path):
    pipeline = _make_pipeline(str(tmp_path))
    search_string = SearchString(id=3, name="builders", boolean="foo")
    state = bootstrap_experiment_state(search_string)
    state.commit_variant("root")
    state.drift_attempt_count = 1

    variant = LinkedInSearchVariant(
        variant_id="drift-1",
        parent_variant_id="root",
        root_string_id=3,
        boolean="foo NOT bar",
        variant_kind="recall",
    )

    result = asyncio.run(
        LinkedInSearchMutationExecutor(pipeline).apply_variant(
            search_string=search_string,
            experiment_state=state,
            variant=variant,
            mutation_kind="drift",
        )
    )

    assert result.applied is False
    assert result.blocked_reason == "drift_attempt_limit"
