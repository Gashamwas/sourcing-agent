"""Prepare GitHub-sourced leads for LinkedIn reconciliation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from github.schemas import ContactInfo
from shared.identity_resolution import summarize_email_domains
from shared.reconciliation_schemas import LinkedInIdentityHints
from shared.storage import read_jsonl

SAVE_DECISIONS = {"SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE", "SIGNAL_SAVE"}


@dataclass
class GitHubReconciliationLead:
    username: str
    candidate_name: str
    github_url: str
    company: str = ""
    location: str = ""
    title: str = ""
    decision: str = ""
    confidence: float = 0.0
    rationale: str = ""
    source_query: str = ""
    source_channel: str = ""
    linkedin_hints: LinkedInIdentityHints | None = None
    candidate_payload: dict = field(default_factory=dict)
    judgment_payload: dict = field(default_factory=dict)
    outreach_payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = asdict(self)
        if self.linkedin_hints is None:
            payload["linkedin_hints"] = None
        return payload


@dataclass
class GitHubReconciliationLoadStats:
    total_saved_judgments: int = 0
    leads_loaded: int = 0
    skipped_missing_name: int = 0
    skipped_ambiguous_name: int = 0
    skipped_unmatched_profile_url: int = 0
    skipped_missing_candidate: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GitHubReconciliationLoadBatch:
    leads: list[GitHubReconciliationLead]
    stats: GitHubReconciliationLoadStats


def _normalize_github_profile_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw.rstrip("/")
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    if netloc.endswith("github.com"):
        scheme = "https"
    if scheme in {"http", "https"} and netloc:
        return urlunsplit((scheme, netloc, path, "", ""))
    return raw.rstrip("/")


def _build_contact(record: dict) -> ContactInfo:
    contact = record.get("contact", {}) if isinstance(record.get("contact"), dict) else {}
    return ContactInfo(
        emails=list(contact.get("emails", []) or []),
        linkedin_url=str(contact.get("linkedin_url", "") or "").strip(),
        twitter_url=str(contact.get("twitter_url", "") or "").strip(),
        website=str(contact.get("website", "") or "").strip(),
    )


def build_identity_hints(candidate_record: dict, judgment_record: dict | None = None) -> LinkedInIdentityHints:
    user = candidate_record.get("user", {}) if isinstance(candidate_record.get("user"), dict) else {}
    contact = _build_contact(candidate_record)
    emails = [email for email in contact.emails if "@" in email]
    profile_url = str(user.get("profile_url", "") or "").strip()
    title = (
        str(candidate_record.get("synthesized_headline", "") or "").strip()
        or str(user.get("bio", "") or "").strip()
    )
    candidate_name = str(user.get("name", "") or "").strip() or str(user.get("username", "") or "").strip()
    source_query = str(candidate_record.get("source_query", "") or "").strip()
    source_channel = str(candidate_record.get("source_strategy", "") or "").strip()
    if judgment_record and not title:
        title = str(judgment_record.get("candidate_title", "") or "").strip()

    return LinkedInIdentityHints(
        candidate_name=candidate_name,
        github_username=str(user.get("username", "") or "").strip(),
        github_url=profile_url,
        linkedin_url_hint=contact.linkedin_url,
        company=str(user.get("company", "") or "").strip(),
        location=str(user.get("location", "") or "").strip(),
        title=title,
        emails=emails,
        email_domains=summarize_email_domains(emails),
        source_query=source_query,
        source_channel=source_channel,
    )


def load_github_reconciliation_batch(output_dir: str | Path) -> GitHubReconciliationLoadBatch:
    output_dir = Path(output_dir)
    candidates = read_jsonl(output_dir / "candidates.jsonl")
    judgments = read_jsonl(output_dir / "final_judgments.jsonl")
    outreach = read_jsonl(output_dir / "outreach.jsonl")
    stats = GitHubReconciliationLoadStats()

    candidate_by_username: dict[str, dict] = {}
    candidate_by_profile_url: dict[str, dict] = {}
    usernames_by_name: dict[str, list[str]] = {}
    for record in candidates:
        user = record.get("user", {}) if isinstance(record.get("user"), dict) else {}
        username = str(record.get("username", "") or user.get("username", "") or "").strip()
        if not username:
            continue
        candidate_by_username[username] = record
        profile_url = _normalize_github_profile_url(str(user.get("profile_url", "") or "").strip())
        if profile_url:
            candidate_by_profile_url[profile_url] = record
        candidate_name = str(user.get("name", "") or "").strip()
        if candidate_name:
            usernames_by_name.setdefault(candidate_name, []).append(username)
        usernames_by_name.setdefault(username, []).append(username)

    outreach_by_username = {
        str(record.get("username", "") or "").strip(): record
        for record in outreach
        if str(record.get("username", "") or "").strip()
    }

    leads: list[GitHubReconciliationLead] = []
    for judgment in judgments:
        if judgment.get("stage") != "full":
            continue
        if judgment.get("decision") not in SAVE_DECISIONS:
            continue
        stats.total_saved_judgments += 1
        candidate_name = str(judgment.get("candidate_name", "") or "").strip()
        if not candidate_name:
            stats.skipped_missing_name += 1
            continue
        judgment_profile_url = _normalize_github_profile_url(str(judgment.get("profile_url", "") or "").strip())
        candidate_record = candidate_by_profile_url.get(judgment_profile_url)
        username = ""
        if candidate_record:
            user = candidate_record.get("user", {}) if isinstance(candidate_record.get("user"), dict) else {}
            username = str(candidate_record.get("username", "") or user.get("username", "") or "").strip()
        elif judgment_profile_url:
            stats.skipped_unmatched_profile_url += 1
            continue
        else:
            matching_usernames = usernames_by_name.get(candidate_name, [])
            if len(matching_usernames) == 1:
                username = matching_usernames[0]
                candidate_record = candidate_by_username.get(username)
            else:
                stats.skipped_ambiguous_name += 1
                continue
        if not candidate_record:
            stats.skipped_missing_candidate += 1
            continue
        user = candidate_record.get("user", {}) if isinstance(candidate_record.get("user"), dict) else {}
        hints = build_identity_hints(candidate_record, judgment)
        leads.append(
            GitHubReconciliationLead(
                username=username,
                candidate_name=hints.candidate_name or candidate_name,
                github_url=str(user.get("profile_url", "") or "").strip(),
                company=hints.company,
                location=hints.location,
                title=hints.title,
                decision=str(judgment.get("decision", "") or "").strip(),
                confidence=float(judgment.get("confidence", 0.0) or 0.0),
                rationale=str(judgment.get("rationale", "") or "").strip(),
                source_query=hints.source_query,
                source_channel=hints.source_channel,
                linkedin_hints=hints,
                candidate_payload=candidate_record,
                judgment_payload=judgment,
                outreach_payload=outreach_by_username.get(username, {}),
            )
        )
    stats.leads_loaded = len(leads)
    return GitHubReconciliationLoadBatch(leads=leads, stats=stats)


def load_saved_github_leads(output_dir: str | Path) -> list[GitHubReconciliationLead]:
    return load_github_reconciliation_batch(output_dir).leads
