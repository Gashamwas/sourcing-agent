"""GitHub-specific data types and adapter functions.

Defines intermediate schemas for GitHub API data, plus adapter methods that
map into the existing CandidateSnippet/CandidateProfileSummary schemas used
by judger.py. The LinkedIn schemas are not modified — this module bridges
GitHub data into the existing evaluation pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional
import json

from shared.schemas import (
    CandidateSnippet,
    CandidateProfileSummary,
    Experience,
    Education,
)


# ---------------------------------------------------------------------------
# GitHub API data types
# ---------------------------------------------------------------------------

@dataclass
class GitHubUser:
    """Raw user data from GET /users/{username}."""
    username: str
    name: str = ""
    bio: str = ""
    company: str = ""
    location: str = ""
    email: str = ""
    blog: str = ""
    hireable: Optional[bool] = None
    followers: int = 0
    following: int = 0
    public_repos: int = 0
    created_at: str = ""
    profile_url: str = ""
    twitter_username: str = ""
    avatar_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_api(cls, data: dict) -> GitHubUser:
        """Parse from GitHub API response."""
        return cls(
            username=data.get("login", ""),
            name=data.get("name", "") or "",
            bio=data.get("bio", "") or "",
            company=data.get("company", "") or "",
            location=data.get("location", "") or "",
            email=data.get("email", "") or "",
            blog=data.get("blog", "") or "",
            hireable=data.get("hireable"),
            followers=data.get("followers", 0),
            following=data.get("following", 0),
            public_repos=data.get("public_repos", 0),
            created_at=data.get("created_at", ""),
            profile_url=data.get("html_url", ""),
            twitter_username=data.get("twitter_username", "") or "",
            avatar_url=data.get("avatar_url", "") or "",
        )


@dataclass
class GitHubRepo:
    """Repository data relevant to candidate assessment."""
    name: str
    full_name: str = ""
    description: str = ""
    language: str = ""
    stars: int = 0
    forks: int = 0
    topics: list[str] = field(default_factory=list)
    pushed_at: str = ""
    created_at: str = ""
    is_fork: bool = False
    html_url: str = ""
    owner_login: str = ""  # to distinguish own repos from org repos

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_api(cls, data: dict) -> GitHubRepo:
        """Parse from GitHub API response."""
        return cls(
            name=data.get("name", ""),
            full_name=data.get("full_name", ""),
            description=data.get("description", "") or "",
            language=data.get("language", "") or "",
            stars=data.get("stargazers_count", 0),
            forks=data.get("forks_count", 0),
            topics=data.get("topics", []),
            pushed_at=data.get("pushed_at", ""),
            created_at=data.get("created_at", ""),
            is_fork=data.get("fork", False),
            html_url=data.get("html_url", ""),
            owner_login=data.get("owner", {}).get("login", ""),
        )


@dataclass
class ContactInfo:
    """Discovered contact information for a candidate."""
    emails: list[str] = field(default_factory=list)  # deduplicated, noreply filtered
    linkedin_url: str = ""
    twitter_url: str = ""
    website: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GitHubCandidate:
    """Enriched candidate combining user profile + repos + contributions + contacts.

    This is the intermediate representation. The adapter methods map it into
    CandidateSnippet and CandidateProfileSummary for the evaluation pipeline.
    """
    user: GitHubUser
    top_repos: list[GitHubRepo] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)  # language -> total bytes
    contact: ContactInfo = field(default_factory=ContactInfo)
    contribution_months: dict[str, int] = field(default_factory=dict)  # "2025-01" -> commit count
    readme_text: str = ""  # profile README content
    source_strategy: str = ""  # "user_search" | "code_search" | "repo_mining" | "org_exploration"
    source_query: str = ""
    data_sufficiency: str = "sufficient"  # "sufficient" | "insufficient" | "minimal"

    # These are populated by the cheap model synthesis step
    synthesized_headline: str = ""
    synthesized_experience_entries: list[str] = field(default_factory=list)
    synthesized_experiences: list[dict] = field(default_factory=list)  # raw dicts for Experience
    synthesized_skills: list[str] = field(default_factory=list)

    # --- Enrichment extensions (Phase 2) ---
    frontier_contributions: list[dict] = field(default_factory=list)
    website_text: str = ""
    paper_links: list[str] = field(default_factory=list)
    paper_titles: list[str] = field(default_factory=list)
    repo_readmes: dict[str, str] = field(default_factory=dict)  # repo_name -> readme_text

    # --- Portfolio extraction (cheap model structured output) ---
    portfolio_summary: dict = field(default_factory=dict)

    # --- Capability-aware synthesis ---
    capability_mapping: list[dict] = field(default_factory=list)
    builder_evidence: list[str] = field(default_factory=list)
    user_evidence: list[str] = field(default_factory=list)
    repo_analysis: list[dict] = field(default_factory=list)

    # --- Outreach (stored, never sent) ---
    outreach_copy: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "user": self.user.to_dict(),
            "top_repos": [r.to_dict() for r in self.top_repos],
            "languages": self.languages,
            "contact": self.contact.to_dict(),
            "contribution_months": self.contribution_months,
            "readme_text": self.readme_text[:500] if self.readme_text else "",
            "source_strategy": self.source_strategy,
            "source_query": self.source_query,
            "data_sufficiency": self.data_sufficiency,
            "synthesized_headline": self.synthesized_headline,
            "synthesized_experience_entries": self.synthesized_experience_entries,
            "synthesized_skills": self.synthesized_skills,
            "frontier_contributions": self.frontier_contributions,
            "website_text": self.website_text[:500] if self.website_text else "",
            "paper_links": self.paper_links,
            "paper_titles": self.paper_titles,
            "repo_readmes": {k: v[:500] for k, v in self.repo_readmes.items()},
            "portfolio_summary": self.portfolio_summary,
            "capability_mapping": self.capability_mapping,
            "builder_evidence": self.builder_evidence,
            "user_evidence": self.user_evidence,
            "repo_analysis": self.repo_analysis,
            "outreach_copy": self.outreach_copy,
        }
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_snippet(self, source_string_id: int = 0, source_string_name: str = "", page: int = 0, result_rank: int = 0) -> CandidateSnippet:
        """Map to CandidateSnippet for facial judgment.

        Uses synthesized fields from the cheap model. If synthesis hasn't run,
        falls back to raw GitHub data.
        """
        headline = self.synthesized_headline or self.user.bio or ""
        experience_entries = self.synthesized_experience_entries or [
            f"{r.name}: {r.description} ({r.language}, {r.stars}★)"
            for r in self.top_repos[:5] if not r.is_fork
        ]

        return CandidateSnippet(
            name=self.user.name or self.user.username,
            headline=headline,
            current_title=self.user.company or "",
            current_company=self.user.company or "",
            location=self.user.location or "",
            education_snippet="",  # GitHub doesn't expose education
            profile_url=self.user.profile_url,
            source_string_id=source_string_id,
            source_string_name=source_string_name,
            page=page,
            result_rank=result_rank,
            experience_entries=experience_entries,
        )

    def to_profile_summary(self) -> CandidateProfileSummary:
        """Map to CandidateProfileSummary for full judgment.

        Uses synthesized fields from the cheap model for experiences.
        Falls back to raw repo data if synthesis hasn't run.
        """
        # Build experiences from synthesized data or raw repos
        experiences = []
        if self.synthesized_experiences:
            for exp_dict in self.synthesized_experiences:
                experiences.append(Experience(
                    title=exp_dict.get("title", ""),
                    company=exp_dict.get("company", ""),
                    location=exp_dict.get("location", ""),
                    start=exp_dict.get("start", ""),
                    end=exp_dict.get("end", ""),
                    summary_bullets=exp_dict.get("summary_bullets", []),
                ))
        else:
            # Fallback: repos as pseudo-experiences
            for repo in self.top_repos[:10]:
                if repo.is_fork:
                    continue
                bullets = [repo.description] if repo.description else []
                if repo.topics:
                    bullets.append(f"Topics: {', '.join(repo.topics)}")
                bullets.append(f"{repo.stars} stars, {repo.forks} forks")
                experiences.append(Experience(
                    title=f"Maintainer — {repo.name}",
                    company="GitHub (open source)",
                    start=repo.created_at[:10] if repo.created_at else "",
                    end=repo.pushed_at[:10] if repo.pushed_at else "",
                    summary_bullets=bullets,
                ))

        # Skills from synthesized or raw language data
        skills = self.synthesized_skills or sorted(
            self.languages.keys(),
            key=lambda l: self.languages[l],
            reverse=True,
        )[:15]

        headline = self.synthesized_headline or self.user.bio or ""

        return CandidateProfileSummary(
            name=self.user.name or self.user.username,
            profile_url=self.user.profile_url,
            headline=headline,
            experiences=experiences,
            education=[],  # GitHub doesn't expose education
            skills_snippet=skills,
        )

    def to_portfolio_text(self) -> str:
        """Format portfolio summary for GitHub facial triage template."""
        ps = self.portfolio_summary
        if not ps:
            # Fallback to raw data if portfolio extraction hasn't run
            lines = [
                f"Username: {self.user.username}",
                f"Name: {self.user.name}",
                f"Bio: {self.user.bio or '(none)'}",
                f"Company: {self.user.company or '(none)'}",
                f"Location: {self.user.location or '(none)'}",
                f"Followers: {self.user.followers}",
                f"Public repos: {self.user.public_repos}",
                f"Account created: {self.user.created_at[:10] if self.user.created_at else 'unknown'}",
                "",
            ]
            if self.top_repos:
                lines.append("Top repositories:")
                for r in self.top_repos[:5]:
                    topics = f" [{', '.join(r.topics)}]" if r.topics else ""
                    lines.append(f"  - {r.name} ({r.language}, {r.stars} stars){topics}: {r.description or '(no description)'}")
            if self.readme_text:
                lines.append(f"\nProfile README excerpt: {self.readme_text[:500]}")
            return "\n".join(lines)

        # Format from structured portfolio summary
        lines = [f"Username: {self.user.username}"]
        lines.append(f"Name: {self.user.name}")
        lines.append(f"Location: {self.user.location or '(none)'}")

        if ps.get("profile_summary"):
            lines.append(f"Profile: {ps['profile_summary']}")

        # Toolchain detection (most important signal)
        tc = ps.get("toolchain_detected", {})
        if tc.get("frameworks"):
            lines.append(f"\nFrontier Toolchain Detected: {', '.join(tc['frameworks'])}")
            if tc.get("evidence"):
                for ev in tc["evidence"]:
                    lines.append(f"  - {ev}")
            if tc.get("capability_areas_signaled"):
                lines.append(f"  Capability areas signaled: {', '.join(tc['capability_areas_signaled'])}")

        # Repo summaries
        repos = ps.get("repo_summaries", [])
        if repos:
            lines.append(f"\nRepositories ({len(repos)}):")
            for r in repos:
                fork_tag = " [FORK]" if r.get("is_fork") else ""
                frameworks = f" — frameworks: {', '.join(r['frameworks_used'])}" if r.get("frameworks_used") else ""
                lines.append(f"  - {r['name']} ({r.get('stars', 0)} stars){fork_tag}{frameworks}")
                if r.get("readme_gist"):
                    lines.append(f"    {r['readme_gist']}")
                if r.get("builder_or_user"):
                    lines.append(f"    Assessment: {r['builder_or_user']}")

        # Frontier contributions
        fc = ps.get("frontier_contributions", [])
        if fc:
            lines.append(f"\nFrontier Contributions: {', '.join(fc)}")

        # Website/papers
        wp = ps.get("website_papers", [])
        if wp:
            lines.append(f"\nWebsite/Papers: {', '.join(wp)}")

        lines.append(f"\nML Signal Strength: {ps.get('ml_signal_strength', 'unknown')}")

        return "\n".join(lines)

    def to_evidence_text(self) -> str:
        """Format full enriched profile for GitHub full evaluation template."""
        lines = [
            f"Username: {self.user.username}",
            f"Name: {self.user.name}",
            f"Bio: {self.user.bio or '(none)'}",
            f"Company: {self.user.company or '(none)'}",
            f"Location: {self.user.location or '(none)'}",
            f"Followers: {self.user.followers}",
            f"Public repos: {self.user.public_repos}",
            f"Account created: {self.user.created_at[:10] if self.user.created_at else 'unknown'}",
            f"Profile URL: {self.user.profile_url}",
        ]

        # Portfolio summary (from cheap model extraction)
        ps = self.portfolio_summary
        if ps:
            tc = ps.get("toolchain_detected", {})
            if tc.get("frameworks"):
                lines.append(f"\n═══ FRONTIER TOOLCHAIN DETECTED ═══")
                lines.append(f"Frameworks: {', '.join(tc['frameworks'])}")
                if tc.get("evidence"):
                    for ev in tc["evidence"]:
                        lines.append(f"  - {ev}")
                if tc.get("capability_areas_signaled"):
                    lines.append(f"Capability areas signaled: {', '.join(tc['capability_areas_signaled'])}")

        # Frontier contributions
        if self.frontier_contributions:
            lines.append(f"\n═══ FRONTIER REPO CONTRIBUTIONS ═══")
            for fc in self.frontier_contributions:
                lines.append(f"  - {fc.get('repo', '')}: {fc.get('type', '')} — {fc.get('detail', '')}")

        # Top repos with READMEs
        lines.append(f"\n═══ REPOSITORIES ═══")
        for r in self.top_repos[:10]:
            fork_tag = " [FORK]" if r.is_fork else ""
            topics = f" Topics: {', '.join(r.topics)}" if r.topics else ""
            lines.append(f"\n{r.name} ({r.language}, {r.stars} stars, {r.forks} forks){fork_tag}")
            lines.append(f"  Description: {r.description or '(none)'}")
            if topics:
                lines.append(f"  {topics}")
            lines.append(f"  Last pushed: {r.pushed_at[:10] if r.pushed_at else 'unknown'}")
            # Include README if available
            readme = self.repo_readmes.get(r.name, "")
            if readme:
                lines.append(f"  README excerpt:\n    {readme[:1500]}")

        # Repo analysis from portfolio extraction
        if self.repo_analysis:
            lines.append(f"\n═══ REPO ANALYSIS (from enrichment) ═══")
            for ra in self.repo_analysis:
                lines.append(f"  {ra.get('name', '')}: {ra.get('what_it_does', '')}")
                if ra.get("builder_signals"):
                    lines.append(f"    Builder signals: {', '.join(ra['builder_signals'])}")
                lines.append(f"    Relevance: {ra.get('relevance', 'unknown')}")

        # Website and papers
        if self.website_text or self.paper_titles:
            lines.append(f"\n═══ WEBSITE & PAPERS ═══")
            if self.paper_titles:
                lines.append("Papers:")
                for pt in self.paper_titles:
                    lines.append(f"  - {pt}")
            if self.website_text:
                lines.append(f"Website content excerpt:\n  {self.website_text[:1000]}")

        # Profile README
        if self.readme_text:
            lines.append(f"\n═══ PROFILE README ═══")
            lines.append(self.readme_text[:2000])

        # Languages
        if self.languages:
            sorted_langs = sorted(self.languages.items(), key=lambda x: x[1], reverse=True)
            lang_str = ", ".join(f"{lang} ({weight})" for lang, weight in sorted_langs[:10])
            lines.append(f"\n═══ LANGUAGE DISTRIBUTION ═══")
            lines.append(lang_str)

        # Builder/user evidence from synthesis
        if self.builder_evidence:
            lines.append(f"\n═══ BUILDER EVIDENCE (from enrichment) ═══")
            for be in self.builder_evidence:
                lines.append(f"  + {be}")
        if self.user_evidence:
            lines.append(f"\n═══ USER-LEVEL EVIDENCE (from enrichment) ═══")
            for ue in self.user_evidence:
                lines.append(f"  - {ue}")

        # Contact info
        if self.contact.emails or self.contact.website:
            lines.append(f"\n═══ CONTACT ═══")
            if self.contact.emails:
                lines.append(f"  Emails: {', '.join(self.contact.emails)}")
            if self.contact.website:
                lines.append(f"  Website: {self.contact.website}")

        return "\n".join(lines)

    def assess_data_sufficiency(self) -> str:
        """Determine if there's enough data to justify an Opus evaluation call."""
        non_fork_repos = [r for r in self.top_repos if not r.is_fork]
        has_bio = bool(self.user.bio and len(self.user.bio) > 10)
        has_repos = len(non_fork_repos) >= 1
        has_activity = any(c > 0 for c in self.contribution_months.values())

        # Strong prior: frontier contributions, high followers, or starred repos
        has_strong_prior = (
            bool(self.frontier_contributions) or
            self.user.followers > 200 or
            any(r.stars > 50 for r in non_fork_repos)
        )

        if has_strong_prior:
            self.data_sufficiency = "sufficient"
        elif has_repos and (has_bio or has_activity):
            self.data_sufficiency = "sufficient"
        elif has_repos or has_bio:
            self.data_sufficiency = "minimal"
        else:
            self.data_sufficiency = "insufficient"

        return self.data_sufficiency


# ---------------------------------------------------------------------------
# GitHub search query (analogous to SearchString for LinkedIn)
# ---------------------------------------------------------------------------

@dataclass
class GitHubSearchQuery:
    """A single search query to execute against GitHub API."""
    id: int
    name: str  # human-readable description
    query: str  # GitHub search query string
    channel: str  # "user_search" | "code_search" | "repo_mining" | "org_exploration" | "topic_search" | "stargazer_mining" | "graph_expansion"
    status: str = "queued"  # "queued" | "in_progress" | "done" | "skipped"
    result_count: int = 0
    candidates_discovered: int = 0
    saves: list[str] = field(default_factory=list)
    notes: str = ""
    # For repo mining: the specific repo to mine
    target_repo: str = ""  # "owner/repo"
    # For org exploration: the specific org
    target_org: str = ""
    # Auto-segmentation tracking
    parent_query_id: Optional[int] = None  # if this was auto-segmented from a larger query
    hit_result_cap: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> GitHubSearchQuery:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# GitHub progress checkpoint
# ---------------------------------------------------------------------------

@dataclass
class GitHubProgress:
    """Resumable checkpoint for GitHub sourcing sessions."""
    brief_name: str
    queries: list[GitHubSearchQuery] = field(default_factory=list)
    candidates_discovered: int = 0
    candidates_enriched: int = 0
    candidates_saved: int = 0
    candidates_rejected: int = 0
    candidates_insufficient: int = 0
    current_query_id: Optional[int] = None
    discovered_usernames: list[str] = field(default_factory=list)  # global dedup (serialized as list)
    mined_repos: list[str] = field(default_factory=list)  # repos whose contributors have been fetched
    api_calls_made: int = 0
    graph_expansion_queue: list[dict] = field(default_factory=list)
    # Each entry: {"username": "...", "reason": "SAVE", "confidence": 0.85, "capability_area": "...", "added_at": "..."}
    graph_expansion_processed: list[str] = field(default_factory=list)  # usernames already processed

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> GitHubProgress:
        queries = [GitHubSearchQuery.from_dict(q) for q in d.get("queries", [])]
        return cls(
            brief_name=d["brief_name"],
            queries=queries,
            candidates_discovered=d.get("candidates_discovered", 0),
            candidates_enriched=d.get("candidates_enriched", 0),
            candidates_saved=d.get("candidates_saved", 0),
            candidates_rejected=d.get("candidates_rejected", 0),
            candidates_insufficient=d.get("candidates_insufficient", 0),
            current_query_id=d.get("current_query_id"),
            discovered_usernames=d.get("discovered_usernames", []),
            mined_repos=d.get("mined_repos", []),
            api_calls_made=d.get("api_calls_made", 0),
            graph_expansion_queue=d.get("graph_expansion_queue", []),
            graph_expansion_processed=d.get("graph_expansion_processed", []),
        )

    @classmethod
    def from_file(cls, path: str) -> GitHubProgress:
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def save(self, path: str) -> None:
        from pathlib import Path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(self.to_json())


# ---------------------------------------------------------------------------
# GitHub batch report (for strategy adaptation)
# ---------------------------------------------------------------------------

@dataclass
class GitHubBatchReport:
    """Summary of a batch of queries, sent to Opus for adaptation."""
    batch_name: str
    queries_run: int = 0
    queries_with_saves: int = 0
    total_candidates_discovered: int = 0
    total_saves: int = 0
    total_rejects: int = 0
    total_insufficient: int = 0
    top_performing_queries: list[dict] = field(default_factory=list)
    zero_save_query_ids: list[int] = field(default_factory=list)
    common_languages_in_saves: list[str] = field(default_factory=list)
    common_repos_in_saves: list[str] = field(default_factory=list)
    queries_hitting_result_cap: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_summary_text(self) -> str:
        lines = [f'Batch "{self.batch_name}" — {self.queries_run} queries complete.']
        lines.append(f"- {self.total_candidates_discovered} candidates discovered, {self.total_saves} saved, {self.total_rejects} rejected, {self.total_insufficient} insufficient data")
        if self.top_performing_queries:
            top = ", ".join(
                f"Query #{q['query_id']} \"{q.get('name', '')}\" ({q.get('saves', 0)} saves)"
                for q in self.top_performing_queries
            )
            lines.append(f"- Top performers: {top}")
        if self.zero_save_query_ids:
            lines.append(f"- Zero-save queries: {', '.join(f'#{qid}' for qid in self.zero_save_query_ids)}")
        if self.common_languages_in_saves:
            lines.append(f"- Common languages in saves: {', '.join(self.common_languages_in_saves)}")
        if self.common_repos_in_saves:
            lines.append(f"- Common repos in saves: {', '.join(self.common_repos_in_saves)}")
        if self.queries_hitting_result_cap:
            lines.append(f"- Queries hitting 1,000 cap: {', '.join(f'#{qid}' for qid in self.queries_hitting_result_cap)}")
        return "\n".join(lines)
