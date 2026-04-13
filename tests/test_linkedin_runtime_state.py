"""LinkedIn runtime-state bridge regressions."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from linkedin.search_intelligence import LinkedInPageInsights, LinkedInSearchVariant, bootstrap_experiment_state
from shared.runtime_state import LinkedInRuntimeStateBridge, RuntimeStateStore
from shared.schemas import CandidateSnippet, OpusDecision, Progress, SearchString
from shared.storage import append_jsonl, read_jsonl


def _make_pipeline(output_dir: str):
    with patch("linkedin.orchestrator.load_brief") as mock_brief, \
         patch("linkedin.orchestrator.init_judger"), \
         patch("linkedin.orchestrator.LinkedInBrowser"):
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

        from linkedin.orchestrator import Pipeline

        return Pipeline(brief_path=str(brief_path), output_dir=output_dir)


def _snippet(**kwargs) -> CandidateSnippet:
    defaults = {
        "name": "Ada Lovelace",
        "headline": "ML Engineer",
        "current_title": "ML Engineer",
        "current_company": "Analytical Engines",
        "location": "NYC",
        "education_snippet": "",
        "profile_url": "/talent/profile/ada",
        "source_string_id": 1,
        "source_string_name": "builders",
        "page": 1,
        "result_rank": 1,
    }
    defaults.update(kwargs)
    return CandidateSnippet(**defaults)


def test_legacy_import_is_idempotent(tmp_path):
    output_dir = tmp_path / "linkedin-output"
    output_dir.mkdir()

    progress = Progress(
        brief_name="test",
        strings=[SearchString(id=1, name="builders", boolean="ml", status="done", pages_reviewed=1)],
        current_string_id=1,
        current_page=1,
    )
    progress.save(str(output_dir / "progress.json"))
    append_jsonl(output_dir / "snippets.jsonl", _snippet().to_dict())
    append_jsonl(
        output_dir / "facial_judgments.jsonl",
        OpusDecision(
            stage="facial",
            decision="FACIAL_YES",
            path="none",
            confidence=0.9,
            rationale="interesting builder",
            candidate_name="Ada Lovelace",
            profile_url="/talent/profile/ada",
        ).to_dict(),
    )
    append_jsonl(
        output_dir / "final_judgments.jsonl",
        OpusDecision(
            stage="full",
            decision="SAVE",
            path="direct_experience",
            confidence=0.93,
            rationale="strong direct fit",
            candidate_name="Ada Lovelace",
            profile_url="/talent/profile/ada",
        ).to_dict(),
    )
    append_jsonl(
        output_dir / "candidate_history-test-project.jsonl",
        {
            "profile_url": "/talent/profile/ada",
            "candidate_name": "Ada Lovelace",
            "outcome": "SAVE",
            "confidence": 0.93,
            "source_string_id": 1,
            "timestamp": "2026-04-07T00:00:00+00:00",
        },
    )

    store = RuntimeStateStore(output_dir / "runtime_state.sqlite3")
    bridge = LinkedInRuntimeStateBridge(
        store=store,
        output_dir=output_dir,
        brief_id="test-project",
        brief_name="test",
    )
    run_id = store.start_run(
        source="linkedin",
        brief_id="test-project",
        output_dir=str(output_dir),
        mode="resume",
        resume_state={"brief_name": "test"},
    )

    bridge.import_legacy_state(run_id)
    with store.connect() as conn:
        first_attempts = conn.execute("SELECT COUNT(*) AS count FROM candidate_attempts").fetchone()["count"]

    bridge.import_legacy_state(run_id)
    with store.connect() as conn:
        second_attempts = conn.execute("SELECT COUNT(*) AS count FROM candidate_attempts").fetchone()["count"]

    assert first_attempts == second_attempts


def test_missing_profile_url_never_enters_dedup_state(tmp_path):
    store = RuntimeStateStore(tmp_path / "runtime_state.sqlite3")
    bridge = LinkedInRuntimeStateBridge(
        store=store,
        output_dir=tmp_path,
        brief_id="test-project",
        brief_name="test",
    )
    run_id = store.start_run(
        source="linkedin",
        brief_id="test-project",
        output_dir=str(tmp_path),
        mode="fresh",
        resume_state={"brief_name": "test"},
    )
    bridge.sync_progress(
        run_id,
        Progress(brief_name="test", strings=[SearchString(id=1, name="builders", boolean="ml")]),
    )

    snippet = _snippet(profile_url="")
    bridge.record_snippet_extracted(
        run_id=run_id,
        search_string=SearchString(id=1, name="builders", boolean="ml"),
        snippet=snippet,
    )

    assert store.has_candidates(source="linkedin", brief_id="test-project") is False


def test_resume_comes_from_db_when_compat_files_are_stale(tmp_path):
    p = _make_pipeline(str(tmp_path))
    progress = Progress(
        brief_name="test",
        strings=[
            SearchString(id=2, name="second", boolean="two"),
            SearchString(id=1, name="first", boolean="one"),
        ],
    )
    p._runtime_run_id, progress = p._runtime_bridge.start_or_resume_run(
        resume=False,
        initial_progress=progress,
    )
    stale_progress = {
        "brief_name": "test",
        "strings": [{"id": 99, "name": "stale", "boolean": "stale", "status": "queued"}],
    }
    (tmp_path / "progress.json").write_text(json.dumps(stale_progress))
    history_path = tmp_path / "candidate_history-test-project.jsonl"
    memory_path = tmp_path / "search_memory-test-project.json"
    history_path.write_text("")
    if memory_path.exists():
        memory_path.unlink()

    p.browser.connect = AsyncMock()
    p.browser.disconnect = AsyncMock()
    p.browser.page = MagicMock(url="https://www.linkedin.com/talent/search")
    p._print_session_summary = MagicMock()
    p._print_summary = MagicMock()
    p._generate_run_report = MagicMock()
    p._session_expired = MagicMock()

    processed_ids: list[int] = []

    async def fake_process(search_string, progress):
        processed_ids.append(search_string.id)

    p._process_string = fake_process

    asyncio.run(p.run_full(resume=True))

    assert processed_ids == [2, 1]


def test_sync_progress_roundtrips_experiment_state(tmp_path):
    store = RuntimeStateStore(tmp_path / "runtime_state.sqlite3")
    bridge = LinkedInRuntimeStateBridge(
        store=store,
        output_dir=tmp_path,
        brief_id="test-project",
        brief_name="test",
    )
    run_id = store.start_run(
        source="linkedin",
        brief_id="test-project",
        output_dir=str(tmp_path),
        mode="fresh",
        resume_state={"brief_name": "test"},
    )

    search_string = SearchString(id=1, name="builders", boolean="foo")
    state = bootstrap_experiment_state(search_string)
    state.begin_experiment_round(
        [
            LinkedInSearchVariant(
                variant_id="precision-1",
                parent_variant_id="root",
                root_string_id=1,
                boolean="foo AND bar",
                variant_kind="precision",
                target_result_min=75,
                target_result_max=400,
            )
        ]
    )
    state.activate_variant("precision-1")
    state.commit_variant("precision-1")
    state.apply_shadow(search_string)

    progress = Progress(brief_name="test", strings=[search_string], current_string_id=1, current_page=2)
    bridge.sync_progress(run_id, progress, experiment_states={1: state})

    loaded_progress = bridge.load_progress(run_id)
    loaded_states = bridge.load_experiment_states(run_id, progress=loaded_progress)

    assert loaded_progress.strings[0].boolean == "foo AND bar"
    assert loaded_progress.strings[0].refinement_stack == ["foo"]
    assert loaded_states[1].active_variant_id == "precision-1"
    assert loaded_states[1].committed_variant_id == "precision-1"


def test_sync_progress_roundtrips_pending_drift_and_family_metrics(tmp_path):
    store = RuntimeStateStore(tmp_path / "runtime_state.sqlite3")
    bridge = LinkedInRuntimeStateBridge(
        store=store,
        output_dir=tmp_path,
        brief_id="test-project",
        brief_name="test",
    )
    run_id = store.start_run(
        source="linkedin",
        brief_id="test-project",
        output_dir=str(tmp_path),
        mode="fresh",
        resume_state={"brief_name": "test"},
    )

    search_string = SearchString(id=1, name="builders", boolean="foo")
    state = bootstrap_experiment_state(search_string)
    state.commit_variant("root")
    page = LinkedInPageInsights(
        page=1,
        result_count=1800,
        result_window="150-800",
        signal_anchors=["ML engineer at OpenAI", "Research engineer at Anthropic"],
        title_clusters=[{"label": "machine learning engineer", "count": 4}],
    )
    state.record_variant_metrics(page_num=1, result_count=1800, page_stats={"candidates": 4, "facial_yes": 2, "saves": 1}, page_insights=page)
    state.record_family_page_metrics(page_num=1, result_count=1800, page_stats={"candidates": 4, "facial_yes": 2, "saves": 1}, page_insights=page)
    state.precommit_recovery_attempts_used = 2
    state.committed_pages_reviewed = 1
    state.committed_zero_signal_streak = 0
    drift_variant = LinkedInSearchVariant(
        variant_id="drift-1",
        parent_variant_id="root",
        root_string_id=1,
        boolean="foo AND bar",
        variant_kind="precision",
    )
    state.variants["drift-1"] = drift_variant
    state.mark_pending_drift(
        variant_id="drift-1",
        parent_variant_id="root",
        summary={"decision": "refine_committed", "keyword_hypothesis": "tighten around ML engineer"},
    )
    state.activate_variant("drift-1")
    state.apply_shadow(search_string)

    progress = Progress(brief_name="test", strings=[search_string], current_string_id=1, current_page=1)
    bridge.sync_progress(run_id, progress, experiment_states={1: state})

    loaded_progress = bridge.load_progress(run_id)
    loaded_states = bridge.load_experiment_states(run_id, progress=loaded_progress)
    row = store.get_work_unit_by_source_id(run_id, kind="linkedin_string", source_unit_id="1")
    metrics = json.loads(row["metrics_json"])

    assert loaded_states[1].pending_drift_variant_id == "drift-1"
    assert loaded_states[1].pending_drift_parent_variant_id == "root"
    assert loaded_states[1].drift_attempt_count == 1
    assert loaded_states[1].precommit_recovery_attempts_used == 2
    assert loaded_states[1].committed_pages_reviewed == 1
    assert loaded_states[1].committed_zero_signal_streak == 0
    assert metrics["experiment_summary"]["family_pages_reviewed_total"] == 1
    assert metrics["experiment_summary"]["active_variant_pages_reviewed"] == 0
    assert metrics["experiment_summary"]["precommit_recovery_attempts_used"] == 2
    assert metrics["experiment_summary"]["drift_rescue_summary"]["decision"] == "refine_committed"


def test_profile_extraction_failure_becomes_failed_retryable(tmp_path):
    p = _make_pipeline(str(tmp_path))
    search_string = SearchString(id=1, name="builders", boolean="ml")
    progress = Progress(brief_name="test", strings=[search_string])
    p._runtime_run_id, _ = p._runtime_bridge.start_or_resume_run(resume=False, initial_progress=progress)

    snippet = _snippet()
    p._record_runtime_snippet(search_string, snippet)
    facial_attempt_id = p._start_runtime_stage_attempt(
        search_string=search_string,
        snippet=snippet,
        stage="facial",
    )
    facial_yes = OpusDecision(
        stage="facial",
        decision="FACIAL_YES",
        path="none",
        confidence=0.82,
        rationale="worth opening",
        candidate_name=snippet.name,
        profile_url=snippet.profile_url,
    )
    p._finish_runtime_stage_success(
        attempt_id=facial_attempt_id,
        stage="facial",
        snippet=snippet,
        decision=facial_yes,
    )

    p.browser.ensure_card_rendered = AsyncMock()
    p.browser.open_profile_by_url = AsyncMock(return_value=None)
    p.browser.simulate_profile_read = AsyncMock(return_value=None)
    p.browser.get_profile_innertext = AsyncMock(side_effect=RuntimeError("extract failed"))
    p.browser.go_back_to_results = AsyncMock(return_value=None)
    p._ensure_browser_healthy = AsyncMock()

    decision = asyncio.run(p._full_evaluate(snippet, None, search_string))

    assert decision is not None
    assert decision.decision == "JUDGMENT_FAILURE"
    candidate = p._runtime_state.get_candidate(
        source="linkedin",
        brief_id="test-project",
        identity_key=snippet.profile_url,
    )
    assert candidate["current_lifecycle_state"] == "failed_retryable"
    assert p._runtime_state.is_dedup_blocked(
        source="linkedin",
        brief_id="test-project",
        identity_key=snippet.profile_url,
    ) is False


def test_restart_string_clears_only_targeted_runtime_state(tmp_path):
    store = RuntimeStateStore(tmp_path / "runtime_state.sqlite3")
    bridge = LinkedInRuntimeStateBridge(
        store=store,
        output_dir=tmp_path,
        brief_id="test-project",
        brief_name="test",
    )
    progress = Progress(
        brief_name="test",
        strings=[
            SearchString(id=1, name="one", boolean="a", status="done", saves=["Ada"]),
            SearchString(id=2, name="two", boolean="b", status="done", saves=["Grace"]),
        ],
        current_string_id=1,
    )
    run_id = store.start_run(
        source="linkedin",
        brief_id="test-project",
        output_dir=str(tmp_path),
        mode="resume",
        resume_state={"brief_name": "test"},
    )
    bridge.sync_progress(run_id, progress)

    for string_id, name, url in (
        (1, "Ada", "/talent/profile/ada"),
        (2, "Grace", "/talent/profile/grace"),
    ):
        store.record_candidate_discovery(
            run_id=run_id,
            work_unit_id=store.get_work_unit_id(run_id, kind="linkedin_string", source_unit_id=str(string_id)),
            source="linkedin",
            brief_id="test-project",
            identity_key=url,
            display_name=name,
            profile_url=url,
            payload={"source_string_id": string_id},
        )
        store.set_candidate_state(
            run_id=run_id,
            source="linkedin",
            brief_id="test-project",
            identity_key=url,
            new_state="snippet_extracted",
        )
        store.set_candidate_state(
            run_id=run_id,
            source="linkedin",
            brief_id="test-project",
            identity_key=url,
            new_state="facial_started",
        )
        store.set_candidate_state(
            run_id=run_id,
            source="linkedin",
            brief_id="test-project",
            identity_key=url,
            new_state="facial_terminal",
            terminal_decision="FACIAL_YES",
            terminal_payload={"source_string_id": string_id},
        )
        store.set_candidate_state(
            run_id=run_id,
            source="linkedin",
            brief_id="test-project",
            identity_key=url,
            new_state="full_started",
        )
        store.set_candidate_state(
            run_id=run_id,
            source="linkedin",
            brief_id="test-project",
            identity_key=url,
            new_state="full_terminal",
            terminal_decision="SAVE",
            terminal_payload={"source_string_id": string_id, "timestamp": "2026-04-07T00:00:00+00:00"},
        )
        attempt_id = store.start_attempt(
            run_id=run_id,
            source="linkedin",
            brief_id="test-project",
            identity_key=url,
            stage="full",
            work_unit_id=store.get_work_unit_id(run_id, kind="linkedin_string", source_unit_id=str(string_id)),
            payload={"source_string_id": string_id, "final_decision": {"decision": "SAVE"}},
            source_cursor={"source_string_id": string_id},
            display_name=name,
            profile_url=url,
        )
        store.finish_attempt_success(
            attempt_id=attempt_id,
            new_state="full_terminal",
            terminal_decision="SAVE",
            payload={"source_string_id": string_id, "final_decision": {"decision": "SAVE"}},
            run_id=run_id,
        )

    bridge.restart_string(run_id=run_id, progress=progress, string_id=1)

    assert store.is_dedup_blocked(
        source="linkedin",
        brief_id="test-project",
        identity_key="/talent/profile/ada",
    ) is False
    assert store.is_dedup_blocked(
        source="linkedin",
        brief_id="test-project",
        identity_key="/talent/profile/grace",
    ) is True
    history = read_jsonl(tmp_path / "candidate_history-test-project.jsonl")
    assert [row["profile_url"] for row in history] == ["/talent/profile/grace"]


def test_restart_string_resets_variant_execution_state(tmp_path):
    store = RuntimeStateStore(tmp_path / "runtime_state.sqlite3")
    bridge = LinkedInRuntimeStateBridge(
        store=store,
        output_dir=tmp_path,
        brief_id="test-project",
        brief_name="test",
    )
    run_id = store.start_run(
        source="linkedin",
        brief_id="test-project",
        output_dir=str(tmp_path),
        mode="fresh",
        resume_state={"brief_name": "test"},
    )

    search_string = SearchString(id=1, name="builders", boolean="foo", status="done")
    state = bootstrap_experiment_state(search_string)
    state.begin_experiment_round(
        [
            LinkedInSearchVariant(
                variant_id="precision-1",
                parent_variant_id="root",
                root_string_id=1,
                boolean="foo AND bar",
                variant_kind="precision",
            )
        ]
    )
    state.activate_variant("precision-1")
    state.commit_variant("precision-1")
    state.apply_shadow(search_string)
    progress = Progress(brief_name="test", strings=[search_string], current_string_id=1, current_page=2)
    bridge.sync_progress(run_id, progress, experiment_states={1: state})

    bridge.restart_string(run_id=run_id, progress=progress, string_id=1)
    reloaded_progress = bridge.load_progress(run_id)
    reloaded_states = bridge.load_experiment_states(run_id, progress=reloaded_progress)

    assert reloaded_progress.strings[0].boolean == "foo"
    assert reloaded_progress.strings[0].refinement_stack == []
    assert reloaded_states[1].active_variant_id == "root"
    assert reloaded_states[1].committed_variant_id is None


def test_restart_string_clears_pending_drift_state(tmp_path):
    store = RuntimeStateStore(tmp_path / "runtime_state.sqlite3")
    bridge = LinkedInRuntimeStateBridge(
        store=store,
        output_dir=tmp_path,
        brief_id="test-project",
        brief_name="test",
    )
    run_id = store.start_run(
        source="linkedin",
        brief_id="test-project",
        output_dir=str(tmp_path),
        mode="fresh",
        resume_state={"brief_name": "test"},
    )
    search_string = SearchString(id=1, name="builders", boolean="foo", status="in_progress")
    state = bootstrap_experiment_state(search_string)
    state.commit_variant("root")
    state.variants["drift-1"] = LinkedInSearchVariant(
        variant_id="drift-1",
        parent_variant_id="root",
        root_string_id=1,
        boolean="foo AND bar",
        variant_kind="precision",
    )
    state.mark_pending_drift(
        variant_id="drift-1",
        parent_variant_id="root",
        summary={"decision": "refine_committed"},
    )
    state.activate_variant("drift-1")
    state.apply_shadow(search_string)
    progress = Progress(brief_name="test", strings=[search_string], current_string_id=1, current_page=1)
    bridge.sync_progress(run_id, progress, experiment_states={1: state})

    bridge.restart_string(run_id=run_id, progress=progress, string_id=1)
    reloaded_progress = bridge.load_progress(run_id)
    reloaded_states = bridge.load_experiment_states(run_id, progress=reloaded_progress)

    assert reloaded_progress.strings[0].boolean == "foo"
    assert reloaded_states[1].pending_drift_variant_id is None
    assert reloaded_states[1].pending_drift_parent_variant_id is None
    assert reloaded_states[1].drift_attempt_count == 0
