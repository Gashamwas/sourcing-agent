"""Tests for LinkedIn Recruiter browser crash recovery helpers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from linkedin.browser import LinkedInBrowser


def test_check_and_recover_routes_target_crash_into_refresh_recovery():
    browser = LinkedInBrowser()
    browser.recover_from_target_crash = AsyncMock(return_value=True)

    page = MagicMock()
    type(page).url = PropertyMock(side_effect=RuntimeError("Target crashed"))
    browser._page = page

    recovered = asyncio.run(browser.check_and_recover())

    assert recovered is True
    browser.recover_from_target_crash.assert_awaited_once()


def test_refresh_active_tab_falls_back_to_os_shortcut_after_target_crash():
    browser = LinkedInBrowser()
    browser._page = MagicMock()
    browser._page.reload = AsyncMock(side_effect=RuntimeError("Target crashed"))
    browser._page.wait_for_timeout = AsyncMock()
    browser._press_key = AsyncMock(side_effect=RuntimeError("Target crashed"))
    browser._send_os_refresh_shortcut = AsyncMock(return_value=True)

    recovered = asyncio.run(browser.refresh_active_tab())

    assert recovered is True
    browser._send_os_refresh_shortcut.assert_awaited_once()


def test_recover_from_target_crash_rebinds_and_restores_search_url():
    browser = LinkedInBrowser()
    browser.refresh_active_tab = AsyncMock(return_value=True)
    browser._bind_existing_recruiter_page = AsyncMock(side_effect=[False, True])
    browser.navigate_to_search = AsyncMock()
    browser._page = MagicMock()
    type(browser._page).url = PropertyMock(return_value="chrome-error://chromewebdata/")

    with patch("linkedin.browser.asyncio.sleep", new=AsyncMock()) as sleep_mock:
        recovered = asyncio.run(
            browser.recover_from_target_crash(
                "https://www.linkedin.com/talent/hire/1957683706/discover/recruiterSearch"
            )
        )

    assert recovered is True
    browser.navigate_to_search.assert_awaited_once()
    assert sleep_mock.await_count >= 1
