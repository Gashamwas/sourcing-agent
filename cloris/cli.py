"""Cloris command-line entrypoint.

Slice 1 ships exactly one subcommand: ``cloris start``. It builds the FastAPI
app via :func:`cloris.app.create_app` and hands off to
:func:`cloris.app.run_app` which owns the full app-process lifecycle (uvicorn
in a background thread, readiness probe, native window launch, clean shutdown).

There is intentionally **no** ``--no-window`` (or any other test-only) flag.
Tests inject a launcher and a server factory through Python kwargs on
``run_app`` instead.
"""

from __future__ import annotations

import argparse
from typing import Sequence


_MISSING_DEPS_HINT = (
    "Cloris requires fastapi and uvicorn (and pywebview for the native "
    "window). Install them with:\n"
    "    pip install fastapi uvicorn pywebview"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the Cloris CLI.

    Exposed at module scope so tests can introspect the registered actions
    (e.g. to assert that no ``--no-window`` flag exists).
    """

    parser = argparse.ArgumentParser(
        prog="cloris",
        description="Cloris desktop shell (v0 / slice 1).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser(
        "start",
        help="Start the Cloris app process (FastAPI + native window).",
        description=(
            "Start the local Cloris app process. Boots a FastAPI server in a "
            "background thread and opens the native window through the "
            "pywebview launcher seam."
        ),
    )
    start.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind the local server to (default: 127.0.0.1).",
    )
    start.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port to bind (default: 0 = pick a free ephemeral port).",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the Cloris CLI.

    Returns an exit code so callers (and ``python -m cloris``) can pass it to
    ``sys.exit``.
    """

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "start":
        return _run_start(host=args.host, port=args.port)

    parser.error(f"unknown command: {args.command!r}")
    return 2


def _run_start(*, host: str, port: int) -> int:
    try:
        from cloris import app as cloris_app
    except ImportError as exc:  # pragma: no cover - defensive import-error path
        print(_MISSING_DEPS_HINT)
        raise SystemExit(_format_import_error(exc)) from exc

    try:
        fastapi_app = cloris_app.create_app()
    except ImportError as exc:
        print(_MISSING_DEPS_HINT)
        raise SystemExit(_format_import_error(exc)) from exc

    cloris_app.run_app(fastapi_app, host=host, port=port)
    return 0


def _format_import_error(exc: ImportError) -> str:
    return f"cloris: missing dependency ({exc})."
