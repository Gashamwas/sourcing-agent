"""Tests for :mod:`github.network_dependents` (Slice 3 — OSS Maintainers).

The HTTP fetch is impractical to unit-test without recording the page
HTML; we instead test the regex parser directly with realistic
fixtures lifted from the dependents page markup pattern. The parser
is the brittle surface (per spec §12) so this is where defense lives.
"""

from __future__ import annotations

from github import network_dependents as nd


def test_parse_extracts_repository_count() -> None:
    html = """
    <a class="btn-link selected" href="/owner/repo/network/dependents">
      <svg></svg>
      12,345
      <span>Repositories</span>
    </a>
    <a class="btn-link" href="/owner/repo/network/dependents?dependent_type=PACKAGE">
      <svg></svg>
      678
      <span>Packages</span>
    </a>
    """
    assert nd._parse_count(html) == 12345


def test_parse_falls_back_to_packages_when_repositories_absent() -> None:
    html = """
    <a class="btn-link selected">
      <svg></svg>
      890
      <span>Packages</span>
    </a>
    """
    assert nd._parse_count(html) == 890


def test_parse_handles_lowercase_label() -> None:
    """Resilience against minor markup changes — case-insensitive label match."""

    html = "<span>123,456 repositories</span>"
    assert nd._parse_count(html) == 123456


def test_parse_returns_none_for_empty_or_unrecognized() -> None:
    assert nd._parse_count("") is None
    assert nd._parse_count("<html><body>Nothing here</body></html>") is None


def test_parse_returns_none_for_non_numeric_segment() -> None:
    """Defense against DOM mutation that puts non-digits where the count was."""

    html = "<span>--- Repositories</span>"
    assert nd._parse_count(html) is None


def test_parse_extracts_large_count() -> None:
    """Heavily-depended-upon projects (millions of dependents) parse cleanly."""

    html = "<span>5,432,109 Repositories</span>"
    assert nd._parse_count(html) == 5432109
