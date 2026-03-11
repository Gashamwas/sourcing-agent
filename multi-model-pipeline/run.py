#!/usr/bin/env python3
"""Entry point for the LinkedIn Recruiter Multi-Model Sourcing Pipeline.

Usage:
    # Test on current browser page (no search string entry)
    python run.py --brief briefs/brazil-v2.json --test-single-page

    # Full run through all search strings
    python run.py --brief briefs/brazil-v2.json

    # Full run with custom search config
    python run.py --brief briefs/brazil-v2.json --search-config search_config.json

    # Re-judge existing snippets with updated rubric (no browser needed)
    python run.py --brief briefs/brazil-v2.json --rejudge-from output/snippets.jsonl

    # Custom output directory
    python run.py --brief briefs/brazil-v2.json --output-dir output/brazil-run-2
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
        "--search-config", default="search_config.json",
        help="Path to the search config JSON (default: search_config.json)"
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

    args = parser.parse_args()

    # Validate brief exists
    if not Path(args.brief).exists():
        print(f"Error: Brief file not found: {args.brief}")
        sys.exit(1)

    if args.rejudge_from:
        # Offline re-judgment mode
        asyncio.run(rejudge(args))
    else:
        # Normal pipeline mode
        from pipeline import Pipeline

        pipeline = Pipeline(
            brief_path=args.brief,
            search_config_path=args.search_config,
            output_dir=args.output_dir,
            test_mode=args.test_single_page,
        )

        if args.test_single_page:
            asyncio.run(pipeline.run_single_page())
        else:
            asyncio.run(pipeline.run())


async def rejudge(args):
    """Re-run Opus judgments on existing snippet extractions. No browser needed."""
    from schemas import CandidateSnippet, OpusDecision
    from hard_filters import hard_filter
    from judger import facial_judge
    from storage import read_jsonl, append_jsonl, read_json

    print("=" * 60)
    print("RE-JUDGE MODE: Processing existing snippets with current rubric")
    print("=" * 60)

    snippets_data = read_jsonl(args.rejudge_from)
    print(f"  Loaded {len(snippets_data)} snippets from {args.rejudge_from}")

    output_dir = Path(args.output_dir) if args.output_dir else Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    rejudge_path = output_dir / "rejudged_facial.jsonl"

    stats = {"total": 0, "hard_filtered": 0, "facial_yes": 0, "facial_no": 0, "errors": 0}

    for i, data in enumerate(snippets_data, 1):
        snippet = CandidateSnippet.from_dict(data)
        stats["total"] += 1

        print(f"\n  [{i}/{len(snippets_data)}] {snippet.name}")
        print(f"    {snippet.current_title} at {snippet.current_company}")

        # Hard filter
        should_skip, reason = hard_filter(snippet)
        if should_skip:
            print(f"    [HARD SKIP] {reason}")
            stats["hard_filtered"] += 1
            continue

        # Facial judgment
        try:
            decision = facial_judge(snippet)
            append_jsonl(rejudge_path, decision.to_dict())

            if decision.decision == "FACIAL_YES":
                print(f"    [FACIAL_YES] {decision.rationale}")
                stats["facial_yes"] += 1
            else:
                print(f"    [FACIAL_NO] {decision.rationale}")
                stats["facial_no"] += 1
        except Exception as e:
            print(f"    [ERROR] {e}")
            stats["errors"] += 1

    print(f"\n{'=' * 60}")
    print(f"  Re-judge Summary")
    print(f"  Total: {stats['total']}, Hard filtered: {stats['hard_filtered']}, "
          f"YES: {stats['facial_yes']}, NO: {stats['facial_no']}, Errors: {stats['errors']}")
    print(f"  Results written to: {rejudge_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
