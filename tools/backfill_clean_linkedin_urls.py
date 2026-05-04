#!/usr/bin/env python3
"""Backfill: re-normalize LinkedIn profile URLs in runtime_state DBs.

Phase C-bis Slice 0.4. The LinkedIn DOM scraper used to persist profile
URLs with search-result tracking parameters embedded
(``?miniProfileUrn=...&trackingId=...&searchEntityType=...&position=...
&searchId=...``). The acquisition layer now strips those at write time
via :func:`shared.identity_resolution.normalize_public_linkedin_url`,
but rows persisted before that change still carry the dirty URL — which
bloats the candidate-detail UI and pollutes the diagnostic Reference
Slip.

This script walks every ``runtime_state.sqlite3`` under
``output/state/linkedin/`` (or a root passed via ``--state-root``),
finds rows with dirty profile URLs, re-normalizes them via the same
helper, and ``UPDATE``s in place. The normalizer is idempotent — running
the script twice is a no-op.

Usage:
    python tools/backfill_clean_linkedin_urls.py             # default root
    python tools/backfill_clean_linkedin_urls.py --dry-run   # preview only
    python tools/backfill_clean_linkedin_urls.py --state-root output/state/linkedin
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.identity_resolution import normalize_public_linkedin_url


DEFAULT_STATE_ROOT = PROJECT_ROOT / "output" / "state" / "linkedin"


def _iter_dbs(state_root: Path):
    if not state_root.exists():
        return
    for db_path in sorted(state_root.glob("*/runtime_state.sqlite3")):
        if db_path.is_file():
            yield db_path


def _backfill_one_db(db_path: Path, *, dry_run: bool) -> tuple[int, int]:
    """Return ``(scanned, updated)`` row counts for a single DB."""

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, profile_url FROM candidates "
            "WHERE source='linkedin' AND profile_url IS NOT NULL "
            "AND profile_url != ''"
        ).fetchall()

        updates: list[tuple[str, int]] = []
        for row in rows:
            current = row["profile_url"] or ""
            cleaned = normalize_public_linkedin_url(current)
            if cleaned and cleaned != current:
                updates.append((cleaned, int(row["id"])))

        if updates and not dry_run:
            conn.executemany(
                "UPDATE candidates SET profile_url=? WHERE id=?",
                updates,
            )
            conn.commit()

        return len(rows), len(updates)
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-root",
        type=Path,
        default=DEFAULT_STATE_ROOT,
        help="Root directory containing per-state-key subdirs with runtime_state.sqlite3 (default: output/state/linkedin)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change, but don't write.",
    )
    args = parser.parse_args()

    state_root: Path = args.state_root
    if not state_root.exists():
        print(f"[backfill] state-root does not exist: {state_root}")
        return 1

    total_scanned = 0
    total_updated = 0
    db_count = 0

    for db_path in _iter_dbs(state_root):
        db_count += 1
        try:
            scanned, updated = _backfill_one_db(db_path, dry_run=args.dry_run)
        except sqlite3.DatabaseError as exc:
            print(f"[backfill] {db_path}: skipped ({exc})")
            continue
        total_scanned += scanned
        total_updated += updated
        marker = "would update" if args.dry_run else "updated"
        rel = db_path.relative_to(PROJECT_ROOT) if PROJECT_ROOT in db_path.parents else db_path
        print(f"[backfill] {rel}: scanned {scanned}, {marker} {updated}")

    summary = "DRY RUN" if args.dry_run else "DONE"
    print(
        f"[backfill] {summary}: {db_count} DB(s), scanned {total_scanned} rows, "
        f"{'would update' if args.dry_run else 'updated'} {total_updated}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
