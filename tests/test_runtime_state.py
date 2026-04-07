"""Tests for the SQLite-backed canonical runtime state store."""

from __future__ import annotations

import sqlite3

import pytest

from shared.runtime_state import RuntimeStateLock, RuntimeStateStore


def _make_store(tmp_path):
    return RuntimeStateStore(tmp_path / "runtime_state.sqlite3")


def _start_run(store: RuntimeStateStore, tmp_path, *, source: str = "github", brief_id: str = "brief-1") -> int:
    return store.start_run(
        source=source,
        brief_id=brief_id,
        output_dir=str(tmp_path),
        mode="fresh",
        resume_state={"brief_name": brief_id},
    )


def test_bootstrap_is_idempotent(tmp_path):
    store = _make_store(tmp_path)
    store.initialize()

    with store.connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        assert row["value"] == "3"


def test_rejects_invalid_state_transition(tmp_path):
    store = _make_store(tmp_path)
    run_id = _start_run(store, tmp_path)
    store.record_candidate_discovery(
        run_id=run_id,
        work_unit_id=None,
        source="github",
        brief_id="brief-1",
        identity_key="alice",
        display_name="Alice",
        profile_url="https://github.com/alice",
    )

    with pytest.raises(ValueError, match="invalid lifecycle transition"):
        store.set_candidate_state(
            run_id=run_id,
            source="github",
            brief_id="brief-1",
            identity_key="alice",
            new_state="full_terminal",
            terminal_decision="SAVE",
        )


def test_same_transition_is_idempotent(tmp_path):
    store = _make_store(tmp_path)
    run_id = _start_run(store, tmp_path)
    store.record_candidate_discovery(
        run_id=run_id,
        work_unit_id=None,
        source="github",
        brief_id="brief-1",
        identity_key="alice",
        display_name="Alice",
        profile_url="https://github.com/alice",
    )
    store.set_candidate_state(
        run_id=run_id,
        source="github",
        brief_id="brief-1",
        identity_key="alice",
        new_state="snippet_extracted",
    )
    store.set_candidate_state(
        run_id=run_id,
        source="github",
        brief_id="brief-1",
        identity_key="alice",
        new_state="snippet_extracted",
    )

    candidate = store.get_candidate(source="github", brief_id="brief-1", identity_key="alice")
    assert candidate["current_lifecycle_state"] == "snippet_extracted"


def test_identity_uniqueness_is_scoped_by_brief_and_source(tmp_path):
    store = _make_store(tmp_path)
    first = store.ensure_candidate(
        source="github",
        brief_id="brief-1",
        identity_key="alice",
        display_name="Alice",
        profile_url="https://github.com/alice",
    )
    second = store.ensure_candidate(
        source="github",
        brief_id="brief-1",
        identity_key="alice",
        display_name="Alice A.",
        profile_url="https://github.com/alice",
    )
    third = store.ensure_candidate(
        source="linkedin",
        brief_id="brief-1",
        identity_key="alice",
        display_name="Alice",
        profile_url="https://linkedin.com/in/alice",
    )

    assert first == second
    assert third != first


def test_reconciles_orphaned_attempts_on_startup(tmp_path):
    store = _make_store(tmp_path)
    run_id = _start_run(store, tmp_path)
    store.record_candidate_discovery(
        run_id=run_id,
        work_unit_id=None,
        source="github",
        brief_id="brief-1",
        identity_key="alice",
        display_name="Alice",
        profile_url="https://github.com/alice",
    )
    attempt_id = store.start_attempt(
        run_id=run_id,
        source="github",
        brief_id="brief-1",
        identity_key="alice",
        stage="facial",
        payload={"candidate_record": {"username": "alice"}},
        source_cursor={"query_id": 1},
        display_name="Alice",
        profile_url="https://github.com/alice",
    )
    assert attempt_id > 0

    reconciled = store.reconcile_open_attempts(source="github", brief_id="brief-1")
    assert reconciled == 1

    candidate = store.get_candidate(source="github", brief_id="brief-1", identity_key="alice")
    assert candidate["current_lifecycle_state"] == "failed_retryable"

    with store.connect() as conn:
        row = conn.execute(
            "SELECT status, failure_kind, failure_reason FROM candidate_attempts WHERE id = ?",
            (attempt_id,),
        ).fetchone()
        assert row["status"] == "reconciled"
        assert row["failure_kind"] == "orphaned_attempt"
        assert "interrupted" in row["failure_reason"]


def test_runtime_lock_enforces_single_writer(tmp_path):
    first = RuntimeStateLock(tmp_path)
    second = RuntimeStateLock(tmp_path)

    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="already locked"):
            second.acquire()
    finally:
        first.release()


def test_finish_run_persists_stop_reason(tmp_path):
    store = _make_store(tmp_path)
    run_id = _start_run(store, tmp_path)

    store.finish_run(run_id, "interrupted", stop_reason="governor_limit")

    run = store.get_run(run_id)
    assert run["status"] == "interrupted"
    assert run["stop_reason"] == "governor_limit"


def test_reconciles_pending_candidate_side_effects_and_allows_manual_replay(tmp_path):
    store = _make_store(tmp_path)
    run_id = _start_run(store, tmp_path, source="linkedin")
    store.record_candidate_discovery(
        run_id=run_id,
        work_unit_id=None,
        source="linkedin",
        brief_id="brief-1",
        identity_key="/talent/profile/ada",
        display_name="Ada",
        profile_url="/talent/profile/ada",
    )

    started = store.begin_candidate_side_effect(
        run_id=run_id,
        source="linkedin",
        brief_id="brief-1",
        identity_key="/talent/profile/ada",
        attempt_id=None,
        effect_type="linkedin_save",
        idempotency_key="save",
        payload={"search_string_id": 1},
    )
    assert started["should_execute"] is True

    reconciled = store.reconcile_pending_side_effects(source="linkedin", brief_id="brief-1")
    assert reconciled == 1

    rows = store.list_candidate_side_effects(source="linkedin", brief_id="brief-1")
    assert rows[0]["status"] == "failed"

    skipped = store.begin_candidate_side_effect(
        run_id=run_id,
        source="linkedin",
        brief_id="brief-1",
        identity_key="/talent/profile/ada",
        attempt_id=None,
        effect_type="linkedin_save",
        idempotency_key="save",
        payload={"search_string_id": 1},
    )
    assert skipped["should_execute"] is False

    invalidated = store.invalidate_candidate_side_effects(
        source="linkedin",
        brief_id="brief-1",
        identity_key="/talent/profile/ada",
        effect_type="linkedin_save",
    )
    assert invalidated == 1

    replay = store.begin_candidate_side_effect(
        run_id=run_id,
        source="linkedin",
        brief_id="brief-1",
        identity_key="/talent/profile/ada",
        attempt_id=None,
        effect_type="linkedin_save",
        idempotency_key="save",
        payload={"search_string_id": 1},
    )
    assert replay["should_execute"] is True
