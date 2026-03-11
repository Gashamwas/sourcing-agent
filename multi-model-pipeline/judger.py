"""Opus judgment: snippet → OpusDecision, summary → OpusDecision.

Two stages:
1. facial_judge() — quick pass on snippet data (~200 tokens input)
2. full_judge() — deep pass on full profile summary (~1500 tokens input)

Both load the rubric from rubric.json at import time.
"""

import json
from pathlib import Path
from schemas import CandidateSnippet, CandidateProfileSummary, OpusDecision
from llm_clients import opus_llm

# Load rubric once at import
_rubric_path = Path(__file__).parent / "rubric.json"
if _rubric_path.exists():
    with open(_rubric_path) as f:
        RUBRIC = json.load(f)
else:
    RUBRIC = {}
    print("[warn] rubric.json not found — judgment quality will be degraded")


def _rubric_text() -> str:
    """Format the rubric as text for inclusion in prompts."""
    if not RUBRIC:
        return "(No rubric loaded)"
    return json.dumps(RUBRIC, indent=2)


# ---------------------------------------------------------------------------
# Stage 2: Facial judgment on snippet
# ---------------------------------------------------------------------------

FACIAL_SYSTEM = """You are a senior technical recruiter evaluating candidates for a frontier AI role. You will see a brief candidate snippet (name, headline, title, company, location, education) and a detailed evaluation rubric.

Your job: make a quick facial-fit judgment. Would a human sourcer open this profile to learn more?

The cost of a false positive (reviewing and rejecting later) is MUCH lower than a false negative (missing someone good). When uncertain, lean toward FACIAL_YES.

Return a JSON object with exactly these fields:
- "decision": "FACIAL_YES" or "FACIAL_NO"
- "path": "pedigree" or "direct_experience" or "none"
- "confidence": float 0.0-1.0
- "rationale": One concise sentence explaining the decision, tied to specific evidence in the snippet

Return valid JSON only. No markdown, no explanation outside the JSON."""


def facial_judge(snippet: CandidateSnippet) -> OpusDecision:
    """Quick facial-fit judgment on a candidate snippet."""

    user_prompt = f"""## Evaluation Rubric
{_rubric_text()}

## Candidate Snippet
Name: {snippet.name}
Headline: {snippet.headline}
Current Title: {snippet.current_title}
Current Company: {snippet.current_company}
Location: {snippet.location}
Education: {snippet.education_snippet}

Decide: FACIAL_YES or FACIAL_NO."""

    result = opus_llm(FACIAL_SYSTEM, user_prompt, expect_json=True)

    return OpusDecision(
        stage="facial",
        decision=result.get("decision", "FACIAL_NO"),
        path=result.get("path", "none"),
        confidence=float(result.get("confidence", 0.0)),
        rationale=result.get("rationale", ""),
        candidate_name=snippet.name,
        profile_url=snippet.profile_url,
    )


# ---------------------------------------------------------------------------
# Stage 4: Full judgment on profile summary
# ---------------------------------------------------------------------------

FULL_SYSTEM = """You are a senior technical recruiter making the FINAL save/reject decision for a frontier AI role. You will see a detailed candidate profile summary and the evaluation rubric.

This person will partner with researchers at OpenAI, Anthropic, and DeepMind to build RL environments, post-training pipelines, and evaluation infrastructure. Ask: "Would this person be credible in that room?"

Two paths to qualification:
- Path 1 (Pedigree/Trajectory): MSc/PhD from strong research institution + 5+ years applied ML + evidence of building products or leading teams.
- Path 2 (Direct Experience): Clear hands-on work in RLHF, RL environments, reward models, LLM fine-tuning, coding agents, eval systems. 4-5 years enough if directly relevant.

Return a JSON object with exactly these fields:
- "decision": "SAVE" or "REJECT"
- "path": "pedigree" or "direct_experience" or "none"
- "confidence": float 0.0-1.0
- "rationale": 1-2 concise sentences explaining the decision with specific evidence from the profile

Return valid JSON only. No markdown, no explanation outside the JSON."""


def full_judge(summary: CandidateProfileSummary) -> OpusDecision:
    """Final save/reject judgment on a full profile summary."""

    # Format experiences compactly
    exp_text = ""
    for e in summary.experiences:
        bullets = "; ".join(e.summary_bullets) if e.summary_bullets else "no details"
        exp_text += f"- {e.title} at {e.company} ({e.start}–{e.end}): {bullets}\n"

    edu_text = ""
    for e in summary.education:
        edu_text += f"- {e.degree} in {e.field}, {e.school} ({e.start}–{e.end})\n"

    skills_text = ", ".join(summary.skills_snippet) if summary.skills_snippet else "none listed"

    user_prompt = f"""## Evaluation Rubric
{_rubric_text()}

## Candidate Profile
Name: {summary.name}
Headline: {summary.headline}

Experience:
{exp_text if exp_text else "None listed"}

Education:
{edu_text if edu_text else "None listed"}

Skills: {skills_text}

Decide: SAVE or REJECT."""

    result = opus_llm(FULL_SYSTEM, user_prompt, expect_json=True)

    return OpusDecision(
        stage="full",
        decision=result.get("decision", "REJECT"),
        path=result.get("path", "none"),
        confidence=float(result.get("confidence", 0.0)),
        rationale=result.get("rationale", ""),
        candidate_name=summary.name,
        profile_url=summary.profile_url,
    )
