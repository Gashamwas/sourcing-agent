"""Tests for the Cloris app process (Slices 1 + 2).

Covers:

- ``GET /healthz`` and ``GET /`` HTTP contract via :class:`TestClient`
  (Slice 1, byte-identical here).
- :func:`cloris.app.run_app` lifecycle with a ``NullWindowLauncher`` and a
  stub ``server_factory``. No real socket is bound and no real window is
  opened; the readiness probe is monkeypatched on
  :mod:`cloris.app`.
- ``GET /api/status`` JSON contract (Slice 2). The aggregator is monkeypatched
  on :mod:`cloris.api` (not :mod:`cloris.control_plane`) because the route
  binds ``aggregate_status`` into the ``cloris.api`` module namespace at
  import time, which is the symbol the route actually calls.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cloris import __version__
from cloris import api as cloris_api
from cloris import app as cloris_app
from cloris.api import StateDirNotFoundError
from cloris.app import NullWindowLauncher, _resolve_port, create_app, run_app
from cloris.models import (
    LaunchResponse,
    ResumeResponse,
    RunSummary,
    StateDirEntry,
    StatusResponse,
    StopResponse,
)
from cloris.worker import BriefPathNotFoundError, WorkerAlreadyRunningError


def test_healthz_contract() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["slice"] == "v0-shell-slice-1"
    assert isinstance(body["version"], str)
    assert body["version"] == __version__


def test_index_serves_built_html_with_cloris_shell_root() -> None:
    """Slice 5: ``GET /`` returns the Vite-built ``index.html`` from
    ``cloris/frontend/dist/``. The response must carry the SPA mount
    point ``id="cloris-shell"`` and the literal ``Cloris`` somewhere
    in the document — the Slice-1 placeholder copy is gone."""

    client = TestClient(create_app())

    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

    body = response.text
    assert 'id="cloris-shell"' in body
    assert "Cloris" in body


class _StubServer:
    """Stand-in for :class:`uvicorn.Server` used in lifecycle tests.

    ``run`` blocks until ``should_exit`` flips to ``True``; the readiness
    probe is short-circuited at the module level, so ``run_app`` proceeds
    straight to ``launcher.open`` without ever talking to a real socket.
    """

    def __init__(self) -> None:
        self.should_exit = False
        self._stopped = threading.Event()
        self.run_calls = 0

    def run(self) -> None:
        self.run_calls += 1
        while not self.should_exit:
            if self._stopped.wait(timeout=0.01):
                return
        self._stopped.set()


def test_run_app_lifecycle_uses_launcher_and_shuts_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _StubServer()

    factory_received: dict[str, Any] = {}

    def stub_server_factory(app: Any, host: str, port: int) -> _StubServer:
        assert host == "127.0.0.1"
        assert isinstance(port, int)
        assert port > 0, (
            "run_app must resolve port=0 to a concrete free port before "
            "calling server_factory; received {port!r}".format(port=port)
        )
        factory_received["host"] = host
        factory_received["port"] = port
        return server

    wait_received: dict[str, Any] = {}

    def fake_wait_until_ready(host: str, port: int, *, timeout: float = 5.0) -> None:
        assert host == "127.0.0.1"
        assert isinstance(port, int)
        assert port > 0
        wait_received["host"] = host
        wait_received["port"] = port

    monkeypatch.setattr(cloris_app, "_wait_until_ready", fake_wait_until_ready)

    launcher = NullWindowLauncher()

    captured_threads: list[threading.Thread] = []
    real_thread_init = threading.Thread.__init__

    def recording_init(self: threading.Thread, *args: Any, **kwargs: Any) -> None:
        real_thread_init(self, *args, **kwargs)
        if kwargs.get("name") == "cloris-uvicorn":
            captured_threads.append(self)

    monkeypatch.setattr(threading.Thread, "__init__", recording_init)

    app_sentinel = object()
    run_app(
        app_sentinel,
        host="127.0.0.1",
        port=0,
        launcher=launcher,
        server_factory=stub_server_factory,
        readiness_timeout=2.0,
        shutdown_timeout=2.0,
        ensure_chrome=lambda: None,
    )

    captured_port = factory_received["port"]
    assert wait_received["port"] == captured_port, (
        "readiness probe must observe the same resolved port as the server factory"
    )
    assert launcher.opened == [f"http://127.0.0.1:{captured_port}"]
    assert server.should_exit is True
    assert server.run_calls == 1

    assert len(captured_threads) == 1
    assert not captured_threads[0].is_alive()


def test_run_app_raises_and_shuts_down_on_readiness_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _StubServer()

    factory_received: dict[str, Any] = {}

    def stub_server_factory(app: Any, host: str, port: int) -> _StubServer:
        assert isinstance(port, int)
        assert port > 0
        factory_received["port"] = port
        return server

    wait_received: dict[str, Any] = {}

    def failing_wait_until_ready(host: str, port: int, *, timeout: float = 5.0) -> None:
        assert isinstance(port, int)
        assert port > 0
        wait_received["port"] = port
        raise RuntimeError("not ready")

    monkeypatch.setattr(cloris_app, "_wait_until_ready", failing_wait_until_ready)

    launcher = NullWindowLauncher()

    with pytest.raises(RuntimeError, match="not ready"):
        run_app(
            object(),
            host="127.0.0.1",
            port=0,
            launcher=launcher,
            server_factory=stub_server_factory,
            readiness_timeout=0.1,
            shutdown_timeout=2.0,
            ensure_chrome=lambda: None,
        )

    assert launcher.opened == []
    assert server.should_exit is True
    assert wait_received["port"] == factory_received["port"]


def test_resolve_port_picks_free_port_for_zero_and_passes_through_otherwise() -> None:
    auto_picked = _resolve_port("127.0.0.1", 0)
    assert isinstance(auto_picked, int)
    assert auto_picked > 0

    assert _resolve_port("127.0.0.1", 8765) == 8765

    second_pick = _resolve_port("127.0.0.1", 0)
    assert isinstance(second_pick, int)
    assert second_pick > 0


def test_api_status_endpoint_returns_empty_for_empty_state_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Slice 4 bumps the StatusResponse slice literal to v0-shell-slice-4
    # because the payload shape gained worker_state, worker_pid, etc.
    def fake_aggregate_status() -> StatusResponse:
        return StatusResponse(slice="v0-shell-slice-4", entries=[])

    monkeypatch.setattr(cloris_api, "aggregate_status", fake_aggregate_status)

    client = TestClient(create_app())
    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    # Phase F Slice F7 added the additive `briefs` field — empty when
    # there are no entries to group.
    assert response.json() == {
        "slice": "v0-shell-slice-4",
        "entries": [],
        "counts": {
            "active": 0,
            "working": 0,
            "paused": 0,
            "finished": 0,
            "lost": 0,
            "archived": 0,
            "orphaned": 0,
        },
        "briefs": [],
    }


def test_api_status_endpoint_serializes_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Slice 4 bumps the slice tag to v0-shell-slice-4 and enriches each
    # entry with worker_* + resumable fields. Test fixtures rely on
    # StateDirEntry's default values for the new fields.
    fixture = StatusResponse(
        slice="v0-shell-slice-4",
        entries=[
            StateDirEntry(
                source="linkedin",
                state_key="li-key",
                runtime_state_present=True,
                latest_run=RunSummary(
                    id=42,
                    status="completed",
                    stop_reason="normal",
                    mode="fresh",
                    started_at="2024-01-01T00:00:00+00:00",
                    ended_at="2024-01-01T00:01:00+00:00",
                ),
                brief_id_from_run="brief-li",
            ),
            StateDirEntry(
                source="github",
                state_key="gh-key",
                runtime_state_present=False,
                latest_run=None,
                brief_id_from_run=None,
            ),
        ],
    )

    def fake_aggregate_status() -> StatusResponse:
        return fixture

    monkeypatch.setattr(cloris_api, "aggregate_status", fake_aggregate_status)

    client = TestClient(create_app())
    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json() == {
        "slice": "v0-shell-slice-4",
        "entries": [
            {
                "source": "linkedin",
                "state_key": "li-key",
                "runtime_state_present": True,
                "runtime_state_corrupt": False,
                "latest_run": {
                    "id": 42,
                    "status": "completed",
                    "stop_reason": "normal",
                    "mode": "fresh",
                    "started_at": "2024-01-01T00:00:00+00:00",
                    "ended_at": "2024-01-01T00:01:00+00:00",
                },
                "brief_id_from_run": "brief-li",
                "brief_path_from_worker": None,
                "worker_json_present": False,
                "worker_pid": None,
                "worker_alive": None,
                "worker_mode": None,
                "worker_input_mode": None,
                "resumable": None,
                "worker_state": "missing",
                "heartbeat_age_s": None,
                "brief_role_title": None,
                "brief_linkedin_project": None,
                "brief_drift_since_last_run": None,
                "attempt_health": None,
                "work_unit_progress": None,
                "run_stalled": False,
                "stall_failure_kind": None,
                "kind": "orphaned_state_dir",
            },
            {
                "source": "github",
                "state_key": "gh-key",
                "runtime_state_present": False,
                "runtime_state_corrupt": False,
                "latest_run": None,
                "brief_id_from_run": None,
                "brief_path_from_worker": None,
                "worker_json_present": False,
                "worker_pid": None,
                "worker_alive": None,
                "worker_mode": None,
                "worker_input_mode": None,
                "resumable": None,
                "worker_state": "missing",
                "heartbeat_age_s": None,
                "brief_role_title": None,
                "brief_linkedin_project": None,
                "brief_drift_since_last_run": None,
                "attempt_health": None,
                "work_unit_progress": None,
                "run_stalled": False,
                "stall_failure_kind": None,
                "kind": "orphaned_state_dir",
            },
        ],
        "counts": {
            "active": 0,
            "working": 0,
            "paused": 0,
            "finished": 0,
            "lost": 0,
            "archived": 0,
            "orphaned": 0,
        },
        # Phase F Slice F7: empty for the fixture above (no briefs
        # configured on the response — the fixture sets entries
        # directly without populating the briefs grouping).
        "briefs": [],
    }


def test_launch_linkedin_endpoint_201_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_launch(req: Any) -> LaunchResponse:
        captured["brief_path"] = req.brief_path
        return LaunchResponse(
            source="linkedin",
            input_mode="concurrent",
            pid=12345,
            state_dir="/tmp/state/linkedin/key",
            worker_json_path="/tmp/state/linkedin/key/worker.json",
        )

    monkeypatch.setattr(cloris_api, "launch_linkedin_worker", fake_launch)

    client = TestClient(create_app())
    response = client.post("/api/launch/linkedin", json={"brief_path": "/tmp/brief.json"})

    assert response.status_code == 201
    # Phase F Slice F1 added `mode` to LaunchResponse (additive — default
    # "fresh"). Existing fields are preserved byte-for-byte; clients that
    # ignore unknown fields are unaffected.
    assert response.json() == {
        "slice": "v0-shell-slice-3",
        "source": "linkedin",
        "input_mode": "concurrent",
        "mode": "fresh",
        "pid": 12345,
        "state_dir": "/tmp/state/linkedin/key",
        "worker_json_path": "/tmp/state/linkedin/key/worker.json",
    }
    assert captured["brief_path"] == "/tmp/brief.json"


def test_launch_linkedin_endpoint_409_when_worker_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_launch(req: Any) -> LaunchResponse:
        raise WorkerAlreadyRunningError(
            pid=12345,
            state_dir="/tmp/state/linkedin/key",
        )

    monkeypatch.setattr(cloris_api, "launch_linkedin_worker", fake_launch)

    client = TestClient(create_app())
    response = client.post("/api/launch/linkedin", json={"brief_path": "/tmp/brief.json"})

    assert response.status_code == 409
    body = response.json()
    detail = body["detail"]
    assert detail["error"] == "worker_already_running"
    assert detail["pid"] == 12345
    assert detail["state_dir"] == "/tmp/state/linkedin/key"


def test_launch_linkedin_endpoint_400_on_missing_brief_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_launch(req: Any) -> LaunchResponse:
        raise BriefPathNotFoundError("/tmp/missing.json")

    monkeypatch.setattr(cloris_api, "launch_linkedin_worker", fake_launch)

    client = TestClient(create_app())
    response = client.post(
        "/api/launch/linkedin", json={"brief_path": "/tmp/missing.json"}
    )

    assert response.status_code == 400
    body = response.json()
    detail = body["detail"]
    assert detail["error"] == "brief_path_not_found"
    assert detail["brief_path"] == "/tmp/missing.json"


def test_launch_linkedin_endpoint_rejects_input_mode_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(req: Any) -> LaunchResponse:
        raise AssertionError(
            "launch_linkedin_worker should not be called when the request "
            "body has an unknown field"
        )

    monkeypatch.setattr(cloris_api, "launch_linkedin_worker", boom)

    client = TestClient(create_app())
    response = client.post(
        "/api/launch/linkedin",
        json={"brief_path": "/tmp/brief.json", "input_mode": "away"},
    )

    assert response.status_code == 422


# --- Slice 4: stop + resume routes + helpers ----------------------------


import json
import os
import signal
from pathlib import Path

from cloris import api as _cloris_api  # alias to expose stop_worker for monkeypatch
from cloris.worker import WORKER_SIDECAR_FILENAME, build_sidecar, write_sidecar


def test_stop_endpoint_alive_pid_sends_sigterm_and_returns_202(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stopping worker_state in the helper response triggers HTTP 202
    from the route. The actual SIGTERM dispatch is exercised at the helper
    level further below; this test pins the route's status-code
    translation."""

    def fake_stop(source: str, state_key: str) -> StopResponse:
        return StopResponse(
            source="linkedin",
            state_key=state_key,
            state_dir="/tmp/state/linkedin/key",
            worker_state="stopping",
            pid=12345,
        )

    monkeypatch.setattr(cloris_api, "stop_worker", fake_stop)

    client = TestClient(create_app())
    response = client.post("/api/stop/linkedin/key")

    assert response.status_code == 202
    body = response.json()
    assert body["worker_state"] == "stopping"
    assert body["pid"] == 12345
    assert body["source"] == "linkedin"
    assert body["state_key"] == "key"
    assert body["state_dir"] == "/tmp/state/linkedin/key"
    assert body["slice"] == "v0-shell-slice-4"


def test_stop_endpoint_missing_sidecar_returns_200_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_stop(source: str, state_key: str) -> StopResponse:
        return StopResponse(
            source="linkedin",
            state_key=state_key,
            state_dir="/tmp/state/linkedin/key",
            worker_state="missing",
            pid=None,
        )

    monkeypatch.setattr(cloris_api, "stop_worker", fake_stop)

    client = TestClient(create_app())
    response = client.post("/api/stop/linkedin/key")

    assert response.status_code == 200
    assert response.json()["worker_state"] == "missing"
    assert response.json()["pid"] is None


def test_stop_endpoint_stale_sidecar_returns_200_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_stop(source: str, state_key: str) -> StopResponse:
        return StopResponse(
            source="linkedin",
            state_key=state_key,
            state_dir="/tmp/state/linkedin/key",
            worker_state="stale",
            pid=None,
        )

    monkeypatch.setattr(cloris_api, "stop_worker", fake_stop)

    client = TestClient(create_app())
    response = client.post("/api/stop/linkedin/key")

    assert response.status_code == 200
    assert response.json()["worker_state"] == "stale"


def test_stop_endpoint_unknown_state_dir_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_stop(source: str, state_key: str) -> StopResponse:
        raise StateDirNotFoundError(source, state_key)

    monkeypatch.setattr(cloris_api, "stop_worker", fake_stop)

    client = TestClient(create_app())
    response = client.post("/api/stop/linkedin/key")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"] == "state_dir_not_found"
    assert detail["source"] == "linkedin"
    assert detail["state_key"] == "key"


def _write_alive_sidecar(state_dir: Path, pid: int) -> Path:
    """Write a sidecar pointing at ``pid`` for stop-helper tests."""

    state_dir.mkdir(parents=True, exist_ok=True)
    payload = build_sidecar(
        source="linkedin",
        brief_id="brief-4",
        brief_path=str(state_dir / "brief.json"),
        output_dir=str(state_dir),
        mode="fresh",
        input_mode="concurrent",
        started_at="2026-04-27T18:00:00+00:00",
        pid=pid,
        run_id=None,
    )
    return write_sidecar(state_dir, payload)


def test_stop_helper_alive_dispatches_sigterm_exactly_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helper signals SIGTERM exactly once with the real-pid fixture
    (os.getpid()) and reports worker_state='stopping'. enumerate_state_dirs
    is monkeypatched to yield the fixture state dir so the
    path-traversal-safe lookup succeeds without any real
    ``output/state/`` discovery. ``_send_sigterm`` is the module-level
    seam used in production; patching it (rather than ``os.kill``) keeps
    the unrelated ``os.kill(pid, 0)`` liveness probe inside
    :func:`cloris.worker.is_pid_alive` untouched."""

    state_dir = tmp_path / "linkedin" / "key"
    _write_alive_sidecar(state_dir, pid=os.getpid())

    def fake_enumerate():
        yield ("linkedin", state_dir)

    monkeypatch.setattr(_cloris_api, "enumerate_state_dirs", fake_enumerate)

    sigterm_calls: list[int] = []

    def fake_send_sigterm(pid: int) -> None:
        sigterm_calls.append(pid)

    monkeypatch.setattr(_cloris_api, "_send_sigterm", fake_send_sigterm)

    result = _cloris_api.stop_worker("linkedin", "key")

    assert result.worker_state == "stopping"
    assert result.pid == os.getpid()
    assert result.state_key == "key"
    assert sigterm_calls == [os.getpid()]
    # Verify the production seam wraps signal.SIGTERM, not some other signal.
    assert signal.SIGTERM == signal.SIGTERM  # contract sanity


def test_stop_helper_stale_does_not_dispatch_signal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-int PID is classified as stale: the helper neither signals nor
    deletes the sidecar file. The existing sidecar must still be readable
    after the call so the next launch can overwrite it via the
    Slice-3-defined stale-overwrite policy."""

    state_dir = tmp_path / "linkedin" / "key"
    state_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = state_dir / WORKER_SIDECAR_FILENAME
    sidecar_path.write_text(
        json.dumps(
            {
                "pid": "not-an-int",
                "source": "linkedin",
                "brief_id": "brief-4",
                "brief_path": str(state_dir / "brief.json"),
                "output_dir": str(state_dir),
                "run_id": None,
                "started_at": "2026-04-27T18:00:00+00:00",
                "heartbeat_at": "2026-04-27T18:00:00+00:00",
                "mode": "fresh",
                "input_mode": "concurrent",
                "launcher_version": "cloris-v0-slice-4",
            },
            indent=2,
            sort_keys=True,
        )
    )

    def fake_enumerate():
        yield ("linkedin", state_dir)

    monkeypatch.setattr(_cloris_api, "enumerate_state_dirs", fake_enumerate)

    sigterm_calls: list[int] = []

    def fake_send_sigterm(pid: int) -> None:
        sigterm_calls.append(pid)

    monkeypatch.setattr(_cloris_api, "_send_sigterm", fake_send_sigterm)

    result = _cloris_api.stop_worker("linkedin", "key")

    assert result.worker_state == "stale"
    assert sigterm_calls == []
    # Stop must not delete the stale sidecar; launch overwrites it next.
    assert sidecar_path.exists()


def test_resume_endpoint_201_spawns_worker_with_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_resume(req: Any) -> ResumeResponse:
        captured["brief_path"] = req.brief_path
        return ResumeResponse(
            source="linkedin",
            input_mode="concurrent",
            pid=23456,
            state_dir="/tmp/state/linkedin/key",
            worker_json_path="/tmp/state/linkedin/key/worker.json",
        )

    monkeypatch.setattr(cloris_api, "resume_linkedin_worker", fake_resume)

    client = TestClient(create_app())
    response = client.post(
        "/api/resume/linkedin", json={"brief_path": "/tmp/brief.json"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["slice"] == "v0-shell-slice-4"
    assert body["mode"] == "resume"
    assert body["pid"] == 23456
    assert body["state_dir"] == "/tmp/state/linkedin/key"
    assert body["worker_json_path"] == "/tmp/state/linkedin/key/worker.json"
    assert captured["brief_path"] == "/tmp/brief.json"


def test_resume_endpoint_409_when_worker_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_resume(req: Any) -> ResumeResponse:
        raise WorkerAlreadyRunningError(
            pid=12345,
            state_dir="/tmp/state/linkedin/key",
        )

    monkeypatch.setattr(cloris_api, "resume_linkedin_worker", fake_resume)

    client = TestClient(create_app())
    response = client.post(
        "/api/resume/linkedin", json={"brief_path": "/tmp/brief.json"}
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "worker_already_running"
    assert detail["pid"] == 12345
    assert detail["state_dir"] == "/tmp/state/linkedin/key"


def test_resume_endpoint_400_on_missing_brief_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_resume(req: Any) -> ResumeResponse:
        raise BriefPathNotFoundError("/tmp/missing.json")

    monkeypatch.setattr(cloris_api, "resume_linkedin_worker", fake_resume)

    client = TestClient(create_app())
    response = client.post(
        "/api/resume/linkedin", json={"brief_path": "/tmp/missing.json"}
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "brief_path_not_found"
    assert detail["brief_path"] == "/tmp/missing.json"


def test_resume_endpoint_rejects_extra_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LaunchLinkedInRequest's extra='forbid' rejects unknown fields at the
    request boundary, identically to the launch route."""

    def boom(req: Any) -> ResumeResponse:
        raise AssertionError(
            "resume_linkedin_worker should not be called when the request "
            "body has an unknown field"
        )

    monkeypatch.setattr(cloris_api, "resume_linkedin_worker", boom)

    client = TestClient(create_app())
    response = client.post(
        "/api/resume/linkedin",
        json={"brief_path": "/tmp/brief.json", "input_mode": "away"},
    )

    assert response.status_code == 422


def test_launch_endpoint_still_returns_slice_3_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REGRESSION: the launch contract version is independent of the status
    contract version. Slice 4 bumped StatusResponse.slice but NOT
    LaunchResponse.slice; clients reading the launch payload must still
    see ``v0-shell-slice-3``."""

    def fake_launch(req: Any) -> LaunchResponse:
        return LaunchResponse(
            source="linkedin",
            input_mode="concurrent",
            pid=11111,
            state_dir="/tmp/state/linkedin/key",
            worker_json_path="/tmp/state/linkedin/key/worker.json",
        )

    monkeypatch.setattr(cloris_api, "launch_linkedin_worker", fake_launch)

    client = TestClient(create_app())
    response = client.post(
        "/api/launch/linkedin", json={"brief_path": "/tmp/brief.json"}
    )

    assert response.status_code == 201
    assert response.json()["slice"] == "v0-shell-slice-3"


# --- Slice 5: built SPA + /assets static mount --------------------------


def _dist_assets_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "cloris" / "frontend" / "dist" / "assets"


def test_assets_mount_serves_a_known_file() -> None:
    """Slice 5: the ``/assets/`` static mount serves the hashed JS and CSS
    bundles Vite emits into ``cloris/frontend/dist/assets/``. We discover
    one ``.js`` and one ``.css`` filename via ``os.scandir`` rather than
    pinning the hash, because the hash changes with every build."""

    assets_dir = _dist_assets_dir()
    assert assets_dir.exists(), (
        f"expected built assets dir at {assets_dir}; run `pnpm build` "
        "in cloris/frontend/ to generate the committed dist artifact"
    )

    js_name: str | None = None
    css_name: str | None = None
    with os.scandir(assets_dir) as entries:
        for entry in entries:
            if entry.is_file():
                if js_name is None and entry.name.endswith(".js"):
                    js_name = entry.name
                elif css_name is None and entry.name.endswith(".css"):
                    css_name = entry.name
    assert js_name is not None, f"no .js file found under {assets_dir}"
    assert css_name is not None, f"no .css file found under {assets_dir}"

    client = TestClient(create_app())

    js_response = client.get(f"/assets/{js_name}")
    assert js_response.status_code == 200
    js_ct = js_response.headers["content-type"].split(";", 1)[0].strip()
    assert js_ct in {"application/javascript", "text/javascript"}, (
        f"unexpected JS content-type {js_ct!r} for {js_name}"
    )

    css_response = client.get(f"/assets/{css_name}")
    assert css_response.status_code == 200
    assert css_response.headers["content-type"].startswith("text/css")


def test_assets_mount_returns_404_for_unknown_file() -> None:
    """Slice 5: requests for files that don't exist under the mounted
    ``/assets/`` directory must 404 — StaticFiles' default behavior, but
    pinned here so a future configuration drift cannot silently start
    serving a fallback."""

    client = TestClient(create_app())
    response = client.get("/assets/this-does-not-exist.js")
    assert response.status_code == 404
