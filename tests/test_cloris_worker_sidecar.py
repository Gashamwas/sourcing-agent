"""Tests for the Cloris detached worker (Slice 3).

Pin the contract of :mod:`cloris.worker` without spawning a real LinkedIn
run:

- ``build_sidecar`` returns the exact spec field set with
  ``heartbeat_at == started_at`` and ``launcher_version == LAUNCHER_VERSION``.
- ``write_sidecar`` is atomic and the written JSON is sort-keyed.
- ``read_sidecar`` collapses missing/malformed sidecars to ``None`` instead
  of raising.
- ``is_pid_alive`` correctly distinguishes self/dead/invalid inputs.
- ``build_session_orchestrator_argv`` produces the exact command shape, with
  ``--resume`` only present when requested.
- ``main`` writes ``worker.json`` then calls ``_exec`` once with the right
  argv (the test process is never replaced because ``_exec`` is monkeypatched).
- ``main`` rejects ``--input-mode away`` at the wrapper boundary.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cloris import worker as worker_mod
from cloris.worker import (
    LAUNCHER_VERSION,
    WORKER_SIDECAR_FILENAME,
    build_session_orchestrator_argv,
    build_sidecar,
    is_pid_alive,
    main,
    read_sidecar,
    write_sidecar,
)


def test_build_sidecar_field_contract() -> None:
    payload = build_sidecar(
        source="linkedin",
        brief_id="brief-1",
        brief_path="/tmp/brief.json",
        output_dir="/tmp/state/linkedin/brief-1",
        mode="fresh",
        input_mode="concurrent",
        started_at="2026-04-27T18:00:00+00:00",
        pid=12345,
        run_id=None,
    )

    assert set(payload.keys()) == {
        "pid",
        "source",
        "brief_id",
        "brief_path",
        "output_dir",
        "run_id",
        "started_at",
        "heartbeat_at",
        "mode",
        "input_mode",
        "launcher_version",
    }
    assert payload["pid"] == 12345
    assert payload["source"] == "linkedin"
    assert payload["brief_id"] == "brief-1"
    assert payload["brief_path"] == "/tmp/brief.json"
    assert payload["output_dir"] == "/tmp/state/linkedin/brief-1"
    assert payload["mode"] == "fresh"
    assert payload["input_mode"] == "concurrent"
    assert payload["started_at"] == "2026-04-27T18:00:00+00:00"
    assert payload["heartbeat_at"] == payload["started_at"]
    assert payload["launcher_version"] == LAUNCHER_VERSION
    assert payload["launcher_version"] == "cloris-v0-slice-4"
    assert payload["run_id"] is None


def test_write_and_read_sidecar_round_trip(tmp_path: Path) -> None:
    payload = build_sidecar(
        source="linkedin",
        brief_id="brief-1",
        brief_path=str(tmp_path / "brief.json"),
        output_dir=str(tmp_path),
        mode="fresh",
        input_mode="concurrent",
        started_at="2026-04-27T18:00:00+00:00",
        pid=999,
    )

    sidecar_path = write_sidecar(tmp_path, payload)

    assert sidecar_path == tmp_path / WORKER_SIDECAR_FILENAME
    assert sidecar_path.exists()

    raw = sidecar_path.read_text()
    parsed = json.loads(raw)
    assert parsed == payload

    expected_serialization = json.dumps(payload, indent=2, sort_keys=True)
    assert raw == expected_serialization

    reread = read_sidecar(tmp_path)
    assert reread == payload


def test_read_sidecar_missing_returns_none(tmp_path: Path) -> None:
    assert read_sidecar(tmp_path) is None


def test_read_sidecar_malformed_returns_none(tmp_path: Path) -> None:
    (tmp_path / WORKER_SIDECAR_FILENAME).write_bytes(b"not json")

    assert read_sidecar(tmp_path) is None


def test_read_sidecar_non_object_returns_none(tmp_path: Path) -> None:
    (tmp_path / WORKER_SIDECAR_FILENAME).write_text(json.dumps([1, 2, 3]))

    assert read_sidecar(tmp_path) is None


def test_is_pid_alive_self() -> None:
    assert is_pid_alive(os.getpid()) is True


def test_is_pid_alive_dead() -> None:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()

    if is_pid_alive(child.pid) is True:
        pytest.skip(
            "PID was recycled before probe; portability fallback exercised by "
            "test_is_pid_alive_handles_invalid_input."
        )
    assert is_pid_alive(child.pid) is False


def test_is_pid_alive_handles_invalid_input() -> None:
    assert is_pid_alive(-1) is False
    assert is_pid_alive("not a pid") is False
    assert is_pid_alive(None) is False


def test_build_session_orchestrator_argv_default_concurrent() -> None:
    argv = build_session_orchestrator_argv(
        brief_path="/tmp/brief.json",
        state_dir="/tmp/state/linkedin/brief-1",
    )

    assert argv[:3] == [sys.executable, "-m", "linkedin.session_orchestrator"]
    assert argv[3:5] == ["--brief", "/tmp/brief.json"]
    assert argv[5:7] == ["--state-dir", "/tmp/state/linkedin/brief-1"]
    assert argv[7:9] == ["--input-mode", "concurrent"]
    assert "--resume" not in argv


def test_build_session_orchestrator_argv_with_resume() -> None:
    argv = build_session_orchestrator_argv(
        brief_path="/tmp/brief.json",
        state_dir="/tmp/state/linkedin/brief-1",
        resume=True,
    )

    assert argv[:3] == [sys.executable, "-m", "linkedin.session_orchestrator"]
    assert argv[-1] == "--resume"
    assert argv.count("--resume") == 1


def test_worker_main_writes_sidecar_then_execs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({"id": "brief-1"}))

    captured_argv: list[list[str]] = []

    def recorder(argv: list[str]) -> None:
        captured_argv.append(list(argv))

    frozen_iso = "2026-04-27T18:00:00+00:00"

    monkeypatch.setattr(worker_mod, "_exec", recorder)
    monkeypatch.setattr(worker_mod, "_now", lambda: frozen_iso)

    import shared.output_paths as output_paths

    monkeypatch.setattr(
        output_paths,
        "resolve_linkedin_state_dir",
        lambda **_: tmp_path,
    )

    rc = main(["--brief", str(brief), "--brief-id", "brief-1"])
    assert rc == 0

    sidecar_path = tmp_path / WORKER_SIDECAR_FILENAME
    assert sidecar_path.exists()
    payload = json.loads(sidecar_path.read_text())
    assert payload["pid"] == os.getpid()
    assert payload["brief_id"] == "brief-1"
    assert payload["source"] == "linkedin"
    assert payload["mode"] == "fresh"
    assert payload["input_mode"] == "concurrent"
    assert payload["started_at"] == frozen_iso
    assert payload["heartbeat_at"] == frozen_iso
    assert payload["launcher_version"] == "cloris-v0-slice-4"
    assert payload["run_id"] is None
    assert payload["brief_path"] == str(brief)
    assert payload["output_dir"] == str(tmp_path)

    assert len(captured_argv) == 1
    argv = captured_argv[0]
    assert argv[:5] == [
        sys.executable,
        "-m",
        "linkedin.session_orchestrator",
        "--brief",
        str(brief),
    ]
    assert "--state-dir" in argv
    assert argv[argv.index("--state-dir") + 1] == str(tmp_path)
    assert "--input-mode" in argv
    assert argv[argv.index("--input-mode") + 1] == "concurrent"


def test_worker_main_rejects_input_mode_away(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--brief", "/tmp/x", "--brief-id", "x", "--input-mode", "away"])

    assert exc_info.value.code != 0


# --- Slice 4: --mode resume + LAUNCHER_VERSION bump ---------------------


def test_launcher_version_constant_is_slice_4() -> None:
    """Slice 4 bumps LAUNCHER_VERSION so reconciliation against older sidecars
    can distinguish slice-3 vs slice-4 worker writes."""

    assert worker_mod.LAUNCHER_VERSION == "cloris-v0-slice-4"


def test_worker_main_resume_mode_writes_sidecar_with_mode_resume_and_passes_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--mode resume threads --resume into the orchestrator argv exactly once
    and the sidecar truthfully records mode == 'resume'."""

    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({"id": "brief-x"}))

    captured_argv: list[list[str]] = []

    def recorder(argv: list[str]) -> None:
        captured_argv.append(list(argv))

    monkeypatch.setattr(worker_mod, "_exec", recorder)
    monkeypatch.setattr(worker_mod, "_now", lambda: "2026-04-27T18:00:00+00:00")

    rc = main(
        [
            "--brief",
            str(brief),
            "--brief-id",
            "x",
            "--state-dir",
            str(tmp_path),
            "--mode",
            "resume",
        ]
    )
    assert rc == 0

    sidecar_path = tmp_path / WORKER_SIDECAR_FILENAME
    payload = json.loads(sidecar_path.read_text())
    assert payload["mode"] == "resume"
    assert payload["launcher_version"] == "cloris-v0-slice-4"

    assert len(captured_argv) == 1
    argv = captured_argv[0]
    assert argv.count("--resume") == 1


def test_worker_main_default_mode_is_fresh_after_slice_4_bump(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default --mode stays 'fresh' after the slice-4 bump and --resume is
    NOT threaded into the orchestrator argv."""

    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({"id": "brief-x"}))

    captured_argv: list[list[str]] = []

    def recorder(argv: list[str]) -> None:
        captured_argv.append(list(argv))

    monkeypatch.setattr(worker_mod, "_exec", recorder)
    monkeypatch.setattr(worker_mod, "_now", lambda: "2026-04-27T18:00:00+00:00")

    rc = main(
        [
            "--brief",
            str(brief),
            "--brief-id",
            "x",
            "--state-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0

    sidecar_path = tmp_path / WORKER_SIDECAR_FILENAME
    payload = json.loads(sidecar_path.read_text())
    assert payload["mode"] == "fresh"

    assert len(captured_argv) == 1
    argv = captured_argv[0]
    assert "--resume" not in argv
