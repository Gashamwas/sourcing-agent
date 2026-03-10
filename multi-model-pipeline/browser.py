"""Browser automation for LinkedIn Recruiter via Playwright.

Connects to an existing logged-in browser session via CDP. Provides helpers for:
- Navigating to search pages
- Entering Boolean strings into the Keywords filter
- Reading results page DOM
- Paginating through results
- Opening candidate profiles
- Reading profile DOM
- Saving candidates to pipeline

IMPORTANT: This attaches to an existing browser with an active LinkedIn Recruiter session.
It does NOT launch a new browser or handle login.
"""

from __future__ import annotations
import asyncio
import time
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
import config


class LinkedInBrowser:
    """Manages a Playwright connection to LinkedIn Recruiter via CDP."""

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def connect(self) -> None:
        """Connect to the existing browser via CDP."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(config.CDP_URL)

        # Get the first context (the existing browser session)
        contexts = self._browser.contexts
        if not contexts:
            raise RuntimeError("No browser contexts found. Is the browser open?")
        self._context = contexts[0]

        # Find or create a LinkedIn Recruiter tab
        self._page = await self._find_or_create_recruiter_page()
        print(f"  Connected to browser. Active page: {self._page.url}")

    async def _find_or_create_recruiter_page(self) -> Page:
        """Find an existing LinkedIn Recruiter tab, or use the first available page."""
        for page in self._context.pages:
            if "linkedin.com/talent" in page.url:
                return page
        # No recruiter tab found — use first page
        if self._context.pages:
            return self._context.pages[0]
        return await self._context.new_page()

    async def disconnect(self) -> None:
        """Disconnect from the browser (does NOT close it)."""
        if self._playwright:
            await self._playwright.stop()

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser not connected. Call connect() first.")
        return self._page

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def navigate_to_search(self, project_url: str) -> None:
        """Navigate to a LinkedIn Recruiter project search page."""
        await self.page.goto(project_url, wait_until="domcontentloaded", timeout=30000)
        await self.page.wait_for_timeout(2000)  # Let SPA settle

    # ------------------------------------------------------------------
    # Search: enter Boolean into Keywords field
    # ------------------------------------------------------------------

    async def enter_search_string(self, boolean: str) -> None:
        """Clear the Keywords field and enter a new Boolean string.
        
        Uses the sidebar Keywords filter, NOT the global search bar.
        """
        # Click the Keywords input to focus it
        keywords_input = self.page.locator(
            'input[placeholder*="keyword" i], '
            'input[aria-label*="keyword" i], '
            'textarea[placeholder*="keyword" i], '
            'textarea[aria-label*="keyword" i]'
        ).first

        try:
            await keywords_input.wait_for(state="visible", timeout=10000)
        except Exception:
            # Try clicking "Show filters" first (AI search panel may be showing)
            try:
                show_filters = self.page.locator('button:has-text("Show filters"), a:has-text("Show filters")').first
                await show_filters.click()
                await self.page.wait_for_timeout(2000)
                await keywords_input.wait_for(state="visible", timeout=10000)
            except Exception:
                raise RuntimeError(
                    "Cannot find Keywords input. Make sure you're on a LinkedIn Recruiter "
                    "search page with the filters sidebar visible."
                )

        # Clear existing text and type new Boolean
        await keywords_input.click()
        await self.page.keyboard.press("Meta+a")  # Select all (Mac)
        await self.page.keyboard.press("Backspace")
        await keywords_input.fill(boolean)
        await self.page.keyboard.press("Enter")

        # Wait for results to load
        await self.page.wait_for_timeout(3000)

    # ------------------------------------------------------------------
    # Results: read DOM, count, paginate
    # ------------------------------------------------------------------

    async def get_results_count(self) -> int:
        """Try to read the total results count from the page."""
        try:
            count_el = self.page.locator(
                '[class*="results-count"], '
                '[class*="total-results"], '
                '[data-test*="results-count"]'
            ).first
            text = await count_el.text_content(timeout=5000)
            if text:
                # Extract number from text like "1,234 results"
                import re
                nums = re.findall(r"[\d,]+", text)
                if nums:
                    return int(nums[0].replace(",", ""))
        except Exception:
            pass
        return -1  # Unknown

    async def get_results_page_dom(self) -> str:
        """Get the DOM content of the search results area.
        
        Returns the outer HTML of the results container, stripped of scripts/styles
        to reduce token count.
        """
        # Try common LinkedIn Recruiter result container selectors
        selectors = [
            '[class*="search-results"]',
            '[class*="results-list"]',
            '[class*="hiring-search"]',
            'main',
            '[role="main"]',
        ]

        for selector in selectors:
            try:
                el = self.page.locator(selector).first
                html = await el.evaluate(
                    """el => {
                        // Clone and strip scripts/styles to reduce size
                        const clone = el.cloneNode(true);
                        clone.querySelectorAll('script, style, svg, img').forEach(e => e.remove());
                        return clone.innerHTML;
                    }""",
                    timeout=10000,
                )
                if html and len(html) > 200:
                    return html
            except Exception:
                continue

        # Fallback: get the full page body (will be large)
        return await self.page.evaluate(
            """() => {
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('script, style, svg, img').forEach(e => e.remove());
                return clone.innerHTML;
            }"""
        )

    async def get_page_count(self) -> int:
        """Try to determine how many pages of results exist."""
        try:
            # Look for pagination elements
            pages = self.page.locator(
                '[class*="pagination"] button, '
                '[class*="pagination"] a, '
                '[class*="page-number"]'
            )
            count = await pages.count()
            if count > 0:
                last = await pages.nth(count - 1).text_content()
                if last and last.strip().isdigit():
                    return int(last.strip())
        except Exception:
            pass
        return 1  # Assume single page if can't determine

    async def go_to_next_page(self) -> bool:
        """Click the 'Next' pagination button. Returns True if successful."""
        try:
            next_btn = self.page.locator(
                'button[aria-label*="Next" i], '
                'a[aria-label*="Next" i], '
                'button:has-text("Next"), '
                '[class*="pagination"] button:last-child'
            ).first
            if await next_btn.is_enabled():
                await next_btn.click()
                await self.page.wait_for_timeout(3000)
                return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # Profile: navigate and read
    # ------------------------------------------------------------------

    async def open_profile(self, profile_url: str) -> None:
        """Navigate to a candidate's full profile page."""
        if not profile_url.startswith("http"):
            profile_url = f"https://www.linkedin.com{profile_url}"
        await self.page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        await self.page.wait_for_timeout(2000)

    async def get_profile_dom(self) -> str:
        """Get the DOM content of a candidate profile, stripped of noise."""
        return await self.page.evaluate(
            """() => {
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('script, style, svg, img, [class*="similar-profiles"], [class*="sidebar"]').forEach(e => e.remove());
                return clone.innerHTML;
            }"""
        )

    # ------------------------------------------------------------------
    # Save candidate to pipeline
    # ------------------------------------------------------------------

    async def save_candidate(self) -> bool:
        """Click 'Save to pipeline' on the current profile. Returns True if successful."""
        try:
            save_btn = self.page.locator(
                'button:has-text("Save"), '
                'button[aria-label*="Save" i], '
                '[class*="save-to-pipeline"], '
                '[data-test*="save"]'
            ).first
            await save_btn.wait_for(state="visible", timeout=5000)
            await save_btn.click()
            await self.page.wait_for_timeout(2000)
            return True
        except Exception as e:
            print(f"  [warn] Failed to save candidate: {e}")
            return False

    async def go_back_to_results(self) -> None:
        """Navigate back to search results from a profile page."""
        await self.page.go_back()
        await self.page.wait_for_timeout(2000)


# ------------------------------------------------------------------
# Convenience: sync wrapper for simple scripts
# ------------------------------------------------------------------

def run_sync(coro):
    """Run an async function synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)
