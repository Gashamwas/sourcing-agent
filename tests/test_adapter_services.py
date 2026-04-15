import asyncio
import importlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from github.schemas import GitHubProgress
from shared.schemas import OpusDecision, Progress, SearchString
from tests.test_github_pipeline import _make_candidate, _make_pipeline as _make_github_pipeline, _make_query
from tests.test_linkedin_pipeline import _make_snippet


def _make_linkedin_pipeline(output_dir: str):
    sys.modules.pop("linkedin.orchestrator", None)
    stubbed_llm = sys.modules.get("shared.llm_clients")
    if stubbed_llm is not None and not hasattr(stubbed_llm, "opus_llm"):
        sys.modules.pop("shared.llm_clients", None)
        importlib.import_module("shared.llm_clients")
    orchestrator_mod = importlib.import_module("linkedin.orchestrator")
    with patch.object(orchestrator_mod, "load_brief") as mock_brief, \
         patch.object(orchestrator_mod, "init_judger"), \
         patch.object(orchestrator_mod, "LinkedInBrowser"):
        brief = MagicMock()
        brief.id = "test"
        brief.linkedin_project_id = "test-project"
        brief.has_v2_schema = False
        brief.employer_blacklist = []
        brief.kit_url = ""
        brief.needs_preflight = MagicMock(return_value=False)
        mock_brief.return_value = brief

        brief_path = Path(output_dir) / "brief.json"
        brief_path.write_text('{"id": "test"}')

        return orchestrator_mod.Pipeline(brief_path=str(brief_path), output_dir=output_dir)


def test_github_acquisition_service_returns_terminal_geo_filter_result():
    pipeline = _make_github_pipeline()
    pipeline._runtime_run_id = None
    pipeline._ensure_services()
    pipeline._passes_geography_check = MagicMock(return_value=False)
    pipeline._prescreen_light = MagicMock(return_value="continue")
    pipeline._finish_preparation_terminal = MagicMock()
    pipeline._mark_terminal = MagicMock()
    pipeline._observer = MagicMock()

    candidate = _make_candidate("ada", "Ada Lovelace")
    query = _make_query(channel="code_search")
    progress = GitHubProgress(brief_name="test")
    enricher = MagicMock()
    enricher.light_enrich = AsyncMock(return_value=candidate)
    enricher.full_enrich = AsyncMock()

    result = asyncio.run(
        pipeline._acquisition_service.prepare_candidate_for_evaluation(
            enricher,
            "ada",
            query,
            progress,
        )
    )

    assert result.terminal_decision == "GEO_FILTERED"
    assert result.skip_reason == "light geography filter"
    pipeline._finish_preparation_terminal.assert_called_once()
    pipeline._mark_terminal.assert_called_once_with("ada")
    enricher.full_enrich.assert_not_awaited()


def test_github_work_unit_service_processes_graph_expansion_queue():
    pipeline = _make_github_pipeline()
    pipeline._runtime_run_id = None
    pipeline._ensure_services()
    pipeline._observer = MagicMock()
    query = _make_query(id=1)
    progress = GitHubProgress(
        brief_name="test",
        queries=[query],
        graph_expansion_queue=[
            {
                "username": "seed-user",
                "reason": "SAVE",
                "confidence": 0.92,
                "capability_area": "research",
                "added_at": "2026-01-01T00:00:00+00:00",
            }
        ],
        graph_expansion_processed=[],
    )

    asyncio.run(pipeline._work_unit_service.process_graph_expansion_queue(progress, progress.queries))

    assert len(progress.queries) == 2
    assert progress.queries[1].channel == "graph_expansion"
    pipeline._observer.on_graph_expansion_processed.assert_called_once()


def test_github_side_effects_service_handles_save_and_outreach():
    pipeline = _make_github_pipeline()
    pipeline._runtime_run_id = None
    pipeline._ensure_services()
    pipeline._observer = MagicMock()
    candidate = _make_candidate("ada", "Ada Lovelace")
    query = _make_query(name="Seed Query", channel="user_search")
    progress = GitHubProgress(brief_name="test")
    decision = OpusDecision(
        stage="full",
        decision="SAVE",
        path="research_builder",
        confidence=0.95,
        rationale="Strong fit",
        candidate_name="Ada Lovelace",
        profile_url="https://github.com/ada",
    )
    envelope = pipeline._execution_envelope(
        username="ada",
        query=query,
        result_rank=1,
        candidate=candidate,
        metadata={"candidate_record": {"username": "ada"}},
    )

    with patch("github.side_effects.generate_outreach", AsyncMock(return_value={"message": "hello"})), patch(
        "github.side_effects.extract_priority_rank",
        return_value=1,
    ):
        outcome = asyncio.run(
            pipeline._side_effects_service.handle_full_decision(
                username="ada",
                candidate=candidate,
                query=query,
                progress=progress,
                full_decision=decision,
                envelope=envelope,
                full_attempt_id=None,
            )
        )

    assert outcome.status == "succeeded"
    assert pipeline.stats["saved"] == 1
    assert progress.candidates_saved == 1
    assert query.saves == ["Ada Lovelace"]
    assert len(progress.graph_expansion_queue) == 1


def test_github_side_effects_service_skips_duplicate_outreach():
    pipeline = _make_github_pipeline()
    pipeline._runtime_run_id = None
    pipeline._ensure_services()
    pipeline._observer = MagicMock()
    pipeline._execution_engine = MagicMock()
    pipeline._execution_engine.runtime = MagicMock()
    pipeline._execution_engine.runtime.begin_candidate_side_effect = MagicMock(
        return_value={"should_execute": False, "side_effect": {"status": "succeeded"}}
    )
    pipeline._execution_engine.runtime.record_side_effect_result = MagicMock()
    candidate = _make_candidate("ada", "Ada Lovelace")
    query = _make_query(name="Seed Query", channel="user_search")
    progress = GitHubProgress(brief_name="test")
    decision = OpusDecision(
        stage="full",
        decision="SAVE",
        path="research_builder",
        confidence=0.95,
        rationale="Strong fit",
        candidate_name="Ada Lovelace",
        profile_url="https://github.com/ada",
    )
    envelope = pipeline._execution_envelope(
        username="ada",
        query=query,
        result_rank=1,
        candidate=candidate,
        metadata={"candidate_record": {"username": "ada"}},
    )
    envelope = type(envelope)(**{**envelope.__dict__, "run_id": 7})

    with patch("github.side_effects.generate_outreach", AsyncMock(return_value={"message": "hello"})), patch(
        "github.side_effects.extract_priority_rank",
        return_value=1,
    ):
        outcome = asyncio.run(
            pipeline._side_effects_service.handle_full_decision(
                username="ada",
                candidate=candidate,
                query=query,
                progress=progress,
                full_decision=decision,
                envelope=envelope,
                full_attempt_id=11,
            )
        )

    assert outcome.status == "succeeded"
    pipeline._execution_engine.runtime.record_side_effect_result.assert_called_once()


def test_linkedin_acquisition_service_extracts_dom_enriched_snippet():
    with tempfile.TemporaryDirectory() as td:
        pipeline = _make_linkedin_pipeline(td)
        pipeline._ensure_services()
        pipeline.browser.focus_card_for_review = AsyncMock()
        pipeline.browser.get_card_snapshot = AsyncMock(
            return_value={
                "innertext": "Select Ada Lovelace\nAda Lovelace\nML Engineer\nActivity 9 messages · In 3 projects · 3 views\nSaved by Sam Vangelos on April 11, 2026",
                "name": "Ada Lovelace",
                "url": "/talent/profile/ada",
                "already_saved": True,
                "recruiter_activity": {
                    "message_count": 9,
                    "project_count": 3,
                    "view_count": 3,
                    "saved_by": "Sam Vangelos",
                    "raw_activity_text": "Activity 9 messages · In 3 projects · 3 views | Saved by Sam Vangelos on April 11, 2026",
                },
            }
        )
        search_string = SearchString(id=9, name="seq", boolean="(test)")

        with patch(
            "linkedin.acquisition.extract_snippet_from_card_innertext",
            return_value=_make_snippet(
                name="Ada Lovelace",
                profile_url="",
                source_string_id=9,
                source_string_name="seq",
                page=2,
                result_rank=3,
            ),
        ), patch("linkedin.acquisition.human_delay_correlated", return_value=0.0):
            result = asyncio.run(
                pipeline._acquisition_service.extract_card_snippet(search_string, page_num=2, card_index=2)
            )

        assert result is not None
        assert result.snippet.name == "Ada Lovelace"
        assert result.snippet.profile_url == "/talent/profile/ada"
        assert result.snippet.already_saved is True
        assert result.snippet.recruiter_activity is not None
        assert result.snippet.recruiter_activity.message_count == 9
        assert result.snippet.novelty_pressure == "high"


def test_linkedin_acquisition_service_records_profile_open_through_governor():
    with tempfile.TemporaryDirectory() as td:
        pipeline = _make_linkedin_pipeline(td)
        pipeline._ensure_services()
        pipeline._governor = MagicMock()
        snippet = _make_snippet()
        snippet.card_index = 0
        pipeline.browser.ensure_card_rendered = AsyncMock()
        pipeline.browser.open_profile_by_url = AsyncMock(return_value=None)
        pipeline.browser.simulate_profile_read = AsyncMock(return_value=None)
        pipeline.browser.get_profile_innertext = AsyncMock(return_value="experience text")
        pipeline._ensure_browser_healthy = AsyncMock()

        with patch("linkedin.acquisition.extract_profile_from_dom", return_value=MagicMock()):
            asyncio.run(pipeline._acquisition_service.extract_profile_summary(snippet))

        pipeline._governor.check_profile_open_or_raise.assert_called_once()
        pipeline._governor.record_profile_open.assert_called_once()


def test_linkedin_work_unit_service_restarts_runtime_string_and_reloads_state():
    with tempfile.TemporaryDirectory() as td:
        pipeline = _make_linkedin_pipeline(td)
        pipeline._ensure_services()
        pipeline._runtime_run_id = 42
        pipeline._runtime_bridge = MagicMock()
        pipeline._runtime_bridge.load_search_memory.return_value = {"families": {}}
        pipeline._seen_urls = {"a"}
        pipeline._in_flight_urls = {"b"}
        pipeline._prior_outcomes = {"a": "SAVE"}
        pipeline._load_candidate_history = MagicMock()

        progress = Progress(brief_name="test", strings=[SearchString(id=5, name="test", boolean="foo")])
        pipeline._work_unit_service.restart_string(progress, 5)

        pipeline._runtime_bridge.restart_string.assert_called_once()
        pipeline._load_candidate_history.assert_called_once()
        assert pipeline._seen_urls == set()
        assert pipeline._in_flight_urls == set()
        assert pipeline._prior_outcomes == {}


def test_linkedin_side_effects_service_records_test_mode_save():
    with tempfile.TemporaryDirectory() as td:
        pipeline = _make_linkedin_pipeline(td)
        pipeline.test_mode = True
        pipeline._ensure_services()
        pipeline._runtime_run_id = 7
        pipeline._runtime_bridge = MagicMock()
        snippet = _make_snippet()
        search_string = SearchString(id=1, name="test", boolean="foo")

        outcome = asyncio.run(
            pipeline._side_effects_service.handle_save_decision(
                snippet=snippet,
                runtime_search_string=search_string,
                attempt_id=11,
            )
        )

        assert outcome.status == "succeeded"
        assert pipeline.stats["saved"] == 1
        pipeline._runtime_bridge.record_side_effect_result.assert_called_once()


def test_linkedin_side_effects_service_skips_duplicate_ledger_entry():
    with tempfile.TemporaryDirectory() as td:
        pipeline = _make_linkedin_pipeline(td)
        pipeline.test_mode = False
        pipeline._ensure_services()
        pipeline._runtime_run_id = 7
        pipeline._runtime_bridge = MagicMock()
        pipeline._runtime_bridge.begin_candidate_side_effect.return_value = {
            "should_execute": False,
            "side_effect": {"status": "succeeded"},
        }
        snippet = _make_snippet()
        search_string = SearchString(id=1, name="test", boolean="foo")

        outcome = asyncio.run(
            pipeline._side_effects_service.handle_save_decision(
                snippet=snippet,
                runtime_search_string=search_string,
                attempt_id=11,
            )
        )

        assert outcome.status == "skipped"
        pipeline.browser.is_already_saved.assert_not_called()
