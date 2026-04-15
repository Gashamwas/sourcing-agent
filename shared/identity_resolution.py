"""Deterministic identity and novelty scoring helpers."""

from __future__ import annotations

import re
from collections import Counter

from shared.reconciliation_schemas import (
    LinkedInIdentityHints,
    LinkedInMatchResult,
    RecruiterActivitySnapshot,
)

_CREDENTIAL_SUFFIX_RE = re.compile(
    r"\b(phd|ph\.d|mba|m\.s|ms|m\.sc|msc|dr|cfa|pmp|pe|frsa)\b\.?",
    re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[^a-z0-9\s]")
_COMPANY_SUFFIX_RE = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|holdings|group|co|company|technologies|technology)\b\.?",
    re.IGNORECASE,
)
_STOPWORDS = {
    "and",
    "of",
    "the",
    "in",
    "at",
    "for",
    "to",
    "new",
    "york",
    "city",
    "area",
    "greater",
    "metropolitan",
    "united",
    "states",
}


def _normalize_text(value: str) -> str:
    value = str(value or "").lower().strip()
    value = _CREDENTIAL_SUFFIX_RE.sub(" ", value)
    value = _PUNCT_RE.sub(" ", value)
    value = " ".join(value.split())
    return value


def _tokenize(value: str) -> list[str]:
    normalized = _normalize_text(value)
    return [token for token in normalized.split() if token and token not in _STOPWORDS]


def normalize_person_name(value: str) -> str:
    return _normalize_text(value)


def normalize_company_name(value: str) -> str:
    value = _COMPANY_SUFFIX_RE.sub(" ", value or "")
    return _normalize_text(value)


def normalize_location_text(value: str) -> str:
    return _normalize_text(value)


def build_candidate_lookup_queries(hints: LinkedInIdentityHints) -> list[str]:
    """Build bounded LinkedIn Recruiter keyword queries for a GitHub lead."""
    name = hints.candidate_name.strip()
    company = normalize_company_name(hints.company)
    location_tokens = _tokenize(hints.location)
    title_tokens = _tokenize(hints.title)
    queries: list[str] = []

    if not name:
        return queries

    quoted_name = f'"{name}"'
    company_terms = sorted({f'"{token}"' for token in company.split() if token})
    location_terms = sorted({f'"{token}"' for token in location_tokens[:3]})
    title_terms = sorted({f'"{token}"' for token in title_tokens[:4]})

    if company:
        company_query = f"{quoted_name} AND ({' OR '.join(company_terms)})"
        queries.append(company_query)

    if location_tokens:
        location_query = f"{quoted_name} AND ({' OR '.join(location_terms)})"
        queries.append(location_query)

    if company and location_tokens:
        combined = (
            f"{quoted_name} AND "
            f"({' OR '.join(company_terms)}) AND "
            f"({' OR '.join(location_terms)})"
        )
        queries.insert(0, combined)

    if title_tokens:
        title_query = f"{quoted_name} AND ({' OR '.join(title_terms)})"
        queries.append(title_query)

    queries.append(quoted_name)

    seen: set[str] = set()
    deduped: list[str] = []
    for query in queries:
        query = " ".join(query.split())
        if query and query not in seen:
            seen.add(query)
            deduped.append(query)
    return deduped[:5]


def resolve_direct_linkedin_hint(
    hints: LinkedInIdentityHints,
) -> LinkedInMatchResult | None:
    """Return a direct-hint match when GitHub already points to LinkedIn."""
    url = (hints.linkedin_url_hint or "").strip()
    if not url:
        return None
    ambiguity_reasons: list[str] = []
    if "/talent/profile/" not in url:
        ambiguity_reasons.append("Recruiter activity unavailable until a Recruiter profile is resolved")
    return LinkedInMatchResult(
        matched_profile_url=url,
        matched_name=hints.candidate_name,
        matched_company=hints.company,
        matched_title=hints.title,
        matched_location=hints.location,
        match_confidence=0.96,
        match_method="direct_linkedin_hint",
        evidence=["Direct LinkedIn URL hint present"],
        ambiguity_reasons=ambiguity_reasons,
        recruiter_activity=None,
        novelty_pressure="",
    )


def classify_recruiter_activity_pressure(activity: RecruiterActivitySnapshot | None) -> str:
    """Convert recruiter activity into a conservative novelty pressure label."""
    if not activity:
        return "low"
    if activity.message_count >= 6 or (activity.project_count >= 3 and activity.view_count >= 3):
        return "high"
    if activity.message_count >= 3 or activity.project_count >= 2 or activity.view_count >= 4:
        return "medium"
    return "low"


def infer_reachout_status(activity: RecruiterActivitySnapshot | None) -> str:
    if not activity:
        return ""
    if activity.last_outbound_contact:
        return "recent_outbound_contact"
    if activity.message_count > 0:
        return "messaged"
    if activity.project_count > 0:
        return "in_projects"
    return "unworked"


def score_linkedin_identity_match(
    hints: LinkedInIdentityHints,
    *,
    matched_name: str,
    matched_company: str = "",
    matched_title: str = "",
    matched_location: str = "",
    matched_profile_url: str = "",
    recruiter_activity: RecruiterActivitySnapshot | None = None,
    match_method: str = "search",
) -> LinkedInMatchResult:
    """Score a likely LinkedIn identity match from normalized hints."""
    evidence: list[str] = []
    ambiguity_reasons: list[str] = []
    score = 0.0

    expected_name = normalize_person_name(hints.candidate_name)
    actual_name = normalize_person_name(matched_name)
    if expected_name and actual_name:
        if expected_name == actual_name:
            score += 0.55
            evidence.append("Exact name match")
        else:
            expected_tokens = set(_tokenize(expected_name))
            actual_tokens = set(_tokenize(actual_name))
            overlap = len(expected_tokens & actual_tokens)
            if overlap >= max(1, min(len(expected_tokens), len(actual_tokens)) - 1):
                score += 0.35
                evidence.append("Strong partial name overlap")
            else:
                ambiguity_reasons.append("Name mismatch")

    expected_company_tokens = set(_tokenize(normalize_company_name(hints.company)))
    actual_company_tokens = set(_tokenize(normalize_company_name(matched_company)))
    if expected_company_tokens and actual_company_tokens:
        overlap = len(expected_company_tokens & actual_company_tokens)
        if overlap:
            score += min(0.2, 0.08 * overlap)
            evidence.append("Company overlap")
        else:
            ambiguity_reasons.append("Company mismatch")

    expected_location_tokens = set(_tokenize(normalize_location_text(hints.location)))
    actual_location_tokens = set(_tokenize(normalize_location_text(matched_location)))
    if expected_location_tokens and actual_location_tokens:
        overlap = len(expected_location_tokens & actual_location_tokens)
        if overlap:
            score += min(0.1, 0.04 * overlap)
            evidence.append("Location overlap")
        else:
            ambiguity_reasons.append("Location mismatch")

    expected_title = _normalize_text(hints.title)
    actual_title = _normalize_text(matched_title)
    title_overlap = len(set(_tokenize(hints.title)) & set(_tokenize(matched_title)))
    if expected_title and actual_title and expected_title == actual_title:
        score += 0.15
        evidence.append("Exact title match")
    elif title_overlap:
        score += min(0.1, 0.03 * title_overlap)
        evidence.append("Title overlap")

    if recruiter_activity and recruiter_activity.saved_by:
        evidence.append(f"Recruiter activity visible (saved by {recruiter_activity.saved_by})")

    score = min(score, 1.0)
    novelty_pressure = classify_recruiter_activity_pressure(recruiter_activity)
    return LinkedInMatchResult(
        matched_profile_url=matched_profile_url,
        matched_name=matched_name,
        matched_company=matched_company,
        matched_title=matched_title,
        matched_location=matched_location,
        match_confidence=round(score, 3),
        match_method=match_method,
        evidence=evidence,
        ambiguity_reasons=ambiguity_reasons,
        recruiter_activity=recruiter_activity,
        novelty_pressure=novelty_pressure,
    )


def choose_best_match(matches: list[LinkedInMatchResult]) -> tuple[str, LinkedInMatchResult | None]:
    """Classify a set of match candidates into high/manual/none buckets."""
    if not matches:
        return "no_confident_match", None
    ranked = sorted(matches, key=lambda item: item.match_confidence, reverse=True)
    best = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    if best.match_confidence >= 0.85 and (second is None or best.match_confidence - second.match_confidence >= 0.15):
        return "high_confidence_match", best
    if best.match_confidence >= 0.6:
        return "manual_review", best
    return "no_confident_match", None


def summarize_email_domains(emails: list[str]) -> list[str]:
    domains = [email.split("@", 1)[1].lower() for email in emails if "@" in email]
    counts = Counter(domains)
    return [domain for domain, _count in counts.most_common(3)]
