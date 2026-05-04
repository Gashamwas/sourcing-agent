"""Data schemas for the sourcing pipeline. All pipeline objects as dataclasses with JSON serialization."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
import json

from shared.reconciliation_schemas import RecruiterActivitySnapshot


# ---------------------------------------------------------------------------
# Kit string (extracted from Search Kit Library)
# ---------------------------------------------------------------------------

@dataclass
class KitString:
    id: int
    block: str  # e.g., "Post-Training & RLHF"
    subblock: str  # "Concepts", "Methods", or "Tools"
    string_type: str  # "Recall" or "Precision"
    boolean: str  # The actual Boolean parenthetical

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> KitString:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Execution plan (Opus strategy output)
# ---------------------------------------------------------------------------

@dataclass
class ExecutionPlan:
    strategy_rationale: str
    noise_predictions: list[dict] = field(default_factory=list)
    generated_strings: list[dict] = field(default_factory=list)
    retrieval_families: list[dict] = field(default_factory=list)
    coverage_gaps: list[dict] = field(default_factory=list)
    # Search architecture
    architecture: str = ""  # sniper|dragnet|titration|negative_space|company_first|title_first
    architecture_rationale: str = ""
    architecture_success_criteria: list[str] = field(default_factory=list)
    architecture_pivot_triggers: list[str] = field(default_factory=list)
    original_architecture: str = ""  # Set once at plan creation, never updated on pivot

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> ExecutionPlan:
        return cls(
            strategy_rationale=d.get("strategy_rationale", ""),
            noise_predictions=d.get("noise_predictions", []),
            generated_strings=d.get("generated_strings", []),
            retrieval_families=d.get("retrieval_families", []),
            coverage_gaps=d.get("coverage_gaps", []),
            architecture=d.get("architecture", ""),
            architecture_rationale=d.get("architecture_rationale", ""),
            architecture_success_criteria=d.get("architecture_success_criteria", []),
            architecture_pivot_triggers=d.get("architecture_pivot_triggers", []),
            original_architecture=d.get("original_architecture", ""),
        )


# ---------------------------------------------------------------------------
# Block report (per-block summary sent to Opus for adaptation)
# ---------------------------------------------------------------------------

@dataclass
class BlockReport:
    block_name: str
    strings_run: int = 0
    strings_with_saves: int = 0
    total_results: int = 0
    total_saves: int = 0
    top_performers: list[dict] = field(default_factory=list)
    zero_save_string_ids: list[int] = field(default_factory=list)
    noise_patterns_observed: list[dict] = field(default_factory=list)
    new_signals: list[str] = field(default_factory=list)
    string_details: list[dict] = field(default_factory=list)
    search_intelligence_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_summary_text(self) -> str:
        lines = [f'Batch "{self.block_name}" — {self.strings_run} strings complete.']
        lines.append(f"- {self.strings_run} strings run, {self.strings_with_saves} produced saves")
        lines.append(f"- {self.strings_run - self.strings_with_saves} strings produced zero results or all noise")
        if self.top_performers:
            top = ", ".join(
                f"String #{p['string_id']} \"{p.get('name', '')}\" ({p.get('saves', 0)} saves from {p.get('results', 0)} results)"
                for p in self.top_performers
            )
            lines.append(f"- Top performers: {top}")
        if self.zero_save_string_ids:
            lines.append(f"- Zero-save strings: {', '.join(f'#{sid}' for sid in self.zero_save_string_ids)}")
        if self.noise_patterns_observed:
            noise = ", ".join(
                f"{p['term']} → {p.get('collision', 'unknown')} ({p.get('count', '?')} occurrences)"
                for p in self.noise_patterns_observed
            )
            lines.append(f"- Noise patterns observed: {noise}")
        if self.new_signals:
            lines.append(f"- New signal observed: {', '.join(self.new_signals)}")
        if self.search_intelligence_summary:
            summary = self.search_intelligence_summary
            if summary.get("strings_with_precommit_experiments"):
                lines.append(
                    "- Pre-commit experiments: "
                    + ", ".join(f"#{sid}" for sid in summary["strings_with_precommit_experiments"])
                )
            if summary.get("strings_rescued_by_drift"):
                lines.append(
                    "- Drift rescues that recovered signal: "
                    + ", ".join(f"#{sid}" for sid in summary["strings_rescued_by_drift"])
                )
            if summary.get("proven_family_keys"):
                lines.append(
                    "- Proven families worth exploiting: "
                    + ", ".join(summary["proven_family_keys"])
                )
            if summary.get("proven_domain_lanes"):
                lines.append(
                    "- Proven lanes worth exploiting: "
                    + ", ".join(summary["proven_domain_lanes"])
                )
            if summary.get("dead_family_keys"):
                lines.append(
                    "- Dead families to demote: "
                    + ", ".join(summary["dead_family_keys"])
                )
            if summary.get("contaminated_family_keys"):
                lines.append(
                    "- Families with seniority contamination: "
                    + ", ".join(summary["contaminated_family_keys"])
                )
            if summary.get("contaminated_domain_lanes"):
                lines.append(
                    "- Lanes with seniority contamination: "
                    + ", ".join(summary["contaminated_domain_lanes"])
                )
        if self.string_details:
            lines.append("- Per-string breakdown:")
            for sd in self.string_details:
                status = f"{sd['saves']} saves" if sd['saves'] else "zero saves"
                metadata = (
                    f"family={sd.get('family_key', 'unknown')} "
                    f"novelty={sd.get('novelty_bucket', 'unknown')} "
                    f"lane={sd.get('domain_lane', 'general')}"
                )
                lines.append(
                    f"  #{sd['string_id']} [{status}, {sd['pages_reviewed']}p, {sd['result_count']} results, {metadata}]: "
                    f"{sd['boolean'][:150]}"
                )
                if "duplicates" in sd or "candidates" in sd:
                    lines.append(
                        f"    Seen: candidates={sd.get('candidates', 0)}, "
                        f"duplicates={sd.get('duplicates', 0)}, "
                        f"facial_yes={sd.get('facial_yes', 0)}, facial_no={sd.get('facial_no', 0)}"
                    )
                if sd.get('notes'):
                    lines.append(f"    Notes: {sd['notes']}")
                if sd.get('save_names'):
                    lines.append(f"    Saved: {', '.join(sd['save_names'])}")
                if sd.get('saved_profiles'):
                    saved_profiles = ", ".join(
                        f"{p.get('name', '?')} ({p.get('title', '')} @ {p.get('company', '')})"
                        for p in sd['saved_profiles'][:3]
                    )
                    lines.append(f"    Save profiles: {saved_profiles}")
                search_intelligence = sd.get("search_intelligence") or {}
                if search_intelligence:
                    clauses: list[str] = []
                    if search_intelligence.get("precommit_recovery_attempts_used"):
                        clauses.append(
                            f"precommit_recovery={search_intelligence['precommit_recovery_attempts_used']}"
                        )
                    if search_intelligence.get("drift_attempt_count"):
                        clauses.append(
                            f"drift_attempts={search_intelligence['drift_attempt_count']}"
                        )
                    if search_intelligence.get("family_signal_total") is not None:
                        clauses.append(
                            f"family_signal={search_intelligence.get('family_signal_total', 0)}"
                        )
                    if search_intelligence.get("family_saves_total") is not None:
                        clauses.append(
                            f"family_saves={search_intelligence.get('family_saves_total', 0)}"
                        )
                    best_variant = search_intelligence.get("best_variant") or {}
                    if best_variant.get("variant_id"):
                        clauses.append(
                            f"best_variant={best_variant.get('variant_kind', 'variant')}:{best_variant['variant_id']}"
                        )
                    drift_summary = search_intelligence.get("drift_rescue_summary") or {}
                    if drift_summary.get("outcome"):
                        clauses.append(f"drift_outcome={drift_summary['outcome']}")
                    if clauses:
                        lines.append(f"    Search intelligence: {', '.join(clauses)}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Adaptation response (Opus mid-run adjustments)
# ---------------------------------------------------------------------------

@dataclass
class AdaptationResponse:
    new_strings: list[dict] = field(default_factory=list)
    new_retrieval_families: list[dict] = field(default_factory=list)
    hypothesis_updates: list[dict] = field(default_factory=list)
    skip_remaining: list[dict] = field(default_factory=list)
    reorder: list[dict] = field(default_factory=list)
    noise_updates: list[dict] = field(default_factory=list)
    # Architecture pivot (optional — empty = no pivot)
    pivot_to_architecture: str = ""
    pivot_rationale: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> AdaptationResponse:
        return cls(
            new_strings=d.get("new_strings", []),
            new_retrieval_families=d.get("new_retrieval_families", []),
            hypothesis_updates=d.get("hypothesis_updates", []),
            skip_remaining=d.get("skip_remaining", []),
            reorder=d.get("reorder", []),
            noise_updates=d.get("noise_updates", []),
            pivot_to_architecture=d.get("pivot_to_architecture", ""),
            pivot_rationale=d.get("pivot_rationale", ""),
        )


# ---------------------------------------------------------------------------
# Stage 1 output: extracted from list view by cheap model
# ---------------------------------------------------------------------------

@dataclass
class CandidateSnippet:
    name: str
    headline: str
    current_title: str
    current_company: str
    location: str
    education_snippet: str
    profile_url: str
    source_string_id: int
    source_string_name: str
    page: int
    result_rank: int
    experience_entries: list[str] = field(default_factory=list)
    card_index: int = -1  # DOM position of <li> in ol.profile-list; -1 = unknown
    already_saved: bool = False  # True if card shows "Change stage" instead of "Save to pipeline"
    recruiter_activity: RecruiterActivitySnapshot | None = None
    novelty_pressure: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        if self.recruiter_activity is None:
            payload["recruiter_activity"] = None
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> CandidateSnippet:
        payload = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        payload["recruiter_activity"] = RecruiterActivitySnapshot.from_dict(
            payload.get("recruiter_activity")
        )
        return cls(**payload)


# ---------------------------------------------------------------------------
# Stage 3 output: extracted from full profile by cheap model
# ---------------------------------------------------------------------------

@dataclass
class Experience:
    title: str
    company: str
    location: str = ""
    start: str = ""
    end: str = ""
    summary_bullets: list[str] = field(default_factory=list)


@dataclass
class Education:
    degree: str
    school: str
    field: str = ""
    start: str = ""
    end: str = ""


@dataclass
class CandidateProfileSummary:
    name: str
    profile_url: str
    headline: str
    experiences: list[Experience] = field(default_factory=list)
    education: list[Education] = field(default_factory=list)
    skills_snippet: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> CandidateProfileSummary:
        exps = [Experience(**e) for e in d.get("experiences", [])]
        edus = [Education(**e) for e in d.get("education", [])]
        return cls(
            name=d["name"],
            profile_url=d["profile_url"],
            headline=d.get("headline", ""),
            experiences=exps,
            education=edus,
            skills_snippet=d.get("skills_snippet", []),
        )


# ---------------------------------------------------------------------------
# Opus judgment output (used for both facial and full stages)
# ---------------------------------------------------------------------------

@dataclass
class OpusDecision:
    stage: str  # "facial" | "full"
    decision: str  # "FACIAL_YES" | "FACIAL_NO" | "SAVE" | "REJECT"
    path: str  # "pedigree" | "direct_experience" | "none"
    confidence: float
    rationale: str
    candidate_name: str
    profile_url: str
    post_save_modifier: str = "NONE"  # V4: which modifier fired, if any
    novelty_value: str = ""
    value_rationale: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> OpusDecision:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Glance assessment (page-level pre-filter)
# ---------------------------------------------------------------------------

@dataclass
class GlanceResult:
    action: str        # "proceed" | "reformulate"
    summary: str       # Human-readable page description for _page_adapt
    confidence: float  # 0.0 to 1.0
    signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Search string tracking
# ---------------------------------------------------------------------------

@dataclass
class SearchString:
    id: int
    name: str
    boolean: str
    status: str = "queued"  # "queued" | "in_progress" | "done" | "skipped"
    result_count: int = 0
    pages_reviewed: int = 0
    saves: list[str] = field(default_factory=list)  # candidate names
    notes: str = ""
    block: str = ""  # Kit block name, e.g. "Post-Training & RLHF"
    subblock: str = ""  # "Concepts", "Methods", or "Tools"
    string_type: str = ""  # "Recall" or "Precision"
    # Facial triage stats (persisted for block-level aggregate computation)
    facial_yes_count: int = 0
    facial_no_count: int = 0
    # C2 (slice 15): own bucket distinct from YES. Stays 0 today because
    # slices 13/14 alias FACIAL_BORDERLINE -> FACIAL_YES at the persistence
    # boundary; this counter only ticks if a future code path persists raw
    # FACIAL_BORDERLINE without the alias.
    facial_borderline_count: int = 0
    candidates_count: int = 0
    duplicates_count: int = 0
    # Two-phase adaptation fields
    phase: str = "scout"  # "scout" | "paginate"
    original_boolean: str = ""  # The original Boolean before any refinements
    refinement_stack: list[str] = field(default_factory=list)  # Stack of applied Booleans (push=narrow, pop=broaden)
    # Strategy metadata for cross-run memory and novelty accounting
    family_key: str = ""
    novelty_bucket: str = ""
    domain_lane: str = ""
    seniority_risk: str = ""
    title_bucket_risk: str = ""
    opening_eligible: Optional[bool] = None
    retrieval_recipe: dict = field(default_factory=dict)
    retrieval_hypothesis_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> SearchString:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Progress checkpoint
# ---------------------------------------------------------------------------

@dataclass
class Progress:
    brief_name: str
    strings: list[SearchString] = field(default_factory=list)
    candidates_saved: int = 0
    candidates_rejected: int = 0
    current_string_id: Optional[int] = None
    current_page: int = 0
    pending_block_name: str = ""
    pending_block_string_ids: list[int] = field(default_factory=list)
    pending_block_ready: bool = False
    pivot_count: int = 0  # Architecture pivots used this run

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> Progress:
        strings = [SearchString.from_dict(s) for s in d.get("strings", [])]
        return cls(
            brief_name=d["brief_name"],
            strings=strings,
            candidates_saved=d.get("candidates_saved", 0),
            candidates_rejected=d.get("candidates_rejected", 0),
            current_string_id=d.get("current_string_id"),
            current_page=d.get("current_page", 0),
            pending_block_name=d.get("pending_block_name", ""),
            pending_block_string_ids=d.get("pending_block_string_ids", []),
            pending_block_ready=d.get("pending_block_ready", False),
            pivot_count=d.get("pivot_count", 0),
        )

    @classmethod
    def from_file(cls, path: str) -> Progress:
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            f.write(self.to_json())


# ---------------------------------------------------------------------------
# External candidate evidence (Perplexity-augmented context for full eval)
# ---------------------------------------------------------------------------
# Slice 1 of the perplexity-evidence-augmentation feature: types only, with no
# callers. Strict separation between sourced facts, model inferences, and
# unresolved ambiguities is the durable contract — it must survive normalization
# all the way to the final judge.

@dataclass
class EvidenceRef:
    """A single citation backing an external fact or inference."""

    url: str
    title: str = ""
    source_quality: str = "unknown"  # "high" | "medium" | "low" | "unknown"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> EvidenceRef:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ExternalFactBlock:
    """A topic-grouped block of sourced facts with citations."""

    topic: str
    facts: list[str] = field(default_factory=list)
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    source_quality: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ExternalFactBlock:
        refs = [EvidenceRef.from_dict(r) for r in d.get("evidence_refs", [])]
        return cls(
            topic=d.get("topic", ""),
            facts=list(d.get("facts", [])),
            evidence_refs=refs,
            source_quality=d.get("source_quality", "unknown"),
        )


@dataclass
class ExternalInference:
    """Model-synthesized claim derived from sourced facts. Kept distinct from facts."""

    claim: str
    basis_refs: list[EvidenceRef] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ExternalInference:
        refs = [EvidenceRef.from_dict(r) for r in d.get("basis_refs", [])]
        return cls(
            claim=d.get("claim", ""),
            basis_refs=refs,
            confidence=float(d.get("confidence", 0.0) or 0.0),
        )


@dataclass
class ExternalCandidateEvidence:
    """Normalized public-web evidence layer used to enrich first-party profile evidence."""

    trigger_reason: str
    identity_confidence: float
    profile_facts_used_for_matching: list[str] = field(default_factory=list)
    external_fact_blocks: list[ExternalFactBlock] = field(default_factory=list)
    external_inferences: list[ExternalInference] = field(default_factory=list)
    unresolved_ambiguities: list[str] = field(default_factory=list)
    do_not_use_for_judgment: list[str] = field(default_factory=list)
    raw_provider_model: str = ""
    normalizer_model: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ExternalCandidateEvidence:
        return cls(
            trigger_reason=d.get("trigger_reason", ""),
            identity_confidence=float(d.get("identity_confidence", 0.0) or 0.0),
            profile_facts_used_for_matching=list(d.get("profile_facts_used_for_matching", [])),
            external_fact_blocks=[
                ExternalFactBlock.from_dict(b)
                for b in d.get("external_fact_blocks", [])
            ],
            external_inferences=[
                ExternalInference.from_dict(i)
                for i in d.get("external_inferences", [])
            ],
            unresolved_ambiguities=list(d.get("unresolved_ambiguities", [])),
            do_not_use_for_judgment=list(d.get("do_not_use_for_judgment", [])),
            raw_provider_model=d.get("raw_provider_model", ""),
            normalizer_model=d.get("normalizer_model", ""),
        )


@dataclass
class ExternalEvidenceFailure:
    """Typed failure result from the external evidence pipeline.

    This is *not* an exception. The provider and normalizer return it directly so
    that callers can fall back to the baseline path without unwinding the stack
    or coupling external-evidence quota errors to LinkedIn run-pause logic.
    """

    reason: str  # see allowed values in the slice 1 spec
    detail: str = ""
    provider: str = ""
    http_status: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ExternalEvidenceFailure:
        status = d.get("http_status")
        return cls(
            reason=d.get("reason", "unknown"),
            detail=d.get("detail", ""),
            provider=d.get("provider", ""),
            http_status=int(status) if isinstance(status, int) else None,
        )


@dataclass
class TriggerDecision:
    """Output of the external-evidence trigger gate."""

    should_run: bool
    reason: str
    skip_reason: str = ""
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> TriggerDecision:
        return cls(
            should_run=bool(d.get("should_run", False)),
            reason=d.get("reason", ""),
            skip_reason=d.get("skip_reason", ""),
            signals=dict(d.get("signals", {})),
        )
