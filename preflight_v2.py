"""
Preflight v2 — Structured brief generation from a JD.

Instead of generating freeform archetypes (which produced the "3+ years minimum bar"
and generic archetypes that caused the permissiveness problem), this preflight asks
Opus to answer specific structured questions. The answers become the Brief's
parametric content.

Usage:
    1. Opus reads the JD and answers the structured questions.
    2. The operator reviews and edits the answers (highest-leverage QA point).
    3. The brief assembles from the reviewed answers.

The operator review step is critical. Preflight generates a DRAFT — the operator
confirms the depth distinction, non-fit patterns, and employer signal rules before
the pipeline runs. This is where you catch "3+ years minimum bar" before it becomes
398 annotation workers in your pipeline.
"""

import json
from typing import Optional


# ---------------------------------------------------------------------------
# PREFLIGHT PROMPT
# ---------------------------------------------------------------------------
# This prompt asks Opus to answer the specific questions that map to Brief fields.
# The output is structured JSON that can be reviewed, edited, and loaded.
# ---------------------------------------------------------------------------

PREFLIGHT_PROMPT = """You are analyzing a job description to generate evaluation criteria for an autonomous sourcing agent. The agent will use these criteria to evaluate hundreds of LinkedIn profiles, so precision matters — small biases compound across many evaluations.

Answer each question below based ONLY on the job description provided. If the JD doesn't provide enough information for a confident answer, say so — do NOT fill gaps with generic criteria. Generic criteria cause either false positives (saving everyone vaguely adjacent) or false negatives (rejecting on keyword absence).

JOB DESCRIPTION:
{jd_text}

{geography_context}

═══════════════════════════════════════════════════════
Answer each question as a JSON object. Respond with ONLY the JSON, no preamble.
═══════════════════════════════════════════════════════

{{
  "role_title": "exact title from JD",
  "role_level": "IC level or seniority (e.g., IC4, Senior, Staff, Lead, Director)",
  "role_summary": "2-3 sentence description of what this person actually does day-to-day. Not a rephrasing of the JD — a synthesized description of the work.",

  "capability_areas": [
    {{
      "name": "short name for this capability area",
      "description": "1-2 sentences: what work in this area looks like at this level",
      "builder_signals": ["specific evidence that someone BUILDS in this area — project types, methodologies, outputs"],
      "user_signals": ["specific evidence that someone USES outputs from this area — deploying, fine-tuning for apps, consuming APIs"],
      "key_terms": ["terms that discriminate builders from users in this area — terms only builders would use"]
    }}
  ],

  "depth_distinction": {{
    "builder_definition": "what 'building' means for THIS role specifically — not generic ML work, but the specific type of systems/artifacts this person creates",
    "user_definition": "what 'using' looks like — the application-layer version of this work that looks similar on a resume but isn't the same job",
    "edge_case_guidance": "how to handle profiles that are genuinely borderline — what tips the balance toward save vs. reject"
  }},

  "non_fit_patterns": [
    {{
      "label": "short name",
      "description": "what this person actually builds every day",
      "why_not": "why their work doesn't connect to this role despite surface similarity",
      "examples": ["concrete example: 'fraud detection ML at a fintech'"]
    }}
  ],

  "employer_signal_rules": [
    {{
      "tier": "frontier_lab | strong_ai | general_tech | neutral",
      "employer_patterns": ["company names or patterns"],
      "evidence_required": "what additional evidence beyond employer is needed to save",
      "save_on_employer_alone": false
    }}
  ],

  "minimum_years_experience": 0,
  "minimum_bar_description": "what the minimum bar means in practice — not just years, but what those years should contain",

  "facial_calibration": {{
    "expected_yes_rate_low": 0.25,
    "expected_yes_rate_high": 0.55,
    "fast_exit_patterns": ["career trajectories where the ENTIRE history is obviously outside scope — every position points away from relevance"],
    "trajectory_yes_patterns": ["career trajectory patterns detectable from title+company+dates that FAVOR passing to full evaluation — e.g., positions at frontier labs, research-to-industry transitions, specific keywords in titles"],
    "trajectory_ambiguous_patterns": ["career trajectory patterns that CANNOT be resolved from a snippet alone — e.g., 'ML Engineer at a strong company' where the specific domain is unknown. These MUST default to YES. This is the most important category — when in doubt, a pattern is ambiguous, not NO."],
    "trajectory_no_patterns": ["career trajectory patterns that favor rejection ONLY if the ENTIRE career history matches — e.g., 'entire career is data analytics/BI with no ML engineering positions'. Even one exception in the trajectory should flip to ambiguous."]
  }},

  "market_density": "sparse | moderate | dense",

  "preflight_confidence_notes": "flag any areas where the JD didn't provide enough info for a confident answer — these are the fields the operator should review most carefully"
}}"""


def generate_preflight_prompt(
    jd_text: str,
    geography: Optional[str] = None,
) -> str:
    """
    Build the preflight prompt from a JD and optional geography context.
    Returns the prompt string to send to Opus.
    """
    geo_context = ""
    if geography:
        geo_context = (
            f"GEOGRAPHY CONTEXT: This search targets candidates in {geography}. "
            f"Consider local employer landscape, relevant institutions, and typical "
            f"profile patterns for this market when generating non-fit patterns and "
            f"employer signal rules."
        )

    return PREFLIGHT_PROMPT.format(
        jd_text=jd_text,
        geography_context=geo_context,
    )


def parse_preflight_response(raw: str) -> dict:
    """
    Parse the preflight JSON response from Opus.
    Strips markdown fences if present. Returns the raw dict for operator review.
    """
    cleaned = raw.strip()
    # Strip markdown code fences
    if cleaned.startswith("```"):
        # Remove first line (```json or ```)
        lines = cleaned.split("\n")
        lines = lines[1:]  # drop opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # drop closing fence
        cleaned = "\n".join(lines)

    return json.loads(cleaned)


def preflight_to_brief_json(preflight_data: dict, overrides: Optional[dict] = None) -> dict:
    """
    Convert preflight output to a Brief-compatible JSON structure.

    The `overrides` dict lets the operator patch specific fields after review.
    This is the QA step — the operator reviews the preflight output, edits
    what needs editing, and the final brief assembles from the merge.

    Example overrides:
        {"minimum_years_experience": 5, "market_density": "dense"}
    """
    result = {**preflight_data}
    if overrides:
        for key, value in overrides.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = {**result[key], **value}
            else:
                result[key] = value
    return result


# ---------------------------------------------------------------------------
# OPERATOR REVIEW FORMATTING
# ---------------------------------------------------------------------------
# Formats the preflight output for human review before the pipeline runs.
# ---------------------------------------------------------------------------

def format_for_review(preflight_data: dict) -> str:
    """
    Format preflight output as a readable review document.
    The operator reads this, edits what's wrong, and confirms.
    """
    lines = []
    lines.append("=" * 70)
    lines.append("PREFLIGHT REVIEW — EDIT BEFORE CONFIRMING")
    lines.append("=" * 70)
    lines.append("")

    lines.append(f"Role: {preflight_data.get('role_title', '???')} ({preflight_data.get('role_level', '???')})")
    lines.append(f"Summary: {preflight_data.get('role_summary', '???')}")
    lines.append("")

    # Capability areas
    lines.append("─" * 40)
    lines.append("CAPABILITY AREAS")
    lines.append("─" * 40)
    for i, ca in enumerate(preflight_data.get("capability_areas", []), 1):
        lines.append(f"\n  {i}. {ca['name']}")
        lines.append(f"     What it looks like: {ca['description']}")
        lines.append(f"     Builder signals: {', '.join(ca['builder_signals'])}")
        lines.append(f"     User signals: {', '.join(ca['user_signals'])}")
        if ca.get("key_terms"):
            lines.append(f"     Key terms: {', '.join(ca['key_terms'])}")
    lines.append("")

    # Depth distinction
    dd = preflight_data.get("depth_distinction", {})
    lines.append("─" * 40)
    lines.append("DEPTH DISTINCTION (highest-leverage review point)")
    lines.append("─" * 40)
    lines.append(f"  BUILDER (save): {dd.get('builder_definition', '???')}")
    lines.append(f"  USER (reject):  {dd.get('user_definition', '???')}")
    lines.append(f"  Edge cases:     {dd.get('edge_case_guidance', '???')}")
    lines.append("")

    # Non-fit patterns
    lines.append("─" * 40)
    lines.append("NON-FIT PATTERNS")
    lines.append("─" * 40)
    for nf in preflight_data.get("non_fit_patterns", []):
        examples = f" (e.g., {', '.join(nf['examples'])})" if nf.get("examples") else ""
        lines.append(f"  - {nf['label']}: {nf['description']}{examples}")
        lines.append(f"    Why not: {nf['why_not']}")
    lines.append("")

    # Employer signals
    lines.append("─" * 40)
    lines.append("EMPLOYER SIGNAL RULES")
    lines.append("─" * 40)
    for rule in preflight_data.get("employer_signal_rules", []):
        companies = ", ".join(rule["employer_patterns"])
        lines.append(f"  [{rule['tier']}] {companies}")
        lines.append(f"    Evidence required: {rule['evidence_required']}")
        lines.append(f"    Save on employer alone: {rule['save_on_employer_alone']}")
    lines.append("")

    # Minimum bar
    lines.append("─" * 40)
    lines.append("MINIMUM BAR")
    lines.append("─" * 40)
    lines.append(f"  Years: {preflight_data.get('minimum_years_experience', '???')}+")
    lines.append(f"  Meaning: {preflight_data.get('minimum_bar_description', '???')}")
    lines.append("")

    # Confidence notes
    notes = preflight_data.get("preflight_confidence_notes", "")
    if notes:
        lines.append("─" * 40)
        lines.append("⚠  PREFLIGHT CONFIDENCE NOTES — REVIEW THESE CAREFULLY")
        lines.append("─" * 40)
        lines.append(f"  {notes}")
        lines.append("")

    # Facial calibration — trajectory patterns
    fc = preflight_data.get("facial_calibration", {})
    lines.append("─" * 40)
    lines.append("FACIAL TRIAGE — TRAJECTORY PATTERNS")
    lines.append("─" * 40)
    lines.append("\n  Fast exits (entire career clearly outside scope):")
    for p in fc.get("fast_exit_patterns", []):
        lines.append(f"    - {p}")
    lines.append("\n  YES patterns (trajectory signals favoring full review):")
    for p in fc.get("trajectory_yes_patterns", []):
        lines.append(f"    - {p}")
    lines.append("\n  AMBIGUOUS patterns (default YES — cannot resolve from snippet):")
    for p in fc.get("trajectory_ambiguous_patterns", []):
        lines.append(f"    - {p}")
    lines.append("\n  NO patterns (only if ENTIRE history matches):")
    for p in fc.get("trajectory_no_patterns", []):
        lines.append(f"    - {p}")
    lines.append("")

    lines.append("=" * 70)
    lines.append("Review complete. Edit the JSON and confirm to proceed.")
    lines.append("=" * 70)

    return "\n".join(lines)
