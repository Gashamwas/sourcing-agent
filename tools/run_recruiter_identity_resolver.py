"""Run the Recruiter-first reconciliation tool for saved GitHub leads."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from github.reconciliation_input import load_saved_github_reconciliation_batch_with_fallback
from github.recruiter_identity_report import (
    build_recruiter_identity_row,
    write_recruiter_identity_csv,
    write_recruiter_identity_jsonl,
    write_recruiter_identity_summary,
    write_recruiter_reconciliation_saved_csv,
    write_recruiter_reconciliation_saved_jsonl,
)
from linkedin.browser import LinkedInBrowser
from linkedin.recruiter_identity_resolver import (
    RecruiterIdentityResolver,
    RecruiterResolverConfig,
)
from shared.brief_loader import load_brief
from shared.judger import init_judger
from shared.recruiter_brief_resolution import resolve_linkedin_brief_path_for_github_run


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile GitHub-sourced leads against LinkedIn Recruiter (identity + fit + engagement)."
    )
    parser.add_argument(
        "--github-output-dir",
        required=True,
        help="GitHub run output directory containing saved leads.",
    )
    parser.add_argument(
        "--project-url",
        help="LinkedIn Recruiter project/search URL to use when the agent should navigate itself.",
    )
    parser.add_argument(
        "--output-dir",
        help="Where to write resolver artifacts; defaults to the GitHub output directory.",
    )
    parser.add_argument(
        "--max-leads",
        type=int,
        default=25,
        help="Maximum number of saved GitHub leads to process.",
    )
    parser.add_argument(
        "--location-filter",
        default="",
        help="Fixed Recruiter location filter for the run. In --use-current-search mode this is recorded as metadata only.",
    )
    parser.add_argument(
        "--use-current-search",
        action="store_true",
        help="Assume you have already opened the Recruiter project and set the location filter manually.",
    )
    parser.add_argument(
        "--max-cards",
        type=int,
        default=5,
        help="How many Recruiter result cards to inspect per lead.",
    )
    parser.add_argument(
        "--skip-profile-open",
        action="store_true",
        help="Stop before opening the matched profile (disables holistic fit and auto-save).",
    )
    parser.add_argument(
        "--linkedin-brief",
        help="Explicit path to the canonical LinkedIn brief JSON (fit authority). "
        "If omitted, a sibling brief is resolved from the GitHub run manifest.",
    )
    parser.add_argument(
        "--github-brief",
        help="Override path to the GitHub brief JSON when run-manifest.json is missing or wrong.",
    )
    parser.add_argument(
        "--dry-run-save",
        action="store_true",
        help="If reconciliation reaches SAVE, skip the Recruiter save click (for testing).",
    )
    return parser


async def _run(args: argparse.Namespace) -> None:
    if not args.use_current_search and not args.project_url:
        raise SystemExit("--project-url is required unless --use-current-search is set")

    github_output_dir = Path(args.github_output_dir)
    output_dir = Path(args.output_dir) if args.output_dir else github_output_dir
    batch = load_saved_github_reconciliation_batch_with_fallback(github_output_dir)
    leads = batch.leads[: max(args.max_leads, 0)]

    linkedin_brief_path = resolve_linkedin_brief_path_for_github_run(
        github_output_dir,
        explicit_linkedin_brief=args.linkedin_brief,
        github_brief_path=args.github_brief,
    )
    linkedin_brief = load_brief(str(linkedin_brief_path))
    init_judger(linkedin_brief)

    browser = LinkedInBrowser()
    await browser.connect()
    try:
        resolver = RecruiterIdentityResolver(
            browser=browser,
            project_url=str(args.project_url or ""),
            config=RecruiterResolverConfig(
                max_cards=max(args.max_cards, 1),
                open_profile_on_likely_match=not bool(args.skip_profile_open),
                dry_run_save=bool(args.dry_run_save),
            ),
            linkedin_brief=linkedin_brief,
            linkedin_brief_path=str(linkedin_brief_path),
        )
        if args.use_current_search:
            await resolver.use_existing_search(args.location_filter)
        else:
            await resolver.prepare_search(args.location_filter)

        rows: list[dict] = []
        for index, lead in enumerate(leads, start=1):
            print(f"[{index}/{len(leads)}] Resolving {lead.candidate_name} ({lead.username})")
            result = await resolver.resolve_lead(lead)
            rows.append(build_recruiter_identity_row(result))

        jsonl_path = write_recruiter_identity_jsonl(
            output_dir / "recruiter_identity_resolutions.jsonl",
            rows,
        )
        csv_path = write_recruiter_identity_csv(
            output_dir / "recruiter_identity_resolutions.csv",
            rows,
        )
        saved_jsonl = write_recruiter_reconciliation_saved_jsonl(
            output_dir / "recruiter_reconciliation_saved.jsonl",
            rows,
        )
        saved_csv = write_recruiter_reconciliation_saved_csv(
            output_dir / "recruiter_reconciliation_saved.csv",
            rows,
        )
        input_stats = batch.stats.to_dict()
        input_stats["processed_leads"] = len(leads)
        input_stats["location_filter"] = args.location_filter
        input_stats["use_current_search"] = bool(args.use_current_search)
        input_stats["linkedin_brief_path"] = str(linkedin_brief_path)
        summary_path = write_recruiter_identity_summary(
            output_dir / "recruiter_identity_resolutions_summary.json",
            rows,
            input_stats=input_stats,
        )
        print(f"Wrote {jsonl_path}")
        print(f"Wrote {csv_path}")
        print(f"Wrote {saved_jsonl}")
        print(f"Wrote {saved_csv}")
        print(f"Wrote {summary_path}")
    finally:
        await browser.disconnect()


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
