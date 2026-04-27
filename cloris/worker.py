"""Cloris detached LinkedIn worker (Slice 3).

Exec-replace entrypoint that the API process spawns via
``subprocess.Popen([sys.executable, "-m", "cloris.worker", ...])``. The worker
writes a ``worker.json`` sidecar into the LinkedIn state directory, then
``os.execvp``s into ``python -m linkedin.session_orchestrator ...``. After the
exec, the same PID belongs to the orchestrator process — so the sidecar's
``pid`` field stays truthful for any later stop/probe operation.

This module is wrapper code only:

- It does not import ``linkedin.session_orchestrator``; it spawns it.
- It does not write canonical SQLite state; the orchestrator does.
- It owns ``worker.json`` as a Cloris-only sidecar (not a runtime-state record).

Slice 3 deliberately:

- Sets ``heartbeat_at == started_at`` once and never updates it.
- Refuses ``--input-mode away`` at the wrapper boundary.
- Exposes ``--mode {fresh}`` only; ``--resume`` is wired in
  :func:`build_session_orchestrator_argv` for Slice 4 reuse but not surfaced
  on the worker CLI yet.

Module-level seams (``_now`` and ``_exec``) exist so tests can monkeypatch
them without ever spawning a real subprocess or replacing the test process.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn, Sequence


WORKER_SIDECAR_FILENAME = "worker.json"
LAUNCHER_VERSION = "cloris-v0-slice-3"


class BriefPathNotFoundError(Exception):
    """Raised by the API launch helper when ``brief_path`` does not exist on disk.

    Imported by :mod:`cloris.api` so the route can map this to HTTP 400. The
    worker CLI does not raise this directly — it expects the API helper to
    have already validated the path.
    """


class WorkerAlreadyRunningError(Exception):
    """Raised when an existing ``worker.json`` references a live PID.

    The route maps this to HTTP 409 Conflict and surfaces ``pid`` plus
    ``state_dir`` in the response body so the client can render an actionable
    error.
    """

    def __init__(self, pid: int, state_dir: str) -> None:
        super().__init__(f"worker already running (pid={pid}, state_dir={state_dir})")
        self.pid = pid
        self.state_dir = state_dir


def build_sidecar(
    *,
    source: str,
    brief_id: str,
    brief_path: str,
    output_dir: str,
    mode: str,
    input_mode: str,
    started_at: str,
    pid: int,
    run_id: int | None = None,
) -> dict:
    """Return the ``worker.json`` payload for a fresh launch.

    Field set is fixed by ``docs/cloris-control-plane-spec.md`` §5; Slice 3
    pins ``heartbeat_at`` to ``started_at`` because no live heartbeat updater
    exists yet.
    """

    return {
        "pid": pid,
        "source": source,
        "brief_id": brief_id,
        "brief_path": brief_path,
        "output_dir": output_dir,
        "run_id": run_id,
        "started_at": started_at,
        "heartbeat_at": started_at,
        "mode": mode,
        "input_mode": input_mode,
        "launcher_version": LAUNCHER_VERSION,
    }


def write_sidecar(state_dir: Path, payload: dict) -> Path:
    """Atomically write ``payload`` to ``<state_dir>/worker.json``.

    Uses ``tmp + os.replace`` so a reader can never observe a partially
    written file. JSON is serialized with ``indent=2, sort_keys=True`` so
    the on-disk artifact is diff-stable.
    """

    state_dir.mkdir(parents=True, exist_ok=True)
    final_path = state_dir / WORKER_SIDECAR_FILENAME
    tmp_path = state_dir / (WORKER_SIDECAR_FILENAME + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp_path, final_path)
    return final_path


def read_sidecar(state_dir: Path) -> dict | None:
    """Return the parsed sidecar dict, or ``None`` for missing/malformed files.

    Never raises. Missing file, unreadable file, malformed JSON, and a JSON
    document whose top level is not an object all collapse to ``None`` —
    callers treat any of those as "no sidecar present" or "stale", which is
    exactly the policy the launch helper applies.
    """

    sidecar_path = state_dir / WORKER_SIDECAR_FILENAME
    if not sidecar_path.exists():
        return None
    try:
        raw = sidecar_path.read_text()
        parsed = json.loads(raw)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def is_pid_alive(pid) -> bool:
    """Return whether ``pid`` is currently a live process.

    ``ProcessLookupError`` ⇒ dead. ``PermissionError`` ⇒ alive (we don't own
    the process but it exists). Anything else (malformed input, type errors,
    other ``OSError``) ⇒ treat as stale — the user-approved policy is to err
    on the side of overwriting unparseable sidecars rather than blocking new
    launches.

    Non-positive ints are rejected up front: ``os.kill(0, 0)`` and
    ``os.kill(-1, 0)`` succeed under POSIX with process-group semantics
    (signal every process in the current session / every process the caller
    can signal), which is not what "is this specific PID alive" should
    answer. We treat them as stale to keep the contract single-PID.
    """

    try:
        coerced = int(pid)
    except (TypeError, ValueError):
        return False

    if coerced <= 0:
        return False

    try:
        os.kill(coerced, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def build_session_orchestrator_argv(
    *,
    brief_path: str,
    state_dir: str,
    input_mode: str = "concurrent",
    resume: bool = False,
    python_executable: str = sys.executable,
) -> list[str]:
    """Compose the argv for ``os.execvp`` into ``linkedin.session_orchestrator``.

    Pure function: no I/O, no globals beyond ``sys.executable``. Kept
    independently testable so test cases can pin the exact command shape
    without going through ``main``. ``resume`` is wired here for Slice 4
    reuse but the worker CLI does not currently surface it.
    """

    argv: list[str] = [
        python_executable,
        "-m",
        "linkedin.session_orchestrator",
        "--brief",
        brief_path,
        "--state-dir",
        state_dir,
        "--input-mode",
        input_mode,
    ]
    if resume:
        argv.append("--resume")
    return argv


def _now() -> str:
    """Return a UTC ISO-8601 timestamp.

    Module-level seam so tests can freeze the clock without monkeypatching
    :mod:`datetime`. Production callers should not rely on the format
    beyond "ISO-8601 with timezone".
    """

    return datetime.now(timezone.utc).isoformat()


def _exec(argv: list[str]) -> NoReturn:
    """Replace the current process image with ``argv``.

    Module-level seam so tests can monkeypatch this to a recorder and
    avoid actually replacing the test process. In production this never
    returns; the test stub returns ``None`` and ``main`` falls through to
    its ``return 0``.
    """

    os.execvp(argv[0], argv)
    raise SystemExit(  # pragma: no cover - execvp never returns
        "os.execvp returned unexpectedly"
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cloris.worker",
        description="Cloris detached LinkedIn worker (writes worker.json then execvp)s into linkedin.session_orchestrator).",
    )
    parser.add_argument(
        "--brief",
        required=True,
        help="Path to the LinkedIn brief JSON (forwarded to the orchestrator).",
    )
    parser.add_argument(
        "--brief-id",
        required=True,
        help="Brief id recorded in worker.json (typically shared.output_paths.linkedin_state_key).",
    )
    parser.add_argument(
        "--state-dir",
        default=None,
        help=(
            "LinkedIn state directory. If absent, resolved via "
            "shared.output_paths.resolve_linkedin_state_dir."
        ),
    )
    parser.add_argument(
        "--input-mode",
        choices=["concurrent"],
        default="concurrent",
        help="Cloris v0 is concurrent-only; 'away' is rejected at the wrapper boundary.",
    )
    parser.add_argument(
        "--mode",
        choices=["fresh"],
        default="fresh",
        help="Slice 3 only supports fresh launches; resume is wired in Slice 4.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entrypoint for ``python -m cloris.worker``.

    Steps: parse args → resolve state dir → write sidecar → execvp into
    ``linkedin.session_orchestrator``. The ``return 0`` is only reached
    when ``_exec`` is monkeypatched in tests; in production the process
    image is replaced before this line.
    """

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.state_dir is not None:
        state_dir = Path(args.state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
    else:
        from shared.output_paths import resolve_linkedin_state_dir

        state_dir = resolve_linkedin_state_dir(brief_path=args.brief)

    payload = build_sidecar(
        source="linkedin",
        brief_id=args.brief_id,
        brief_path=args.brief,
        output_dir=str(state_dir),
        mode=args.mode,
        input_mode=args.input_mode,
        started_at=_now(),
        pid=os.getpid(),
        run_id=None,
    )
    write_sidecar(state_dir, payload)

    argv_to_exec = build_session_orchestrator_argv(
        brief_path=args.brief,
        state_dir=str(state_dir),
        input_mode=args.input_mode,
    )
    _exec(argv_to_exec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
