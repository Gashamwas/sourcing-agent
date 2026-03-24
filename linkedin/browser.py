"""Browser automation for LinkedIn Recruiter via Playwright.

All selectors verified against docs/linkedin-recruiter-dom-map.md.
Profile is a SLIDE-IN PANEL, not page navigation.

IMPORTANT: This attaches to an existing browser with an active LinkedIn Recruiter session.
It does NOT launch a new browser or handle login.
"""

from __future__ import annotations
import asyncio
import random
import re
from typing import Optional, TYPE_CHECKING
from shared import config
from shared.human_timing import human_delay_correlated
from decoy.actions._utils import human_scroll

if TYPE_CHECKING:
    from rebrowser_playwright.async_api import Browser, Page, BrowserContext

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


async def _retry(coro_fn, retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS):
    """Retry an async callable up to `retries` times with randomized delay."""
    last_err = None
    for attempt in range(retries):
        try:
            return await coro_fn()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                jittered = delay * random.uniform(0.5, 1.5)
                print(f"    [retry {attempt + 1}/{retries}] {e}")
                await asyncio.sleep(jittered)
    raise last_err


class LinkedInBrowser:
    """Manages a Playwright connection to LinkedIn Recruiter via CDP."""

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._cursor = None  # GhostCursor for human-like mouse movement

    async def connect(self) -> None:
        from rebrowser_playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(config.CDP_URL)
        contexts = self._browser.contexts
        if not contexts:
            raise RuntimeError("No browser contexts found. Is the browser open?")

        # Search ALL contexts and ALL tabs for a LinkedIn Recruiter page
        for ctx in contexts:
            for page in ctx.pages:
                if "linkedin.com/talent" in page.url:
                    self._context = ctx
                    self._page = page
                    # Initialize ghost-cursor for human-like mouse trajectories
                    try:
                        from python_ghost_cursor.playwright_async import create_cursor
                        self._cursor = create_cursor(self._page)
                        print(f"  Connected to browser (ghost-cursor active). Active page: {self._page.url}")
                    except Exception as e:
                        print(f"  Connected to browser (ghost-cursor unavailable: {e}). Active page: {self._page.url}")
                    return

        # No Recruiter tab found
        all_urls = []
        for ctx in contexts:
            for page in ctx.pages:
                all_urls.append(page.url)
        urls_text = "\n    ".join(all_urls) if all_urls else "(no tabs open)"
        raise RuntimeError(
            f"No LinkedIn Recruiter tab found.\n"
            f"  Open linkedin.com/talent in Chrome, then run again.\n"
            f"  Found {len(all_urls)} tab(s):\n    {urls_text}"
        )

    async def disconnect(self) -> None:
        if self._playwright:
            await self._playwright.stop()

    async def _ghost_click(self, selector: str) -> bool:
        """Click using ghost-cursor (Bézier trajectory + Fitts's Law timing).

        Falls back to JS eval click if ghost-cursor unavailable or fails.
        Returns True if ghost-cursor succeeded, False if fell back to JS.
        """
        if self._cursor:
            try:
                await asyncio.wait_for(self._cursor.click(selector), timeout=5.0)
                return True
            except Exception:
                pass
        return False

    async def _ghost_move(self, selector: str) -> bool:
        """Move cursor to element without clicking. Returns True if succeeded."""
        if self._cursor:
            try:
                await asyncio.wait_for(self._cursor.move(selector), timeout=5.0)
                return True
            except Exception:
                pass
        return False

    async def _ghost_click_locator(self, locator) -> bool:
        """Ghost-click a Playwright Locator (not a CSS selector)."""
        if self._cursor:
            try:
                handle = await locator.element_handle(timeout=3000)
                if handle:
                    await asyncio.wait_for(self._cursor.click(handle), timeout=5.0)
                    return True
            except Exception:
                pass
        # Fallback to Playwright click
        await locator.click(timeout=5000)
        return False

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser not connected. Call connect() first.")
        return self._page

    # ------------------------------------------------------------------
    # Emergency recovery — "break glass" protocol
    # ------------------------------------------------------------------

    async def check_and_recover(self) -> bool:
        """Detect error/stuck states and attempt recovery. Returns True if recovery happened."""
        try:
            # Check for LinkedIn's "Something went wrong" error page
            error_heading = self.page.locator('text="Something went wrong"').first
            try_again_btn = self.page.locator('button:has-text("Try again")').first

            if await error_heading.is_visible(timeout=1000):
                print("  [recovery] Detected 'Something went wrong' page — attempting recovery...")
                # Strategy 1: Click "Try again" if present
                try:
                    if await try_again_btn.is_visible(timeout=2000):
                        await try_again_btn.click()
                        await self.page.wait_for_timeout(5000)
                        # Check if recovery succeeded
                        if not await error_heading.is_visible(timeout=2000):
                            print("  [recovery] 'Try again' click succeeded.")
                            return True
                except Exception:
                    pass

                # Strategy 2: Reload the page
                print("  [recovery] 'Try again' didn't work — reloading page...")
                await self.page.reload(wait_until="domcontentloaded", timeout=30000)
                await self.page.wait_for_timeout(5000)
                if not await error_heading.is_visible(timeout=2000):
                    print("  [recovery] Page reload succeeded.")
                    return True

                # Strategy 3: Navigate back to LinkedIn Recruiter base
                print("  [recovery] Reload didn't work — navigating to LinkedIn Recruiter home...")
                await self.page.goto("https://www.linkedin.com/talent/search", wait_until="domcontentloaded", timeout=30000)
                await self.page.wait_for_timeout(5000)
                print("  [recovery] Navigated to LI Recruiter home. Will need to re-enter project.")
                return True
        except Exception:
            pass  # No error page detected — normal state

        # Check for blank/empty page (no LinkedIn DOM at all)
        try:
            url = self.page.url
            if "linkedin.com" not in url:
                print(f"  [recovery] Page navigated away from LinkedIn ({url}) — going back...")
                await self.page.go_back(wait_until="domcontentloaded", timeout=30000)
                await self.page.wait_for_timeout(3000)
                return True
        except Exception:
            pass

        # Check for login redirect
        try:
            if "/login" in self.page.url or "/uas/login" in self.page.url:
                print("  [recovery] CRITICAL: Redirected to login page. Session may have expired.")
                print("  [recovery] Please re-authenticate in the browser window and resume the run.")
                raise RuntimeError("LinkedIn session expired — re-authenticate and resume.")
        except RuntimeError:
            raise
        except Exception:
            pass

        return False

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def navigate_to_search(self, project_url: str) -> None:
        await self.page.goto(project_url, wait_until="domcontentloaded", timeout=30000)
        await self.page.wait_for_timeout(2000)

    # ------------------------------------------------------------------
    # Search: enter Boolean into Keywords field
    # ------------------------------------------------------------------

    async def enter_search_string(self, boolean: str) -> None:
        """Enter a Boolean into the sidebar Keywords field (NOT the global search bar).

        Uses the project search page sidebar: Clear Keywords button → edit button → textarea.
        NEVER targets input[aria-label*="keyword"] which is the global search bar.
        The setup steps (clear → edit → fill → Enter) are retried on failure.
        The final results wait is NOT retried to avoid double-submitting searches.
        """
        # Pre-flight: dismiss any stale profile slide-in blocking the sidebar
        await self.go_back_to_results()

        async def _do():
            # Step 1: Clear existing keywords if the Clear Keywords button is visible
            clear_btn = self.page.locator('button[aria-label="Clear Keywords"]').first
            try:
                if await clear_btn.is_visible(timeout=2000):
                    await clear_btn.click()
                    await self.page.wait_for_timeout(1000)
            except Exception:
                pass  # Field is already empty

            # Step 2: Click the edit/add button to reveal the textarea
            edit_btn = self.page.locator('button[aria-label*="Profile keywords"]').first
            await edit_btn.wait_for(state="visible", timeout=10000)
            await edit_btn.click()
            await self.page.wait_for_timeout(1000)

            # Step 3: Fill the sidebar textarea (the ONLY correct target)
            textarea = self.page.locator('textarea[id*="free-text-single-value-input"]').first
            await textarea.wait_for(state="visible", timeout=5000)
            await textarea.fill(boolean)

            # Step 4: Submit
            await self.page.keyboard.press("Enter")

        await _retry(_do)

        # Step 5: Wait for results (outside retry — never re-submit on timeout)
        await self.page.wait_for_timeout(3000)

    async def has_next_page(self) -> bool:
        """Check if the Next pagination button exists and is enabled."""
        try:
            next_btn = self.page.locator('button[aria-label="Next"]').first
            return await next_btn.is_enabled(timeout=3000)
        except Exception:
            return False

    async def get_result_count(self) -> int:
        """Parse 'N RESULTS' from the page. Alias for get_results_count."""
        return await self.get_results_count()

    # ------------------------------------------------------------------
    # Filter application
    # ------------------------------------------------------------------

    async def apply_permanent_filters(self, filters: dict) -> None:
        """Set Location, Seniority, etc. from the brief's permanent_filters.

        This is complex UI automation — implements Location, stubs the rest.
        """
        print(f"  Applying permanent filters...")

        # Location filter
        location = filters.get("Location") or filters.get("location")
        if location:
            await self._set_location_filter(location)

        # Seniority filter
        seniority = filters.get("seniority")
        if seniority:
            print(f"  [TODO] Seniority filter: {seniority} — requires dropdown UI automation")

        # Years of experience
        years_exp = filters.get("years_experience")
        if years_exp:
            print(f"  [TODO] Years experience filter: {years_exp} — requires slider/input automation")

        # Log any unhandled filters
        handled = {"Location", "location", "seniority", "years_experience",
                    "company_filters", "keywords", "seniority_excluded"}
        for key in filters:
            if key not in handled:
                print(f"  [TODO] Unhandled filter: {key} = {filters[key]}")

    async def _set_location_filter(self, location: str) -> None:
        """Set the Location filter in LinkedIn Recruiter sidebar."""
        try:
            # Find the Location input — typically a typeahead
            loc_input = self.page.locator(
                'input[aria-label*="location" i], input[placeholder*="location" i]'
            ).first
            await loc_input.wait_for(state="visible", timeout=5000)
            await loc_input.click()
            await loc_input.fill(location)
            await self.page.wait_for_timeout(1500)

            # Select from typeahead dropdown
            option = self.page.locator(
                f'[role="option"]:has-text("{location}"), '
                f'li:has-text("{location}")'
            ).first
            await option.click()
            await self.page.wait_for_timeout(2000)
            print(f"  Location filter set: {location}")
        except Exception as e:
            print(f"  [warn] Location filter failed: {e} — set manually before running")

    # ------------------------------------------------------------------
    # Results: innerText, count, paginate
    # ------------------------------------------------------------------

    async def get_results_count(self) -> int:
        """Parse "N RESULTS" text from the page. Returns int (-1 if unparseable)."""
        raw = await self.get_results_count_text()
        if not raw:
            return -1
        # Strip suffix like "K+", "M+" and parse
        clean = raw.replace(",", "").strip()
        if clean.upper().endswith("K+"):
            try:
                return int(float(clean[:-2]) * 1000)
            except ValueError:
                return -1
        if clean.upper().endswith("M+"):
            try:
                return int(float(clean[:-2]) * 1_000_000)
            except ValueError:
                return -1
        try:
            return int(clean)
        except ValueError:
            return -1

    async def get_results_count_text(self) -> str:
        """Read the raw result count text from .search-query-summary__title (e.g. '1.2K+ results').

        Waits briefly for LinkedIn to update the result count in the DOM
        after a search is executed.
        """
        for _ in range(5):
            try:
                el = self.page.locator(".search-query-summary__title").first
                text = (await el.inner_text(timeout=3000)).strip()
                if text:
                    # Extract the count portion: "1,234 results" → "1,234", "1.2K+ results" → "1.2K+"
                    match = re.search(r"([\d.,]+[KkMm]?\+?)", text)
                    if match:
                        return match.group(1)
            except Exception:
                pass
            await self.page.wait_for_timeout(1000)
        return ""

    async def scroll_to_load_all_results(self) -> int:
        """Scroll the results list container to trigger LinkedIn's lazy loading.

        The results list lives inside a scrollable parent container (not the main window).
        Each <li> in ol.profile-list is always present, but the <article> inside only
        renders when the <li> is scrolled into the container's viewport.

        Strategy: scroll through results with human-like chunked scrolling to force
        all articles to render. Returns the final rendered article count.
        """
        cards_selector = "ol.profile-list article.profile-list-item"
        li_selector = "ol.profile-list > li"

        li_count = await self.page.locator(li_selector).count()
        if li_count == 0:
            return 0

        # Scroll down through results in human-like chunks
        total_scrolled = 0
        for i in range(li_count):
            li = self.page.locator(li_selector).nth(i)
            try:
                box = await li.bounding_box(timeout=3000)
                if box and box["y"] > 0:
                    scroll_amount = int(box["y"] * 0.8)
                    await human_scroll(self.page, scroll_amount)
                    total_scrolled += scroll_amount
            except Exception:
                pass
            # Brief dwell every few items to simulate scanning
            if (i + 1) % 5 == 0:
                await asyncio.sleep(human_delay_correlated(0.4))

        # Final wait for any remaining renders
        await self.page.wait_for_timeout(800)

        # Scroll back to top
        if total_scrolled > 0:
            await human_scroll(self.page, -total_scrolled)
        await asyncio.sleep(human_delay_correlated(0.3))

        final_count = await self.page.locator(cards_selector).count()
        return final_count

    async def get_card_name_url_pairs(self) -> list[dict]:
        """Extract name + profile URL atomically from each rendered article card.

        Returns a list of {"name": str, "url": str} dicts in DOM order.
        Pairs are extracted per-card so name and URL always correspond.
        """
        async def _do():
            cards = self.page.locator("ol.profile-list article.profile-list-item")
            count = await cards.count()
            pairs = []
            for i in range(count):
                card = cards.nth(i)
                name = ""
                url = ""
                try:
                    name_el = card.locator('[class*="lockup__title"] a').first
                    name = (await name_el.inner_text(timeout=2000)).strip()
                    url = (await name_el.get_attribute("href")) or ""
                except Exception:
                    # Try the profile link directly if lockup title fails
                    try:
                        link = card.locator('a[href*="/talent/profile/"]').first
                        url = (await link.get_attribute("href")) or ""
                        name = (await link.inner_text(timeout=2000)).strip()
                    except Exception:
                        pass
                if name or url:
                    pairs.append({"name": name, "url": url})
            return pairs
        return await _retry(_do)

    async def get_results_list_innertext(self) -> str:
        """Get innerText of ol.profile-list (the results container)."""
        # Fast guard: don't burn 75s retrying if the list doesn't exist
        if await self.page.locator("ol.profile-list").count() == 0:
            return ""
        async def _do():
            el = self.page.locator("ol.profile-list").first
            await el.wait_for(state="attached", timeout=5000)
            return await el.inner_text(timeout=10000)
        return await _retry(_do)

    async def get_card_innertext(self, card_index: int) -> str:
        """Get innerText of a specific candidate card by 0-based index."""
        async def _do():
            cards = self.page.locator("ol.profile-list article.profile-list-item")
            count = await cards.count()
            if card_index >= count:
                raise IndexError(f"Card index {card_index} out of range ({count} cards)")
            return await cards.nth(card_index).inner_text(timeout=10000)
        return await _retry(_do)

    async def get_card_count(self) -> int:
        cards = self.page.locator("ol.profile-list article.profile-list-item")
        return await cards.count()

    async def go_to_next_page(self) -> bool:
        """Click the bottom pagination link to advance to the next results page.

        Primary: a.pagination__quick-link--next (bottom of results list)
        Fallback: button[aria-label="Next"] (non-project search pages)
        Verifies the page actually advanced by comparing the first candidate name before/after.
        """
        try:
            # Read first candidate name BEFORE clicking
            first_name_before = ""
            try:
                first_link = self.page.locator('ol.profile-list article.profile-list-item [class*="lockup__title"] a').first
                first_name_before = (await first_link.inner_text(timeout=3000)).strip()
            except Exception:
                pass

            # Try the bottom pagination link first
            next_link = self.page.locator('a.pagination__quick-link--next').first
            try:
                visible = await next_link.is_visible(timeout=3000)
            except Exception:
                visible = False

            if visible:
                await next_link.scroll_into_view_if_needed()
                await self.page.wait_for_timeout(500)
                if not await self._ghost_click('a.pagination__quick-link--next'):
                    await next_link.click()
            else:
                # Fallback: button[aria-label="Next"] for non-project pages
                next_btn = self.page.locator(
                    'button[aria-label="Next"]:not(.skyline-pagination-button)'
                ).first
                if not await next_btn.is_enabled(timeout=3000):
                    return False
                if not await self._ghost_click('button[aria-label="Next"]:not(.skyline-pagination-button)'):
                    await next_btn.click()

            await self.page.wait_for_timeout(3000)

            # Verify the page actually advanced by checking the first candidate name
            if first_name_before:
                try:
                    first_link = self.page.locator('ol.profile-list article.profile-list-item [class*="lockup__title"] a').first
                    first_name_after = (await first_link.inner_text(timeout=3000)).strip()
                    if first_name_after == first_name_before:
                        await self.page.wait_for_timeout(2000)
                        first_name_after = (await first_link.inner_text(timeout=3000)).strip()
                        if first_name_after == first_name_before:
                            print("    [warn] Pagination click did not advance — first candidate unchanged")
                            return False
                except Exception:
                    pass  # Can't verify, assume it worked

            return True
        except Exception:
            return False

    async def go_to_previous_page(self) -> bool:
        async def _do():
            prev_btn = self.page.locator('button[aria-label="Previous"]').first
            if await prev_btn.is_enabled():
                await prev_btn.click()
                await self.page.wait_for_timeout(3000)
                return True
            return False
        try:
            return await _retry(_do)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Profile: slide-in panel (NOT page navigation)
    # ------------------------------------------------------------------

    async def open_profile(self, candidate_name: str) -> None:
        """Click candidate name link to open the slide-in profile panel.

        Tries multiple strategies: Playwright text match, then JS click by name substring.
        """
        async def _do():
            # Strategy 1: Ghost-cursor with Playwright text match
            selector = f'ol.profile-list article.profile-list-item a:has-text("{candidate_name}")'
            try:
                name_link = self.page.locator(selector).first
                if await name_link.count() > 0:
                    await name_link.wait_for(state="visible", timeout=5000)
                    if not await self._ghost_click(selector):
                        await name_link.evaluate("el => el.click()")
                    await self.page.locator("div.profile-slidein__container").wait_for(
                        state="visible", timeout=10000
                    )
                    await self.page.wait_for_timeout(1500)
                    return
            except Exception:
                pass

            # Strategy 2: JS click — find link by name substring (handles special chars)
            escaped_name = candidate_name.replace("'", "\\'").replace('"', '\\"')
            clicked = await self.page.evaluate(f"""() => {{
                const links = document.querySelectorAll('ol.profile-list article.profile-list-item a');
                // Strip credential suffixes (PhD, MBA, M.Sc., etc.) and trailing punctuation
                let target = '{escaped_name}'.replace(/,?\\s*(PhD|Ph\\.?D|MBA|M\\.?Sc\\.?|M\\.?S\\.?|Dr\\.?|CFA|PMP|PE)\\s*$/gi, '').trim().toLowerCase();
                for (const link of links) {{
                    const text = link.textContent.trim().toLowerCase();
                    if (text.includes(target) || target.includes(text)) {{
                        link.click();
                        return true;
                    }}
                }}
                // Fuzzy: try matching just the first name + last name (ignore middle/suffix)
                const parts = target.split(/\\s+/);
                if (parts.length >= 2) {{
                    const first = parts[0];
                    // Find last part that's not a single letter (initial)
                    let last = parts[parts.length - 1];
                    for (let i = parts.length - 1; i >= 1; i--) {{
                        if (parts[i].length > 1) {{ last = parts[i]; break; }}
                    }}
                    for (const link of links) {{
                        const text = link.textContent.trim().toLowerCase();
                        if (text.includes(first) && text.includes(last)) {{
                            link.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }}""")
            if not clicked:
                raise Exception(f"Could not find profile link for '{candidate_name}'")
            await self.page.locator("div.profile-slidein__container").wait_for(
                state="visible", timeout=10000
            )
            await self.page.wait_for_timeout(1500)
        await _retry(_do)

    async def ensure_card_rendered(self, card_index: int) -> None:
        """Scroll the Nth <li> in the results list into view to force article rendering.

        LinkedIn uses virtual scrolling — <li> containers are always in the DOM
        but <article> elements inside only render when the <li> is visible.
        Call this before open_profile_by_url/open_profile to guarantee the
        target card's links exist in the DOM.
        """
        try:
            li = self.page.locator("ol.profile-list > li").nth(card_index)
            await li.scroll_into_view_if_needed(timeout=3000)
            await self.page.wait_for_timeout(600)  # Let article render
        except Exception as e:
            print(f"    [warn] ensure_card_rendered({card_index}) failed: {e}")

    async def open_profile_by_url(self, profile_url: str) -> None:
        """Open a profile by matching the name link href in the results list.

        Uses JS click to bypass overlay issues. Falls back to Playwright locator.
        Caller should call ensure_card_rendered() first to guarantee the article is in the DOM.
        """
        async def _do():
            # Extract the unique profile ID segment for more reliable matching
            url_fragment = profile_url
            if "/talent/profile/" in profile_url:
                url_fragment = profile_url.split("/talent/profile/")[-1].split("?")[0]

            selector = f'ol.profile-list a[href*="{url_fragment}"]'

            # Strategy 1: Ghost-cursor click (Bézier trajectory + mouse events)
            if not await self._ghost_click(selector):
                # Strategy 2: JS click by href match (bypasses overlay)
                clicked = await self.page.evaluate(f"""() => {{
                    const fragment = '{url_fragment}';
                    const links = document.querySelectorAll('ol.profile-list a[href*="/talent/profile/"]');
                    for (const link of links) {{
                        if (link.href.includes(fragment)) {{
                            link.click();
                            return true;
                        }}
                    }}
                    return false;
                }}""")
                if not clicked:
                    raise Exception(f"Could not find profile link for URL fragment '{url_fragment}'")

            await self.page.locator("div.profile-slidein__container").wait_for(
                state="visible", timeout=10000
            )
            await self.page.wait_for_timeout(1500)
        await _retry(_do)

    async def simulate_profile_read(self) -> None:
        """Scroll through profile panel to simulate a recruiter reading before extraction.

        Produces 8-20s of visible scrolling/dwelling depending on profile length.
        """
        container = self.page.locator("div.profile__main-container").first
        try:
            await container.wait_for(state="attached", timeout=5000)
        except Exception:
            return  # Profile not loaded, skip simulation

        try:
            height = await container.evaluate("el => el.scrollHeight")
            viewport_h = await container.evaluate("el => el.clientHeight")
        except Exception:
            await asyncio.sleep(human_delay_correlated(3.0))
            return

        if height <= viewport_h:
            # Profile fits in viewport, just dwell
            await asyncio.sleep(human_delay_correlated(3.0))
            return

        # Scroll down in sections, pausing to "read"
        scrolled = 0
        while scrolled < height - viewport_h:
            chunk = random.randint(200, 400)  # ~1-2 section heights
            await human_scroll(self.page, chunk)
            scrolled += chunk
            await asyncio.sleep(human_delay_correlated(random.uniform(1.5, 4.0)))

        # Scroll back to top for text extraction
        await human_scroll(self.page, -scrolled)
        await asyncio.sleep(human_delay_correlated(0.5))

    async def get_profile_innertext(self) -> str:
        """Get trimmed innerText from div.profile__main-container.

        Expands all collapsed "Read more" / "see more" sections first,
        then extracts text. Keeps header + Summary + Experience + Education.
        Skips Accomplishments, Volunteer Experience, Personal Information, etc.
        """
        async def _do():
            container = self.page.locator("div.profile__main-container").first
            await container.wait_for(state="attached", timeout=10000)

            # Expand all collapsed sections before extracting text
            await self._expand_all_readmore(container)

            full_text = await container.inner_text(timeout=15000)
            return _trim_profile_text(full_text)
        return await _retry(_do)

    async def _expand_all_readmore(self, container) -> None:
        """Expand collapsed sections in the profile slide-in.

        Only expands content sections that matter for evaluation:
        - About/Summary "see more" links
        - Experience entry description bullets
        - Education details

        Capped at 15 clicks. Uses ghost-cursor for human-like click trajectories.
        Skips skills endorsements, recommendations, and other non-eval sections.
        """
        MAX_EXPANSIONS = 15
        expand_texts = ['see more', 'read more', 'show more', 'ver mais']

        clickables = await container.locator('a, button, [role="button"]').all()
        clicked = 0

        for el in clickables:
            if clicked >= MAX_EXPANSIONS:
                break
            try:
                text = (await el.inner_text(timeout=1000)).strip().lower()
                if len(text) < 20 and any(t in text for t in expand_texts):
                    visible = await el.is_visible()
                    if visible:
                        await self._ghost_click_locator(el)
                        clicked += 1
                        await asyncio.sleep(human_delay_correlated(0.4))
            except Exception:
                continue

        if clicked:
            await self.page.wait_for_timeout(800)
            print(f"    [profile] Expanded {clicked} collapsed section(s)")

    async def go_back_to_results(self) -> None:
        """Dismiss the profile slide-in panel if it's open.

        The artdeco-modal-outlet overlay can block all Playwright clicks,
        so we use multiple strategies including JS-based dismissal.
        Never calls go_back() — that navigates away from the search page.
        """
        async def _do():
            slidein = self.page.locator("div.profile-slidein__container")
            if not await slidein.is_visible():
                return  # Slide-in not open — nothing to dismiss

            # Strategy 1: Find and click any close/dismiss button inside the modal via JS
            # (bypasses pointer-events interception)
            closed = await self.page.evaluate("""() => {
                const outlet = document.getElementById('artdeco-modal-outlet');
                if (!outlet) return false;
                // Try multiple close button patterns
                const selectors = [
                    'button[aria-label="Close"]',
                    'button[aria-label="close"]',
                    'button.artdeco-modal__dismiss',
                    'button[data-test-modal-close-btn]',
                    'button.artdeco-button--circle[aria-label]',
                ];
                for (const sel of selectors) {
                    const btn = outlet.querySelector(sel);
                    if (btn) { btn.click(); return true; }
                }
                return false;
            }""")
            if closed:
                await self.page.wait_for_timeout(1000)
                if not await slidein.is_visible():
                    return

            # Strategy 2: Escape key
            await self.page.keyboard.press("Escape")
            await self.page.wait_for_timeout(1000)
            if not await slidein.is_visible():
                return

            # Strategy 3: JS — click the back/close link in the slide-in header
            await self.page.evaluate("""() => {
                const outlet = document.getElementById('artdeco-modal-outlet');
                if (!outlet) return;
                // Click any <a> or <button> that looks like navigation back
                const links = outlet.querySelectorAll('a, button');
                for (const el of links) {
                    const text = (el.textContent || '').trim().toLowerCase();
                    const label = (el.getAttribute('aria-label') || '').toLowerCase();
                    if (text === '×' || text === 'x' || label.includes('close') ||
                        label.includes('dismiss') || label.includes('back')) {
                        el.click(); return;
                    }
                }
                // Nuclear: hide the modal outlet entirely
                outlet.style.display = 'none';
            }""")
            await self.page.wait_for_timeout(1000)

            # If we hid the outlet, restore it after a beat so future modals work
            await self.page.evaluate("""() => {
                const outlet = document.getElementById('artdeco-modal-outlet');
                if (outlet && outlet.style.display === 'none') {
                    outlet.style.display = '';
                    // Clear its children to remove stale modal content
                    outlet.innerHTML = '';
                }
            }""")
            await self.page.wait_for_timeout(500)
        await _retry(_do)

    async def next_profile_in_panel(self) -> bool:
        """Click "Next candidate" skyline-pagination-button in the slide-in."""
        try:
            buttons = self.page.locator("button.skyline-pagination-button")
            count = await buttons.count()
            for i in range(count):
                text = await buttons.nth(i).inner_text()
                if "next" in text.lower():
                    await buttons.nth(i).click()
                    await self.page.wait_for_timeout(1500)
                    return True
            return False
        except Exception:
            return False

    async def previous_profile_in_panel(self) -> bool:
        try:
            buttons = self.page.locator("button.skyline-pagination-button")
            count = await buttons.count()
            for i in range(count):
                text = await buttons.nth(i).inner_text()
                if "previous" in text.lower():
                    await buttons.nth(i).click()
                    await self.page.wait_for_timeout(1500)
                    return True
            return False
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Save candidate to pipeline
    # ------------------------------------------------------------------

    async def is_already_saved(self) -> bool:
        """Check if the currently open profile is already saved to the project.

        When a candidate is already saved, the 'Save to pipeline' button is
        replaced by a 'Change stage' button with different styling.
        """
        try:
            change_stage = self.page.locator(
                'button:has-text("Change stage"), '
                'button[data-test-change-stage-button]'
            ).first
            return await change_stage.is_visible(timeout=2000)
        except Exception:
            return False

    async def save_candidate(self) -> bool:
        """Click button.save-to-pipeline__button (NOT the dropdown trigger).

        Uses JS click to bypass artdeco-modal-outlet overlay elements
        that intercept pointer events inside the profile slide-in.
        """
        async def _do():
            selector = "button.save-to-pipeline__button"
            save_btn = self.page.locator(selector).first
            await save_btn.wait_for(state="visible", timeout=5000)
            # Ghost-cursor first (generates mouse trajectory), JS click as fallback
            if not await self._ghost_click(selector):
                await save_btn.evaluate("el => el.click()")
            await self.page.wait_for_timeout(2000)
            return True
        try:
            return await _retry(_do)
        except Exception as e:
            print(f"  [warn] Failed to save candidate: {e}")
            return False

    # ------------------------------------------------------------------
    # Legacy aliases (orchestrator compatibility)
    # ------------------------------------------------------------------

    async def get_results_page_dom(self) -> str:
        return await self.get_results_list_innertext()

    async def get_profile_dom(self) -> str:
        return await self.get_profile_innertext()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _trim_profile_text(full_text: str) -> str:
    """Trim profile innerText to relevant sections only."""
    lines = full_text.split("\n")
    trimmed = []
    skip_sections = {
        "accomplishments", "volunteer experience", "personal information",
        "similar profiles", "projects", "messages", "greenhouse", "feedback",
    }
    current_skip = False

    for line in lines:
        line_lower = line.strip().lower()
        if line_lower in skip_sections:
            current_skip = True
            continue
        if line_lower in {"summary", "experience", "education"}:
            current_skip = False
        if not current_skip:
            trimmed.append(line)

    return "\n".join(trimmed)


def run_sync(coro):
    return asyncio.get_event_loop().run_until_complete(coro)
