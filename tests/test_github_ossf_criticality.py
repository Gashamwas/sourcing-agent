"""Tests for :mod:`github.ossf_criticality` (OSS Maintainers Slice 5).

Covers:

- Snapshot lookup hits known entries and is case-insensitive.
- Missing keys return ``None``.
- Malformed CSV rows are skipped without raising.
- Missing snapshot file returns an empty cache (fail-soft).
- The shipped snapshot at ``data/ossf_criticality_snapshot.csv``
  contains the expected high-criticality anchors (kubernetes,
  rust-lang, etc.) so Slice 6's evaluator block has data to lean on
  out of the box.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from github import ossf_criticality as oc


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    oc.reset_snapshot_cache()
    yield
    oc.reset_snapshot_cache()


def test_lookup_finds_known_high_criticality_anchor() -> None:
    score = oc.lookup_criticality_score("kubernetes", "kubernetes")
    assert score is not None
    assert score > 0.9


def test_lookup_is_case_insensitive() -> None:
    score = oc.lookup_criticality_score("KUBERNETES", "Kubernetes")
    assert score is not None


def test_lookup_returns_none_for_unknown_repo() -> None:
    assert oc.lookup_criticality_score("nonexistent-org", "nonexistent-repo") is None


def test_lookup_returns_none_for_empty_inputs() -> None:
    assert oc.lookup_criticality_score("", "kubernetes") is None
    assert oc.lookup_criticality_score("kubernetes", "") is None


def test_shipped_snapshot_has_expected_anchors() -> None:
    """Smoke: the snapshot ships with the calibration-fixture-target anchors."""

    expected_anchors = [
        ("kubernetes", "kubernetes"),
        ("rust-lang", "rust"),
        ("torvalds", "linux"),
        ("pytorch", "pytorch"),
        ("astral-sh", "uv"),
        ("facebook", "react"),
        ("vercel", "next.js"),
        ("etcd-io", "etcd"),
    ]
    for owner, repo in expected_anchors:
        score = oc.lookup_criticality_score(owner, repo)
        assert score is not None, f"missing anchor: {owner}/{repo}"
        assert 0.0 <= score <= 1.0


def test_missing_snapshot_falls_back_to_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing snapshot file should not crash; lookup returns None."""

    monkeypatch.setattr(oc, "SNAPSHOT_PATH", tmp_path / "missing.csv")
    oc.reset_snapshot_cache()

    assert oc.lookup_criticality_score("kubernetes", "kubernetes") is None


def test_malformed_rows_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Malformed rows in the snapshot are skipped, not crash-inducing."""

    snapshot = tmp_path / "snap.csv"
    snapshot.write_text(
        "# header line\n"
        "repo,score\n"
        "kubernetes/kubernetes,0.95\n"
        "garbage_no_score\n"  # no comma — skipped
        "rust-lang/rust,not-a-number\n"  # non-numeric score — skipped
        "etcd-io/etcd,0.88\n"
    )
    monkeypatch.setattr(oc, "SNAPSHOT_PATH", snapshot)
    oc.reset_snapshot_cache()

    assert oc.lookup_criticality_score("kubernetes", "kubernetes") == 0.95
    assert oc.lookup_criticality_score("etcd-io", "etcd") == 0.88
    assert oc.lookup_criticality_score("rust-lang", "rust") is None


def test_score_clamped_to_unit_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defensive clamp: out-of-range scores get bounded to [0, 1]."""

    snapshot = tmp_path / "snap.csv"
    snapshot.write_text(
        "repo,score\n"
        "weird-org/weird-repo,1.5\n"
        "negative-org/negative-repo,-0.3\n"
    )
    monkeypatch.setattr(oc, "SNAPSHOT_PATH", snapshot)
    oc.reset_snapshot_cache()

    assert oc.lookup_criticality_score("weird-org", "weird-repo") == 1.0
    assert oc.lookup_criticality_score("negative-org", "negative-repo") == 0.0
