"""Tests for the Phase D Slice D2 brief detail / edit endpoints
(``GET /api/brief/{brief_id}`` + ``PUT /api/brief/{brief_id}``).

Pins the contract:

- GET returns the full V2/legacy partition (``v2_data``,
  ``preserved_legacy``, ``deprecated_keys``, ``unknown_keys``) so
  PUT can roundtrip without a backend disk re-read.
- PUT rebuilds full payload as ``v2_data ∪ preserved_legacy``,
  validates V2 portion, atomic-writes canonical FIRST then copies
  to ``versions/<timestamp>.json`` (architectural-fit critique catch
  on ordering).
- Flat → nested migration on first edit (Fork C); brief_id stays
  stable post-migration (since ``linkedin_state_key`` reads brief
  content, not path).
- 422 on V2-validation failures; 404 on unknown brief_id.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _write_brief(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _v2_minimal(role: str = "Test Role") -> dict:
    return {
        "role_title": role,
        "id": role.lower().replace(" ", "_"),
        # Use a stable id so linkedin_state_key returns a deterministic
        # value derived from the payload (NOT from the file path).
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
    }


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Spin up a TestClient against an isolated tmp config dir.

    Patches ``_PROJECT_ROOT`` and ``_CONFIG_DIR`` on the api module so
    the GET/PUT handlers walk our temp catalog instead of the real
    project tree.
    """

    from cloris.app import create_app
    from cloris import api as cloris_api

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cloris_api, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cloris_api, "_CONFIG_DIR", config_dir)

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# GET /api/brief/{brief_id}
# ---------------------------------------------------------------------------


def test_get_brief_returns_v2_legacy_partition(
    client: TestClient, tmp_path: Path
) -> None:
    """The wire shape carries v2_data + preserved_legacy + deprecated_keys
    + unknown_keys so PUT can rebuild without disk re-read."""

    config_dir = tmp_path / "config" / "fde-nyc"
    payload = _v2_minimal("FDE NYC")
    payload["must_haves"] = ["legacy thing"]  # deprecated key
    payload["recruiter_notes"] = "recruiter-authored"  # unknown key
    _write_brief(config_dir / "brief.json", payload)

    # Resolve brief_id by computing the same hash the endpoint does.
    from shared.output_paths import linkedin_state_key

    brief_id = linkedin_state_key(brief_path=str(config_dir / "brief.json"))

    response = client.get(f"/api/brief/{brief_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["slice"] == "v0-brief-detail-1"
    assert body["brief_id"] == brief_id
    assert "capability_areas" in body["v2_data"]
    assert body["preserved_legacy"]["must_haves"] == ["legacy thing"]
    assert body["preserved_legacy"]["recruiter_notes"] == "recruiter-authored"
    assert "must_haves" in body["deprecated_keys"]
    assert "recruiter_notes" in body["unknown_keys"]
    assert body["was_flat"] is False
    assert body["version_count"] == 0


def test_get_brief_marks_flat_layout_with_was_flat_true(
    client: TestClient, tmp_path: Path
) -> None:
    flat_path = tmp_path / "config" / "brief-flat.json"
    payload = _v2_minimal("Flat Brief")
    _write_brief(flat_path, payload)

    from shared.output_paths import linkedin_state_key

    brief_id = linkedin_state_key(brief_path=str(flat_path))

    response = client.get(f"/api/brief/{brief_id}")

    assert response.status_code == 200
    assert response.json()["was_flat"] is True


def test_get_brief_unknown_id_returns_404(client: TestClient) -> None:
    response = client.get("/api/brief/totally_bogus_id")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "brief_not_found"


# ---------------------------------------------------------------------------
# PUT /api/brief/{brief_id}
# ---------------------------------------------------------------------------


def test_put_brief_writes_new_version_and_keeps_canonical_fresh(
    client: TestClient, tmp_path: Path
) -> None:
    """Architectural-fit critique catch: write canonical FIRST then copy
    to versions/. Test verifies the canonical never lags behind the
    versions/ snapshot."""

    config_dir = tmp_path / "config" / "fde"
    payload = _v2_minimal("FDE")
    _write_brief(config_dir / "brief.json", payload)

    from shared.output_paths import linkedin_state_key

    brief_id = linkedin_state_key(brief_path=str(config_dir / "brief.json"))

    # Edit: keep the V2 fields, change a depth_distinction line.
    edited_v2 = dict(payload)
    edited_v2["depth_distinction"] = {
        **edited_v2["depth_distinction"],
        "edge_case_guidance": "EDITED",
    }

    response = client.put(
        f"/api/brief/{brief_id}",
        json={
            "v2_data": edited_v2,
            "preserved_legacy": {},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert (
        body["v2_data"]["depth_distinction"]["edge_case_guidance"]
        == "EDITED"
    )
    assert body["version_count"] == 1

    # Canonical reflects the edit.
    canonical = json.loads((config_dir / "brief.json").read_text())
    assert (
        canonical["depth_distinction"]["edge_case_guidance"]
        == "EDITED"
    )

    # versions/ has exactly one snapshot, and it matches the canonical.
    versions_dir = config_dir / "versions"
    assert versions_dir.is_dir()
    snapshots = list(versions_dir.glob("*.json"))
    assert len(snapshots) == 1
    snapshot = json.loads(snapshots[0].read_text())
    assert snapshot == canonical


def test_put_brief_rebuilds_payload_from_preserved_legacy(
    client: TestClient, tmp_path: Path
) -> None:
    """Rebuild = v2_data ∪ preserved_legacy. Frontend decides what
    legacy keys survive; backend writes the union verbatim."""

    config_dir = tmp_path / "config" / "fde"
    payload = _v2_minimal("FDE")
    payload["calibration_examples"] = [{"who": "A", "verdict": "save"}]
    payload["recruiter_notes"] = "keep me"
    _write_brief(config_dir / "brief.json", payload)

    from shared.output_paths import linkedin_state_key

    brief_id = linkedin_state_key(brief_path=str(config_dir / "brief.json"))

    response = client.put(
        f"/api/brief/{brief_id}",
        json={
            "v2_data": _v2_minimal("FDE"),  # V2 unchanged
            "preserved_legacy": {
                # Drop calibration_examples; keep recruiter_notes.
                "recruiter_notes": "keep me",
            },
            "dropped_legacy_keys": ["calibration_examples"],
        },
    )

    assert response.status_code == 200
    canonical = json.loads((config_dir / "brief.json").read_text())
    assert "calibration_examples" not in canonical
    assert canonical["recruiter_notes"] == "keep me"
    assert "capability_areas" in canonical


def test_put_brief_migrates_flat_to_nested_on_first_edit(
    client: TestClient, tmp_path: Path
) -> None:
    """Fork C: D2 migrates flat → nested on first edit. brief_id stays
    stable because linkedin_state_key reads brief content not path."""

    flat_path = tmp_path / "config" / "brief-flat.json"
    payload = _v2_minimal("Flat Brief")
    _write_brief(flat_path, payload)

    from shared.output_paths import linkedin_state_key

    brief_id_before = linkedin_state_key(brief_path=str(flat_path))

    response = client.put(
        f"/api/brief/{brief_id_before}",
        json={
            "v2_data": _v2_minimal("Flat Brief"),
            "preserved_legacy": {},
        },
    )

    assert response.status_code == 200
    # Original flat path no longer exists.
    assert not flat_path.exists()
    # Nested path exists.
    nested_path = tmp_path / "config" / "brief-flat" / "brief.json"
    assert nested_path.exists()

    # brief_id is stable post-migration.
    brief_id_after = linkedin_state_key(brief_path=str(nested_path))
    assert brief_id_after == brief_id_before


def test_put_brief_invalid_v2_returns_422(
    client: TestClient, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config" / "fde"
    payload = _v2_minimal("FDE")
    _write_brief(config_dir / "brief.json", payload)

    from shared.output_paths import linkedin_state_key

    brief_id = linkedin_state_key(brief_path=str(config_dir / "brief.json"))

    response = client.put(
        f"/api/brief/{brief_id}",
        json={
            "v2_data": {"role_title": "Missing Required Fields"},
            "preserved_legacy": {},
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"]["error"] == "invalid_v2_brief"
    assert "capability_areas" in body["detail"]["missing_keys"]


def test_put_brief_unknown_id_returns_404(client: TestClient) -> None:
    response = client.put(
        "/api/brief/totally_bogus_id",
        json={"v2_data": _v2_minimal(), "preserved_legacy": {}},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "brief_not_found"


def test_put_brief_writes_new_version_per_edit(
    client: TestClient, tmp_path: Path
) -> None:
    """Two consecutive edits → two distinct version files."""

    config_dir = tmp_path / "config" / "fde"
    payload = _v2_minimal("FDE")
    _write_brief(config_dir / "brief.json", payload)

    from shared.output_paths import linkedin_state_key

    brief_id = linkedin_state_key(brief_path=str(config_dir / "brief.json"))

    for round_n in range(2):
        edited = dict(payload)
        edited["depth_distinction"] = {
            **edited["depth_distinction"],
            "edge_case_guidance": f"round-{round_n}",
        }
        # Tiny sleep-free counter via filename-time spread: the version
        # filename includes microseconds, so back-to-back edits get
        # distinct filenames in practice. If this flakes, pin a stamp
        # injection point.
        response = client.put(
            f"/api/brief/{brief_id}",
            json={"v2_data": edited, "preserved_legacy": {}},
        )
        assert response.status_code == 200

    snapshots = list((config_dir / "versions").glob("*.json"))
    assert len(snapshots) == 2


# ---------------------------------------------------------------------------
# Path 3 trial slice — source_config.linkedin round-trip via PUT
# ---------------------------------------------------------------------------
#
# The frontend's <LinkedInProjectEditor> writes the parsed project_id
# back through this same endpoint. These tests pin the round-trip
# semantic for two starting states:
#
# 1. The brief had no project_id at all (the "first time setting it"
#    case the trial recruiter hits via either the intake wizard or the
#    inline launch-readiness blocker).
# 2. The brief had only the flat legacy `linkedin_project_id` (the
#    state every brief in `config/` sits in today). Setting
#    source_config must preserve the flat field — flat lives in
#    preserved_legacy and the resolver still reads source_config first
#    via shared.brief_v2_schema.linkedin_project_id_from_brief.


def test_put_brief_sets_source_config_with_legacy_flat_field_present(
    client: TestClient, tmp_path: Path
) -> None:
    """Path 3 trial slice: the realistic "unconfigured" flow.

    Most briefs in `config/` already carry a flat `linkedin_project_id`
    by the time the F2 readiness blocker can fire — the field has been
    in the schema since Phase D. The trial flow is "recruiter pastes a
    URL, source_config gets the same project_id." State_key stays
    stable because the resolver was already returning that value.

    The truly-empty-brief case (no flat field, no source_config, no
    matching brief.id) is captured separately as a state-key-migration
    xfail below — it's a pre-existing PUT bug unrelated to Path 3."""

    config_dir = tmp_path / "config" / "fde"
    payload = _v2_minimal("FDE Pending")
    # Brief has the flat field but no source_config — exactly the
    # state every brief in config/ sits in today.
    payload["linkedin_project_id"] = "1990251114"
    _write_brief(config_dir / "brief.json", payload)

    from shared.output_paths import linkedin_state_key

    brief_id = linkedin_state_key(brief_path=str(config_dir / "brief.json"))
    assert brief_id == "1990251114"

    # The frontend reads via GET, mutates v2_data, writes via PUT.
    get_resp = client.get(f"/api/brief/{brief_id}")
    detail = get_resp.json()
    v2_data = dict(detail["v2_data"])
    v2_data["source_config"] = {"linkedin": {"project_id": "1990251114"}}

    response = client.put(
        f"/api/brief/{brief_id}",
        json={
            "v2_data": v2_data,
            "preserved_legacy": detail["preserved_legacy"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert (
        body["v2_data"]["source_config"]["linkedin"]["project_id"]
        == "1990251114"
    )

    canonical = json.loads((config_dir / "brief.json").read_text())
    assert (
        canonical["source_config"]["linkedin"]["project_id"] == "1990251114"
    )


def test_put_brief_sets_source_config_alongside_legacy_flat_field(
    client: TestClient, tmp_path: Path
) -> None:
    """Path 3 trial slice: migration from flat-only → flat + source_config.

    Every brief in config/ today carries `linkedin_project_id` at the
    top level. The Path 3 editor adds `source_config.linkedin.project_id`
    additively; the flat field stays in preserved_legacy and the
    resolver prefers source_config (verified separately in
    test_save_destination_config.py). State_key is stable because both
    paths produce the same value."""

    config_dir = tmp_path / "config" / "fde"
    payload = _v2_minimal("FDE Flat")
    payload["linkedin_project_id"] = "1990251114"  # flat legacy path
    _write_brief(config_dir / "brief.json", payload)

    from shared.output_paths import linkedin_state_key

    brief_id = linkedin_state_key(brief_path=str(config_dir / "brief.json"))

    # Read the partition the way the frontend does — separate v2 vs
    # legacy — then write source_config into v2 while preserving the
    # flat field in preserved_legacy.
    get_resp = client.get(f"/api/brief/{brief_id}")
    assert get_resp.status_code == 200
    detail = get_resp.json()
    v2_data = dict(detail["v2_data"])
    preserved_legacy = dict(detail["preserved_legacy"])
    # The flat field is unknown to V2 schema → lands in preserved_legacy.
    assert preserved_legacy.get("linkedin_project_id") == "1990251114"

    v2_data["source_config"] = {"linkedin": {"project_id": "1990251114"}}

    response = client.put(
        f"/api/brief/{brief_id}",
        json={"v2_data": v2_data, "preserved_legacy": preserved_legacy},
    )
    assert response.status_code == 200

    # Both paths now point at the same project_id; resolver still
    # prefers source_config but the flat field stays for any external
    # reader that hasn't migrated yet.
    canonical = json.loads((config_dir / "brief.json").read_text())
    assert (
        canonical["source_config"]["linkedin"]["project_id"] == "1990251114"
    )
    assert canonical["linkedin_project_id"] == "1990251114"

    # Brief id stays stable across the source_config addition — the
    # resolver-preferred value didn't change. State_dirs don't orphan.
    brief_id_after = linkedin_state_key(
        brief_path=str(config_dir / "brief.json")
    )
    assert brief_id_after == brief_id


def test_put_brief_updates_source_config_with_project_name(
    client: TestClient, tmp_path: Path
) -> None:
    """Path 3 trial slice: editor surfaces a project_name when the
    parser produces one (currently null; future Path 1 work fills from
    page title). PUT should accept it without disturbing the rest of
    the schema. State_key is stable because brief.linkedin_project_id
    matches the source_config project_id."""

    config_dir = tmp_path / "config" / "fde"
    payload = _v2_minimal("FDE With Name")
    payload["linkedin_project_id"] = "1990251114"
    _write_brief(config_dir / "brief.json", payload)

    from shared.output_paths import linkedin_state_key

    brief_id = linkedin_state_key(brief_path=str(config_dir / "brief.json"))

    get_resp = client.get(f"/api/brief/{brief_id}")
    assert get_resp.status_code == 200
    detail = get_resp.json()

    v2_data = dict(detail["v2_data"])
    v2_data["source_config"] = {
        "linkedin": {
            "project_id": "1990251114",
            "project_name": "Forward Deployed Engineer — NYC",
        }
    }

    response = client.put(
        f"/api/brief/{brief_id}",
        json={
            "v2_data": v2_data,
            "preserved_legacy": detail["preserved_legacy"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    li = body["v2_data"]["source_config"]["linkedin"]
    assert li["project_id"] == "1990251114"
    assert li["project_name"] == "Forward Deployed Engineer — NYC"


@pytest.mark.xfail(
    reason=(
        "Pre-existing PUT bug surfaced by Path 3 tests, NOT introduced "
        "by Path 3 itself. When source_config.linkedin.project_id "
        "differs from the resolver-fallback path "
        "(brief.linkedin_project_id → brief.id → stem), adding it "
        "migrates the state_key. The PUT handler's final step "
        "`return api_brief_detail(brief_id)` then 404s because the "
        "brief is now resolvable only under the new id. The on-disk "
        "write succeeds; the failing path is the response. Surfaced "
        "as adjacent issue per the commit-hygiene rule. Realistic "
        "Path 3 trial flow keeps state_key stable (covered above); "
        "this xfail documents the pre-existing edge."
    ),
    strict=True,
)
def test_put_brief_state_key_migration_returns_404_pre_existing_bug(
    client: TestClient, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config" / "fde"
    payload = _v2_minimal("Migration Edge")
    payload.pop("linkedin_project_id", None)
    # brief.id ≠ what the recruiter pastes — guarantees state-key
    # migration when source_config is set.
    payload["id"] = "old_id"
    _write_brief(config_dir / "brief.json", payload)

    from shared.output_paths import linkedin_state_key

    brief_id_before = linkedin_state_key(brief_path=str(config_dir / "brief.json"))
    assert brief_id_before == "old_id"

    edited_v2 = dict(payload)
    edited_v2["source_config"] = {"linkedin": {"project_id": "1990251114"}}

    response = client.put(
        f"/api/brief/{brief_id_before}",
        json={"v2_data": edited_v2, "preserved_legacy": {}},
    )
    # Path 3 fix — when the PUT bug is addressed, this should return
    # 200 and the response should carry the post-migration brief_id.
    assert response.status_code == 200
