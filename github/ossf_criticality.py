"""OpenSSF Criticality Score lookup (OSS Maintainers Slice 5).

Per OSS Maintainers Module Spec §9, OpenSSF publishes a weekly-
refreshed `criticality_score` dataset. We don't compute the score
live (the upstream pipeline is heavyweight); instead, we ship a
snapshot CSV at :file:`data/ossf_criticality_snapshot.csv` and
look up scores in-process. Refresh cadence + provenance are recorded
in the CSV header.

The lookup is deliberately defensive: a missing key returns
``None`` (caller treats as "signal unavailable" per spec §12), a
malformed snapshot file is logged but does not raise (the project-
quality sub-index drops the signal and continues).

Snapshot format (CSV with two leading metadata lines)::

    # snapshot_source: https://github.com/ossf/criticality_score
    # snapshot_date: 2026-04-15
    repo,score
    kubernetes/kubernetes,0.99432
    rust-lang/rust,0.97845
    ...

The header lines are skipped; the body is ``repo,score`` rows.
``repo`` is lowercased on load.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


SNAPSHOT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "ossf_criticality_snapshot.csv"
)


_cached_scores: dict[str, float] | None = None


def _load_snapshot() -> dict[str, float]:
    """Load the snapshot CSV into an in-process dict, cached.

    Failure mode: if the file is missing OR malformed, returns an
    empty dict and logs a warning. Callers (lookup) treat empty as
    "every key returns None," which is the spec-§12-conformant
    fail-soft posture.
    """

    global _cached_scores
    if _cached_scores is not None:
        return _cached_scores

    if not SNAPSHOT_PATH.exists():
        logger.warning(
            "ossf_criticality: snapshot file missing at %s — sub-index will "
            "skip the OSSF signal until the snapshot lands",
            SNAPSHOT_PATH,
        )
        _cached_scores = {}
        return _cached_scores

    scores: dict[str, float] = {}
    try:
        with SNAPSHOT_PATH.open("r", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            for row in reader:
                if not row:
                    continue
                # Skip metadata header lines (start with `#`) and the
                # column header row.
                first = row[0].strip()
                if first.startswith("#") or first.lower() == "repo":
                    continue
                if len(row) < 2:
                    continue
                key = first.lower()
                try:
                    score = float(row[1])
                except ValueError:
                    continue
                # Clamp to [0, 1] defensively (OSSF publishes [0, 1]
                # but a malformed row could carry > 1).
                scores[key] = max(0.0, min(score, 1.0))
    except OSError as exc:
        logger.warning(
            "ossf_criticality: failed to read snapshot at %s (%s); falling back to empty",
            SNAPSHOT_PATH,
            exc,
        )
        _cached_scores = {}
        return _cached_scores

    _cached_scores = scores
    return _cached_scores


def lookup_criticality_score(owner: str, repo: str) -> Optional[float]:
    """Return the OSSF criticality score for ``owner/repo``, or ``None``.

    Spec §12 fail-soft: a missing key, a missing snapshot file, or a
    malformed snapshot all return ``None``. The project-quality sub-
    index treats ``None`` as "signal unavailable" and drops it from
    the composite.
    """

    if not owner or not repo:
        return None
    key = f"{owner.strip().lower()}/{repo.strip().lower()}"
    snapshot = _load_snapshot()
    return snapshot.get(key)


def reset_snapshot_cache() -> None:
    """Test-only hook to force a re-read of the snapshot file.

    Production callers cache for the lifetime of the process; tests
    that monkeypatch :data:`SNAPSHOT_PATH` need to reset between
    cases.
    """

    global _cached_scores
    _cached_scores = None
