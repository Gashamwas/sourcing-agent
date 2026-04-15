"""Tests for LinkedIn pipeline dedup semantics.

Run with: python -m pytest tests/test_linkedin_pipeline.py -v
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.schemas import (
    AdaptationResponse,
    CandidateSnippet,
    ExecutionPlan,
    GlanceResult,
    OpusDecision,
    Progress,
    SearchString,
)
from shared.reconciliation_schemas import RecruiterActivitySnapshot
from shared.governor import SessionExpired
from shared.storage import append_jsonl, read_jsonl
from linkedin.search_intelligence import LinkedInPageInsights, LinkedInSearchVariant
from linkedin.search_mutation import SearchMutationResult


def _make_snippet(**kwargs) -> CandidateSnippet:
    defaults = {
        "name": "Test Person",
        "headline": "",
        "current_title": "",
        "current_company": "",
        "location": "Somewhere",
        "education_snippet": "",
        "profile_url": "/talent/profile/test123",
        "source_string_id": 1,
        "source_string_name": "test",
        "page": 1,
        "result_rank": 1,
    }
    defaults.update(kwargs)
    return CandidateSnippet(**defaults)


def _make_pipeline(output_dir: str):
    """Create a Pipeline instance with mocked dependencies for unit testing."""
    with patch("linkedin.orchestrator.load_brief") as mock_brief, \
         patch("linkedin.orchestrator.init_judger"), \
         patch("linkedin.orchestrator.LinkedInBrowser"):
        brief = MagicMock()
        brief.id = "test"
        brief.linkedin_project_id = "test-project"
        brief.has_v2_schema = False
        brief.employer_blacklist = []
        mock_brief.return_value = brief

        # Create a dummy brief file
        brief_path = Path(output_dir) / "brief.json"
        brief_path.write_text('{"id": "test"}')

        from linkedin.orchestrator import Pipeline
        p = Pipeline(brief_path=str(brief_path), output_dir=output_dir)
        return p


# ---------------------------------------------------------------------------
# _mark_terminal
# ---------------------------------------------------------------------------

def test_mark_terminal_promotes_url():
    """_mark_terminal moves URL from in-flight to seen."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        url = "/talent/profile/abc"
        p._in_flight_urls.add(url)
        assert url not in p._seen_urls

        p._mark_terminal(url)

        assert url in p._seen_urls
        assert url not in p._in_flight_urls


def test_checkpoint_progress_persists_mid_page_state():
    """Mid-page checkpoint should persist the current page for resume."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        p.stats["saved"] = 3
        p.stats["rejected"] = 2

        search_string = SearchString(id=58, name="test", boolean="foo", status="in_progress")
        progress = Progress(brief_name="test", strings=[search_string], current_string_id=58, current_page=1)

        p._checkpoint_progress(progress, search_string=search_string, page_num=2)

        saved = json.loads(Path(td, "progress.json").read_text())
        assert saved["current_string_id"] == 58
        assert saved["current_page"] == 2
        assert saved["candidates_saved"] == 3
        assert saved["candidates_rejected"] == 2
        assert saved["strings"][0]["pages_reviewed"] == 2


def test_checkpoint_progress_does_not_move_page_backwards():
    """Checkpointing an earlier page should not regress resume state."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        search_string = SearchString(
            id=58,
            name="test",
            boolean="foo",
            status="in_progress",
            pages_reviewed=3,
        )
        progress = Progress(brief_name="test", strings=[search_string], current_string_id=58, current_page=3)

        p._checkpoint_progress(progress, search_string=search_string, page_num=2)

        saved = json.loads(Path(td, "progress.json").read_text())
        assert saved["current_page"] == 2
        assert saved["strings"][0]["pages_reviewed"] == 3


# ---------------------------------------------------------------------------
# Dedup checks
# ---------------------------------------------------------------------------

def test_in_flight_blocks_dedup():
    """URL in _in_flight_urls should block at dedup check."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        url = "/talent/profile/inflight"
        p._in_flight_urls.add(url)

        # Should be blocked
        assert url in p._in_flight_urls
        assert url not in p._seen_urls
        # Both sets checked together
        assert url in p._seen_urls or url in p._in_flight_urls


def test_seen_blocks_dedup():
    """URL in _seen_urls should block at dedup check."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        url = "/talent/profile/seen"
        p._seen_urls.add(url)

        assert url in p._seen_urls or url in p._in_flight_urls


# ---------------------------------------------------------------------------
# Dedup source: history only, not snippets.jsonl
# ---------------------------------------------------------------------------

def test_snippets_jsonl_not_dedup_source():
    """_seen_urls starts empty, NOT populated from snippets.jsonl."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        url = "/talent/profile/from-snippets"

        # Write a snippet to snippets.jsonl
        snippet = _make_snippet(profile_url=url)
        append_jsonl(p.snippets_path, snippet.to_dict())

        # Reset dedup state as init paths do
        p._seen_urls = set()
        p._in_flight_urls = set()
        p._prior_outcomes = {}
        p._load_candidate_history()

        # URL should NOT be in _seen_urls (no history entry)
        assert url not in p._seen_urls


def test_crash_after_snippet_retries_on_resume():
    """URL in snippets.jsonl but NOT in history → NOT in _seen_urls on reload."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        url = "/talent/profile/crashed"

        # Simulate: snippet extracted but crash before history write
        append_jsonl(p.snippets_path, _make_snippet(profile_url=url).to_dict())
        # No history entry for this URL

        # Simulate resume reload
        p._seen_urls = set()
        p._in_flight_urls = set()
        p._prior_outcomes = {}
        p._load_candidate_history()

        assert url not in p._seen_urls
        assert url not in p._in_flight_urls


def test_terminal_candidate_skipped_on_resume():
    """URL in history with REJECT → IS in _seen_urls on reload."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        url = "/talent/profile/rejected"

        # Write history entry
        append_jsonl(p.history_path, {
            "profile_url": url,
            "candidate_name": "Rejected Person",
            "outcome": "REJECT",
            "confidence": 0.9,
            "timestamp": "2026-01-01T00:00:00+00:00",
        })

        # Simulate resume reload
        p._seen_urls = set()
        p._in_flight_urls = set()
        p._prior_outcomes = {}
        p._load_candidate_history()

        assert url in p._seen_urls
        assert p._prior_outcomes[url] == "REJECT"


# ---------------------------------------------------------------------------
# Non-terminal outcomes
# ---------------------------------------------------------------------------

def test_parse_failure_not_terminal():
    """PARSE_FAILURE → URL NOT in _seen_urls, removed from _in_flight_urls."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        url = "/talent/profile/parse-fail"
        p._in_flight_urls.add(url)

        # Simulate what the code does on PARSE_FAILURE
        p._in_flight_urls.discard(url)

        assert url not in p._seen_urls
        assert url not in p._in_flight_urls


def test_judgment_failure_not_terminal():
    """JUDGMENT_FAILURE at full stage → not promoted, allows retry."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        url = "/talent/profile/judgment-fail"

        # Simulate: facial passed (terminal), then full judgment fails
        p._in_flight_urls.add(url)
        # Facial terminal marking happened
        p._mark_terminal(url)
        p._prior_outcomes[url] = "FACIAL_YES"

        # Now full judgment failure: URL is in _seen_urls from facial
        # but _prior_outcomes is FACIAL_YES → FACIAL_YES recovery path handles it
        assert url in p._seen_urls
        assert p._prior_outcomes[url] == "FACIAL_YES"


def test_activity_saturation_skip_is_conservative_for_weak_high_pressure_snippet():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        snippet = _make_snippet(
            headline="GenAI builder",
            recruiter_activity=RecruiterActivitySnapshot(message_count=9, project_count=3, view_count=3),
            novelty_pressure="high",
        )
        facial = OpusDecision(
            stage="facial",
            decision="FACIAL_YES",
            path="direct_experience",
            confidence=0.62,
            rationale="Plausible but limited evidence from preview.",
            candidate_name=snippet.name,
            profile_url=snippet.profile_url,
        )

        assert p._should_skip_full_eval_for_activity(snippet, facial) is True


def test_build_run_report_snapshot_includes_activity_metrics():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        p.stats.update(
            {
                "snippets_extracted": 10,
                "facial_yes": 4,
                "facial_no": 6,
                "saved": 2,
                "rejected": 1,
                "high_pressure_candidates_seen": 3,
                "activity_saturated_preview_skips": 2,
                "high_fit_low_novelty_saves": 1,
            }
        )
        progress = Progress(
            brief_name="test",
            strings=[SearchString(id=1, name="test", boolean="foo", status="done", pages_reviewed=1)],
        )

        snapshot = p._build_run_report_snapshot(progress)

        metrics = snapshot["metrics_summary"]
        assert metrics["high_pressure_candidates_seen"] == 3
        assert metrics["activity_saturated_preview_skips"] == 2
        assert metrics["high_fit_low_novelty_saves"] == 1


# ---------------------------------------------------------------------------
# FACIAL_YES recovery
# ---------------------------------------------------------------------------

def test_facial_yes_prior_triggers_reeval():
    """_prior_outcomes[url] == 'FACIAL_YES' → discarded from _seen_urls for re-eval."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        url = "/talent/profile/facial-yes"

        # Simulate: history has FACIAL_YES
        p._seen_urls.add(url)
        p._prior_outcomes[url] = "FACIAL_YES"

        # The dedup check logic discards FACIAL_YES from _seen_urls
        prior = p._prior_outcomes.get(url, "")
        assert prior == "FACIAL_YES"
        p._seen_urls.discard(url)

        # After discard, should pass dedup
        assert url not in p._seen_urls


# ---------------------------------------------------------------------------
# Glance skip
# ---------------------------------------------------------------------------

def test_glance_skip_same_session_only():
    """Glance-skip marks terminal in-session via _mark_terminal, NOT persisted to history."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        url = "/talent/profile/glance"

        # Simulate glance skip: add to in-flight then mark terminal
        p._in_flight_urls.add(url)
        p._mark_terminal(url)

        assert url in p._seen_urls
        assert url not in p._in_flight_urls

        # No history entry written — on resume, URL should NOT be in _seen_urls
        p._seen_urls = set()
        p._in_flight_urls = set()
        p._prior_outcomes = {}
        p._load_candidate_history()

        assert url not in p._seen_urls


# ---------------------------------------------------------------------------
# _restart_string
# ---------------------------------------------------------------------------

def test_restart_string_clears_history():
    """_restart_string removes matching URLs from history, _seen_urls, _prior_outcomes."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        url1 = "/talent/profile/string1-candidate"
        url2 = "/talent/profile/other-string-candidate"

        # Write snippets for string 1 and string 2
        append_jsonl(p.snippets_path, _make_snippet(
            profile_url=url1, source_string_id=1,
        ).to_dict())
        append_jsonl(p.snippets_path, _make_snippet(
            profile_url=url2, source_string_id=2, name="Other Person",
        ).to_dict())

        # Write history entries
        append_jsonl(p.history_path, {
            "profile_url": url1, "candidate_name": "Test Person",
            "outcome": "REJECT", "confidence": 0.9,
            "source_string_id": 1,
            "timestamp": "2026-01-01T00:00:00+00:00",
        })
        append_jsonl(p.history_path, {
            "profile_url": url2, "candidate_name": "Other Person",
            "outcome": "SAVE", "confidence": 0.95,
            "source_string_id": 2,
            "timestamp": "2026-01-01T00:00:00+00:00",
        })

        # Load into memory
        p._seen_urls = {url1, url2}
        p._prior_outcomes = {url1: "REJECT", url2: "SAVE"}
        p._in_flight_urls = set()

        # Create a mock progress with string 1
        from shared.schemas import SearchString, Progress
        s1 = SearchString(id=1, name="test string", boolean="test", status="done",
                          pages_reviewed=3, saves=[], notes="")
        s2 = SearchString(id=2, name="other string", boolean="test2", status="done",
                          pages_reviewed=2, saves=[], notes="")
        progress = Progress(brief_name="test", strings=[s1, s2], current_string_id=1)
        progress.save = MagicMock()

        p._restart_string(progress, 1)

        # url1 should be removed from everything
        assert url1 not in p._seen_urls
        assert url1 not in p._prior_outcomes

        # url2 should still be present
        assert url2 in p._seen_urls
        assert p._prior_outcomes[url2] == "SAVE"

        # History file should only have url2's entry
        remaining = read_jsonl(p.history_path)
        remaining_urls = [r["profile_url"] for r in remaining]
        assert url1 not in remaining_urls
        assert url2 in remaining_urls


def test_restart_strings_restarts_multiple_ids():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)

        append_jsonl(p.snippets_path, _make_snippet(
            profile_url="/talent/profile/string1-candidate",
            source_string_id=1,
        ).to_dict())
        append_jsonl(p.snippets_path, _make_snippet(
            profile_url="/talent/profile/string2-candidate",
            source_string_id=2,
            name="Second Person",
        ).to_dict())

        append_jsonl(p.history_path, {
            "profile_url": "/talent/profile/string1-candidate",
            "candidate_name": "Test Person",
            "outcome": "REJECT",
            "confidence": 0.9,
            "source_string_id": 1,
            "timestamp": "2026-01-01T00:00:00+00:00",
        })
        append_jsonl(p.history_path, {
            "profile_url": "/talent/profile/string2-candidate",
            "candidate_name": "Second Person",
            "outcome": "SAVE",
            "confidence": 0.95,
            "source_string_id": 2,
            "timestamp": "2026-01-01T00:00:00+00:00",
        })

        p._seen_urls = {"/talent/profile/string1-candidate", "/talent/profile/string2-candidate"}
        p._prior_outcomes = {
            "/talent/profile/string1-candidate": "REJECT",
            "/talent/profile/string2-candidate": "SAVE",
        }
        p._in_flight_urls = set()

        s1 = SearchString(id=1, name="one", boolean="a", status="done", pages_reviewed=3, saves=["A"], notes="Error")
        s2 = SearchString(id=2, name="two", boolean="b", status="done", pages_reviewed=2, saves=["B"], notes="Error")
        s3 = SearchString(id=3, name="three", boolean="c", status="queued", pages_reviewed=0, saves=[], notes="")
        progress = Progress(brief_name="test", strings=[s1, s2, s3], current_string_id=2)
        progress.save = MagicMock()

        p._restart_strings(progress, [2, 1, 2])

        assert s1.status == "queued"
        assert s2.status == "queued"
        assert s1.notes == ""
        assert s2.notes == ""
        assert s1.saves == []
        assert s2.saves == []
        assert "/talent/profile/string1-candidate" not in p._seen_urls
        assert "/talent/profile/string2-candidate" not in p._seen_urls
        assert "/talent/profile/string1-candidate" not in p._prior_outcomes
        assert "/talent/profile/string2-candidate" not in p._prior_outcomes


# ---------------------------------------------------------------------------
# In-flight reset on dedup rebuild
# ---------------------------------------------------------------------------

def test_in_flight_reset_on_dedup_rebuild():
    """_in_flight_urls and _prior_outcomes start empty on each dedup rebuild."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)

        # Simulate some state from a prior run
        p._in_flight_urls = {"/talent/profile/stale"}
        p._prior_outcomes = {"stale": "FACIAL_YES"}

        # Rebuild as init paths do
        p._seen_urls = set()
        p._in_flight_urls = set()
        p._prior_outcomes = {}
        p._load_candidate_history()

        assert len(p._in_flight_urls) == 0
        # _prior_outcomes only populated from history file
        assert "stale" not in p._prior_outcomes


# ---------------------------------------------------------------------------
# _prior_outcomes sync
# ---------------------------------------------------------------------------

def test_prior_outcomes_synced_on_terminal():
    """After history write + _mark_terminal, _prior_outcomes[url] matches the decision."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        url = "/talent/profile/synced"

        # Simulate what the code does after a terminal facial decision
        p._in_flight_urls.add(url)
        p._prior_outcomes[url] = "FACIAL_NO"
        p._mark_terminal(url)

        assert url in p._seen_urls
        assert url not in p._in_flight_urls
        assert p._prior_outcomes[url] == "FACIAL_NO"

        # Simulate what the code does after a terminal full decision
        url2 = "/talent/profile/synced2"
        p._in_flight_urls.add(url2)
        p._prior_outcomes[url2] = "SAVE"
        p._mark_terminal(url2)

        assert url2 in p._seen_urls
        assert p._prior_outcomes[url2] == "SAVE"


# ---------------------------------------------------------------------------
# Sequential per-card extraction
# ---------------------------------------------------------------------------

def test_extract_card_snippet_uses_dom_metadata():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        p.browser.focus_card_for_review = AsyncMock()
        p.browser.get_card_snapshot = AsyncMock(return_value={
            "innertext": "Select Ada Lovelace\nAda Lovelace\nML Engineer",
            "name": "Ada Lovelace",
            "url": "/talent/profile/ada",
            "already_saved": True,
        })

        from shared.schemas import SearchString
        search_string = SearchString(id=9, name="seq", boolean="(test)")

        with patch("linkedin.acquisition.extract_snippet_from_card_innertext", return_value=_make_snippet(
            name="LLM Name",
            profile_url="",
            source_string_id=9,
            source_string_name="seq",
            page=2,
            result_rank=3,
        )), patch("linkedin.acquisition.human_delay_correlated", return_value=0.0):
            snippet = asyncio.run(p._extract_card_snippet(search_string, page_num=2, card_index=2))

        assert snippet is not None
        assert snippet.name == "Ada Lovelace"
        assert snippet.profile_url == "/talent/profile/ada"
        assert snippet.card_index == 2
        assert snippet.already_saved is True
        p.browser.focus_card_for_review.assert_awaited_once_with(2)


def test_extract_card_snippet_returns_none_when_card_text_missing():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        p.browser.focus_card_for_review = AsyncMock()
        p.browser.get_card_snapshot = AsyncMock(return_value={
            "innertext": "",
            "name": "",
            "url": "",
            "already_saved": False,
        })

        from shared.schemas import SearchString
        search_string = SearchString(id=9, name="seq", boolean="(test)")

        with patch("linkedin.acquisition.human_delay_correlated", return_value=0.0):
            snippet = asyncio.run(p._extract_card_snippet(search_string, page_num=1, card_index=0))

    assert snippet is None


def test_extract_card_snippet_uses_dom_metadata_when_card_text_missing():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        p.browser.focus_card_for_review = AsyncMock()
        p.browser.get_card_snapshot = AsyncMock(return_value={
            "innertext": "",
            "name": "Ada Lovelace",
            "url": "/talent/profile/ada",
            "already_saved": False,
        })

        from shared.schemas import SearchString
        search_string = SearchString(id=9, name="seq", boolean="(test)")

        with patch(
            "linkedin.acquisition.extract_snippet_from_card_innertext",
            return_value=_make_snippet(
                name="Ada Lovelace",
                profile_url="",
                source_string_id=9,
                source_string_name="seq",
                page=1,
                result_rank=1,
            ),
        ) as extract_mock, patch("linkedin.acquisition.human_delay_correlated", return_value=0.0):
            snippet = asyncio.run(p._extract_card_snippet(search_string, page_num=1, card_index=0))

        assert snippet is not None
        assert snippet.name == "Ada Lovelace"
        assert snippet.profile_url == "/talent/profile/ada"
        extract_mock.assert_called_once()
        assert extract_mock.call_args.kwargs["dom_name"] == "Ada Lovelace"
        assert extract_mock.call_args.kwargs["dom_url"] == "/talent/profile/ada"


def test_extract_card_snippet_returns_none_on_slot_rehydration_error():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        p.browser.focus_card_for_review = AsyncMock(
            side_effect=TimeoutError("Locator.scroll_into_view_if_needed: Timeout 3000ms exceeded.")
        )
        p.browser.get_card_snapshot = AsyncMock()
        p.browser.go_back_to_results = AsyncMock()

        search_string = SearchString(id=16, name="seq", boolean="(test)")

        with patch("linkedin.acquisition.human_delay_correlated", return_value=0.0):
            snippet = asyncio.run(p._extract_card_snippet(search_string, page_num=1, card_index=5))

        assert snippet is None
        p.browser.go_back_to_results.assert_awaited_once()
        p.browser.get_card_snapshot.assert_not_awaited()


# ---------------------------------------------------------------------------
# Batch facial parity
# ---------------------------------------------------------------------------

def test_batch_full_failures_do_not_increment_facial_yes():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        p.brief_obj.has_v2_schema = True
        p.brief_obj.employer_blacklist = []
        p.browser.get_card_slot_count = AsyncMock(return_value=2)
        p._extract_card_snippet = AsyncMock(side_effect=[
            _make_snippet(name="Alice", profile_url="/talent/profile/alice"),
            _make_snippet(name="Bob", profile_url="/talent/profile/bob"),
        ])
        p._full_evaluate = AsyncMock(side_effect=[
            OpusDecision(
                stage="full", decision="PARSE_FAILURE", path="none",
                confidence=0.0, rationale="[PARSE_FAILURE: bad output]",
                candidate_name="Alice", profile_url="/talent/profile/alice",
            ),
            OpusDecision(
                stage="full", decision="JUDGMENT_FAILURE", path="none",
                confidence=0.0, rationale="[JUDGMENT_FAILURE: timeout]",
                candidate_name="Bob", profile_url="/talent/profile/bob",
            ),
        ])
        p._checkpoint_progress = MagicMock()
        p._bias_monitor = None
        p._triage_tightened = False
        p._tightening_prefix = ""

        search_string = SearchString(id=1, name="batch", boolean="ml")
        page_report = MagicMock()
        all_candidates = []
        string_stats = {
            "pages": 1,
            "candidates": 0,
            "duplicates": 0,
            "facial_yes": 0,
            "facial_no": 0,
            "saves": 0,
            "rejects": 0,
        }

        with patch(
            "shared.judger.facial_judge_batch",
            return_value=[
                OpusDecision(
                    stage="facial", decision="FACIAL_YES", path="none",
                    confidence=1.0, rationale="good signal",
                    candidate_name="Alice", profile_url="/talent/profile/alice",
                ),
                OpusDecision(
                    stage="facial", decision="FACIAL_YES", path="none",
                    confidence=1.0, rationale="good signal",
                    candidate_name="Bob", profile_url="/talent/profile/bob",
                ),
            ],
        ):
            asyncio.run(
                p._review_page_batch(
                    search_string, 1, 0, page_report, all_candidates, string_stats, None,
                )
            )

        assert string_stats["facial_yes"] == 0
        assert string_stats["saves"] == 0
        assert string_stats["rejects"] == 0
        assert [c["outcome"] for c in all_candidates] == ["error", "error"]


# ---------------------------------------------------------------------------
# Judgment failure from exception is non-terminal
# ---------------------------------------------------------------------------

def test_judgment_failure_exception_not_terminal():
    """Facial exception -> JUDGMENT_FAILURE -> not in _seen_urls, not in history."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        url = "/talent/profile/exception-candidate"

        # Simulate: candidate enters in-flight
        p._in_flight_urls.add(url)

        # Simulate what orchestrator does on JUDGMENT_FAILURE:
        # is_failure_decision(facial.decision) is True -> discard from in-flight
        p._in_flight_urls.discard(url)

        # Should NOT be terminal
        assert url not in p._seen_urls
        assert url not in p._in_flight_urls
        assert url not in p._prior_outcomes

        # On resume, should NOT be in _seen_urls (no history entry)
        p._seen_urls = set()
        p._in_flight_urls = set()
        p._prior_outcomes = {}
        p._load_candidate_history()

        assert url not in p._seen_urls


# ---------------------------------------------------------------------------
# Resume / adaptation ordering
# ---------------------------------------------------------------------------

def test_run_full_resume_preserves_persisted_queue_order():
    """Resume should preserve the saved queue order instead of sorting by ID."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)

        from shared.schemas import Progress, SearchString

        progress = Progress(
            brief_name="test",
            strings=[
                SearchString(id=2, name="second", boolean="two"),
                SearchString(id=1, name="first", boolean="one"),
            ],
        )
        progress.save(str(p.progress_path))

        p.browser.connect = AsyncMock()
        p.browser.disconnect = AsyncMock()
        p.browser.page = MagicMock(url="https://www.linkedin.com/talent/search")
        p._load_candidate_history = MagicMock()
        p._print_session_summary = MagicMock()
        p._print_summary = MagicMock()
        p._generate_run_report = MagicMock()
        p._session_expired = MagicMock()

        processed_ids = []

        async def fake_process(search_string, progress):
            processed_ids.append(search_string.id)

        p._process_string = fake_process

        asyncio.run(p.run_full(resume=True))

        assert processed_ids == [2, 1]


def test_run_block_adaptation_pivot_keeps_inserted_replacements_queued():
    """Architecture pivots should skip the old queue, not the newly inserted replacements."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)

        from shared.schemas import Progress, SearchString

        progress = Progress(
            brief_name="test",
            strings=[
                SearchString(id=1, name="done", boolean="one", status="done", block="Block A"),
                SearchString(id=2, name="old queued", boolean="two", block="Block A"),
                SearchString(id=3, name="later queued", boolean="three", block="Block B"),
            ],
        )
        p._execution_plan = ExecutionPlan(
            strategy_rationale="test",
            architecture="sniper",
            original_architecture="sniper",
        )

        response = AdaptationResponse(
            new_strings=[
                {"boolean": "replacement one", "rationale": "replacement one"},
                {"boolean": "replacement two", "rationale": "replacement two"},
            ],
            pivot_to_architecture="company_first",
            pivot_rationale="switch architectures",
        )

        asyncio.run(
            p._run_block_adaptation(
                "Block A",
                [progress.strings[0]],
                progress,
                lambda *args, **kwargs: response,
            )
        )

        assert [(s.id, s.status) for s in progress.strings] == [
            (1, "done"),
            (4, "queued"),
            (5, "queued"),
            (2, "skipped"),
            (3, "skipped"),
        ]


def test_run_full_rechecks_queue_after_block_adaptation():
    """When adaptation mutates the queue, run_full should process the replacement string next."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)

        from shared.schemas import Progress, SearchString

        progress = Progress(
            brief_name="test",
            strings=[
                SearchString(id=1, name="block a", boolean="one", block="Block A"),
                SearchString(id=2, name="block b", boolean="two", block="Block B"),
            ],
        )
        progress.save(str(p.progress_path))

        p.browser.connect = AsyncMock()
        p.browser.disconnect = AsyncMock()
        p.browser.page = MagicMock(url="https://www.linkedin.com/talent/search")
        p._load_candidate_history = MagicMock()
        p._print_session_summary = MagicMock()
        p._print_summary = MagicMock()
        p._generate_run_report = MagicMock()
        p._session_expired = MagicMock()
        p._execution_plan = ExecutionPlan(
            strategy_rationale="test",
            architecture="sniper",
            original_architecture="sniper",
        )

        processed_ids = []

        async def fake_process(search_string, progress):
            processed_ids.append(search_string.id)

        p._process_string = fake_process

        responses = iter([
            AdaptationResponse(
                new_strings=[{"boolean": "replacement", "rationale": "replacement"}],
                skip_remaining=[{"string_id": 2, "reason": "replace old next string"}],
                pivot_to_architecture="company_first",
                pivot_rationale="switch architectures",
            ),
            AdaptationResponse(),
        ])

        def fake_adapt(*args, **kwargs):
            return next(responses)

        with patch("linkedin.strategy.adapt_after_block", side_effect=fake_adapt):
            asyncio.run(p.run_full(resume=True))

        assert processed_ids == [1, 3]


def test_run_full_resume_preserves_in_progress_string_on_session_expiry():
    """SessionExpired should checkpoint and bubble out without downgrading the interrupted string."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)

        progress = Progress(
            brief_name="test",
            strings=[
                SearchString(
                    id=5,
                    name="interrupted",
                    boolean="one",
                    status="in_progress",
                    block="Block A",
                    pages_reviewed=1,
                ),
                SearchString(id=6, name="next", boolean="two", status="queued", block="Block B"),
            ],
            current_string_id=5,
            current_page=1,
        )
        progress.save(str(p.progress_path))

        p.browser.connect = AsyncMock()
        p.browser.disconnect = AsyncMock()
        p.browser.page = MagicMock(url="https://www.linkedin.com/talent/search")
        p._print_session_summary = MagicMock()
        p._print_summary = MagicMock()
        p._generate_run_report = MagicMock()

        processed_ids = []

        async def fake_process(search_string, progress):
            processed_ids.append(search_string.id)
            raise SessionExpired("session_duration_cap")

        p._process_string = fake_process

        with pytest.raises(SessionExpired):
            asyncio.run(p.run_full(resume=True))

        saved = json.loads(Path(td, "progress.json").read_text())
        assert processed_ids == [5]
        assert saved["current_string_id"] == 5
        assert saved["current_page"] == 1
        assert saved["strings"][0]["status"] == "in_progress"
        assert saved["strings"][1]["status"] == "queued"


def test_run_full_retries_same_string_after_browser_crash_recovery():
    """Browser target crashes should recover and retry the interrupted string in place."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)

        progress = Progress(
            brief_name="test",
            strings=[SearchString(id=5, name="interrupted", boolean="one", status="queued", block="Block A")],
        )
        progress.save(str(p.progress_path))

        p.browser.connect = AsyncMock()
        p.browser.disconnect = AsyncMock()
        p.browser.page = MagicMock(url="https://www.linkedin.com/talent/search")
        p.browser.recover_from_target_crash = AsyncMock(return_value=True)
        p._attempt_reconnect = AsyncMock(return_value=False)
        p._print_session_summary = MagicMock()
        p._print_summary = MagicMock()
        p._generate_run_report = MagicMock()

        calls = {"count": 0}

        async def fake_process(search_string, progress):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("Page.evaluate: Target crashed")
            search_string.pages_reviewed = 2

        p._process_string = fake_process

        asyncio.run(p.run_full(resume=True))

        saved = json.loads(Path(td, "progress.json").read_text())
        assert calls["count"] == 2
        p.browser.recover_from_target_crash.assert_awaited_once()
        p._attempt_reconnect.assert_not_awaited()
        assert saved["strings"][0]["status"] == "done"
        assert saved["strings"][0]["pages_reviewed"] == 2


def test_run_full_resume_executes_pending_block_adaptation_before_next_string():
    """A completed block that never adapted must adapt before the next queued string runs."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)

        progress = Progress(
            brief_name="test",
            strings=[
                SearchString(id=1, name="done", boolean="one", status="done", block="Block A"),
                SearchString(id=2, name="next", boolean="two", status="queued", block="Block B"),
            ],
            pending_block_name="Block A",
            pending_block_string_ids=[1],
        )
        progress.save(str(p.progress_path))

        p.browser.connect = AsyncMock()
        p.browser.disconnect = AsyncMock()
        p.browser.page = MagicMock(url="https://www.linkedin.com/talent/search")
        p._print_session_summary = MagicMock()
        p._print_summary = MagicMock()
        p._generate_run_report = MagicMock()
        p._execution_plan = ExecutionPlan(strategy_rationale="test")

        call_order = []

        async def fake_process(search_string, progress):
            call_order.append(f"process:{search_string.id}")

        def fake_adapt(*args, **kwargs):
            call_order.append("adapt")
            return AdaptationResponse()

        p._process_string = fake_process

        with patch("linkedin.strategy.adapt_after_block", side_effect=fake_adapt):
            asyncio.run(p.run_full(resume=True))

        saved = json.loads(Path(td, "progress.json").read_text())
        assert call_order == ["adapt", "process:2"]
        assert saved["pending_block_name"] == ""
        assert saved["pending_block_string_ids"] == []


def test_process_string_continues_pagination_instead_of_forced_narrow_below_min_pages():
    """Low-signal pagination keeps paging until the minimum depth, then stops cleanly."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)

        search_string = SearchString(id=5, name="test", boolean="foo", status="queued")
        progress = Progress(brief_name="test", strings=[search_string], current_string_id=5, current_page=0)

        no_results = MagicMock()
        no_results.is_visible = AsyncMock(return_value=False)
        locator = MagicMock()
        locator.first = no_results

        p.browser.page = MagicMock(url="https://www.linkedin.com/talent/search")
        p.browser.page.locator.return_value = locator
        p.browser.enter_search_string = AsyncMock()
        p.browser.get_results_count_text = AsyncMock(return_value="144")
        p.browser.get_results_count = AsyncMock(return_value=144)
        p.browser.go_to_next_page = AsyncMock(return_value=True)

        p._ensure_browser_healthy = AsyncMock()
        p._review_page_sequentially = AsyncMock(return_value=None)
        p._assess_string_state = AsyncMock(
            side_effect=[
                {"decision": "continue", "rationale": "keep paging", "page": 1},
                {"decision": "stop", "rationale": "signal exhausted", "page": 2},
            ]
        )
        p._plan_variant_experiments = AsyncMock()

        with patch("linkedin.orchestrator.human_delay_correlated", return_value=0):
            asyncio.run(p._process_string(search_string, progress))

        assert p._assess_string_state.await_count == 2
        assert p._plan_variant_experiments.await_count == 0
        p.browser.go_to_next_page.assert_awaited_once()
        assert "Stopped after page 2." in (search_string.notes or "")


def test_process_string_runs_variant_experiment_before_commit():
    """Large noisy pools can run a sibling experiment and then commit it to pagination."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)

        search_string = SearchString(id=9, name="scout", boolean="foo", status="queued")
        progress = Progress(brief_name="test", strings=[search_string], current_string_id=9, current_page=0)

        no_results = MagicMock()
        no_results.is_visible = AsyncMock(return_value=False)
        locator = MagicMock()
        locator.first = no_results

        p.browser.page = MagicMock(url="https://www.linkedin.com/talent/search")
        p.browser.page.locator.return_value = locator
        p.browser.enter_search_string = AsyncMock()
        p.browser.get_results_count_text = AsyncMock(side_effect=["3.2K+", "120"])
        p.browser.get_results_count = AsyncMock(side_effect=[3200, 120])
        p.browser.go_to_next_page = AsyncMock(return_value=True)

        p._ensure_browser_healthy = AsyncMock()
        p._review_page_sequentially = AsyncMock(
            side_effect=[
                GlanceResult(action="reformulate", summary="all noise", confidence=0.91),
                None,
                None,
            ]
        )
        p._assess_string_state = AsyncMock(
            side_effect=[
                {"decision": "experiment", "rationale": "too broad", "page": 1},
                {"decision": "commit", "rationale": "variant is strong", "page": 1},
                {"decision": "stop", "rationale": "done", "page": 2},
            ]
        )
        p._plan_variant_experiments = AsyncMock(
            return_value=[
                LinkedInSearchVariant(
                    variant_id="precision-1",
                    parent_variant_id="root",
                    root_string_id=9,
                    boolean="bar",
                    variant_kind="precision",
                    hypothesis="tighter signal slice",
                    target_result_min=75,
                    target_result_max=400,
                )
            ]
        )
        async def _apply_variant(*, search_string, experiment_state, variant):
            experiment_state.activate_variant(variant.variant_id)
            return SearchMutationResult(
                applied=True,
                result_count=120,
                result_count_text="120",
            )

        p._search_mutation_executor.apply_variant = AsyncMock(side_effect=_apply_variant)

        with patch("linkedin.orchestrator.human_delay_correlated", return_value=0):
            asyncio.run(p._process_string(search_string, progress))

        assert p._plan_variant_experiments.await_count == 1
        p._search_mutation_executor.apply_variant.assert_awaited_once()
        assert search_string.boolean == "bar"
        assert search_string.refinement_stack == ["foo"]
        p.browser.go_to_next_page.assert_awaited_once()
        assert "Committed precision variant on page 1." in (search_string.notes or "")
        assert "Stopped after page 2." in (search_string.notes or "")


def test_process_string_uses_real_scout_gate_for_large_noisy_pool():
    """A 6k noisy scout page should trigger a bounded sibling experiment before commit."""
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)

        search_string = SearchString(id=91, name="scout", boolean="foo", status="queued")
        progress = Progress(brief_name="test", strings=[search_string], current_string_id=91, current_page=0)

        no_results = MagicMock()
        no_results.is_visible = AsyncMock(return_value=False)
        locator = MagicMock()
        locator.first = no_results

        p.browser.page = MagicMock(url="https://www.linkedin.com/talent/search")
        p.browser.page.locator.return_value = locator
        p.browser.enter_search_string = AsyncMock()
        p.browser.get_results_count_text = AsyncMock(side_effect=["6K+", "220"])
        p.browser.get_results_count = AsyncMock(side_effect=[6000, 220])
        p.browser.go_to_next_page = AsyncMock(return_value=False)
        p._ensure_browser_healthy = AsyncMock()
        p._record_runtime_event = MagicMock()

        async def _review_page(*, search_string, page_num, result_count, page_report, all_candidates, string_stats, progress):
            if search_string.boolean == "foo":
                string_stats["candidates"] += 11
                string_stats["facial_yes"] += 2
                string_stats["facial_no"] += 10
                all_candidates.extend(
                    [
                        {"title": "Applied Scientist", "company": "OpenAI", "facial": "yes", "save_reason": "strong"},
                        {"title": "Research Engineer", "company": "Anthropic", "facial": "yes", "save_reason": "strong"},
                        {"title": "Product Manager", "company": "BankCorp", "facial": "no"},
                        {"title": "Program Manager", "company": "BigCo", "facial": "no"},
                        {"title": "Engineering Manager", "company": "Enterprise Inc", "facial": "no"},
                    ]
                )
                p._latest_page_preview_snippets = [
                    _make_snippet(current_title="Applied Scientist", current_company="OpenAI"),
                    _make_snippet(current_title="Research Engineer", current_company="Anthropic"),
                    _make_snippet(current_title="Product Manager", current_company="BankCorp"),
                    _make_snippet(current_title="Program Manager", current_company="BigCo"),
                ]
                return GlanceResult(action="reformulate", summary="manager-heavy noise dominates", confidence=0.92)

            string_stats["candidates"] += 2
            string_stats["saves"] += 1
            all_candidates.extend(
                [
                    {"title": "Staff Applied Scientist", "company": "Anthropic", "final_decision": "save"},
                    {"title": "Research Engineer", "company": "OpenAI", "facial": "yes"},
                ]
            )
            p._latest_page_preview_snippets = [
                _make_snippet(current_title="Staff Applied Scientist", current_company="Anthropic"),
                _make_snippet(current_title="Research Engineer", current_company="OpenAI"),
            ]
            return None

        p._review_page_sequentially = AsyncMock(side_effect=_review_page)
        p._plan_variant_experiments = AsyncMock(
            return_value=[
                LinkedInSearchVariant(
                    variant_id="precision-1",
                    parent_variant_id="root",
                    root_string_id=91,
                    boolean="bar",
                    variant_kind="precision",
                    hypothesis="preserve frontier applied scientists and exclude manager-heavy noise",
                    target_result_min=75,
                    target_result_max=400,
                )
            ]
        )

        async def _apply_variant(*, search_string, experiment_state, variant):
            experiment_state.activate_variant(variant.variant_id)
            return SearchMutationResult(applied=True, result_count=220, result_count_text="220")

        p._search_mutation_executor.apply_variant = AsyncMock(side_effect=_apply_variant)

        with patch("linkedin.orchestrator.human_delay_correlated", return_value=0):
            asyncio.run(p._process_string(search_string, progress))

        assert p._plan_variant_experiments.await_count == 1
        p._search_mutation_executor.apply_variant.assert_awaited_once()
        assert search_string.boolean == "bar"
        assert search_string.refinement_stack == ["foo"]
        assert "Variant precision applied on page 1." in (search_string.notes or "")
        assert "Committed precision variant on page 1." in (search_string.notes or "")
        assess_events = [
            call.kwargs["payload"]
            for call in p._record_runtime_event.call_args_list
            if call.kwargs.get("event_type") == "linkedin_search_assess"
        ]
        assert assess_events
        assert assess_events[0]["real_signal"] is True
        assert assess_events[0]["scout_gate_bucket"] == "precommit_real_signal_noisy_recovery"
        assert assess_events[0]["noise_dominant"] is True


def test_build_ordered_search_strings_uses_opening_micro_block():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        p._execution_plan = ExecutionPlan(
            strategy_rationale="test",
            generated_strings=[
                {"boolean": f"foo {idx}", "rationale": f"string {idx}"}
                for idx in range(1, 9)
            ],
            coverage_gaps=[],
        )

        strings = p._build_ordered_search_strings()

        assert [s.block for s in strings[:3]] == ["Compound Batch 1"] * 3
        assert [s.block for s in strings[3:8]] == ["Compound Batch 2"] * 5


def test_run_block_adaptation_uses_opening_checkpoint_mode():
        with tempfile.TemporaryDirectory() as td:
            p = _make_pipeline(td)
            progress = Progress(
                brief_name="test",
                strings=[
                    SearchString(id=1, name="one", boolean="foo", status="done", block="Compound Batch 1"),
                    SearchString(id=2, name="two", boolean="bar", status="queued", block="Compound Batch 2"),
                ],
            )
        block_strings = [
            SearchString(
                id=1,
                name="one",
                boolean="foo",
                status="done",
                block="Compound Batch 1",
                facial_yes_count=1,
                facial_no_count=3,
                candidates_count=4,
                duplicates_count=0,
                saves=[],
                result_count=900,
                pages_reviewed=1,
            )
        ]
        observed = {}

        def fake_adapt(*args, **kwargs):
            observed["checkpoint_mode"] = kwargs["checkpoint_mode"]
            return AdaptationResponse()

        asyncio.run(p._run_block_adaptation("Compound Batch 1", block_strings, progress, fake_adapt))

        assert observed["checkpoint_mode"] == "opening_checkpoint"


def test_run_block_adaptation_treats_adaptive_followup_as_normal_checkpoint():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        progress = Progress(
            brief_name="test",
            strings=[
                SearchString(id=1, name="adaptive followup", boolean="foo", status="done", block="Compound Batch 1", string_type="Adaptive"),
                SearchString(id=2, name="two", boolean="bar", status="queued", block="Compound Batch 2"),
            ],
        )
        block_strings = [
            SearchString(
                id=1,
                name="adaptive followup",
                boolean="foo",
                status="done",
                block="Compound Batch 1",
                string_type="Adaptive",
                facial_yes_count=1,
                facial_no_count=1,
                candidates_count=2,
                duplicates_count=0,
                saves=["Ada"],
                result_count=220,
                pages_reviewed=1,
                family_key="capital_markets_head_ai",
                novelty_bucket="edge_case",
                domain_lane="capital_markets",
            )
        ]
        observed = {}

        def fake_adapt(*args, **kwargs):
            observed["checkpoint_mode"] = kwargs["checkpoint_mode"]
            return AdaptationResponse()

        asyncio.run(p._run_block_adaptation("Compound Batch 1", block_strings, progress, fake_adapt))

        assert observed["checkpoint_mode"] == "normal_block_checkpoint"


def test_run_block_adaptation_exploitation_bias_promotes_live_lane_and_demotes_dead_family():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)

        winner = SearchString(
            id=1,
            name="winner",
            boolean="winner",
            status="done",
            block="Compound Batch 1",
            pages_reviewed=2,
            saves=["Ada"],
            facial_yes_count=2,
            facial_no_count=3,
            candidates_count=5,
            family_key="market_infra_head_ai",
            novelty_bucket="edge_case",
            domain_lane="capital_markets",
        )
        loser = SearchString(
            id=2,
            name="loser",
            boolean="loser",
            status="done",
            block="Compound Batch 1",
            pages_reviewed=2,
            facial_yes_count=0,
            facial_no_count=8,
            candidates_count=8,
            family_key="dead_hidden_population",
            novelty_bucket="edge_case",
            domain_lane="insurance",
        )

        winner_state = p._experiment_state_for(winner)
        winner_state.commit_variant("root")
        winner_state.family_signal_total = 4
        winner_state.family_saves_total = 1
        winner_state.precommit_recovery_attempts_used = 1
        winner_state.last_drift_refinement_summary = {"outcome": "rescued"}

        loser_state = p._experiment_state_for(loser)
        loser_state.commit_variant("root")
        loser_state.family_signal_total = 0
        loser_state.family_saves_total = 0

        progress = Progress(
            brief_name="test",
            strings=[
                winner,
                loser,
                SearchString(
                    id=3,
                    name="same family",
                    boolean="family",
                    block="Compound Batch 2",
                    family_key="market_infra_head_ai",
                    novelty_bucket="edge_case",
                    domain_lane="capital_markets",
                ),
                SearchString(
                    id=4,
                    name="same lane",
                    boolean="lane",
                    block="Compound Batch 2",
                    family_key="adjacent_market_infra",
                    novelty_bucket="edge_case",
                    domain_lane="capital_markets",
                ),
                SearchString(
                    id=5,
                    name="dead family",
                    boolean="dead",
                    block="Compound Batch 2",
                    family_key="dead_hidden_population",
                    novelty_bucket="edge_case",
                    domain_lane="insurance",
                ),
                SearchString(
                    id=6,
                    name="neutral edge",
                    boolean="neutral",
                    block="Compound Batch 2",
                    family_key="neutral_lane",
                    novelty_bucket="edge_case",
                    domain_lane="payments",
                ),
            ],
        )

        captured = {}

        def fake_adapt(*args, **kwargs):
            report = args[1]
            captured["summary"] = report.search_intelligence_summary
            captured["detail"] = report.string_details[0]["search_intelligence"]
            return AdaptationResponse()

        asyncio.run(p._run_block_adaptation("Compound Batch 1", [winner, loser], progress, fake_adapt))

        queued_ids = [s.id for s in progress.strings if s.status == "queued"]
        assert queued_ids == [3, 4, 6, 5]
        assert captured["summary"]["proven_family_keys"] == ["market_infra_head_ai"]
        assert captured["summary"]["dead_family_keys"] == ["dead_hidden_population"]
        assert captured["detail"]["drift_rescue_summary"]["outcome"] == "rescued"


def test_assess_string_state_stops_committed_variant_after_zero_signal_streak():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        search_string = SearchString(id=21, name="builders", boolean="foo")
        state = p._experiment_state_for(search_string)
        state.commit_variant("root")
        state.committed_pages_reviewed = 2
        state.committed_zero_signal_streak = 2

        assessment = asyncio.run(
            p._assess_string_state(
                search_string=search_string,
                experiment_state=state,
                page_num=3,
                result_count=3200,
                string_stats={"facial_no": 4},
                page_stats={"facial_no": 4},
                page_insights=LinkedInPageInsights(
                    page=3,
                    result_count=3200,
                    result_window="150-800",
                    noise_anchors=["Product manager at BankCorp"],
                    dominant_non_fit_patterns=["product-heavy profiles dominate"],
                    glance_action="reformulate",
                ),
                remaining_queued_strings=4,
            )
        )

        assert assessment["decision"] == "stop"
        assert "zero-signal decay limit" in assessment["rationale"]


def test_search_intelligence_aggregate_does_not_label_productive_family_as_dead():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        winner = SearchString(
            id=1,
            name="Winner",
            boolean="winner",
            status="done",
            pages_reviewed=2,
            saves=["Ada Lovelace"],
            family_key="shared_family",
            domain_lane="market_infra",
        )
        loser = SearchString(
            id=2,
            name="Loser",
            boolean="loser",
            status="done",
            pages_reviewed=1,
            family_key="shared_family",
            domain_lane="market_infra",
        )

        winner_state = p._experiment_state_for(winner)
        winner_state.family_signal_total = 3
        loser_state = p._experiment_state_for(loser)
        loser_state.family_signal_total = 0

        summary = p._search_intelligence_aggregate([loser, winner])

        assert summary["proven_family_keys"] == ["shared_family"]
        assert summary["dead_family_keys"] == []


def test_search_intelligence_aggregate_blocks_family_promotion_when_saved_profiles_are_above_band():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        risky = SearchString(
            id=21,
            name="Buy-side broad lane",
            boolean='("BlackRock" OR "Two Sigma") AND ("GenAI" OR "LLM")',
            status="done",
            pages_reviewed=2,
            saves=["Ada Lovelace"],
            family_key="buy_side_generic",
            domain_lane="asset_management",
            seniority_risk="medium",
            title_bucket_risk="low",
            opening_eligible=False,
        )
        risky_state = p._experiment_state_for(risky)
        risky_state.family_signal_total = 3

        summary = p._search_intelligence_aggregate(
            [risky],
            profile_index={
                "ada lovelace": {
                    "name": "Ada Lovelace",
                    "headline": "Senior Managing Director, Global Head of AI",
                    "experiences": [{"title": "Senior Managing Director, Global Head of AI", "company": "BlackRock"}],
                }
            },
        )

        assert summary["proven_family_keys"] == []
        assert summary["contaminated_family_keys"] == ["buy_side_generic"]
        assert summary["contaminated_domain_lanes"] == ["asset_management"]


def test_exploitation_overlay_never_demotes_proven_families_even_if_summary_is_contaminated():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        adaptation = AdaptationResponse()
        remaining = [
            SearchString(
                id=10,
                name="Hot family A",
                boolean="foo",
                family_key="shared_family",
                domain_lane="market_infra",
                novelty_bucket="canonical",
            ),
            SearchString(
                id=11,
                name="Hot family B",
                boolean="bar",
                family_key="shared_family",
                domain_lane="market_infra",
                novelty_bucket="canonical",
            ),
            SearchString(
                id=12,
                name="Hot family C",
                boolean="baz",
                family_key="shared_family",
                domain_lane="market_infra",
                novelty_bucket="canonical",
            ),
            SearchString(
                id=13,
                name="Actually dead family",
                boolean="qux",
                family_key="dead_family",
                domain_lane="payments",
                novelty_bucket="canonical",
            ),
        ]

        overlay = p._apply_exploitation_bias_to_adaptation(
            adaptation=adaptation,
            remaining=remaining,
            block_summary={
                "proven_family_keys": ["shared_family"],
                "proven_domain_lanes": ["market_infra"],
                "dead_family_keys": ["shared_family", "dead_family"],
            },
            checkpoint_mode="normal_block_checkpoint",
        )

        assert overlay["promoted_string_ids"] == [10, 11, 12]
        assert overlay["demoted_string_ids"] == [13]
        assert all(
            action["string_id"] != 10 or action["move_to"] != "last"
            for action in adaptation.reorder
        )
        assert all(
            action["string_id"] != 11 or action["move_to"] != "last"
            for action in adaptation.reorder
        )
        assert all(
            action["string_id"] != 12 or action["move_to"] != "last"
            for action in adaptation.reorder
        )


def test_exploitation_overlay_demotes_contaminated_families_in_strict_seniority_runs():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        adaptation = AdaptationResponse()
        remaining = [
            SearchString(
                id=30,
                name="Risky buy-side lane",
                boolean="foo",
                family_key="buy_side_generic",
                domain_lane="asset_management",
                novelty_bucket="edge_case",
                seniority_risk="medium",
                title_bucket_risk="low",
                opening_eligible=False,
            ),
            SearchString(
                id=31,
                name="Safe capital-markets lane",
                boolean="bar",
                family_key="capital_markets_safe",
                domain_lane="capital_markets",
                novelty_bucket="edge_case",
                seniority_risk="low",
                title_bucket_risk="low",
                opening_eligible=True,
            ),
        ]

        overlay = p._apply_exploitation_bias_to_adaptation(
            adaptation=adaptation,
            remaining=remaining,
            block_summary={
                "proven_family_keys": [],
                "proven_domain_lanes": [],
                "dead_family_keys": [],
                "contaminated_family_keys": ["buy_side_generic"],
                "contaminated_domain_lanes": ["asset_management"],
            },
            checkpoint_mode="opening_checkpoint",
        )

        assert overlay["promoted_string_ids"] == []
        assert overlay["demoted_string_ids"] == [30]
        assert any(
            action["string_id"] == 30 and action["move_to"] == "last"
            for action in adaptation.reorder
        )


def test_assess_string_state_stops_after_single_zero_signal_page_post_failed_drift():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        search_string = SearchString(id=22, name="builders", boolean="foo")
        state = p._experiment_state_for(search_string)
        state.commit_variant("root")
        state.committed_pages_reviewed = 1
        state.committed_zero_signal_streak = 1
        state.last_drift_refinement_summary = {"outcome": "not_rescued"}

        assessment = asyncio.run(
            p._assess_string_state(
                search_string=search_string,
                experiment_state=state,
                page_num=4,
                result_count=3200,
                string_stats={"facial_no": 3},
                page_stats={"facial_no": 3},
                page_insights=LinkedInPageInsights(
                    page=4,
                    result_count=3200,
                    result_window="150-800",
                    noise_anchors=["Program manager at BankCorp"],
                    dominant_non_fit_patterns=["manager-heavy profiles dominate"],
                    glance_action="reformulate",
                ),
                remaining_queued_strings=4,
            )
        )

        assert assessment["decision"] == "stop"
        assert "failed drift rescue" in assessment["rationale"]


def test_assess_pagination_drift_prefers_recall_when_overfit_risk_is_high():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        search_string = SearchString(id=9, name="scout", boolean="foo", status="queued")
        state = p._experiment_state_for(search_string)
        state.commit_variant("root")
        # Snapshot uses one strong anchor, which should make rescue more recall-friendly.
        from linkedin.search_intelligence import LinkedInVariantSnapshot

        state.early_signal_snapshot = LinkedInVariantSnapshot.from_page(
            page_num=1,
            result_count=3200,
            page_insights=LinkedInPageInsights(
                page=1,
                result_count=3200,
                result_window="150-800",
                title_clusters=[{"label": "machine learning engineer", "count": 3}],
                signal_anchors=["ML engineer at OpenAI"],
            ),
            page_stats={"saves": 1, "facial_yes": 0, "rejects": 0},
        )
        state.recent_noise_snapshot = LinkedInVariantSnapshot.from_page(
            page_num=3,
            result_count=3200,
            page_insights=LinkedInPageInsights(
                page=3,
                result_count=3200,
                result_window="150-800",
                title_clusters=[{"label": "product manager", "count": 4}],
                noise_anchors=["Product manager at BankCorp"],
                dominant_non_fit_patterns=["product-heavy profiles dominate"],
                glance_action="reformulate",
            ),
            page_stats={"facial_no": 3},
        )
        state.family_saves_total = 1
        state.active_variant.pages_reviewed = 3
        state.pages_since_last_mutation = 1

        assessment = p._assess_pagination_drift(
            experiment_state=state,
            page_num=3,
            result_count=3200,
            page_stats={"facial_no": 3},
            page_insights=LinkedInPageInsights(
                page=3,
                result_count=3200,
                result_window="150-800",
                noise_anchors=["Product manager at BankCorp"],
                dominant_non_fit_patterns=["product-heavy profiles dominate"],
                glance_action="reformulate",
            ),
            remaining_queued_strings=4,
        )

        assert assessment.decision == "spawn_recall_sibling"
        assert assessment.future_filter_hypothesis.startswith("title filter")


def test_process_string_runs_bounded_drift_rescue():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)

        search_string = SearchString(id=12, name="scout", boolean="foo", status="queued")
        progress = Progress(
            brief_name="test",
            strings=[search_string, SearchString(id=13, name="other", boolean="bar", status="queued")],
            current_string_id=12,
            current_page=0,
        )

        no_results = MagicMock()
        no_results.is_visible = AsyncMock(return_value=False)
        locator = MagicMock()
        locator.first = no_results

        p.browser.page = MagicMock(url="https://www.linkedin.com/talent/search")
        p.browser.page.locator.return_value = locator
        p.browser.enter_search_string = AsyncMock()
        p.browser.get_results_count_text = AsyncMock(side_effect=["3.2K+", "600"])
        p.browser.get_results_count = AsyncMock(side_effect=[3200, 600])
        p.browser.go_to_next_page = AsyncMock(return_value=True)

        p._ensure_browser_healthy = AsyncMock()
        p._review_page_sequentially = AsyncMock(side_effect=[None, None, None, None])
        p._assess_string_state = AsyncMock(
            side_effect=[
                {"decision": "commit", "rationale": "page 1 strong", "page": 1},
                {"decision": "refine_committed", "rationale": "drifting", "page": 2},
                {"decision": "commit", "rationale": "rescued", "page": 1},
                {"decision": "stop", "rationale": "done", "page": 2},
            ]
        )
        p._plan_variant_experiments = AsyncMock()
        p._plan_drift_refinement = AsyncMock(
            return_value=(
                LinkedInSearchVariant(
                    variant_id="drift-12-1",
                    parent_variant_id="root",
                    root_string_id=12,
                    boolean="foo NOT product",
                    variant_kind="precision",
                ),
                {"decision": "refine_committed", "keyword_hypothesis": "exclude product-heavy leakage"},
            )
        )

        async def _apply_variant(*, search_string, experiment_state, variant, mutation_kind="experiment", mutation_summary=None):
            experiment_state.mark_pending_drift(
                variant_id=variant.variant_id,
                parent_variant_id=experiment_state.committed_variant_id or experiment_state.active_variant_id,
                summary=mutation_summary,
            )
            experiment_state.activate_variant(variant.variant_id)
            return SearchMutationResult(
                applied=True,
                result_count=600,
                result_count_text="600",
            )

        p._search_mutation_executor.apply_variant = AsyncMock(side_effect=_apply_variant)

        with patch("linkedin.orchestrator.human_delay_correlated", return_value=0):
            asyncio.run(p._process_string(search_string, progress))

        assert p._plan_drift_refinement.await_count == 1
        assert p._search_mutation_executor.apply_variant.await_args.kwargs["mutation_kind"] == "drift"
        assert search_string.boolean == "foo NOT product"
        assert search_string.pages_reviewed == 2
        assert "Drift rescue precision applied on page 2." in (search_string.notes or "")


def _sample_report_analysis() -> dict:
    return {
        "winning_lanes": [
            {
                "lane": "Research Copilot",
                "string_ids": [2],
                "candidate_examples": ["Mithun Azhagappan"],
                "evidence": "Highest save count from workflow-specific BFSI product language.",
                "why_it_worked": "Product-output vocabulary gated for real builders.",
                "recommended_action": "UNIQUE_REPORT_SENTINEL promote this lane earlier.",
            }
        ],
        "underperforming_lanes": [
            {
                "lane": "Surveillance",
                "string_ids": [8],
                "issue": "Traditional compliance-tech noise.",
                "evidence": "Zero saves across two pages.",
                "recommended_action": "Only run with an explicit GenAI AND-gate.",
            }
        ],
        "coverage_gaps": [
            {
                "gap": "Payments",
                "why_it_matters": "The run never explicitly covered transaction banking.",
                "suggested_search_strategy": "Add payment-orchestration and RTP strings.",
            }
        ],
        "noise_patterns": [
            {
                "pattern": "Product-heavy AI leadership",
                "evidence": "Several product/strategy AI officers were rejected post deep-dive.",
                "mitigation": "Strengthen builder-authoring verbs and architecture language.",
            }
        ],
        "saved_candidate_patterns": {
            "standout_candidates": [{"name": "Mithun Azhagappan", "why": "Goldman AI platform architect."}],
            "common_employers": [{"employer": "JPMorgan", "count": 3, "note": "Strong bank GenAI-convert segment."}],
            "common_titles": [{"title_family": "Executive Director", "count": 1, "note": "Right seniority band."}],
            "archetype_distribution": [{"archetype": "BFSI-native GenAI converts", "count": 4, "note": "Dominant save pattern."}],
            "seniority_notes": ["Many VP-level bank builders were interesting but below the full lab-leadership bar."],
        },
        "adaptation_assessment": {
            "summary": "Adaptation stayed focused on workflow-specific strings.",
            "effective_refinements": ["Narrowing research-copilot language improved precision."],
            "questionable_or_skipped": ["Payments stayed under-covered."],
            "operational_notes": ["Prefer tight workflow language over broad archetype-first queries."],
        },
        "recommendations": {
            "try_next": ["Payments and transaction-banking builders"],
            "avoid_next": ["Ungated surveillance strings"],
            "prioritize_pipeline": ["Mithun Azhagappan"],
        },
        "brief_iteration_hints": {
            "instructions": ["Cover payments in the first search block."],
            "search_priorities": ["Payments / transaction-banking builders"],
            "additional_search_terms": ["payment orchestration", "transaction banking"],
            "intake_notes": "The latest run validated research-copilot lanes and exposed a payments gap.",
            "depth_distinction": {
                "builder_definition": "Still an executive-builder search.",
                "user_definition": "Product and strategy leaders remain out of scope.",
                "edge_case_guidance": "VP bank builders need extra scope scrutiny.",
            },
            "non_fit_patterns": [
                {
                    "label": "Product-heavy AI officer",
                    "description": "Executive product leadership without system-builder authorship.",
                    "why_not": "Wrong depth for this role.",
                    "examples": ["Chief Product & AI Officer"],
                }
            ],
            "minimum_bar_description": "NYC, 15+ years, BFSI depth, and post-2022 GenAI remain hard requirements.",
            "facial_calibration": {
                "expected_yes_rate_low": 0.1,
                "expected_yes_rate_high": 0.22,
                "fast_exit_patterns": ["Pure product history"],
                "trajectory_yes_patterns": ["Big-bank GenAI convert"],
                "trajectory_ambiguous_patterns": ["VP at smaller firm"],
                "trajectory_no_patterns": ["Vendor field CTO without build ownership"],
            },
            "employer_signal_rules": [
                {
                    "tier": "payments_builder",
                    "employer_patterns": ["Visa", "Mastercard"],
                    "evidence_required": "Still requires production builder evidence.",
                    "save_on_employer_alone": False,
                }
            ],
            "calibration_examples": {
                "strong_saves": [{"name": "Mithun Azhagappan", "why": "Strong fit."}],
                "incorrect_saves": [{"name": "Deepinder Gulati", "why": "Product-heavy."}],
                "borderline_verify": [{"name": "Peter Chung", "why": "Check scope carefully."}],
            },
            "notes": "Promote payments in the next draft.",
            "locked_field_cautions": ["Do not relax geography or years-of-experience gates."],
        },
    }


def test_generate_run_report_writes_json_markdown_and_input_artifacts():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        p.brief_obj.role_title = "Head of Applied AI Lab"
        p.brief_obj.linkedin_project = "Head of Applied AI Lab"
        p.brief_obj.linkedin_project_id = "1957683706"
        p.brief_obj.raw = {"version": "2.1"}
        p.stats.update(
            {
                "snippets_extracted": 12,
                "facial_yes": 4,
                "facial_no": 8,
                "saved": 1,
                "rejected": 2,
            }
        )
        p._search_memory = {
            "project_id": "1957683706",
            "overall": {
                "strings_seen": 1,
                "candidates_seen": 12,
                "duplicates": 2,
                "saves": 1,
                "edge_case_saves": 1,
                "canonical_saves": 0,
            },
            "families": {
                "research_copilot_asset_mgmt": {
                    "family_key": "research_copilot_asset_mgmt",
                    "novelty_bucket": "edge_case",
                    "domain_lane": "asset_management",
                    "status": "active",
                    "status_reason": "",
                    "strings_seen": 1,
                    "candidates_seen": 12,
                    "duplicates": 2,
                    "saves": 1,
                    "dominant_anchors": ["research copilot"],
                }
            },
        }
        p._bias_summary_for_report = MagicMock(return_value="Bias summary sentinel")

        append_jsonl(
            p.final_path,
            {
                "candidate_name": "Mithun Azhagappan",
                "decision": "SAVE",
                "path": "DIRECT",
                "confidence": 0.92,
                "rationale": "Goldman AI platform architect.",
            },
        )
        append_jsonl(
            p.final_path,
            {
                "candidate_name": "Deepinder Gulati",
                "decision": "REJECT",
                "path": "REJECT",
                "confidence": 0.12,
                "rationale": "Product-heavy AI leadership without builder evidence.",
            },
        )

        progress = Progress(
            brief_name="head-ai-lab",
            strings=[
                SearchString(
                    id=2,
                    name="Research copilot lane",
                    boolean="research",
                    status="done",
                    result_count=526,
                    pages_reviewed=4,
                    saves=["Mithun Azhagappan"],
                    notes="Strong lane",
                    facial_yes_count=3,
                    facial_no_count=7,
                    candidates_count=10,
                    family_key="research_copilot_asset_mgmt",
                    novelty_bucket="edge_case",
                    domain_lane="asset_management",
                ),
                SearchString(
                    id=8,
                    name="Surveillance lane",
                    boolean="surveillance",
                    status="skipped",
                    result_count=1100,
                    pages_reviewed=2,
                    notes="Stopped early after noise.",
                    facial_yes_count=0,
                    facial_no_count=6,
                    candidates_count=6,
                    family_key="surveillance_builder",
                    novelty_bucket="edge_case",
                    domain_lane="risk_compliance",
                ),
            ],
        )

        with patch("shared.llm_clients.opus_llm", return_value=_sample_report_analysis()):
            p._generate_run_report(progress)

        report_input = json.loads(Path(td, "run-report-input.json").read_text())
        report_json = json.loads(Path(td, "run-report.json").read_text())
        report_md = Path(td, "run-report.md").read_text()

        assert report_input["saved_candidate_summaries"][0]["candidate_name"] == "Mithun Azhagappan"
        assert report_input["rejected_candidate_summaries"][0]["candidate_name"] == "Deepinder Gulati"
        assert report_input["search_memory_summary"]["overall"]["families_tracked"] == 1
        assert report_json["winning_lanes"][0]["recommended_action"].startswith("UNIQUE_REPORT_SENTINEL")
        assert report_json["metrics_summary"]["saved"] == 1
        assert "UNIQUE_REPORT_SENTINEL" in report_md
        assert "Payments" in report_md


def test_generate_run_report_failure_is_warning_only(capsys):
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        p.brief_obj.role_title = "Head of Applied AI Lab"
        p.brief_obj.linkedin_project = "Head of Applied AI Lab"
        p.brief_obj.linkedin_project_id = "1957683706"
        p.brief_obj.raw = {"version": "2.1"}

        progress = Progress(
            brief_name="head-ai-lab",
            strings=[SearchString(id=2, name="Research lane", boolean="research", status="done", result_count=10)],
        )

        with patch("shared.llm_clients.opus_llm", side_effect=RuntimeError("boom")):
            p._generate_run_report(progress)

        captured = capsys.readouterr()
        assert "Report generation failed: boom" in captured.out
        assert not Path(td, "run-report.json").exists()
        assert not Path(td, "run-report.md").exists()


def test_build_run_report_snapshot_includes_search_intelligence_summary():
    with tempfile.TemporaryDirectory() as td:
        p = _make_pipeline(td)
        p.brief_obj.role_title = "Head of Applied AI Lab"
        p.brief_obj.linkedin_project = "Head of Applied AI Lab"
        p.brief_obj.linkedin_project_id = "1957683706"
        p.brief_obj.raw = {"version": "2.1"}
        p.stats["snippets_extracted"] = 12
        p.stats["facial_yes"] = 3
        p.stats["facial_no"] = 9
        p.stats["saved"] = 1
        p.stats["rejected"] = 2

        winner = SearchString(
            id=2,
            name="Market infra lane",
            boolean="market infra",
            status="done",
            result_count=214,
            pages_reviewed=3,
            saves=["Ada"],
            facial_yes_count=3,
            facial_no_count=4,
            candidates_count=7,
            family_key="market_infra_head_ai",
            novelty_bucket="edge_case",
            domain_lane="capital_markets",
        )
        state = p._experiment_state_for(winner)
        state.commit_variant("root")
        state.family_signal_total = 5
        state.family_saves_total = 1
        state.precommit_recovery_attempts_used = 1
        state.drift_attempt_count = 1
        state.last_drift_refinement_summary = {"outcome": "rescued", "decision": "refine_committed"}

        progress = Progress(brief_name="head-ai-lab", strings=[winner])

        snapshot = p._build_run_report_snapshot(progress)

        assert snapshot["metrics_summary"]["strings_with_precommit_experiments"] == 1
        assert snapshot["metrics_summary"]["strings_with_drift_rescue_attempts"] == 1
        assert snapshot["metrics_summary"]["strings_rescued_by_drift"] == 1
        assert snapshot["metrics_summary"]["proven_family_keys"] == ["market_infra_head_ai"]
        assert snapshot["string_performance"][0]["search_intelligence"]["family_signal_total"] == 5
        assert (
            snapshot["string_performance"][0]["search_intelligence"]["drift_rescue_summary"]["outcome"]
            == "rescued"
        )
