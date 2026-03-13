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

