"""Recovery script: re-save Brazil PhD candidates to LinkedIn Recruiter.

Usage:
    python3 recover_saves.py [--dry-run]
    python3 recover_saves.py --resume-from 51        # skip first 50 (already saved)
    python3 recover_saves.py --project-id 1983396346 # override project

Prerequisites:
    - Chrome open with LinkedIn Recruiter session
    - CDP port active (same as main pipeline)
    - Target project exists in LinkedIn Recruiter
"""

import asyncio
import csv
import argparse
import json
import random
import re
from datetime import datetime
from shared import config  # noqa: F401 — loads CDP_URL from .env


async def connect_browser():
    """Connect to Chrome via CDP using standard Playwright (no rebrowser patching needed)."""
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(config.CDP_URL, timeout=60000)

    # Find the LinkedIn Recruiter tab
    page = None
    for ctx in browser.contexts:
        for p in ctx.pages:
            if "linkedin.com/talent" in p.url:
                page = p
                break
        if page:
            break

    if not page:
        all_urls = [p.url for ctx in browser.contexts for p in ctx.pages]
        raise RuntimeError(
            f"No LinkedIn Recruiter tab found among {len(all_urls)} tabs.\n"
            f"Open linkedin.com/talent in Chrome, then run again."
        )

    print(f"  Connected to browser. Active page: {page.url[:100]}")
    return pw, page


def load_and_dedup(csv_path: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Load CSV, separate into actionable / no-URL / duplicate buckets."""
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    seen_urls = set()
    actionable = []
    no_url = []
    duplicates = []

    for r in rows:
        url = r.get("LinkedIn URL", "").strip()
        if not url:
            no_url.append(r)
            continue
        url_key = url.split("?")[0]  # dedupe by profile ID, ignore query params
        if url_key in seen_urls:
            duplicates.append(r)
            continue
        seen_urls.add(url_key)
        actionable.append(r)

    return actionable, no_url, duplicates


async def recover(csv_path: str, project_id: str, dry_run: bool = False, resume_from: int = 1):
    actionable, no_url, duplicates = load_and_dedup(csv_path)

    print(f"CSV: {len(actionable)} unique candidates, {len(duplicates)} duplicates skipped, {len(no_url)} missing URLs")

    if no_url:
        print(f"\nThese {len(no_url)} candidates have no URL and need manual recovery:")
        for r in no_url:
            print(f"  - {r['Name']}")

    if dry_run:
        print(f"\n[DRY RUN] Would save {len(actionable)} candidates to project {project_id}:")
        for i, c in enumerate(actionable, 1):
            skip = " (skip - before resume point)" if i < resume_from else ""
            print(f"  {i}. {c['Name']}{skip}")
        return

    # Connect to browser (direct CDP, bypasses LinkedInBrowser for extended timeout)
    print(f"\nConnecting to Chrome (this may take a moment with many tabs open)...")
    pw, page = await connect_browser()

    save_selector = "button.save-to-pipeline__button"
    saved = 0
    failed = []
    log_path = f"output/recovery-log-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"

    print(f"Starting saves (project {project_id}, resume_from={resume_from})")
    print(f"Logging to {log_path}\n")

    for i, candidate in enumerate(actionable, 1):
        name = candidate["Name"]
        url = candidate["LinkedIn URL"]

        if i < resume_from:
            continue

        # Rewrite project ID in URL to target the correct project
        url = re.sub(r"project=\d+", f"project={project_id}", url)

        print(f"[{i}/{len(actionable)}] {name}...", end=" ", flush=True)

        status = "unknown"
        error_msg = ""
        try:
            # Navigate directly to profile page
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Click save button
            save_btn = page.locator(save_selector).first
            await save_btn.wait_for(state="visible", timeout=5000)
            await save_btn.evaluate("el => el.click()")
            await page.wait_for_timeout(2000)

            saved += 1
            status = "saved"
            print("OK")
        except Exception as e:
            status = "error"
            error_msg = str(e)
            failed.append({"index": i, "name": name, "status": status, "error": error_msg})
            print(f"FAILED ({e})")

        # Log every attempt for resume capability
        with open(log_path, "a") as lf:
            lf.write(json.dumps({"index": i, "name": name, "status": status, "error": error_msg}) + "\n")

        # Human-like delay between profiles
        delay = random.uniform(3, 8)
        await asyncio.sleep(delay)

    await pw.stop()

    print(f"\nDone: {saved} saved, {len(failed)} failed (out of {len(actionable)} unique candidates)")
    if failed:
        print(f"\nFailed candidates (re-run with --resume-from <index>):")
        for f in failed:
            print(f"  [{f['index']}] {f['name']} — {f['status']}{': ' + f.get('error','') if f.get('error') else ''}")
    print(f"\nFull log: {log_path}")


def main():
    parser = argparse.ArgumentParser(description="Re-save Brazil PhD candidates to LinkedIn Recruiter")
    parser.add_argument("--project-id", default="1983396346", help="LinkedIn Recruiter project ID (default: FDL Brazil PhD)")
    parser.add_argument("--csv", default="output/brazil-phd-saves-recovery.csv", help="Path to recovery CSV")
    parser.add_argument("--dry-run", action="store_true", help="List candidates without saving")
    parser.add_argument("--resume-from", type=int, default=1, help="Skip candidates before this index (1-based)")
    args = parser.parse_args()

    asyncio.run(recover(args.csv, args.project_id, args.dry_run, args.resume_from))


if __name__ == "__main__":
    main()
