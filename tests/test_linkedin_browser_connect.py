"""CDP connect vs Recruiter-tab readiness (deferred validation)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from linkedin.browser import LinkedInBrowser, _is_unusable_cdp_page_url


def test_is_unusable_cdp_page_url():
    assert _is_unusable_cdp_page_url("chrome://omnibox-popup.top-chrome/") is True
    assert _is_unusable_cdp_page_url("chrome-devtools://devtools/bundled/inspector.html") is True
    assert _is_unusable_cdp_page_url("devtools://devtools/bundled/inspector.html") is True
    assert _is_unusable_cdp_page_url("about:blank") is False
    assert _is_unusable_cdp_page_url("https://www.linkedin.com/talent/search") is False


def test_require_recruiter_tab_raises_when_no_talent_tab():
    browser = LinkedInBrowser()
    page = MagicMock()
    type(page).url = PropertyMock(return_value="about:blank")
    browser._page = page
    with patch.object(browser, "_bind_existing_recruiter_page", new=AsyncMock(return_value=False)):
        with pytest.raises(RuntimeError, match="LinkedIn Recruiter is required"):
            asyncio.run(browser.require_recruiter_tab())


def test_require_recruiter_tab_updates_project_id_when_bind_succeeds():
    browser = LinkedInBrowser()
    page = MagicMock()
    type(page).url = PropertyMock(
        return_value="https://www.linkedin.com/talent/hire/123/discover/recruiterSearch"
    )
    browser._page = page
    with patch.object(browser, "_bind_existing_recruiter_page", new=AsyncMock(return_value=True)):
        asyncio.run(browser.require_recruiter_tab())
    assert browser._project_id == "123"
