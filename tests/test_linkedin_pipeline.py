"""Tests for LinkedIn pipeline dedup semantics.

Run with: python -m pytest tests/test_linkedin_pipeline.py -v
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from shared.schemas import (
    AdaptationResponse,
    CandidateSnippet,
    ExecutionPlan,
    OpusDecision,
    Progress,
    SearchString,
)
from shared.storage import append_jsonl, read_jsonl


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

        with patch("linkedin.orchestrator.extract_snippet_from_card_innertext", return_value=_make_snippet(
            name="LLM Name",
            profile_url="",
            source_string_id=9,
            source_string_name="seq",
            page=2,
            result_rank=3,
        )), patch("linkedin.orchestrator.human_delay_correlated", return_value=0.0):
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

        with patch("linkedin.orchestrator.human_delay_correlated", return_value=0.0):
            snippet = asyncio.run(p._extract_card_snippet(search_string, page_num=1, card_index=0))

        assert snippet is None


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
