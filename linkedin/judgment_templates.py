"""
Judgment prompt templates for the autonomous sourcing agent.

These templates encode the STRUCTURAL evaluation procedure. They never change per role.
All role-specific content is injected from the Brief at runtime via the assemble_* functions.

The core procedure (both stages):
  1. Capability mapping — which area does this candidate's work map to?
  2. Depth test — builder or user?
  3. Decision — does the case-for survive the case-against?

Design principles:
  - Procedures, not philosophies. The model follows a reasoning sequence, not vibes.
  - Claim-and-evidence structure. Forces Opus to articulate both sides before deciding.
  - Anchored synthesis. Requires naming a specific capability area, not "strong ML background."
  - Stateless per-candidate. No cumulative save/reject context leaks into evaluation.
"""

from shared.brief_schema import Brief


# ---------------------------------------------------------------------------
# FACIAL TRIAGE TEMPLATE
# ---------------------------------------------------------------------------
# Purpose: Filter out candidates where no reasonable full evaluation could
# produce a save. This is a TRIAGE, not a judgment.
# Expected pass-through: 25-60% depending on search/market density.
# Parse failure default: YES (cost of false positive = one cheap extraction;
# cost of false negative = a permanently missed candidate).
# ---------------------------------------------------------------------------

FACIAL_TRIAGE_TEMPLATE = """You are triaging candidate snippets from LinkedIn Recruiter search results.

ROLE: {role_title} ({role_level}) — {role_summary}

YOUR TASK: Decide whether this candidate's snippet warrants a full profile review. You are deciding whether to spend tokens on a full read, not whether to save.

WHAT YOU HAVE: A name, headline, current title/company, location, education line, and a CAREER HISTORY — a list of all visible positions with titles, companies, and dates. You do NOT have job description bullets, project details, or skills. You cannot tell from this data what someone actually built at a given company.

═══════════════════════════════════════════════════════
STEP 1 — FAST EXITS
═══════════════════════════════════════════════════════

Reject immediately ONLY if the ENTIRE career trajectory clearly indicates work outside scope:
{fast_exit_block}

A fast exit requires that NO position in the career history has a plausible connection to the role. One relevant-looking position anywhere in the trajectory means this is NOT a fast exit.

═══════════════════════════════════════════════════════
STEP 2 — TRAJECTORY READ
═══════════════════════════════════════════════════════

The career history is your highest-signal field. Read the FULL trajectory, not just the current role. What you're looking for:

TRAJECTORY PATTERNS THAT FAVOR YES:
{trajectory_yes_patterns}

TRAJECTORY PATTERNS THAT ARE AMBIGUOUS (default YES — let the full evaluation resolve):
{trajectory_ambiguous_patterns}

TRAJECTORY PATTERNS THAT FAVOR NO (only if consistent across the ENTIRE history):
{trajectory_no_patterns}

CAPABILITY AREAS for this role:
{capability_area_names}

═══════════════════════════════════════════════════════
DECISION
═══════════════════════════════════════════════════════

You CANNOT distinguish domain relevance from a snippet in most cases. "ML Engineer at Nubank" could be fraud detection (reject) or model training infrastructure (save). Do NOT try to make domain calls at this stage.

- FACIAL_YES: Any position in the trajectory has a title, employer, or transition pattern that COULD connect to a capability area. Ambiguity favors YES.
- FACIAL_NO: The ENTIRE trajectory clearly indicates work outside all capability areas. Every position points away from relevance. No single entry creates doubt.

CANDIDATE SNIPPET:
{candidate_snippet}

Respond with EXACTLY this format:
DECISION: FACIAL_YES or FACIAL_NO
REASON: One sentence — what trajectory signal you see (if YES) or why the full trajectory is clearly outside scope (if NO)."""


FACIAL_TRIAGE_TEMPLATE_BATCH = """You are triaging candidate snippets from LinkedIn Recruiter search results.

ROLE: {role_title} ({role_level}) — {role_summary}

YOUR TASK: For each candidate, decide whether the snippet warrants a full profile review. You are deciding whether to spend tokens on a full read, not whether to save.

WHAT YOU HAVE: Names, headlines, current titles/companies, locations, education, and CAREER HISTORIES. You do NOT have job description bullets or project details. You cannot tell what someone actually built at a given company.

FAST EXITS — reject ONLY if the ENTIRE career trajectory clearly indicates:
{fast_exit_block}

TRAJECTORY READ — the career history is your highest-signal field. Read the FULL trajectory:

YES patterns: {trajectory_yes_patterns_compact}
AMBIGUOUS (default YES): {trajectory_ambiguous_patterns_compact}
NO patterns (only if entire history matches): {trajectory_no_patterns_compact}

CAPABILITY AREAS: {capability_area_names_inline}

You CANNOT distinguish domain relevance from snippets. "ML Engineer at Nubank" could be fraud or training infra. Do NOT make domain calls — let the full evaluation resolve.

- FACIAL_YES: Any position COULD connect to a capability area. Ambiguity favors YES.
- FACIAL_NO: ENTIRE trajectory clearly outside scope. Every position points away.

CANDIDATES:
{candidate_snippets_numbered}

Respond with EXACTLY this format for each candidate, one per line:
[candidate_number] FACIAL_YES or FACIAL_NO | one-sentence reason citing trajectory signal"""


# ---------------------------------------------------------------------------
# FULL EVALUATION TEMPLATE
# ---------------------------------------------------------------------------
# Purpose: Determine whether a candidate should be saved to the pipeline.
# This is where the bar lives. Three-step claim-and-evidence procedure.
# Parse failure default: REJECT with PARSE_FAILURE flag (auditable, not silent).
# ---------------------------------------------------------------------------

FULL_EVALUATION_TEMPLATE = """You are evaluating a candidate for a specific technical role. Follow the procedure below EXACTLY. Do not skip steps.

ROLE: {role_title} ({role_level})
{role_summary}

MINIMUM BAR: {minimum_years_experience}+ years hands-on. {minimum_bar_description}

WHAT YOU HAVE: A structured profile extracted from LinkedIn — name, headline, a list of EXPERIENCES (each with title, company, dates, and summary bullets describing their actual work), education, and a skills snippet.

EVIDENCE HIERARCHY:
1. Summary bullets from experience entries — HIGHEST value. These describe actual work.
2. Publications, team names, project names mentioned in bullets — HIGH value.
3. Title + company combinations — MODERATE value. Indicates environment but not what they built.
4. Skills list — LOWEST value for general skills. HOWEVER: highly specific technical skills ({discriminating_skills_examples} — terms only practitioners use) are meaningful signal, especially on sparse profiles. "PyTorch" tells you nothing. "QLoRA" tells you this person has fine-tuned models.

═══════════════════════════════════════════════════════
SPARSE PROFILE CHECK (run FIRST, before anything else)
═══════════════════════════════════════════════════════

A sparse profile is one with FEW OR NO summary bullets — just titles, companies, dates, and maybe a skills list. If the profile is sparse, check:

{inferential_save_block}

ADDITIONAL SPARSE SIGNAL: If the profile is sparse BUT the skills list contains highly specific practitioner terms ({discriminating_skills_examples}), treat this as supporting evidence. These terms are too specific to list without hands-on experience. A sparse profile with PhD + ML title + QLoRA in skills is a stronger inferential save than PhD + ML title alone.

If an inferential save condition is met, respond with DECISION: INFERENTIAL_SAVE, confidence 0.4–0.6. These go to the recruiter for manual review.

If no inferential save applies AND the profile is sparse, respond REJECT — not enough signal.

If the profile HAS meaningful detail, proceed to Step 1.

═══════════════════════════════════════════════════════
STEP 1 — CAPABILITY MAPPING (signal, NOT a gate)
═══════════════════════════════════════════════════════

Try to map the candidate's ACTUAL WORK to one of the following capability areas. Areas are stack-ranked — higher-ranked matches increase confidence.

{capability_area_block}

EMPLOYER SIGNAL RULES:
{employer_signal_block}

RESULT — classify the match as one of:
- DIRECT: Summary bullets describe work that falls squarely within a capability area. Cite the area and the evidence.
- ADJACENT: The work touches a capability area but isn't core to it (e.g., built ML evaluation tools but for a non-LLM domain). Note what's adjacent and why.
- NONE: No capability area maps. This is NOT an automatic reject — proceed to Step 2.

═══════════════════════════════════════════════════════
STEP 2 — DEPTH TEST (runs REGARDLESS of Step 1 result)
═══════════════════════════════════════════════════════

This step evaluates the candidate's hands-on ML depth INDEPENDENT of whether their domain matches. Read the summary bullets across ALL positions. Do they describe hands-on ML work where data quality, model training, or evaluation methodology was a primary focus?

{depth_block}

Key distinction — look at VERBS and OBJECTS in the summary bullets:
- Hands-on ML verbs: designed, built, created, fine-tuned, trained, developed (a pipeline/framework/system), published, implemented (a novel method), explored, prototyped, experimented with
- Application-layer verbs: deployed (without training), integrated (an API), managed (a team), monitored (dashboards), used (a pre-built model)
- ML-depth objects: training pipelines, evaluation suites/frameworks, reward models, fine-tuned models, data curation systems, quality metrics, annotation methodologies, synthetic data generators, RL environments, custom model architectures, novel evaluation methods
- Application-layer objects: production APIs, dashboards, business KPIs, customer-facing features, A/B test results

"Fine-tuned" is a BUILDER verb — someone who fine-tuned an LLM with hands-on PyTorch/HuggingFace work is doing model training. "Fine-tuned via API" without code is using a service.

A profile that lists relevant skills but whose bullets describe only application-layer work does not pass the depth test.

═══════════════════════════════════════════════════════
STEP 3 — TRANSFERABILITY (only if Step 1 was ADJACENT or NONE)
═══════════════════════════════════════════════════════

If Step 1 found no direct capability area match, ask: does this person's METHODOLOGY transfer to the role, even though their DOMAIN doesn't match?

The test: "If you took this person's skills and methodology and pointed them at LLM training data / RL environments / model evaluation instead of their current domain, would the skills apply?"

TRANSFERS (methodology is domain-portable):
- Evaluation framework design in any ML domain → evaluation framework design for LLMs. The person knows how to measure model quality. The specific model changes; the methodology of rigorous evaluation is the same.
- Data quality systems for model training in any domain → data quality for frontier model training. Someone who built data curation pipelines and quality metrics for computational biology models knows what training data quality means. The domain content changes; the data engineering and quality judgment transfer.
- Custom model training (architectures, training loops, hyperparameter optimization) in any domain → can learn LLM training. Deep hands-on model training experience is the hardest skill to develop.
- PhD-level research methodology with hands-on implementation → the rigor, the experimental design, the evaluation instincts transfer even when the specific research area doesn't.

DOES NOT TRANSFER (domain gap is too wide AND methodology doesn't port):
- Classical engineering simulation (CFD, FEA, circuit design) without ML → uses "simulation" but the methodology is physics-based, not learned.
- Statistical analysis / hypothesis testing without ML model building → data-adjacent but no model training methodology to transfer.
- Software engineering with no ML component → strong coding but no ML depth to port.

RESULT: TRANSFERABLE (cite what methodology transfers) or NOT_TRANSFERABLE (explain why the gap is too wide).

═══════════════════════════════════════════════════════
STEP 4 — DECISION
═══════════════════════════════════════════════════════

State the strongest CASE FOR this candidate's relevance:
- What evidence supports their fit? (capability area match, depth evidence, transferable methodology)

State the strongest CASE AGAINST:
- What's missing, misaligned, or uncertain?

NON-FIT PATTERNS — work that is valuable but outside scope:
{non_fit_block}

CRITICAL — NON-FIT OVERRIDE RULE:
{non_fit_override_rule}

DECISION MATRIX — weigh the evidence from Steps 1-3 together:

DIRECT match + BUILDER depth = SAVE (high confidence, 0.75-0.95)
ADJACENT match + BUILDER depth = SAVE (moderate confidence, 0.55-0.75)
NONE match + BUILDER depth + TRANSFERABLE methodology = SAVE (moderate confidence, 0.45-0.65, flag as TRANSFERABLE_SAVE for recruiter awareness)
NONE match + BUILDER depth + NOT TRANSFERABLE = REJECT
Any match level + USER depth = REJECT (application-layer work regardless of domain)
Sparse profile meeting inferential conditions = INFERENTIAL_SAVE (0.4-0.6)

The decision standard: would the hiring manager agree this person has the hands-on ML depth and data quality instincts to learn the FDL role? Not "already doing it at a frontier lab" — that's too high. Not "vaguely ML-adjacent" — that's too low. "Has done hands-on ML work with enough depth to grow into this role, even if their current domain is different."

The guard against permissiveness is the DEPTH TEST, not the capability mapping. A person must demonstrate hands-on ML builder depth to be saved — no exceptions. What the capability mapping determines is confidence level, not the binary decision. Strong domain match + depth = high confidence save. No domain match + depth + transferable methodology = moderate confidence save. No depth = reject regardless of domain.

CANDIDATE PROFILE:
{candidate_profile}

═══════════════════════════════════════════════════════
RESPOND WITH EXACTLY THIS FORMAT:
═══════════════════════════════════════════════════════

STEP_1_MATCH: DIRECT or ADJACENT or NONE
STEP_1_AREA: [capability area name if DIRECT/ADJACENT, or "N/A"]
STEP_1_EVIDENCE: [cite specific summary bullets, 2-3 sentences max]

STEP_2_DEPTH: BUILDER or USER
STEP_2_EVIDENCE: [what verbs/objects in the bullets indicate, 1-2 sentences]

STEP_3_TRANSFERABILITY: TRANSFERABLE or NOT_TRANSFERABLE or N/A (if DIRECT match)
STEP_3_EVIDENCE: [what methodology transfers, or why the gap is too wide, 1-2 sentences. Write "N/A" if Step 1 was DIRECT]

CASE_FOR: [strongest argument for relevance, 1-2 sentences]
CASE_AGAINST: [strongest argument against, 1-2 sentences]

DECISION: SAVE or REJECT or INFERENTIAL_SAVE or TRANSFERABLE_SAVE
CONFIDENCE: [0.0 to 1.0 — use the decision matrix ranges above]
SUMMARY: [one-line evaluation a hiring manager could act on]"""


# ---------------------------------------------------------------------------
# ASSEMBLY FUNCTIONS
# ---------------------------------------------------------------------------
# These inject Brief content into template slots at runtime.
# The judger calls these — never constructs prompts directly.
# ---------------------------------------------------------------------------

def assemble_facial_prompt(brief: Brief, candidate_snippet: str) -> str:
    """Assemble a facial triage prompt for a single candidate."""
    return FACIAL_TRIAGE_TEMPLATE.format(
        role_title=brief.role_title,
        role_level=brief.role_level,
        role_summary=brief.role_summary,
        fast_exit_block=brief.fast_exit_block(),
        trajectory_yes_patterns=brief.trajectory_yes_block(),
        trajectory_ambiguous_patterns=brief.trajectory_ambiguous_block(),
        trajectory_no_patterns=brief.trajectory_no_block(),
        capability_area_names="\n".join(f"  - {name}" for name in brief.capability_area_names()),
        candidate_snippet=candidate_snippet,
    )


def assemble_facial_prompt_batch(brief: Brief, candidate_snippets: list[str]) -> str:
    """Assemble a facial triage prompt for a batch of candidates (one page)."""
    numbered = "\n\n".join(
        f"[{i+1}] {snippet}" for i, snippet in enumerate(candidate_snippets)
    )
    return FACIAL_TRIAGE_TEMPLATE_BATCH.format(
        role_title=brief.role_title,
        role_level=brief.role_level,
        role_summary=brief.role_summary,
        fast_exit_block=brief.fast_exit_block(),
        trajectory_yes_patterns_compact=brief.trajectory_yes_compact(),
        trajectory_ambiguous_patterns_compact=brief.trajectory_ambiguous_compact(),
        trajectory_no_patterns_compact=brief.trajectory_no_compact(),
        capability_area_names_inline=brief.capability_area_names_inline(),
        candidate_snippets_numbered=numbered,
    )


def assemble_full_evaluation_prompt(brief: Brief, candidate_profile: str) -> str:
    """Assemble a full evaluation prompt for one candidate."""
    return FULL_EVALUATION_TEMPLATE.format(
        role_title=brief.role_title,
        role_level=brief.role_level,
        role_summary=brief.role_summary,
        minimum_years_experience=brief.minimum_years_experience,
        minimum_bar_description=brief.minimum_bar_description,
        capability_area_block=brief.capability_area_block(),
        depth_block=brief.depth_block(),
        non_fit_block=brief.non_fit_block(),
        non_fit_override_rule=brief.non_fit_override_rule_block(),
        employer_signal_block=brief.employer_signal_block(),
        inferential_save_block=brief.inferential_save_block(),
        discriminating_skills_examples=brief.discriminating_skills_examples(),
        candidate_profile=candidate_profile,
    )


# ---------------------------------------------------------------------------
# RESPONSE PARSING
# ---------------------------------------------------------------------------
# Strict parsers that flag failures explicitly rather than defaulting silently.
# ---------------------------------------------------------------------------

from dataclasses import dataclass
from typing import Optional


@dataclass
class FacialResult:
    decision: str           # "FACIAL_YES" | "FACIAL_NO" | "PARSE_FAILURE"
    reason: str
    raw_response: str


@dataclass
class FullEvaluationResult:
    decision: str               # "SAVE" | "REJECT" | "INFERENTIAL_SAVE" | "TRANSFERABLE_SAVE" | "PARSE_FAILURE"
    match_type: Optional[str]   # "DIRECT" | "ADJACENT" | "NONE" | None
    capability_area: Optional[str]
    capability_evidence: str
    depth: Optional[str]        # "BUILDER" | "USER" | None
    depth_evidence: str
    transferability: Optional[str]  # "TRANSFERABLE" | "NOT_TRANSFERABLE" | "N/A" | None
    transferability_evidence: str
    case_for: str
    case_against: str
    confidence: float
    summary: str
    raw_response: str


def parse_facial_response(raw: str) -> FacialResult:
    """
    Parse facial triage response.
    Default on failure: FACIAL_YES (permissive at triage, strict at full eval).
    Flags the failure explicitly.
    """
    raw_stripped = raw.strip()

    # Try to find DECISION line
    for line in raw_stripped.split("\n"):
        line_upper = line.strip().upper()
        if line_upper.startswith("DECISION:"):
            value = line_upper.replace("DECISION:", "").strip()
            if "YES" in value:
                reason = _extract_field(raw_stripped, "REASON:")
                return FacialResult("FACIAL_YES", reason, raw_stripped)
            elif "NO" in value:
                reason = _extract_field(raw_stripped, "REASON:")
                return FacialResult("FACIAL_NO", reason, raw_stripped)

    # Fallback: scan for YES/NO anywhere
    if "FACIAL_YES" in raw_stripped.upper():
        return FacialResult("FACIAL_YES", "parsed from raw", raw_stripped)
    if "FACIAL_NO" in raw_stripped.upper():
        return FacialResult("FACIAL_NO", "parsed from raw", raw_stripped)

    # Parse failure — default YES at facial stage (cost of FP = one extraction)
    return FacialResult("FACIAL_YES", "PARSE_FAILURE: defaulting to YES", raw_stripped)


def parse_full_evaluation_response(raw: str) -> FullEvaluationResult:
    """
    Parse full evaluation response (4-step format with transferability).
    Default on failure: REJECT with PARSE_FAILURE flag (auditable, not silent).
    """
    raw_stripped = raw.strip()

    try:
        # Step 1 — capability mapping (with match type)
        match_type_raw = _extract_field(raw_stripped, "STEP_1_MATCH:")
        capability_area = _extract_field(raw_stripped, "STEP_1_AREA:")
        capability_evidence = _extract_field(raw_stripped, "STEP_1_EVIDENCE:")

        # Step 2 — depth test
        depth_raw = _extract_field(raw_stripped, "STEP_2_DEPTH:")
        depth_evidence = _extract_field(raw_stripped, "STEP_2_EVIDENCE:")

        # Step 3 — transferability
        transferability_raw = _extract_field(raw_stripped, "STEP_3_TRANSFERABILITY:")
        transferability_evidence = _extract_field(raw_stripped, "STEP_3_EVIDENCE:")

        # Step 4 — decision
        case_for = _extract_field(raw_stripped, "CASE_FOR:")
        case_against = _extract_field(raw_stripped, "CASE_AGAINST:")
        decision_raw = _extract_field(raw_stripped, "DECISION:")
        confidence_raw = _extract_field(raw_stripped, "CONFIDENCE:")
        summary = _extract_field(raw_stripped, "SUMMARY:")

        # Parse match type
        match_type = None
        mt_upper = match_type_raw.upper().strip()
        if "DIRECT" in mt_upper:
            match_type = "DIRECT"
        elif "ADJACENT" in mt_upper:
            match_type = "ADJACENT"
        elif "NONE" in mt_upper:
            match_type = "NONE"

        # Parse decision — check specific types before generic SAVE
        decision = "PARSE_FAILURE"
        decision_upper = decision_raw.upper()
        if "TRANSFERABLE_SAVE" in decision_upper:
            decision = "TRANSFERABLE_SAVE"
        elif "INFERENTIAL_SAVE" in decision_upper:
            decision = "INFERENTIAL_SAVE"
        elif "SAVE" in decision_upper:
            decision = "SAVE"
        elif "REJECT" in decision_upper:
            decision = "REJECT"

        # Parse depth
        depth = None
        if "BUILDER" in depth_raw.upper():
            depth = "BUILDER"
        elif "USER" in depth_raw.upper():
            depth = "USER"

        # Parse transferability
        transferability = None
        t_upper = transferability_raw.upper().strip()
        if "NOT_TRANSFERABLE" in t_upper:
            transferability = "NOT_TRANSFERABLE"
        elif "TRANSFERABLE" in t_upper:
            transferability = "TRANSFERABLE"
        elif "N/A" in t_upper:
            transferability = "N/A"

        # Parse confidence
        try:
            confidence = float(confidence_raw.strip())
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, AttributeError):
            confidence = 0.5

        # Parse capability area
        cap_area = capability_area.strip()
        if cap_area.upper() in ("NONE", "N/A", ""):
            cap_area = None

        return FullEvaluationResult(
            decision=decision,
            match_type=match_type,
            capability_area=cap_area,
            capability_evidence=capability_evidence,
            depth=depth,
            depth_evidence=depth_evidence,
            transferability=transferability,
            transferability_evidence=transferability_evidence,
            case_for=case_for,
            case_against=case_against,
            confidence=confidence,
            summary=summary,
            raw_response=raw_stripped,
        )

    except Exception:
        return FullEvaluationResult(
            decision="REJECT",
            match_type=None,
            capability_area=None,
            capability_evidence="",
            depth=None,
            depth_evidence="",
            transferability=None,
            transferability_evidence="",
            case_for="",
            case_against="PARSE_FAILURE — could not extract structured response",
            confidence=0.0,
            summary="PARSE_FAILURE",
            raw_response=raw_stripped,
        )


def _extract_field(text: str, field_name: str) -> str:
    """Extract the value after a field label, handling multi-line values."""
    # Known field names — used for reliable boundary detection
    KNOWN_FIELDS = {
        "STEP_1_MATCH", "STEP_1_AREA", "STEP_1_EVIDENCE",
        "STEP_1_CAPABILITY_AREA",  # legacy format compat
        "STEP_2_DEPTH", "STEP_2_EVIDENCE",
        "STEP_3_TRANSFERABILITY", "STEP_3_EVIDENCE",
        "CASE_FOR", "CASE_AGAINST",
        "DECISION", "CONFIDENCE", "SUMMARY",
    }

    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.strip().upper().startswith(field_name.upper()):
            # Value is everything after the first colon on this line
            value = line.split(":", 1)[1].strip() if ":" in line else ""
            # Collect continuation lines until we hit another known field
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if next_line and ":" in next_line:
                    pre_colon = next_line.split(":")[0].strip().upper()
                    if pre_colon in KNOWN_FIELDS:
                        break
                if next_line:
                    value += " " + next_line
                j += 1
            return value.strip()
    return ""
