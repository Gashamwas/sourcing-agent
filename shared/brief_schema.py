"""
Brief schema for the autonomous sourcing agent.

The Brief carries ALL role-specific parametric content. The evaluation templates,
adaptation heuristics, and reporting layer read from this schema — nothing role-specific
lives outside it. Swapping roles means swapping briefs, nothing else.

Integrates with existing brief_loader.py — the loader normalizes whatever JSON format
you hand it into this dataclass.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class MarketDensity(str, Enum):
    """How talent-dense the search geography/domain is. Controls pagination depth."""
    SPARSE = "sparse"        # Few plausible candidates per string. Paginate conservatively.
    MODERATE = "moderate"    # Normal distribution. Default pagination.
    DENSE = "dense"          # Many plausible candidates per string. Paginate deeper but watch for volume inversion.


@dataclass
class PostSaveModifier:
    """
    A confidence modifier that fires ONLY after a save decision has been made
    on the core capability areas. Cannot trigger a rejection — only adjusts
    confidence on already-saved candidates.
    """
    name: str                       # e.g. "Client-Facing / Forward-Deployed Delivery Experience"
    trigger: str                    # When this modifier fires
    if_present: str                 # What to do if present (boost)
    if_absent: str                  # What to do if absent (no adjustment)
    signals: list[str] = field(default_factory=list)  # Evidence signals


@dataclass
class CapabilityArea:
    """
    A single domain that defines part of the role's scope.
    The evaluation template maps every candidate against these.
    """
    name: str                       # e.g. "Post-Training Data & RLHF Pipelines"
    description: str                # 1-2 sentences: what work in this area looks like
    builder_signals: list[str]      # Specific evidence that someone BUILDS in this area
    user_signals: list[str]         # Specific evidence that someone USES outputs from this area
    key_terms: list[str] = field(default_factory=list)  # Terms that discriminate builders from users
    github_code_signals: list[str] = field(default_factory=list)


@dataclass
class NonFitPattern:
    """
    A common profile type that appears in search results, looks adjacent, but isn't a fit.
    Must describe WORK, not titles or keywords.
    """
    label: str                      # e.g. "Applied ML for business metrics"
    description: str                # What this person actually builds every day
    why_not: str                    # Why it doesn't connect to the role despite surface similarity
    examples: list[str] = field(default_factory=list)  # Concrete examples: "fraud detection at Nubank"


@dataclass
class EmployerSignalRule:
    """
    How much weight company name carries, and what additional evidence is required.
    """
    tier: str                       # "frontier_lab" | "strong_ai" | "general_tech" | "neutral"
    employer_patterns: list[str]    # Company names or patterns that fall in this tier
    evidence_required: str          # What ADDITIONAL evidence beyond employer is needed to save
    save_on_employer_alone: bool    # Whether employer + relevant title is sufficient (almost always False)


@dataclass
class DepthDistinction:
    """
    The single most important calibration point. Defines what "builder" vs "user"
    means for THIS specific role. Role-specific, not generic.
    """
    builder_definition: str         # What "building" means for this role
    user_definition: str            # What "using" means — the application layer
    edge_case_guidance: str         # How to handle borderline cases (e.g., MLOps that touches training)


@dataclass
class FacialCalibration:
    """
    Expected pass-through rates for the facial triage stage.
    Used for anomaly detection, not as thresholds.
    """
    expected_yes_rate_low: float    # Lower bound of healthy range (e.g., 0.25)
    expected_yes_rate_high: float   # Upper bound of healthy range (e.g., 0.55)
    fast_exit_patterns: list[str]   # Narrow, concrete list of obviously-out-of-scope work

    # Trajectory patterns — what career histories signal at the snippet level.
    # These are the highest-information field available at facial stage.
    trajectory_yes_patterns: list[str]       # Career patterns that favor YES
    trajectory_ambiguous_patterns: list[str]  # Patterns that default to YES (let full eval resolve)
    trajectory_no_patterns: list[str]         # Patterns that favor NO (only if entire history matches)

    github_fast_exit_patterns: list[str] = field(default_factory=list)
    github_portfolio_yes_patterns: list[str] = field(default_factory=list)
    github_portfolio_ambiguous_patterns: list[str] = field(default_factory=list)
    github_portfolio_no_patterns: list[str] = field(default_factory=list)


@dataclass
class BiasControls:
    """
    Role-level tuning for the compounding bias controls.
    The controls themselves are in the orchestrator; these are the parameters.
    """
    max_consecutive_saves: int = 5          # Auto-pause string after N saves with no reject
    max_consecutive_rejects: int = 20       # Flag for review — may indicate prompt drift or bad string
    parse_failure_alarm_rate: float = 0.03  # Flag if parse failures exceed this % of evaluations


@dataclass
class Brief:
    """
    Complete brief for one sourcing search.
    Everything the evaluation templates, adaptation layer, and orchestrator need.
    """

    # --- Identity ---
    role_title: str                                 # e.g. "Junior Frontier Data Lead"
    role_level: str                                 # e.g. "IC4"
    role_summary: str                               # 2-3 sentence description of what the role does
    geography: str                                  # e.g. "Brazil"
    linkedin_project: str                           # LinkedIn Recruiter project name/ID for saves

    # --- Capability Areas (the anchors for Step 1 of evaluation) ---
    capability_areas: list[CapabilityArea]           # 3-7 domains that define scope

    # --- Depth Distinction (the anchor for Step 2 of evaluation) ---
    depth_distinction: DepthDistinction

    # --- Non-Fit Patterns (checked AFTER capability mapping, not before) ---
    non_fit_patterns: list[NonFitPattern]

    # --- Employer Signal Rules ---
    employer_signal_rules: list[EmployerSignalRule]

    # --- Minimum Bar ---
    minimum_years_experience: int                   # Hard floor for experience
    minimum_bar_description: str                    # What the minimum bar means in practice

    # --- Facial Triage Calibration ---
    facial_calibration: FacialCalibration

    # --- Search Configuration ---
    market_density: MarketDensity = MarketDensity.MODERATE
    employer_blacklist: list[str] = field(default_factory=list)
    kit_url: Optional[str] = None
    jd_path: Optional[str] = None

    # --- Bias Controls ---
    bias_controls: BiasControls = field(default_factory=BiasControls)

    # --- V3 Extensions (optional — backwards compatible with V2 briefs) ---
    inferential_save_rules: Optional[dict] = None       # Conditions for saving sparse high-prior profiles
    non_fit_override_rule: str = ""                       # Rule for when evidence overrides non-fit patterns
    calibration_examples: Optional[dict] = None          # Strong/incorrect/borderline examples for evaluation
    instructions: list[str] = field(default_factory=list) # Role-specific instructions injected into prompt

    # --- V4 Extensions ---
    post_save_modifiers: list[PostSaveModifier] = field(default_factory=list)
    additional_search_terms: list[str] = field(default_factory=list)

    # --- Metadata ---
    version: str = "1.0"
    author: str = ""
    notes: str = ""

    def capability_area_names(self) -> list[str]:
        """Convenience: list of just the capability area names for template injection."""
        return [ca.name for ca in self.capability_areas]

    def capability_area_block(self) -> str:
        """
        Formats capability areas for injection into evaluation prompts.
        Each area gets its name, description, and builder signals.
        """
        lines = []
        for i, ca in enumerate(self.capability_areas, 1):
            lines.append(f"{i}. {ca.name}")
            lines.append(f"   What it looks like: {ca.description}")
            lines.append(f"   Builder signals: {', '.join(ca.builder_signals)}")
            if ca.user_signals:
                lines.append(f"   NOT this (user signals): {', '.join(ca.user_signals)}")
            if ca.key_terms:
                lines.append(f"   Discriminating terms: {', '.join(ca.key_terms)}")
            lines.append("")
        return "\n".join(lines)

    def depth_block(self) -> str:
        """Formats the depth distinction for injection into evaluation prompts."""
        d = self.depth_distinction
        return (
            f"BUILDER (save): {d.builder_definition}\n"
            f"USER (reject): {d.user_definition}\n"
            f"Edge cases: {d.edge_case_guidance}"
        )

    def non_fit_block(self) -> str:
        """Formats non-fit patterns for injection into evaluation prompts."""
        lines = []
        for nf in self.non_fit_patterns:
            examples_str = f" (e.g., {', '.join(nf.examples)})" if nf.examples else ""
            lines.append(f"- {nf.label}: {nf.description}{examples_str}")
            lines.append(f"  Why not: {nf.why_not}")
        return "\n".join(lines)

    def employer_signal_block(self) -> str:
        """Formats employer signal rules for injection into evaluation prompts."""
        lines = []
        for rule in self.employer_signal_rules:
            companies = ", ".join(rule.employer_patterns)
            lines.append(f"- [{rule.tier}] {companies}")
            lines.append(f"  Required evidence: {rule.evidence_required}")
            if rule.save_on_employer_alone:
                lines.append(f"  Note: Employer + relevant title is sufficient for this tier.")
        return "\n".join(lines)

    def fast_exit_block(self) -> str:
        """Formats fast exit patterns for the facial triage prompt."""
        return "\n".join(f"- {p}" for p in self.facial_calibration.fast_exit_patterns)

    def trajectory_yes_block(self) -> str:
        """Formats trajectory YES patterns for facial triage."""
        return "\n".join(f"- {p}" for p in self.facial_calibration.trajectory_yes_patterns)

    def trajectory_ambiguous_block(self) -> str:
        """Formats trajectory AMBIGUOUS patterns for facial triage."""
        return "\n".join(f"- {p}" for p in self.facial_calibration.trajectory_ambiguous_patterns)

    def trajectory_no_block(self) -> str:
        """Formats trajectory NO patterns for facial triage."""
        return "\n".join(f"- {p}" for p in self.facial_calibration.trajectory_no_patterns)

    def trajectory_yes_compact(self) -> str:
        """One-line version for batch facial prompt."""
        return "; ".join(self.facial_calibration.trajectory_yes_patterns)

    def trajectory_ambiguous_compact(self) -> str:
        """One-line version for batch facial prompt."""
        return "; ".join(self.facial_calibration.trajectory_ambiguous_patterns)

    def trajectory_no_compact(self) -> str:
        """One-line version for batch facial prompt."""
        return "; ".join(self.facial_calibration.trajectory_no_patterns)

    def non_fit_compact(self) -> str:
        """Compact version of non-fit patterns for batch facial prompt.
        Bullet format with why_not reasoning (the actionable part), drops description.
        """
        parts = []
        for nf in self.non_fit_patterns:
            parts.append(f"• {nf.label} — {nf.why_not}")
        return "\n".join(parts)

    def capability_area_names_inline(self) -> str:
        """Comma-separated capability area names for compact prompts."""
        return ", ".join(ca.name for ca in self.capability_areas)

    def inferential_save_block(self) -> str:
        """Formats inferential save conditions for the full evaluation prompt."""
        if not self.inferential_save_rules:
            return "No inferential save pathway defined for this role. Sparse profiles default to REJECT."
        conditions = self.inferential_save_rules.get("conditions", [])
        lines = [self.inferential_save_rules.get("description", "")]
        lines.append("")
        lines.append("Conditions (if ANY of these are met, respond INFERENTIAL_SAVE):")
        for c in conditions:
            lines.append(f"  - {c}")
        return "\n".join(lines)

    def non_fit_override_rule_block(self) -> str:
        """Formats the non-fit override rule for the full evaluation prompt."""
        if not self.non_fit_override_rule:
            return "Non-fit patterns apply as stated. No override rule."
        return self.non_fit_override_rule

    def github_fast_exit_block(self) -> str:
        """Formats GitHub fast exit patterns for the facial triage prompt."""
        patterns = self.facial_calibration.github_fast_exit_patterns
        if not patterns:
            # Sensible defaults
            patterns = [
                "Profile has zero non-fork repositories AND no bio AND no profile README",
                "ALL repositories are unmodified forks of tutorials or course materials with no original commits",
                "Account is an organization, not an individual",
            ]
        return "\n".join(f"- {p}" for p in patterns)

    def github_portfolio_yes_block(self) -> str:
        """Formats GitHub portfolio YES patterns for facial triage."""
        patterns = self.facial_calibration.github_portfolio_yes_patterns
        if not patterns:
            patterns = [
                "Repos using frontier ML toolchain frameworks (trl, axolotl, lm-evaluation-harness, swe-bench, vllm, deepeval, unsloth, peft)",
                "Contributed to known frontier AI repositories (huggingface/trl, EleutherAI/lm-evaluation-harness, OpenRLHF/OpenRLHF, etc.)",
                "Repos tagged with capability area topics (reinforcement-learning, rlhf, reward-model, fine-tuning, evaluation)",
                "Bio or profile README mentions ML research, model training, evaluation, or specific frontier frameworks",
                "Published papers in ML (arxiv links in profile README or website)",
                "Personal website with ML project descriptions or research portfolio",
                "Repos with >50 stars in ML-relevant domains",
            ]
        return "\n".join(f"- {p}" for p in patterns)

    def github_portfolio_ambiguous_block(self) -> str:
        """Formats GitHub portfolio AMBIGUOUS patterns for facial triage."""
        patterns = self.facial_calibration.github_portfolio_ambiguous_patterns
        if not patterns:
            patterns = [
                "Python repos with generic topics but company field shows a known tech/AI company",
                "Sparse public profile but high follower count (>100) or starred frontier repos",
                "Private-heavy account (high account age, few public repos, but what exists looks relevant)",
                "Website exists but content unclear from portfolio summary",
                "Mix of ML and non-ML repos — direction unclear without deeper analysis",
            ]
        return "\n".join(f"- {p}" for p in patterns)

    def github_portfolio_no_block(self) -> str:
        """Formats GitHub portfolio NO patterns for facial triage."""
        patterns = self.facial_calibration.github_portfolio_no_patterns
        if not patterns:
            patterns = [
                "ALL repos are web frontend only (React, Vue, Angular, HTML/CSS) with no ML signal",
                "ALL repos are DevOps/infrastructure only (Terraform, Ansible, Docker, Kubernetes) with no ML",
                "ALL repos are data analytics with no ML (SQL, Tableau, pandas for reporting)",
                "Profile is clearly a student with only coursework repos and no framework usage",
                "ALL repos are mobile development (iOS/Android) with no ML component",
            ]
        return "\n".join(f"- {p}" for p in patterns)

    def github_code_signals_block(self) -> str:
        """Formats GitHub code signals from capability areas for evaluation."""
        lines = []
        for ca in self.capability_areas:
            if ca.github_code_signals:
                lines.append(f"  {ca.name}: {', '.join(ca.github_code_signals)}")
        if not lines:
            return "(No GitHub-specific code signals defined in brief — use general capability area key_terms)"
        return "\n".join(lines)

    def discriminating_skills_examples(self) -> str:
        """
        Collects key_terms from all capability areas as examples of
        discriminating skills — terms too specific to list without hands-on experience.
        Used in the sparse profile check to upgrade inferential saves.
        """
        terms = []
        for ca in self.capability_areas:
            terms.extend(ca.key_terms[:3])  # Top 3 from each area
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for t in terms:
            if t.lower() not in seen:
                seen.add(t.lower())
                unique.append(t)
        return ", ".join(unique[:15])  # Cap at 15 examples

    # --- Seniority-Aware Evaluation Methods ---

    def is_senior_role(self) -> bool:
        """Whether this role targets L7+ / executive-track candidates."""
        level = self.role_level.upper()
        for n in range(7, 15):
            if f"L{n}" in level:
                return True
        for kw in ("DIRECTOR", "VP", "HEAD", "EXECUTIVE", "PRINCIPAL", "DISTINGUISHED"):
            if kw in level:
                return True
        return False

    def seniority_calibration_block(self) -> str:
        """Three-tier evidence framework for L7+ roles. Empty string for IC roles."""
        if not self.is_senior_role():
            return ""
        return f"""
SENIORITY CALIBRATION ({self.role_level}):
At the executive level (L7+), the evidence hierarchy shifts. Senior leaders describe work at a higher abstraction level — "pioneering Agentic AI paradigms" and "translating R&D into products delivering $10M+ impact" rather than "built a LangGraph pipeline with Pinecone." This is expected, not a deficiency.

For L7+ candidates, apply THREE TIERS of evidence:

Tier 1 — Direct Evidence: Profile explicitly names tools, systems, production metrics, action verbs with specificity. Standard evaluation. Strongest signal when present.

Tier 2 — Contextual Inference: Title + company + scope + budget + team size make it overwhelmingly likely the person has the capability. "Head of AI at Franklin Templeton, built global R&D teams, $12-15M budget, $10M+ monthly economic impact" → this person almost certainly drove technical architecture decisions and built production AI systems, even though their bullets describe organizational achievements. For L7+ candidates, Tier 2 evidence is CO-PRIMARY with Tier 1 — not a fallback.

Tier 3 — Trajectory Inference: No single position provides evidence, but the career arc does. MIT PhD → BofA quant → JPMorgan VP → Head of AI at a major asset manager → Amazon Senior Research Scientist. The trajectory tells you the person has deep technical foundations, has led AI at enterprise scale, and is currently at a top-tier research organization. For L8-L9 candidates, Tier 3 can independently support a SAVE when the trajectory is unambiguous.

You MUST state which tier supports each of your conclusions. Do not reject a candidate for lacking Tier 1 evidence when Tier 2 or Tier 3 evidence is strong."""

    def executive_builder_block(self) -> str:
        """Executive builder calibration for L7+ roles. Empty string for IC roles."""
        if not self.is_senior_role():
            return ""
        return f"""
EXECUTIVE BUILDER CALIBRATION ({self.role_level}):
At the L7+ level, the builder/user distinction shifts. An executive who:
- Built and led the AI function at an enterprise from scratch
- Hired and developed the technical team that builds the systems
- Set the technical direction and made architecture-level decisions
- Directed multi-million-dollar R&D budgets toward production AI
- Drove R&D-to-production translation with measurable business impact
- Holds a PhD or deep technical background that preceded their leadership career

...is a BUILDER at the organizational level. They build the MACHINE that builds the systems. The test is NOT "do they still write code" — it's "did they build and technically direct the AI capability, and does their background demonstrate they have the depth to evaluate and critique technical work at the architecture level?"

Organizational builder verbs for L7+: built (teams/functions/organizations), established (AI governance, technical standards), directed (R&D budgets, technical strategy), pioneered (new AI paradigms, architectural approaches), translated (R&D into production). These are BUILDER signals at this seniority, not USER signals.

Career trajectory as depth evidence: A career arc from PhD → quantitative research → engineering leadership → Head of AI demonstrates hands-on technical foundations that preceded the executive role. The person didn't start as a manager — they started as a builder and scaled. Weight this heavily."""

    def decision_matrix_block(self) -> str:
        """Returns the full decision matrix text, seniority-aware for L7+ roles."""
        base = """DECISION MATRIX — weigh the evidence from Steps 1-3 together:

DIRECT match + BUILDER depth = SAVE (high confidence, 0.80-0.95)
ADJACENT match + BUILDER depth = SAVE (moderate confidence, 0.60-0.75)
NONE match + BUILDER depth + TRANSFERABLE methodology = SAVE (moderate confidence, 0.45-0.55, flag as TRANSFERABLE_SAVE for recruiter awareness)
NONE match + BUILDER depth + NOT TRANSFERABLE = REJECT
"""
        if self.is_senior_role():
            base += f"""Any match level + USER depth (for IC/L4-L6 roles) = REJECT
Any match level + USER depth (for L7+ roles) = REJECT ONLY IF the profile shows no technical foundation in career history (no PhD, no engineering IC roles, no technical leadership progression). If the candidate has a technical career arc that preceded their executive role, re-evaluate using the Executive Builder Calibration above before rejecting.
"""
        else:
            base += """Any match level + USER depth = REJECT (application-layer work regardless of domain)
"""
        base += """Sparse profile meeting inferential conditions = INFERENTIAL_SAVE (0.35-0.50)

CONFIDENCE CALIBRATION (within each range):
- Top of range: Multiple independent evidence sources.
- Middle of range: One strong source, one ambiguous.
- Bottom of range: Single weak source.
- Capability area stack rank also differentiates: higher-ranked areas should score toward the top of the applicable range; lower-ranked areas toward the bottom.

The decision standard: would the hiring manager agree this person has the technical depth and capability to succeed in this role? Not "already doing it at a frontier lab" — that's too high. Not "vaguely ML-adjacent" — that's too low. "Has done hands-on ML work with enough depth to grow into this role, even if their current domain is different."

The guard against permissiveness is the DEPTH TEST, not the capability mapping. A person must demonstrate hands-on ML builder depth to be saved — no exceptions. What the capability mapping determines is confidence level, not the binary decision. Strong domain match + depth = high confidence save. No domain match + depth + transferable methodology = moderate confidence save. No depth = reject regardless of domain."""
        return base

    def post_evaluation_safety_net(self) -> str:
        """Post-evaluation safety net for L7+ roles. Empty string for IC roles."""
        if not self.is_senior_role():
            return ""
        return f"""
POST-EVALUATION SAFETY NET ({self.role_level} roles only):
If the standard procedure produced REJECT for an L7+ candidate, pause and check:

1. Does this candidate hold or has held a title of Head of AI, VP of AI, Director of AI/Engineering, or equivalent at a Fortune 500, major financial institution, or well-known technology company?
2. Does the career trajectory show progression from technical IC work into executive AI leadership?
3. Is there evidence of organizational building (teams, budgets, R&D programs) combined with technical domain language (AI, ML, GenAI, agentic, optimization)?

If YES to all three: Override to INFERENTIAL_SAVE with confidence 0.45-0.50. The standard procedure's evidence model is calibrated for IC-level profiles and may produce false negatives on executive profiles where evidence is positional and trajectory-based rather than tool-name-based. Flag for recruiter review."""

    def calibration_block(self) -> str:
        """Formats calibration examples for injection into evaluation prompts."""
        if not self.calibration_examples:
            return ""
        lines = ["\nCALIBRATION EXAMPLES (use these to anchor your judgment):"]
        strong = self.calibration_examples.get("strong_saves", [])
        if strong:
            lines.append("\nStrong Saves (correct — these should be SAVED):")
            for ex in strong:
                lines.append(f"  - {ex['name']}: {ex['why']}")
        incorrect = self.calibration_examples.get("incorrect_saves", [])
        if incorrect:
            lines.append("\nIncorrect Saves (should have been REJECTED):")
            for ex in incorrect:
                lines.append(f"  - {ex['name']}: {ex['why']}")
        borderline = self.calibration_examples.get("borderline_verify", [])
        if borderline:
            lines.append("\nBorderline (verify carefully):")
            for ex in borderline:
                lines.append(f"  - {ex['name']}: {ex['why']}")
        return "\n".join(lines)

    def instructions_block(self) -> str:
        """Formats role-specific instructions for injection into evaluation prompts."""
        if not self.instructions:
            return ""
        lines = ["\nROLE-SPECIFIC INSTRUCTIONS:"]
        for i, inst in enumerate(self.instructions, 1):
            lines.append(f"{i}. {inst}")
        return "\n".join(lines)

    def post_save_modifiers_block(self) -> str:
        """Formats post-save modifiers for injection into evaluation prompts."""
        if not self.post_save_modifiers:
            return ""
        lines = ["\nPOST-SAVE MODIFIERS (apply ONLY after a SAVE/INFERENTIAL_SAVE/TRANSFERABLE_SAVE/SIGNAL_SAVE decision):"]
        lines.append("These modifiers CANNOT change a REJECT to a SAVE. They only adjust confidence on already-saved candidates.\n")
        for mod in self.post_save_modifiers:
            lines.append(f"MODIFIER: {mod.name}")
            lines.append(f"  Trigger: {mod.trigger}")
            lines.append(f"  If present: {mod.if_present}")
            lines.append(f"  If absent: {mod.if_absent}")
            if mod.signals:
                lines.append(f"  Signals to look for:")
                for sig in mod.signals:
                    lines.append(f"    - {sig}")
            lines.append("")
        lines.append("After evaluating all modifiers, report which (if any) fired in the POST_SAVE_MODIFIER response field.")
        return "\n".join(lines)

    def additional_search_terms_block(self) -> str:
        """Formats additional search terms for injection into strategy prompts."""
        if not self.additional_search_terms:
            return ""
        return ", ".join(self.additional_search_terms)

    def capability_area_stack_rank_guidance(self) -> str:
        """Dynamic stack-rank guidance based on actual number of capability areas."""
        n = len(self.capability_areas)
        if n <= 2:
            return (f"Areas are stack-ranked. Within the same match level (DIRECT or ADJACENT), "
                    f"score toward the TOP of the confidence range for area #1 and toward the BOTTOM for area #{n}. "
                    f"Example: ADJACENT to area #1 → 0.65-0.75; ADJACENT to area #{n} → 0.60-0.65. "
                    f"Never score below the range floor regardless of area rank.")
        top = n - 1
        return (f"Areas are stack-ranked. Within the same match level (DIRECT or ADJACENT), "
                f"score toward the TOP of the confidence range for areas ranked 1-{top} and toward the BOTTOM for area #{n}. "
                f"Example: ADJACENT to area #1 → 0.65-0.75; ADJACENT to area #{n} → 0.60-0.65. "
                f"Never score below the range floor regardless of area rank.")

