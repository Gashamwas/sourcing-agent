"""Step C1 — FACIAL_BORDERLINE third-state persistence pins.

These tests pin the C1 invariants:

1. Carve-out widening in shared/execution/runtime.py — facial-stage success
   with decision="FACIAL_BORDERLINE" persists with terminal_decision=NULL,
   exactly like FACIAL_YES, while facial NO/SKIP and full-stage decisions
   are unchanged.
2. DEDUP_BLOCKING_LINKEDIN_DECISIONS does NOT contain FACIAL_BORDERLINE
   (defensive duplication of the slice-12 pin in test_phase0_contracts.py).
3. Alias-on-read: project_linkedin_candidate_history translates
   FACIAL_BORDERLINE → FACIAL_YES in the projected outcome while leaving
   the canonical SQLite terminal_decision column untouched.
4. Defense-in-depth: load_linkedin_history applies the same translation,
   and the alias does not promote borderline rows into the saved_urls set.
5. End-to-end: a stored borderline row reaches the orchestrator's
   _prior_outcomes dict as "FACIAL_YES", so the existing FACIAL_YES
   recovery branch re-enables re-evaluation on resume.

Companion files:
- shared/execution/runtime.py:finish_stage_success (carve-out)
- shared/runtime_state/projections.py:project_linkedin_candidate_history
- shared/runtime_state/linkedin_artifacts.py:load_linkedin_history

Run with: pytest tests/test_facial_borderline_persistence.py -q
"""

from __future__ import annotations

from shared.execution import CandidateExecutionEngine
from shared.runtime_state import RuntimeStateStore
from shared.runtime_state.linkedin_artifacts import load_linkedin_history
from shared.runtime_state.projections import project_linkedin_candidate_history
from shared.runtime_state.store import (
    DEDUP_BLOCKING_DECISIONS,
    DEDUP_BLOCKING_LINKEDIN_DECISIONS,
    LINKEDIN_STRING_KIND,
)
from shared.schemas import CandidateSnippet, OpusDecision, SearchString


# ---------------------------------------------------------------------------
# Shared fixtures (mirroring tests/test_shared_execution.py style)
# ---------------------------------------------------------------------------

def _make_store(tmp_path):
    return RuntimeStateStore(tmp_path / "runtime_state.sqlite3")


def _snippet(url: str = "https://linkedin.com/in/borderline") -> CandidateSnippet:
    return CandidateSnippet(
        name="Borderline Candidate",
        headline="Senior Engineer",
        current_title="Senior Engineer",
        current_company="Borderline Co",
        location="NYC",
        education_snippet="",
        profile_url=url,
        source_string_id=1,
        source_string_name="builders",
        page=1,
        result_rank=1,
    )


def _setup_linkedin_engine(tmp_path, brief_id: str = "brief-1"):
    store = _make_store(tmp_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id=brief_id,
        output_dir=str(tmp_path),
        mode="fresh",
        resume_state={"brief_name": brief_id},
    )
    search_string = SearchString(id=1, name="builders", boolean="ml", status="queued")
    store.upsert_work_unit(
        run_id=run_id,
        source="linkedin",
        brief_id=brief_id,
        kind=LINKEDIN_STRING_KIND,
        source_unit_id="1",
        display_name=search_string.name,
        ordering_index=0,
        status="queued",
        payload=search_string.to_dict(),
    )
    engine = CandidateExecutionEngine(
        store=store,
        output_dir=str(tmp_path),
        brief_id=brief_id,
        source="linkedin",
    )
    return store, run_id, engine, search_string


def _drive_facial_stage(
    *,
    store,
    run_id,
    engine,
    search_string,
    snippet: CandidateSnippet,
    decision_value: str,
    brief_id: str = "brief-1",
):
    envelope = engine.envelope(
        source="linkedin",
        brief_id=brief_id,
        run_id=run_id,
        work_unit_kind=LINKEDIN_STRING_KIND,
        work_unit_source_id="1",
        identity_key=snippet.profile_url,
        display_name=snippet.name,
        profile_url=snippet.profile_url,
        snippet=snippet,
        source_cursor={"source_string_id": search_string.id, "page": 1, "result_rank": 1},
    )
    engine.runtime.record_discovery(envelope, payload=envelope.source_cursor)
    engine.runtime.record_snippet_extracted(
        envelope,
        payload={"cursor": envelope.source_cursor, "snippet": snippet.to_dict()},
    )
    facial_attempt = engine.runtime.start_stage(
        envelope, stage="facial", payload={"cursor": envelope.source_cursor}
    )
    engine.runtime.finish_stage_success(
        attempt_id=facial_attempt,
        envelope=envelope,
        stage="facial",
        decision=OpusDecision(
            stage="facial",
            decision=decision_value,
            path="none",
            confidence=0.7,
            rationale=f"facial decision {decision_value}",
            candidate_name=snippet.name,
            profile_url=snippet.profile_url,
        ),
    )
    return envelope


def _insert_borderline_candidate(
    store: RuntimeStateStore,
    *,
    run_id: int,
    brief_id: str,
    url: str = "https://linkedin.com/in/borderline",
    display_name: str = "Borderline Candidate",
    timestamp: str = "2026-04-25T00:00:00+00:00",
) -> str:
    """Insert a candidate with terminal_decision='FACIAL_BORDERLINE' into the store.

    Uses set_candidate_state (the production write path), not raw SQL. The
    terminal_decision TEXT column has no CHECK constraint
    (shared/runtime_state/store.py:136), so the literal lands as-is.
    """
    store.record_candidate_discovery(
        run_id=run_id,
        work_unit_id=None,
        source="linkedin",
        brief_id=brief_id,
        identity_key=url,
        display_name=display_name,
        profile_url=url,
    )
    store.set_candidate_state(
        run_id=run_id,
        source="linkedin",
        brief_id=brief_id,
        identity_key=url,
        new_state="failed_terminal",
        terminal_decision="FACIAL_BORDERLINE",
        terminal_payload={
            "confidence": 0.55,
            "source_string_id": 1,
            "timestamp": timestamp,
        },
    )
    return url


# ---------------------------------------------------------------------------
# Carve-out tests (shared/execution/runtime.py)
# ---------------------------------------------------------------------------

def test_carve_out_widens_to_borderline(tmp_path):
    """A facial-stage FACIAL_BORDERLINE persists with terminal_decision=NULL."""
    store, run_id, engine, search_string = _setup_linkedin_engine(tmp_path)
    snippet = _snippet("https://linkedin.com/in/borderline-1")
    _drive_facial_stage(
        store=store,
        run_id=run_id,
        engine=engine,
        search_string=search_string,
        snippet=snippet,
        decision_value="FACIAL_BORDERLINE",
    )

    candidate = store.get_candidate(
        source="linkedin", brief_id="brief-1", identity_key=snippet.profile_url
    )
    assert candidate is not None
    assert candidate["current_lifecycle_state"] == "facial_terminal"
    assert candidate["terminal_decision"] is None, (
        "C1 carve-out must clear terminal_decision for FACIAL_BORDERLINE so it "
        "behaves structurally like FACIAL_YES at the lifecycle layer."
    )
    assert (
        store.is_dedup_blocked(
            source="linkedin", brief_id="brief-1", identity_key=snippet.profile_url
        )
        is False
    )


def test_carve_out_keeps_facial_yes_unchanged(tmp_path):
    """Regression: FACIAL_YES still persists with terminal_decision=NULL."""
    store, run_id, engine, search_string = _setup_linkedin_engine(tmp_path)
    snippet = _snippet("https://linkedin.com/in/yes-1")
    _drive_facial_stage(
        store=store,
        run_id=run_id,
        engine=engine,
        search_string=search_string,
        snippet=snippet,
        decision_value="FACIAL_YES",
    )

    candidate = store.get_candidate(
        source="linkedin", brief_id="brief-1", identity_key=snippet.profile_url
    )
    assert candidate is not None
    assert candidate["current_lifecycle_state"] == "facial_terminal"
    assert candidate["terminal_decision"] is None


def test_carve_out_keeps_facial_no_terminal(tmp_path):
    """Regression: FACIAL_NO still persists with terminal_decision='FACIAL_NO'."""
    store, run_id, engine, search_string = _setup_linkedin_engine(tmp_path)
    snippet = _snippet("https://linkedin.com/in/no-1")
    _drive_facial_stage(
        store=store,
        run_id=run_id,
        engine=engine,
        search_string=search_string,
        snippet=snippet,
        decision_value="FACIAL_NO",
    )

    candidate = store.get_candidate(
        source="linkedin", brief_id="brief-1", identity_key=snippet.profile_url
    )
    assert candidate is not None
    assert candidate["terminal_decision"] == "FACIAL_NO"
    assert (
        store.is_dedup_blocked(
            source="linkedin", brief_id="brief-1", identity_key=snippet.profile_url
        )
        is True
    )


def test_carve_out_keeps_full_stage_unchanged(tmp_path):
    """Regression: full-stage SAVE persists with terminal_decision='SAVE'.

    Pins that the carve-out only fires for stage='facial' and does not leak
    into full-stage handling.
    """
    store, run_id, engine, search_string = _setup_linkedin_engine(tmp_path)
    snippet = _snippet("https://linkedin.com/in/full-save-1")
    envelope = _drive_facial_stage(
        store=store,
        run_id=run_id,
        engine=engine,
        search_string=search_string,
        snippet=snippet,
        decision_value="FACIAL_YES",
    )
    full_attempt = engine.runtime.start_stage(
        envelope, stage="full", payload={"cursor": envelope.source_cursor}
    )
    engine.runtime.finish_stage_success(
        attempt_id=full_attempt,
        envelope=envelope,
        stage="full",
        decision=OpusDecision(
            stage="full",
            decision="SAVE",
            path="direct_experience",
            confidence=0.92,
            rationale="strong fit",
            candidate_name=snippet.name,
            profile_url=snippet.profile_url,
        ),
    )

    candidate = store.get_candidate(
        source="linkedin", brief_id="brief-1", identity_key=snippet.profile_url
    )
    assert candidate is not None
    assert candidate["current_lifecycle_state"] == "full_terminal"
    assert candidate["terminal_decision"] == "SAVE"


# ---------------------------------------------------------------------------
# Dedup-set pin (shared/runtime_state/store.py)
# ---------------------------------------------------------------------------

def test_dedup_set_does_not_contain_borderline():
    """C1 must not promote FACIAL_BORDERLINE into the dedup-blocking set.

    Defensive duplication of test_phase0_contracts.py:test_facial_borderline_is_not_dedup_blocking;
    having it here means future readers see the invariant alongside the C1
    code paths that touch nearby logic.
    """
    assert "FACIAL_BORDERLINE" not in DEDUP_BLOCKING_LINKEDIN_DECISIONS
    assert "FACIAL_BORDERLINE" not in DEDUP_BLOCKING_DECISIONS


# ---------------------------------------------------------------------------
# Alias-on-read at the projection layer
# ---------------------------------------------------------------------------

def test_projection_aliases_borderline_to_yes(tmp_path):
    """project_linkedin_candidate_history maps FACIAL_BORDERLINE → FACIAL_YES."""
    store = _make_store(tmp_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-1",
        output_dir=str(tmp_path),
        mode="fresh",
        resume_state={"brief_name": "brief-1"},
    )
    url = _insert_borderline_candidate(store, run_id=run_id, brief_id="brief-1")

    history = project_linkedin_candidate_history(store, brief_id="brief-1")
    assert len(history) == 1
    assert history[0]["profile_url"] == url
    assert history[0]["outcome"] == "FACIAL_YES", (
        "Projection must alias FACIAL_BORDERLINE → FACIAL_YES so the orchestrator's "
        "existing FACIAL_YES recovery branch handles aliased borderline rows."
    )


def test_projection_preserves_canonical_sqlite_value(tmp_path):
    """Aliasing is read-only; SQLite still stores the literal 'FACIAL_BORDERLINE'."""
    store = _make_store(tmp_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-1",
        output_dir=str(tmp_path),
        mode="fresh",
        resume_state={"brief_name": "brief-1"},
    )
    url = _insert_borderline_candidate(store, run_id=run_id, brief_id="brief-1")

    project_linkedin_candidate_history(store, brief_id="brief-1")

    candidate = store.get_candidate(
        source="linkedin", brief_id="brief-1", identity_key=url
    )
    assert candidate is not None
    assert candidate["terminal_decision"] == "FACIAL_BORDERLINE", (
        "Canonical SQLite value must be preserved; alias is read-only."
    )


# ---------------------------------------------------------------------------
# Alias-on-read at the bridge-load layer
# ---------------------------------------------------------------------------

def test_load_linkedin_history_aliases_borderline_to_yes(tmp_path):
    """load_linkedin_history surfaces FACIAL_BORDERLINE rows as FACIAL_YES."""
    store = _make_store(tmp_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-1",
        output_dir=str(tmp_path),
        mode="fresh",
        resume_state={"brief_name": "brief-1"},
    )
    url = _insert_borderline_candidate(store, run_id=run_id, brief_id="brief-1")

    save_decisions = {"SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE", "SIGNAL_SAVE"}
    blocked_urls, prior_outcomes, saved_urls = load_linkedin_history(
        store, brief_id="brief-1", save_decisions=save_decisions
    )

    assert prior_outcomes.get(url) == "FACIAL_YES"
    assert "FACIAL_BORDERLINE" not in prior_outcomes.values()


def test_load_linkedin_history_alias_does_not_change_save_set(tmp_path):
    """Aliased borderline rows must NOT be counted as saves.

    FACIAL_YES is non-terminal and not a save outcome, so the saved_urls
    set must remain empty for a borderline-only history.
    """
    store = _make_store(tmp_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-1",
        output_dir=str(tmp_path),
        mode="fresh",
        resume_state={"brief_name": "brief-1"},
    )
    url = _insert_borderline_candidate(store, run_id=run_id, brief_id="brief-1")

    save_decisions = {"SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE", "SIGNAL_SAVE"}
    _, _, saved_urls = load_linkedin_history(
        store, brief_id="brief-1", save_decisions=save_decisions
    )
    assert url not in saved_urls
    assert saved_urls == set()


# ---------------------------------------------------------------------------
# End-to-end: bridge-load surface for the orchestrator
# ---------------------------------------------------------------------------

def test_orchestrator_borderline_resume_uses_yes_recovery_branch(tmp_path):
    """The orchestrator's _prior_outcomes never contains 'FACIAL_BORDERLINE'.

    Mirrors what linkedin/orchestrator.py:_load_candidate_history does on the
    runtime-bridge path: copy load_linkedin_history's prior_outcomes into the
    pipeline's _prior_outcomes dict. After C1 alias-on-read, that dict only
    ever sees 'FACIAL_YES' for what was originally a borderline row, so the
    existing FACIAL_YES recovery branch (linkedin/orchestrator.py:1740-1742)
    handles re-evaluation transparently regardless of whether the URL was
    initially in blocked_urls.
    """
    store = _make_store(tmp_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-1",
        output_dir=str(tmp_path),
        mode="fresh",
        resume_state={"brief_name": "brief-1"},
    )
    url = _insert_borderline_candidate(store, run_id=run_id, brief_id="brief-1")

    save_decisions = {"SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE", "SIGNAL_SAVE"}
    _, prior_outcomes, _ = load_linkedin_history(
        store, brief_id="brief-1", save_decisions=save_decisions
    )

    pipeline_prior_outcomes: dict[str, str] = dict(prior_outcomes)

    assert pipeline_prior_outcomes[url] == "FACIAL_YES", (
        "Bridge layer must surface borderline rows as FACIAL_YES so the "
        "orchestrator's existing recovery branch handles them."
    )
    assert "FACIAL_BORDERLINE" not in pipeline_prior_outcomes.values(), (
        "_prior_outcomes must NEVER contain 'FACIAL_BORDERLINE' under the "
        "alias-on-read rule; if it does, the orchestrator falls into the "
        "'already processed' branch and silently skips on resume."
    )


def test_resume_borderline_candidate_re_evaluates(tmp_path):
    """Simulate the orchestrator's dedup recovery flow for a borderline row.

    Reproduces linkedin/orchestrator.py:1731-1742 (the FACIAL_YES recovery
    branch) after the alias-on-read rule. Without aliasing, prior would be
    'FACIAL_BORDERLINE' and the candidate would fall through to the
    'already processed' branch; this test pins the lifecycle invariant the
    alias rule is for.
    """
    store = _make_store(tmp_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-1",
        output_dir=str(tmp_path),
        mode="fresh",
        resume_state={"brief_name": "brief-1"},
    )
    url = _insert_borderline_candidate(store, run_id=run_id, brief_id="brief-1")

    save_decisions = {"SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE", "SIGNAL_SAVE"}
    _, prior_outcomes, _ = load_linkedin_history(
        store, brief_id="brief-1", save_decisions=save_decisions
    )

    seen_urls: set[str] = {url}
    prior = prior_outcomes.get(url, "")
    re_evaluated = False
    fell_through_to_already_processed = False
    if prior in ("SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE"):
        pass
    elif prior == "REJECT":
        pass
    elif prior in ("FACIAL_NO", "FACIAL_SKIP"):
        pass
    elif prior == "FACIAL_YES":
        seen_urls.discard(url)
        re_evaluated = True
    else:
        fell_through_to_already_processed = True

    assert re_evaluated, (
        "Borderline candidate must reach the FACIAL_YES re-eval branch via "
        "alias-on-read; otherwise the candidate is silently skipped on resume."
    )
    assert not fell_through_to_already_processed
    assert url not in seen_urls
