"""Designer judgment templates — Slice 1 placeholder.

The real text-based contextualization prompt arrives in Slice 2; the
vision-LLM evaluation prompt arrives in Slice 5. Slice 1 ships a
deterministic placeholder that returns an :class:`OpusDecision` shaped
the way the read-model contract expects (so the workspace surface can
already render Designer rows the moment Slice 6 lands the
``surface_type`` dispatch — without depending on the vision pipeline
being live).

The placeholder rationale is recruiter-readable on purpose: if a
designer brief launches before Slice 5 ships, the recruiter should see
"no judgment yet — designer pipeline not built" in the workspace card
rather than a stack trace or an empty `save_reason` field.
"""

from __future__ import annotations

from shared.schemas import OpusDecision


PLACEHOLDER_RATIONALE = (
    "no judgment yet — designer pipeline not built (Slice 1 placeholder; "
    "real text-based contextualization arrives in Slice 2, vision evaluation "
    "in Slice 5)"
)


def designer_facial_judge_placeholder(
    *,
    candidate_name: str = "",
    profile_url: str = "",
) -> OpusDecision:
    """Return a placeholder facial-stage decision.

    Until Slice 2 wires the real facial-triage prompt, every Designer
    candidate that reaches the facial stage gets `FACIAL_NO` with the
    placeholder rationale. This is the conservative posture: don't
    surface Designer candidates as saves until the pipeline can
    actually evaluate them.
    """

    return OpusDecision(
        stage="facial",
        decision="FACIAL_NO",
        path="placeholder",
        confidence=0.0,
        rationale=PLACEHOLDER_RATIONALE,
        candidate_name=candidate_name,
        profile_url=profile_url,
    )


def designer_full_judge_placeholder(
    *,
    candidate_name: str = "",
    profile_url: str = "",
) -> OpusDecision:
    """Return a placeholder full-stage decision.

    Mirrors :func:`designer_facial_judge_placeholder` shape; same
    rationale text. Slice 5 replaces this with the real vision
    evaluation flow that produces the structured visual_judgment
    payload Slice 6 renders in the HITL visual review surface.
    """

    return OpusDecision(
        stage="full",
        decision="REJECT",
        path="placeholder",
        confidence=0.0,
        rationale=PLACEHOLDER_RATIONALE,
        candidate_name=candidate_name,
        profile_url=profile_url,
    )
