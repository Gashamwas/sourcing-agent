"""Sourcing Preflight — Opus reads the JD and generates eval criteria + role understanding.

This runs once at the start of a fresh run (not on resume). It takes the JD text
(and optional intake notes / instructions) and produces the structured eval criteria
that the judger and strategy modules need: archetypes, minimum bar, noise predictions,
experience floor, and capability areas.

When a hand-written brief already provides these fields, preflight is skipped.
When only a JD is available, preflight fills in the gaps.
"""

from __future__ import annotations
import json
import sys
from llm_clients import opus_llm


def run_preflight(
    jd_text: str,
    intake_notes: str = "",
    instructions: list[str] | None = None,
    existing_archetypes: list[dict] | None = None,
    existing_minimum_bar: str = "",
) -> dict:
    """Ask Opus to derive eval criteria from JD + intake notes.

    Only generates fields that are missing. If the brief already has archetypes
    and a minimum_bar, preflight won't overwrite them.

    Returns a dict with:
        - archetypes: list of archetype dicts
        - minimum_bar: string
        - noise_archetypes: list of noise pattern dicts
        - experience_floor: dict with required/disqualifying/note
        - capability_areas: string
        - hard_skips: list of strings
        - clear_skips_from_review: list of strings
        - role_title: string
        - role_description: string
    """
    # Determine what we need to generate
    need_archetypes = not existing_archetypes
    need_minimum_bar = not existing_minimum_bar

    if not need_archetypes and not need_minimum_bar:
        print("  Preflight: Brief already has archetypes + minimum bar. Skipping.")
        return {}

    system = _build_preflight_system(need_archetypes, need_minimum_bar)
    user = _build_preflight_user(jd_text, intake_notes, instructions)

    print("  Sourcing Preflight... (Opus is reading the JD and generating eval criteria)")
    try:
        result = opus_llm(system, user, expect_json=True, max_tokens=16384)
        print("  Preflight complete.")
        return result
    except Exception as e:
        print(f"  [warn] Preflight failed ({e}) — proceeding with brief defaults", file=sys.stderr)
        return {}


def _build_preflight_system(need_archetypes: bool, need_minimum_bar: bool) -> str:
    sections_needed = []
    if need_archetypes:
        sections_needed.append("archetypes, noise_archetypes")
    if need_minimum_bar:
        sections_needed.append("minimum_bar, experience_floor, hard_skips, clear_skips_from_review")

    return f"""You are a senior technical recruiter preparing to source for a role. You are reading
a job description (and optional intake notes) to build your sourcing and evaluation criteria.

Your job: extract structured evaluation criteria that will guide both SEARCH (what Boolean
strings to generate) and EVALUATION (how to judge candidate profiles).

Think like a recruiter who just finished an intake meeting with the hiring manager. You need
to write down:
1. WHO you're looking for (archetypes — distinct candidate personas worth a conversation)
2. The MINIMUM BAR (what combination of signals makes someone worth reaching out to)
3. NOISE AWARENESS (patterns that waste time — genuinely different domains or career stages)
4. CLEAR NON-FITS (profiles where no evaluation is needed — e.g., undergraduate students, non-technical PMs)

## Language Rules for Eval Criteria
Write all criteria using INCLUSIVE language, not exclusive language. Frame rules as what TO LOOK FOR,
not what to reject. The downstream agent that reads your criteria will take absolutist language literally
and use it as permission to reject good candidates.

BAD (creates a rejection machine):
- "Simply having ML experience is insufficient"
- "No evidence of X" / "Must not" / "Does not meet the bar"
- "Only save candidates who explicitly..."

GOOD (creates a thoughtful evaluator):
- "Look for evidence of depth — building systems, not just using them"
- "Stronger candidates will show X, but adjacent experience at strong companies is also worth exploring"
- "The ideal candidate has X, though someone with Y + Z likely has transferable depth"

Never use "insufficient", "does not meet", "must not", "is not enough", or similar absolutist exclusion
language in archetypes, minimum_bar, or noise descriptions. Every criterion should guide toward
a yes/no decision, not pre-decide "no."

## Key Principles

### Sourcing ≠ Hiring
You are deciding who is worth a 30-minute conversation, NOT who gets an offer. Every candidate
you save will be manually reviewed by a human recruiter. Your job is to avoid obvious misses —
rejecting someone a hiring manager would want to talk to is FAR worse than saving someone who
turns out to be borderline.

### Synthesize, Don't Checklist
LinkedIn profiles are partial signals. People don't list everything they do. A PhD + senior role at
a strong AI company + relevant technical domain = assume depth beyond what's written. Someone
at a competitor doing adjacent work almost certainly has transferable skills. Evaluate the COMBINATION
of datapoints (employer + title + education + skills + projects), not whether specific phrases appear.

### The JD Is Not a Checklist
The JD describes the ideal candidate in the hiring manager's language. Real candidates will describe
the same work using different words, or will have done 70% of it at a company where the other 30%
was inevitable but not LinkedIn-worthy. A person building RAG systems at a major AI company has
almost certainly dealt with data quality, evaluation, and training pipelines — even if their profile says
"built RAG system" not "curated training data."

## Output Requirements
Generate ONLY the fields listed below. Return valid JSON only.

### archetypes (array of objects)
Each archetype represents a distinct candidate persona worth sourcing. For each:
- "name": Short label (e.g., "Post-Training Data Engineer")
- "capability_area": Which JD capability area this maps to
- "pattern": 2-3 sentence description of what this person's career looks like
- "save_signals": Array of 4-6 specific, observable signals that confirm this person is right
- "caution_signals": Array of 2-3 signals that suggest a lookalike rather than a true match — for calibration, not automatic rejection

Archetypes should be MUTUALLY EXCLUSIVE — each describes a different type of person.
Generate 4-6 archetypes. IMPORTANT: Include at least one archetype for "Deep ML Practitioner
at Strong Company" — senior ML/AI researchers or engineers at recognized labs, tech companies,
or competitors whose depth and employer signal make them worth a conversation even if their profile
doesn't perfectly match the JD's specific tasks. These are people a hiring manager would say "yes,
talk to them" based on pedigree + technical depth alone.

### noise_archetypes (array of objects)
Common false positive profiles that will appear in searches but should be skipped.
- "name": Label (e.g., "Fintech ML Engineer")
- "description": Why this person appears in searches but doesn't fit
- "signals": Array of 2-3 observable patterns that identify this noise type

Generate 3-6 noise archetypes. IMPORTANT GUARDRAILS:
- Do NOT create noise archetypes that would reject people with deep technical ML/AI experience at
  strong companies. "Research scientist with publications" is NOT noise for a role that needs research depth.
- Noise means genuinely wrong domain or wrong level: a marketing analyst who took a Coursera ML course,
  a project manager at an AI company who doesn't code, a data analyst doing SQL dashboards.
- If in doubt about whether a profile type is noise, leave it OUT. False negatives are much worse than false positives.

### minimum_bar (string)
A paragraph describing the minimum threshold for saving a candidate. This should be a FLOOR, not a ceiling.
Write it as: "Save anyone who..." not "Only save people who explicitly..."
- Focus on what combination of signals makes someone worth a conversation
- Include the inference principle: "If someone has X + Y, they likely have Z even if unstated"
- Do NOT require that every JD capability area be explicitly mentioned on the profile

### experience_floor (object)
- "required": What experience is necessary (years + type)
- "disqualifying": What experience rules someone out
- "note": Any nuance (e.g., "degree not required if demonstrated depth")

### hard_skips (array of strings)
Instant disqualifiers. These should be checked before any evaluation.
Examples: currently enrolled undergrads, annotation/labeling workers at specific companies.

### clear_skips_from_review (array of strings)
Profiles that are clearly wrong but might require a sentence of explanation.
Examples: "Backend engineers whose ML is ETL pipelines and dashboards."

### role_title (string)
The role title as it should appear in sourcing contexts.

### role_description (string)
2-3 sentence summary of the role for use in evaluation prompts.

### capability_areas (string)
Summary of what capability areas the candidate must show depth in.

Return valid JSON only."""


def _build_preflight_user(
    jd_text: str,
    intake_notes: str = "",
    instructions: list[str] | None = None,
) -> str:
    prompt = f"""## Job Description

{jd_text}"""

    if intake_notes:
        prompt += f"""

## Intake Notes

{intake_notes}"""

    if instructions:
        prompt += f"""

## Sourcing Instructions (from recruiter)
These override or supplement the JD where specified:
{chr(10).join(f"- {i}" for i in instructions)}"""

    prompt += """

Generate the structured eval criteria now. Return valid JSON only."""

    return prompt


def apply_preflight_to_brief(brief, preflight_result: dict) -> None:
    """Merge preflight results into a Brief, filling only empty fields."""
    if not preflight_result:
        return

    if not brief.archetypes and preflight_result.get("archetypes"):
        brief.archetypes = preflight_result["archetypes"]
        print(f"  Preflight → {len(brief.archetypes)} archetypes generated")

    if not brief.minimum_bar and preflight_result.get("minimum_bar"):
        brief.minimum_bar = preflight_result["minimum_bar"]
        print(f"  Preflight → minimum bar set")

    if not brief.noise_archetypes and preflight_result.get("noise_archetypes"):
        brief.noise_archetypes = preflight_result["noise_archetypes"]
        print(f"  Preflight → {len(brief.noise_archetypes)} noise archetypes generated")

    if not brief.hard_skips and preflight_result.get("hard_skips"):
        brief.hard_skips = preflight_result["hard_skips"]

    if not brief.clear_skips_from_review and preflight_result.get("clear_skips_from_review"):
        brief.clear_skips_from_review = preflight_result["clear_skips_from_review"]

    if not brief.experience_floor and preflight_result.get("experience_floor"):
        brief.experience_floor = preflight_result["experience_floor"]

    if not brief.role_title and preflight_result.get("role_title"):
        brief.role_title = preflight_result["role_title"]

    if not brief.role_description and preflight_result.get("role_description"):
        brief.role_description = preflight_result["role_description"]

    # Store in raw for downstream modules that read raw fields
    if preflight_result.get("capability_areas"):
        brief.raw.setdefault("evaluation", {})["capability_areas"] = preflight_result["capability_areas"]
