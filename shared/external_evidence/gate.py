"""Heuristic trigger gate for the candidate-level external-evidence step.

Slice 1 keeps this minimal and dependency-free: a pure function over the already
extracted ``CandidateProfileSummary``. The ``Brief`` is accepted in the signature
so that slice 2/3 can layer in role/brief-aware gating without rewiring callers,
but slice 1 deliberately does not consult it.

The gate never raises and never performs I/O.
"""

from __future__ import annotations

from shared.brief_schema import Brief
from shared.schemas import CandidateProfileSummary, TriggerDecision

_PHD_TOKENS: tuple[str, ...] = ("phd", "ph.d", "doctor")


def _has_phd_education(summary: CandidateProfileSummary) -> bool:
    for edu in summary.education:
        degree = (edu.degree or "").lower()
        for token in _PHD_TOKENS:
            if token in degree:
                return True
    return False


def _bullet_count(summary: CandidateProfileSummary) -> int:
    return sum(len(exp.summary_bullets) for exp in summary.experiences)


def should_request_external_evidence(
    *,
    summary: CandidateProfileSummary,
    brief: Brief,
) -> TriggerDecision:
    """Decide whether to request external evidence augmentation for this candidate.

    Slice 1 only fires on two heuristics:

    - ``academic_context``: any education entry whose degree mentions PhD.
    - ``sparse_profile``: at most 2 experiences AND fewer than 3 total bullets.

    Anything else returns ``should_run=False`` with ``skip_reason="no_trigger_matched"``.
    The ``brief`` argument is reserved for slice 2/3 and is intentionally unused
    here (kept in the signature so callers don't break when policy lands).
    """

    del brief  # reserved for slice 2/3 — intentionally unused in slice 1.

    experience_count = len(summary.experiences)
    education_count = len(summary.education)
    bullet_total = _bullet_count(summary)
    has_phd = _has_phd_education(summary)

    base_signals: dict = {
        "experience_count": experience_count,
        "education_count": education_count,
        "bullet_total": bullet_total,
        "has_phd": has_phd,
    }

    if has_phd:
        return TriggerDecision(
            should_run=True,
            reason="academic_context",
            skip_reason="",
            signals={**base_signals, "fired": "academic_context"},
        )

    if experience_count <= 2 and bullet_total < 3:
        return TriggerDecision(
            should_run=True,
            reason="sparse_profile",
            skip_reason="",
            signals={**base_signals, "fired": "sparse_profile"},
        )

    return TriggerDecision(
        should_run=False,
        reason="",
        skip_reason="no_trigger_matched",
        signals={**base_signals, "fired": "none"},
    )
