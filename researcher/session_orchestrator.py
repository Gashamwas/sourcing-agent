"""Researcher session orchestrator — Slice 1 stub.

Accepts the argv shape produced by
`cloris.launchers._researcher_orchestrator_argv` so the launch path
is exercisable end-to-end (worker spawns, orchestrator parses argv,
exits 0). Slice 6 wires the real `ResearcherPipeline.run` here.

The stub deliberately does NOT touch runtime state, the brief, or the
state directory beyond verifying the path exists. Slice 1 is foundation
only; running a researcher target_modules brief should be a clean no-op
that demonstrates the launch chain works.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="researcher.session_orchestrator",
        description=(
            "Researcher session orchestrator (Slice 1 stub). "
            "The real pipeline ships in Slice 6."
        ),
    )
    parser.add_argument(
        "--brief",
        required=True,
        help="Path to the brief JSON.",
    )
    parser.add_argument(
        "--state-dir",
        required=True,
        help="Per-source state directory.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue an interrupted run (no-op in Slice 1 stub).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Slice 1 stub entrypoint.

    Validates argv shape and that the brief path exists, then exits 0.
    Slice 6 replaces the body with the real pipeline run.
    """

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    brief_path = Path(args.brief)
    if not brief_path.exists():
        sys.stderr.write(
            f"researcher.session_orchestrator: brief not found at {brief_path}\n"
        )
        return 2

    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    sys.stdout.write(
        f"researcher.session_orchestrator: Slice 1 stub — brief={brief_path} "
        f"state_dir={state_dir} resume={args.resume}. "
        f"Pipeline arrives in Slice 6.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
