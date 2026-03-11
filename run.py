#!/usr/bin/env python3
"""Entry point for the LinkedIn Recruiter Multi-Model Sourcing Pipeline.

Usage:
    python run.py --brief config/brief-brazil-real.json --test-single-page
    python run.py --brief config/brief-brazil-real.json --search-config config/search-strings-and-filters.json
    python run.py --brief config/brief-brazil-real.json --rejudge-from output/snippets.jsonl
    python run.py --brief config/brief-brazil-real.json --full-run
    python run.py --brief config/brief-brazil-real.json --full-run --resume
"""

import argparse
import asyncio
import sys
from pathlib import Path


def main():
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

    # Validate brief exists
    if not Path(args.brief).exists():
        print(f"Error: Brief file not found: {args.brief}")
        sys.exit(1)

    from orchestrator import Pipeline

    pipeline = Pipeline(
        brief_path=args.brief,
        search_config_path=args.search_config,
        output_dir=args.output_dir,
        test_mode=args.test_single_page,
    )

    if args.rejudge_from:
        asyncio.run(pipeline.rejudge_from_file(args.rejudge_from))
    elif args.test_single_page:
        asyncio.run(pipeline.run_single_page())
    elif args.full_run:
        asyncio.run(pipeline.run_full(resume=args.resume))
    elif args.search_config:
        asyncio.run(pipeline.run())
    else:
        print("Error: Specify --test-single-page, --full-run, --search-config, or --rejudge-from")
        sys.exit(1)


if __name__ == "__main__":
    main()
