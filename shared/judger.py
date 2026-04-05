"""Opus judgment: snippet -> OpusDecision, summary -> OpusDecision.

Prompts are built dynamically from the brief — not hardcoded.
The brief is the single source of truth for evaluation criteria.

V2 briefs use structural templates from judgment_templates.py (claim-and-evidence
procedure with capability mapping + depth test). Old briefs use the original
prompt builders below.
"""

from __future__ import annotations
import json
import logging
import re
from shared.failures import (
    is_failure_decision as _is_failure_decision,
    judgment_failure_decision,
    parse_failure_decision,
)
from shared.schemas import CandidateSnippet, CandidateProfileSummary, OpusDecision
from shared.llm_clients import opus_llm, opus_llm_cached, facial_llm
from shared.brief_loader import Brief

logger = logging.getLogger(__name__)

# Valid decisions for old-brief prompt contracts
_VALID_FACIAL = {"FACIAL_YES", "FACIAL_NO"}
_VALID_FULL = {"SAVE", "REJECT"}


def _safe_confidence(val, default: float = 0.5) -> float:
    """Safely convert a value to float, returning default on failure."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def is_failure_decision(decision: str) -> bool:
    """True if decision represents a non-terminal parse/judgment failure."""
    return _is_failure_decision(decision)


def extract_priority_rank(path: str) -> int:
    """Extract capability area rank from a decision path.

    Paths look like 'DIRECT:3. Agentic Systems...' or 'ADJACENT:1. RL Post-Training|TRANSFERABLE'.
    Returns the numeric rank (1-based), or 0 if not found.
    """
    m = re.search(r':(\d+)\.', path)
    return int(m.group(1)) if m else 0
from linkedin.judgment_templates import (
    assemble_facial_prompt,
    assemble_facial_system,
    assemble_full_evaluation_prompt,
    assemble_full_evaluation_system,
    assemble_facial_batch_system,
    parse_facial_response,
    parse_facial_batch_response,
    parse_full_evaluation_response,
)

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

## Non-Fit Patterns (genuinely wrong profiles — wrong career stage, wrong domain entirely)
{hard_skips_text}
{preview_section}{clear_skips_section}
## Target Archetypes (evaluate these FIRST — match before checking non-fit patterns)
{arch_text}{noise_section}{calibration_section}
## Your Task
Make a quick facial-fit judgment. Would a human sourcer open this profile to learn more?

THINK LIKE A RECRUITER, NOT A KEYWORD MATCHER. Synthesize the datapoints:
- What does the combination of employer + title + skills imply about their actual work?
- If someone works at a competitor or adjacent company doing related technical work, they likely have transferable depth even if their profile doesn't spell out every capability.
- A PhD + industry AI role + specific technical signals often means the person operates at a level beyond what their LinkedIn bullet points describe.
- Infer what's probable from context: e.g., someone building RAG systems and agentic frameworks at a major AI company is almost certainly working with training data, evaluation, and model quality — even if they don't say "data curation" verbatim.

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
        caution = a.get("caution_signals") or a.get("skip_signals")
        if caution:
            arch_text += "Caution signals (lookalikes — verify, don't auto-reject):\n"
            for s in caution:
                arch_text += f"  ~ {s}\n"
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

    return f"""You are a senior technical recruiter deciding if this candidate is worth a conversation for: {role}

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

## Target Archetypes (evaluate these FIRST)
{arch_text}{noise_section}{calibration_section}

## Non-Fit Patterns (check AFTER archetype evaluation — only if no archetype matches)
{hard_skips_text}
{preview_section}
## Weaker Signal Patterns (not auto-reject — verify against overall profile strength)
{clear_skips_text}

## Your Task
Decide if this candidate is worth a conversation.

SYNTHESIZE, DON'T CHECKLIST. Your job is to evaluate the whole candidate, not to check whether specific phrases appear on their profile.
- Combine employer, title, education, skills, and project descriptions to infer what this person actually does day-to-day — not just what they wrote down.
- Competitor employees doing adjacent work are high-value targets. If they work at a company that does similar work to this role, they almost certainly have relevant depth that isn't fully described on LinkedIn.
- PhD + senior industry role + relevant technical domain = assume depth beyond what's listed. These people don't put everything on LinkedIn.
- Ask: "Would a hiring manager want to talk to this person?" not "Does this profile explicitly mention every capability area?"
- The profile is a partial signal. A 30-minute conversation would reveal whether the depth is there. Your job is to decide if that conversation is worth having.

SAVE when the combination of datapoints makes a compelling case, even if no single datapoint is a perfect match. REJECT when the datapoints collectively point away from the role — wrong domain, wrong depth, wrong trajectory.

Return JSON only:
- "decision": "SAVE" or "REJECT"
- "path": matching archetype name, or "none"
- "confidence": float 0.0-1.0
- "rationale": 1-2 sentences with specific evidence"""


# ---------------------------------------------------------------------------
# V2 helpers: format pipeline schemas → text for structural templates
# ---------------------------------------------------------------------------

def _snippet_to_text(snippet: CandidateSnippet) -> str:
    """Format a CandidateSnippet as plain text for the facial template."""
    lines = [
        f"Name: {snippet.name}",
        f"Headline: {snippet.headline}",
        f"Current Title: {snippet.current_title}",
        f"Current Company: {snippet.current_company}",
        f"Location: {snippet.location}",
        f"Education: {snippet.education_snippet}",
    ]
    if snippet.experience_entries:
        lines.append("")
        lines.append("Career History:")
        for entry in snippet.experience_entries:
            lines.append(f"- {entry}")
    return "\n".join(lines)


def _profile_to_text(summary: CandidateProfileSummary) -> str:
    """Format a CandidateProfileSummary as plain text for the full eval template."""
    lines = [
        f"Name: {summary.name}",
        f"Headline: {summary.headline}",
        "",
        "Experience:",
    ]
    if summary.experiences:
        for e in summary.experiences:
            bullets = "; ".join(e.summary_bullets) if e.summary_bullets else "no details"
            lines.append(f"- {e.title} at {e.company} ({e.start}-{e.end}): {bullets}")
    else:
        lines.append("None listed")

    lines.append("")
    lines.append("Education:")
    if summary.education:
        for e in summary.education:
            lines.append(f"- {e.degree} in {e.field}, {e.school} ({e.start}-{e.end})")
    else:
        lines.append("None listed")

    skills_text = ", ".join(summary.skills_snippet) if summary.skills_snippet else "none listed"
    lines.append("")
    lines.append(f"Skills: {skills_text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stage 2: Facial judgment
# ---------------------------------------------------------------------------

def facial_judge(snippet: CandidateSnippet, brief: Brief | None = None, prompt_prefix: str = "") -> OpusDecision:
    b = brief or _brief
    if not b:
        raise RuntimeError("Judger not initialized. Call init_judger(brief) or pass brief.")

    # --- V2 path: structural templates with prompt caching ---
    if b.has_v2_schema:
        system = assemble_facial_system(b._new_brief)
        snippet_text = _snippet_to_text(snippet)
        user_msg = snippet_text
        if prompt_prefix:
            user_msg = prompt_prefix + user_msg
        try:
            raw = facial_llm(system, user_msg, expect_json=False)
        except Exception as e:
            logger.warning("V2 facial judge exception: %s", e)
            return judgment_failure_decision(
                stage="facial",
                candidate_name=snippet.name,
                profile_url=snippet.profile_url,
                error=e,
                source="judgment",
            )
        result = parse_facial_response(raw)
        confidence = 0.0 if is_failure_decision(result.decision) else 1.0
        return OpusDecision(
            stage="facial",
            decision=result.decision,
            path="none",
            confidence=confidence,
            rationale=result.reason,
            candidate_name=snippet.name,
            profile_url=snippet.profile_url,
        )

    # --- Old path: original prompt builders ---
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

    try:
        result = opus_llm_cached(system, user_prompt, expect_json=True)
    except Exception as e:
        logger.warning("old-brief facial judge exception: %s", e)
        return judgment_failure_decision(
            stage="facial",
            candidate_name=snippet.name,
            profile_url=snippet.profile_url,
            error=e,
            source="judgment",
        )

    raw_decision = result.get("decision") if isinstance(result, dict) else None
    if raw_decision not in _VALID_FACIAL:
        logger.warning("facial parse-failure: decision=%r (old-brief path)", raw_decision)
        return parse_failure_decision(
            stage="facial",
            candidate_name=snippet.name,
            profile_url=snippet.profile_url,
            reason="invalid_decision",
            detail=f"decision={raw_decision!r}",
        )
    return OpusDecision(
        stage="facial",
        decision=raw_decision,
        path=result.get("path", "none"),
        confidence=_safe_confidence(result.get("confidence", 0.5)),
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

    # --- V2 path: structural templates with prompt caching ---
    if b.has_v2_schema:
        system = assemble_full_evaluation_system(b._new_brief)
        profile_text = _profile_to_text(summary)
        try:
            raw = opus_llm_cached(system, profile_text, expect_json=False)
        except Exception as e:
            logger.warning("V2 full judge exception: %s", e)
            return judgment_failure_decision(
                stage="full",
                candidate_name=summary.name,
                profile_url=summary.profile_url,
                error=e,
                source="judgment",
            )
        result = parse_full_evaluation_response(raw)
        # Build path from match_type + capability_area for downstream logging
        if result.match_type and result.capability_area:
            path = f"{result.match_type}:{result.capability_area}"
        elif result.match_type:
            path = result.match_type.lower()
        else:
            path = result.capability_area or "none"
        # Append transferability info if present
        if result.transferability and result.transferability not in ("N/A", None):
            path += f"|{result.transferability}"
        return OpusDecision(
            stage="full",
            decision=result.decision,
            path=path,
            confidence=result.confidence,
            rationale=result.summary or result.case_for or "[parse error]",
            candidate_name=summary.name,
            profile_url=summary.profile_url,
            post_save_modifier=getattr(result, 'post_save_modifier', 'NONE'),
        )

    # --- Old path: original prompt builders ---
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

    try:
        result = opus_llm_cached(system, user_prompt, expect_json=True)
    except Exception as e:
        logger.warning("old-brief full judge exception: %s", e)
        return judgment_failure_decision(
            stage="full",
            candidate_name=summary.name,
            profile_url=summary.profile_url,
            error=e,
            source="judgment",
        )

    raw_decision = result.get("decision") if isinstance(result, dict) else None
    if raw_decision not in _VALID_FULL:
        logger.warning("full parse-failure: decision=%r (old-brief path)", raw_decision)
        return parse_failure_decision(
            stage="full",
            candidate_name=summary.name,
            profile_url=summary.profile_url,
            reason="invalid_decision",
            detail=f"decision={raw_decision!r}",
        )
    return OpusDecision(
        stage="full",
        decision=raw_decision,
        path=result.get("path", "none"),
        confidence=_safe_confidence(result.get("confidence", 0.5)),
        rationale=result.get("rationale", ""),
        candidate_name=summary.name,
        profile_url=summary.profile_url,
    )


# ---------------------------------------------------------------------------
# GitHub-specific judges
# ---------------------------------------------------------------------------

def github_facial_judge(portfolio_text: str, brief: Brief | None = None) -> OpusDecision:
    """GitHub facial triage — uses portfolio summary from cheap model extraction.

    Unlike LinkedIn facial which receives a CandidateSnippet, GitHub facial
    receives the structured portfolio text (toolchain, repos, contributions).
    """
    from github.judgment_templates import (
        assemble_github_facial_system,
        parse_facial_response,
    )

    b = brief or _brief
    if not b:
        raise RuntimeError("Judger not initialized. Call init_judger(brief) or pass brief.")

    if not b.has_v2_schema:
        raise RuntimeError("GitHub judges require a V2 brief with capability_areas.")

    system = assemble_github_facial_system(b._new_brief)
    try:
        raw = facial_llm(system, portfolio_text, expect_json=False)
    except Exception as e:
        logger.warning("GitHub facial judge exception: %s", e)
        return judgment_failure_decision(
            stage="facial",
            candidate_name="",
            profile_url="",
            error=e,
            source="judgment",
        )
    result = parse_facial_response(raw)

    return OpusDecision(
        stage="facial",
        decision=result.decision,
        path="none",
        confidence=0.0 if is_failure_decision(result.decision) else 1.0,
        rationale=result.reason,
        candidate_name="",  # Caller sets this
        profile_url="",     # Caller sets this
    )


def github_full_judge(evidence_text: str, brief: Brief | None = None) -> OpusDecision:
    """GitHub full evaluation — uses enriched evidence text.

    Unlike LinkedIn full which receives a CandidateProfileSummary, GitHub full
    receives the complete evidence text (toolchain, repos, READMEs, papers, etc.).
    """
    from github.judgment_templates import (
        assemble_github_full_evaluation_system,
        parse_full_evaluation_response,
    )

    b = brief or _brief
    if not b:
        raise RuntimeError("Judger not initialized. Call init_judger(brief) or pass brief.")

    if not b.has_v2_schema:
        raise RuntimeError("GitHub judges require a V2 brief with capability_areas.")

    system = assemble_github_full_evaluation_system(b._new_brief)
    try:
        raw = opus_llm_cached(system, evidence_text, expect_json=False)
    except Exception as e:
        logger.warning("GitHub full judge exception: %s", e)
        return judgment_failure_decision(
            stage="full",
            candidate_name="",
            profile_url="",
            error=e,
            source="judgment",
        )
    result = parse_full_evaluation_response(raw)

    # Build path from match_type + capability_area
    if result.match_type and result.capability_area:
        path = f"{result.match_type}:{result.capability_area}"
    elif result.match_type:
        path = result.match_type.lower()
    else:
        path = result.capability_area or "none"
    if result.transferability and result.transferability not in ("N/A", None):
        path += f"|{result.transferability}"

    return OpusDecision(
        stage="full",
        decision=result.decision,
        path=path,
        confidence=result.confidence,
        rationale=result.summary or result.case_for or "[parse error]",
        candidate_name="",  # Caller sets this
        profile_url="",     # Caller sets this
    )


# ---------------------------------------------------------------------------
# Batch facial triage (Phase 2)
# ---------------------------------------------------------------------------

def facial_judge_batch(
    snippets: list[CandidateSnippet],
    brief: Brief | None = None,
    prompt_prefix: str = "",
) -> list[OpusDecision]:
    """Batch facial triage — one LLM call for all snippets on a page.

    V2 briefs only. Falls back to sequential for old briefs or on batch failure.
    """
    b = brief or _brief
    if not b:
        raise RuntimeError("Judger not initialized. Call init_judger(brief) or pass brief.")

    if not b.has_v2_schema:
        return [facial_judge(s, b, prompt_prefix=prompt_prefix) for s in snippets]

    if not snippets:
        return []

    # Build batch user message
    snippet_texts = [_snippet_to_text(s) for s in snippets]
    numbered = "\n\n".join(f"[{i+1}] {text}" for i, text in enumerate(snippet_texts))
    user_msg = numbered
    if prompt_prefix:
        user_msg = prompt_prefix + user_msg

    system = assemble_facial_batch_system(b._new_brief)

    try:
        raw = facial_llm(system, user_msg, expect_json=False, max_tokens=4096)
    except Exception as e:
        logger.warning("Batch facial judge failed, falling back to sequential: %s", e)
        return [facial_judge(s, b, prompt_prefix=prompt_prefix) for s in snippets]

    results = parse_facial_batch_response(raw, len(snippets))

    decisions: list[OpusDecision | None] = []
    failed_indexes: list[int] = []
    for idx, (snippet, result) in enumerate(zip(snippets, results)):
        if is_failure_decision(result.decision):
            failed_indexes.append(idx)
            decisions.append(None)
            continue

        decisions.append(OpusDecision(
            stage="facial",
            decision=result.decision,
            path="none",
            confidence=1.0,
            rationale=result.reason,
            candidate_name=snippet.name,
            profile_url=snippet.profile_url,
        ))

    if failed_indexes:
        logger.warning(
            "Batch facial judge had %s parse failure(s); retrying sequentially for those entries",
            len(failed_indexes),
        )
        for idx in failed_indexes:
            decisions[idx] = facial_judge(snippets[idx], b, prompt_prefix=prompt_prefix)

    return [decision for decision in decisions if decision is not None]


def github_facial_judge_batch(
    portfolio_texts: list[tuple[str, str, str]],
    brief: Brief | None = None,
) -> list[OpusDecision]:
    """Batch GitHub facial triage — one LLM call for multiple candidates.

    Args:
        portfolio_texts: list of (username, profile_url, portfolio_text) tuples
        brief: optional Brief override

    V2 briefs only. Falls back to sequential on batch failure.
    """
    from github.judgment_templates import (
        assemble_github_facial_batch_system,
    )

    b = brief or _brief
    if not b:
        raise RuntimeError("Judger not initialized.")

    if not b.has_v2_schema:
        raise RuntimeError("GitHub batch facial requires a V2 brief.")

    if not portfolio_texts:
        return []

    system = assemble_github_facial_batch_system(b._new_brief)

    # Build batch user message (reuse LinkedIn batch format: [N] content)
    numbered = "\n\n".join(
        f"[{i+1}] {text}" for i, (_, _, text) in enumerate(portfolio_texts)
    )

    try:
        raw = facial_llm(system, numbered, expect_json=False, max_tokens=4096)
    except Exception as e:
        logger.warning("GitHub batch facial failed, falling back to sequential: %s", e)
        decisions = []
        for candidate_name, profile_url, text in portfolio_texts:
            decision = github_facial_judge(text, b)
            decision.candidate_name = candidate_name
            decision.profile_url = profile_url
            decisions.append(decision)
        return decisions

    results = parse_facial_batch_response(raw, len(portfolio_texts))

    decisions: list[OpusDecision | None] = []
    failed_indexes: list[int] = []
    for idx, ((candidate_name, profile_url, _), result) in enumerate(zip(portfolio_texts, results)):
        if is_failure_decision(result.decision):
            failed_indexes.append(idx)
            decisions.append(None)
            continue

        decisions.append(OpusDecision(
            stage="facial",
            decision=result.decision,
            path="none",
            confidence=1.0,
            rationale=result.reason,
            candidate_name=candidate_name,
            profile_url=profile_url,
        ))

    if failed_indexes:
        logger.warning(
            "GitHub batch facial had %s parse failure(s); retrying sequentially for those entries",
            len(failed_indexes),
        )
        for idx in failed_indexes:
            candidate_name, profile_url, text = portfolio_texts[idx]
            decision = github_facial_judge(text, b)
            decision.candidate_name = candidate_name
            decision.profile_url = profile_url
            decisions[idx] = decision

    return [decision for decision in decisions if decision is not None]
