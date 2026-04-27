"""Tests for the Cloris app process (Slice 1).

Covers:

- ``GET /healthz`` and ``GET /`` HTTP contract via :class:`TestClient`.
- :func:`cloris.app.run_app` lifecycle with a ``NullWindowLauncher`` and a
  stub ``server_factory``. No real socket is bound and no real window is
  opened; the readiness probe is monkeypatched on
  :mod:`cloris.app`.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cloris import __version__
from cloris import app as cloris_app
from cloris.app import NullWindowLauncher, _resolve_port, create_app, run_app


def test_healthz_contract() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["slice"] == "v0-shell-slice-1"
    assert isinstance(body["version"], str)
    assert body["version"] == __version__


def test_index_serves_inline_html() -> None:
    client = TestClient(create_app())

    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

    body = response.text
    assert "01" in body
    assert "Cloris — shell v0 — slice 1" in body


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
