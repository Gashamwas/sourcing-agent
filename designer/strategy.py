"""Designer module — query formation from brief content.

Designer Slice 2. The strategy layer consumes a V2 brief and produces a
list of :class:`designer.schemas.DesignerSearchQuery` objects that
:mod:`designer.acquisition` executes against the per-source clients.

Slice 2 covers Behance only. Slice 3 extends with Google CSE queries
(filtered to portfolio-host domains). Both sources read from the same
V2 brief shape — Cloris doesn't fork the brief contract per source.

Brief content consumed:

- ``capability_areas[*].name`` + ``description`` — the recruiter's
  capability framing. Each capability area becomes one or more queries.
- ``capability_areas[*].behance_specialization_signals`` (optional) —
  list of strings the recruiter pasted that map to Behance creative-
  field tags or specialization vocab. If present, these become
  high-precision query terms.
- ``capability_areas[*].tool_stack_signals`` (optional) — Figma,
  After Effects, Cinema 4D, etc. Combined with capability area name
  to form tool-anchored queries.
- ``design_rubric.calibration_exemplars[*].discipline`` — used to bias
  the query distribution toward the discipline mix the recruiter
  exemplified (e.g., 4 product + 1 brand → product-weighted queries).
- ``geography`` (optional, top-level) — passed through as Behance's
  ``country`` filter when a 2-letter ISO code is detectable.

This module is deliberately small and deterministic. The Slice-2 spec
note on "Opus-driven query generation" lives in :mod:`designer.judgment_templates`
(prompts) plus a future LLM-assisted query expander (Slice 5+ when the
brief polish loop has more signal). For Slice 2, the query set is
recipe-style: walk capability areas, emit per-area queries, dedup.
"""

from __future__ import annotations

from typing import Any, Iterable

from designer.schemas import DesignerSearchQuery


# Behance's `sort` parameter values, in priority order. The first
# value is what every Slice-2 query uses by default; the others are
# available to callers that want to broaden the discovery surface
# (e.g., a "newer voices" pass would use `published_date`).
BEHANCE_SORT_PRIMARY = "appreciations"
BEHANCE_SORT_VALUES = ("appreciations", "views", "published_date")

# Cap on how many queries a single capability area generates. Without
# this, a brief with 5 specialization signals × 3 tool signals would
# produce 15 queries per capability area; at 4 capability areas that's
# 60 queries, exhausting Behance's per-hour budget on a single brief.
MAX_QUERIES_PER_CAPABILITY_AREA = 6


def form_designer_strategy(
    brief: dict[str, Any],
    *,
    sources: Iterable[str] = ("behance",),
) -> list[DesignerSearchQuery]:
    """Build the list of discovery queries for a Designer brief.

    Returns a deduped list of :class:`DesignerSearchQuery`. Queries are
    deterministic given identical input — important for tests and for
    runtime-state resume semantics (a re-run of the same brief produces
    the same work-units and so the same canonical work-unit IDs).

    ``sources`` is the set of source names to emit queries for. Slice 2
    handles ``"behance"`` only; passing ``("behance", "google_cse")``
    is a no-op for the CSE branch until Slice 3 lands.
    """

    queries: list[DesignerSearchQuery] = []
    seen: set[tuple[str, str]] = set()  # (source, query_text) for dedup

    capability_areas = brief.get("capability_areas") or []
    if not isinstance(capability_areas, list):
        return queries

    discipline = _dominant_discipline(brief)
    geography_code = _country_code(brief)

    for capability_area in capability_areas:
        if not isinstance(capability_area, dict):
            continue
        name = str(capability_area.get("name") or "").strip()
        if not name:
            continue

        if "behance" in sources:
            for query in _behance_queries_for_capability_area(
                capability_area=capability_area,
                discipline=discipline,
                geography_code=geography_code,
            ):
                key = (query.source, query.query_text.lower())
                if key in seen:
                    continue
                seen.add(key)
                queries.append(query)

        if "google_cse" in sources:
            for query in _google_cse_queries_for_capability_area(
                capability_area=capability_area,
                discipline=discipline,
            ):
                key = (query.source, query.query_text.lower())
                if key in seen:
                    continue
                seen.add(key)
                queries.append(query)

    return queries


def _behance_queries_for_capability_area(
    *,
    capability_area: dict[str, Any],
    discipline: str,
    geography_code: str,
) -> list[DesignerSearchQuery]:
    """Form Behance queries for one capability area.

    Recipe:
    1. Always emit the bare capability-area name as a query.
    2. Emit each ``behance_specialization_signals`` value as its own
       query (high precision; recruiter-authored vocab).
    3. Cross-product the top 2 specialization signals with the top 2
       tool signals as combined queries.
    4. Cap at ``MAX_QUERIES_PER_CAPABILITY_AREA``.
    """

    name = str(capability_area.get("name") or "").strip()
    extra_filters: dict[str, Any] = {}
    if geography_code:
        extra_filters["country"] = geography_code

    queries: list[DesignerSearchQuery] = [
        DesignerSearchQuery(
            source="behance",
            query_text=name,
            sort=BEHANCE_SORT_PRIMARY,
            capability_area_name=name,
            discipline=discipline,
            extra_filters=dict(extra_filters),
        )
    ]

    spec_signals = _as_str_list(capability_area.get("behance_specialization_signals"))
    tool_signals = _as_str_list(capability_area.get("tool_stack_signals"))

    for signal in spec_signals:
        queries.append(
            DesignerSearchQuery(
                source="behance",
                query_text=signal,
                sort=BEHANCE_SORT_PRIMARY,
                capability_area_name=name,
                discipline=discipline,
                extra_filters=dict(extra_filters),
            )
        )

    for signal in spec_signals[:2]:
        for tool in tool_signals[:2]:
            queries.append(
                DesignerSearchQuery(
                    source="behance",
                    query_text=f"{signal} {tool}",
                    sort=BEHANCE_SORT_PRIMARY,
                    capability_area_name=name,
                    discipline=discipline,
                    extra_filters=dict(extra_filters),
                )
            )

    return queries[:MAX_QUERIES_PER_CAPABILITY_AREA]


# Maximum CSE queries per capability area. CSE is more expensive
# (paid above 100/day) AND each query also fans out across the
# portfolio-host set in :mod:`designer.acquisition`, so the per-
# capability cap is tighter than Behance's.
MAX_CSE_QUERIES_PER_CAPABILITY_AREA = 3


def _google_cse_queries_for_capability_area(
    *,
    capability_area: dict[str, Any],
    discipline: str,
) -> list[DesignerSearchQuery]:
    """Form CSE queries for one capability area.

    CSE queries DON'T site-restrict at strategy-formation time —
    :mod:`designer.acquisition` fans each query out across the
    portfolio-host set so the per-host quota burn is explicit at the
    acquisition layer rather than baked into the work-unit shape.

    Recipe:
    1. Capability-area name as bare query.
    2. Top 1 specialization signal as query.
    3. Top 1 specialization × top 1 tool as combined query.
    Capped at ``MAX_CSE_QUERIES_PER_CAPABILITY_AREA``.
    """

    name = str(capability_area.get("name") or "").strip()
    queries: list[DesignerSearchQuery] = [
        DesignerSearchQuery(
            source="google_cse",
            query_text=name,
            sort="relevance",
            capability_area_name=name,
            discipline=discipline,
        )
    ]
    spec_signals = _as_str_list(capability_area.get("behance_specialization_signals"))
    tool_signals = _as_str_list(capability_area.get("tool_stack_signals"))

    if spec_signals:
        queries.append(
            DesignerSearchQuery(
                source="google_cse",
                query_text=spec_signals[0],
                sort="relevance",
                capability_area_name=name,
                discipline=discipline,
            )
        )

    if spec_signals and tool_signals:
        queries.append(
            DesignerSearchQuery(
                source="google_cse",
                query_text=f"{spec_signals[0]} {tool_signals[0]} portfolio",
                sort="relevance",
                capability_area_name=name,
                discipline=discipline,
            )
        )

    return queries[:MAX_CSE_QUERIES_PER_CAPABILITY_AREA]


def _dominant_discipline(brief: dict[str, Any]) -> str:
    """Return the most-frequently-tagged discipline across calibration
    exemplars; empty string when the brief carries none."""

    rubric = brief.get("design_rubric")
    if not isinstance(rubric, dict):
        return ""
    exemplars = rubric.get("calibration_exemplars") or []
    if not isinstance(exemplars, list):
        return ""
    counts: dict[str, int] = {}
    for ex in exemplars:
        if not isinstance(ex, dict):
            continue
        discipline = ex.get("discipline")
        if isinstance(discipline, str) and discipline:
            counts[discipline] = counts.get(discipline, 0) + 1
    if not counts:
        return ""
    # Stable: first key with max count when ties.
    return max(counts, key=lambda k: (counts[k], -list(counts.keys()).index(k)))


def _country_code(brief: dict[str, Any]) -> str:
    """Extract a 2-letter ISO country code from the brief's geography
    field if it parses cleanly. Behance's `country` filter expects ISO."""

    geography = brief.get("geography")
    if not isinstance(geography, str):
        return ""
    geography = geography.strip().upper()
    # Conservative: only accept exact 2-letter strings as ISO codes.
    if len(geography) == 2 and geography.isalpha():
        return geography
    # Common natural-language geographies → ISO codes. Slice-2 handles
    # only the ones Cloris's existing customer base sees; broader
    # coverage is a follow-up.
    natural_language_map = {
        "USA": "US",
        "UNITED STATES": "US",
        "UNITED KINGDOM": "GB",
        "UK": "GB",
        "GERMANY": "DE",
        "BRAZIL": "BR",
        "COLOMBIA": "CO",
    }
    return natural_language_map.get(geography, "")


def _as_str_list(value: Any) -> list[str]:
    """Coerce a brief field to a list of non-empty strings."""

    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]
