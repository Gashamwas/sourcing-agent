"""Bounded draft-brief generation from structured run debriefs."""

from __future__ import annotations

import copy
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from shared import config
from shared.brief_loader import load_brief
from shared.llm_clients import opus_llm
from shared.run_report_schema import StructuredRunReport
from shared.search_memory import build_search_memory_summary, extract_dominant_anchors
from shared.storage import read_json, read_jsonl, write_json


SAVE_DECISIONS = {"SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE", "SIGNAL_SAVE"}
MUTABLE_FIELDS = {
    "instructions",
    "search_priorities",
    "additional_search_terms",
    "intake_notes",
    "depth_distinction",
    "non_fit_patterns",
    "minimum_bar_description",
    "facial_calibration",
    "employer_signal_rules",
    "calibration_examples",
    "notes",
    "version",
}
LOCKED_FIELDS = {
    "role_title",
    "role_level",
    "role_summary",
    "geography",
    "linkedin_project",
    "linkedin_project_id",
    "capability_areas",
    "minimum_years_experience",
    "market_density",
    "kit_url",
}
LIST_LIMITS = {
    "instructions": 16,
    "search_priorities": 12,
    "additional_search_terms": 120,
    "non_fit_patterns": 10,
    "employer_signal_rules": 10,
}
CALIBRATION_MAX_DELTA = 0.10


@dataclass
class BriefIterationResult:
    draft_brief_path: Path
    rationale_path: Path
    draft_brief: dict
    rationale_markdown: str
    warnings: list[str]
    proposal: dict


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _dedupe_strings(values: list[Any], limit: int | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = _normalize_text(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if limit and len(out) >= limit:
            break
    return out


def _normalize_non_fit_patterns(values: Any, current: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for item in values or []:
        if not isinstance(item, dict):
            continue
        label = _normalize_text(item.get("label"))
        description = _normalize_text(item.get("description"))
        why_not = _normalize_text(item.get("why_not"))
        if not (label and description and why_not):
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "label": label,
                "description": description,
                "why_not": why_not,
                "examples": _dedupe_strings(item.get("examples", []), limit=5),
            }
        )
        if len(out) >= LIST_LIMITS["non_fit_patterns"]:
            break
    return out or copy.deepcopy(current)


def _normalize_employer_signal_rules(values: Any, current: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for item in values or []:
        if not isinstance(item, dict):
            continue
        tier = _normalize_text(item.get("tier"))
        evidence_required = _normalize_text(item.get("evidence_required"))
        if not (tier and evidence_required):
            continue
        key = tier.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "tier": tier,
                "employer_patterns": _dedupe_strings(item.get("employer_patterns", []), limit=20),
                "evidence_required": evidence_required,
                "save_on_employer_alone": False,
            }
        )
        if len(out) >= LIST_LIMITS["employer_signal_rules"]:
            break
    return out or copy.deepcopy(current)


def _normalize_calibration_examples(values: Any, current: dict) -> dict:
    if not isinstance(values, dict):
        return copy.deepcopy(current)

    def _bucket(name: str) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        for item in values.get(name, []) or []:
            if not isinstance(item, dict):
                continue
            candidate = _normalize_text(item.get("name"))
            why = _normalize_text(item.get("why"))
            if not (candidate and why):
                continue
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": candidate, "why": why})
            if len(out) >= 6:
                break
        return out

    normalized = {
        "strong_saves": _bucket("strong_saves"),
        "incorrect_saves": _bucket("incorrect_saves"),
        "borderline_verify": _bucket("borderline_verify"),
    }
    for key, value in normalized.items():
        if not value and isinstance(current, dict):
            normalized[key] = copy.deepcopy(current.get(key, []))
    return normalized


def _normalize_depth_distinction(values: Any, current: dict) -> dict:
    if not isinstance(values, dict):
        return copy.deepcopy(current)
    normalized = {
        "builder_definition": _normalize_text(values.get("builder_definition")) or _normalize_text(current.get("builder_definition")),
        "user_definition": _normalize_text(values.get("user_definition")) or _normalize_text(current.get("user_definition")),
        "edge_case_guidance": _normalize_text(values.get("edge_case_guidance")) or _normalize_text(current.get("edge_case_guidance")),
    }
    return normalized


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_facial_calibration(values: Any, current: dict) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    if not isinstance(values, dict):
        return copy.deepcopy(current), warnings

    current_low = float(current.get("expected_yes_rate_low", 0.0))
    current_high = float(current.get("expected_yes_rate_high", 1.0))
    proposed_low = float(values.get("expected_yes_rate_low", current_low))
    proposed_high = float(values.get("expected_yes_rate_high", current_high))
    clamped_low = _clamp(proposed_low, max(0.0, current_low - CALIBRATION_MAX_DELTA), min(1.0, current_low + CALIBRATION_MAX_DELTA))
    clamped_high = _clamp(proposed_high, max(0.0, current_high - CALIBRATION_MAX_DELTA), min(1.0, current_high + CALIBRATION_MAX_DELTA))
    if clamped_high < clamped_low:
        clamped_high = clamped_low
    if clamped_low != proposed_low or clamped_high != proposed_high:
        warnings.append(
            "Facial calibration deltas were clamped to prevent a single run from radically retuning pass-through expectations."
        )

    normalized = {
        "expected_yes_rate_low": round(clamped_low, 4),
        "expected_yes_rate_high": round(clamped_high, 4),
        "fast_exit_patterns": _dedupe_strings(values.get("fast_exit_patterns", current.get("fast_exit_patterns", [])), limit=12),
        "trajectory_yes_patterns": _dedupe_strings(values.get("trajectory_yes_patterns", current.get("trajectory_yes_patterns", [])), limit=12),
        "trajectory_ambiguous_patterns": _dedupe_strings(values.get("trajectory_ambiguous_patterns", current.get("trajectory_ambiguous_patterns", [])), limit=12),
        "trajectory_no_patterns": _dedupe_strings(values.get("trajectory_no_patterns", current.get("trajectory_no_patterns", [])), limit=12),
    }
    return normalized, warnings


def _derive_next_draft_version(current_version: str) -> str:
    version = _normalize_text(current_version)
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:-draft)?$", version)
    if not match:
        return "draft"
    major = int(match.group(1))
    minor = int(match.group(2) or 0) + 1
    return f"{major}.{minor}-draft"


def _draft_brief_path(brief_path: Path, draft_version: str) -> Path:
    stem = brief_path.stem
    if draft_version == "draft":
        return brief_path.with_name(f"{stem}-draft{brief_path.suffix}")
    version_token = f"v{draft_version}"
    if re.search(r"-v\d+(?:\.\d+)?(?:-draft)?$", stem):
        new_stem = re.sub(r"-v\d+(?:\.\d+)?(?:-draft)?$", f"-{version_token}", stem)
    else:
        new_stem = f"{stem}-{version_token}"
    return brief_path.with_name(f"{new_stem}{brief_path.suffix}")


def _backup_existing(path: Path) -> Path | None:
    if not path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.stem}.bak-{timestamp}{path.suffix}")
    path.rename(backup)
    return backup


def _summarize_final_judgments(path: Path | None, limit: int = 12) -> dict:
    if not path or not path.exists():
        return {}
    records = [row for row in read_jsonl(path) if isinstance(row, dict)]
    saves: list[dict] = []
    rejects: list[dict] = []
    for row in records:
        entry = {
            "candidate_name": row.get("candidate_name", ""),
            "decision": row.get("decision", ""),
            "path": row.get("path", ""),
            "confidence": row.get("confidence"),
            "rationale": _normalize_text(row.get("rationale", ""))[:280],
        }
        if row.get("decision") in SAVE_DECISIONS and len(saves) < limit:
            saves.append(entry)
        elif row.get("decision") == "REJECT" and len(rejects) < limit:
            rejects.append(entry)
    return {
        "total_records": len(records),
        "save_examples": saves,
        "reject_examples": rejects,
    }


def _resolve_optional_paths(
    brief_path: Path,
    report_path: str | None,
    search_memory_path: str | None,
    final_judgments_path: str | None,
    output_dir: str | None,
) -> tuple[Path, Path, Path | None, Path | None]:
    output_root = Path(output_dir) if output_dir else config.OUTPUT_DIR
    brief = load_brief(str(brief_path))
    project_id = brief.linkedin_project_id or brief_path.stem
    resolved_report = Path(report_path) if report_path else output_root / "run-report.json"
    resolved_search_memory = (
        Path(search_memory_path)
        if search_memory_path
        else output_root / f"search_memory-{project_id}.json"
    )
    resolved_final = (
        Path(final_judgments_path)
        if final_judgments_path
        else output_root / "final_judgments.jsonl"
    )
    return output_root, resolved_report, resolved_search_memory, resolved_final


def _build_iteration_system() -> str:
    return """You are revising a sourcing brief after a completed run.

Return valid JSON only with this exact shape:
{
  "summary": "short summary string",
  "proposed_changes": {
    "instructions": ["..."],
    "search_priorities": ["..."],
    "additional_search_terms": ["..."],
    "intake_notes": "string",
    "depth_distinction": {
      "builder_definition": "string",
      "user_definition": "string",
      "edge_case_guidance": "string"
    },
    "non_fit_patterns": [
      {"label": "string", "description": "string", "why_not": "string", "examples": ["..."]}
    ],
    "minimum_bar_description": "string",
    "facial_calibration": {
      "expected_yes_rate_low": 0.0,
      "expected_yes_rate_high": 0.0,
      "fast_exit_patterns": ["..."],
      "trajectory_yes_patterns": ["..."],
      "trajectory_ambiguous_patterns": ["..."],
      "trajectory_no_patterns": ["..."]
    },
    "employer_signal_rules": [
      {"tier": "string", "employer_patterns": ["..."], "evidence_required": "string", "save_on_employer_alone": false}
    ],
    "calibration_examples": {
      "strong_saves": [{"name": "string", "why": "string"}],
      "incorrect_saves": [{"name": "string", "why": "string"}],
      "borderline_verify": [{"name": "string", "why": "string"}]
    },
    "notes": "string",
    "version": "string"
  },
  "changed_fields": [
    {
      "field": "field_name",
      "why": "why the change matters",
      "evidence": ["quoted or paraphrased evidence from the run report"],
      "expected_effects": ["downstream operational effects"]
    }
  ],
  "warnings": ["optional warning strings"]
}

Rules:
- Propose changes ONLY for mutable fields explicitly shown above.
- Do NOT propose changes to role identity, geography, LinkedIn project mapping, minimum years, capability areas, or market density.
- Keep hard gates intact: geography, years, BFSI domain, post-2022 GenAI builder evidence, executive-builder scope.
- Prefer replacing low-signal items over append-only growth.
- Keep lists concise and high-signal.
- If you suggest employer signal rules, save_on_employer_alone must stay false.
- If you suggest facial calibration changes, make them small and evidence-based.
- If there is not enough evidence to change a field, omit it from proposed_changes."""


def _build_iteration_user_prompt(
    current_raw: dict,
    report: StructuredRunReport,
    search_memory: dict | None,
    final_judgments_summary: dict | None,
) -> str:
    mutable_snapshot = {field: current_raw.get(field) for field in MUTABLE_FIELDS if field in current_raw}
    locked_snapshot = {field: current_raw.get(field) for field in LOCKED_FIELDS if field in current_raw}
    context = {
        "current_mutable_fields": mutable_snapshot,
        "locked_fields": locked_snapshot,
        "run_report": report.to_dict(),
        "search_memory_summary": build_search_memory_summary(search_memory) if search_memory else None,
        "final_judgments_summary": final_judgments_summary or None,
    }
    return (
        "Revise the brief using the run report and optional supporting artifacts.\n"
        "Only propose bounded edits to mutable fields.\n\n"
        f"{json.dumps(context, indent=2)}"
    )


def _ensure_hard_gate_instruction(instructions: list[str], current_raw: dict) -> list[str]:
    existing = _dedupe_strings(instructions, limit=LIST_LIMITS["instructions"])
    if any("hard gates" in item.lower() for item in existing):
        return existing
    geography = current_raw.get("geography", "the target geography")
    years = current_raw.get("minimum_years_experience", 0)
    fallback = (
        f"The evaluation bar does NOT move. Keep the hard gates: {geography}, "
        f"{years}+ years, BFSI domain depth, post-2022 applied GenAI build evidence, and executive-builder scope."
    )
    existing.append(fallback)
    return _dedupe_strings(existing, limit=LIST_LIMITS["instructions"])


def _ensure_minimum_bar_guardrail(description: str, current_raw: dict) -> str:
    text = _normalize_text(description)
    required_bits: list[str] = []
    geography = str(current_raw.get("geography", "")).strip()
    years = current_raw.get("minimum_years_experience")
    if geography and geography.lower() not in text.lower():
        required_bits.append(f"Current {geography} location remains non-negotiable.")
    if years and str(years) not in text and "fifteen" not in text.lower():
        required_bits.append(f"{years}+ years remains a hard floor.")
    if "genai" not in text.lower() and "llm" not in text.lower():
        required_bits.append("Post-2022 applied GenAI or LLM work remains a hard requirement.")
    if "bfsi" not in text.lower() and "financial" not in text.lower():
        required_bits.append("This remains a BFSI-first search.")
    if "builder" not in text.lower():
        required_bits.append("The role remains an executive-builder search, not strategy or product management.")
    if required_bits:
        text = f"{text} {' '.join(required_bits)}".strip()
    return text


def _collect_heuristic_hints() -> set[str]:
    from linkedin import strategy as strategy_mod
    from shared import search_memory as search_memory_mod

    hints = set()
    for source in (
        getattr(strategy_mod, "_EDGE_CASE_PATTERNS", ()),
        getattr(strategy_mod, "_EDGE_CASE_COMPANY_PATTERNS", ()),
        getattr(search_memory_mod, "_ANCHOR_PHRASES", ()),
        getattr(search_memory_mod, "_EDGE_CASE_TERMS", ()),
    ):
        hints.update(_normalize_text(item).lower() for item in source if _normalize_text(item))
    for values in getattr(search_memory_mod, "_DOMAIN_LANE_HINTS", {}).values():
        hints.update(_normalize_text(item).lower() for item in values if _normalize_text(item))
    return hints


def _find_heuristic_gap_warnings(current_raw: dict, draft_raw: dict) -> list[str]:
    heuristic_hints = _collect_heuristic_hints()
    warnings: list[str] = []

    current_terms = {_normalize_text(item).lower() for item in current_raw.get("additional_search_terms", [])}
    for term in draft_raw.get("additional_search_terms", []):
        normalized = _normalize_text(term).lower()
        if not normalized or normalized in current_terms:
            continue
        if not any(hint in normalized or normalized in hint for hint in heuristic_hints):
            warnings.append(
                f"New search term '{term}' is not recognized by current strategy/search-memory heuristics and may need follow-up heuristic support."
            )

    current_priorities = {_normalize_text(item).lower() for item in current_raw.get("search_priorities", [])}
    for priority in draft_raw.get("search_priorities", []):
        normalized = _normalize_text(priority).lower()
        if not normalized or normalized in current_priorities:
            continue
        anchors = [anchor.lower() for anchor in extract_dominant_anchors(priority, limit=6)]
        if anchors and not any(
            any(hint in anchor or anchor in hint for hint in heuristic_hints)
            for anchor in anchors
        ):
            warnings.append(
                f"New search priority '{priority}' introduces a lane that current strategy/search-memory heuristics may not recognize."
            )

    deduped: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        key = warning.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(warning)
    return deduped


def _json_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def _apply_iteration_proposal(current_raw: dict, proposal: dict, report_path: Path) -> tuple[dict, list[str]]:
    draft = copy.deepcopy(current_raw)
    warnings: list[str] = []
    changes = proposal.get("proposed_changes", {}) if isinstance(proposal, dict) else {}

    if "instructions" in changes:
        draft["instructions"] = _dedupe_strings(changes["instructions"], limit=LIST_LIMITS["instructions"])
    if "search_priorities" in changes:
        draft["search_priorities"] = _dedupe_strings(changes["search_priorities"], limit=LIST_LIMITS["search_priorities"])
    if "additional_search_terms" in changes:
        draft["additional_search_terms"] = _dedupe_strings(changes["additional_search_terms"], limit=LIST_LIMITS["additional_search_terms"])
    if "intake_notes" in changes:
        draft["intake_notes"] = _normalize_text(changes["intake_notes"])
    if "depth_distinction" in changes:
        draft["depth_distinction"] = _normalize_depth_distinction(
            changes["depth_distinction"], current_raw.get("depth_distinction", {})
        )
    if "non_fit_patterns" in changes:
        draft["non_fit_patterns"] = _normalize_non_fit_patterns(
            changes["non_fit_patterns"], current_raw.get("non_fit_patterns", [])
        )
    if "minimum_bar_description" in changes:
        draft["minimum_bar_description"] = _ensure_minimum_bar_guardrail(
            _normalize_text(changes["minimum_bar_description"]), current_raw
        )
    if "facial_calibration" in changes:
        draft["facial_calibration"], clamp_warnings = _normalize_facial_calibration(
            changes["facial_calibration"], current_raw.get("facial_calibration", {})
        )
        warnings.extend(clamp_warnings)
    if "employer_signal_rules" in changes:
        draft["employer_signal_rules"] = _normalize_employer_signal_rules(
            changes["employer_signal_rules"], current_raw.get("employer_signal_rules", [])
        )
    if "calibration_examples" in changes:
        draft["calibration_examples"] = _normalize_calibration_examples(
            changes["calibration_examples"], current_raw.get("calibration_examples", {})
        )
    if "notes" in changes:
        draft["notes"] = _normalize_text(changes["notes"])

    draft["instructions"] = _ensure_hard_gate_instruction(
        draft.get("instructions", current_raw.get("instructions", [])),
        current_raw,
    )
    draft["minimum_bar_description"] = _ensure_minimum_bar_guardrail(
        draft.get("minimum_bar_description", current_raw.get("minimum_bar_description", "")),
        current_raw,
    )

    draft["version"] = _derive_next_draft_version(str(current_raw.get("version", "")))
    generated_note = f"Draft iteration generated from {report_path.name}."
    if draft.get("notes"):
        if generated_note.lower() not in draft["notes"].lower():
            draft["notes"] = f"{draft['notes']} {generated_note}".strip()
    else:
        draft["notes"] = generated_note

    warnings.extend(_find_heuristic_gap_warnings(current_raw, draft))
    return draft, _dedupe_strings(warnings)


def _validate_draft_brief(draft_raw: dict) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump(draft_raw, tmp, indent=2)
        temp_path = Path(tmp.name)
    try:
        load_brief(str(temp_path))
    finally:
        temp_path.unlink(missing_ok=True)


def _render_iteration_rationale(
    source_brief: Path,
    draft_brief: Path,
    report_path: Path,
    current_raw: dict,
    draft_raw: dict,
    proposal: dict,
    warnings: list[str],
) -> str:
    detail_map = {
        item.get("field"): item
        for item in proposal.get("changed_fields", [])
        if isinstance(item, dict) and item.get("field")
    }
    actual_changed = [
        field for field in MUTABLE_FIELDS
        if field in draft_raw and field in current_raw and not _json_equal(current_raw[field], draft_raw[field])
    ]
    lines = [
        f"# Brief Iteration Report: {source_brief.name} → {draft_brief.name}",
        "",
        f"- Source report: {report_path}",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Draft version: {draft_raw.get('version', '')}",
        "",
    ]
    summary = _normalize_text(proposal.get("summary"))
    if summary:
        lines.extend(["## Summary", summary, ""])

    lines.append("## Changed Fields")
    if not actual_changed:
        lines.append("- No mutable fields changed.")
    for field in actual_changed:
        detail = detail_map.get(field, {})
        lines.append(f"- **{field}**")
        why = _normalize_text(detail.get("why"))
        if why:
            lines.append(f"  Why: {why}")
        evidence = _dedupe_strings(detail.get("evidence", []), limit=5)
        if evidence:
            lines.append(f"  Evidence: {'; '.join(evidence)}")
        effects = _dedupe_strings(detail.get("expected_effects", []), limit=5)
        if effects:
            lines.append(f"  Expected effects: {'; '.join(effects)}")
    lines.append("")

    lines.append("## Locked Fields Preserved")
    for field in sorted(LOCKED_FIELDS):
        lines.append(f"- {field}")
    lines.append("")

    lines.append("## Guardrails Applied")
    lines.append("- Locked fields were preserved from the source brief.")
    lines.append("- Search terms and priorities were deduplicated and capped.")
    lines.append("- Employer signal rules were forced to keep `save_on_employer_alone = false`.")
    lines.append("- Facial calibration deltas were clamped before writing the draft.")
    lines.append("- The resulting draft was validated by round-tripping through `load_brief`.")
    lines.append("")

    lines.append("## Warnings")
    combined_warnings = _dedupe_strings(list(proposal.get("warnings", [])) + warnings)
    if not combined_warnings:
        lines.append("- None")
    else:
        for warning in combined_warnings:
            lines.append(f"- {warning}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def iterate_brief_draft(
    brief_path: str | Path,
    report_path: str | None = None,
    search_memory_path: str | None = None,
    final_judgments_path: str | None = None,
    output_dir: str | None = None,
) -> BriefIterationResult:
    brief_path = Path(brief_path)
    if not brief_path.exists():
        raise FileNotFoundError(f"Brief file not found: {brief_path}")

    output_root, resolved_report, resolved_search_memory, resolved_final = _resolve_optional_paths(
        brief_path,
        report_path,
        search_memory_path,
        final_judgments_path,
        output_dir,
    )
    if not resolved_report.exists():
        raise FileNotFoundError(f"Structured run report not found: {resolved_report}")

    current_raw = read_json(brief_path)
    report = StructuredRunReport.from_dict(read_json(resolved_report))
    search_memory = read_json(resolved_search_memory) if resolved_search_memory and resolved_search_memory.exists() else None
    final_summary = _summarize_final_judgments(resolved_final) if resolved_final and resolved_final.exists() else None

    proposal = opus_llm(
        _build_iteration_system(),
        _build_iteration_user_prompt(current_raw, report, search_memory, final_summary),
        expect_json=True,
        max_tokens=12000,
    )
    if not isinstance(proposal, dict):
        raise ValueError("brief iteration proposal must be a dict")

    draft_raw, warnings = _apply_iteration_proposal(current_raw, proposal, resolved_report)
    _validate_draft_brief(draft_raw)

    draft_path = _draft_brief_path(brief_path, str(draft_raw.get("version", "draft")))
    rationale_path = output_root / f"brief-iteration-report-{draft_path.stem}.md"
    _backup_existing(draft_path)
    _backup_existing(rationale_path)
    write_json(draft_path, draft_raw)

    rationale_markdown = _render_iteration_rationale(
        brief_path,
        draft_path,
        resolved_report,
        current_raw,
        draft_raw,
        proposal,
        warnings,
    )
    rationale_path.parent.mkdir(parents=True, exist_ok=True)
    rationale_path.write_text(rationale_markdown)

    return BriefIterationResult(
        draft_brief_path=draft_path,
        rationale_path=rationale_path,
        draft_brief=draft_raw,
        rationale_markdown=rationale_markdown,
        warnings=warnings,
        proposal=proposal,
    )
