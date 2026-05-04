"""Tests for the intake-session CRUD module + API endpoints (Slice 1B).

Per ``/Users/sam.vangelos/.claude/plans/ancient-plotting-lemon.md`` A24, the
onboarding flow's authoring state lives in a dedicated ``intake_sessions``
SQLite table colocated with the canonical ``runtime_state.sqlite3``
schema. These tests exercise:

- the :mod:`cloris.intake_sessions` CRUD helpers directly against a
  ``RuntimeStateStore`` pointed at ``tmp_path``;
- the FastAPI router endpoints with ``_intake_store`` monkeypatched to the
  same tmp_path-backed store, so route shape + status codes get coverage
  without touching the real ``output/intake/`` tree;
- the schema-migration idempotency guarantee (running ``_migrate`` twice
  on a fresh DB produces exactly one ``intake_sessions`` table and no
  errors);
- the ``ConfigDict(extra="forbid")`` wire contract (POST with an unknown
  field returns HTTP 422).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloris import api as cloris_api
from cloris import intake_sessions as intake_module
from cloris.app import create_app
from shared.runtime_state.store import RuntimeStateStore


def _make_store(tmp_path: Path) -> RuntimeStateStore:
    """Construct a RuntimeStateStore pointed at a tmp intake DB.

    Mirrors the production layout (``intake/intake_sessions.sqlite3``)
    inside tmp_path so any path-shape regressions surface here rather than
    polluting the real output tree.
    """

    return RuntimeStateStore(tmp_path / "intake" / "intake_sessions.sqlite3")


@pytest.fixture
def store(tmp_path: Path) -> RuntimeStateStore:
    """A fresh, migrated RuntimeStateStore for direct CRUD testing."""

    return _make_store(tmp_path)


@pytest.fixture
def api_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """A TestClient whose intake endpoints write to a tmp-path-backed store.

    Monkeypatches both seams:

    - ``cloris.api._intake_store`` — used by POST/PATCH/DELETE handlers,
      returns the tmp-path-backed writer.
    - ``cloris.api._intake_db_path`` — used by the read-only GET
      handlers (which route through ``read_models`` to avoid
      writer instantiation on read paths). Returns the same path the
      tmp_store writes to so both sides see the same DB.
    """

    tmp_db_path = tmp_path / "intake" / "intake_sessions.sqlite3"
    tmp_store = RuntimeStateStore(tmp_db_path)

    def fake_intake_store() -> RuntimeStateStore:
        return tmp_store

    def fake_intake_db_path() -> Path:
        return tmp_db_path

    monkeypatch.setattr(cloris_api, "_intake_store", fake_intake_store)
    monkeypatch.setattr(cloris_api, "_intake_db_path", fake_intake_db_path)

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Direct CRUD coverage
# ---------------------------------------------------------------------------


def test_create_intake_session_returns_initial_shape(
    store: RuntimeStateStore,
) -> None:
    session = intake_module.create_intake_session(store, role_title=None)

    assert isinstance(session["id"], int)
    assert session["id"] > 0
    assert session["brief_id_draft"] is None
    assert session["role_title"] is None
    assert session["current_step"] == "welcome"
    assert session["state_json"] == {}
    assert session["started_at"]
    assert session["updated_at"] == session["started_at"]
    assert session["completed_at"] is None
    assert session["archived_at"] is None


def test_create_intake_session_accepts_role_title_hint(
    store: RuntimeStateStore,
) -> None:
    session = intake_module.create_intake_session(
        store, role_title="Head of AI Lab"
    )
    assert session["role_title"] == "Head of AI Lab"
    # Step is still welcome — the optional hint doesn't advance state.
    assert session["current_step"] == "welcome"


def test_list_intake_sessions_returns_newest_first_excluding_archived(
    store: RuntimeStateStore,
) -> None:
    """Active sessions only, ordered by updated_at DESC.

    We bump the second session's updated_at via a patch so the ordering
    contract is exercised even if the create timestamps tie at the
    sub-millisecond level. We then archive the third session via a raw
    SQL UPDATE to verify the WHERE archived_at IS NULL clause filters it
    out.
    """

    a = intake_module.create_intake_session(store, role_title="A")
    b = intake_module.create_intake_session(store, role_title="B")
    c = intake_module.create_intake_session(store, role_title="C")

    # Touch B last so it's newest by updated_at.
    intake_module.patch_intake_session(
        store, session_id=b["id"], current_step="role_basics"
    )

    # Archive C so list_intake_sessions excludes it.
    with store.connect() as conn:
        conn.execute(
            "UPDATE intake_sessions SET archived_at = ? WHERE id = ?",
            ("2026-04-28T00:00:00+00:00", c["id"]),
        )

    sessions = intake_module.list_intake_sessions(store)
    ids_in_order = [s["id"] for s in sessions]

    assert c["id"] not in ids_in_order, "archived session must be excluded"
    assert ids_in_order[0] == b["id"], "newest-first ordering by updated_at"
    assert ids_in_order[1] == a["id"]


def test_get_intake_session_returns_row_or_none(
    store: RuntimeStateStore,
) -> None:
    session = intake_module.create_intake_session(store)

    fetched = intake_module.get_intake_session(store, session_id=session["id"])
    assert fetched is not None
    assert fetched["id"] == session["id"]

    missing = intake_module.get_intake_session(store, session_id=999_999)
    assert missing is None


def test_patch_current_step_only_preserves_state_json(
    store: RuntimeStateStore,
) -> None:
    """Patching only ``current_step`` must not touch ``state_json``.

    Regression guard: the SQL builder must not include ``state_json = ?``
    in the SET list when the caller didn't provide one, or unrelated
    authoring state would silently get clobbered.
    """

    created = intake_module.create_intake_session(store)
    intake_module.patch_intake_session(
        store,
        session_id=created["id"],
        state_json={"role_basics": {"function": "Engineering"}},
    )

    patched = intake_module.patch_intake_session(
        store, session_id=created["id"], current_step="role_basics"
    )
    assert patched is not None
    assert patched["current_step"] == "role_basics"
    assert patched["state_json"] == {"role_basics": {"function": "Engineering"}}
    assert patched["updated_at"] >= created["updated_at"]


def test_patch_state_json_only_preserves_current_step(
    store: RuntimeStateStore,
) -> None:
    """Patching only ``state_json`` must not touch ``current_step``."""

    created = intake_module.create_intake_session(store)
    intake_module.patch_intake_session(
        store, session_id=created["id"], current_step="role_framing"
    )

    patched = intake_module.patch_intake_session(
        store,
        session_id=created["id"],
        state_json={"good_looks_like": "10x platform engineer"},
    )
    assert patched is not None
    assert patched["current_step"] == "role_framing"
    assert patched["state_json"] == {"good_looks_like": "10x platform engineer"}


def test_patch_both_fields_updates_both(
    store: RuntimeStateStore,
) -> None:
    created = intake_module.create_intake_session(store)
    patched = intake_module.patch_intake_session(
        store,
        session_id=created["id"],
        current_step="synthesis",
        state_json={"locked": True, "notes": ["seed1", "seed2"]},
        role_title="Staff ML Engineer",
    )
    assert patched is not None
    assert patched["current_step"] == "synthesis"
    assert patched["state_json"] == {"locked": True, "notes": ["seed1", "seed2"]}
    assert patched["role_title"] == "Staff ML Engineer"


def test_patch_missing_session_returns_none(
    store: RuntimeStateStore,
) -> None:
    result = intake_module.patch_intake_session(
        store, session_id=42_424_242, current_step="welcome"
    )
    assert result is None


def test_delete_intake_session_returns_true_on_hit_and_removes_row(
    store: RuntimeStateStore,
) -> None:
    session = intake_module.create_intake_session(store)
    assert intake_module.delete_intake_session(
        store, session_id=session["id"]
    ) is True
    assert intake_module.get_intake_session(
        store, session_id=session["id"]
    ) is None


def test_delete_missing_session_returns_false(
    store: RuntimeStateStore,
) -> None:
    assert intake_module.delete_intake_session(
        store, session_id=999_999
    ) is False


# ---------------------------------------------------------------------------
# Migration idempotency
# ---------------------------------------------------------------------------


def test_migrate_is_idempotent_for_intake_sessions(tmp_path: Path) -> None:
    """Running ``_migrate`` twice on a fresh DB must be a no-op.

    Constructs a store (which runs ``initialize`` → ``_migrate``), then
    re-invokes ``_migrate`` on a fresh connection. Verifies exactly one
    ``intake_sessions`` table exists and the index is present once.
    """

    store = _make_store(tmp_path)

    with store.connect() as conn:
        # First _migrate happened during __init__. Run it again on the
        # same DB — must not error.
        store._migrate(conn)

        tables = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='intake_sessions'"
        ).fetchall()
        assert len(tables) == 1, "exactly one intake_sessions table"

        indexes = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name='idx_intake_sessions_active'"
        ).fetchall()
        assert len(indexes) == 1, "exactly one idx_intake_sessions_active index"

    # Sanity: the table is usable after re-migration.
    session = intake_module.create_intake_session(store)
    assert session["current_step"] == "welcome"


# ---------------------------------------------------------------------------
# API endpoint coverage
# ---------------------------------------------------------------------------


def test_post_create_returns_201_with_session_envelope(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/intake/sessions",
        json={"role_title": "Director of Talent Strategy"},
    )
    assert response.status_code == 201

    body = response.json()
    assert body["slice"] == "v0-onboarding-slice-1"
    session = body["session"]
    assert session["role_title"] == "Director of Talent Strategy"
    assert session["current_step"] == "welcome"
    assert session["state_json"] == {}
    assert isinstance(session["id"], int)


def test_post_create_with_extra_field_returns_422(
    api_client: TestClient,
) -> None:
    """Slice 1B contract: ``ConfigDict(extra="forbid")`` rejects unknown fields.

    Mirrors the existing wire-discipline pattern from
    :class:`LaunchLinkedInRequest` so onboarding-flow callers can't smuggle
    state through the API by adding extra keys.
    """

    response = api_client.post(
        "/api/intake/sessions",
        json={"role_title": "X", "future_field_we_havent_added": True},
    )
    assert response.status_code == 422


def test_get_list_returns_active_sessions_envelope(
    api_client: TestClient,
) -> None:
    api_client.post("/api/intake/sessions", json={"role_title": "alpha"})
    api_client.post("/api/intake/sessions", json={"role_title": "beta"})

    response = api_client.get("/api/intake/sessions")
    assert response.status_code == 200
    body = response.json()
    assert body["slice"] == "v0-onboarding-slice-1"
    assert len(body["sessions"]) == 2
    titles = {s["role_title"] for s in body["sessions"]}
    assert titles == {"alpha", "beta"}


def test_get_one_returns_session(api_client: TestClient) -> None:
    created = api_client.post(
        "/api/intake/sessions", json={"role_title": "deep"}
    ).json()["session"]

    response = api_client.get(f"/api/intake/sessions/{created['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["session"]["id"] == created["id"]


def test_get_one_missing_returns_404(api_client: TestClient) -> None:
    response = api_client.get("/api/intake/sessions/999999")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"] == "intake_session_not_found"
    assert detail["id"] == 999999


def test_patch_updates_fields_and_returns_session(
    api_client: TestClient,
) -> None:
    created = api_client.post(
        "/api/intake/sessions", json={"role_title": "to-be-patched"}
    ).json()["session"]

    response = api_client.patch(
        f"/api/intake/sessions/{created['id']}",
        json={
            "current_step": "exemplars",
            "state_json": {"exemplars": ["alice", "bob"]},
        },
    )
    assert response.status_code == 200
    session = response.json()["session"]
    assert session["current_step"] == "exemplars"
    assert session["state_json"] == {"exemplars": ["alice", "bob"]}
    # Untouched field is preserved.
    assert session["role_title"] == "to-be-patched"


def test_patch_missing_returns_404(api_client: TestClient) -> None:
    response = api_client.patch(
        "/api/intake/sessions/424242",
        json={"current_step": "welcome"},
    )
    assert response.status_code == 404


def test_patch_extra_field_returns_422(api_client: TestClient) -> None:
    created = api_client.post(
        "/api/intake/sessions", json={"role_title": "x"}
    ).json()["session"]

    response = api_client.patch(
        f"/api/intake/sessions/{created['id']}",
        json={"unknown_field": "boom"},
    )
    assert response.status_code == 422


def test_delete_returns_envelope_and_removes_session(
    api_client: TestClient,
) -> None:
    created = api_client.post(
        "/api/intake/sessions", json={"role_title": "doomed"}
    ).json()["session"]

    response = api_client.delete(f"/api/intake/sessions/{created['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "slice": "v0-onboarding-slice-1",
        "deleted": True,
        "id": created["id"],
    }

    assert api_client.get(
        f"/api/intake/sessions/{created['id']}"
    ).status_code == 404


def test_delete_missing_returns_404(api_client: TestClient) -> None:
    response = api_client.delete("/api/intake/sessions/424242")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"] == "intake_session_not_found"
    assert detail["id"] == 424242
