"""Market-intelligence evidence ingestion, synthesis, and artifact persistence."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Protocol

from market_intelligence.agent_backends import (
    CriticResult,
    HeuristicCriticBackend,
    HeuristicPlannerBackend,
    LLMCriticBackend,
    LLMInternalSynthesisBackend,
    LLMPlannerBackend,
    PlannerResult,
)
from market_intelligence.research_context import maybe_build_and_persist_research_packet
from market_intelligence.run_snapshots import (
    import_legacy_run_snapshot,
    load_run_manifest,
    validate_run_dir_for_ingestion,
)
from market_intelligence.schema import (
    MarketEvidenceBatch,
    MarketHypothesis,
    MarketIntelAgentState,
    MarketIdentity,
    MarketIntelArtifact,
    ResearchOpportunity,
    SectionGenerationMetadata,
    SourceRegistryEntry,
    market_thesis_summary_looks_like_review,
    render_market_intel_markdown,
    render_market_intel_technical_markdown,
    sanitize_market_findings,
    sanitize_market_intel_payload,
    sanitize_narrative_items,
    sanitize_sourcing_implications,
)
import shared.config as shared_config
from shared.brief_loader import Brief, load_brief
from shared.llm_usage import llm_usage_session
from shared.output_paths import (
    classify_output_location,
    is_output_root,
    is_run_dir,
    is_state_dir,
    looks_like_finalized_run_dir,
    output_root_for_path,
)
from shared.retrieval_design import (
    retrieval_design_from_payload,
    summarize_retrieval_design,
)
from shared.run_report_schema import StructuredRunReport
from shared.strict_seniority import looks_like_company_inventory
from shared.search_memory import (
    extract_dominant_anchors,
    get_search_memory_families,
    infer_domain_lane,
    normalize_family_key,
    normalize_novelty_bucket,
)
from shared.storage import append_jsonl, read_json, read_jsonl, write_json


SCHEMA_VERSION = 1
SAVE_DECISIONS = {"SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE", "SIGNAL_SAVE"}
BORDERLINE_DECISIONS = {"SIGNAL_SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE"}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _slugify(value: str) -> str:
    lowered = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or ""))
    while "__" in lowered:
        lowered = lowered.replace("__", "_")
    return lowered.strip("_") or "unknown"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _max_timestamp(values: list[str]) -> str:
    parsed = [(_parse_dt(value), value) for value in values if value]
    parsed = [(dt, raw) for dt, raw in parsed if dt is not None]
    if not parsed:
        return ""
    parsed.sort(key=lambda item: item[0])
    return parsed[-1][1]


def _maybe_build_external_research_backend() -> Any | None:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return None
    try:
        from market_intelligence.research_agent import build_external_research_backend

        return build_external_research_backend()
    except Exception:
        return None


def _merge_external_sources(
    *,
    previous_sources: list[dict] | None,
    current_sources: list[dict] | None,
) -> list[dict]:
    merged: dict[str, dict] = {}
    for source in list(previous_sources or []) + list(current_sources or []):
        if not isinstance(source, dict):
            continue
        source_id = _normalize_text(source.get("source_id"))
        url = _normalize_text(source.get("url"))
        key = source_id or url
        if not key:
            continue
        existing = merged.get(key, {})
        combined = dict(existing)
        combined.update(source)
        existing_used_for = {
            _normalize_text(item)
            for item in existing.get("used_for", [])
            if _normalize_text(item)
        }
        current_used_for = {
            _normalize_text(item)
            for item in source.get("used_for", [])
            if _normalize_text(item)
        }
        if existing_used_for or current_used_for:
            combined["used_for"] = sorted(existing_used_for | current_used_for)
        merged[key] = combined
    return list(merged.values())


def _relative_output_dir(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(shared_config.PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _output_root(output_dir: str | Path | None) -> Path:
    return output_root_for_path(output_dir)


def _role_level_from_brief(brief: Brief, raw: dict) -> str:
    return _normalize_text(raw.get("role_level")) or _normalize_text(
        getattr(getattr(brief, "_new_brief", None), "role_level", "")
    )


def _geography_from_brief(brief: Brief, raw: dict) -> str:
    if _normalize_text(raw.get("geography")):
        return _normalize_text(raw.get("geography"))
    if _normalize_text(brief.permanent_filters.get("Location")):
        return _normalize_text(brief.permanent_filters.get("Location"))
    return ""


def derive_market_key(brief: Brief, raw: dict) -> str:
    return "__".join(
        [
            _slugify(brief.role_title),
            _slugify(_geography_from_brief(brief, raw)),
            _slugify(_role_level_from_brief(brief, raw)),
        ]
    )


def resolve_market_intel_artifact_path(
    brief_path: str | Path,
    output_dir: str | Path | None = None,
) -> Path:
    brief_path = Path(brief_path)
    raw = read_json(brief_path)
    brief = load_brief(str(brief_path))
    market_key = derive_market_key(brief, raw)
    root = _output_root(output_dir)
    return root / "market_intelligence" / market_key / "market-intel.json"


def resolve_market_intel_agent_state_path(
    brief_path: str | Path,
    output_dir: str | Path | None = None,
) -> Path:
    return resolve_market_intel_artifact_path(
        brief_path,
        output_dir=output_dir,
    ).with_name("agent-state.json")


def resolve_market_intel_research_log_path(
    brief_path: str | Path,
    output_dir: str | Path | None = None,
) -> Path:
    return resolve_market_intel_artifact_path(
        brief_path,
        output_dir=output_dir,
    ).with_name("research-log.jsonl")


@dataclass
class ExternalResearchResult:
    sources: list[dict] = field(default_factory=list)
    inferred_research_questions: list[dict] = field(default_factory=list)
    market_findings: list[dict] = field(default_factory=list)
    sourcing_implications: list[dict] = field(default_factory=list)
    market_thesis_context: list[dict] = field(default_factory=list)
    open_questions: list[dict] = field(default_factory=list)
    edge_case_triggered: bool = False
    edge_case_reasoning: str = ""
    edge_case_focus: list[dict] = field(default_factory=list)
    edge_case_inferred_research_questions: list[dict] = field(default_factory=list)
    edge_case_submarkets: list[dict] = field(default_factory=list)
    title_to_archetype_mapping: list[dict] = field(default_factory=list)
    self_presentation_patterns: list[dict] = field(default_factory=list)
    false_negative_hypotheses: list[dict] = field(default_factory=list)
    edge_case_sourcing_implications: list[dict] = field(default_factory=list)
    edge_case_open_questions: list[dict] = field(default_factory=list)


def _emit_stage(message: str) -> None:
    print(f"[market-intel] {message}", file=sys.stderr, flush=True)


def _dedupe_dict_records(items: list[dict], *, key_fields: tuple[str, ...]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[tuple[str, ...]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        key = tuple(_normalize_text(item.get(field)).lower() for field in key_fields)
        if not any(key):
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _merge_external_results(
    base: ExternalResearchResult | None,
    extra: ExternalResearchResult | None,
) -> ExternalResearchResult | None:
    if base is None:
        return extra
    if extra is None:
        return base
    return ExternalResearchResult(
        sources=_dedupe_dict_records(
            list(base.sources) + list(extra.sources),
            key_fields=("source_id", "url"),
        ),
        inferred_research_questions=_dedupe_dict_records(
            list(base.inferred_research_questions)
            + list(extra.inferred_research_questions),
            key_fields=("question",),
        ),
        market_findings=_dedupe_dict_records(
            list(base.market_findings) + list(extra.market_findings),
            key_fields=("finding_key", "label", "kind"),
        ),
        sourcing_implications=_dedupe_dict_records(
            list(base.sourcing_implications) + list(extra.sourcing_implications),
            key_fields=("implication_id", "recommendation"),
        ),
        market_thesis_context=_dedupe_dict_records(
            list(base.market_thesis_context) + list(extra.market_thesis_context),
            key_fields=("claim",),
        ),
        open_questions=_dedupe_dict_records(
            list(base.open_questions) + list(extra.open_questions),
            key_fields=("question",),
        ),
        edge_case_triggered=base.edge_case_triggered or extra.edge_case_triggered,
        edge_case_reasoning=_normalize_text(extra.edge_case_reasoning)
        or _normalize_text(base.edge_case_reasoning),
        edge_case_focus=_dedupe_dict_records(
            list(base.edge_case_focus) + list(extra.edge_case_focus),
            key_fields=("focus",),
        ),
        edge_case_inferred_research_questions=_dedupe_dict_records(
            list(base.edge_case_inferred_research_questions)
            + list(extra.edge_case_inferred_research_questions),
            key_fields=("question",),
        ),
        edge_case_submarkets=_dedupe_dict_records(
            list(base.edge_case_submarkets) + list(extra.edge_case_submarkets),
            key_fields=("submarket_key", "label"),
        ),
        title_to_archetype_mapping=_dedupe_dict_records(
            list(base.title_to_archetype_mapping) + list(extra.title_to_archetype_mapping),
            key_fields=("mapping_key", "title_family", "likely_archetype"),
        ),
        self_presentation_patterns=_dedupe_dict_records(
            list(base.self_presentation_patterns) + list(extra.self_presentation_patterns),
            key_fields=("pattern_key", "label"),
        ),
        false_negative_hypotheses=_dedupe_dict_records(
            list(base.false_negative_hypotheses) + list(extra.false_negative_hypotheses),
            key_fields=("hypothesis_key", "statement"),
        ),
        edge_case_sourcing_implications=_dedupe_dict_records(
            list(base.edge_case_sourcing_implications)
            + list(extra.edge_case_sourcing_implications),
            key_fields=("implication_id", "recommendation"),
        ),
        edge_case_open_questions=_dedupe_dict_records(
            list(base.edge_case_open_questions) + list(extra.edge_case_open_questions),
            key_fields=("question",),
        ),
    )


class ExternalResearchBackend(Protocol):
    def collect(
        self,
        *,
        market_identity: MarketIdentity,
        previous_artifact: MarketIntelArtifact | None,
        previous_agent_state: MarketIntelAgentState | None,
        evidence_batches: list[MarketEvidenceBatch],
        planner_result: PlannerResult | None = None,
        research_focus: list[dict] | None = None,
        research_mode: str = "general",
        edge_case_reasoning: str = "",
    ) -> ExternalResearchResult: ...


class MarketIntelSynthesisBackend(Protocol):
    def synthesize(
        self,
        *,
        market_identity: MarketIdentity,
        deterministic_summary: dict,
        evidence_batches: list[MarketEvidenceBatch],
        previous_artifact: MarketIntelArtifact | None,
        planner_result: PlannerResult | None = None,
        external_research: ExternalResearchResult | None,
    ) -> dict: ...


class PlannerBackend(Protocol):
    def plan(
        self,
        *,
        market_identity: MarketIdentity,
        deterministic_summary: dict,
        evidence_batches: list[MarketEvidenceBatch],
        previous_artifact: MarketIntelArtifact | None,
        previous_agent_state: MarketIntelAgentState | None,
    ) -> PlannerResult: ...


class CriticBackend(Protocol):
    def critique(
        self,
        *,
        market_identity: MarketIdentity,
        deterministic_summary: dict,
        evidence_batches: list[MarketEvidenceBatch],
        previous_artifact: MarketIntelArtifact | None,
        planner_result: PlannerResult,
        draft_sections: dict,
        external_research: ExternalResearchResult | None,
    ) -> CriticResult: ...


class HeuristicMarketIntelSynthesisBackend:
    """Deterministic, evidence-led synthesis without a live model dependency."""

    def synthesize(
        self,
        *,
        market_identity: MarketIdentity,
        deterministic_summary: dict,
        evidence_batches: list[MarketEvidenceBatch],
        previous_artifact: MarketIntelArtifact | None,
        planner_result: PlannerResult | None = None,
        external_research: ExternalResearchResult | None,
    ) -> dict:
        lane_records = deterministic_summary["lane_intelligence"]
        lane_by_key = {lane["lane_key"]: lane for lane in lane_records}

        lane_narratives: dict[str, dict] = {}
        talent_pools: dict[str, dict] = {}
        noise_patterns: dict[str, dict] = {}
        employer_signals: dict[str, dict] = {}
        brief_recs: dict[str, dict] = {}
        open_questions: dict[str, dict] = {}

        for batch in evidence_batches:
            report = batch.report or {}
            research_context = batch.research_context or {}
            deterministic_snapshot = (
                research_context.get("deterministic_snapshot", {})
                if isinstance(research_context, dict)
                else {}
            )
            report_analysis = (
                research_context.get("report_analysis", {})
                if isinstance(research_context, dict)
                else {}
            )
            performance = {
                int(item.get("string_id", -1)): item
                for item in (
                    deterministic_snapshot.get("string_performance")
                    or report.get("string_performance", [])
                )
                if isinstance(item, dict)
            }

            for winner in report_analysis.get("winning_lanes", []) or report.get(
                "winning_lanes", []
            ):
                lane_key = _lane_key_from_report_lane(winner, performance)
                if not lane_key or lane_key not in lane_by_key:
                    continue
                lane_narratives[lane_key] = {
                    "lane_key": lane_key,
                    "supporting_run_refs": [batch.run_ref],
                    "why_it_works": _normalize_text(winner.get("why_it_worked"))
                    or "Repeatedly surfaced builder-quality saves.",
                    "recommended_action": _normalize_text(
                        winner.get("recommended_action")
                    )
                    or "Keep this lane active.",
                    "confidence": 0.8,
                }

            for under in report_analysis.get(
                "underperforming_lanes", []
            ) or report.get("underperforming_lanes", []):
                lane_key = _lane_key_from_report_lane(under, performance)
                if not lane_key or lane_key not in lane_by_key:
                    continue
                lane_narratives[lane_key] = {
                    "lane_key": lane_key,
                    "supporting_run_refs": [batch.run_ref],
                    "why_it_works": _normalize_text(under.get("issue"))
                    or "This lane produced weak signal.",
                    "recommended_action": _normalize_text(
                        under.get("recommended_action")
                    )
                    or "Reduce or retire this lane.",
                    "confidence": 0.68,
                }

            saved_patterns = report_analysis.get("saved_candidate_patterns", {}) or report.get(
                "saved_candidate_patterns", {}
            )
            for archetype in saved_patterns.get("archetype_distribution", []):
                label = _normalize_text(archetype.get("archetype"))
                if not label:
                    continue
                pool_key = _slugify(label)
                recommended_terms: list[str] = []
                for lane in lane_records[:3]:
                    recommended_terms.extend(lane.get("dominant_anchors", []))
                talent_pools[pool_key] = {
                    "pool_key": pool_key,
                    "label": label,
                    "status": "core_pool",
                    "signal_strength": round(
                        min(1.0, float(archetype.get("count", 1)) / 10.0 + 0.5),
                        2,
                    ),
                    "supporting_run_refs": [batch.run_ref],
                    "evidence_summary": _normalize_text(archetype.get("note"))
                    or "Observed repeatedly in saved candidates.",
                    "recommended_search_terms": recommended_terms[:6],
                }

            for pattern in report_analysis.get("noise_patterns", []) or report.get(
                "noise_patterns", []
            ):
                label = _normalize_text(pattern.get("pattern"))
                if not label:
                    continue
                pattern_key = _slugify(label)
                noise_patterns[pattern_key] = {
                    "pattern_key": pattern_key,
                    "label": label,
                    "severity": (
                        "high"
                        if "zero saves"
                        in _normalize_text(pattern.get("evidence")).lower()
                        else "medium"
                    ),
                    "supporting_run_refs": [batch.run_ref],
                    "mitigations": (
                        [_normalize_text(pattern.get("mitigation"))]
                        if _normalize_text(pattern.get("mitigation"))
                        else []
                    ),
                    "confidence": 0.7,
                }

            for employer in saved_patterns.get("common_employers", []):
                label = _normalize_text(employer.get("employer"))
                if not label:
                    continue
                cluster_key = _slugify(label)
                employer_signals[cluster_key] = {
                    "cluster_key": cluster_key,
                    "label": label,
                    "status": "positive",
                    "supporting_employers": [label],
                    "supporting_run_refs": [batch.run_ref],
                    "evidence_summary": _normalize_text(employer.get("note"))
                    or "Repeatedly appeared among saved candidates.",
                    "confidence": round(
                        min(0.95, 0.55 + float(employer.get("count", 1)) * 0.05),
                        2,
                    ),
                }

            hints = report_analysis.get("brief_iteration_hints", {}) or report.get(
                "brief_iteration_hints", {}
            )
            # Behavior-first / anti-employer-proxy guardrail: if the run's
            # brief-iteration hints are dominated by employer-inventory
            # content, demote them so they cannot drive opening retrieval.
            # Employer findings remain valid late-stage classifier signal,
            # but lane/anchor/noise evidence is the primary retrieval driver.
            # See market-intel + brief-authoring guide doctrine: titles,
            # employers, and keywords can support a pattern but should not
            # become the pattern.
            if hints.get("search_priorities"):
                priorities_items = [
                    str(item).strip()
                    for item in hints.get("search_priorities", [])[:3]
                    if str(item).strip()
                ]
                priorities_employer_proxy = any(
                    looks_like_company_inventory(item) for item in priorities_items
                )
                if priorities_employer_proxy:
                    brief_recs["rec-search-priorities"] = {
                        "recommendation_id": "rec-search-priorities",
                        "target_field": "employer_signal_rules",
                        "proposal_kind": "late_stage_gap_probe",
                        "proposal": ", ".join(priorities_items),
                        "reason": (
                            "Employer-cluster proposal surfaced in run hints; "
                            "demoted from opening retrieval to late-stage "
                            "lane classification per anti-employer-proxy rule."
                        ),
                        "supporting_run_refs": [batch.run_ref],
                        "confidence": 0.45,
                    }
                else:
                    brief_recs["rec-search-priorities"] = {
                        "recommendation_id": "rec-search-priorities",
                        "target_field": "search_priorities",
                        "proposal_kind": "opening_retrieval",
                        "proposal": ", ".join(priorities_items),
                        "reason": "Run evidence indicates these lanes deserve more explicit prioritization.",
                        "supporting_run_refs": [batch.run_ref],
                        "confidence": 0.8,
                        "retrieval_update": {
                            "update_type": "layer_update",
                            "category": "promote_family_objective",
                            "target_field": "retrieval_design",
                            "layer_name": "entry_signals",
                            "suggested_values": priorities_items,
                            "reason": "Winning lanes should become explicit retrieval-family priorities.",
                        },
                    }
            if hints.get("additional_search_terms"):
                term_items = [
                    str(item).strip()
                    for item in hints.get("additional_search_terms", [])[:6]
                    if str(item).strip()
                ]
                terms_employer_proxy = any(
                    looks_like_company_inventory(item) for item in term_items
                )
                if terms_employer_proxy:
                    brief_recs["rec-additional-search-terms"] = {
                        "recommendation_id": "rec-additional-search-terms",
                        "target_field": "employer_signal_rules",
                        "proposal_kind": "late_stage_gap_probe",
                        "proposal": ", ".join(term_items),
                        "reason": (
                            "Employer-inventory terms surfaced in run hints; "
                            "demoted from opening retrieval to late-stage "
                            "classifier signal per anti-employer-proxy rule."
                        ),
                        "supporting_run_refs": [batch.run_ref],
                        "confidence": 0.42,
                    }
                else:
                    brief_recs["rec-additional-search-terms"] = {
                        "recommendation_id": "rec-additional-search-terms",
                        "target_field": "additional_search_terms",
                        "proposal_kind": "opening_retrieval",
                        "proposal": ", ".join(term_items),
                        "reason": "These terms surfaced from the best-performing parts of the run.",
                        "supporting_run_refs": [batch.run_ref],
                        "confidence": 0.78,
                        "retrieval_update": {
                            "update_type": "layer_update",
                            "category": "promote_layer_terms",
                            "target_field": "retrieval_design",
                            "layer_name": "capability_proxies",
                            "suggested_values": term_items,
                            "reason": "Winning anchors should become typed capability or reality-filter terms.",
                        },
                    }

            for gap in report_analysis.get("coverage_gaps", []) or report.get(
                "coverage_gaps", []
            ):
                question = (
                    f"How should we cover "
                    f"{str(gap.get('gap', 'this gap')).strip()} more directly?"
                )
                open_questions[_slugify(question)] = {
                    "question": question,
                    "priority": "medium",
                    "next_step": _normalize_text(gap.get("suggested_search_strategy"))
                    or "Run one exploratory lane next cycle.",
                    "supporting_run_refs": [batch.run_ref],
                }

        aggregate = deterministic_summary["aggregate_metrics"]
        lane_labels = [lane["lane_key"].replace("_", " ") for lane in lane_records[:2]]
        if aggregate.get("save_rate", 0) >= 0.1 or aggregate.get("saved_count", 0) >= 20:
            supply = "dense"
        elif aggregate.get("save_rate", 0) >= 0.04 or aggregate.get("saved_count", 0) >= 5:
            supply = "moderate"
        else:
            supply = "sparse"
        competition = {"dense": "medium", "moderate": "high", "sparse": "high"}[supply]

        thesis_summary = (
            f"The market for {market_identity.role_title} in "
            f"{market_identity.geography or 'the target geography'} looks {supply}, "
            f"with the strongest current signal in "
            f"{', '.join(lane_labels) or 'the top lanes'}."
        )

        return {
            "lane_intelligence": list(lane_narratives.values()),
            "talent_pool_intelligence": list(talent_pools.values()),
            "noise_patterns": list(noise_patterns.values()),
            "employer_signal_intelligence": list(employer_signals.values()),
            "market_thesis": {
                "summary": thesis_summary,
                "supply_assessment": supply,
                "competition_assessment": competition,
                "external_context": [],
            },
            "brief_recommendations": list(brief_recs.values()),
            "open_questions": list(open_questions.values()),
        }


def _infer_snapshot_source(path: Path) -> str:
    runtime_summary = _load_runtime_summary(path / "runtime_state.sqlite3")
    source = _normalize_text(runtime_summary.get("source"))
    if source:
        return source
    return "github" if "github" in str(path).lower() else "linkedin"


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_market_intel_run_dir(
    *,
    brief_path: Path,
    mode: str,
    run_dir: str | Path | None,
    run_id: int | None,
    legacy_output_dir: str | Path | None,
    output_dir: str | Path | None,
    report_path: str | Path | None,
    allow_live_state_dir: bool,
    reconstruct_report_analysis: bool,
) -> Path | None:
    if output_dir is not None:
        if mode == "backfill" and legacy_output_dir is None and run_dir is None:
            legacy_output_dir = output_dir
        elif run_dir is None:
            run_dir = output_dir
    if run_dir is None and report_path is not None and mode != "backfill":
        run_dir = Path(report_path).parent

    candidate_run_dir = Path(run_dir).resolve() if run_dir is not None else None
    candidate_legacy_dir = (
        Path(legacy_output_dir).resolve() if legacy_output_dir is not None else None
    )

    if candidate_run_dir is not None:
        if is_output_root(candidate_run_dir):
            raise ValueError(
                "Market intel cannot ingest the bare output/ root. Point it at a finalized run_dir under output/runs/."
            )
        if is_state_dir(candidate_run_dir):
            if not allow_live_state_dir:
                raise ValueError(
                    "Market intel requires a finalized run_dir under output/runs/, not a mutable state_dir under output/state/."
                )
            candidate_legacy_dir = candidate_run_dir
            candidate_run_dir = None
        elif is_run_dir(candidate_run_dir):
            candidate_run_dir = validate_run_dir_for_ingestion(candidate_run_dir)
        else:
            if mode == "backfill":
                candidate_legacy_dir = candidate_run_dir
                candidate_run_dir = None
            else:
                location = classify_output_location(candidate_run_dir)
                raise ValueError(
                    f"Expected a finalized run_dir under output/runs/, got {location}: {candidate_run_dir}"
                )

    if candidate_legacy_dir is not None:
        imported_run_dir = import_legacy_run_snapshot(
            brief_path=brief_path,
            legacy_output_dir=candidate_legacy_dir,
            source=_infer_snapshot_source(candidate_legacy_dir),
            run_id=run_id,
            reconstruct_report_analysis=reconstruct_report_analysis or mode == "backfill",
        )
        return validate_run_dir_for_ingestion(imported_run_dir)

    return candidate_run_dir


def update_market_intel(
    *,
    brief_path: str | Path,
    run_dir: str | Path | None = None,
    run_id: int | None = None,
    legacy_output_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    report_path: str | Path | None = None,
    mode: str = "post_run",
    external_research_backend: ExternalResearchBackend | None = None,
    synthesis_backend: MarketIntelSynthesisBackend | None = None,
    planner_backend: PlannerBackend | None = None,
    critic_backend: CriticBackend | None = None,
    with_external_research: bool | None = None,
    force_external_research: bool = False,
    force_edge_case_research: bool = False,
    allow_live_state_dir: bool = False,
    reconstruct_report_analysis: bool = False,
) -> MarketIntelArtifact:
    brief_path = Path(brief_path)
    if mode not in {"post_run", "scheduled", "backfill"}:
        raise ValueError("mode must be 'post_run', 'scheduled', or 'backfill'")
    if not brief_path.exists():
        raise FileNotFoundError(f"Brief file not found: {brief_path}")

    run_dir_path = _resolve_market_intel_run_dir(
        brief_path=brief_path,
        mode=mode,
        run_dir=run_dir,
        run_id=run_id,
        legacy_output_dir=legacy_output_dir,
        output_dir=output_dir,
        report_path=report_path,
        allow_live_state_dir=allow_live_state_dir,
        reconstruct_report_analysis=reconstruct_report_analysis,
    )
    if mode in {"post_run", "backfill"} and run_dir_path is None:
        raise ValueError(
            "post_run/backfill updates require a finalized run_dir under output/runs/ or a legacy directory to import."
        )

    raw = read_json(brief_path)
    brief = load_brief(str(brief_path))
    market_identity = MarketIdentity(
        market_key=derive_market_key(brief, raw),
        role_title=brief.role_title,
        role_level=_role_level_from_brief(brief, raw),
        geography=_geography_from_brief(brief, raw),
        channels_seen=[],
        brief_ids_seen=[],
        brief_versions_seen=[],
    )

    artifact_path = resolve_market_intel_artifact_path(brief_path, output_dir=run_dir_path)
    agent_state_path = resolve_market_intel_agent_state_path(
        brief_path,
        output_dir=run_dir_path,
    )
    research_log_path = resolve_market_intel_research_log_path(
        brief_path,
        output_dir=run_dir_path,
    )
    artifact_dir = artifact_path.parent
    history_dir = artifact_dir / "history"
    previous_artifact = _load_previous_artifact(artifact_path)
    previous_agent_state = _load_previous_agent_state(agent_state_path)
    if mode == "scheduled" and run_dir_path is None and previous_artifact is None:
        raise ValueError(
            "scheduled mode requires an existing market-intel artifact or an explicit run_dir."
        )

    evidence_batches = _collect_evidence_batches(
        brief_path=brief_path,
        brief=brief,
        raw=raw,
        mode=mode,
        run_dir=run_dir_path,
        report_path=Path(report_path) if report_path else None,
        previous_artifact=previous_artifact,
        reconstruct_report_analysis=reconstruct_report_analysis or mode == "backfill",
    )
    if not evidence_batches:
        raise RuntimeError("No market-intelligence evidence batches could be resolved")

    deterministic_summary = _build_deterministic_summary(
        market_identity=market_identity,
        evidence_batches=evidence_batches,
        previous_artifact=previous_artifact,
    )

    if external_research_backend is None and with_external_research is not False:
        external_research_backend = _maybe_build_external_research_backend()

    planner_backend = planner_backend or LLMPlannerBackend(
        fallback=HeuristicPlannerBackend()
    )
    heuristic_synthesis_backend = HeuristicMarketIntelSynthesisBackend()
    synthesis_backend = synthesis_backend or LLMInternalSynthesisBackend(
        fallback_backend=heuristic_synthesis_backend
    )
    critic_backend = critic_backend or LLMCriticBackend(
        fallback=HeuristicCriticBackend()
    )
    external_result: ExternalResearchResult | None = None
    planner_result = PlannerResult()
    generated_sections: dict[str, Any] = {}
    critic_result = CriticResult()
    preserve_previous_narrative = False
    stage_errors: list[str] = []
    token_cost_log_path = artifact_dir / "token-cost-log.jsonl"

    with llm_usage_session(
        token_cost_log_path,
        pipeline="market_intel",
        market_key=market_identity.market_key,
        mode=mode,
        brief_path=str(brief_path),
    ):
        _emit_stage(f"planner:start backend={planner_backend.__class__.__name__}")
        try:
            planner_result = planner_backend.plan(
                market_identity=market_identity,
                deterministic_summary=deterministic_summary,
                evidence_batches=evidence_batches,
                previous_artifact=previous_artifact,
                previous_agent_state=previous_agent_state,
            )
            _emit_stage(
                "planner:done should_collect_external="
                f"{planner_result.should_collect_external_research} "
                f"focus={len(planner_result.external_research_focus)} "
                f"edge_case={planner_result.should_collect_edge_case_research} "
                f"edge_case_focus={len(planner_result.edge_case_research_focus)}"
            )
        except Exception as exc:
            preserve_previous_narrative = True
            stage_errors.append(f"planner:{exc}")
            _emit_stage(f"planner:error {exc}")
            planner_result = HeuristicPlannerBackend().plan(
                market_identity=market_identity,
                deterministic_summary=deterministic_summary,
                evidence_batches=evidence_batches,
                previous_artifact=previous_artifact,
                previous_agent_state=previous_agent_state,
            )
            _emit_stage(
                "planner:fallback backend=HeuristicPlannerBackend "
                f"focus={len(planner_result.external_research_focus)} "
                f"edge_case_focus={len(planner_result.edge_case_research_focus)}"
            )

        default_run_refs = [batch.run_ref for batch in evidence_batches if _normalize_text(batch.run_ref)]
        if force_external_research:
            planner_result.should_collect_external_research = True
            if not planner_result.external_research_focus:
                planner_result.external_research_focus = [
                    {
                        "focus": "Forced external research replay",
                        "priority": "high",
                        "reason": "Operator requested a provenance-preserving replay with external research enabled.",
                        "supporting_run_refs": default_run_refs,
                    }
                ]
            _emit_stage(
                "planner:override force_external_research "
                f"focus={len(planner_result.external_research_focus)}"
            )
        if force_edge_case_research:
            planner_result.should_collect_edge_case_research = True
            if not planner_result.edge_case_research_reasoning:
                planner_result.edge_case_research_reasoning = (
                    "Operator requested an edge-case replay to preserve hidden-pool analysis."
                )
            if not planner_result.edge_case_research_focus:
                planner_result.edge_case_research_focus = [
                    {
                        "focus": "Forced edge-case research replay",
                        "priority": "high",
                        "reason": "Operator requested a hidden-pool and title-fragmentation replay.",
                        "supporting_run_refs": default_run_refs,
                    }
                ]
            _emit_stage(
                "planner:override force_edge_case_research "
                f"focus={len(planner_result.edge_case_research_focus)}"
            )

        try:
            force_any_external = force_external_research or force_edge_case_research
            external_allowed = (
                True
                if force_any_external
                else (with_external_research if with_external_research is not None else True)
            )
            batch_incomplete = _explicit_linkedin_batch_is_incomplete(
                evidence_batches=evidence_batches,
                output_dir=Path(output_dir) if output_dir else None,
            )
            should_collect_external = (
                bool(external_research_backend)
                and external_allowed
                and planner_result.should_collect_external_research
            )
            should_collect_edge_case = (
                bool(external_research_backend)
                and external_allowed
                and planner_result.should_collect_edge_case_research
            )
            if should_collect_external and not batch_incomplete:
                try:
                    _emit_stage(
                        "external_research:start backend="
                        f"{external_research_backend.__class__.__name__} "
                        f"focus={len(planner_result.external_research_focus)}"
                    )
                    external_result = external_research_backend.collect(
                        market_identity=market_identity,
                        previous_artifact=previous_artifact,
                        previous_agent_state=previous_agent_state,
                        evidence_batches=evidence_batches,
                        planner_result=planner_result,
                        research_focus=planner_result.external_research_focus,
                        research_mode="general",
                    )
                    _emit_stage(
                        "external_research:done sources="
                        f"{len(external_result.sources)} "
                        f"findings={len(external_result.market_findings)} "
                        f"implications={len(external_result.sourcing_implications)} "
                        f"open_questions={len(external_result.open_questions)}"
                    )
                except Exception as exc:
                    preserve_previous_narrative = True
                    stage_errors.append(f"external_research:{exc}")
                    _emit_stage(f"external_research:error {exc}")
            elif not should_collect_edge_case:
                reason = "planner_disabled"
                if not external_allowed:
                    reason = "flag_disabled"
                elif not external_research_backend:
                    reason = "no_backend"
                elif batch_incomplete:
                    reason = "incomplete_run"
                _emit_stage(f"external_research:skip reason={reason}")
            if should_collect_edge_case and not batch_incomplete:
                try:
                    _emit_stage(
                        "edge_case_research:start backend="
                        f"{external_research_backend.__class__.__name__} "
                        f"focus={len(planner_result.edge_case_research_focus)}"
                    )
                    edge_case_result = external_research_backend.collect(
                        market_identity=market_identity,
                        previous_artifact=previous_artifact,
                        previous_agent_state=previous_agent_state,
                        evidence_batches=evidence_batches,
                        planner_result=planner_result,
                        research_focus=planner_result.edge_case_research_focus,
                        research_mode="edge_case",
                        edge_case_reasoning=planner_result.edge_case_research_reasoning,
                    )
                    edge_case_result.edge_case_triggered = True
                    edge_case_result.edge_case_reasoning = (
                        planner_result.edge_case_research_reasoning
                    )
                    edge_case_result.edge_case_focus = list(
                        planner_result.edge_case_research_focus
                    )
                    external_result = _merge_external_results(
                        external_result,
                        edge_case_result,
                    )
                    _emit_stage(
                        "edge_case_research:done submarkets="
                        f"{len(edge_case_result.edge_case_submarkets)} "
                        f"mappings={len(edge_case_result.title_to_archetype_mapping)} "
                        f"implications={len(edge_case_result.edge_case_sourcing_implications)} "
                        f"open_questions={len(edge_case_result.edge_case_open_questions)}"
                    )
                except Exception as exc:
                    preserve_previous_narrative = True
                    stage_errors.append(f"edge_case_research:{exc}")
                    _emit_stage(f"edge_case_research:error {exc}")
            else:
                reason = "planner_disabled"
                if not external_allowed:
                    reason = "flag_disabled"
                elif not external_research_backend:
                    reason = "no_backend"
                elif batch_incomplete:
                    reason = "incomplete_run"
                _emit_stage(f"edge_case_research:skip reason={reason}")
        except Exception as exc:
            preserve_previous_narrative = True
            stage_errors.append(f"external_research_orchestration:{exc}")
            _emit_stage(f"external_research_orchestration:error {exc}")

        _emit_stage(f"synthesis:start backend={synthesis_backend.__class__.__name__}")
        try:
            generated_sections = synthesis_backend.synthesize(
                market_identity=market_identity,
                deterministic_summary=deterministic_summary,
                evidence_batches=evidence_batches,
                previous_artifact=previous_artifact,
                planner_result=planner_result,
                external_research=external_result,
            )
            generated_sections = _merge_external_research_into_sections(
                generated_sections,
                external_result,
            )
            _emit_stage(f"synthesis:done sections={len(generated_sections)}")
        except Exception as exc:
            preserve_previous_narrative = True
            stage_errors.append(f"synthesis:{exc}")
            _emit_stage(f"synthesis:error {exc}")
            generated_sections = _merge_external_research_into_sections({}, external_result)

        _emit_stage(f"critic:start backend={critic_backend.__class__.__name__}")
        try:
            critic_result = critic_backend.critique(
                market_identity=market_identity,
                deterministic_summary=deterministic_summary,
                evidence_batches=evidence_batches,
                previous_artifact=previous_artifact,
                planner_result=planner_result,
                draft_sections=generated_sections,
                external_research=external_result,
            )
            _emit_stage(
                "critic:done keep_sections="
                f"{len(critic_result.keep_sections or {})} "
                f"delta_keys={len(critic_result.delta_since_last_run or {})}"
            )
        except Exception as exc:
            preserve_previous_narrative = True
            stage_errors.append(f"critic:{exc}")
            _emit_stage(f"critic:error {exc}")
            critic_result = HeuristicCriticBackend().critique(
                market_identity=market_identity,
                deterministic_summary=deterministic_summary,
                evidence_batches=evidence_batches,
                previous_artifact=previous_artifact,
                planner_result=planner_result,
                draft_sections=generated_sections,
                external_research=external_result,
            )
            _emit_stage("critic:fallback backend=HeuristicCriticBackend")

    artifact = _build_artifact(
        brief=brief,
        market_identity=market_identity,
        deterministic_summary=deterministic_summary,
        evidence_batches=evidence_batches,
        previous_artifact=previous_artifact,
        generated_sections=critic_result.keep_sections or generated_sections,
        preserve_previous_narrative=preserve_previous_narrative,
        external_result=external_result,
        section_generation_metadata=critic_result.section_generation_metadata,
        delta_since_last_run=critic_result.delta_since_last_run,
    )
    agent_state = _build_agent_state(
        market_identity=market_identity,
        evidence_batches=evidence_batches,
        previous_agent_state=previous_agent_state,
        planner_result=planner_result,
        critic_result=critic_result,
        external_result=external_result,
    )

    artifact_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    artifact_markdown = render_market_intel_markdown(artifact)
    technical_markdown = render_market_intel_technical_markdown(
        artifact,
        planner_summary=planner_result.planner_summary,
        critique_summary=critic_result.critique_summary,
        edge_case_research_reasoning=getattr(
            external_result,
            "edge_case_reasoning",
            "",
        )
        if external_result
        else "",
        edge_case_focus=getattr(external_result, "edge_case_focus", [])
        if external_result
        else [],
        inferred_research_questions=getattr(
            external_result,
            "inferred_research_questions",
            [],
        )
        if external_result
        else [],
        market_findings=getattr(external_result, "market_findings", [])
        if external_result
        else [],
        sourcing_implications=getattr(
            external_result,
            "sourcing_implications",
            [],
        )
        if external_result
        else [],
        edge_case_inferred_research_questions=getattr(
            external_result,
            "edge_case_inferred_research_questions",
            [],
        )
        if external_result
        else [],
        edge_case_submarkets=getattr(
            external_result,
            "edge_case_submarkets",
            [],
        )
        if external_result
        else [],
        title_to_archetype_mapping=getattr(
            external_result,
            "title_to_archetype_mapping",
            [],
        )
        if external_result
        else [],
        self_presentation_patterns=getattr(
            external_result,
            "self_presentation_patterns",
            [],
        )
        if external_result
        else [],
        false_negative_hypotheses=getattr(
            external_result,
            "false_negative_hypotheses",
            [],
        )
        if external_result
        else [],
        edge_case_sourcing_implications=getattr(
            external_result,
            "edge_case_sourcing_implications",
            [],
        )
        if external_result
        else [],
        edge_case_open_questions=getattr(
            external_result,
            "edge_case_open_questions",
            [],
        )
        if external_result
        else [],
        stage_errors=stage_errors,
    )
    write_json(artifact_path, artifact.to_dict())
    write_json(agent_state_path, agent_state.to_dict())
    (artifact_dir / "market-intel.md").write_text(artifact_markdown)
    (artifact_dir / "market-intel-technical.md").write_text(technical_markdown)
    history_stem = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    write_json(history_dir / f"{history_stem}.json", artifact.to_dict())
    write_json(history_dir / f"{history_stem}__agent-state.json", agent_state.to_dict())
    (history_dir / f"{history_stem}__market-intel.md").write_text(artifact_markdown)
    (history_dir / f"{history_stem}__market-intel-technical.md").write_text(
        technical_markdown
    )
    append_jsonl(
        research_log_path,
        {
            "timestamp": _utc_now(),
            "market_key": market_identity.market_key,
            "mode": mode,
            "planner_summary": planner_result.planner_summary,
            "critique_summary": critic_result.critique_summary,
            "external_sources_count": len(external_result.sources) if external_result else 0,
            "external_inferred_question_count": len(
                getattr(external_result, "inferred_research_questions", [])
            )
            if external_result
            else 0,
            "external_finding_count": len(getattr(external_result, "market_findings", []))
            if external_result
            else 0,
            "external_implication_count": len(
                getattr(external_result, "sourcing_implications", [])
            )
            if external_result
            else 0,
            "edge_case_triggered": bool(
                getattr(external_result, "edge_case_triggered", False)
            )
            if external_result
            else False,
            "edge_case_reasoning": _normalize_text(
                getattr(external_result, "edge_case_reasoning", "")
            )
            if external_result
            else "",
            "edge_case_submarket_count": len(
                getattr(external_result, "edge_case_submarkets", [])
            )
            if external_result
            else 0,
            "edge_case_mapping_count": len(
                getattr(external_result, "title_to_archetype_mapping", [])
            )
            if external_result
            else 0,
            "edge_case_implication_count": len(
                getattr(external_result, "edge_case_sourcing_implications", [])
            )
            if external_result
            else 0,
            "stage_errors": stage_errors,
            "run_refs": [batch.run_ref for batch in evidence_batches],
        },
    )
    _emit_stage(
        f"persist:done artifact={artifact_path} external_sources={len(external_result.sources) if external_result else 0}"
    )
    return artifact


def _load_previous_artifact(path: Path) -> MarketIntelArtifact | None:
    if not path.exists():
        return None
    payload = sanitize_market_intel_payload(read_json(path))
    return MarketIntelArtifact.from_dict(payload)


def _load_previous_agent_state(path: Path) -> MarketIntelAgentState | None:
    if not path.exists():
        return None
    try:
        return MarketIntelAgentState.from_dict(read_json(path))
    except Exception:
        return None


def _build_agent_state(
    *,
    market_identity: MarketIdentity,
    evidence_batches: list[MarketEvidenceBatch],
    previous_agent_state: MarketIntelAgentState | None,
    planner_result: PlannerResult,
    critic_result: CriticResult,
    external_result: ExternalResearchResult | None,
) -> MarketIntelAgentState:
    active_hypotheses: list[MarketHypothesis] = []
    if planner_result.active_hypotheses:
        active_hypotheses = [
            MarketHypothesis.from_dict(item)
            for item in planner_result.active_hypotheses
        ]
    elif previous_agent_state:
        active_hypotheses = list(previous_agent_state.active_hypotheses)

    resolved_map = {
        item.hypothesis_id: item
        for item in (previous_agent_state.resolved_hypotheses if previous_agent_state else [])
    }
    for item in planner_result.resolved_hypotheses:
        resolved = MarketHypothesis.from_dict(item)
        resolved_map[resolved.hypothesis_id] = resolved

    research_backlog: list[ResearchOpportunity] = []
    if planner_result.research_backlog:
        research_backlog = [
            ResearchOpportunity.from_dict(item)
            for item in planner_result.research_backlog
        ]
    elif previous_agent_state:
        research_backlog = list(previous_agent_state.research_backlog)

    previous_sources = {
        item.source_id: item
        for item in (previous_agent_state.source_registry if previous_agent_state else [])
    }
    for source in getattr(external_result, "sources", []) or []:
        try:
            entry = SourceRegistryEntry.from_dict(source)
        except Exception:
            continue
        previous_sources[entry.source_id] = entry
    prior_advisories = {
        item.advisory_id: item
        for item in (previous_agent_state.prior_advisories if previous_agent_state else [])
    }
    for advisory in _collect_live_advisories_for_agent_state(evidence_batches):
        prior_advisories[advisory.advisory_id] = advisory
    return MarketIntelAgentState(
        schema_version=SCHEMA_VERSION,
        market_key=market_identity.market_key,
        updated_at=_utc_now(),
        active_hypotheses=active_hypotheses,
        resolved_hypotheses=list(resolved_map.values()),
        open_unknowns=planner_result.open_unknowns or (
            previous_agent_state.open_unknowns if previous_agent_state else []
        ),
        research_backlog=research_backlog,
        source_registry=list(previous_sources.values()),
        confidence_by_claim_area=critic_result.confidence_by_claim_area,
        prior_advisories=list(prior_advisories.values())[-50:],
        section_generation_metadata={
            section: SectionGenerationMetadata.from_dict(value)
            for section, value in critic_result.section_generation_metadata.items()
            if isinstance(value, dict)
        },
    )


def _deterministic_section_generation_metadata(
    *,
    deterministic_summary: dict,
    evidence_batches: list[MarketEvidenceBatch],
    critic_metadata: dict[str, dict],
) -> dict[str, dict]:
    now = _utc_now()
    supporting_refs = [batch.run_ref for batch in evidence_batches]
    metadata = {
        "freshness": {
            "generation_mode": "deterministic",
            "quality_level": "high",
            "updated_at": now,
            "notes": ["Computed from deterministic evidence timestamps."],
            "supporting_run_refs": supporting_refs,
            "evidence_refs": [],
        },
        "evidence_index": {
            "generation_mode": "deterministic",
            "quality_level": "high",
            "updated_at": now,
            "notes": ["Derived from indexed run and source records."],
            "supporting_run_refs": supporting_refs,
            "evidence_refs": [],
        },
        "aggregate_metrics": {
            "generation_mode": "deterministic",
            "quality_level": "high",
            "updated_at": now,
            "notes": ["Counts and rates recomputed from all evidence batches."],
            "supporting_run_refs": supporting_refs,
            "evidence_refs": [],
        },
        "channel_summaries": {
            "generation_mode": "deterministic",
            "quality_level": "high",
            "updated_at": now,
            "notes": ["Per-channel lane summaries derived from deterministic lane aggregation."],
            "supporting_run_refs": supporting_refs,
            "evidence_refs": [],
        },
        "candidate_signal_summary": critic_metadata.get(
            "candidate_signal_summary",
            {
                "generation_mode": "deterministic",
                "quality_level": "high" if evidence_batches else "low",
                "updated_at": now,
                "notes": ["Derived from final judgment rationale anchors."],
                "supporting_run_refs": supporting_refs,
                "evidence_refs": [],
            },
        ),
    }
    metadata.update(critic_metadata)
    return metadata


def _collect_live_advisories_for_agent_state(
    evidence_batches: list[MarketEvidenceBatch],
) -> list[Any]:
    advisories = []
    seen: set[str] = set()
    for batch in evidence_batches:
        candidate_dirs = [batch.run_dir, batch.output_dir, batch.state_dir]
        for candidate_dir in candidate_dirs:
            if not candidate_dir:
                continue
            path = Path(candidate_dir) / "market_intel" / "live-advisories.jsonl"
            if not path.exists():
                continue
            for record in read_jsonl(path):
                if not isinstance(record, dict):
                    continue
                try:
                    from market_intelligence.schema import MarketIntelAdvisory

                    advisory = MarketIntelAdvisory.from_dict(record)
                except Exception:
                    continue
                if advisory.advisory_id in seen:
                    continue
                seen.add(advisory.advisory_id)
                advisories.append(advisory)
    return advisories


def _collect_evidence_batches(
    *,
    brief_path: Path,
    brief: Brief,
    raw: dict,
    mode: str,
    run_dir: Path | None,
    report_path: Path | None,
    previous_artifact: MarketIntelArtifact | None,
    reconstruct_report_analysis: bool,
) -> list[MarketEvidenceBatch]:
    candidates: list[tuple[Path, bool, Path | None]] = []
    seen: set[Path] = set()

    def _add_candidate(
        path: Path | None,
        trust: bool,
        explicit_report: Path | None = None,
    ) -> None:
        if not path:
            return
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        candidates.append((resolved, trust, explicit_report))

    if run_dir is not None:
        _add_candidate(run_dir, True, report_path)

    if previous_artifact:
        for index, record in enumerate(previous_artifact.evidence_index.get("runs", []), start=1):
            output_path = Path(
                str(record.get("run_dir") or record.get("output_dir", ""))
            )
            if str(output_path).strip():
                if looks_like_finalized_run_dir(output_path):
                    _add_candidate(output_path, False)
                elif output_path.exists():
                    imported = import_legacy_run_snapshot(
                        brief_path=brief_path,
                        legacy_output_dir=output_path,
                        source=_normalize_text(record.get("source")) or _infer_snapshot_source(output_path),
                        run_id=_coerce_int(record.get("run_id")),
                        reconstruct_report_analysis=reconstruct_report_analysis,
                        legacy_index=index,
                    )
                    _add_candidate(imported, False)

    batches: list[MarketEvidenceBatch] = []
    for candidate_output_dir, trust, explicit_report in candidates:
        batch = _load_evidence_batch(
            brief_path=brief_path,
            brief=brief,
            raw=raw,
            output_dir=candidate_output_dir,
            explicit_report=explicit_report,
            trust_output_dir=trust,
            reconstruct_report_analysis=reconstruct_report_analysis,
        )
        if batch:
            batches.append(batch)
    return batches


def _load_evidence_batch(
    *,
    brief_path: Path,
    brief: Brief,
    raw: dict,
    output_dir: Path,
    explicit_report: Path | None,
    trust_output_dir: bool,
    reconstruct_report_analysis: bool,
) -> MarketEvidenceBatch | None:
    output_dir = output_dir.resolve()
    run_manifest = load_run_manifest(output_dir)
    report_path = explicit_report if explicit_report else output_dir / "run-report.json"
    report: dict | None = None
    if report_path.exists():
        report = StructuredRunReport.from_dict(read_json(report_path)).to_dict()
    manifest_run_id = _coerce_int(run_manifest.get("run_id"))

    runtime_summary = _load_runtime_summary(
        output_dir / "runtime_state.sqlite3",
        run_id=manifest_run_id,
    )
    if report and not _evidence_matches_brief(
        brief_path=brief_path,
        brief=brief,
        raw=raw,
        report=report,
        runtime_summary={},
    ):
        report = None
    matches_brief = _evidence_matches_brief(
        brief_path=brief_path,
        brief=brief,
        raw=raw,
        report=report,
        runtime_summary=runtime_summary,
    )
    if not trust_output_dir and not matches_brief:
        return None
    if trust_output_dir and (report or runtime_summary.get("brief_ids")) and not matches_brief:
        return None

    project_id = _normalize_text(raw.get("linkedin_project_id")) or _normalize_text(
        brief.linkedin_project_id
    ) or brief_path.stem
    search_memory_path = output_dir / f"search_memory-{project_id}.json"
    search_memory = read_json(search_memory_path) if search_memory_path.exists() else None
    if search_memory is None:
        search_memory_files = sorted(output_dir.glob("search_memory-*.json"))
        if search_memory_files:
            search_memory = read_json(search_memory_files[0])
    final_records = read_jsonl(output_dir / "final_judgments.jsonl")
    if (
        not report
        and not final_records
        and not runtime_summary.get("work_units")
        and not search_memory
        and not _run_dir_has_auxiliary_signal(output_dir)
    ):
        return None

    source = _normalize_text(run_manifest.get("source")) or _normalize_text(
        runtime_summary.get("source")
    )
    if not source:
        source = "github" if "github" in _relative_output_dir(output_dir) else "linkedin"

    generated_at = (
        _normalize_text((report or {}).get("run_metadata", {}).get("generated_at"))
        or _normalize_text(run_manifest.get("ended_at"))
        or _normalize_text(run_manifest.get("started_at"))
        or _normalize_text(runtime_summary.get("latest_generated_at"))
        or _file_timestamp(
            report_path if report_path.exists() else output_dir / "final_judgments.jsonl"
        )
        or _utc_now()
    )
    brief_version = _normalize_text(
        (report or {}).get("run_metadata", {}).get("brief_version")
    ) or _normalize_text(raw.get("version"))
    run_ref = f"{source}:{_relative_output_dir(output_dir)}"
    state_dir = _normalize_text(run_manifest.get("state_dir"))

    batch = MarketEvidenceBatch(
        run_ref=run_ref,
        source=source,
        output_dir=str(output_dir),
        run_id=manifest_run_id,
        run_dir=str(output_dir),
        state_dir=state_dir,
        brief_version=brief_version,
        generated_at=generated_at,
        report=report,
        search_memory=search_memory,
        final_judgments=final_records,
        runtime_summary=runtime_summary,
        metrics_summary=_extract_metrics_summary(report, runtime_summary, final_records),
        is_complete=_evidence_batch_is_complete(report, runtime_summary),
    )
    if batch.source == "linkedin":
        batch = maybe_build_and_persist_research_packet(
            batch,
            reconstruct_report_analysis=reconstruct_report_analysis,
        )
    elif batch.source == "github":
        # OSS Maintainers Slice 9: github batches get an ecosystem-
        # momentum narrative variant rather than the LinkedIn lane
        # / search-memory analysis. The shared abstraction (Phase 3
        # cleanup per spec §16) unifies the two once both have
        # hardened against real customer signal.
        from market_intelligence.github_reflection import (
            maybe_build_and_persist_github_research_packet,
        )

        batch = maybe_build_and_persist_github_research_packet(batch)
    return batch


def _evidence_matches_brief(
    *,
    brief_path: Path,
    brief: Brief,
    raw: dict,
    report: dict | None,
    runtime_summary: dict,
) -> bool:
    brief_keys = {
        _normalize_text(brief.role_title).lower(),
        _normalize_text(brief.id).lower(),
        _normalize_text(str(raw.get("linkedin_project_id", ""))).lower(),
        _normalize_text(brief_path.stem).lower(),
    }
    if report:
        role_title = _normalize_text(
            report.get("run_metadata", {}).get("role_title")
        ).lower()
        brief_name = _normalize_text(
            report.get("run_metadata", {}).get("brief_name")
        ).lower()
        if role_title and role_title in brief_keys:
            return True
        if brief_name and brief_name in brief_keys:
            return True
    for brief_id in runtime_summary.get("brief_ids", []):
        if _normalize_text(brief_id).lower() in brief_keys:
            return True
    return False


def _run_dir_has_auxiliary_signal(output_dir: Path) -> bool:
    for filename in (
        "market-intel-research-input.json",
        "profile_summaries.jsonl",
        "snippets.jsonl",
        "run_log.jsonl",
    ):
        path = output_dir / filename
        if not path.exists():
            continue
        try:
            if path.read_text().strip() not in {"", "[]", "{}"}:
                return True
        except OSError:
            continue
    return False


def _load_runtime_summary(db_path: Path, run_id: int | None = None) -> dict:
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if not {"runs", "work_units"}.issubset(tables):
            return {}
        if run_id is not None:
            run_rows = conn.execute(
                "SELECT id, source, brief_id, output_dir, status, started_at, ended_at FROM runs WHERE id = ?",
                (run_id,),
            ).fetchall()
            work_rows = conn.execute(
                """
                SELECT
                  source_unit_id,
                  display_name,
                  family_key,
                  novelty_bucket,
                  domain_lane,
                  payload_json,
                  checkpoint_json,
                  metrics_json,
                  candidates_discovered,
                  facial_yes_count,
                  facial_no_count,
                  facial_borderline_count,
                  saves_count,
                  rejected_count
                FROM work_units
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchall()
        else:
            run_rows = conn.execute(
                "SELECT id, source, brief_id, output_dir, status, started_at, ended_at FROM runs"
            ).fetchall()
            work_rows = conn.execute(
                """
                SELECT
                  source_unit_id,
                  display_name,
                  family_key,
                  novelty_bucket,
                  domain_lane,
                  payload_json,
                  checkpoint_json,
                  metrics_json,
                  candidates_discovered,
                  facial_yes_count,
                  facial_no_count,
                  facial_borderline_count,
                  saves_count,
                  rejected_count
                FROM work_units
                """
            ).fetchall()
    finally:
        conn.close()

    latest_run = dict(run_rows[-1]) if run_rows else {}
    source = _normalize_text(latest_run.get("source")) if latest_run else ""
    brief_ids = sorted(
        {
            _normalize_text(row["brief_id"])
            for row in run_rows
            if _normalize_text(row["brief_id"])
        }
    )
    latest_generated_at = _max_timestamp(
        [
            _normalize_text(row["ended_at"]) or _normalize_text(row["started_at"])
            for row in run_rows
        ]
    )

    work_units: list[dict] = []
    totals = {
        "run_count": len(run_rows),
        "candidate_volume": 0,
        "facial_yes": 0,
        "facial_no": 0,
        "facial_borderline": 0,
        "saved": 0,
        "rejected": 0,
    }
    for row in work_rows:
        payload = _loads_json(row["payload_json"])
        checkpoint = _loads_json(row["checkpoint_json"])
        metrics = _loads_json(row["metrics_json"])
        # C2 (slice 15): include facial_borderline_count in the YES+NO+BORDERLINE
        # floor so the candidate-volume estimate stays honest if a future code
        # path persists raw FACIAL_BORDERLINE rows. With slices 13/14 active,
        # this term is 0.
        facial_borderline_count = int(row["facial_borderline_count"] or 0)
        candidate_volume = max(
            int(row["candidates_discovered"] or 0),
            int(row["facial_yes_count"] or 0)
            + int(row["facial_no_count"] or 0)
            + facial_borderline_count,
            int(metrics.get("profiles_processed", 0) or 0),
            int(metrics.get("candidates_count", 0) or 0),
            int(row["saves_count"] or 0) + int(row["rejected_count"] or 0),
        )
        totals["candidate_volume"] += candidate_volume
        totals["facial_yes"] += int(row["facial_yes_count"] or 0)
        totals["facial_no"] += int(row["facial_no_count"] or 0)
        totals["facial_borderline"] += facial_borderline_count
        totals["saved"] += int(row["saves_count"] or 0)
        totals["rejected"] += int(row["rejected_count"] or 0)
        work_units.append(
            {
                "source_unit_id": str(row["source_unit_id"]),
                "display_name": _normalize_text(row["display_name"]),
                "family_key": _normalize_text(row["family_key"]),
                "novelty_bucket": _normalize_text(row["novelty_bucket"]),
                "domain_lane": _normalize_text(row["domain_lane"]),
                "boolean": _normalize_text(payload.get("boolean")),
                "pages_reviewed": int(
                    checkpoint.get("pages_reviewed")
                    or metrics.get("pages_reviewed")
                    or 0
                ),
                "duplicates_count": int(
                    checkpoint.get("duplicates_count")
                    or metrics.get("duplicates_count")
                    or 0
                ),
                "candidate_volume": candidate_volume,
                "facial_yes_count": int(row["facial_yes_count"] or 0),
                "facial_no_count": int(row["facial_no_count"] or 0),
                "facial_borderline_count": facial_borderline_count,
                "saves_count": int(row["saves_count"] or 0),
                "rejected_count": int(row["rejected_count"] or 0),
            }
        )

    return {
        "source": source,
        "brief_ids": brief_ids,
        "run_count": totals["run_count"],
        "latest_generated_at": latest_generated_at,
        "latest_run_status": _normalize_text(latest_run.get("status")),
        "latest_run_started_at": _normalize_text(latest_run.get("started_at")),
        "latest_run_ended_at": _normalize_text(latest_run.get("ended_at")),
        "candidate_volume": totals["candidate_volume"],
        "facial_yes": totals["facial_yes"],
        "facial_no": totals["facial_no"],
        "facial_borderline": totals["facial_borderline"],
        "saved": totals["saved"],
        "rejected": totals["rejected"],
        "work_units": work_units,
    }


def _evidence_batch_is_complete(report: dict | None, runtime_summary: dict) -> bool:
    if report:
        return True
    status = _normalize_text(runtime_summary.get("latest_run_status")).lower()
    if not status:
        return True
    return status not in {"running"}


def _explicit_linkedin_batch_is_incomplete(
    *,
    evidence_batches: list[MarketEvidenceBatch],
    output_dir: Path | None,
) -> bool:
    if output_dir is None:
        return False
    target = output_dir.resolve()
    for batch in evidence_batches:
        if batch.source != "linkedin":
            continue
        candidate_paths = [batch.output_dir, batch.run_dir, batch.state_dir]
        for candidate in candidate_paths:
            if not candidate:
                continue
            try:
                batch_dir = Path(candidate).resolve()
            except OSError:
                continue
            if batch_dir == target and not batch.is_complete:
                return True
    return False


def _build_deterministic_summary(
    *,
    market_identity: MarketIdentity,
    evidence_batches: list[MarketEvidenceBatch],
    previous_artifact: MarketIntelArtifact | None,
) -> dict:
    aggregate = {
        "run_count": 0,
        "saved_count": 0,
        "rejected_count": 0,
        "facial_yes_rate": 0.0,
        "save_rate": 0.0,
        "candidate_volume_by_channel": defaultdict(int),
    }
    total_candidate_volume = 0
    total_facial_yes = 0

    for batch in evidence_batches:
        metrics = batch.metrics_summary
        aggregate["run_count"] += int(metrics.get("run_count", 0))
        aggregate["saved_count"] += int(metrics.get("saved", 0))
        aggregate["rejected_count"] += int(metrics.get("rejected", 0))
        total_candidate_volume += int(metrics.get("candidate_volume", 0))
        total_facial_yes += int(metrics.get("facial_yes", 0))
        aggregate["candidate_volume_by_channel"][batch.source] += int(
            metrics.get("candidate_volume", 0)
        )

    aggregate["facial_yes_rate"] = round(
        total_facial_yes / max(total_candidate_volume, 1),
        4,
    )
    aggregate["save_rate"] = round(
        aggregate["saved_count"] / max(total_candidate_volume, 1),
        4,
    )
    aggregate["candidate_volume_by_channel"] = dict(
        aggregate["candidate_volume_by_channel"]
    )

    prior_identity = previous_artifact.market_identity if previous_artifact else None
    market_identity.channels_seen = sorted(
        set(prior_identity.channels_seen if prior_identity else [])
        | {batch.source for batch in evidence_batches}
    )
    market_identity.brief_ids_seen = sorted(
        set(prior_identity.brief_ids_seen if prior_identity else [])
        | {
            _normalize_text(brief_id)
            for batch in evidence_batches
            for brief_id in batch.runtime_summary.get("brief_ids", [])
            if _normalize_text(brief_id)
        }
        | {_normalize_text(market_identity.role_title)}
    )
    market_identity.brief_versions_seen = sorted(
        set(prior_identity.brief_versions_seen if prior_identity else [])
        | {
            _normalize_text(batch.brief_version)
            for batch in evidence_batches
            if _normalize_text(batch.brief_version)
        }
    )

    internal_data_through = _max_timestamp([batch.generated_at for batch in evidence_batches])
    freshness = {
        "artifact_updated_at": _utc_now(),
        "internal_data_through": internal_data_through,
        "external_research_through": "",
        "staleness_days": _staleness_days(internal_data_through),
    }

    lane_intelligence = _aggregate_lane_intelligence(
        evidence_batches=evidence_batches,
        previous_artifact=previous_artifact,
    )
    return {
        "freshness": freshness,
        "evidence_index": {
            "runs": [batch.to_run_index_record() for batch in evidence_batches],
            "external_sources": [],
        },
        "aggregate_metrics": aggregate,
        "channel_summaries": _build_channel_summaries(lane_intelligence, evidence_batches),
        "lane_intelligence": lane_intelligence,
        "candidate_signal_summary": _build_candidate_signal_summary(evidence_batches),
    }


def _aggregate_lane_intelligence(
    *,
    evidence_batches: list[MarketEvidenceBatch],
    previous_artifact: MarketIntelArtifact | None,
) -> list[dict]:
    previous_by_key = {
        lane["lane_key"]: lane
        for lane in (previous_artifact.lane_intelligence if previous_artifact else [])
    }
    lanes: dict[str, dict] = {}

    for batch in evidence_batches:
        report = batch.report or {}
        for entry in report.get("string_performance", []):
            if not isinstance(entry, dict):
                continue
            lane_key = normalize_family_key(
                entry.get("family_key"),
                entry.get("name", ""),
                entry.get("notes", ""),
            )
            lane = lanes.setdefault(
                lane_key,
                _empty_lane_record(
                    lane_key,
                    domain_lane=infer_domain_lane(
                        entry.get("domain_lane"),
                        entry.get("name", ""),
                        entry.get("notes", ""),
                    ),
                    novelty_bucket=normalize_novelty_bucket(
                        entry.get("novelty_bucket"),
                        entry.get("name", ""),
                        entry.get("notes", ""),
                    ),
                ),
            )
            candidates = int(entry.get("candidates_count") or 0)
            if not candidates:
                candidates = int(entry.get("facial_yes_count") or 0) + int(
                    entry.get("facial_no_count") or 0
                )
            _record_lane_metrics(
                lane,
                batch=batch,
                strings_seen=1,
                candidates_seen=candidates,
                saves=_save_count(entry.get("saves")),
                facial_yes=int(entry.get("facial_yes_count") or 0),
                facial_no=int(entry.get("facial_no_count") or 0),
                duplicates=int(entry.get("duplicates_count") or 0),
                anchors=extract_dominant_anchors(
                    f"{entry.get('name', '')} {entry.get('notes', '')}",
                    limit=8,
                ),
            )

        if not report:
            for work_unit in batch.runtime_summary.get("work_units", []):
                lane_key = normalize_family_key(
                    work_unit.get("family_key"),
                    work_unit.get("display_name", ""),
                    work_unit.get("boolean", ""),
                )
                lane = lanes.setdefault(
                    lane_key,
                    _empty_lane_record(
                        lane_key,
                        domain_lane=infer_domain_lane(
                            work_unit.get("domain_lane"),
                            work_unit.get("boolean", ""),
                            work_unit.get("display_name", ""),
                        ),
                        novelty_bucket=normalize_novelty_bucket(
                            work_unit.get("novelty_bucket"),
                            work_unit.get("boolean", ""),
                            work_unit.get("display_name", ""),
                        ),
                    ),
                )
                _record_lane_metrics(
                    lane,
                    batch=batch,
                    strings_seen=1,
                    candidates_seen=int(work_unit.get("candidate_volume", 0)),
                    saves=int(work_unit.get("saves_count", 0)),
                    facial_yes=int(work_unit.get("facial_yes_count", 0)),
                    facial_no=int(work_unit.get("facial_no_count", 0)),
                    duplicates=int(work_unit.get("duplicates_count", 0)),
                    anchors=extract_dominant_anchors(
                        f"{work_unit.get('display_name', '')} {work_unit.get('boolean', '')}",
                        limit=8,
                    ),
                )

        for family in get_search_memory_families(batch.search_memory):
            lane_key = normalize_family_key(
                family.get("family_key"),
                " ".join(family.get("dominant_anchors", [])),
                "",
            )
            lane = lanes.get(lane_key)
            if lane:
                _record_lane_metrics(
                    lane,
                    batch=batch,
                    strings_seen=0,
                    candidates_seen=0,
                    saves=0,
                    facial_yes=0,
                    facial_no=0,
                    duplicates=0,
                    anchors=_string_list(family.get("dominant_anchors", [])),
                )

    rendered: list[dict] = []
    for lane_key, lane in lanes.items():
        previous = previous_by_key.get(lane_key, {})
        metrics = lane["metrics"]
        metrics["save_rate"] = round(
            metrics["saves"] / max(metrics["candidates_seen"], 1),
            4,
        )
        metrics["duplicate_rate"] = round(
            metrics["duplicates"]
            / max(metrics["candidates_seen"] + metrics["duplicates"], 1),
            4,
        )
        supporting = sorted(
            set(previous.get("supporting_run_refs", []))
            | set(lane["supporting_run_refs"])
        )
        dominant = [anchor for anchor, _count in lane["anchor_counter"].most_common(5)]
        first_seen = previous.get("first_seen_at") or lane["first_seen_at"] or ""
        if previous.get("first_seen_at") and lane["first_seen_at"]:
            first_seen = min(previous["first_seen_at"], lane["first_seen_at"])
        last_seen = max(previous.get("last_seen_at", ""), lane["last_seen_at"])
        rendered.append(
            {
                "lane_key": lane_key,
                "domain_lane": lane["domain_lane"],
                "novelty_bucket": lane["novelty_bucket"],
                "status": _determine_lane_status(metrics),
                "first_seen_at": first_seen,
                "last_seen_at": last_seen,
                "supporting_run_refs": supporting,
                "metrics": metrics,
                "dominant_anchors": dominant,
            }
        )
    rendered.sort(
        key=lambda item: (
            0 if item["status"] == "winning" else 1,
            -item["metrics"]["saves"],
            item["lane_key"],
        )
    )
    return rendered


def _empty_lane_record(
    lane_key: str,
    *,
    domain_lane: str,
    novelty_bucket: str,
) -> dict:
    return {
        "lane_key": lane_key,
        "domain_lane": domain_lane or "general",
        "novelty_bucket": novelty_bucket or "canonical",
        "first_seen_at": "",
        "last_seen_at": "",
        "supporting_run_refs": set(),
        "anchor_counter": Counter(),
        "metrics": {
            "strings_seen": 0,
            "candidates_seen": 0,
            "saves": 0,
            "duplicates": 0,
            "facial_yes": 0,
            "facial_no": 0,
        },
    }


def _record_lane_metrics(
    lane: dict,
    *,
    batch: MarketEvidenceBatch,
    strings_seen: int,
    candidates_seen: int,
    saves: int,
    facial_yes: int,
    facial_no: int,
    duplicates: int,
    anchors: list[str],
) -> None:
    lane["metrics"]["strings_seen"] += max(strings_seen, 0)
    lane["metrics"]["candidates_seen"] += max(candidates_seen, 0)
    lane["metrics"]["saves"] += max(saves, 0)
    lane["metrics"]["duplicates"] += max(duplicates, 0)
    lane["metrics"]["facial_yes"] += max(facial_yes, 0)
    lane["metrics"]["facial_no"] += max(facial_no, 0)
    if batch.generated_at:
        if not lane["first_seen_at"] or batch.generated_at < lane["first_seen_at"]:
            lane["first_seen_at"] = batch.generated_at
        if batch.generated_at > lane["last_seen_at"]:
            lane["last_seen_at"] = batch.generated_at
    lane["supporting_run_refs"].add(batch.run_ref)
    lane["anchor_counter"].update(anchor for anchor in anchors if anchor)


def _determine_lane_status(metrics: dict) -> str:
    save_rate = metrics.get("save_rate", 0)
    duplicate_rate = metrics.get("duplicate_rate", 0)
    strings_seen = metrics.get("strings_seen", 0)
    candidates_seen = metrics.get("candidates_seen", 0)
    saves = metrics.get("saves", 0)
    if duplicate_rate >= 0.45 and strings_seen >= 2:
        return "saturated"
    if saves == 0 and candidates_seen >= 20:
        return "noise"
    if saves >= 3 or (save_rate >= 0.08 and candidates_seen >= 10):
        return "winning"
    return "mixed"


def _build_channel_summaries(
    lane_intelligence: list[dict],
    evidence_batches: list[MarketEvidenceBatch],
) -> dict:
    run_counts = Counter()
    for batch in evidence_batches:
        run_counts[batch.source] += int(batch.metrics_summary.get("run_count", 0) or 1)
    result: dict[str, dict] = {}
    for source in sorted(run_counts):
        source_lanes = [
            lane
            for lane in lane_intelligence
            if any(
                ref.startswith(f"{source}:")
                for ref in lane.get("supporting_run_refs", [])
            )
        ]
        source_lanes.sort(key=lambda item: item["metrics"]["saves"], reverse=True)
        result[source] = {
            "run_count": run_counts[source],
            "top_lane_keys": [
                lane["lane_key"]
                for lane in source_lanes
                if lane["status"] == "winning"
            ][:5],
            "saturated_lane_keys": [
                lane["lane_key"]
                for lane in source_lanes
                if lane["status"] == "saturated"
            ][:5],
        }
    return result


def _build_candidate_signal_summary(evidence_batches: list[MarketEvidenceBatch]) -> dict:
    standout_text: list[str] = []
    borderline_text: list[str] = []
    disqualifying_text: list[str] = []
    for batch in evidence_batches:
        for record in batch.final_judgments:
            if not isinstance(record, dict):
                continue
            text = " ".join(
                [
                    _normalize_text(record.get("rationale")),
                    _normalize_text(record.get("path")),
                    _normalize_text(record.get("reason")),
                ]
            )
            decision = _normalize_text(record.get("decision")).upper()
            if decision in SAVE_DECISIONS:
                standout_text.append(text)
            if decision in BORDERLINE_DECISIONS:
                borderline_text.append(text)
            if decision in {"REJECT", "FACIAL_NO", "FACIAL_SKIP"}:
                disqualifying_text.append(text)
    return {
        "standout_signals": extract_dominant_anchors(" ".join(standout_text), limit=6),
        "borderline_signals": extract_dominant_anchors(
            " ".join(borderline_text),
            limit=6,
        ),
        "disqualifying_signals": extract_dominant_anchors(
            " ".join(disqualifying_text),
            limit=6,
        ),
    }


def _sanitize_generated_sections(generated_sections: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(generated_sections or {})
    for section_name in (
        "talent_pool_intelligence",
        "noise_patterns",
        "employer_signal_intelligence",
        "brief_recommendations",
        "open_questions",
    ):
        if section_name in sanitized:
            sanitized[section_name] = sanitize_narrative_items(
                section_name,
                sanitized.get(section_name, []),
            )
    if isinstance(sanitized.get("market_thesis"), dict):
        market_thesis = dict(sanitized["market_thesis"])
        sanitized["market_thesis"] = {
            "summary": _normalize_text(market_thesis.get("summary")),
            "supply_assessment": _normalize_text(
                market_thesis.get("supply_assessment")
            )
            or "unknown",
            "competition_assessment": _normalize_text(
                market_thesis.get("competition_assessment")
            )
            or "unknown",
            "external_context": sanitize_narrative_items(
                "market_thesis.external_context",
                market_thesis.get("external_context", []),
            ),
        }
    return sanitized


def _finding_to_external_context(item: dict) -> dict | None:
    claim = _normalize_text(item.get("summary"))
    if not claim:
        return None
    evidence_refs = [
        ref for ref in item.get("evidence_refs", []) if _normalize_text(ref)
    ]
    if not evidence_refs:
        return None
    return {
        "claim": claim,
        "evidence_refs": evidence_refs,
        "confidence": float(item.get("confidence", 0.5) or 0.5),
    }


def _finding_to_talent_pool(item: dict) -> dict | None:
    if item.get("kind") not in {
        "title_variant",
        "talent_pool",
        "consulting_overlap",
        "adjacent_archetype",
    }:
        return None
    label = _normalize_text(item.get("label"))
    if not label:
        return None
    evidence_refs = [
        ref for ref in item.get("evidence_refs", []) if _normalize_text(ref)
    ]
    supporting_run_refs = [
        ref
        for ref in item.get("supporting_run_refs", [])
        if _normalize_text(ref)
    ]
    return {
        "pool_key": _slugify(label),
        "label": label,
        "status": "core_pool" if item.get("kind") == "talent_pool" else "adjacent_pool",
        "signal_strength": round(float(item.get("confidence", 0.6) or 0.6), 2),
        "supporting_run_refs": supporting_run_refs,
        "evidence_refs": evidence_refs,
        "evidence_summary": _normalize_text(item.get("summary"))
        or _normalize_text(item.get("why_it_matters")),
        "recommended_search_terms": [label],
    }


def _edge_case_submarket_to_external_context(item: dict) -> dict | None:
    label = _normalize_text(item.get("label"))
    summary = _normalize_text(item.get("summary"))
    why_missed = _normalize_text(item.get("why_it_is_easy_to_miss"))
    evidence_refs = [
        ref for ref in item.get("evidence_refs", []) if _normalize_text(ref)
    ]
    if not (label and summary and evidence_refs):
        return None
    claim = f"Hidden pool: {label}. {summary}"
    if why_missed:
        claim = f"{claim} Why this may be missed: {why_missed}"
    return {
        "claim": claim,
        "evidence_refs": evidence_refs,
        "confidence": float(item.get("confidence", 0.55) or 0.55),
    }


def _false_negative_hypothesis_to_external_context(item: dict) -> dict | None:
    statement = _normalize_text(item.get("statement"))
    why_it_matters = _normalize_text(item.get("why_it_matters"))
    evidence_refs = [
        ref for ref in item.get("evidence_refs", []) if _normalize_text(ref)
    ]
    if not (statement and why_it_matters and evidence_refs):
        return None
    return {
        "claim": f"{statement} {why_it_matters}",
        "evidence_refs": evidence_refs,
        "confidence": float(item.get("confidence", 0.5) or 0.5),
    }


def _edge_case_submarket_to_talent_pool(item: dict) -> dict | None:
    label = _normalize_text(item.get("label"))
    if not label:
        return None
    supporting_run_refs = [
        ref for ref in item.get("supporting_run_refs", []) if _normalize_text(ref)
    ]
    evidence_refs = [
        ref for ref in item.get("evidence_refs", []) if _normalize_text(ref)
    ]
    return {
        "pool_key": _normalize_text(item.get("submarket_key")) or _slugify(label),
        "label": label,
        "status": "adjacent_pool",
        "signal_strength": round(float(item.get("confidence", 0.55) or 0.55), 2),
        "supporting_run_refs": supporting_run_refs,
        "evidence_refs": evidence_refs,
        "evidence_summary": _normalize_text(item.get("summary"))
        or _normalize_text(item.get("why_it_is_easy_to_miss")),
        "recommended_search_terms": [label],
    }


def _title_mapping_to_talent_pool(item: dict) -> dict | None:
    title_family = _normalize_text(item.get("title_family"))
    likely_archetype = _normalize_text(item.get("likely_archetype"))
    caveats = _normalize_text(item.get("caveats"))
    if not (title_family and likely_archetype):
        return None
    supporting_run_refs = [
        ref for ref in item.get("supporting_run_refs", []) if _normalize_text(ref)
    ]
    evidence_refs = [
        ref for ref in item.get("evidence_refs", []) if _normalize_text(ref)
    ]
    summary = f"Likely archetype: {likely_archetype}."
    if caveats:
        summary = f"{summary} Caveat: {caveats}"
    return {
        "pool_key": _normalize_text(item.get("mapping_key"))
        or _slugify(f"{title_family}-{likely_archetype}"),
        "label": title_family,
        "status": "adjacent_pool",
        "signal_strength": 0.58,
        "supporting_run_refs": supporting_run_refs,
        "evidence_refs": evidence_refs,
        "evidence_summary": summary,
        "recommended_search_terms": [title_family],
    }


def _self_presentation_pattern_to_talent_pool(item: dict) -> dict | None:
    label = _normalize_text(item.get("label"))
    pattern = _normalize_text(item.get("pattern"))
    why_false_negative = _normalize_text(item.get("why_it_causes_false_negatives"))
    if not (label and pattern):
        return None
    supporting_run_refs = [
        ref for ref in item.get("supporting_run_refs", []) if _normalize_text(ref)
    ]
    evidence_refs = [
        ref for ref in item.get("evidence_refs", []) if _normalize_text(ref)
    ]
    summary = pattern
    if why_false_negative:
        summary = f"{summary} {why_false_negative}"
    return {
        "pool_key": _normalize_text(item.get("pattern_key")) or _slugify(label),
        "label": label,
        "status": "adjacent_pool",
        "signal_strength": 0.52,
        "supporting_run_refs": supporting_run_refs,
        "evidence_refs": evidence_refs,
        "evidence_summary": summary,
        "recommended_search_terms": [label],
    }


def _finding_to_employer_signal(item: dict) -> dict | None:
    if item.get("kind") != "employer_cluster":
        return None
    label = _normalize_text(item.get("label"))
    if not label:
        return None
    evidence_refs = [
        ref for ref in item.get("evidence_refs", []) if _normalize_text(ref)
    ]
    supporting_run_refs = [
        ref
        for ref in item.get("supporting_run_refs", [])
        if _normalize_text(ref)
    ]
    return {
        "cluster_key": _slugify(label),
        "label": label,
        "status": "positive",
        "supporting_employers": [label],
        "supporting_run_refs": supporting_run_refs,
        "evidence_refs": evidence_refs,
        "evidence_summary": _normalize_text(item.get("summary"))
        or _normalize_text(item.get("why_it_matters")),
        "confidence": round(float(item.get("confidence", 0.6) or 0.6), 2),
    }


def _implication_to_brief_recommendation(item: dict) -> dict | None:
    category = _normalize_text(item.get("category"))
    recommendation = _normalize_text(item.get("recommendation"))
    rationale = _normalize_text(item.get("rationale"))
    if not (category and recommendation and rationale):
        return None
    target_field = _normalize_text(item.get("brief_target_field"))
    if not target_field:
        target_field = {
            "add_title_family": "additional_search_terms",
            "add_employer_target": "employer_signal_rules",
            "probe_adjacent_pool": "search_priorities",
            "relax_boolean": "instructions",
            "validate_hypothesis": "instructions",
            "instrumentation_followup": "notes",
        }.get(category, "instructions")
    suggested_values = [
        value for value in item.get("suggested_values", []) if _normalize_text(value)
    ]
    proposal = ", ".join(suggested_values) if suggested_values else recommendation
    retrieval_update = _implication_to_retrieval_update(item, target_field=target_field)
    recommendation_record = {
        "recommendation_id": _normalize_text(item.get("implication_id"))
        or _slugify(f"{category}-{proposal}"),
        "target_field": target_field,
        "proposal": proposal,
        "reason": rationale,
        "supporting_run_refs": [
            ref
            for ref in item.get("supporting_run_refs", [])
            if _normalize_text(ref)
        ],
        "evidence_refs": [
            ref for ref in item.get("evidence_refs", []) if _normalize_text(ref)
        ],
        "confidence": round(
            0.55
            + {
                "high": 0.25,
                "medium": 0.15,
                "low": 0.05,
            }.get(_normalize_text(item.get("priority")).lower(), 0.15),
            2,
        ),
    }
    if retrieval_update:
        recommendation_record["retrieval_update"] = retrieval_update
    return recommendation_record


def _implication_to_retrieval_update(
    item: dict,
    *,
    target_field: str,
) -> dict[str, Any] | None:
    category = _normalize_text(item.get("category"))
    suggested_values = [
        value for value in item.get("suggested_values", []) if _normalize_text(value)
    ]
    if not category:
        return None
    layer_name = {
        "add_title_family": "entry_signals",
        "probe_adjacent_pool": "capability_proxies",
        "relax_boolean": "reality_filters",
        "add_employer_target": "target_employers",
    }.get(category, "")
    update_type = {
        "validate_hypothesis": "hypothesis_validation",
        "instrumentation_followup": "instrumentation_followup",
    }.get(category, "layer_update")
    record = {
        "update_type": update_type,
        "category": category,
        "target_field": target_field,
        "layer_name": layer_name,
        "suggested_values": suggested_values,
        "reason": _normalize_text(item.get("rationale")),
        "expected_effect": _normalize_text(item.get("expected_effect")),
    }
    if category == "probe_adjacent_pool":
        record["edge_case_hypothesis"] = {
            "label": _normalize_text(item.get("recommendation")),
            "hidden_cohort": _normalize_text(item.get("recommendation")),
            "why_missed": _normalize_text(item.get("rationale")),
            "validation_rule": "Promote only after repeated signal across later runs.",
            "source": "market_intel",
        }
    return record


def _build_retrieval_design_summary(
    *,
    brief: Brief,
    brief_recommendations: list[dict],
    previous_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    baseline = summarize_retrieval_design(
        retrieval_design_from_payload(
            getattr(brief, "retrieval_design", {}) or brief.raw.get("retrieval_design"),
            legacy_search_priorities=brief.search_priorities,
            legacy_additional_search_terms=brief.additional_search_terms,
            role_title=brief.role_title,
        )
    )
    updates = []
    for recommendation in brief_recommendations:
        if not isinstance(recommendation, dict):
            continue
        retrieval_update = recommendation.get("retrieval_update")
        if isinstance(retrieval_update, dict):
            updates.append(retrieval_update)
    prior_updates = []
    if isinstance(previous_summary, dict):
        prior_updates = [
            update
            for update in previous_summary.get("recommended_updates", [])
            if isinstance(update, dict)
        ]
    deduped_updates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for update in prior_updates + updates:
        key = json.dumps(update, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped_updates.append(update)
    baseline["recommended_updates"] = deduped_updates[:12]
    return baseline


def _merge_external_research_into_sections(
    draft_sections: dict[str, Any],
    external_research: ExternalResearchResult | None,
) -> dict[str, Any]:
    integrated = _sanitize_generated_sections(draft_sections)
    if not external_research:
        return integrated

    market_thesis = dict(integrated.get("market_thesis") or {})
    market_thesis.setdefault("summary", "")
    market_thesis.setdefault("supply_assessment", "unknown")
    market_thesis.setdefault("competition_assessment", "unknown")
    external_context = list(market_thesis.get("external_context", []))
    external_context.extend(external_research.market_thesis_context)
    external_context.extend(
        [
            context
            for context in (
                _finding_to_external_context(item)
                for item in external_research.market_findings
            )
            if context
        ]
    )
    market_thesis["external_context"] = sanitize_narrative_items(
        "market_thesis.external_context",
        external_context,
    )
    integrated["market_thesis"] = market_thesis

    integrated["talent_pool_intelligence"] = sanitize_narrative_items(
        "talent_pool_intelligence",
        list(integrated.get("talent_pool_intelligence", []))
        + [
            record
            for record in (
                _finding_to_talent_pool(item)
                for item in external_research.market_findings
            )
            if record
        ]
        + [
            record
            for record in (
                _edge_case_submarket_to_talent_pool(item)
                for item in external_research.edge_case_submarkets
            )
            if record
        ]
        + [
            record
            for record in (
                _title_mapping_to_talent_pool(item)
                for item in external_research.title_to_archetype_mapping
            )
            if record
        ]
        + [
            record
            for record in (
                _self_presentation_pattern_to_talent_pool(item)
                for item in external_research.self_presentation_patterns
            )
            if record
        ],
    )
    integrated["employer_signal_intelligence"] = sanitize_narrative_items(
        "employer_signal_intelligence",
        list(integrated.get("employer_signal_intelligence", []))
        + [
            record
            for record in (
                _finding_to_employer_signal(item)
                for item in external_research.market_findings
            )
            if record
        ],
    )
    integrated["brief_recommendations"] = sanitize_narrative_items(
        "brief_recommendations",
        list(integrated.get("brief_recommendations", []))
        + [
            record
            for record in (
                _implication_to_brief_recommendation(item)
                for item in external_research.sourcing_implications
            )
            if record
        ]
        + [
            record
            for record in (
                _implication_to_brief_recommendation(item)
                for item in external_research.edge_case_sourcing_implications
            )
            if record
        ],
    )
    integrated["open_questions"] = sanitize_narrative_items(
        "open_questions",
        list(integrated.get("open_questions", []))
        + list(external_research.open_questions),
    )
    integrated["open_questions"] = sanitize_narrative_items(
        "open_questions",
        list(integrated.get("open_questions", []))
        + list(external_research.edge_case_open_questions),
    )
    market_thesis["external_context"] = sanitize_narrative_items(
        "market_thesis.external_context",
        list(market_thesis.get("external_context", []))
        + [
            context
            for context in (
                _edge_case_submarket_to_external_context(item)
                for item in external_research.edge_case_submarkets
            )
            if context
        ]
        + [
            context
            for context in (
                _false_negative_hypothesis_to_external_context(item)
                for item in external_research.false_negative_hypotheses
            )
            if context
        ],
    )
    integrated["market_thesis"] = market_thesis
    return integrated


def _build_artifact(
    *,
    brief: Brief,
    market_identity: MarketIdentity,
    deterministic_summary: dict,
    evidence_batches: list[MarketEvidenceBatch],
    previous_artifact: MarketIntelArtifact | None,
    generated_sections: dict[str, Any],
    preserve_previous_narrative: bool,
    external_result: ExternalResearchResult | None,
    section_generation_metadata: dict[str, dict],
    delta_since_last_run: dict,
) -> MarketIntelArtifact:
    previous = previous_artifact.to_dict() if previous_artifact else {}
    sanitized_generated = _sanitize_generated_sections(generated_sections)

    freshness = dict(deterministic_summary["freshness"])
    previous_external_sources = list(
        (previous.get("evidence_index", {}) or {}).get("external_sources", []) or []
    )
    external_sources = list(previous_external_sources)
    if external_result:
        external_sources = _merge_external_sources(
            previous_sources=previous_external_sources,
            current_sources=external_result.sources,
        )
        freshness["external_research_through"] = _max_timestamp(
            [source.get("retrieved_at", "") for source in external_result.sources]
        )
    elif previous_artifact:
        freshness["external_research_through"] = (
            previous_artifact.freshness.get("external_research_through", "")
        )

    lane_entries = _merge_lane_entries(
        deterministic_lanes=deterministic_summary["lane_intelligence"],
        generated_lanes=sanitized_generated.get("lane_intelligence", []),
        previous_lanes=previous.get("lane_intelligence", []),
    )

    market_thesis = _merge_market_thesis(
        current=sanitized_generated.get("market_thesis", {}),
        previous=previous.get("market_thesis", {}),
        preserve_previous=preserve_previous_narrative,
    )
    if (
        not external_result
        and previous.get("market_thesis", {})
        and not sanitize_narrative_items(
            "market_thesis.external_context",
            market_thesis.get("external_context", []),
        )
    ):
        market_thesis["external_context"] = previous.get("market_thesis", {}).get(
            "external_context",
            [],
        )
    merged_brief_recommendations = _merge_narrative_collection(
        key_field="recommendation_id",
        current=sanitized_generated.get("brief_recommendations", []),
        previous=previous.get("brief_recommendations", []),
        preserve_previous=preserve_previous_narrative,
    )

    data = {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": int(previous.get("artifact_version", 0)) + 1,
        "market_identity": market_identity.to_dict(),
        "freshness": freshness,
        "evidence_index": {
            "runs": deterministic_summary["evidence_index"]["runs"],
            "external_sources": external_sources,
        },
        "aggregate_metrics": deterministic_summary["aggregate_metrics"],
        "channel_summaries": deterministic_summary["channel_summaries"],
        "lane_intelligence": lane_entries,
        "talent_pool_intelligence": _merge_narrative_collection(
            key_field="pool_key",
            current=sanitized_generated.get("talent_pool_intelligence", []),
            previous=previous.get("talent_pool_intelligence", []),
            preserve_previous=preserve_previous_narrative,
        ),
        "noise_patterns": _merge_narrative_collection(
            key_field="pattern_key",
            current=sanitized_generated.get("noise_patterns", []),
            previous=previous.get("noise_patterns", []),
            preserve_previous=preserve_previous_narrative,
        ),
        "employer_signal_intelligence": _merge_narrative_collection(
            key_field="cluster_key",
            current=sanitized_generated.get("employer_signal_intelligence", []),
            previous=previous.get("employer_signal_intelligence", []),
            preserve_previous=preserve_previous_narrative,
        ),
        "candidate_signal_summary": deterministic_summary["candidate_signal_summary"],
        "market_thesis": market_thesis,
        "brief_recommendations": merged_brief_recommendations,
        "open_questions": _merge_narrative_collection(
            key_field="question",
            current=sanitized_generated.get("open_questions", []),
            previous=previous.get("open_questions", []),
            preserve_previous=preserve_previous_narrative,
        ),
        "retrieval_design_summary": _build_retrieval_design_summary(
            brief=brief,
            brief_recommendations=merged_brief_recommendations,
            previous_summary=previous.get("retrieval_design_summary", {}),
        ),
        "section_generation_metadata": _deterministic_section_generation_metadata(
            deterministic_summary=deterministic_summary,
            evidence_batches=evidence_batches,
            critic_metadata=section_generation_metadata,
        ),
        "delta_since_last_run": dict(delta_since_last_run or {}),
    }
    return MarketIntelArtifact.from_dict(data)


def _merge_lane_entries(
    *,
    deterministic_lanes: list[dict],
    generated_lanes: list[dict],
    previous_lanes: list[dict],
) -> list[dict]:
    generated_by_key = {
        lane.get("lane_key"): lane
        for lane in generated_lanes
        if isinstance(lane, dict)
    }
    previous_by_key = {
        lane.get("lane_key"): lane
        for lane in previous_lanes
        if isinstance(lane, dict)
    }
    merged: list[dict] = []
    for lane in deterministic_lanes:
        lane_key = lane["lane_key"]
        previous = previous_by_key.get(lane_key, {})
        generated = generated_by_key.get(lane_key, {})
        merged_lane = dict(lane)
        merged_lane["supporting_run_refs"] = sorted(
            set(previous.get("supporting_run_refs", []))
            | set(lane.get("supporting_run_refs", []))
        )
        merged_lane["why_it_works"] = _normalize_text(
            generated.get("why_it_works")
        ) or _normalize_text(previous.get("why_it_works")) or _default_lane_why(lane)
        merged_lane["recommended_action"] = _normalize_text(
            generated.get("recommended_action")
        ) or _normalize_text(previous.get("recommended_action")) or _default_lane_action(
            lane
        )
        merged_lane["confidence"] = float(
            generated.get("confidence")
            or previous.get("confidence")
            or _default_lane_confidence(lane)
        )
        merged.append(merged_lane)
    return merged


def _merge_narrative_collection(
    *,
    key_field: str,
    current: list[dict],
    previous: list[dict],
    preserve_previous: bool,
) -> list[dict]:
    merged = {
        item.get(key_field): dict(item)
        for item in previous
        if isinstance(item, dict) and item.get(key_field)
    }
    if current:
        for item in current:
            if isinstance(item, dict) and item.get(key_field):
                merged[item[key_field]] = dict(item)
    elif not preserve_previous:
        merged = {}
    return list(merged.values())


def _merge_market_thesis(
    *,
    current: dict,
    previous: dict,
    preserve_previous: bool,
) -> dict:
    if current:
        merged = dict(current)
        summary = _normalize_text(merged.get("summary"))
        if market_thesis_summary_looks_like_review(summary):
            merged["summary"] = ""
        if previous:
            previous_summary = _normalize_text(previous.get("summary"))
            if (
                not _normalize_text(merged.get("summary"))
                or market_thesis_summary_looks_like_review(merged.get("summary"))
            ) and previous_summary and not market_thesis_summary_looks_like_review(previous_summary):
                merged["summary"] = previous_summary
            if not _normalize_text(merged.get("supply_assessment")) or _normalize_text(
                merged.get("supply_assessment")
            ) == "unknown":
                merged["supply_assessment"] = previous.get(
                    "supply_assessment",
                    "unknown",
                )
            if not _normalize_text(merged.get("competition_assessment")) or _normalize_text(
                merged.get("competition_assessment")
            ) == "unknown":
                merged["competition_assessment"] = previous.get(
                    "competition_assessment",
                    "unknown",
                )
            if not sanitize_narrative_items(
                "market_thesis.external_context",
                merged.get("external_context", []),
            ):
                merged["external_context"] = previous.get("external_context", [])
        return merged
    if preserve_previous and previous:
        return previous
    return {
        "summary": "Market thesis not yet synthesized.",
        "supply_assessment": "unknown",
        "competition_assessment": "unknown",
        "external_context": [],
    }


def _default_lane_why(lane: dict) -> str:
    if lane.get("status") == "winning":
        return "This lane is repeatedly producing saved candidates."
    if lane.get("status") == "noise":
        return "This lane is producing weak signal relative to review effort."
    if lane.get("status") == "saturated":
        return "This lane is generating high overlap and appears increasingly exhausted."
    return "This lane is producing mixed results so far."


def _default_lane_action(lane: dict) -> str:
    if lane.get("status") == "winning":
        return "Keep this lane active and expand nearby variants."
    if lane.get("status") == "noise":
        return "Tighten the lane or retire it."
    if lane.get("status") == "saturated":
        return "De-prioritize this lane and look for adjacent whitespace."
    return "Keep monitoring before promoting or retiring this lane."


def _default_lane_confidence(lane: dict) -> float:
    metrics = lane.get("metrics", {})
    if lane.get("status") == "winning":
        return 0.8 if metrics.get("saves", 0) >= 3 else 0.7
    if lane.get("status") == "noise":
        return 0.72
    if lane.get("status") == "saturated":
        return 0.75
    return 0.6


def _staleness_days(value: str) -> int:
    dt = _parse_dt(value)
    if dt is None:
        return 0
    return max(0, (datetime.now(timezone.utc) - dt).days)


def _loads_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _file_timestamp(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _save_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _string_list(values: list[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = _normalize_text(value)
        if text:
            out.append(text)
    return out


def _extract_metrics_summary(
    report: dict | None,
    runtime_summary: dict,
    final_records: list[dict],
) -> dict:
    report_metrics = (report or {}).get("metrics_summary", {})
    if report_metrics:
        return {
            "run_count": int(runtime_summary.get("run_count", 1) or 1),
            "candidate_volume": int(report_metrics.get("candidates_evaluated", 0)),
            "facial_yes": int(report_metrics.get("facial_yes", 0)),
            "facial_no": int(report_metrics.get("facial_no", 0)),
            "saved": int(report_metrics.get("saved", 0)),
            "rejected": int(report_metrics.get("rejected", 0)),
        }
    saved = sum(
        1
        for record in final_records
        if _normalize_text(record.get("decision")).upper() in SAVE_DECISIONS
    )
    rejected = sum(
        1
        for record in final_records
        if _normalize_text(record.get("decision")).upper() == "REJECT"
    )
    candidate_volume = int(runtime_summary.get("candidate_volume", 0)) or len(final_records)
    return {
        "run_count": int(runtime_summary.get("run_count", 1) or 1),
        "candidate_volume": candidate_volume,
        "facial_yes": int(runtime_summary.get("facial_yes", 0)),
        "facial_no": int(runtime_summary.get("facial_no", 0)),
        "saved": int(runtime_summary.get("saved", 0)) or saved,
        "rejected": int(runtime_summary.get("rejected", 0)) or rejected,
    }


def _lane_key_from_report_lane(report_lane: dict, performance: dict[int, dict]) -> str:
    for string_id in report_lane.get("string_ids", []):
        try:
            normalized_id = int(string_id)
        except (TypeError, ValueError):
            continue
        if normalized_id in performance:
            perf = performance[normalized_id]
            return normalize_family_key(
                perf.get("family_key"),
                perf.get("name", ""),
                perf.get("notes", ""),
            )
    return _slugify(_normalize_text(report_lane.get("lane")))


# ---------------------------------------------------------------------------
# Phase E Slice E1: public reader API for the market viewer.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarketRecord:
    """Catalog row for the market viewer's list page.

    Lightweight summary derived from `freshness` + `aggregate_metrics` so
    the list payload doesn't ship the full 60-lane artifact for every
    market. The detail page calls `load_artifact()` for the heavy data.
    """

    market_key: str
    role_title: str
    role_level: str
    geography: str
    last_updated_at: str
    run_count: int
    saved_count: int
    aggregate_save_rate: float | None


_MARKET_INTEL_FILENAME = "market-intel.json"


def _markets_root(output_root: Path | None = None) -> Path:
    """Resolve the `output/market_intelligence/` directory.

    Mirrors the `_output_root` pattern but lazy-imports the canonical
    constant so callers can pass an explicit override (test fixtures,
    alternate install layouts).
    """

    if output_root is not None:
        return Path(output_root) / "market_intelligence"
    from shared.output_paths import MARKET_INTELLIGENCE_ROOT

    return MARKET_INTELLIGENCE_ROOT


def load_artifact(
    market_key: str,
    *,
    output_root: Path | None = None,
) -> MarketIntelArtifact | None:
    """Load and parse the on-disk artifact for a market.

    Returns ``None`` when the file is missing or unparseable so the
    route layer can render a graceful empty state without crashing on
    the first malformed artifact.
    """

    if not market_key:
        return None
    path = _markets_root(output_root) / market_key / _MARKET_INTEL_FILENAME
    if not path.exists():
        return None
    try:
        data = read_json(path)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return MarketIntelArtifact.from_dict(data)
    except Exception:
        return None


def list_market_records(
    *,
    output_root: Path | None = None,
) -> list[MarketRecord]:
    """Walk `output/market_intelligence/` and return one record per
    directory containing a parseable `market-intel.json`.

    Sort: most-recently-updated first (artifact_updated_at desc) so the
    list reads as "what Cloris has been studying lately." A directory
    whose artifact fails to parse is skipped silently — the catalog is
    a recruiter-facing surface and a malformed artifact is a backend
    bug, not a viewer concern.
    """

    root = _markets_root(output_root)
    if not root.exists() or not root.is_dir():
        return []

    out: list[MarketRecord] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        artifact_path = child / _MARKET_INTEL_FILENAME
        if not artifact_path.exists():
            continue
        try:
            data = read_json(artifact_path)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        # Catalog inclusion gate: skip artifacts missing the recruiter-
        # facing identity block. A bare `{"schema_version": 1}` shouldn't
        # surface as an "Unknown" row in the viewer.
        if not isinstance(data.get("market_identity"), dict):
            continue
        market_identity = data["market_identity"]
        freshness = data.get("freshness") or {}
        aggregate_metrics = data.get("aggregate_metrics") or {}
        market_key = (
            str(market_identity.get("market_key") or "").strip() or child.name
        )
        save_rate = aggregate_metrics.get("save_rate")
        try:
            save_rate_f = float(save_rate) if save_rate is not None else None
        except (TypeError, ValueError):
            save_rate_f = None
        out.append(
            MarketRecord(
                market_key=market_key,
                role_title=str(market_identity.get("role_title") or "").strip(),
                role_level=str(market_identity.get("role_level") or "").strip(),
                geography=str(market_identity.get("geography") or "").strip(),
                last_updated_at=str(
                    freshness.get("artifact_updated_at") or ""
                ).strip(),
                run_count=int(aggregate_metrics.get("run_count") or 0),
                saved_count=int(aggregate_metrics.get("saved_count") or 0),
                aggregate_save_rate=save_rate_f,
            )
        )
    out.sort(key=lambda r: r.last_updated_at, reverse=True)
    return out
