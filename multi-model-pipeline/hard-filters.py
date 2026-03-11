"""Pre-Opus hard filters. Catches obvious non-matches before wasting an Opus call.

Returns (should_skip: bool, reason: str). If should_skip is True, the candidate
is logged and skipped without calling Opus.
"""

from schemas import CandidateSnippet

# ---------------------------------------------------------------------------
# Skip lists (case-insensitive matching)
# ---------------------------------------------------------------------------

ANNOTATION_COMPANIES = {
    "scale ai", "outlier", "appen", "remotasks", "surge ai",
    "invisible technologies", "crowdgen", "telus digital",
    "telus international", "dataannotation", "data annotation",
    "alignerr", "superhuman ai", "toloka",
}

SKIP_TITLES = {
    "ai trainer", "quality reviewer", "content evaluator", "ai rater",
    "prompt writer", "data annotator", "annotation specialist",
    "labeling specialist", "ai tutor", "prompt engineer",
    "rpa developer", "rpa engineer", "rpa consultant",
    "automation developer",  # often RPA
}

# Partial matches — if any of these appear in title or headline
SKIP_TITLE_FRAGMENTS = [
    "rpa",
    "robotic process automation",
    "data protection officer",  # DPO in Brazil = LGPD, not ML
]

SKIP_HEADLINE_FRAGMENTS = [
    "rpa",
    "robotic process automation",
    "data protection officer",
]


def hard_filter(snippet: CandidateSnippet) -> tuple[bool, str]:
    """Check if a candidate should be skipped before Opus evaluation.
    
    Returns:
        (should_skip, reason) — if should_skip is True, skip this candidate.
    """
    company_lower = snippet.current_company.lower().strip()
    title_lower = snippet.current_title.lower().strip()
    headline_lower = snippet.headline.lower().strip()

    # --- Annotation companies ---
    for co in ANNOTATION_COMPANIES:
        if co in company_lower:
            return True, f"Annotation company: {snippet.current_company}"

    # --- Exact title matches ---
    for skip_title in SKIP_TITLES:
        if title_lower == skip_title or title_lower.startswith(skip_title + " "):
            return True, f"Skip title: {snippet.current_title}"

    # --- Title fragment matches ---
    for frag in SKIP_TITLE_FRAGMENTS:
        if frag in title_lower:
            return True, f"Skip title fragment '{frag}': {snippet.current_title}"

    # --- Headline fragment matches ---
    for frag in SKIP_HEADLINE_FRAGMENTS:
        if frag in headline_lower:
            return True, f"Skip headline fragment '{frag}': {snippet.headline}"

    # --- Intern / undergrad TA ---
    if "intern" in title_lower and "internal" not in title_lower:
        return True, f"Intern: {snippet.current_title}"
    if "teaching assistant" in title_lower or "undergraduate ta" in title_lower:
        return True, f"Undergrad TA: {snippet.current_title}"

    return False, ""
