"""Executive Search session orchestrator — Slice 1 stub.

Accepts the argv shape produced by
`cloris.launchers._exec_search_orchestrator_argv` so the launch path
is exercisable end-to-end (worker spawns, orchestrator parses argv,
exits 0). Slices 2-10 wire the real pipeline (extending the LinkedIn
evaluation pipeline + off-LinkedIn signals + Cloris-native shortlist
destination).

The stub deliberately does NOT touch runtime state, the brief, or the
state directory beyond verifying the path exists. Slice 1 is foundation
only; running an exec_search target_modules brief should be a clean
no-op that demonstrates the launch chain works.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exec_search.session_orchestrator",
        description=(
            "Executive Search session orchestrator (Slice 1 stub). "
            "The real pipeline ships across Slices 2-10."
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
    The real pipeline replaces the body progressively across Slices
    2-10; the LinkedIn full-eval branch extends in Slice 2 with the
    `DOSSIER_RATIONALE:` block, and off-LinkedIn signal acquisition
    + the Cloris-native shortlist destination land in Slices 3-7.
    """

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    brief_path = Path(args.brief)
    if not brief_path.exists():
        sys.stderr.write(
            f"exec_search.session_orchestrator: brief not found at {brief_path}\n"
        )
        return 2

    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    sys.stdout.write(
        f"exec_search.session_orchestrator: Slice 1 stub — brief={brief_path} "
        f"state_dir={state_dir} resume={args.resume}. "
        f"Dossier-depth pipeline arrives in Slices 2-10.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
