"""Schemas for Recruiter-first identity resolution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from shared.reconciliation_schemas import RecruiterActivitySnapshot


@dataclass
class PlausibleProfileReview:
    """Evidence from opening one plausible Recruiter card (identity + fit + engagement snapshot)."""

    rank: int
    profile_url: str = ""
    card_name: str = ""
    match_confidence: float = 0.0
    extraction_failed: bool = False
    holistic_fit_decision: str = ""
    holistic_fit_confidence: float = 0.0
    holistic_fit_rationale: str = ""
    holistic_fit_path: str = ""
    holistic_profile_summary: dict = field(default_factory=dict)
    profile_status: dict | None = None
    novelty_pressure: str = ""
    reachout_status: str = ""
    gate_final_action: str = ""
    gate_final_subreason: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "PlausibleProfileReview":
        return cls(
            rank=int(data.get("rank", 0) or 0),
            profile_url=str(data.get("profile_url", "") or "").strip(),
            card_name=str(data.get("card_name", "") or "").strip(),
            match_confidence=float(data.get("match_confidence", 0.0) or 0.0),
            extraction_failed=bool(data.get("extraction_failed", False)),
            holistic_fit_decision=str(data.get("holistic_fit_decision", "") or "").strip(),
            holistic_fit_confidence=float(data.get("holistic_fit_confidence", 0.0) or 0.0),
            holistic_fit_rationale=str(data.get("holistic_fit_rationale", "") or "").strip(),
            holistic_fit_path=str(data.get("holistic_fit_path", "") or "").strip(),
            holistic_profile_summary=dict(data.get("holistic_profile_summary", {}) or {}),
            profile_status=data.get("profile_status") if isinstance(data.get("profile_status"), dict) else None,
            novelty_pressure=str(data.get("novelty_pressure", "") or "").strip(),
            reachout_status=str(data.get("reachout_status", "") or "").strip(),
            gate_final_action=str(data.get("gate_final_action", "") or "").strip(),
            gate_final_subreason=str(data.get("gate_final_subreason", "") or "").strip(),
        )


@dataclass
class RecruiterIdentityCandidate:
    """One Recruiter result card considered during identity resolution."""

    rank: int
    profile_url: str = ""
    name: str = ""
    headline: str = ""
    current_title: str = ""
    current_company: str = ""
    location: str = ""
    already_saved: bool = False
    match_confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    ambiguity_reasons: list[str] = field(default_factory=list)
    recruiter_activity: RecruiterActivitySnapshot | None = None
    raw_card_text: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        if self.recruiter_activity is None:
            payload["recruiter_activity"] = None
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "RecruiterIdentityCandidate":
        return cls(
            rank=int(data.get("rank", 0) or 0),
            profile_url=str(data.get("profile_url", "") or "").strip(),
            name=str(data.get("name", "") or "").strip(),
            headline=str(data.get("headline", "") or "").strip(),
            current_title=str(data.get("current_title", "") or "").strip(),
            current_company=str(data.get("current_company", "") or "").strip(),
            location=str(data.get("location", "") or "").strip(),
            already_saved=bool(data.get("already_saved", False)),
            match_confidence=float(data.get("match_confidence", 0.0) or 0.0),
            evidence=[str(item).strip() for item in data.get("evidence", []) if str(item).strip()],
            ambiguity_reasons=[
                str(item).strip()
                for item in data.get("ambiguity_reasons", [])
                if str(item).strip()
            ],
            recruiter_activity=RecruiterActivitySnapshot.from_dict(data.get("recruiter_activity")),
            raw_card_text=str(data.get("raw_card_text", "") or "").strip(),
        )


@dataclass
class RecruiterIdentityResolution:
    """Reconciliation outcome for one GitHub lead on Recruiter (identity + fit + engagement)."""

    github_username: str
    candidate_name: str
    lookup_name: str
    github_url: str = ""
    github_company: str = ""
    github_location: str = ""
    github_title: str = ""
    search_location: str = ""
    query: str = ""
    rationale: str = ""
    top_candidates: list[RecruiterIdentityCandidate] = field(default_factory=list)
    selected_candidate_rank: int = 0
    selected_profile_url: str = ""
    already_saved: bool = False
    opened_profile: bool = False
    profile_status: RecruiterActivitySnapshot | None = None
    novelty_pressure: str = ""
    reachout_status: str = ""
    notes: list[str] = field(default_factory=list)
    # --- Canonical reconciliation (GitHub-LinkedIn-Reconciliation-Source-of-Truth) ---
    final_action: str = ""
    final_subreason: str = ""
    identity_classification: str = ""
    linkedin_brief_path: str = ""
    holistic_fit_decision: str = ""
    holistic_fit_confidence: float = 0.0
    holistic_fit_rationale: str = ""
    holistic_fit_path: str = ""
    holistic_profile_summary: dict = field(default_factory=dict)
    recruiter_save_attempted: bool = False
    recruiter_save_succeeded: bool = False
    had_plausible_cards: bool = False
    extraction_failed: bool = False
    plausible_profile_reviews: list[PlausibleProfileReview] = field(default_factory=list)
    ambiguity_multi_review: bool = False

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["top_candidates"] = [candidate.to_dict() for candidate in self.top_candidates]
        if self.profile_status is None:
            payload["profile_status"] = None
        payload["plausible_profile_reviews"] = [item.to_dict() for item in self.plausible_profile_reviews]
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "RecruiterIdentityResolution":
        final_action = str(data.get("final_action", "") or "").strip()
        if not final_action:
            final_action = str(data.get("action", "") or "").strip()
        return cls(
            github_username=str(data.get("github_username", "") or "").strip(),
            candidate_name=str(data.get("candidate_name", "") or "").strip(),
            lookup_name=str(data.get("lookup_name", "") or "").strip(),
            github_url=str(data.get("github_url", "") or "").strip(),
            github_company=str(data.get("github_company", "") or "").strip(),
            github_location=str(data.get("github_location", "") or "").strip(),
            github_title=str(data.get("github_title", "") or "").strip(),
            search_location=str(data.get("search_location", "") or "").strip(),
            query=str(data.get("query", "") or "").strip(),
            rationale=str(data.get("rationale", "") or "").strip(),
            top_candidates=[
                RecruiterIdentityCandidate.from_dict(item)
                for item in data.get("top_candidates", [])
                if isinstance(item, dict)
            ],
            selected_candidate_rank=int(data.get("selected_candidate_rank", 0) or 0),
            selected_profile_url=str(data.get("selected_profile_url", "") or "").strip(),
            already_saved=bool(data.get("already_saved", False)),
            opened_profile=bool(data.get("opened_profile", False)),
            profile_status=RecruiterActivitySnapshot.from_dict(data.get("profile_status")),
            novelty_pressure=str(data.get("novelty_pressure", "") or "").strip(),
            reachout_status=str(data.get("reachout_status", "") or "").strip(),
            notes=[str(item).strip() for item in data.get("notes", []) if str(item).strip()],
            final_action=final_action,
            final_subreason=str(data.get("final_subreason", "") or "").strip(),
            identity_classification=str(data.get("identity_classification", "") or "").strip(),
            linkedin_brief_path=str(data.get("linkedin_brief_path", "") or "").strip(),
            holistic_fit_decision=str(data.get("holistic_fit_decision", "") or "").strip(),
            holistic_fit_confidence=float(data.get("holistic_fit_confidence", 0.0) or 0.0),
            holistic_fit_rationale=str(data.get("holistic_fit_rationale", "") or "").strip(),
            holistic_fit_path=str(data.get("holistic_fit_path", "") or "").strip(),
            holistic_profile_summary=dict(data.get("holistic_profile_summary", {}) or {}),
            recruiter_save_attempted=bool(data.get("recruiter_save_attempted", False)),
            recruiter_save_succeeded=bool(data.get("recruiter_save_succeeded", False)),
            had_plausible_cards=bool(data.get("had_plausible_cards", False)),
            extraction_failed=bool(data.get("extraction_failed", False)),
            plausible_profile_reviews=[
                PlausibleProfileReview.from_dict(item)
                for item in data.get("plausible_profile_reviews", [])
                if isinstance(item, dict)
            ],
            ambiguity_multi_review=bool(data.get("ambiguity_multi_review", False)),
        )
