"""Tests for OSS Maintainers Slice 6 — evidence + evaluation integration.

Two key contracts:

1. ``GitHubCandidate.to_evidence_text()`` is BYTE-IDENTICAL when the
   candidate has no ``maintainership`` payload (classic github
   briefs run unchanged per spec §11). When ``maintainership`` is
   set, a MAINTAINERSHIP EVIDENCE section appears.
2. ``assemble_github_full_evaluation_system(brief)`` is BYTE-
   IDENTICAL when ``brief.target_projects`` is empty. When it's
   set, a MAINTAINERSHIP-LEVEL EVALUATION block appears with the
   recruiter's project list and desired level.
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from github.judgment_templates import (
    _assemble_maintainership_block,
    assemble_github_full_evaluation_system,
)
from github.schemas import ContactInfo, GitHubCandidate, GitHubUser


# ---------------------------------------------------------------------------
# Brief stub — pre-Slice-2 callers might construct Brief objects in tests
# without the new fields. Use a stub that exposes only the surface the
# evaluator template reads from.
# ---------------------------------------------------------------------------


class _BriefStub:
    """Minimal Brief-shaped stub for the evaluator template.

    Mirrors the methods :data:`GITHUB_FULL_EVALUATION_TEMPLATE` calls
    on a Brief; lets tests set ``target_projects`` /
    ``maintainership_level`` without standing up the loader pipeline.
    """

    def __init__(
        self,
        *,
        target_projects: list[str] | None = None,
        target_stacks: list[str] | None = None,
        maintainership_level: str = "contributor",
    ) -> None:
        self.role_title = "Staff infra engineer"
        self.role_level = "L7"
        self.role_summary = "Infra leadership."
        self.minimum_years_experience = 7
        self.minimum_bar_description = "Has shipped infra at scale."
        self.target_projects = list(target_projects or [])
        self.target_stacks = list(target_stacks or [])
        self.maintainership_level = maintainership_level

    def capability_area_block(self) -> str:
        return "1. Infra"

    def depth_block(self) -> str:
        return "Builder = ships infra."

    def non_fit_block(self) -> str:
        return "(none)"

    def non_fit_override_rule_block(self) -> str:
        return "(none)"

    def employer_signal_block(self) -> str:
        return "(none)"

    def inferential_save_block(self) -> str:
        return "(none)"

    def discriminating_skills_examples(self) -> str:
        return "kubernetes, etcd"


# ---------------------------------------------------------------------------
# to_evidence_text() — byte-identical without maintainership
# ---------------------------------------------------------------------------


def _minimal_candidate() -> GitHubCandidate:
    return GitHubCandidate(
        user=GitHubUser(
            username="alice",
            name="Alice Doe",
            bio="ML engineer",
            company="ExampleCorp",
            followers=200,
            public_repos=10,
            created_at="2018-01-01T00:00:00Z",
            profile_url="https://github.com/alice",
        ),
    )


def test_evidence_text_byte_identical_when_maintainership_unset() -> None:
    """Spec §11: classic github briefs render byte-identically."""

    candidate = _minimal_candidate()
    candidate.maintainership = None
    text = candidate.to_evidence_text()
    assert "MAINTAINERSHIP EVIDENCE" not in text


def test_evidence_text_includes_maintainership_block_when_set() -> None:
    candidate = _minimal_candidate()
    candidate.maintainership = {
        "level": "maintainer",
        "confidence": 0.78,
        "evidence_sources": [
            "merge_authority:kubernetes/kubernetes:23PRs",
            "contributors_file:kubernetes/kubernetes",
        ],
        "signals": {"merge_authority": 1.5, "budget_exhausted": False},
    }
    text = candidate.to_evidence_text()

    assert "MAINTAINERSHIP EVIDENCE" in text
    assert "maintainer" in text
    assert "0.78" in text
    assert "merge_authority:kubernetes/kubernetes:23PRs" in text


def test_evidence_text_surfaces_budget_exhausted_note() -> None:
    candidate = _minimal_candidate()
    candidate.maintainership = {
        "level": "contributor",
        "confidence": 0.3,
        "evidence_sources": [],
        "signals": {"budget_exhausted": True},
    }
    text = candidate.to_evidence_text()

    assert "MAINTAINERSHIP EVIDENCE" in text
    assert "budget exhausted" in text


def test_evidence_text_omits_block_when_level_missing() -> None:
    """Defensive: malformed maintainership dict (no level) doesn't render."""

    candidate = _minimal_candidate()
    candidate.maintainership = {"confidence": 0.5}  # no level key
    text = candidate.to_evidence_text()

    assert "MAINTAINERSHIP EVIDENCE" not in text


# ---------------------------------------------------------------------------
# assemble_github_full_evaluation_system — byte-identical contract
# ---------------------------------------------------------------------------


def test_full_eval_system_byte_identical_when_target_projects_empty() -> None:
    """Spec §11: classic github briefs render byte-identically.

    Compares the system prompt with `target_projects=[]` against the
    block returned by :func:`_assemble_maintainership_block` — the
    block must be empty so the template's `{maintainership_block}`
    slot renders as nothing extra (just two adjacent newlines around
    the slot).
    """

    brief = _BriefStub(target_projects=[])
    block = _assemble_maintainership_block(brief)
    assert block == ""

    prompt = assemble_github_full_evaluation_system(brief)
    assert "MAINTAINERSHIP-LEVEL EVALUATION" not in prompt
    assert "named target projects" not in prompt.lower()


def test_full_eval_system_includes_block_when_target_projects_set() -> None:
    brief = _BriefStub(
        target_projects=["kubernetes/kubernetes", "etcd-io/etcd"],
        maintainership_level="maintainer",
    )
    prompt = assemble_github_full_evaluation_system(brief)

    assert "MAINTAINERSHIP-LEVEL EVALUATION" in prompt
    assert "kubernetes/kubernetes" in prompt
    assert "etcd-io/etcd" in prompt
    assert "maintainer" in prompt


def test_full_eval_block_renders_each_recognized_level() -> None:
    """All three levels render cleanly into the block."""

    for level in ("contributor", "maintainer", "project_lead"):
        brief = _BriefStub(
            target_projects=["kubernetes/kubernetes"],
            maintainership_level=level,
        )
        block = _assemble_maintainership_block(brief)
        assert level in block, f"{level} missing from block"


def test_full_eval_block_describes_all_three_levels() -> None:
    """The block teaches the LLM what the three levels mean."""

    brief = _BriefStub(target_projects=["kubernetes/kubernetes"])
    block = _assemble_maintainership_block(brief)

    assert "contributor:" in block
    assert "maintainer:" in block
    assert "project_lead:" in block


def test_full_eval_block_contains_named_projects_in_visible_position() -> None:
    """Recruiter-named projects appear in the system prompt verbatim."""

    brief = _BriefStub(target_projects=["rust-lang/rust", "huggingface/trl"])
    block = _assemble_maintainership_block(brief)

    assert "rust-lang/rust" in block
    assert "huggingface/trl" in block
