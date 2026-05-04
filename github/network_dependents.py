"""Throttled HTML scrape for ``/network/dependents`` (Slice 3 — OSS Maintainers).

Per OSS Maintainers Module Spec §9, GitHub does not expose downstream-
dependents count via the REST API. The number is publicly rendered on
the project's ``/network/dependents`` HTML page, which we scrape with
a defensive regex (no DOM path) and a conservative throttle. Per spec
§12, the parse is fail-soft: any parse failure returns ``None``, the
caller logs a warning, and the project-quality sub-index drops the
signal for that project.

The cache layer at :mod:`github.maintainer_signal_cache` serves as the
front-line throttle (30-day TTL per spec §9): once we know the count
for ``kubernetes/kubernetes``, we don't re-scrape for a month even if
multiple briefs target it. The ``throttle_seconds`` knob below adds
per-call delay when the cache misses, to avoid hammering the public
HTML surface during a burst of cache rebuilds.

Behaviour posture:

- Network errors ⇒ warn + return None.
- Non-200 HTTP ⇒ warn + return None.
- Markup that doesn't match the expected regex ⇒ warn + return None.
- The integer is the parse result, no upper bound enforced (some
  projects have millions of dependents).
"""

from __future__ import annotations

import asyncio
import logging
import re
import ssl
from typing import Optional

import aiohttp
import certifi

from github import maintainer_signal_cache as mcache

logger = logging.getLogger(__name__)


# The dependents page renders the count inline as e.g.::
#
#     <a class="btn-link selected" href="/{owner}/{repo}/network/dependents?dependent_type=REPOSITORY">
#       <svg ...></svg>
#       12,345,678
#       <span>Repositories</span>
#     </a>
#
# We don't bind to the DOM path (per spec §12 — defensive regex on
# the count label, not DOM path). The regex matches an integer with
# optional thousands separators preceded by ANY interleaving HTML
# whitespace + tags before the "Repositories" / "Packages" label.
# Permissive on the gap so minor markup tweaks don't break parsing;
# strict on the count + label so we don't match unrelated digits.
# "Repositories" is the canonical answer; if present we prefer that.
# "Packages" is a fallback (some repos only expose package
# dependents). Case-insensitive across the label.
_REPOSITORY_DEPENDENTS_RE = re.compile(
    r"([0-9][0-9,]{0,15})[\s\S]{0,200}?Repositories",
    re.IGNORECASE,
)
_PACKAGE_DEPENDENTS_RE = re.compile(
    r"([0-9][0-9,]{0,15})[\s\S]{0,200}?Packages",
    re.IGNORECASE,
)


_USER_AGENT = "sourcing-agent/1.0 (oss-maintainers-module)"
_TIMEOUT_SECONDS = 15


async def fetch_dependents_count(
    owner: str,
    repo: str,
    *,
    throttle_seconds: float = 2.0,
    use_cache: bool = True,
) -> Optional[int]:
    """Return the count of repository dependents for ``owner/repo``, or None.

    Cache-aware: hits the 30-day cache via
    :mod:`github.maintainer_signal_cache` first; only scrapes on miss.
    The ``throttle_seconds`` knob applies post-fetch (a defensive
    sleep so back-to-back cache rebuilds don't rate-limit GitHub's
    public HTML surface).

    Spec §12 contract: any failure mode (network, HTTP, parse) returns
    ``None`` and emits a single warning. Callers (project-quality sub-
    index in Slice 5) treat ``None`` as "signal absent for this
    project" and continue.
    """

    if use_cache:
        cached = mcache.get(owner, repo, "network_dependents")
        if cached is not None and isinstance(cached.data, int):
            return cached.data

    url = f"https://github.com/{owner}/{repo}/network/dependents"
    html = await _fetch_html(url)
    if html is None:
        return None

    count = _parse_count(html)
    if count is None:
        logger.warning(
            "network_dependents: parse failed for %s/%s — page markup may have changed",
            owner,
            repo,
        )
        return None

    if use_cache:
        mcache.put(owner, repo, "network_dependents", count)
    if throttle_seconds > 0:
        await asyncio.sleep(throttle_seconds)
    return count


async def _fetch_html(url: str) -> Optional[str]:
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SECONDS)
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html"}
    try:
        async with aiohttp.ClientSession(
            connector=connector, headers=headers, timeout=timeout
        ) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(
                        "network_dependents: HTTP %d for %s", resp.status, url
                    )
                    return None
                return await resp.text()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning("network_dependents: fetch failed for %s (%s)", url, exc)
        return None


def _parse_count(html: str) -> Optional[int]:
    """Extract the integer count from the dependents page HTML.

    Prefers the "Repositories" label; falls back to "Packages" only
    when the repo doesn't expose repo-level dependents.
    """

    match = _REPOSITORY_DEPENDENTS_RE.search(html)
    if match is None:
        match = _PACKAGE_DEPENDENTS_RE.search(html)
    if match is None:
        return None
    raw = match.group(1).replace(",", "")
    try:
        return int(raw)
    except ValueError:
        return None
