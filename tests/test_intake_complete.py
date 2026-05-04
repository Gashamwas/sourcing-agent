"""Tests for the Phase D Slice D3 intake-complete endpoint
(``POST /api/intake/sessions/{id}/complete``).

The endpoint is the wizard's terminal call: it validates
``state_json["v2_draft"]`` against the V2 schema, writes a fresh
``config/<role-slug>/brief.json`` via the shared atomic writer, and
stamps the session as completed with a freshly-computed brief_id.

Pins:

- 422 on missing or invalid v2_draft (carries missing_keys/invalid_keys).
- 404 on unknown session id.
- 409 on target-dir name collision.
- 200 on success: writes the brief, snapshots a versions/<stamp>.json,
  marks the session ``current_step="completed"``, sets
  ``brief_id_draft``, returns the same brief_id the brief library
  would compute for the new file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _v2_minimal(role: str = "Test Role") -> dict:
    """Minimal V2 brief that passes validate_v2_brief."""
    return {
        "role_title": role,
        "id": role.lower().replace(" ", "_"),
        "linkedin_project_id": role.lower().replace(" ", "_"),
        "capability_areas": [
            {
                "name": "Product engineering",
                "description": "Ships customer-facing systems end-to-end.",
            }
        ],
        "depth_distinction": {
            "builder_definition": "Owns architecture and ships.",
            "user_definition": "Maintains existing features.",
            "edge_case_guidance": "Borderline = full eval.",
        },
        "non_fit_patterns": [],
        "target_modules": ["linkedin"],
    }


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Spin up TestClient with both _PROJECT_ROOT and the intake DB
    isolated to tmp_path. The intake DB lives at
    ``output/intake/intake_sessions.sqlite3`` by default; redirecting
    via ``CLORIS_OUTPUT_ROOT`` keeps the test hermetic.
    """

    from cloris.app import create_app
    from cloris import api as cloris_api

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cloris_api, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cloris_api, "_CONFIG_DIR", config_dir)

    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CLORIS_OUTPUT_ROOT", str(output_dir))

    return TestClient(create_app())


def _create_session_with_draft(
    client: TestClient, draft: dict | None
) -> int:
    """Helper: create a session and patch state_json.v2_draft = draft.
    Returns the session id.
    """

    create = client.post("/api/intake/sessions", json={})
    assert create.status_code == 201, create.text
    session_id: int = create.json()["session"]["id"]

    if draft is not None:
        patch = client.patch(
            f"/api/intake/sessions/{session_id}",
            json={"state_json": {"v2_draft": draft}},
        )
        assert patch.status_code == 200, patch.text
    return session_id


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_complete_writes_brief_and_marks_session_completed(
    client: TestClient, tmp_path: Path
) -> None:
    draft = _v2_minimal("Forward Deployed Engineer")
    session_id = _create_session_with_draft(client, draft)

    response = client.post(
        f"/api/intake/sessions/{session_id}/complete"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["slice"] == "v0-onboarding-slice-1"
    # Session marked completed with brief_id_draft populated.
    assert body["session"]["current_step"] == "completed"
    assert body["session"]["completed_at"] is not None
    assert body["session"]["brief_id_draft"] == body["brief_id"]
    # Brief landed at the slugified role-title path under tmp config.
    # slugify_output_component lowercases + underscores non-alnum.
    assert "forward_deployed_engineer" in body["brief_path"]
    expected_path = tmp_path / body["brief_path"]
    assert expected_path.is_file()
    on_disk = json.loads(expected_path.read_text())
    assert on_disk["role_title"] == draft["role_title"]
    assert on_disk["target_modules"] == ["linkedin"]


def test_complete_snapshots_to_versions_dir(
    client: TestClient, tmp_path: Path
) -> None:
    """The shared brief writer must mirror D2's contract — canonical
    first, then snapshot to versions/<timestamp>.json."""

    draft = _v2_minimal("Versioned Role")
    session_id = _create_session_with_draft(client, draft)

    response = client.post(
        f"/api/intake/sessions/{session_id}/complete"
    )

    assert response.status_code == 200, response.text
    brief_path = tmp_path / response.json()["brief_path"]
    versions_dir = brief_path.parent / "versions"
    assert versions_dir.is_dir()
    snapshots = list(versions_dir.glob("*.json"))
    assert len(snapshots) == 1, snapshots
    snap_payload = json.loads(snapshots[0].read_text())
    canon_payload = json.loads(brief_path.read_text())
    assert snap_payload == canon_payload


def test_complete_brief_id_matches_library_recompute(
    client: TestClient, tmp_path: Path
) -> None:
    """The freshly-written brief must compute the SAME brief_id the
    brief library uses (linkedin_state_key over the same file). If
    these diverge, runs spawned from this brief would be unjoinable
    with the brief catalog — Phase F's identity layer would be wrong.
    """

    draft = _v2_minimal("Identity Match Role")
    session_id = _create_session_with_draft(client, draft)

    response = client.post(
        f"/api/intake/sessions/{session_id}/complete"
    )
    assert response.status_code == 200, response.text
    server_brief_id = response.json()["brief_id"]

    brief_path = tmp_path / response.json()["brief_path"]
    from shared.output_paths import linkedin_state_key

    library_brief_id = linkedin_state_key(brief_path=str(brief_path))
    assert server_brief_id == library_brief_id


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------


def test_complete_missing_v2_draft_returns_422(client: TestClient) -> None:
    session_id = _create_session_with_draft(client, draft=None)

    response = client.post(
        f"/api/intake/sessions/{session_id}/complete"
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "invalid_v2_brief"
    assert "v2_draft" in detail["missing_keys"]


def test_complete_invalid_v2_draft_returns_422(client: TestClient) -> None:
    """Draft missing required V2 keys → 422 with structured detail."""

    bad_draft = {
        "role_title": "Bad Role",
        # capability_areas + depth_distinction missing
    }
    session_id = _create_session_with_draft(client, bad_draft)

    response = client.post(
        f"/api/intake/sessions/{session_id}/complete"
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "invalid_v2_brief"
    assert "capability_areas" in detail["missing_keys"]
    assert "depth_distinction" in detail["missing_keys"]


def test_complete_unknown_session_returns_404(client: TestClient) -> None:
    response = client.post("/api/intake/sessions/9999999/complete")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "intake_session_not_found"


# ---------------------------------------------------------------------------
# Collision
# ---------------------------------------------------------------------------


def test_complete_collision_with_existing_brief_returns_409(
    client: TestClient, tmp_path: Path
) -> None:
    """If config/<role-slug>/brief.json already exists, 409 protects
    the recruiter from accidentally overwriting an existing brief.
    """

    # Pre-seed an existing brief at the target path. slug is the
    # slugify_output_component output: lowercase + underscores.
    role = "Existing Role"
    slug = "existing_role"
    target_dir = tmp_path / "config" / slug
    target_dir.mkdir(parents=True)
    (target_dir / "brief.json").write_text(json.dumps(_v2_minimal(role)))

    draft = _v2_minimal(role)
    session_id = _create_session_with_draft(client, draft)

    response = client.post(
        f"/api/intake/sessions/{session_id}/complete"
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "brief_already_exists"
    assert detail["slug"] == slug


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_complete_session_disappeared_mid_complete_returns_410(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Race window: between the ``get_intake_session`` check at the
    top of the handler and the ``complete_intake_session`` stamp at
    the bottom, a parallel DELETE removes the session row. By that
    point ``write_brief_atomic`` has already succeeded, so the brief
    is on disk. The endpoint must return 410 Gone with structured
    detail (brief_id + brief_path) so the wizard can recover via
    the brief library — not crash on an AssertionError.
    """

    draft = _v2_minimal("Racy Role")
    session_id = _create_session_with_draft(client, draft)

    from cloris import api as cloris_api
    from cloris import intake_sessions as intake_sessions_module

    def racy_complete(*, store, session_id: int, brief_id: str) -> None:
        # Simulate a parallel DELETE that wins the race after the
        # brief has been written but before completion is stamped.
        with store.connect() as conn:
            conn.execute(
                "DELETE FROM intake_sessions WHERE id = ?", (session_id,)
            )
        return None

    monkeypatch.setattr(
        intake_sessions_module, "complete_intake_session", racy_complete
    )

    response = client.post(
        f"/api/intake/sessions/{session_id}/complete"
    )

    assert response.status_code == 410, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "intake_session_gone_after_complete"
    assert "brief_id" in detail and detail["brief_id"]
    assert "brief_path" in detail and detail["brief_path"]
    # The brief file landed before the race — recovery path is via
    # the brief library scanning config/<slug>/brief.json.
    brief_path = tmp_path / detail["brief_path"]
    assert brief_path.is_file()
    assert (cloris_api._CONFIG_DIR / "racy_role" / "brief.json").is_file()


def test_complete_is_safe_to_call_twice_via_collision(
    client: TestClient, tmp_path: Path
) -> None:
    """First call writes the brief and returns 200. Second call hits
    409 because the brief now exists at the target slug — the wizard
    treats that as a "this is already done" signal, not a hard error.
    """

    draft = _v2_minimal("Idempotent Role")
    session_id = _create_session_with_draft(client, draft)

    first = client.post(f"/api/intake/sessions/{session_id}/complete")
    assert first.status_code == 200

    second = client.post(f"/api/intake/sessions/{session_id}/complete")
    assert second.status_code == 409
