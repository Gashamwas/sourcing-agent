"""Opus judgment: snippet -> OpusDecision, summary -> OpusDecision.

Prompts are built dynamically from the brief — not hardcoded.
The brief is the single source of truth for evaluation criteria.
"""

from __future__ import annotations
import json
from schemas import CandidateSnippet, CandidateProfileSummary, OpusDecision
from llm_clients import opus_llm
from brief_loader import Brief

# Module-level brief, set by init_judger()
_brief: Brief | None = None


def init_judger(brief: Brief) -> None:
    """Initialize the judger with a sourcing brief."""
    global _brief
    _brief = brief


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_preview_scan_section(brief: Brief) -> str:
    """Build preview scan criteria section from brief."""
    psc = brief.raw.get("preview_scan_criteria", {})
    if not psc:
        return ""
    rule = psc.get("rule", "")
    signals = psc.get("signals", [])
    if not signals:
        return ""
    signals_text = "\n".join(f"- {s}" for s in signals)
    return f"\n## Preview Scan Criteria\n{rule}\n{signals_text}\n"


def _build_calibration_section(brief: Brief) -> str:
    """Build calibration examples section from brief."""
    cal = brief.raw.get("calibration_examples", {})
    if not cal:
        return ""
    parts = []
    strong = cal.get("strong_saves", [])
    if strong:
        parts.append("### Strong Saves (correct)")
        for ex in strong:
            parts.append(f"- {ex['name']}: {ex['why']}")
    incorrect = cal.get("incorrect_saves", [])
    if incorrect:
        parts.append("### Incorrect Saves (should have been rejected)")
        for ex in incorrect:
            parts.append(f"- {ex['name']}: {ex['why']}")
    borderline = cal.get("borderline_verify", [])
    if borderline:
        parts.append("### Borderline (verify carefully)")
        for ex in borderline:
            parts.append(f"- {ex['name']}: {ex['why']}")
    if not parts:
        return ""
    return "\n## Calibration Examples\n" + "\n".join(parts) + "\n"


def _build_clear_skips_section(brief: Brief) -> str:
    """Build clear skips section from brief."""
    clear_skips = brief.clear_skips_from_review
    if not clear_skips:
        return ""
    text = "\n".join(f"- {s}" for s in clear_skips)
    return f"\n## Clear Skips from Review\n{text}\n"


YOE_INSTRUCTION = """
## Experience Counting — MANDATORY
When calculating years of experience, you MUST count:
- PhD programs: add the full duration (typically 4-6 years) to career experience
- Master's programs: add 1-2 years
- Research positions (postdoc, research scientist, predoctoral): count as full work experience
- The start date of the EARLIEST of: first degree, first job, or PhD program start

Examples:
- PhD started 2011, graduated 2016, first industry job 2016 → 15 years experience in 2026 (count from 2011)
- MS started 2009, first job 2011 → 17 years experience in 2026 (count from 2009)
- BS 2007, PhD 2011-2016, career 2016-present → 19 years experience in 2026 (count from 2007)

Do NOT count only post-graduation industry years. Advanced degrees are professional development that counts toward total experience."""


def _build_facial_system(brief: Brief) -> str:
    role = brief.role_title
    description = brief.role_description
    minimum_bar = brief.minimum_bar

    hard_skips = brief.hard_skips
    hard_skips_text = "\n".join(f"- {s}" for s in hard_skips) if hard_skips else "None defined"

    archetypes = brief.archetypes
    arch_text = ""
    for a in archetypes:
        arch_text += f"- {a['name']}"
        if a.get("capability_area"):
            arch_text += f" ({a['capability_area']})"
        arch_text += f": {a.get('pattern', '')}\n"
    if not arch_text:
        arch_text = "None defined"

    # Noise archetypes are optional — only include if the brief defines them
    noise_section = ""
    noise = brief.noise_archetypes
    if noise:
        noise_text = ""
        for n in noise:
            noise_text += f"- {n['name']}: {n.get('description', '')}\n"
        noise_section = f"\n## Noise Archetypes (skip these)\n{noise_text}"

    preview_section = _build_preview_scan_section(brief)
    calibration_section = _build_calibration_section(brief)
    clear_skips_section = _build_clear_skips_section(brief)

    return f"""You are a senior technical recruiter evaluating candidates for: {role}

{description}

## Minimum Bar
{minimum_bar}
{YOE_INSTRUCTION}

## Hard Skips (instant reject)
{hard_skips_text}
{preview_section}{clear_skips_section}
## Target Archetypes
{arch_text}{noise_section}{calibration_section}
## Your Task
Make a quick facial-fit judgment. Would a human sourcer open this profile to learn more?

The cost of a false positive is MUCH lower than a false negative. When uncertain, lean FACIAL_YES.

Return JSON only:
- "decision": "FACIAL_YES" or "FACIAL_NO"
- "path": most likely archetype name, or "none"
- "confidence": float 0.0-1.0
- "rationale": One concise sentence with specific evidence"""


def _build_full_system(brief: Brief) -> str:
    role = brief.role_title
    description = brief.role_description
    minimum_bar = brief.minimum_bar

    exp_floor = brief.experience_floor
    if isinstance(exp_floor, dict) and exp_floor:
        exp_text = f"Required: {exp_floor.get('required', '')}\nDisqualifying: {exp_floor.get('disqualifying', '')}"
        if exp_floor.get("note"):
            exp_text += f"\nNote: {exp_floor['note']}"
    else:
        exp_text = str(exp_floor) if exp_floor else "Not specified"

    # Pull evaluation fields from raw if available
    evaluation = brief.raw.get("evaluation", {})
    save_threshold = evaluation.get("save_threshold", "")
    capability_areas = evaluation.get("capability_areas", "")

    hard_skips = brief.hard_skips
    hard_skips_text = "\n".join(f"- {s}" for s in hard_skips) if hard_skips else "None"

    clear_skips = brief.clear_skips_from_review
    clear_skips_text = "\n".join(f"- {s}" for s in clear_skips) if clear_skips else "None"

    archetypes = brief.archetypes
    arch_text = ""
    for a in archetypes:
        arch_text += f"\n### {a['name']}"
        if a.get("capability_area"):
            arch_text += f" ({a['capability_area']})"
        arch_text += f"\n{a.get('pattern', '')}\n"
        if a.get("save_signals"):
            arch_text += "Save signals:\n"
            for s in a["save_signals"]:
                arch_text += f"  + {s}\n"
        if a.get("skip_signals"):
            arch_text += "Skip signals:\n"
            for s in a["skip_signals"]:
                arch_text += f"  - {s}\n"
    if not arch_text:
        arch_text = "None defined"

    # Noise archetypes are optional — only include if the brief defines them
    noise_section = ""
    noise = brief.noise_archetypes
    if noise:
        noise_text = ""
        for n in noise:
            noise_text += f"\n### {n['name']}\n{n.get('description', '')}\n"
            if n.get("signals"):
                for s in n["signals"]:
                    noise_text += f"  - {s}\n"
        noise_section = f"\n## Noise Archetypes\n{noise_text}"

    preview_section = _build_preview_scan_section(brief)
    calibration_section = _build_calibration_section(brief)

    return f"""You are a senior technical recruiter making the FINAL save/reject decision for: {role}

{description}

## Minimum Bar
{minimum_bar}
{YOE_INSTRUCTION}

## Experience Floor
{exp_text}

## Save Threshold
{save_threshold}

## Capability Areas
{capability_areas}

## Hard Skips
{hard_skips_text}
{preview_section}
## Clear Skips from Review
{clear_skips_text}

## Target Archetypes (with save/skip signals)
{arch_text}{noise_section}{calibration_section}
## Your Task
Make the FINAL save/reject decision. Only save when you can articulate a clear case — what they built, which archetype, why the signal crosses the threshold.

Return JSON only:
- "decision": "SAVE" or "REJECT"
- "path": matching archetype name, or "none"
- "confidence": float 0.0-1.0
- "rationale": 1-2 sentences with specific evidence"""


# ---------------------------------------------------------------------------
# Stage 2: Facial judgment
# ---------------------------------------------------------------------------

def facial_judge(snippet: CandidateSnippet, brief: Brief | None = None) -> OpusDecision:
    b = brief or _brief
    if not b:
        raise RuntimeError("Judger not initialized. Call init_judger(brief) or pass brief.")

    system = _build_facial_system(b)

    career_section = ""
    if snippet.experience_entries:
        career_lines = "\n".join(f"- {e}" for e in snippet.experience_entries)
        career_section = f"\n\nCareer History:\n{career_lines}"

    user_prompt = f"""## Candidate Snippet
Name: {snippet.name}
Headline: {snippet.headline}
Current Title: {snippet.current_title}
Current Company: {snippet.current_company}
Location: {snippet.location}
Education: {snippet.education_snippet}{career_section}

Decide: FACIAL_YES or FACIAL_NO."""

    result = opus_llm(system, user_prompt, expect_json=True)

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
# Stage 4: Full judgment
# ---------------------------------------------------------------------------

def full_judge(summary: CandidateProfileSummary, brief: Brief | None = None) -> OpusDecision:
    b = brief or _brief
    if not b:
        raise RuntimeError("Judger not initialized. Call init_judger(brief) or pass brief.")

    system = _build_full_system(b)

    exp_text = ""
    for e in summary.experiences:
        bullets = "; ".join(e.summary_bullets) if e.summary_bullets else "no details"
        exp_text += f"- {e.title} at {e.company} ({e.start}-{e.end}): {bullets}\n"

    edu_text = ""
    for e in summary.education:
        edu_text += f"- {e.degree} in {e.field}, {e.school} ({e.start}-{e.end})\n"

    skills_text = ", ".join(summary.skills_snippet) if summary.skills_snippet else "none listed"

    user_prompt = f"""## Candidate Profile
Name: {summary.name}
Headline: {summary.headline}

Experience:
{exp_text if exp_text else "None listed"}

Education:
{edu_text if edu_text else "None listed"}

Skills: {skills_text}

Decide: SAVE or REJECT."""

    result = opus_llm(system, user_prompt, expect_json=True)

    return OpusDecision(
        stage="full",
        decision=result.get("decision", "REJECT"),
        path=result.get("path", "none"),
        confidence=float(result.get("confidence", 0.0)),
        rationale=result.get("rationale", ""),
        candidate_name=summary.name,
        profile_url=summary.profile_url,
    )
