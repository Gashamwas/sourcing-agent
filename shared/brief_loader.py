"""Brief loader — normalizes any brief JSON into a standard Brief dataclass.

Handles three brief formats:
1. Brazil FDL (old) — archetypes as dicts with save_signals/skip_signals
2. Head of AI Lab (old) — sweet_spot.archetypes as strings
3. V2 schema (new) — capability_areas, depth_distinction, non_fit_patterns, employer_signal_rules

For V2 briefs, loads into both the old Brief (for strategy.py/adaptation compat)
and the new brief_schema.Brief (for judgment_templates.py). The new brief is
stored as Brief._new_brief.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

KIT_BASE_URL = "https://search-kit-library.vercel.app/kit"


def _is_v2_brief(raw: dict) -> bool:
    """Detect if a brief JSON uses the V2 schema (has capability_areas or core_areas)."""
    has_capability = "capability_areas" in raw or "core_areas" in raw
    return has_capability and "depth_distinction" in raw


@dataclass
class Brief:
    id: str
    role_title: str
    role_description: str
    kit_url: str
    linkedin_project: str
    linkedin_project_id: str
    minimum_bar: str
    archetypes: list[dict]
    noise_archetypes: list[dict]
    hard_skips: list[str]
    clear_skips_from_review: list[str]
    known_noise_patterns: list[dict]
    permanent_filters: dict
    save_instructions: dict
    experience_floor: dict
    search_priorities: list[str] = field(default_factory=list)
    noise_predictions: list[dict] = field(default_factory=list)
    # V2 brief fields surfaced for strategy formation
    market_density: str = ""  # "sparse" | "moderate" | "dense" — from V2 brief
    key_terms_by_area: dict = field(default_factory=dict)  # {area_name: [terms]}
    # Lightweight brief fields — JD-driven mode
    jd_text: str = ""
    intake_notes: str = ""
    instructions: list[str] = field(default_factory=list)
    employer_blacklist: list[str] = field(default_factory=list)
    additional_search_terms: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    # V2 brief schema object (set when loading a V2 brief)
    _new_brief: Any = field(default=None, repr=False)

    def needs_preflight(self) -> bool:
        """Check if this brief needs Sourcing Preflight to fill eval criteria."""
        # V2 briefs never need preflight — they carry their own eval criteria
        if self._new_brief is not None:
            return False
        has_jd = bool(self.jd_text)
        has_archetypes = bool(self.archetypes)
        has_minimum_bar = bool(self.minimum_bar)
        return has_jd and (not has_archetypes or not has_minimum_bar)

    @property
    def has_v2_schema(self) -> bool:
        """Whether this brief was loaded from a V2 schema with structured evaluation."""
        return self._new_brief is not None


def load_brief(path: str | Path) -> Brief:
    """Load a brief JSON file and return a normalized Brief dataclass."""
    with open(path) as f:
        raw = json.load(f)
    if _is_v2_brief(raw):
        return _load_v2_brief(raw)
    return normalize_brief(raw)


def _load_v2_brief(raw: dict) -> Brief:
    """Load a V2 brief: create the new brief_schema.Brief AND map to old Brief for compat."""
    from shared.brief_schema import Brief as NewBrief, CapabilityArea, DepthDistinction, \
        NonFitPattern, EmployerSignalRule, FacialCalibration, BiasControls, MarketDensity, \
        PostSaveModifier

    # --- Build the new brief_schema.Brief ---
    # Normalize v3.1 field names: merge core_areas + differentiator_areas → capability_areas
    if "core_areas" in raw and "capability_areas" not in raw:
        raw["capability_areas"] = raw.get("core_areas", []) + raw.get("differentiator_areas", [])

    capability_areas = [
        CapabilityArea(
            name=ca["name"], description=ca["description"],
            builder_signals=ca.get("builder_signals", ca.get("positive_signals", [])),
            user_signals=ca.get("user_signals", ca.get("false_positive_signals", [])),
            key_terms=ca.get("key_terms", []),
            github_code_signals=ca.get("github_code_signals", []),
        ) for ca in raw["capability_areas"]
    ]
    depth = DepthDistinction(
        builder_definition=raw["depth_distinction"]["builder_definition"],
        user_definition=raw["depth_distinction"]["user_definition"],
        edge_case_guidance=raw["depth_distinction"]["edge_case_guidance"],
    )
    non_fit_patterns = [
        NonFitPattern(
            label=nf["label"], description=nf["description"],
            why_not=nf["why_not"], examples=nf.get("examples", []),
        ) for nf in raw.get("non_fit_patterns", [])
    ]
    employer_rules = [
        EmployerSignalRule(
            tier=er["tier"], employer_patterns=er["employer_patterns"],
            evidence_required=er["evidence_required"],
            save_on_employer_alone=er.get("save_on_employer_alone", False),
        ) for er in raw.get("employer_signal_rules", [])
    ]
    fc_data = raw.get("facial_calibration", {})
    facial = FacialCalibration(
        expected_yes_rate_low=fc_data.get("expected_yes_rate_low", 0.25),
        expected_yes_rate_high=fc_data.get("expected_yes_rate_high", 0.55),
        fast_exit_patterns=fc_data.get("fast_exit_patterns", []),
        trajectory_yes_patterns=fc_data.get("trajectory_yes_patterns", []),
        trajectory_ambiguous_patterns=fc_data.get("trajectory_ambiguous_patterns", []),
        trajectory_no_patterns=fc_data.get("trajectory_no_patterns", []),
        github_fast_exit_patterns=fc_data.get("github_fast_exit_patterns", []),
        github_portfolio_yes_patterns=fc_data.get("github_portfolio_yes_patterns", []),
        github_portfolio_ambiguous_patterns=fc_data.get("github_portfolio_ambiguous_patterns", []),
        github_portfolio_no_patterns=fc_data.get("github_portfolio_no_patterns", []),
    )
    bc_data = raw.get("bias_controls", {})
    bias = BiasControls(
        max_consecutive_saves=bc_data.get("max_consecutive_saves", 5),
        max_consecutive_rejects=bc_data.get("max_consecutive_rejects", 20),
        parse_failure_alarm_rate=bc_data.get("parse_failure_alarm_rate", 0.03),
    )
    post_save_modifiers = [
        PostSaveModifier(
            name=psm["name"],
            trigger=psm.get("trigger", ""),
            if_present=psm.get("if_present", ""),
            if_absent=psm.get("if_absent", ""),
            signals=psm.get("signals", []),
        ) for psm in raw.get("post_save_modifiers", [])
    ]
    additional_search_terms = raw.get("additional_search_terms", [])

    new_brief = NewBrief(
        role_title=raw["role_title"],
        role_level=raw.get("role_level", ""),
        role_summary=raw.get("role_summary", ""),
        geography=raw.get("geography", ""),
        linkedin_project=raw.get("linkedin_project", ""),
        capability_areas=capability_areas,
        depth_distinction=depth,
        non_fit_patterns=non_fit_patterns,
        employer_signal_rules=employer_rules,
        minimum_years_experience=raw.get("minimum_years_experience", 4),
        minimum_bar_description=raw.get("minimum_bar_description", ""),
        facial_calibration=facial,
        market_density=MarketDensity(raw.get("market_density", "moderate")),
        employer_blacklist=raw.get("employer_blacklist", []),
        kit_url=raw.get("kit_url"),
        jd_path=raw.get("jd_path"),
        bias_controls=bias,
        inferential_save_rules=raw.get("inferential_save_rules"),
        non_fit_override_rule=raw.get("non_fit_override_rule", ""),
        calibration_examples=raw.get("calibration_examples"),
        instructions=raw.get("instructions", []),
        post_save_modifiers=post_save_modifiers,
        additional_search_terms=additional_search_terms,
        version=raw.get("version", "2.0"),
        author=raw.get("author", ""),
        notes=raw.get("notes", ""),
    )

    # --- Map V2 fields to old Brief for strategy.py / adaptation compat ---
    # capability_areas → archetypes
    archetypes = []
    for ca in raw["capability_areas"]:
        archetypes.append({
            "name": ca["name"],
            "capability_area": ca["name"],
            "pattern": ca["description"],
            "save_signals": ca.get("builder_signals", ca.get("positive_signals", [])),
            "skip_signals": ca.get("user_signals", ca.get("false_positive_signals", [])),
        })

    # non_fit_patterns → noise_archetypes
    noise_archetypes = []
    for nf in raw.get("non_fit_patterns", []):
        noise_archetypes.append({
            "name": nf["label"],
            "description": nf["description"],
            "signals": nf.get("examples", []),
        })

    # hard_skips from fast_exit_patterns
    hard_skips = fc_data.get("fast_exit_patterns", [])

    # minimum_bar from minimum_bar_description
    min_bar = raw.get("minimum_bar_description", "")
    min_years = raw.get("minimum_years_experience", 4)
    if min_bar and min_years:
        min_bar = f"{min_years}+ years. {min_bar}"

    # permanent_filters from geography
    permanent_filters = {}
    if raw.get("geography"):
        permanent_filters["Location"] = raw["geography"]

    # experience_floor
    experience_floor = {
        "required": f"{min_years}+ years hands-on",
        "disqualifying": "",
    }

    # Load JD text from jd_path if provided
    jd_text = raw.get("jd", "") or raw.get("jd_text", "")
    if not jd_text and raw.get("jd_path"):
        jd_file = Path(raw["jd_path"])
        if jd_file.exists():
            jd_text = jd_file.read_text()

    old_brief = Brief(
        id=raw.get("role_title", "v2-brief"),
        role_title=raw["role_title"],
        role_description=raw.get("role_summary", ""),
        kit_url=raw.get("kit_url", ""),
        linkedin_project=raw.get("linkedin_project", ""),
        linkedin_project_id=raw.get("linkedin_project_id", ""),
        minimum_bar=min_bar,
        archetypes=archetypes,
        noise_archetypes=noise_archetypes,
        hard_skips=hard_skips,
        clear_skips_from_review=[],
        known_noise_patterns=[],
        permanent_filters=permanent_filters,
        save_instructions={"destination": raw.get("linkedin_project", "")},
        experience_floor=experience_floor,
        employer_blacklist=raw.get("employer_blacklist", []),
        additional_search_terms=additional_search_terms,
        jd_text=jd_text,
        intake_notes=raw.get("intake_notes", ""),
        instructions=raw.get("instructions", []),
        search_priorities=raw.get("search_priorities", []),
        market_density=new_brief.market_density.value if new_brief.market_density else "",
        key_terms_by_area={
            ca.name: ca.key_terms
            for ca in new_brief.capability_areas
            if ca.key_terms
        },
        raw=raw,
        _new_brief=new_brief,
    )
    return old_brief


def normalize_brief(raw: dict) -> Brief:
    """Normalize an old-format brief dict into a Brief dataclass."""

    # --- ID ---
    brief_id = raw.get("name") or raw.get("brief_id") or "unknown"

    # --- Role title ---
    role_title = raw.get("role_title") or raw.get("project_name") or raw.get("name") or ""

    # --- Role description ---
    role_description = raw.get("description") or raw.get("role_summary") or ""

    # --- Kit URL ---
    kit_url = raw.get("kit_url") or ""
    if not kit_url:
        kit_id = raw.get("search_kit_id") or ""
        if kit_id:
            kit_url = f"{KIT_BASE_URL}/{kit_id}"

    # --- LinkedIn project ---
    linkedin_project = raw.get("linkedin_project") or raw.get("project_name") or ""
    linkedin_project_id = raw.get("linkedin_project_id") or ""

    # --- Minimum bar ---
    minimum_bar = raw.get("minimum_bar", "")
    if isinstance(minimum_bar, dict):
        minimum_bar = _minimum_bar_to_text(minimum_bar)

    # --- Archetypes ---
    archetypes = _normalize_archetypes(raw)

    # --- Noise archetypes ---
    noise_archetypes = raw.get("noise_archetypes", [])

    # --- Hard skips ---
    hard_skips = [str(s) for s in raw.get("hard_skips", [])]

    # --- Clear skips from review ---
    clear_skips_from_review = _normalize_clear_skips(raw.get("clear_skips_from_review", []))

    # --- Known noise patterns ---
    known_noise_patterns = raw.get("known_noise_patterns", [])

    # --- Permanent filters ---
    permanent_filters = raw.get("permanent_filters", {})

    # --- Save instructions ---
    save_instructions = raw.get("save_instructions", {})
    if not save_instructions:
        si = {}
        if raw.get("linkedin_project"):
            si["destination"] = raw["linkedin_project"]
        if raw.get("linkedin_project_id"):
            si["project_id"] = raw["linkedin_project_id"]
        save_instructions = si

    # --- Experience floor ---
    experience_floor = raw.get("evaluation", {}).get("experience_floor", {})
    if not experience_floor and isinstance(raw.get("minimum_bar"), dict):
        experience_floor = {
            "required": f"{raw['minimum_bar'].get('years_experience', '')} years",
            "disqualifying": raw["minimum_bar"].get("experience_note", ""),
        }

    # --- Strategy hints ---
    search_priorities = raw.get("search_priorities", [])
    noise_predictions = raw.get("noise_predictions", [])

    # --- Lightweight brief fields (JD-driven mode) ---
    jd_text = raw.get("jd", "") or raw.get("jd_text", "")
    if jd_text and not jd_text.strip().startswith(("#", "*", "T", "W", "A")):
        jd_path_candidate = Path(jd_text)
        if jd_path_candidate.exists() and jd_path_candidate.suffix in (".md", ".txt"):
            jd_text = jd_path_candidate.read_text()
    # If no inline JD text, try loading from jd_path
    if not jd_text and raw.get("jd_path"):
        jd_file = Path(raw["jd_path"])
        if jd_file.exists():
            jd_text = jd_file.read_text()

    intake_notes = raw.get("intake_notes", "")
    instructions = raw.get("instructions", [])
    employer_blacklist = raw.get("employer_blacklist", [])

    return Brief(
        id=brief_id,
        role_title=role_title,
        role_description=role_description,
        kit_url=kit_url,
        linkedin_project=linkedin_project,
        linkedin_project_id=linkedin_project_id,
        minimum_bar=minimum_bar,
        archetypes=archetypes,
        noise_archetypes=noise_archetypes,
        hard_skips=hard_skips,
        clear_skips_from_review=clear_skips_from_review,
        known_noise_patterns=known_noise_patterns,
        permanent_filters=permanent_filters,
        save_instructions=save_instructions,
        experience_floor=experience_floor,
        search_priorities=search_priorities,
        noise_predictions=noise_predictions,
        jd_text=jd_text,
        intake_notes=intake_notes,
        instructions=instructions,
        employer_blacklist=employer_blacklist,
        raw=raw,
    )


def _minimum_bar_to_text(mb: dict) -> str:
    """Convert a minimum_bar dict into a readable text summary for Opus."""
    parts = []
    if mb.get("years_experience"):
        parts.append(f"{mb['years_experience']}+ years experience.")
    if mb.get("experience_note"):
        parts.append(mb["experience_note"])
    if mb.get("title_floor"):
        parts.append(f"Title floor: {mb['title_floor']}.")
    if mb.get("title_ceiling_note"):
        parts.append(mb["title_ceiling_note"])
    if mb.get("technical_depth"):
        parts.append(mb["technical_depth"])
    if mb.get("bfsi_domain"):
        parts.append(mb["bfsi_domain"])
    if mb.get("genai_fluency"):
        parts.append(mb["genai_fluency"])
    if mb.get("location"):
        parts.append(mb["location"])
    # Catch any keys not explicitly handled
    handled = {"years_experience", "experience_note", "title_floor", "title_ceiling_note",
               "technical_depth", "bfsi_domain", "genai_fluency", "location"}
    for k, v in mb.items():
        if k not in handled and isinstance(v, str) and v.strip():
            parts.append(v)
    return " ".join(parts)


def _normalize_archetypes(raw: dict) -> list[dict]:
    """Normalize archetypes to [{name, pattern, save_signals, skip_signals}]."""
    archetypes = raw.get("archetypes", [])
    if archetypes and isinstance(archetypes[0], dict) and "name" in archetypes[0]:
        # Already in standard format (Brazil brief)
        return archetypes

    # Head of AI Lab format: sweet_spot.archetypes is a list of strings
    sweet_spot = raw.get("sweet_spot", {})
    if isinstance(sweet_spot, dict):
        ss_archetypes = sweet_spot.get("archetypes", [])
        if ss_archetypes:
            return [
                {
                    "name": f"Sweet Spot Archetype {i + 1}",
                    "pattern": desc,
                    "save_signals": [],
                    "skip_signals": [],
                }
                for i, desc in enumerate(ss_archetypes)
                if isinstance(desc, str)
            ]

    return archetypes


def _normalize_clear_skips(raw_skips: list) -> list[str]:
    """Flatten clear_skips_from_review to a list of strings."""
    result = []
    for entry in raw_skips:
        if isinstance(entry, str):
            result.append(entry)
        elif isinstance(entry, dict):
            pattern = entry.get("pattern", "")
            reason = entry.get("reason", "")
            if pattern and reason:
                result.append(f"{pattern}: {reason}")
            elif pattern:
                result.append(pattern)
            elif reason:
                result.append(reason)
    return result
