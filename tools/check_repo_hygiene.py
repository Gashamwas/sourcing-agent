#!/usr/bin/env python3
"""Lightweight repo hygiene checks."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.brief_lifecycle import summarize_brief_lifecycle


def is_incidental_tracked_path(path: str) -> bool:
    """Return True when a tracked path looks like accidental repo junk."""
    parts = Path(path).parts
    name = parts[-1] if parts else path
    if name == ".DS_Store":
        return True
    if "__pycache__" in parts:
        return True
    if name.endswith(".json") and ".bak-" in name:
        return True
    return False


def tracked_incidental_files(project_root: Path = PROJECT_ROOT) -> list[str]:
    """Return tracked files that should not normally live in the repo."""
    output = subprocess.check_output(
        ["git", "ls-files"],
        cwd=project_root,
        text=True,
    )
    tracked_paths = [line.strip() for line in output.splitlines() if line.strip()]
    return sorted(path for path in tracked_paths if is_incidental_tracked_path(path))


def main() -> int:
    junk = tracked_incidental_files(PROJECT_ROOT)
    summary = summarize_brief_lifecycle(CONFIG_DIR, recursive=True)

    print("[hygiene] brief inventory")
    for lifecycle, paths in summary.items():
        print(f"  - {lifecycle}: {len(paths)}")

    if junk:
        print("[hygiene] tracked incidental files found:")
        for path in junk:
            print(f"  - {path}")
        return 1

    print("[hygiene] tracked incidental files: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
