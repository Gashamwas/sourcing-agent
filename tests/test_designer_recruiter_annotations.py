"""Designer Slice 7 — recruiter annotation primitives.

Pins:

- ``ExcludedAssetStore`` is append-only with idempotent active-
  exclusion behavior (re-excluding an already-excluded asset is a
  no-op; re-excluding after revoke produces a new row).
- ``PrincipleFeedbackStore.record`` validates marker enum and raises
  on unknown markers.
- ``feedback_marker_distribution`` rolls up counts per principle
  for the Slice-9 reflection polish input.
- ``compute_re_eval_asset_set`` is a pure function that filters the
  original asset set by the recruiter-excluded URL set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from designer.recruiter_annotations import (
    RECOGNIZED_FEEDBACK_MARKERS,
    ExcludedAssetStore,
    PrincipleFeedbackStore,
    compute_re_eval_asset_set,
)


# ---------------------------------------------------------------------------
# ExcludedAssetStore
# ---------------------------------------------------------------------------


def test_exclude_persists_active_exclusion(tmp_path: Path) -> None:
    store = ExcludedAssetStore(tmp_path / "annotations.sqlite3")
    excluded = store.exclude(
        candidate_identity_key="behance:joe",
        asset_url="https://example.com/img1.jpg",
        reason="That's their old portfolio.",
    )
    assert excluded.candidate_identity_key == "behance:joe"
    assert excluded.asset_url == "https://example.com/img1.jpg"
    assert excluded.reason == "That's their old portfolio."
    assert excluded.revoked_at is None


def test_exclude_is_idempotent_on_active_exclusion(tmp_path: Path) -> None:
    """Excluding the same asset twice without revoking returns the
    existing row — no duplicate rows."""

    store = ExcludedAssetStore(tmp_path / "annotations.sqlite3")
    first = store.exclude(
        candidate_identity_key="behance:joe", asset_url="https://x.com/a.jpg"
    )
    second = store.exclude(
        candidate_identity_key="behance:joe", asset_url="https://x.com/a.jpg"
    )
    assert first.excluded_id == second.excluded_id

    actives = store.active_exclusions_for_candidate("behance:joe")
    assert len(actives) == 1


def test_revoke_marks_existing_exclusion_revoked_at(tmp_path: Path) -> None:
    store = ExcludedAssetStore(tmp_path / "annotations.sqlite3")
    store.exclude(
        candidate_identity_key="behance:joe", asset_url="https://x.com/a.jpg"
    )
    revoked = store.revoke(
        candidate_identity_key="behance:joe", asset_url="https://x.com/a.jpg"
    )
    assert revoked is True
    assert (
        store.active_exclusion(
            candidate_identity_key="behance:joe", asset_url="https://x.com/a.jpg"
        )
        is None
    )


def test_revoke_returns_false_when_no_active_exclusion(tmp_path: Path) -> None:
    store = ExcludedAssetStore(tmp_path / "annotations.sqlite3")
    assert (
        store.revoke(
            candidate_identity_key="behance:joe", asset_url="https://x.com/a.jpg"
        )
        is False
    )


def test_re_exclude_after_revoke_produces_new_row(tmp_path: Path) -> None:
    """Recruiter intent over time: each exclude → revoke → re-exclude
    cycle leaves a distinct row in the append-only log."""

    store = ExcludedAssetStore(tmp_path / "annotations.sqlite3")
    first = store.exclude(
        candidate_identity_key="behance:joe", asset_url="https://x.com/a.jpg"
    )
    store.revoke(
        candidate_identity_key="behance:joe", asset_url="https://x.com/a.jpg"
    )
    second = store.exclude(
        candidate_identity_key="behance:joe", asset_url="https://x.com/a.jpg"
    )
    assert first.excluded_id != second.excluded_id


def test_active_exclusions_for_candidate_omits_revoked(tmp_path: Path) -> None:
    store = ExcludedAssetStore(tmp_path / "annotations.sqlite3")
    store.exclude(
        candidate_identity_key="behance:joe", asset_url="https://x.com/a.jpg"
    )
    store.exclude(
        candidate_identity_key="behance:joe", asset_url="https://x.com/b.jpg"
    )
    store.revoke(
        candidate_identity_key="behance:joe", asset_url="https://x.com/a.jpg"
    )
    actives = store.active_exclusions_for_candidate("behance:joe")
    assert {ex.asset_url for ex in actives} == {"https://x.com/b.jpg"}


# ---------------------------------------------------------------------------
# PrincipleFeedbackStore
# ---------------------------------------------------------------------------


def test_recognized_markers_set() -> None:
    assert RECOGNIZED_FEEDBACK_MARKERS == frozenset(
        {"useful_guidance", "wrong_shallow", "off_rubric"}
    )


def test_record_persists_marker(tmp_path: Path) -> None:
    store = PrincipleFeedbackStore(tmp_path / "annotations.sqlite3")
    marker = store.record(
        candidate_identity_key="behance:joe",
        principle_name="Visual hierarchy",
        marker="useful_guidance",
        note="Strong primary focal point read.",
    )
    assert marker.marker == "useful_guidance"
    assert marker.principle_name == "Visual hierarchy"
    assert marker.note == "Strong primary focal point read."


def test_record_rejects_unknown_marker(tmp_path: Path) -> None:
    store = PrincipleFeedbackStore(tmp_path / "annotations.sqlite3")
    with pytest.raises(ValueError, match="Unknown feedback marker"):
        store.record(
            candidate_identity_key="behance:joe",
            principle_name="Visual hierarchy",
            marker="thumbs_up",  # not in the recognized set
        )


def test_markers_for_candidate_returns_history(tmp_path: Path) -> None:
    store = PrincipleFeedbackStore(tmp_path / "annotations.sqlite3")
    store.record(
        candidate_identity_key="behance:joe",
        principle_name="Visual hierarchy",
        marker="useful_guidance",
    )
    store.record(
        candidate_identity_key="behance:joe",
        principle_name="Typographic refinement",
        marker="off_rubric",
    )
    history = store.markers_for_candidate("behance:joe")
    assert len(history) == 2
    assert {m.principle_name for m in history} == {
        "Visual hierarchy",
        "Typographic refinement",
    }


def test_feedback_marker_distribution_rolls_up_counts(tmp_path: Path) -> None:
    store = PrincipleFeedbackStore(tmp_path / "annotations.sqlite3")
    # Visual hierarchy: 2× useful_guidance.
    store.record(
        candidate_identity_key="behance:a",
        principle_name="Visual hierarchy",
        marker="useful_guidance",
    )
    store.record(
        candidate_identity_key="behance:b",
        principle_name="Visual hierarchy",
        marker="useful_guidance",
    )
    # Typographic refinement: 1× off_rubric.
    store.record(
        candidate_identity_key="behance:a",
        principle_name="Typographic refinement",
        marker="off_rubric",
    )
    distribution = store.feedback_marker_distribution()
    assert distribution["Visual hierarchy"]["useful_guidance"] == 2
    assert distribution["Typographic refinement"]["off_rubric"] == 1


# ---------------------------------------------------------------------------
# compute_re_eval_asset_set
# ---------------------------------------------------------------------------


def test_compute_re_eval_asset_set_drops_excluded_urls() -> None:
    original = [
        (0, "https://x.com/a.jpg"),
        (1, "https://x.com/b.jpg"),
        (2, "https://x.com/c.jpg"),
        (3, "https://x.com/d.jpg"),
    ]
    excluded = {"https://x.com/b.jpg", "https://x.com/d.jpg"}
    out = compute_re_eval_asset_set(
        original_assets=original, excluded_asset_urls=excluded
    )
    assert out == [0, 2]


def test_compute_re_eval_asset_set_preserves_order() -> None:
    original = [
        (5, "https://x.com/e.jpg"),
        (6, "https://x.com/f.jpg"),
        (1, "https://x.com/a.jpg"),
    ]
    out = compute_re_eval_asset_set(
        original_assets=original, excluded_asset_urls=set()
    )
    assert out == [5, 6, 1]


def test_compute_re_eval_asset_set_empty_when_all_excluded() -> None:
    original = [(0, "https://x.com/a.jpg")]
    excluded = {"https://x.com/a.jpg"}
    out = compute_re_eval_asset_set(
        original_assets=original, excluded_asset_urls=excluded
    )
    assert out == []
