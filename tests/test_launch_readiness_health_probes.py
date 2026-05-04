"""Tests for the Phase D Slice D-prep launch-readiness health probes.

Pins the contract D9 (`GET /api/launch-readiness/{source}/{brief_id}`)
depends on:

- ``linkedin.health.probe_linkedin_readiness`` returns a structured
  :class:`ReadinessReport` with editorial blockers when CDP is unreachable
  or no browser context is attached.
- ``github.health.probe_github_readiness`` returns a config blocker when
  the GITHUB_TOKEN env var is empty; an auth blocker when GitHub rejects
  the token; ready=True when validate_credentials succeeds.

The probes don't actually hit external services in unit tests — we patch
the underlying dependencies (HTTP probe, async validator) so the tests
exercise the wrapper logic, not the real network.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import linkedin.health as linkedin_health
import github.health as github_health


# ---------------------------------------------------------------------------
# LinkedIn readiness
# ---------------------------------------------------------------------------


def test_linkedin_readiness_blocks_when_cdp_endpoint_unreachable(monkeypatch) -> None:
    """If Chrome isn't running, the CDP probe fails and we surface a
    'Cloris can't reach Chrome' net blocker with the launch-chrome
    remediation. No async dependency loaded."""

    monkeypatch.setattr(linkedin_health, "_probe_cdp_endpoint", lambda url, timeout=2.0: False)

    report = linkedin_health.probe_linkedin_readiness(cdp_url="http://127.0.0.1:9222")

    assert report.ready is False
    assert len(report.blockers) == 1
    blocker = report.blockers[0]
    assert blocker.kind == "net"
    assert "Chrome" in blocker.message
    assert "launch-chrome" in blocker.remediation


def test_linkedin_readiness_blocks_when_no_browser_context(monkeypatch) -> None:
    """CDP up but no contexts attached → auth blocker pointing at
    'open a Chrome window' remediation."""

    monkeypatch.setattr(linkedin_health, "_probe_cdp_endpoint", lambda url, timeout=2.0: True)

    async def _no_context(*_args, **_kwargs):
        return (False, False)

    # Stub the async helper directly, then re-route asyncio.run to call it
    # synchronously without spinning up a real event loop.
    monkeypatch.setattr(linkedin_health, "_probe_linkedin_context_async", _no_context)

    def _run_sync(coro):
        # asyncio.run on a coroutine that doesn't await anything real:
        # construct a tiny loop just for this test.
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(linkedin_health.asyncio, "run", _run_sync)

    report = linkedin_health.probe_linkedin_readiness(cdp_url="http://127.0.0.1:9222")

    assert report.ready is False
    assert len(report.blockers) == 1
    assert report.blockers[0].kind == "auth"
    assert "browser session" in report.blockers[0].message


def test_linkedin_readiness_blocks_when_no_linkedin_url_loaded(monkeypatch) -> None:
    """Chrome up + context attached but no LinkedIn URL anywhere → auth
    blocker (soft warning treated as blocker for v1; D9 may downgrade)."""

    monkeypatch.setattr(linkedin_health, "_probe_cdp_endpoint", lambda url, timeout=2.0: True)

    async def _has_context_no_linkedin(*_args, **_kwargs):
        return (True, False)

    monkeypatch.setattr(
        linkedin_health, "_probe_linkedin_context_async", _has_context_no_linkedin
    )

    def _run_sync(coro):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(linkedin_health.asyncio, "run", _run_sync)

    report = linkedin_health.probe_linkedin_readiness(cdp_url="http://127.0.0.1:9222")

    assert report.ready is False
    assert len(report.blockers) == 1
    assert report.blockers[0].kind == "auth"
    assert "LinkedIn" in report.blockers[0].message


def test_linkedin_readiness_passes_when_chrome_and_linkedin_present(monkeypatch) -> None:
    """All three checks pass → ready=True, no blockers."""

    monkeypatch.setattr(linkedin_health, "_probe_cdp_endpoint", lambda url, timeout=2.0: True)

    async def _full_health(*_args, **_kwargs):
        return (True, True)

    monkeypatch.setattr(linkedin_health, "_probe_linkedin_context_async", _full_health)

    def _run_sync(coro):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(linkedin_health.asyncio, "run", _run_sync)

    report = linkedin_health.probe_linkedin_readiness(cdp_url="http://127.0.0.1:9222")

    assert report.ready is True
    assert report.blockers == ()


# ---------------------------------------------------------------------------
# GitHub readiness
# ---------------------------------------------------------------------------


def test_github_readiness_blocks_when_token_missing(monkeypatch) -> None:
    """No GITHUB_TOKEN env var → config blocker pointing at .env setup."""

    # Pass token=None and force the underlying config to be empty.
    monkeypatch.setattr(github_health.github_config, "GITHUB_TOKEN", "")

    report = github_health.probe_github_readiness(token=None)

    assert report.ready is False
    assert len(report.blockers) == 1
    blocker = report.blockers[0]
    assert blocker.kind == "config"
    assert "GITHUB_TOKEN" in blocker.remediation


def test_github_readiness_blocks_on_auth_rejection(monkeypatch) -> None:
    """GitHub rejects the token (401) → auth blocker pointing at token
    rotation remediation."""

    async def _reject(_token: str):
        return (False, "GitHub credential preflight failed with status 401.")

    monkeypatch.setattr(github_health, "_async_validate", _reject)

    def _run_sync(coro):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(github_health.asyncio, "run", _run_sync)

    report = github_health.probe_github_readiness(token="bogus_token")

    assert report.ready is False
    assert len(report.blockers) == 1
    assert report.blockers[0].kind == "auth"
    assert "rejected" in report.blockers[0].message.lower()


def test_github_readiness_blocks_on_network_error(monkeypatch) -> None:
    """Non-auth failure (DNS, timeout) → net blocker carrying the
    underlying error string."""

    async def _net_error(_token: str):
        return (False, "connection failed: timeout")

    monkeypatch.setattr(github_health, "_async_validate", _net_error)

    def _run_sync(coro):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(github_health.asyncio, "run", _run_sync)

    report = github_health.probe_github_readiness(token="ok_token")

    assert report.ready is False
    assert len(report.blockers) == 1
    assert report.blockers[0].kind == "net"


def test_github_readiness_passes_when_token_validates(monkeypatch) -> None:
    """validate_credentials succeeds → ready=True, no blockers."""

    async def _ok(_token: str):
        return (True, None)

    monkeypatch.setattr(github_health, "_async_validate", _ok)

    def _run_sync(coro):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(github_health.asyncio, "run", _run_sync)

    report = github_health.probe_github_readiness(token="real_token")

    assert report.ready is True
    assert report.blockers == ()
