"""Runtime-backed LinkedIn search-intelligence state and helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from shared.schemas import SearchString


def result_window_for_count(result_count: int) -> tuple[int, int] | None:
    """Return the target result window for a noisy result set."""
    if result_count > 5000:
        return (200, 1200)
    if result_count >= 1500:
        return (150, 800)
    if result_count >= 500:
        return (75, 400)
    return None


@dataclass
class LinkedInStructuredFilters:
    titles: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    assessments: list[str] = field(default_factory=list)
    sidebar_filters: dict[str, Any] = field(default_factory=dict)
    advanced_filters: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not any(
            (
                self.titles,
                self.companies,
                self.skills,
                self.assessments,
                self.sidebar_filters,
                self.advanced_filters,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "titles": list(self.titles),
            "companies": list(self.companies),
            "skills": list(self.skills),
            "assessments": list(self.assessments),
            "sidebar_filters": dict(self.sidebar_filters),
            "advanced_filters": dict(self.advanced_filters),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "LinkedInStructuredFilters":
        payload = payload or {}
        return cls(
            titles=list(payload.get("titles", [])),
            companies=list(payload.get("companies", [])),
            skills=list(payload.get("skills", [])),
            assessments=list(payload.get("assessments", [])),
            sidebar_filters=dict(payload.get("sidebar_filters", {})),
            advanced_filters=dict(payload.get("advanced_filters", {})),
        )


@dataclass
class LinkedInSearchIntent:
    root_boolean: str
    family_key: str = ""
    novelty_bucket: str = ""
    domain_lane: str = ""
    retrieval_recipe: dict[str, Any] = field(default_factory=dict)
    applied_hypothesis_ids: list[str] = field(default_factory=list)
    structured_filters: LinkedInStructuredFilters = field(default_factory=LinkedInStructuredFilters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_boolean": self.root_boolean,
            "family_key": self.family_key,
            "novelty_bucket": self.novelty_bucket,
            "domain_lane": self.domain_lane,
            "retrieval_recipe": dict(self.retrieval_recipe),
            "applied_hypothesis_ids": list(self.applied_hypothesis_ids),
            "structured_filters": self.structured_filters.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "LinkedInSearchIntent":
        payload = payload or {}
        return cls(
            root_boolean=payload.get("root_boolean", ""),
            family_key=payload.get("family_key", ""),
            novelty_bucket=payload.get("novelty_bucket", ""),
            domain_lane=payload.get("domain_lane", ""),
            retrieval_recipe=dict(payload.get("retrieval_recipe", {})),
            applied_hypothesis_ids=list(payload.get("applied_hypothesis_ids", [])),
            structured_filters=LinkedInStructuredFilters.from_dict(payload.get("structured_filters")),
        )


@dataclass
class LinkedInPageInsights:
    page: int
    result_count: int
    result_window: str
    title_clusters: list[dict[str, Any]] = field(default_factory=list)
    company_clusters: list[dict[str, Any]] = field(default_factory=list)
    signal_anchors: list[str] = field(default_factory=list)
    noise_anchors: list[str] = field(default_factory=list)
    dominant_non_fit_patterns: list[str] = field(default_factory=list)
    glance_action: str = ""
    glance_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "result_count": self.result_count,
            "result_window": self.result_window,
            "title_clusters": list(self.title_clusters),
            "company_clusters": list(self.company_clusters),
            "signal_anchors": list(self.signal_anchors),
            "noise_anchors": list(self.noise_anchors),
            "dominant_non_fit_patterns": list(self.dominant_non_fit_patterns),
            "glance_action": self.glance_action,
            "glance_summary": self.glance_summary,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "LinkedInPageInsights | None":
        if not payload:
            return None
        return cls(
            page=int(payload.get("page", 0)),
            result_count=int(payload.get("result_count", 0)),
            result_window=str(payload.get("result_window", "")),
            title_clusters=list(payload.get("title_clusters", [])),
            company_clusters=list(payload.get("company_clusters", [])),
            signal_anchors=list(payload.get("signal_anchors", [])),
            noise_anchors=list(payload.get("noise_anchors", [])),
            dominant_non_fit_patterns=list(payload.get("dominant_non_fit_patterns", [])),
            glance_action=str(payload.get("glance_action", "")),
            glance_summary=str(payload.get("glance_summary", "")),
        )


@dataclass
class LinkedInVariantSnapshot:
    page_start: int
    page_end: int
    result_count: int
    result_window: str
    title_clusters: list[dict[str, Any]] = field(default_factory=list)
    company_clusters: list[dict[str, Any]] = field(default_factory=list)
    signal_anchors: list[str] = field(default_factory=list)
    noise_anchors: list[str] = field(default_factory=list)
    dominant_non_fit_patterns: list[str] = field(default_factory=list)
    signal_weight: float = 0.0
    noise_weight: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_start": self.page_start,
            "page_end": self.page_end,
            "result_count": self.result_count,
            "result_window": self.result_window,
            "title_clusters": list(self.title_clusters),
            "company_clusters": list(self.company_clusters),
            "signal_anchors": list(self.signal_anchors),
            "noise_anchors": list(self.noise_anchors),
            "dominant_non_fit_patterns": list(self.dominant_non_fit_patterns),
            "signal_weight": self.signal_weight,
            "noise_weight": self.noise_weight,
        }

    @classmethod
    def from_page(
        cls,
        *,
        page_num: int,
        result_count: int,
        page_insights: LinkedInPageInsights,
        page_stats: dict[str, int],
    ) -> "LinkedInVariantSnapshot":
        signal_weight = float(
            page_stats.get("saves", 0) * 3
            + page_stats.get("facial_yes", 0)
            + page_stats.get("rejects", 0)
        )
        noise_weight = float(page_stats.get("facial_no", 0))
        return cls(
            page_start=page_num,
            page_end=page_num,
            result_count=result_count,
            result_window=page_insights.result_window,
            title_clusters=list(page_insights.title_clusters),
            company_clusters=list(page_insights.company_clusters),
            signal_anchors=list(page_insights.signal_anchors),
            noise_anchors=list(page_insights.noise_anchors),
            dominant_non_fit_patterns=list(page_insights.dominant_non_fit_patterns),
            signal_weight=signal_weight,
            noise_weight=noise_weight,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "LinkedInVariantSnapshot | None":
        if not payload:
            return None
        return cls(
            page_start=int(payload.get("page_start", 0)),
            page_end=int(payload.get("page_end", 0)),
            result_count=int(payload.get("result_count", 0)),
            result_window=str(payload.get("result_window", "")),
            title_clusters=list(payload.get("title_clusters", [])),
            company_clusters=list(payload.get("company_clusters", [])),
            signal_anchors=list(payload.get("signal_anchors", [])),
            noise_anchors=list(payload.get("noise_anchors", [])),
            dominant_non_fit_patterns=list(payload.get("dominant_non_fit_patterns", [])),
            signal_weight=float(payload.get("signal_weight", 0.0)),
            noise_weight=float(payload.get("noise_weight", 0.0)),
        )


@dataclass
class LinkedInDriftAssessment:
    decision: str
    rationale: str
    eligible: bool
    overfit_risk: str = ""
    keyword_hypothesis: str = ""
    future_filter_hypothesis: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "rationale": self.rationale,
            "eligible": self.eligible,
            "overfit_risk": self.overfit_risk,
            "keyword_hypothesis": self.keyword_hypothesis,
            "future_filter_hypothesis": self.future_filter_hypothesis,
        }


@dataclass
class LinkedInSearchVariant:
    variant_id: str
    parent_variant_id: str | None
    root_string_id: int
    boolean: str
    variant_kind: str = "original"
    hypothesis: str = ""
    target_result_min: int | None = None
    target_result_max: int | None = None
    status: str = "planned"
    experiment_round: int = 0
    structured_filters: LinkedInStructuredFilters = field(default_factory=LinkedInStructuredFilters)
    result_count: int = 0
    pages_reviewed: int = 0
    candidates: int = 0
    duplicates: int = 0
    saves: int = 0
    rejects: int = 0
    facial_yes: int = 0
    facial_no: int = 0
    last_page_insights: LinkedInPageInsights | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "parent_variant_id": self.parent_variant_id,
            "root_string_id": self.root_string_id,
            "boolean": self.boolean,
            "variant_kind": self.variant_kind,
            "hypothesis": self.hypothesis,
            "target_result_min": self.target_result_min,
            "target_result_max": self.target_result_max,
            "status": self.status,
            "experiment_round": self.experiment_round,
            "structured_filters": self.structured_filters.to_dict(),
            "result_count": self.result_count,
            "pages_reviewed": self.pages_reviewed,
            "candidates": self.candidates,
            "duplicates": self.duplicates,
            "saves": self.saves,
            "rejects": self.rejects,
            "facial_yes": self.facial_yes,
            "facial_no": self.facial_no,
            "last_page_insights": self.last_page_insights.to_dict() if self.last_page_insights else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LinkedInSearchVariant":
        return cls(
            variant_id=str(payload.get("variant_id", "root")),
            parent_variant_id=payload.get("parent_variant_id"),
            root_string_id=int(payload.get("root_string_id", 0)),
            boolean=str(payload.get("boolean", "")),
            variant_kind=str(payload.get("variant_kind", "original")),
            hypothesis=str(payload.get("hypothesis", "")),
            target_result_min=payload.get("target_result_min"),
            target_result_max=payload.get("target_result_max"),
            status=str(payload.get("status", "planned")),
            experiment_round=int(payload.get("experiment_round", 0)),
            structured_filters=LinkedInStructuredFilters.from_dict(payload.get("structured_filters")),
            result_count=int(payload.get("result_count", 0)),
            pages_reviewed=int(payload.get("pages_reviewed", 0)),
            candidates=int(payload.get("candidates", 0)),
            duplicates=int(payload.get("duplicates", 0)),
            saves=int(payload.get("saves", 0)),
            rejects=int(payload.get("rejects", 0)),
            facial_yes=int(payload.get("facial_yes", 0)),
            facial_no=int(payload.get("facial_no", 0)),
            last_page_insights=LinkedInPageInsights.from_dict(payload.get("last_page_insights")),
        )

    def within_target_window(self) -> bool:
        if self.result_count <= 0 or self.target_result_min is None or self.target_result_max is None:
            return False
        return self.target_result_min <= self.result_count <= self.target_result_max

    def score(self) -> float:
        score = float(self.saves * 10 + self.facial_yes * 4 - self.facial_no)
        if self.within_target_window():
            score += 5.0
        elif self.result_count > 0 and self.target_result_min is not None and self.target_result_max is not None:
            midpoint = (self.target_result_min + self.target_result_max) / 2
            distance = abs(self.result_count - midpoint) / max(midpoint, 1)
            score += max(0.0, 3.0 - distance * 3.0)
        return score


@dataclass
class LinkedInExperimentState:
    root_string_id: int
    intent: LinkedInSearchIntent
    mode: str = "recon"
    active_variant_id: str = "root"
    committed_variant_id: str | None = None
    planned_variant_ids: list[str] = field(default_factory=list)
    experiment_round: int = 0
    mutations_used: int = 0
    consecutive_mutations: int = 0
    pages_since_last_mutation: int = 0
    executed_sibling_count: int = 0
    family_pages_reviewed_total: int = 0
    family_candidates_total: int = 0
    family_duplicates_total: int = 0
    family_signal_total: int = 0
    family_saves_total: int = 0
    precommit_recovery_attempts_used: int = 0
    committed_pages_reviewed: int = 0
    committed_zero_signal_streak: int = 0
    early_signal_snapshot: LinkedInVariantSnapshot | None = None
    recent_noise_snapshot: LinkedInVariantSnapshot | None = None
    drift_attempt_count: int = 0
    pending_drift_variant_id: str | None = None
    pending_drift_parent_variant_id: str | None = None
    pending_drift_started_at: str = ""
    last_drift_refinement_summary: dict[str, Any] = field(default_factory=dict)
    variants: dict[str, LinkedInSearchVariant] = field(default_factory=dict)
    last_page_insights: LinkedInPageInsights | None = None

    def __post_init__(self) -> None:
        if "root" not in self.variants:
            self.variants["root"] = LinkedInSearchVariant(
                variant_id="root",
                parent_variant_id=None,
                root_string_id=self.root_string_id,
                boolean=self.intent.root_boolean,
                variant_kind="original",
                status="active",
                experiment_round=0,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_string_id": self.root_string_id,
            "intent": self.intent.to_dict(),
            "mode": self.mode,
            "active_variant_id": self.active_variant_id,
            "committed_variant_id": self.committed_variant_id,
            "planned_variant_ids": list(self.planned_variant_ids),
            "experiment_round": self.experiment_round,
            "mutations_used": self.mutations_used,
            "consecutive_mutations": self.consecutive_mutations,
            "pages_since_last_mutation": self.pages_since_last_mutation,
            "executed_sibling_count": self.executed_sibling_count,
            "family_pages_reviewed_total": self.family_pages_reviewed_total,
            "family_candidates_total": self.family_candidates_total,
            "family_duplicates_total": self.family_duplicates_total,
            "family_signal_total": self.family_signal_total,
            "family_saves_total": self.family_saves_total,
            "precommit_recovery_attempts_used": self.precommit_recovery_attempts_used,
            "committed_pages_reviewed": self.committed_pages_reviewed,
            "committed_zero_signal_streak": self.committed_zero_signal_streak,
            "early_signal_snapshot": self.early_signal_snapshot.to_dict() if self.early_signal_snapshot else None,
            "recent_noise_snapshot": self.recent_noise_snapshot.to_dict() if self.recent_noise_snapshot else None,
            "drift_attempt_count": self.drift_attempt_count,
            "pending_drift_variant_id": self.pending_drift_variant_id,
            "pending_drift_parent_variant_id": self.pending_drift_parent_variant_id,
            "pending_drift_started_at": self.pending_drift_started_at,
            "last_drift_refinement_summary": dict(self.last_drift_refinement_summary),
            "variants": {key: variant.to_dict() for key, variant in self.variants.items()},
            "last_page_insights": self.last_page_insights.to_dict() if self.last_page_insights else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "LinkedInExperimentState | None":
        if not payload:
            return None
        variants = {
            key: LinkedInSearchVariant.from_dict(value)
            for key, value in dict(payload.get("variants", {})).items()
        }
        state = cls(
            root_string_id=int(payload.get("root_string_id", 0)),
            intent=LinkedInSearchIntent.from_dict(payload.get("intent")),
            mode=str(payload.get("mode", "recon")),
            active_variant_id=str(payload.get("active_variant_id", "root")),
            committed_variant_id=payload.get("committed_variant_id"),
            planned_variant_ids=list(payload.get("planned_variant_ids", [])),
            experiment_round=int(payload.get("experiment_round", 0)),
            mutations_used=int(payload.get("mutations_used", 0)),
            consecutive_mutations=int(payload.get("consecutive_mutations", 0)),
            pages_since_last_mutation=int(payload.get("pages_since_last_mutation", 0)),
            executed_sibling_count=int(payload.get("executed_sibling_count", 0)),
            family_pages_reviewed_total=int(payload.get("family_pages_reviewed_total", 0)),
            family_candidates_total=int(payload.get("family_candidates_total", 0)),
            family_duplicates_total=int(payload.get("family_duplicates_total", 0)),
            family_signal_total=int(payload.get("family_signal_total", 0)),
            family_saves_total=int(payload.get("family_saves_total", 0)),
            precommit_recovery_attempts_used=int(payload.get("precommit_recovery_attempts_used", 0)),
            committed_pages_reviewed=int(payload.get("committed_pages_reviewed", 0)),
            committed_zero_signal_streak=int(payload.get("committed_zero_signal_streak", 0)),
            early_signal_snapshot=LinkedInVariantSnapshot.from_dict(payload.get("early_signal_snapshot")),
            recent_noise_snapshot=LinkedInVariantSnapshot.from_dict(payload.get("recent_noise_snapshot")),
            drift_attempt_count=int(payload.get("drift_attempt_count", 0)),
            pending_drift_variant_id=payload.get("pending_drift_variant_id"),
            pending_drift_parent_variant_id=payload.get("pending_drift_parent_variant_id"),
            pending_drift_started_at=str(payload.get("pending_drift_started_at", "")),
            last_drift_refinement_summary=dict(payload.get("last_drift_refinement_summary", {})),
            variants=variants,
            last_page_insights=LinkedInPageInsights.from_dict(payload.get("last_page_insights")),
        )
        state.__post_init__()
        return state

    @property
    def root_variant(self) -> LinkedInSearchVariant:
        return self.variants["root"]

    @property
    def active_variant(self) -> LinkedInSearchVariant:
        return self.variants[self.active_variant_id]

    @property
    def committed_variant(self) -> LinkedInSearchVariant | None:
        if not self.committed_variant_id:
            return None
        return self.variants.get(self.committed_variant_id)

    def current_boolean(self) -> str:
        if self.active_variant_id in self.variants:
            return self.active_variant.boolean
        return self.root_variant.boolean

    def compat_refinement_stack(self) -> list[str]:
        lineage = self.variant_lineage(self.active_variant_id)
        return [variant.boolean for variant in lineage[:-1]]

    def compat_phase(self) -> str:
        return "paginate" if self.mode in {"paginate", "drift"} else "scout"

    def apply_shadow(self, search_string: SearchString) -> None:
        search_string.boolean = self.current_boolean()
        search_string.original_boolean = self.intent.root_boolean
        search_string.refinement_stack = self.compat_refinement_stack()
        search_string.phase = self.compat_phase()

    def variant_lineage(self, variant_id: str | None = None) -> list[LinkedInSearchVariant]:
        variant_id = variant_id or self.active_variant_id
        lineage: list[LinkedInSearchVariant] = []
        seen: set[str] = set()
        current = self.variants.get(variant_id)
        while current and current.variant_id not in seen:
            lineage.append(current)
            seen.add(current.variant_id)
            current = self.variants.get(current.parent_variant_id or "")
        lineage.reverse()
        return lineage or [self.root_variant]

    def note_page_review(self) -> None:
        self.consecutive_mutations = 0
        self.pages_since_last_mutation += 1
        if self.pending_drift_variant_id and self.pending_drift_variant_id == self.active_variant_id:
            self.clear_pending_drift()

    def begin_experiment_round(self, variants: list[LinkedInSearchVariant]) -> None:
        self.experiment_round += 1
        self.mode = "experiment"
        self.executed_sibling_count = 0
        self.planned_variant_ids = []
        parent_id = self.active_variant_id
        for index, variant in enumerate(variants[:3], start=1):
            variant.parent_variant_id = variant.parent_variant_id or parent_id
            variant.root_string_id = self.root_string_id
            variant.experiment_round = self.experiment_round
            variant.status = "planned"
            if not variant.variant_id:
                variant.variant_id = f"round-{self.experiment_round}-{index}"
            self.variants[variant.variant_id] = variant
            self.planned_variant_ids.append(variant.variant_id)

    def next_planned_variant(self) -> LinkedInSearchVariant | None:
        for variant_id in self.planned_variant_ids:
            variant = self.variants.get(variant_id)
            if variant and variant.status == "planned":
                return variant
        return None

    def activate_variant(self, variant_id: str) -> LinkedInSearchVariant:
        current_mode = self.mode
        if self.active_variant_id in self.variants and self.variants[self.active_variant_id].status == "active":
            self.variants[self.active_variant_id].status = "explored"
        variant = self.variants[variant_id]
        variant.status = "active"
        self.active_variant_id = variant_id
        self.mutations_used += 1
        self.consecutive_mutations += 1
        self.pages_since_last_mutation = 0
        if variant_id in self.planned_variant_ids:
            self.executed_sibling_count += 1
            if current_mode in {"recon", "experiment"} and self.committed_variant_id is None:
                self.precommit_recovery_attempts_used += 1
        return variant

    def commit_variant(self, variant_id: str | None = None) -> LinkedInSearchVariant:
        variant_id = variant_id or self.active_variant_id
        variant = self.variants[variant_id]
        preserving_drift_summary = self.mode == "drift"
        variant.status = "committed"
        self.committed_variant_id = variant_id
        self.active_variant_id = variant_id
        self.mode = "paginate"
        self.planned_variant_ids = []
        self.executed_sibling_count = 0
        self.committed_pages_reviewed = 0
        self.committed_zero_signal_streak = 0
        self.early_signal_snapshot = None
        self.recent_noise_snapshot = None
        self.drift_attempt_count = 0
        self.pending_drift_variant_id = None
        self.pending_drift_parent_variant_id = None
        self.pending_drift_started_at = ""
        if not preserving_drift_summary:
            self.last_drift_refinement_summary = {}
        return variant

    def record_variant_metrics(
        self,
        *,
        variant_id: str | None = None,
        page_num: int,
        result_count: int,
        page_stats: dict[str, Any],
        page_insights: LinkedInPageInsights | None = None,
    ) -> None:
        variant = self.variants[variant_id or self.active_variant_id]
        variant.result_count = result_count
        variant.pages_reviewed = max(variant.pages_reviewed, page_num)
        variant.candidates += int(page_stats.get("candidates", 0))
        variant.duplicates += int(page_stats.get("duplicates", 0))
        variant.saves += int(page_stats.get("saves", 0))
        variant.rejects += int(page_stats.get("rejects", 0))
        variant.facial_yes += int(page_stats.get("facial_yes", 0))
        variant.facial_no += int(page_stats.get("facial_no", 0))
        variant.last_page_insights = page_insights
        self.last_page_insights = page_insights
        if variant.status == "planned":
            variant.status = "explored"

    def record_family_page_metrics(
        self,
        *,
        page_num: int,
        result_count: int,
        page_stats: dict[str, int],
        page_insights: LinkedInPageInsights,
    ) -> None:
        self.family_pages_reviewed_total += 1
        self.family_candidates_total += int(page_stats.get("candidates", 0))
        self.family_duplicates_total += int(page_stats.get("duplicates", 0))
        page_signal = int(page_stats.get("saves", 0)) + int(page_stats.get("facial_yes", 0)) + int(
            page_stats.get("rejects", 0)
        )
        self.family_signal_total += page_signal
        self.family_saves_total += int(page_stats.get("saves", 0))

        is_committed_variant_page = (
            self.committed_variant_id is not None and self.active_variant_id == self.committed_variant_id
        )
        if is_committed_variant_page and self.early_signal_snapshot is None:
            if int(page_stats.get("saves", 0)) > 0 or len(page_insights.signal_anchors) >= 2:
                self.early_signal_snapshot = LinkedInVariantSnapshot.from_page(
                    page_num=page_num,
                    result_count=result_count,
                    page_insights=page_insights,
                    page_stats=page_stats,
                )
        if is_committed_variant_page:
            self.committed_pages_reviewed += 1
            no_signal = page_signal == 0
            noisy_page = bool(page_insights.noise_anchors) or page_insights.glance_action == "reformulate"
            if no_signal:
                self.committed_zero_signal_streak += 1
            else:
                self.committed_zero_signal_streak = 0
                if self.last_drift_refinement_summary.get("outcome") == "not_rescued":
                    self.last_drift_refinement_summary = {
                        **self.last_drift_refinement_summary,
                        "outcome": "signal_returned",
                    }
            if no_signal and noisy_page:
                self.recent_noise_snapshot = LinkedInVariantSnapshot.from_page(
                    page_num=page_num,
                    result_count=result_count,
                    page_insights=page_insights,
                    page_stats=page_stats,
                )

    def real_signal_seen(self) -> bool:
        if self.family_saves_total > 0:
            return True
        return bool(self.early_signal_snapshot and len(self.early_signal_snapshot.signal_anchors) >= 2)

    def mark_pending_drift(
        self,
        *,
        variant_id: str,
        parent_variant_id: str | None,
        summary: dict[str, Any] | None = None,
    ) -> None:
        self.mode = "drift"
        self.drift_attempt_count += 1
        self.pending_drift_variant_id = variant_id
        self.pending_drift_parent_variant_id = parent_variant_id
        self.pending_drift_started_at = datetime.now(timezone.utc).isoformat()
        if summary is not None:
            self.last_drift_refinement_summary = dict(summary)

    def clear_pending_drift(self, summary: dict[str, Any] | None = None) -> None:
        self.pending_drift_variant_id = None
        self.pending_drift_parent_variant_id = None
        self.pending_drift_started_at = ""
        if summary is not None:
            self.last_drift_refinement_summary = dict(summary)

    def rollback_pending_drift(self) -> None:
        if self.drift_attempt_count > 0:
            self.drift_attempt_count -= 1
        self.pending_drift_variant_id = None
        self.pending_drift_parent_variant_id = None
        self.pending_drift_started_at = ""
        if self.mode == "drift":
            self.mode = "paginate" if self.committed_variant_id else "recon"

    def resume_committed_after_failed_drift(self) -> None:
        if self.active_variant_id in self.variants:
            self.variants[self.active_variant_id].status = "explored"
        if self.committed_variant_id:
            self.active_variant_id = self.committed_variant_id
        self.pending_drift_variant_id = None
        self.pending_drift_parent_variant_id = None
        self.pending_drift_started_at = ""
        self.mode = "paginate" if self.committed_variant_id else "recon"
        self.pages_since_last_mutation = 0

    def best_variant(self) -> LinkedInSearchVariant:
        candidates = [
            variant
            for variant in self.variants.values()
            if variant.pages_reviewed > 0 or variant.result_count > 0 or variant.variant_id == self.active_variant_id
        ]
        return max(candidates, key=lambda variant: variant.score(), default=self.active_variant)

    def metrics_summary(self) -> dict[str, Any]:
        active_variant = self.active_variant
        return {
            "mode": self.mode,
            "active_variant_id": self.active_variant_id,
            "committed_variant_id": self.committed_variant_id,
            "experiment_round": self.experiment_round,
            "mutations_used": self.mutations_used,
            "drift_attempt_count": self.drift_attempt_count,
            "pending_drift_variant_id": self.pending_drift_variant_id,
            "pending_drift_parent_variant_id": self.pending_drift_parent_variant_id,
            "pending_drift_started_at": self.pending_drift_started_at,
            "family_pages_reviewed_total": self.family_pages_reviewed_total,
            "family_candidates_total": self.family_candidates_total,
            "family_duplicates_total": self.family_duplicates_total,
            "family_signal_total": self.family_signal_total,
            "family_saves_total": self.family_saves_total,
            "precommit_recovery_attempts_used": self.precommit_recovery_attempts_used,
            "committed_pages_reviewed": self.committed_pages_reviewed,
            "committed_zero_signal_streak": self.committed_zero_signal_streak,
            "active_variant_page": active_variant.pages_reviewed,
            "active_variant_pages_reviewed": active_variant.pages_reviewed,
            "active_variant_result_count": active_variant.result_count,
            "active_variant_signal": active_variant.saves + active_variant.facial_yes + active_variant.rejects,
            "active_variant_saves": active_variant.saves,
            "executed_sibling_count": self.executed_sibling_count,
            "early_signal_snapshot": self.early_signal_snapshot.to_dict() if self.early_signal_snapshot else None,
            "recent_noise_snapshot": self.recent_noise_snapshot.to_dict() if self.recent_noise_snapshot else None,
            "family_outcome_summary": {
                "root_string_id": self.root_string_id,
                "committed_variant_id": self.committed_variant_id,
                "family_pages_reviewed_total": self.family_pages_reviewed_total,
                "family_signal_total": self.family_signal_total,
                "family_saves_total": self.family_saves_total,
            },
            "drift_rescue_summary": dict(self.last_drift_refinement_summary),
            "variants": {
                key: {
                    "variant_kind": variant.variant_kind,
                    "status": variant.status,
                    "result_count": variant.result_count,
                    "pages_reviewed": variant.pages_reviewed,
                    "saves": variant.saves,
                    "facial_yes": variant.facial_yes,
                    "facial_no": variant.facial_no,
                    "score": round(variant.score(), 2),
                }
                for key, variant in self.variants.items()
            },
        }


def bootstrap_experiment_state(search_string: SearchString) -> LinkedInExperimentState:
    """Bootstrap experiment state from compatibility-era SearchString fields."""
    root_boolean = search_string.original_boolean or search_string.boolean
    intent = LinkedInSearchIntent(
        root_boolean=root_boolean,
        family_key=search_string.family_key,
        novelty_bucket=search_string.novelty_bucket,
        domain_lane=search_string.domain_lane,
        retrieval_recipe=dict(search_string.retrieval_recipe or {}),
        applied_hypothesis_ids=list(search_string.retrieval_hypothesis_ids or []),
    )
    state = LinkedInExperimentState(
        root_string_id=search_string.id,
        intent=intent,
        mode="paginate" if search_string.phase == "paginate" else "recon",
    )

    chain = list(search_string.refinement_stack)
    if not chain:
        state.root_variant.boolean = root_boolean
        state.apply_shadow(search_string)
        return state

    current_parent = "root"
    seen_boolean = root_boolean
    for index, boolean in enumerate(chain + [search_string.boolean], start=1):
        if not boolean or boolean == seen_boolean:
            continue
        variant_id = f"legacy-{index}"
        variant = LinkedInSearchVariant(
            variant_id=variant_id,
            parent_variant_id=current_parent,
            root_string_id=search_string.id,
            boolean=boolean,
            variant_kind="precision",
            status="committed" if boolean == search_string.boolean else "explored",
            experiment_round=0,
        )
        state.variants[variant_id] = variant
        current_parent = variant_id
        seen_boolean = boolean

    state.active_variant_id = current_parent
    state.committed_variant_id = current_parent
    state.mode = "paginate"
    state.apply_shadow(search_string)
    return state


def reset_experiment_state(
    search_string: SearchString,
    state: LinkedInExperimentState | None = None,
) -> LinkedInExperimentState:
    if state is None:
        state = bootstrap_experiment_state(search_string)
    intent = LinkedInSearchIntent(
        root_boolean=state.intent.root_boolean or search_string.original_boolean or search_string.boolean,
        family_key=state.intent.family_key or search_string.family_key,
        novelty_bucket=state.intent.novelty_bucket or search_string.novelty_bucket,
        domain_lane=state.intent.domain_lane or search_string.domain_lane,
        retrieval_recipe=state.intent.retrieval_recipe or dict(search_string.retrieval_recipe or {}),
        applied_hypothesis_ids=state.intent.applied_hypothesis_ids or list(search_string.retrieval_hypothesis_ids or []),
        structured_filters=state.intent.structured_filters,
    )
    reset_state = LinkedInExperimentState(root_string_id=search_string.id, intent=intent, mode="recon")
    reset_state.apply_shadow(search_string)
    return reset_state
