"""GitHub launch-readiness probe.

Phase D Slice D-prep-B. Provides a sync ``probe_github_readiness()`` the
API layer (`GET /api/launch-readiness/github/{brief_id}`) wraps to surface
readiness failures BEFORE a worker fires off.

The underlying check uses :class:`github.client.GitHubClient`'s existing
``validate_credentials()`` async method (which probes ``/rate_limit``).
This wrapper handles the env-var presence check, asyncio-loop boilerplate,
and translates RuntimeErrors into editorial blockers.

Mirrors the shape of :mod:`linkedin.health` so the API endpoint can
union the two without per-source branching at the route layer.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from github import config as github_config


BlockerKind = Literal["auth", "config", "net"]


@dataclass(frozen=True)
class ReadinessBlocker:
    """One reason the launch isn't ready. Each carries editorial remediation.

    Mirrors :class:`linkedin.health.ReadinessBlocker` so the API layer
    can return a uniform shape across sources.
    """

    kind: BlockerKind
    message: str
    remediation: str


@dataclass(frozen=True)
class ReadinessReport:
    """Outcome of a readiness probe. ``ready`` is true iff blockers is empty."""

    ready: bool
    blockers: tuple[ReadinessBlocker, ...]


async def _async_validate(token: str) -> tuple[bool, str | None]:
    """Probe /rate_limit using the existing GitHubClient.

    Returns ``(ok, error_message)``. ``ok`` is True iff the token validated
    and the API returned 200. On any failure, ``error_message`` carries
    the underlying RuntimeError text so the caller can map it to an
    editorial remediation.
    """

    # Late import to avoid pulling aiohttp / certifi at module import time
    # (the API layer imports github.health on every readiness check; the
    # heavy GitHubClient deps only load when a real probe fires).
    try:
        from github.client import GitHubClient
    except ImportError as exc:
        return (False, f"GitHubClient import failed: {exc}")

    try:
        async with GitHubClient(token=token) as client:
            await client.validate_credentials()
        return (True, None)
    except RuntimeError as exc:
        return (False, str(exc))
    except Exception as exc:
        return (False, f"unexpected error: {exc}")


def probe_github_readiness(*, token: str | None = None) -> ReadinessReport:
    """Launch-readiness probe for GitHub.

    Synchronous wrapper. Calls :class:`github.client.GitHubClient`'s
    ``validate_credentials()`` under ``asyncio.run`` so a sync FastAPI
    route handler can call this directly.

    Args:
        token: Override the GITHUB_TOKEN env var. Defaults to
            ``shared.config.GITHUB_TOKEN`` (the same source GitHubClient
            uses).

    Returns:
        :class:`ReadinessReport` with ``ready`` true iff the token
        present + valid + GitHub API reachable.
    """

    blockers: list[ReadinessBlocker] = []

    effective_token = token or github_config.GITHUB_TOKEN
    if not effective_token:
        blockers.append(
            ReadinessBlocker(
                kind="config",
                message="No GitHub token configured.",
                remediation=(
                    "Add GITHUB_TOKEN to your .env file. "
                    "You can create one at github.com/settings/tokens "
                    "with the `read:org` and `read:user` scopes."
                ),
            )
        )
        return ReadinessReport(ready=False, blockers=tuple(blockers))

    try:
        ok, err = asyncio.run(_async_validate(effective_token))
    except RuntimeError:
        # asyncio.run can't run inside an existing loop. The API layer is
        # sync, so this shouldn't happen in production — surface a config
        # blocker so the recruiter sees something rather than a crash.
        blockers.append(
            ReadinessBlocker(
                kind="config",
                message="GitHub readiness probe ran from an async context.",
                remediation=(
                    "This is an internal error. Please report it; "
                    "the launch was not blocked by your setup."
                ),
            )
        )
        return ReadinessReport(ready=False, blockers=tuple(blockers))

    if not ok:
        # Map RuntimeError text to a Cloris-voice remediation. The
        # underlying validate_credentials raises RuntimeError on any
        # non-200 — most commonly 401 (bad token) or network issue.
        message_lower = (err or "").lower()
        if "401" in message_lower or "preflight failed" in message_lower:
            blockers.append(
                ReadinessBlocker(
                    kind="auth",
                    message="GitHub rejected your token.",
                    remediation=(
                        "Your GITHUB_TOKEN may have been revoked or expired. "
                        "Generate a new token at github.com/settings/tokens "
                        "and update your .env file."
                    ),
                )
            )
        else:
            blockers.append(
                ReadinessBlocker(
                    kind="net",
                    message="Cloris couldn't reach the GitHub API.",
                    remediation=(
                        "Check your internet connection. "
                        f"Underlying error: {err or 'unknown'}"
                    ),
                )
            )
        return ReadinessReport(ready=False, blockers=tuple(blockers))

    return ReadinessReport(ready=True, blockers=())
