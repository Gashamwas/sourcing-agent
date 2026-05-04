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
        # Phase 1.5 bumped schema_version to "4" for the stop_reason_detail
        # column + legacy normalization path. Pin against
        # CURRENT_SCHEMA_VERSION rather than a literal so the test tracks
        # the constant rather than going stale on the next bump.
        from shared.runtime_state.store import CURRENT_SCHEMA_VERSION

        assert row["value"] == CURRENT_SCHEMA_VERSION


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


def test_record_candidate_discovery_normalizes_linkedin_url(tmp_path):
    """Phase C-bis 0.4: defense-in-depth URL normalization at the store
    layer. The acquisition path already strips tracking params, but any
    future code path that bypasses acquisition (manual backfill, a
    different module) gets the same scrubbing on insert. The normalizer
    is idempotent."""

    store = _make_store(tmp_path)
    run_id = _start_run(store, tmp_path, source="linkedin")

    dirty_url = (
        "https://www.linkedin.com/in/pat-doe?"
        "miniProfileUrn=urn%3Ali%3Afsd_profile%3AACoAAA"
        "&trackingId=abc123"
        "&searchEntityType=PEOPLE"
        "&position=4"
        "&searchId=xyz789"
    )

    store.record_candidate_discovery(
        run_id=run_id,
        work_unit_id=None,
        source="linkedin",
        brief_id="brief-1",
        identity_key="li-pat-doe",
        display_name="Pat Doe",
        profile_url=dirty_url,
    )

    with store.connect() as conn:
        row = conn.execute(
            "SELECT profile_url FROM candidates "
            "WHERE source='linkedin' AND brief_id='brief-1' "
            "AND identity_key='li-pat-doe'"
        ).fetchone()

    assert row is not None
    # Tracking params stripped; trailing slash absent; lowercased.
    assert row["profile_url"] == "https://www.linkedin.com/in/pat-doe"


def test_record_candidate_discovery_does_not_normalize_github_url(tmp_path):
    """Negative case: the normalizer is LinkedIn-specific. GitHub URLs
    pass through untouched, so the defense-in-depth is scoped and won't
    surprise other modules."""

    store = _make_store(tmp_path)
    run_id = _start_run(store, tmp_path, source="github")

    github_url = "https://github.com/alice?ref=tracking"

    store.record_candidate_discovery(
        run_id=run_id,
        work_unit_id=None,
        source="github",
        brief_id="brief-1",
        identity_key="alice",
        display_name="Alice",
        profile_url=github_url,
    )

    with store.connect() as conn:
        row = conn.execute(
            "SELECT profile_url FROM candidates "
            "WHERE source='github' AND brief_id='brief-1' "
            "AND identity_key='alice'"
        ).fetchone()

    assert row is not None
    # Untouched — the LinkedIn-specific normalizer is gated by source.
    assert row["profile_url"] == github_url
