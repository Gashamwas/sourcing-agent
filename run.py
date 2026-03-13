#!/usr/bin/env python3
"""Entry point for the LinkedIn Recruiter Multi-Model Sourcing Pipeline.

Usage:
    python run.py                          # interactive mode
    python run.py --brief config/brief-fdl-lightweight.json --full-run
    python run.py --brief config/brief-fdl-lightweight.json --full-run --resume
    python run.py --brief config/brief-brazil-real.json --test-single-page
    python run.py --brief config/brief-brazil-real.json --rejudge-from output/snippets.jsonl
"""

import argparse
import asyncio
import json
import sys
import urllib.request
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "config"
OUTPUT_DIR = Path(__file__).parent / "output"


# ------------------------------------------------------------------
# Interactive mode
# ------------------------------------------------------------------

def _pick(prompt: str, options: list[str]) -> int:
    """Display numbered options, return 0-based index of the user's choice."""
    print(f"\n{prompt}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    while True:
        raw = input("\n> ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(f"  Enter a number 1-{len(options)}")


def _discover_briefs() -> list[Path]:
    """Find all brief JSON files in config/."""
    return sorted(CONFIG_DIR.glob("brief-*.json"))


def _brief_label(path: Path) -> str:
    """Human-readable label for a brief file."""
    try:
        raw = json.loads(path.read_text())
        name = raw.get("name") or raw.get("brief_id") or path.stem
        has_jd = bool(raw.get("jd") or raw.get("jd_text"))
        has_kit = bool(raw.get("kit_url") or raw.get("search_kit_id"))
        tags = []
        if has_jd:
            tags.append("JD")
        if has_kit:
            tags.append("kit")
        if raw.get("archetypes") or raw.get("sweet_spot", {}).get("archetypes"):
            tags.append("full eval")
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        return f"{name}{tag_str}  ({path.name})"
    except Exception:
        return path.name


def _has_progress() -> bool:
    """Check if a resumable progress file exists."""
    progress_path = OUTPUT_DIR / "progress.json"
    if not progress_path.exists():
        return False
    try:
        data = json.loads(progress_path.read_text())
        strings = data.get("strings", [])
        done = sum(1 for s in strings if s.get("status") == "done")
        total = len(strings)
        return done < total  # Only resumable if there's work left
    except Exception:
        return False


def _progress_summary() -> str:
    """One-line summary of existing progress."""
    try:
        data = json.loads((OUTPUT_DIR / "progress.json").read_text())
        strings = data.get("strings", [])
        done = sum(1 for s in strings if s.get("status") == "done")
        total = len(strings)
        brief_name = data.get("brief_name", "?")
        return f"{brief_name}: {done}/{total} strings done"
    except Exception:
        return "unknown state"


def interactive():
    """Interactive mode — prompts for brief and run mode."""
    print("=" * 50)
    print("  Sourcing Pipeline")
    print("=" * 50)

    # Step 1: Pick a brief
    briefs = _discover_briefs()
    if not briefs:
        print(f"\nNo brief files found in {CONFIG_DIR}/")
        print("Add a brief-*.json file and try again.")
        sys.exit(1)

    labels = [_brief_label(b) for b in briefs]
    idx = _pick("Which brief?", labels)
    brief_path = briefs[idx]

    # Step 2: Pick a run mode
    modes = [
        "Full run (kit + strategy + execute)",
        "Test single page (current browser page only)",
    ]

    # Offer resume if progress exists
    resumable = _has_progress()
    if resumable:
        modes.insert(0, f"Resume previous run ({_progress_summary()})")

    mode_idx = _pick("Run mode?", modes)

    # Adjust index if resume was inserted
    if resumable:
        if mode_idx == 0:
            # Resume
            _launch(brief_path, full_run=True, resume=True)
            return
        mode_idx -= 1  # Shift back to match original modes list

    if mode_idx == 0:
        _launch(brief_path, full_run=True)
    elif mode_idx == 1:
        _launch(brief_path, test_single_page=True)


def _launch(
    brief_path: Path,
    full_run: bool = False,
    resume: bool = False,
    test_single_page: bool = False,
    search_config: str | None = None,
    rejudge_from: str | None = None,
):
    """Import Pipeline and run."""
    from orchestrator import Pipeline

    pipeline = Pipeline(
        brief_path=str(brief_path),
        search_config_path=search_config,
        test_mode=test_single_page,
    )

    if rejudge_from:
        asyncio.run(pipeline.rejudge_from_file(rejudge_from))
    elif test_single_page:
        asyncio.run(pipeline.run_single_page())
    elif full_run:
        asyncio.run(pipeline.run_full(resume=resume))
    elif search_config:
        asyncio.run(pipeline.run())


# ------------------------------------------------------------------
# CLI mode (flags)
# ------------------------------------------------------------------

def cli():
    parser = argparse.ArgumentParser(
        description="LinkedIn Recruiter Multi-Model Sourcing Pipeline"
    )
    parser.add_argument(
        "--brief", required=True,
        help="Path to the sourcing brief JSON file"
    )
    parser.add_argument(
        "--search-config", default=None,
        help="Path to the search config JSON"
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory (default: output/)"
    )
    parser.add_argument(
        "--test-single-page", action="store_true",
        help="Test mode: process only the current browser results page"
    )
    parser.add_argument(
        "--rejudge-from", default=None,
        help="Re-judge snippets from an existing JSONL file (no browser needed)"
    )
    parser.add_argument(
        "--full-run", action="store_true",
        help="Full autonomous run: extract kit, form strategy, execute all strings with adaptation"
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from existing progress file (used with --full-run)"
    )

    args = parser.parse_args()

    if not Path(args.brief).exists():
        print(f"Error: Brief file not found: {args.brief}")
        sys.exit(1)

    _launch(
        brief_path=Path(args.brief),
        full_run=args.full_run,
        resume=args.resume,
        test_single_page=args.test_single_page,
        search_config=args.search_config,
        rejudge_from=args.rejudge_from,
    )

    if not any([args.full_run, args.test_single_page, args.search_config, args.rejudge_from]):
        print("Error: Specify --test-single-page, --full-run, --search-config, or --rejudge-from")
        sys.exit(1)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main():
    # If no args (or just the script name), go interactive
    if len(sys.argv) == 1:
        interactive()
    else:
        cli()


if __name__ == "__main__":
    main()
