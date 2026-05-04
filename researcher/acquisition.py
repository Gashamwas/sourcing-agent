"""Researcher acquisition — Slice 4.

Execute one researcher query against OpenAlex, paginate, dedup by
``author_id``, hand off to disambiguation. The result is a list of
:class:`ResearcherCandidate` records ready for the deterministic gates
+ LLM evaluators at Slice 5.

The query dict shape is the one produced by
:func:`researcher.strategy.form_strategy` — see
:data:`researcher.strategy.RESEARCHER_QUERY_SCHEMA_KEYS`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from researcher.schemas import ResearcherCandidate, ResearcherPaper
from researcher.sources.openalex import OpenAlexClient


# Default per-query result cap. The orchestrator (Slice 6) can override.
_DEFAULT_MAX_AUTHORS = 200


@dataclass
class AcquisitionResult:
    """Outcome of a single query execution."""

    query_id: int
    query_name: str
    candidates: list[ResearcherCandidate] = field(default_factory=list)
    pages_fetched: int = 0
    raw_authors_seen: int = 0
    duplicates_skipped: int = 0
    truncated: bool = False  # True when we hit max_authors before exhausting

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "query_name": self.query_name,
            "candidate_count": len(self.candidates),
            "pages_fetched": self.pages_fetched,
            "raw_authors_seen": self.raw_authors_seen,
            "duplicates_skipped": self.duplicates_skipped,
            "truncated": self.truncated,
        }


def execute_query(
    *,
    query: dict,
    client: OpenAlexClient,
    papers_in_window_months: int = 36,
    max_authors: int = _DEFAULT_MAX_AUTHORS,
    per_page: int = 25,
    now: datetime | None = None,
) -> AcquisitionResult:
    """Execute a researcher query against OpenAlex; return deduped candidates.

    The query dict matches the strategy output:
    ``{topic_concepts, venue_filter, min_year, min_citations,
    ror_country_filter, id, name, ...}``.

    Pagination uses OpenAlex's cursor protocol (``cursor=*`` initial,
    then ``meta.next_cursor`` from each response). Stops when:
    - ``meta.next_cursor`` is null/empty (exhaustion), or
    - we've collected ``max_authors`` unique candidates (truncation).
    """

    now = now or datetime.now(timezone.utc)
    window_start_year = now.year - max(0, int(papers_in_window_months) // 12)

    seen_author_ids: set[str] = set()
    candidates: list[ResearcherCandidate] = []
    pages_fetched = 0
    raw_authors_seen = 0
    duplicates_skipped = 0
    cursor = "*"
    truncated = False

    concept_ids = _as_str_list(query.get("topic_concepts"))
    country_codes = _as_str_list(query.get("ror_country_filter"))
    min_citations = int(query.get("min_citations") or 0)

    while cursor and len(candidates) < max_authors:
        response = client.search_authors(
            concept_ids=concept_ids or None,
            country_codes=country_codes or None,
            min_citations=min_citations or None,
            cursor=cursor,
            per_page=per_page,
        )
        pages_fetched += 1

        results = response.get("results") or []
        for raw in results:
            raw_authors_seen += 1
            author_id = _extract_author_id(raw)
            if not author_id:
                continue
            if author_id in seen_author_ids:
                duplicates_skipped += 1
                continue
            seen_author_ids.add(author_id)
            candidates.append(
                _build_candidate(
                    raw,
                    window_start_year=window_start_year,
                )
            )
            if len(candidates) >= max_authors:
                truncated = True
                break

        cursor = ((response.get("meta") or {}).get("next_cursor") or "") if not truncated else ""

    return AcquisitionResult(
        query_id=int(query.get("id") or 0),
        query_name=str(query.get("name") or ""),
        candidates=candidates,
        pages_fetched=pages_fetched,
        raw_authors_seen=raw_authors_seen,
        duplicates_skipped=duplicates_skipped,
        truncated=truncated,
    )


def _build_candidate(
    raw: dict,
    *,
    window_start_year: int,
) -> ResearcherCandidate:
    """Build a :class:`ResearcherCandidate` from one OpenAlex author dict."""

    author_id = _extract_author_id(raw)
    orcid = str(raw.get("orcid") or "").strip()
    name = str(raw.get("display_name") or "").strip()

    affiliations = _extract_affiliations(raw)
    summary = raw.get("summary_stats") or {}
    h_index = int(summary.get("h_index") or 0)
    citation_count = int(raw.get("cited_by_count") or 0)
    works_count = int(raw.get("works_count") or 0)

    counts_by_year = raw.get("counts_by_year") or []
    papers_in_window = sum(
        int(c.get("works_count") or 0)
        for c in counts_by_year
        if isinstance(c, dict) and int(c.get("year") or 0) >= window_start_year
    )

    profile_url = (
        f"https://orcid.org/{_bare_orcid(orcid)}"
        if orcid
        else (raw.get("id") or f"https://openalex.org/{author_id}")
    )

    top_papers = _extract_top_papers(raw)

    return ResearcherCandidate(
        author_id=author_id,
        orcid=orcid,
        name=name,
        affiliations=affiliations,
        top_papers=top_papers,
        h_index=h_index,
        citation_count=citation_count,
        works_count=works_count,
        papers_in_window=papers_in_window,
        profile_url=profile_url,
        raw_openalex=raw,
    )


def _extract_author_id(raw: dict) -> str:
    """OpenAlex authors carry an id like ``https://openalex.org/A1234``.

    We store the bare ``A1234`` for stable comparison.
    """

    raw_id = str(raw.get("id") or "").strip()
    if not raw_id:
        return ""
    for prefix in (
        "https://openalex.org/",
        "http://openalex.org/",
        "openalex.org/",
    ):
        if raw_id.startswith(prefix):
            return raw_id[len(prefix):]
    return raw_id


def _extract_affiliations(raw: dict) -> list[str]:
    affiliations: list[str] = []
    for inst in raw.get("last_known_institutions") or []:
        if not isinstance(inst, dict):
            continue
        name = str(inst.get("display_name") or "").strip()
        country = str(inst.get("country_code") or "").strip()
        if name and country:
            affiliations.append(f"{name} ({country})")
        elif name:
            affiliations.append(name)
    return affiliations


def _extract_top_papers(raw: dict) -> list[ResearcherPaper]:
    """OpenAlex author payloads optionally embed top works under
    ``top_works`` (Cloris's enrichment may also stuff the works list
    here at acquisition time). Defensive: handle absence.
    """

    works = raw.get("top_works") or raw.get("works") or []
    papers: list[ResearcherPaper] = []
    for w in works:
        if not isinstance(w, dict):
            continue
        title = str(w.get("title") or w.get("display_name") or "").strip()
        if not title:
            continue
        venue = ""
        primary_loc = w.get("primary_location") or {}
        source = primary_loc.get("source") if isinstance(primary_loc, dict) else None
        if isinstance(source, dict):
            venue = str(source.get("display_name") or "").strip()
        publication_year = int(w.get("publication_year") or 0)
        cited_by = int(w.get("cited_by_count") or 0)
        first_author_position = False
        authorships = w.get("authorships") or []
        if isinstance(authorships, list) and authorships:
            first = authorships[0]
            if isinstance(first, dict):
                first_author_position = (
                    str(first.get("author_position") or "").lower() == "first"
                )
        openalex_id = str(w.get("id") or "").strip()
        papers.append(
            ResearcherPaper(
                title=title,
                venue=venue,
                year=publication_year,
                citation_count=cited_by,
                is_first_author=first_author_position,
                openalex_id=openalex_id,
            )
        )
    return papers[:5]


def _bare_orcid(orcid: str) -> str:
    candidate = orcid.strip()
    for prefix in ("https://orcid.org/", "http://orcid.org/", "orcid.org/"):
        if candidate.startswith(prefix):
            return candidate[len(prefix):]
    return candidate


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if isinstance(v, str) and str(v).strip()]
