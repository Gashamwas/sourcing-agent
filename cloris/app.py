"""Cloris app process: FastAPI assembly + lifecycle.

This module owns three things and only three things in Slice 1:

1. :func:`create_app` — build the FastAPI app and include the API router.
2. The :class:`WindowLauncher` protocol plus two concrete launchers
   (:class:`PyWebviewLauncher` for production, :class:`NullWindowLauncher` for
   tests).
3. :func:`run_app` — own one clean lifecycle: start uvicorn in a background
   thread, wait for readiness, hand off to the launcher, then trigger a
   bounded shutdown.

There is no static-files mount and no broader frontend tree exposed. The HTTP
surface is exactly what ``cloris.api`` declares.
"""

from __future__ import annotations

import logging
import socket as _socket
import threading
import time
from typing import Any, Callable, Optional, Protocol, runtime_checkable
from urllib.error import URLError
from urllib.request import urlopen

if False:  # pragma: no cover - import-time-only typing aid
    from fastapi import FastAPI


log = logging.getLogger(__name__)


def create_app() -> "FastAPI":
    """Construct the Cloris FastAPI app.

    ``fastapi`` is imported lazily so that importing :mod:`cloris.app` (e.g.
    by tests that only need the launcher protocol or the CLI parser) does not
    require FastAPI to be installed.
    """

    from fastapi import FastAPI

    from cloris import __version__
    from cloris.api import router

    app = FastAPI(
        title="Cloris",
        version=__version__,
        description="Cloris desktop shell — v0 / slice 1.",
    )
    app.include_router(router)
    return app


@runtime_checkable
class WindowLauncher(Protocol):
    """Open a native window pointed at the local Cloris server.

    ``open(url)`` MUST block until the window is closed. The blocking contract
    is what makes the lifecycle in :func:`run_app` simple: when ``open``
    returns, the user is done with the window and the server should shut down.
    """

    def open(self, url: str) -> None:  # pragma: no cover - protocol stub
        ...


class PyWebviewLauncher:
    """Launcher that opens a real native window via ``pywebview``.

    ``webview`` is imported inside :meth:`open` so that importing the launcher
    (or the rest of :mod:`cloris.app`) does not pull pywebview into the
    process. CI hosts and test machines without GTK/Qt stay unaffected until
    the user actually runs ``cloris start``.
    """

    def open(self, url: str) -> None:
        import webview

        webview.create_window("Cloris", url)
        webview.start()


class NullWindowLauncher:
    """No-op launcher used by tests.

    Records every ``open`` call and returns immediately, so the lifecycle in
    :func:`run_app` proceeds straight to shutdown without opening anything.
    """

    def __init__(self) -> None:
        self.opened: list[str] = []

    def open(self, url: str) -> None:
        self.opened.append(url)


ServerFactory = Callable[[Any, str, int], Any]


def _resolve_port(host: str, port: int) -> int:
    """Return ``port`` unchanged if nonzero; otherwise bind a transient socket
    to ``(host, 0)`` to obtain a concrete free local port, close it, and
    return that port number.

    This deliberately uses stdlib socket binding rather than reaching into
    ``uvicorn.Server.servers[...].sockets[...]`` because the test seams in
    Slice 1 are a swappable ``server_factory`` and a swappable
    ``_wait_until_ready``; coupling to uvicorn internals would force every
    stub to mimic uvicorn's nested startup state. The small bind/close race
    window is acceptable: the worst case is a clean uvicorn bind error, not
    a silent ``:0`` URL.
    """

    if port != 0:
        return port
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def _default_server_factory(app: Any, host: str, port: int) -> Any:
    """Build a real ``uvicorn.Server`` configured for the app process."""

    import uvicorn

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    return uvicorn.Server(config)


def _wait_until_ready(host: str, port: int, *, timeout: float = 5.0) -> None:
    """Poll ``GET /healthz`` until it returns 200 or ``timeout`` elapses.

    Exposed at module scope so tests can monkeypatch it without having to
    bind a real socket. Raises :class:`RuntimeError` on timeout.
    """

    deadline = time.monotonic() + timeout
    url = f"http://{host}:{port}/healthz"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=0.5) as resp:  # noqa: S310 - localhost only
                if resp.status == 200:
                    return
        except (URLError, OSError) as exc:
            last_error = exc
        time.sleep(0.05)
    raise RuntimeError(
        f"Cloris server did not become ready at {url} within {timeout:.1f}s"
        f" (last_error={last_error!r})"
    )


def run_app(
    app: Any,
    *,
    host: str,
    port: int,
    launcher: Optional[WindowLauncher] = None,
    server_factory: Optional[ServerFactory] = None,
    readiness_timeout: float = 5.0,
    shutdown_timeout: float = 5.0,
) -> None:
    """Run the Cloris app process through one full lifecycle.

    Steps:

    1. Build the server via ``server_factory`` (default uses uvicorn).
    2. Start ``server.run()`` in a background daemon thread.
    3. Poll ``/healthz`` until the server is reachable, or fail fast.
    4. Hand off to ``launcher.open(url)`` (blocks until the window closes).
    5. Set ``server.should_exit = True`` to ask uvicorn to wind down.
    6. Join the server thread with a bounded timeout. On overrun, log one
       warning and return — daemon thread will be reaped at process exit.

    The ``launcher`` and ``server_factory`` kwargs are the test seams. Both
    default to production implementations when not provided.
    """

    if launcher is None:
        launcher = PyWebviewLauncher()
    if server_factory is None:
        server_factory = _default_server_factory

    resolved_port = _resolve_port(host, port)
    server = server_factory(app, host, resolved_port)

    thread = threading.Thread(
        target=server.run,
        name="cloris-uvicorn",
        daemon=True,
    )
    thread.start()

    try:
        _wait_until_ready(host, resolved_port, timeout=readiness_timeout)
    except Exception:
        server.should_exit = True
        thread.join(timeout=shutdown_timeout)
        raise

    url = f"http://{host}:{resolved_port}"
    try:
        launcher.open(url)
    finally:
        server.should_exit = True
        thread.join(timeout=shutdown_timeout)
        if thread.is_alive():
            log.warning(
                "cloris: uvicorn server did not stop within %.1fs of "
                "should_exit=True; leaving daemon thread to be reaped at "
                "process exit.",
                shutdown_timeout,
            )
