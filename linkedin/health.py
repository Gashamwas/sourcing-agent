"""LinkedIn launch-readiness probe.

Phase D Slice D-prep-A. Provides a callable ``probe_linkedin_readiness()``
that the API layer (`GET /api/launch-readiness/linkedin/{brief_id}`) wraps
to surface readiness failures BEFORE a worker fires off.

This is intentionally distinct from
:meth:`linkedin.orchestrator.Pipeline._ensure_browser_healthy`, which is a
*recovery* loop for an already-running session. Launch readiness is a
pre-flight check: can we even start? It does NOT spin up a browser; it
asks whether the recruiter has the prerequisites in place.

LinkedIn architecture: Cloris connects to Chrome over CDP at
``config.CDP_URL``. The recruiter launches Chrome separately with
``./launch-chrome.sh --force`` and opens linkedin.com/talent. A healthy
launch needs:

1. CDP endpoint reachable.
2. At least one browser context attached.
3. (Best-effort) a LinkedIn Recruiter page loaded in some context — if
   not, the worker will try to navigate but may stall on auth.

Each blocker carries an editorial remediation string the UI renders as
italic prose. Failures NEVER read as red error chips — Cloris-voice
("Cloris can't reach LinkedIn — your browser session may have ended.").
"""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal

from shared import config


BlockerKind = Literal["auth", "config", "net"]


@dataclass(frozen=True)
class ReadinessBlocker:
    """One reason the launch isn't ready. Each carries editorial remediation."""

    kind: BlockerKind
    message: str
    remediation: str


@dataclass(frozen=True)
class ReadinessReport:
    """Outcome of a readiness probe. ``ready`` is true iff blockers is empty."""

    ready: bool
    blockers: tuple[ReadinessBlocker, ...]


def _probe_cdp_endpoint(cdp_url: str, timeout: float = 2.0) -> bool:
    """Try a synchronous HTTP GET against the CDP base URL.

    Chrome's DevTools Protocol exposes ``/json/version`` as a quick liveness
    endpoint. If it responds 200, Chrome is up and CDP is listening.
    Returns ``False`` on any network error or non-200 response.
    """

    probe_url = cdp_url.rstrip("/") + "/json/version"
    try:
        with urllib.request.urlopen(probe_url, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


async def _probe_linkedin_context_async(cdp_url: str, timeout: float = 5.0) -> tuple[bool, bool]:
    """Connect over CDP and report ``(has_context, has_linkedin_url)``.

    - ``has_context`` is True iff at least one BrowserContext is attached.
    - ``has_linkedin_url`` is True iff at least one page in any context has
      a linkedin.com URL loaded. Best-effort signal: a healthy session
      typically has linkedin.com/talent open. If false but ``has_context``
      is true, the worker can still navigate — but the recruiter may need
      to log in.

    Returns ``(False, False)`` on any connect or query error so the caller
    can map to a single blocker without nested error handling.
    """

    try:
        from rebrowser_playwright.async_api import async_playwright

        pw = await async_playwright().start()
        try:
            browser = await asyncio.wait_for(
                pw.chromium.connect_over_cdp(cdp_url),
                timeout=timeout,
            )
        except (asyncio.TimeoutError, Exception):
            await pw.stop()
            return (False, False)

        try:
            contexts = browser.contexts
            if not contexts:
                return (False, False)
            has_linkedin = False
            for ctx in contexts:
                for page in ctx.pages:
                    try:
                        url = page.url
                    except Exception:
                        continue
                    if "linkedin.com" in url:
                        has_linkedin = True
                        break
                if has_linkedin:
                    break
            return (True, has_linkedin)
        finally:
            try:
                await browser.close()
            except Exception:
                pass
            await pw.stop()
    except ImportError:
        # rebrowser_playwright not installed — surface as a config blocker
        # caller-side; here we just report no context found.
        return (False, False)


def probe_linkedin_readiness(*, cdp_url: str | None = None) -> ReadinessReport:
    """Launch-readiness probe for LinkedIn.

    Synchronous wrapper. Internally uses asyncio.run for the playwright
    connect since the API layer (FastAPI sync route) calls this directly.

    Args:
        cdp_url: Override the CDP endpoint. Defaults to
            ``shared.config.CDP_URL`` (env-overridable; default
            ``http://127.0.0.1:9222``).

    Returns:
        :class:`ReadinessReport` with ``ready`` true iff every check passed.
    """

    cdp = cdp_url or config.CDP_URL
    blockers: list[ReadinessBlocker] = []

    # Step 1: synchronous CDP liveness check (no playwright dependency).
    if not _probe_cdp_endpoint(cdp):
        blockers.append(
            ReadinessBlocker(
                kind="net",
                message="Cloris can't reach Chrome over CDP.",
                remediation=(
                    "Run ./launch-chrome.sh --force, open linkedin.com/talent, "
                    "wait a few seconds, then retry."
                ),
            )
        )
        # No point checking contexts if CDP itself is down.
        return ReadinessReport(ready=False, blockers=tuple(blockers))

    # Step 2: connect via playwright and inspect contexts.
    try:
        has_context, has_linkedin = asyncio.run(_probe_linkedin_context_async(cdp))
    except RuntimeError:
        # asyncio.run may fail if called from inside a running loop. The
        # API layer is sync (FastAPI sync def routes), so this should not
        # happen in production — but if a caller in an async context hits
        # this, surface a config blocker rather than crashing.
        blockers.append(
            ReadinessBlocker(
                kind="config",
                message="Cloris's launch-readiness probe ran from an async context.",
                remediation=(
                    "This is an internal error. Please report it; "
                    "the launch was not blocked by your setup."
                ),
            )
        )
        return ReadinessReport(ready=False, blockers=tuple(blockers))

    if not has_context:
        blockers.append(
            ReadinessBlocker(
                kind="auth",
                message="Chrome is up, but Cloris couldn't find a browser session.",
                remediation=(
                    "Open a Chrome window and navigate to linkedin.com/talent. "
                    "Cloris will attach to that session on the next launch."
                ),
            )
        )
        return ReadinessReport(ready=False, blockers=tuple(blockers))

    if not has_linkedin:
        # Soft warning, not a hard block — the worker can still navigate.
        # We surface it as an "auth" blocker so the recruiter sees it,
        # but Phase D D9 may decide to downgrade this to a non-blocking
        # warning if real-world false-blocks are common.
        blockers.append(
            ReadinessBlocker(
                kind="auth",
                message="Chrome is open, but no LinkedIn page is loaded.",
                remediation=(
                    "Open linkedin.com/talent in a tab so Cloris can confirm "
                    "you're signed in. If you're already signed in elsewhere, "
                    "this is just a heads-up — the worker will navigate anyway."
                ),
            )
        )

    return ReadinessReport(ready=not blockers, blockers=tuple(blockers))
