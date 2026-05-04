"""Researcher strategy formation — Slice 3.

`form_strategy(brief, prior_data)` produces an :class:`ExecutionPlan`
whose ``generated_strings`` carry researcher query dicts (NOT human-
readable Boolean strings — see Researcher Module Spec Opinion 2).

Each query is one work_unit with ``kind="researcher_author_query"``;
the acquisition layer (Slice 4) hydrates it into OpenAlex API calls.

Brief blocks consumed:

- ``capability_areas`` → mapped to OpenAlex Concept IDs (the LLM picks
  the right concepts given the capability prose)
- ``source_config.researcher.research_topics`` → additive prompt context
  (free-text topics the recruiter named; the LLM blends them with the
  concept mapping)
- ``source_config.researcher.conference_allowlist`` → seed
  ``venue_filter`` (the LLM may emit per-venue queries)
- ``source_config.researcher.h_index_floor`` +
  ``papers_in_window_floor`` → passed through to the deterministic
  gates at evaluation time (Slice 5); strategy doesn't filter on them
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from shared.brief_schema import Brief
from shared.brief_v2_schema import source_config_for
from shared.schemas import ExecutionPlan


RESEARCHER_QUERY_SCHEMA_KEYS = (
    "topic_concepts",
    "venue_filter",
    "min_year",
    "min_citations",
    "ror_country_filter",
)


def form_strategy(
    brief: Brief,
    prior_data: dict | None = None,
    *,
    llm_caller: Callable[[str, str], dict] | None = None,
) -> ExecutionPlan:
    """Compose an :class:`ExecutionPlan` for the researcher pipeline.

    ``llm_caller`` is injectable so tests don't require a real Opus call;
    when ``None``, defaults to ``shared.llm_clients.opus_llm`` with
    JSON-expecting kwargs. Production callers leave it ``None``.

    The plan's ``generated_strings`` field carries researcher query
    dicts conforming to :data:`RESEARCHER_QUERY_SCHEMA_KEYS`. The
    orchestrator (Slice 6) wraps each into a SearchString-shaped
    work_unit; the boolean field stays empty per Spec Opinion 2.
    """

    raw_brief = _brief_raw(brief)
    source_config = source_config_for(raw_brief, "researcher")

    system = _build_system_prompt(brief, source_config)
    user_prompt = _build_user_prompt(brief, source_config, prior_data)

    if llm_caller is None:
        from shared.llm_clients import opus_llm

        def _default_caller(s: str, u: str) -> dict:
            return opus_llm(s, u, expect_json=True, max_tokens=16384)

        llm_caller = _default_caller

    result = llm_caller(system, user_prompt)
    return _parse_plan(result, source_config=source_config)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _build_system_prompt(brief: Brief, source_config: dict[str, Any]) -> str:
    """Assemble the cacheable system prompt — all brief context, no LLM
    output coupling.
    """

    capability_block = _capability_area_block(brief)
    venue_seed = ", ".join(_as_str_list(source_config.get("conference_allowlist")))
    research_topics = ", ".join(_as_str_list(source_config.get("research_topics")))
    discipline = _as_str(source_config.get("discipline"))

    return _SYSTEM_TEMPLATE.format(
        role_title=brief.role_title or "(unspecified)",
        role_summary=getattr(brief, "role_summary", "") or "(none)",
        capability_block=capability_block,
        research_topics=research_topics or "(none specified)",
        venue_seed=venue_seed or "(none specified — pick canonical venues)",
        discipline=discipline or "ml_general",
    )


def _build_user_prompt(
    brief: Brief,
    source_config: dict[str, Any],
    prior_data: dict | None,
) -> str:
    """Assemble the per-call user prompt — instruction + output contract."""

    prior_summary = _summarize_prior_data(prior_data)
    return _USER_TEMPLATE.format(
        prior_summary=prior_summary,
        query_schema_keys=", ".join(RESEARCHER_QUERY_SCHEMA_KEYS),
    )


def _capability_area_block(brief: Brief) -> str:
    areas = getattr(brief, "capability_areas", None) or []
    if not areas:
        return "(no capability areas declared — fall back to brief.role_summary)"
    lines: list[str] = []
    for idx, area in enumerate(areas, start=1):
        name = getattr(area, "name", None) or ""
        description = getattr(area, "description", None) or ""
        lines.append(f"  {idx}. {name}")
        if description:
            lines.append(f"     — {description}")
    return "\n".join(lines)


def _summarize_prior_data(prior_data: dict | None) -> str:
    if not prior_data:
        return "(no prior run data — this is a fresh strategy)"
    lines = ["Prior run hints:"]
    if "queries_explored" in prior_data:
        lines.append(f"  - queries explored: {prior_data['queries_explored']}")
    if "underperforming_concepts" in prior_data:
        lines.append(
            f"  - concepts underperforming: {prior_data['underperforming_concepts']}"
        )
    if "high_yield_venues" in prior_data:
        lines.append(f"  - high-yield venues: {prior_data['high_yield_venues']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Plan parsing / normalization
# ---------------------------------------------------------------------------


def _parse_plan(
    result: dict,
    *,
    source_config: dict[str, Any],
) -> ExecutionPlan:
    """Normalize the LLM output into a clean :class:`ExecutionPlan`.

    Defensive against missing or malformed keys: missing
    ``generated_strings`` ⇒ empty list (caller surfaces an
    "empty_search_results" stop reason); each query dict gets its
    keys defaulted so the acquisition layer can rely on the shape.
    """

    plan_dict = dict(result or {})
    raw_queries = plan_dict.get("generated_strings") or []
    if not isinstance(raw_queries, list):
        raw_queries = []

    normalized: list[dict] = []
    for idx, raw in enumerate(raw_queries):
        if not isinstance(raw, dict):
            continue
        normalized.append(_normalize_query(raw, idx=idx, source_config=source_config))

    plan_dict["generated_strings"] = normalized
    return ExecutionPlan.from_dict(plan_dict)


def _normalize_query(
    raw: dict,
    *,
    idx: int,
    source_config: dict[str, Any],
) -> dict:
    """Coerce one query dict into the canonical schema."""

    topic_concepts = _as_str_list(raw.get("topic_concepts"))
    venue_filter = _as_str_list(raw.get("venue_filter")) or _as_str_list(
        source_config.get("conference_allowlist")
    )
    ror_country_filter = _as_str_list(raw.get("ror_country_filter"))

    min_year_raw = raw.get("min_year")
    min_year = int(min_year_raw) if isinstance(min_year_raw, (int, float)) else 0

    min_citations_raw = raw.get("min_citations")
    min_citations = (
        int(min_citations_raw) if isinstance(min_citations_raw, (int, float)) else 0
    )

    name = _as_str(raw.get("name")) or _default_query_name(
        idx=idx,
        topic_concepts=topic_concepts,
        venue_filter=venue_filter,
    )

    return {
        # SearchString-compatible identity fields so the orchestrator
        # can wrap this into a work_unit uniformly.
        "id": int(raw.get("id") or idx + 1),
        "name": name,
        "boolean": "",  # Spec Opinion 2: no Boolean string layer for researcher.
        "string_type": "Recall",
        # The actual researcher query parameters.
        "topic_concepts": topic_concepts,
        "venue_filter": venue_filter,
        "min_year": min_year,
        "min_citations": min_citations,
        "ror_country_filter": ror_country_filter,
    }


def _default_query_name(
    *,
    idx: int,
    topic_concepts: list[str],
    venue_filter: list[str],
) -> str:
    parts: list[str] = []
    if topic_concepts:
        parts.append("+".join(topic_concepts[:2]))
    if venue_filter:
        parts.append("/".join(venue_filter[:2]))
    if not parts:
        return f"query-{idx + 1}"
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Brief raw access
# ---------------------------------------------------------------------------


def _brief_raw(brief: Brief) -> dict:
    """Return the V2 raw dict if the Brief was loaded via the V2 path.

    Falls back to a minimal dict synthesized from accessible fields when
    the brief is from the legacy path. Tests can pass any object that
    duck-types as :class:`Brief` plus an optional ``_new_brief`` shim.
    """

    raw = getattr(brief, "_new_brief", None)
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "raw_dict"):
        candidate = raw.raw_dict()
        if isinstance(candidate, dict):
            return candidate
    return {}


def _as_str(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if isinstance(v, str) and str(v).strip()]


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


_SYSTEM_TEMPLATE = """\
You are Cloris, generating a search strategy for the Researcher module
against the OpenAlex academic publication graph. The recruiter authored a
brief; your job is to translate it into N concrete OpenAlex queries that
will surface qualified researchers.

ROLE CONTEXT
  Title: {role_title}
  Summary: {role_summary}
  Field discipline: {discipline}

CAPABILITY AREAS (recruiter's "what this person ships"):
{capability_block}

RECRUITER-AUTHORED RESEARCH TOPICS (additive context — blend with the
capability areas; not a replacement):
  {research_topics}

VENUE SEED (recruiter-allowed conferences/journals — start here, expand
only if a capability area is poorly covered):
  {venue_seed}

QUERY DESIGN PRINCIPLES
  1. Each query targets ONE conceptual axis (don't AND four concepts
     together — diluting your concept set will surface nobody).
  2. Spread queries across the capability areas; no single area should
     dominate.
  3. Venue-driven queries (filtering works at NeurIPS/ICML/ICLR) are
     stronger signal than concept-only queries when the brief names
     specific venues — prefer venue+concept combinations.
  4. Year window: default to last 36 months unless the role explicitly
     wants seasoned alumni (e.g., "research scientist with 10+ years
     publishing"); then widen to 60 months.
  5. min_citations is a courtesy filter for budget control, not an
     editorial bar. Use a low number (10–50) so deterministic gates at
     evaluation time can do their job.
"""


_USER_TEMPLATE = """\
{prior_summary}

OUTPUT: A JSON object with the following keys:

  - strategy_rationale (str): one paragraph explaining the overall plan.
  - generated_strings (list of query dicts): each dict has exactly
    these keys: {query_schema_keys}.
      - topic_concepts: list[str] of OpenAlex Concept IDs (e.g.,
        "C2778407487" for Natural Language Processing). Pick 1–3 per
        query; do not over-AND.
      - venue_filter: list[str] of OpenAlex Source IDs or venue names
        (e.g., "S4306420609" for NeurIPS, or just "NeurIPS"). Empty list
        is allowed for concept-only queries.
      - min_year: int, e.g., 2023.
      - min_citations: int, e.g., 20.
      - ror_country_filter: list[str] of ISO country codes (e.g., ["US",
        "GB", "CA"]). Empty list = global.
  - coverage_gaps (list of dicts): areas the strategy didn't reach;
    optional. Empty list is fine.
  - architecture (str): always "concept_first" for researcher v1.
  - architecture_rationale (str): one sentence explaining why this
    architecture fits the brief.

Emit 5–15 queries; spread across the capability areas. Output ONLY the
JSON object — no preamble, no markdown fences.
"""
