"""Brief loader — normalizes any brief JSON into a standard Brief dataclass.

Handles the two known brief formats (Brazil FDL, Head of AI Lab) and any future
brief that follows either pattern. The loader maps idiosyncratic field names to
a common schema so all downstream modules use a single interface.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

KIT_BASE_URL = "https://search-kit-library.vercel.app/kit"


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
    raw: dict = field(default_factory=dict)


def load_brief(path: str | Path) -> Brief:
    """Load a brief JSON file and return a normalized Brief dataclass."""
    with open(path) as f:
        raw = json.load(f)
    return normalize_brief(raw)


def normalize_brief(raw: dict) -> Brief:
    """Normalize a raw brief dict into a Brief dataclass."""

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
        # Construct from individual fields
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
