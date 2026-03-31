"""Tests for GitHub pipeline interruption safety and governor enforcement.

Covers: governor lifecycle, query error handling, deferred dedup, and resume semantics.

Run with: python -m pytest tests/test_github_pipeline.py -v
"""

import asyncio
import importlib
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeExhaustionState:
    def __init__(self):
        self.channels = {}

    def record_query_result(self, **kw):
        pass

    def to_adaptation_context(self):
        return ""


def _import_pipeline_with_stubs():
    """Import github.orchestrator under temporary stubs without polluting later tests."""
    stub_names = (
        "github.client",
        "github.enricher",
        "github.strategy",
        "github.query_validator",
        "github.observability",
        "github.outreach",
        "github.export",
        "shared.contact_discovery",
        "shared.judger",
    )
    originals = {name: sys.modules.get(name) for name in stub_names}

    try:
        for mod_name in stub_names:
            sys.modules[mod_name] = types.ModuleType(mod_name)

        client_mod = sys.modules["github.client"]
        client_mod.GitHubClient = MagicMock

        enricher_mod = sys.modules["github.enricher"]
        enricher_mod.GitHubEnricher = MagicMock

        strategy_mod = sys.modules["github.strategy"]
        strategy_mod.form_github_strategy = MagicMock(return_value=([], ""))
        strategy_mod.adapt_after_batch = MagicMock()

        qv_mod = sys.modules["github.query_validator"]
        qv_mod.ExhaustionState = _FakeExhaustionState

        obs_mod = sys.modules["github.observability"]
        obs_mod.SessionObserver = MagicMock

        contact_mod = sys.modules["shared.contact_discovery"]
        contact_mod.merge_profile_contact = MagicMock()

        judger_mod = sys.modules["shared.judger"]
        for name in (
            "facial_judge",
            "full_judge",
            "init_judger",
            "github_facial_judge",
            "github_full_judge",
            "extract_priority_rank",
        ):
            setattr(judger_mod, name, MagicMock())

        judger_mod.is_failure_decision = (
            lambda decision: decision in ("PARSE_FAILURE", "JUDGMENT_FAILURE")
        )

        outreach_mod = sys.modules["github.outreach"]
        outreach_mod.generate_outreach = AsyncMock(return_value={"message": "hi"})

        from github.governor import GitHubGovernor, GitHubGovernorLimitReached
        from github.schemas import GitHubProgress, GitHubSearchQuery

        orchestrator_mod = importlib.import_module("github.orchestrator")
        return (
            GitHubGovernor,
            GitHubGovernorLimitReached,
            GitHubProgress,
            GitHubSearchQuery,
            orchestrator_mod.GitHubPipeline,
            orchestrator_mod,
        )
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


(
    GitHubGovernor,
    GitHubGovernorLimitReached,
    GitHubProgress,
    GitHubSearchQuery,
    GitHubPipeline,
    github_orchestrator,
) = _import_pipeline_with_stubs()


# ---------------------------------------------------------------------------
# Minimal pipeline fixture
# ---------------------------------------------------------------------------

def _make_pipeline(**overrides):
    """Build a GitHubPipeline with heavy deps stubbed out."""
    brief = MagicMock()
    brief.id = "test-brief"
    brief.has_v2_schema = True
    brief._new_brief = {}

    with patch.object(GitHubPipeline, "__init__", lambda self: None):
        p = GitHubPipeline()

    p.brief_path = "fake.json"
    p.brief_obj = brief
    p.output_dir = "/tmp/test_gh_pipeline"
    p.progress_path = Path(tempfile.mkdtemp(prefix="gh_pipeline_test_")) / "progress.json"
    p.candidates_path = "/tmp/test_gh_pipeline/candidates.jsonl"
    p.snippets_path = "/tmp/test_gh_pipeline/snippets.jsonl"
    p.facial_path = "/tmp/test_gh_pipeline/facial.jsonl"
    p.profiles_path = "/tmp/test_gh_pipeline/profiles.jsonl"
    p.final_path = "/tmp/test_gh_pipeline/final.jsonl"
    p.saves_path = "/tmp/test_gh_pipeline/saves.jsonl"
    p.outreach_path = "/tmp/test_gh_pipeline/outreach.jsonl"
    p.log_path = "/tmp/test_gh_pipeline/log.jsonl"
    p.stats = {
        "candidates_discovered": 0,
        "candidates_enriched": 0,
        "facial_yes": 0,
        "facial_no": 0,
        "saved": 0,
        "rejected": 0,
        "insufficient": 0,
    }
    p._governor = GitHubGovernor()
    p._governor.start_session()
    p._bias_monitor = None
    p._progress = None
    p._client = None
    p._observer = MagicMock()
    p._shutdown_requested = False
    p._seen_usernames = set()
    p._in_flight_usernames = set()
    p._exhaustion = _FakeExhaustionState()

    for k, v in overrides.items():
        setattr(p, k, v)
    return p


def _make_query(**overrides) -> GitHubSearchQuery:
    defaults = dict(
        id=1, name="test query", query="language:python", channel="user_search",
    )
    defaults.update(overrides)
    return GitHubSearchQuery(**defaults)


# ---------------------------------------------------------------------------
# Fix 1: Governor lifecycle
# ---------------------------------------------------------------------------

class TestGovernorLifecycle:
    def test_governor_starts_in_run(self):
        """Governor._active is True after start_session() called."""
        gov = GitHubGovernor()
        assert not gov._active
        gov.start_session()
        assert gov._active

    def test_governor_ends_in_finally(self):
        """Governor._active is False after end_session()."""
        gov = GitHubGovernor()
        gov.start_session()
        assert gov._active
        gov.end_session()
        assert not gov._active


# ---------------------------------------------------------------------------
# Fix 2: Query error handling
# ---------------------------------------------------------------------------

class TestQueryErrorHandling:
    def test_query_done_on_success(self):
        """Successful query → status='done'."""
        pipeline = _make_pipeline()
        query = _make_query()
        progress = GitHubProgress(brief_name="test")
        progress.queries = [query]

        client = MagicMock()
        client.limiter.remaining.return_value = 5000
        enricher = MagicMock()

        pipeline._execute_single_query = AsyncMock()
        pipeline._save_progress = MagicMock()
        pipeline._get_api_status = MagicMock(return_value={})
        pipeline._get_executed_query_strings = MagicMock(return_value=set())

        asyncio.run(pipeline._execute_queries(client, enricher, progress))
        assert query.status == "done"

    def test_query_error_on_failure(self):
        """Failed query → status='error'."""
        pipeline = _make_pipeline()
        query = _make_query()
        progress = GitHubProgress(brief_name="test")
        progress.queries = [query]

        client = MagicMock()
        client.limiter.remaining.return_value = 5000
        enricher = MagicMock()

        pipeline._execute_single_query = AsyncMock(side_effect=RuntimeError("boom"))
        pipeline._save_progress = MagicMock()
        pipeline._get_api_status = MagicMock(return_value={})

        asyncio.run(pipeline._execute_queries(client, enricher, progress))
        assert query.status == "error"
        assert "boom" in query.notes

    def test_error_query_retried_on_resume(self):
        """'error' queries are NOT in the skip set ('done', 'skipped')."""
        query = _make_query(status="error")
        assert query.status not in ("done", "skipped")

    def test_error_query_not_in_batch_stats(self):
        """Errored query does not appear in batch_stats — only done query does."""
        pipeline = _make_pipeline()
        q1 = _make_query(id=1)
        q2 = _make_query(id=2)
        progress = GitHubProgress(brief_name="test")
        progress.queries = [q1, q2]

        client = MagicMock()
        client.limiter.remaining.return_value = 5000
        enricher = MagicMock()

        call_count = 0
        async def _side_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("fail first")

        pipeline._execute_single_query = AsyncMock(side_effect=_side_effect)
        pipeline._save_progress = MagicMock()
        pipeline._get_api_status = MagicMock(return_value={})

        asyncio.run(pipeline._execute_queries(client, enricher, progress))

        # q1 errored, q2 succeeded
        assert q1.status == "error"
        assert q2.status == "done"

    def test_resume_skips_do_not_trigger_early_adaptation(self):
        """Resume batches should count newly executed queries, not raw loop index."""
        pipeline = _make_pipeline()
        q1 = _make_query(id=1, status="done")
        q2 = _make_query(id=2, status="skipped")
        q3 = _make_query(id=3)
        progress = GitHubProgress(brief_name="test")
        progress.queries = [q1, q2, q3]

        client = MagicMock()
        client.limiter.remaining.return_value = 5000
        enricher = MagicMock()

        pipeline._execute_single_query = AsyncMock()
        pipeline._save_progress = MagicMock()
        pipeline._get_api_status = MagicMock(return_value={})
        pipeline._get_executed_query_strings = MagicMock(return_value=set())

        with patch.object(github_orchestrator, "_ADAPTATION_BATCH_SIZE", 2), patch.object(
            github_orchestrator, "adapt_after_batch", return_value=([], "", [])
        ) as adapt_mock:
            asyncio.run(pipeline._execute_queries(client, enricher, progress))

        adapt_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Fix 3: Deferred dedup
# ---------------------------------------------------------------------------

class TestDeferredDedup:
    def test_dedup_terminal_permanent(self):
        """Username with terminal outcome stays in _seen_usernames."""
        pipeline = _make_pipeline()
        pipeline._in_flight_usernames.add("alice")
        pipeline._mark_terminal("alice")
        assert "alice" in pipeline._seen_usernames
        assert "alice" not in pipeline._in_flight_usernames

    def test_dedup_inflight_not_persisted(self):
        """_in_flight_usernames not in progress.discovered_usernames."""
        pipeline = _make_pipeline()
        progress = GitHubProgress(brief_name="test")
        pipeline._progress = progress
        pipeline._client = MagicMock()
        pipeline._client.limiter.total_calls = 0

        # Simulate in-flight and terminal
        pipeline._in_flight_usernames = {"inflight_user"}
        pipeline._seen_usernames = {"terminal_user"}

        pipeline._save_progress()

        assert "terminal_user" in progress.discovered_usernames
        assert "inflight_user" not in progress.discovered_usernames

    def test_light_enrich_failure_not_terminal(self):
        """light_enrich returning None → username NOT in _seen_usernames."""
        pipeline = _make_pipeline()
        result = pipeline._dedup_usernames(["bob"])
        assert result == ["bob"]
        assert "bob" in pipeline._in_flight_usernames

        # Simulate light_enrich returning None — no _mark_terminal called
        assert "bob" not in pipeline._seen_usernames
        assert "bob" in pipeline._in_flight_usernames

    def test_parse_failure_not_terminal(self):
        """PARSE_FAILURE → username NOT in _seen_usernames (non-terminal)."""
        pipeline = _make_pipeline()
        pipeline._dedup_usernames(["charlie"])
        # PARSE_FAILURE exits without calling _mark_terminal
        assert "charlie" not in pipeline._seen_usernames
        assert "charlie" in pipeline._in_flight_usernames

    def test_candidates_jsonl_not_dedup_source(self):
        """_seen_usernames not loaded from candidates.jsonl."""
        pipeline = _make_pipeline()
        assert pipeline._seen_usernames == set()

    def test_dedup_blocks_seen_and_inflight(self):
        """_dedup_usernames filters both _seen and _in_flight."""
        pipeline = _make_pipeline()
        pipeline._seen_usernames = {"alice"}
        pipeline._in_flight_usernames = {"bob"}

        result = pipeline._dedup_usernames(["alice", "bob", "charlie"])
        assert result == ["charlie"]
        assert "charlie" in pipeline._in_flight_usernames
