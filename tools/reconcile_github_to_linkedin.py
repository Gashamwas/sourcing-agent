"""Reconcile saved GitHub leads against LinkedIn Recruiter."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from github.reconciliation_input import load_github_reconciliation_batch
from github.reconciliation_report import (
    build_reconciliation_row,
    write_reconciliation_csv,
    write_reconciliation_jsonl,
    write_reconciliation_summary,
)
from linkedin.browser import LinkedInBrowser
from linkedin.reconciliation import LinkedInReconciliationService


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve GitHub-sourced leads to LinkedIn Recruiter profiles and novelty status."
    )
    parser.add_argument("--github-output-dir", required=True, help="GitHub run output directory containing candidates.jsonl and final_judgments.jsonl")
    parser.add_argument("--project-url", required=True, help="LinkedIn Recruiter project/search URL to use for lookup")
    parser.add_argument("--output-dir", help="Where to write reconciliation artifacts; defaults to the GitHub output directory")
    parser.add_argument("--max-leads", type=int, default=50, help="Maximum saved GitHub leads to reconcile")
    parser.add_argument("--max-results-per-query", type=int, default=5, help="How many Recruiter search results to inspect for each lookup query")
    return parser


async def _run(args: argparse.Namespace) -> None:
    github_output_dir = Path(args.github_output_dir)
    output_dir = Path(args.output_dir) if args.output_dir else github_output_dir
    batch = load_github_reconciliation_batch(github_output_dir)
    leads = batch.leads[: max(args.max_leads, 0)]
    browser = LinkedInBrowser()
    await browser.connect()
    try:
        service = LinkedInReconciliationService(
            browser=browser,
            project_url=args.project_url,
            max_results_per_query=max(args.max_results_per_query, 1),
        )
        rows: list[dict] = []
        for index, lead in enumerate(leads, start=1):
            print(f"[{index}/{len(leads)}] Reconciling {lead.candidate_name} ({lead.username})")
            decision = await service.reconcile_lead(lead)
            rows.append(build_reconciliation_row(lead, decision))

        jsonl_path = write_reconciliation_jsonl(output_dir / "linkedin_reconciliation.jsonl", rows)
        csv_path = write_reconciliation_csv(output_dir / "linkedin_reconciliation.csv", rows)
        input_stats = batch.stats.to_dict()
        input_stats["processed_leads"] = len(leads)
        summary_path = write_reconciliation_summary(
            output_dir / "linkedin_reconciliation_summary.json",
            rows,
            input_stats=input_stats,
        )
        print(f"Wrote {jsonl_path}")
        print(f"Wrote {csv_path}")
        print(f"Wrote {summary_path}")
    finally:
        await browser.disconnect()


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
