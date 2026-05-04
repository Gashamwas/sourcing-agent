"""Designer module — recruiter annotation primitives.

Designer Slice 7. The load-bearing HITL distinction (per spec §5.4):
the recruiter sees Cloris's vision judgment alongside the actual
images Cloris evaluated, can flag any image as misrepresentative,
and can mark per-principle feedback ("Useful guidance" /
"Wrong / shallow" / "Off-rubric") that feeds into Slice 9's
reflection polish.

This module owns the data layer for those annotations:

- :class:`ExcludedAssetStore` — append-only log of recruiter-excluded
  ``(candidate_identity_key, asset_url)`` pairs with optional reason.
  Stored alongside :mod:`designer.image_acquisition`'s asset cache
  in the same per-state-dir SQLite file.
- :class:`PrincipleFeedbackStore` — append-only log of per-principle
  feedback markers (one row per ``(candidate, principle, marker)``
  tuple).
- ``compute_re_eval_asset_set(candidate, original_asset_set,
  excluded_asset_urls) -> list[asset_id]`` — pure function: returns
  the asset_ids the re-evaluation pass should consume after
  exclusions are applied.
- ``feedback_marker_distribution(brief_id) -> dict[str, int]`` —
  recruiter-feedback rollup for the workspace surface and Slice 9's
  reflection polish prompt input.

The HTTP endpoint that dispatches into these primitives lives in
``cloris/api.py`` (Slice 7's wire-layer addition). The orchestrator
that re-runs the vision evaluation against the reduced asset set
is wired in Slice 7 as well; this module is the pure-data substrate.

Design choice: append-only stores with a ``revoked_at`` soft-delete
column rather than mutable rows. Recruiter annotations are recruiter
intent over time — a recruiter who excludes then un-excludes an
asset has a different signal than a recruiter who never excluded it,
and Slice 9's reflection polish needs that history.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


# Recognized per-principle feedback markers. Slice 7 ships three
# (positive / neutral-skeptical / negative); Slice 9's reflection
# polish maps these to rubric weight refinements (consistently
# "Off-rubric" → propose lower weight; consistently "Useful guidance"
# → propose higher weight or new exemplar).
RECOGNIZED_FEEDBACK_MARKERS: frozenset[str] = frozenset(
    {"useful_guidance", "wrong_shallow", "off_rubric"}
)


@dataclass(frozen=True)
class ExcludedAsset:
    excluded_id: int
    candidate_identity_key: str
    asset_url: str
    reason: str
    excluded_at: str
    revoked_at: str | None


@dataclass(frozen=True)
class PrincipleFeedbackMarker:
    marker_id: int
    candidate_identity_key: str
    principle_name: str
    marker: str
    note: str
    marked_at: str


class ExcludedAssetStore:
    """Append-only store for recruiter-excluded assets.

    Schema:
    - ``excluded_id`` PK
    - ``(candidate_identity_key, asset_url)`` is NOT unique — exclude
      → revoke → re-exclude is a valid sequence and each row
      preserves the recruiter's intent at that point in time.
    - ``revoked_at`` is non-null when the recruiter un-excluded; the
      "is this asset currently excluded?" query is "exists at least
      one row with revoked_at IS NULL for this (candidate, url)".
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS excluded_assets (
        excluded_id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_identity_key TEXT NOT NULL,
        asset_url TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        excluded_at TEXT NOT NULL,
        revoked_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_excluded_candidate
        ON excluded_assets(candidate_identity_key);
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(self.SCHEMA_SQL)
            conn.commit()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def exclude(
        self,
        *,
        candidate_identity_key: str,
        asset_url: str,
        reason: str = "",
    ) -> ExcludedAsset:
        """Record a recruiter exclusion.

        Idempotent on currently-active exclusions: if the recruiter
        excludes the same asset twice without revoking, the second
        call returns the existing row rather than inserting a
        duplicate. Re-exclude AFTER revoke produces a new row.
        """

        existing = self.active_exclusion(
            candidate_identity_key=candidate_identity_key, asset_url=asset_url
        )
        if existing is not None:
            return existing

        excluded_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO excluded_assets (
                    candidate_identity_key, asset_url, reason, excluded_at, revoked_at
                ) VALUES (?, ?, ?, ?, NULL)
                """,
                (candidate_identity_key, asset_url, reason, excluded_at),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM excluded_assets WHERE excluded_id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return _row_to_excluded(row)

    def revoke(
        self,
        *,
        candidate_identity_key: str,
        asset_url: str,
    ) -> bool:
        """Mark the active exclusion as revoked. Returns True if
        a row was revoked, False if no active exclusion existed.
        """

        active = self.active_exclusion(
            candidate_identity_key=candidate_identity_key, asset_url=asset_url
        )
        if active is None:
            return False
        revoked_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE excluded_assets SET revoked_at = ? WHERE excluded_id = ?",
                (revoked_at, active.excluded_id),
            )
            conn.commit()
        return True

    def active_exclusion(
        self,
        *,
        candidate_identity_key: str,
        asset_url: str,
    ) -> ExcludedAsset | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM excluded_assets
                WHERE candidate_identity_key = ?
                  AND asset_url = ?
                  AND revoked_at IS NULL
                ORDER BY excluded_id DESC
                LIMIT 1
                """,
                (candidate_identity_key, asset_url),
            ).fetchone()
        return _row_to_excluded(row) if row is not None else None

    def active_exclusions_for_candidate(
        self, candidate_identity_key: str
    ) -> tuple[ExcludedAsset, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM excluded_assets
                WHERE candidate_identity_key = ?
                  AND revoked_at IS NULL
                ORDER BY excluded_id
                """,
                (candidate_identity_key,),
            ).fetchall()
        return tuple(_row_to_excluded(row) for row in rows)


class PrincipleFeedbackStore:
    """Append-only store for per-principle recruiter feedback markers.

    Schema:
    - ``marker_id`` PK
    - ``marker`` MUST be in :data:`RECOGNIZED_FEEDBACK_MARKERS`; the
      :func:`record` validates and raises on unknown markers.
    - ``(candidate, principle, marker)`` is NOT unique — a recruiter
      may mark the same principle differently across runs (their
      taste evolves; this is signal for Slice 9 reflection polish).
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS principle_feedback (
        marker_id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_identity_key TEXT NOT NULL,
        principle_name TEXT NOT NULL,
        marker TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        marked_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_feedback_candidate
        ON principle_feedback(candidate_identity_key);
    CREATE INDEX IF NOT EXISTS idx_feedback_principle
        ON principle_feedback(principle_name);
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(self.SCHEMA_SQL)
            conn.commit()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def record(
        self,
        *,
        candidate_identity_key: str,
        principle_name: str,
        marker: str,
        note: str = "",
    ) -> PrincipleFeedbackMarker:
        """Append a feedback marker.

        Raises ``ValueError`` for unknown markers — the wire layer
        catches and maps to HTTP 422 so the recruiter's input never
        silently fails validation.
        """

        if marker not in RECOGNIZED_FEEDBACK_MARKERS:
            raise ValueError(
                f"Unknown feedback marker {marker!r}; "
                f"expected one of {sorted(RECOGNIZED_FEEDBACK_MARKERS)}"
            )
        marked_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO principle_feedback (
                    candidate_identity_key, principle_name, marker, note, marked_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (candidate_identity_key, principle_name, marker, note, marked_at),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM principle_feedback WHERE marker_id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return _row_to_marker(row)

    def markers_for_candidate(
        self, candidate_identity_key: str
    ) -> tuple[PrincipleFeedbackMarker, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM principle_feedback
                WHERE candidate_identity_key = ?
                ORDER BY marker_id
                """,
                (candidate_identity_key,),
            ).fetchall()
        return tuple(_row_to_marker(row) for row in rows)

    def feedback_marker_distribution(self) -> dict[str, dict[str, int]]:
        """Roll up marker counts per principle.

        Returns a nested dict ``{principle_name: {marker: count}}``.
        Slice 9's reflection polish prompt grounds itself in this
        distribution to propose rubric weight refinements.
        """

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT principle_name, marker, COUNT(*) AS cnt
                FROM principle_feedback
                GROUP BY principle_name, marker
                """
            ).fetchall()
        out: dict[str, dict[str, int]] = {}
        for row in rows:
            out.setdefault(row["principle_name"], {})[row["marker"]] = int(row["cnt"])
        return out


def _row_to_excluded(row: sqlite3.Row) -> ExcludedAsset:
    return ExcludedAsset(
        excluded_id=int(row["excluded_id"]),
        candidate_identity_key=str(row["candidate_identity_key"]),
        asset_url=str(row["asset_url"]),
        reason=str(row["reason"] or ""),
        excluded_at=str(row["excluded_at"]),
        revoked_at=str(row["revoked_at"]) if row["revoked_at"] is not None else None,
    )


def _row_to_marker(row: sqlite3.Row) -> PrincipleFeedbackMarker:
    return PrincipleFeedbackMarker(
        marker_id=int(row["marker_id"]),
        candidate_identity_key=str(row["candidate_identity_key"]),
        principle_name=str(row["principle_name"]),
        marker=str(row["marker"]),
        note=str(row["note"] or ""),
        marked_at=str(row["marked_at"]),
    )


# ---------------------------------------------------------------------------
# Re-evaluation asset-set helper
# ---------------------------------------------------------------------------


def compute_re_eval_asset_set(
    *,
    original_assets: list[tuple[int, str]],
    excluded_asset_urls: set[str],
) -> list[int]:
    """Return the asset_ids the re-evaluation pass should consume.

    Trivially: drop any asset whose URL is in ``excluded_asset_urls``,
    return the rest's ids in original order. Pure function so the
    re-eval orchestrator can compute the asset set without touching
    the SQLite stores.

    Intentionally bare: future scope (e.g., enriching with newly-
    fetched assets to backfill the excluded ones) lands here, but
    Slice 7 ships the minimum-viable filter only.
    """

    return [
        asset_id
        for (asset_id, asset_url) in original_assets
        if asset_url not in excluded_asset_urls
    ]
