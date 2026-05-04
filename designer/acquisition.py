"""Designer module — candidate acquisition from per-source clients.

Designer Slice 2. Executes :class:`designer.schemas.DesignerSearchQuery`
objects against the per-source clients (Behance in Slice 2; Google CSE
in Slice 3) and produces a deduped stream of
:class:`designer.schemas.DesignerSnippet` instances ready for the
text-based facial-stage judge.

Cross-source dedup happens by ``identity_key``. Behance candidates
carry ``behance:<username>``; Google CSE candidates carry
``cse:<portfolio_url>``. Slice 8's identity-resolution layer joins
across sources at the workspace surface; this module only dedups
within the current acquisition stream.
"""

from __future__ import annotations

from typing import AsyncIterator

from designer.schemas import (
    DesignerSearchQuery,
    DesignerSnippet,
    behance_user_to_snippet,
)
from designer.sources.behance import BehanceClient


# Cap on candidates per query so a single broad query (e.g.,
# capability-area name = "design") doesn't burn the per-hour API
# budget on one search. Behance returns 12 per page by default; one
# page per query is the Slice-2 default. Wider sweeps land in Slice 5+
# once the orchestrator has a per-run governor that can spend budget
# adaptively.
DEFAULT_MAX_USERS_PER_QUERY = 12


async def acquire_behance_candidates(
    queries: list[DesignerSearchQuery],
    *,
    client: BehanceClient,
    max_users_per_query: int = DEFAULT_MAX_USERS_PER_QUERY,
) -> AsyncIterator[DesignerSnippet]:
    """Run each Behance query, yield deduped snippets.

    Generator shape so the orchestrator can apply backpressure (a
    full-stage judge call costs money; we don't want to acquire 500
    candidates before the first eval lands).

    Per-query failure: if a query 4xx/5xx's, log and continue rather
    than aborting the run. The orchestrator surfaces stop-reason
    `acquisition_partial_failure` only when ALL queries fail.
    """

    seen_identity_keys: set[str] = set()

    for query in queries:
        if query.source != "behance":
            continue

        params: dict[str, str] = {}
        if "country" in query.extra_filters and isinstance(
            query.extra_filters["country"], str
        ):
            params["country"] = query.extra_filters["country"]

        try:
            status, body = await client.search_users(
                query=query.query_text,
                country=params.get("country"),
                sort=query.sort,
                page=1,
            )
        except Exception:
            # Per-query failure is recoverable; continue with remaining
            # queries. The orchestrator's stop-reason logic decides
            # whether the run as a whole fails.
            continue

        if status != 200 or not isinstance(body, dict):
            continue

        users = body.get("users") or []
        if not isinstance(users, list):
            continue

        for user in users[:max_users_per_query]:
            if not isinstance(user, dict):
                continue
            snippet = behance_user_to_snippet(user)
            if not snippet.identity_key or snippet.identity_key == "behance:_unknown_":
                continue
            if snippet.identity_key in seen_identity_keys:
                continue
            seen_identity_keys.add(snippet.identity_key)
            yield snippet


def dedup_snippets(snippets: list[DesignerSnippet]) -> list[DesignerSnippet]:
    """Cross-source dedup by ``identity_key``.

    Useful when a Behance acquisition stream and a Google CSE stream
    (Slice 3) merge: the same person discovered via both surfaces
    deduplicates here. Returns the snippets in original order; first
    occurrence wins (the source that surfaced the candidate first
    keeps the metadata).
    """

    seen: set[str] = set()
    out: list[DesignerSnippet] = []
    for snippet in snippets:
        if snippet.identity_key in seen:
            continue
        seen.add(snippet.identity_key)
        out.append(snippet)
    return out
