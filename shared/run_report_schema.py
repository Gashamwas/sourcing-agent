"""Structured run-report schema and markdown rendering helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


def _require_dict(name: str, value: Any) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a dict")
    return value


def _require_list(name: str, value: Any) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _stringify_list(value: list[Any]) -> list[str]:
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            out.append(text)
    return out


@dataclass
class RunDebriefAnalysis:
    """Model-authored analytical sections for a run debrief."""

    winning_lanes: list[dict]
    underperforming_lanes: list[dict]
    coverage_gaps: list[dict]
    noise_patterns: list[dict]
    saved_candidate_patterns: dict
    adaptation_assessment: dict
    recommendations: dict
    brief_iteration_hints: dict

    @classmethod
    def from_dict(cls, data: dict) -> "RunDebriefAnalysis":
        if not isinstance(data, dict):
            raise ValueError("run debrief analysis must be a dict")
        required = (
            "winning_lanes",
            "underperforming_lanes",
            "coverage_gaps",
            "noise_patterns",
            "saved_candidate_patterns",
            "adaptation_assessment",
            "recommendations",
            "brief_iteration_hints",
        )
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"run debrief analysis missing keys: {', '.join(missing)}")

        return cls(
            winning_lanes=[item for item in _require_list("winning_lanes", data["winning_lanes"]) if isinstance(item, dict)],
            underperforming_lanes=[item for item in _require_list("underperforming_lanes", data["underperforming_lanes"]) if isinstance(item, dict)],
            coverage_gaps=[item for item in _require_list("coverage_gaps", data["coverage_gaps"]) if isinstance(item, dict)],
            noise_patterns=[item for item in _require_list("noise_patterns", data["noise_patterns"]) if isinstance(item, dict)],
            saved_candidate_patterns=_require_dict("saved_candidate_patterns", data["saved_candidate_patterns"]),
            adaptation_assessment=_require_dict("adaptation_assessment", data["adaptation_assessment"]),
            recommendations=_require_dict("recommendations", data["recommendations"]),
            brief_iteration_hints=_require_dict("brief_iteration_hints", data["brief_iteration_hints"]),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StructuredRunReport:
    """Validated machine-readable end-of-run report."""

    schema_version: int
    run_metadata: dict
    metrics_summary: dict
    string_performance: list[dict]
    winning_lanes: list[dict]
    underperforming_lanes: list[dict]
    coverage_gaps: list[dict]
    noise_patterns: list[dict]
    saved_candidate_patterns: dict
    adaptation_assessment: dict
    recommendations: dict
    brief_iteration_hints: dict

    @classmethod
    def from_parts(cls, snapshot: dict, analysis: RunDebriefAnalysis) -> "StructuredRunReport":
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot must be a dict")
        required = ("run_metadata", "metrics_summary", "string_performance")
        missing = [key for key in required if key not in snapshot]
        if missing:
            raise ValueError(f"run-report snapshot missing keys: {', '.join(missing)}")

        return cls(
            schema_version=int(snapshot.get("schema_version", 1)),
            run_metadata=_require_dict("run_metadata", snapshot["run_metadata"]),
            metrics_summary=_require_dict("metrics_summary", snapshot["metrics_summary"]),
            string_performance=[item for item in _require_list("string_performance", snapshot["string_performance"]) if isinstance(item, dict)],
            winning_lanes=analysis.winning_lanes,
            underperforming_lanes=analysis.underperforming_lanes,
            coverage_gaps=analysis.coverage_gaps,
            noise_patterns=analysis.noise_patterns,
            saved_candidate_patterns=analysis.saved_candidate_patterns,
            adaptation_assessment=analysis.adaptation_assessment,
            recommendations=analysis.recommendations,
            brief_iteration_hints=analysis.brief_iteration_hints,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "StructuredRunReport":
        if not isinstance(data, dict):
            raise ValueError("structured run report must be a dict")
        required = (
            "schema_version",
            "run_metadata",
            "metrics_summary",
            "string_performance",
            "winning_lanes",
            "underperforming_lanes",
            "coverage_gaps",
            "noise_patterns",
            "saved_candidate_patterns",
            "adaptation_assessment",
            "recommendations",
            "brief_iteration_hints",
        )
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"structured run report missing keys: {', '.join(missing)}")
        analysis = RunDebriefAnalysis.from_dict(
            {
                "winning_lanes": data["winning_lanes"],
                "underperforming_lanes": data["underperforming_lanes"],
                "coverage_gaps": data["coverage_gaps"],
                "noise_patterns": data["noise_patterns"],
                "saved_candidate_patterns": data["saved_candidate_patterns"],
                "adaptation_assessment": data["adaptation_assessment"],
                "recommendations": data["recommendations"],
                "brief_iteration_hints": data["brief_iteration_hints"],
            }
        )
        return cls.from_parts(
            {
                "schema_version": data["schema_version"],
                "run_metadata": data["run_metadata"],
                "metrics_summary": data["metrics_summary"],
                "string_performance": data["string_performance"],
            },
            analysis,
        )

    def to_dict(self) -> dict:
        return asdict(self)


def _render_named_section(title: str, items: list[dict], heading_key: str, detail_keys: list[str]) -> list[str]:
    lines = [f"## {title}"]
    if not items:
        lines.append("- None")
        lines.append("")
        return lines
    for item in items:
        heading = str(item.get(heading_key, "Unnamed")).strip() or "Unnamed"
        lines.append(f"- **{heading}**")
        for key in detail_keys:
            value = item.get(key)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, list):
                rendered = ", ".join(_stringify_list(value))
            else:
                rendered = str(value).strip()
            if rendered:
                label = key.replace("_", " ")
                lines.append(f"  {label}: {rendered}")
    lines.append("")
    return lines


def render_run_report_markdown(report: StructuredRunReport) -> str:
    """Render human-readable markdown from a validated structured report."""
    meta = report.run_metadata
    metrics = report.metrics_summary
    saved_patterns = report.saved_candidate_patterns or {}
    adaptation = report.adaptation_assessment or {}
    recs = report.recommendations or {}
    hints = report.brief_iteration_hints or {}

    title = meta.get("role_title") or meta.get("brief_name") or "Run Debrief"
    lines = [f"# End-of-Run Debrief Report: {title}", ""]

    lines.append("## Executive Summary")
    overall_summary = str(meta.get("overall_summary", "")).strip()
    if overall_summary:
        lines.append(overall_summary)
        lines.append("")
    lines.extend(
        [
            "| Metric | Value |",
            "|---|---|",
            f"| Strings executed | {metrics.get('strings_executed', 0)} |",
            f"| Strings skipped | {metrics.get('strings_skipped', 0)} |",
            f"| Total results | {metrics.get('total_results', 0)} |",
            f"| Pages reviewed | {metrics.get('total_pages_reviewed', 0)} |",
            f"| Candidates evaluated | {metrics.get('candidates_evaluated', 0)} |",
            f"| Facial YES | {metrics.get('facial_yes', 0)} |",
            f"| Facial NO | {metrics.get('facial_no', 0)} |",
            f"| Saved | {metrics.get('saved', 0)} |",
            f"| Rejected | {metrics.get('rejected', 0)} |",
            f"| Overall save rate | {metrics.get('overall_save_rate', 0):.1%} |",
            f"| Facial YES rate | {metrics.get('facial_yes_rate', 0):.1%} |",
            "",
        ]
    )

    lines.extend(
        _render_named_section(
            "Top Performing Lanes",
            report.winning_lanes,
            "lane",
            ["string_ids", "candidate_examples", "evidence", "why_it_worked", "recommended_action"],
        )
    )
    lines.extend(
        _render_named_section(
            "Underperforming Lanes",
            report.underperforming_lanes,
            "lane",
            ["string_ids", "issue", "evidence", "recommended_action"],
        )
    )
    lines.extend(
        _render_named_section(
            "Coverage Gaps",
            report.coverage_gaps,
            "gap",
            ["why_it_matters", "suggested_search_strategy"],
        )
    )
    lines.extend(
        _render_named_section(
            "Noise Patterns",
            report.noise_patterns,
            "pattern",
            ["evidence", "mitigation"],
        )
    )

    lines.append("## Saved Candidate Patterns")
    standout = saved_patterns.get("standout_candidates", [])
    if standout:
        lines.append("### Standout Candidates")
        for item in standout:
            lines.append(f"- **{item.get('name', 'Unnamed')}**: {item.get('why', '').strip()}")
    common_employers = saved_patterns.get("common_employers", [])
    if common_employers:
        lines.append("### Common Employers")
        for item in common_employers:
            note = f" — {item.get('note', '').strip()}" if item.get("note") else ""
            lines.append(f"- **{item.get('employer', 'Unknown')}**: {item.get('count', 0)}{note}")
    common_titles = saved_patterns.get("common_titles", [])
    if common_titles:
        lines.append("### Common Titles")
        for item in common_titles:
            note = f" — {item.get('note', '').strip()}" if item.get("note") else ""
            lines.append(f"- **{item.get('title_family', 'Unknown')}**: {item.get('count', 0)}{note}")
    archetypes = saved_patterns.get("archetype_distribution", [])
    if archetypes:
        lines.append("### Archetype Distribution")
        for item in archetypes:
            note = f" — {item.get('note', '').strip()}" if item.get("note") else ""
            lines.append(f"- **{item.get('archetype', 'Unknown')}**: {item.get('count', 0)}{note}")
    seniority_notes = _stringify_list(saved_patterns.get("seniority_notes", []))
    if seniority_notes:
        lines.append("### Seniority Notes")
        for item in seniority_notes:
            lines.append(f"- {item}")
    lines.append("")

    lines.append("## Adaptation Assessment")
    if adaptation.get("summary"):
        lines.append(str(adaptation["summary"]).strip())
    effective = _stringify_list(adaptation.get("effective_refinements", []))
    if effective:
        lines.append("")
        lines.append("### Effective Refinements")
        for item in effective:
            lines.append(f"- {item}")
    questionable = _stringify_list(adaptation.get("questionable_or_skipped", []))
    if questionable:
        lines.append("")
        lines.append("### Questionable or Skipped")
        for item in questionable:
            lines.append(f"- {item}")
    operational = _stringify_list(adaptation.get("operational_notes", []))
    if operational:
        lines.append("")
        lines.append("### Operational Notes")
        for item in operational:
            lines.append(f"- {item}")
    lines.append("")

    lines.append("## Recommendations")
    for heading, key in (
        ("Try Next", "try_next"),
        ("Avoid Next", "avoid_next"),
        ("Prioritize Pipeline", "prioritize_pipeline"),
    ):
        values = _stringify_list(recs.get(key, []))
        if values:
            lines.append(f"### {heading}")
            for item in values:
                lines.append(f"- {item}")
    lines.append("")

    locked_cautions = _stringify_list(hints.get("locked_field_cautions", []))
    if locked_cautions:
        lines.append("## Brief Iteration Hints")
        for item in locked_cautions:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
