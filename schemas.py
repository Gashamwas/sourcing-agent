"""Data schemas for the sourcing pipeline. All pipeline objects as dataclasses with JSON serialization."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
import json


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
    coverage_gaps: list[dict] = field(default_factory=list)

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
            coverage_gaps=d.get("coverage_gaps", []),
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

    def to_dict(self) -> dict:
        return asdict(self)

    def to_summary_text(self) -> str:
        lines = [f'Block "{self.block_name}" complete.']
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
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Adaptation response (Opus mid-run adjustments)
# ---------------------------------------------------------------------------

@dataclass
class AdaptationResponse:
    new_strings: list[dict] = field(default_factory=list)
    skip_remaining: list[dict] = field(default_factory=list)
    reorder: list[dict] = field(default_factory=list)
    noise_updates: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> AdaptationResponse:
        return cls(
            new_strings=d.get("new_strings", []),
            skip_remaining=d.get("skip_remaining", []),
            reorder=d.get("reorder", []),
            noise_updates=d.get("noise_updates", []),
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

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> CandidateSnippet:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


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

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> OpusDecision:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


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
    # Two-phase adaptation fields
    phase: str = "scout"  # "scout" | "paginate"
    original_boolean: str = ""  # The original Boolean before any refinements
    refinement_stack: list[str] = field(default_factory=list)  # Stack of applied Booleans (push=narrow, pop=broaden)

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
        )

    @classmethod
    def from_file(cls, path: str) -> Progress:
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            f.write(self.to_json())
