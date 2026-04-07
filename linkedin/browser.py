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
import subprocess
import sys
from typing import Optional, TYPE_CHECKING
from shared import config
from shared.human_timing import human_delay_correlated
from linkedin.input_backends import create_input_backend

if TYPE_CHECKING:
    from rebrowser_playwright.async_api import Browser, Page, BrowserContext

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5
_TARGET_CRASH_PATTERNS = (
    "target crashed",
    "page crashed",
    "session closed",
    "target closed",
)


def _is_target_crash_error(error: BaseException | str) -> bool:
    text = str(error).lower()
    return any(pattern in text for pattern in _TARGET_CRASH_PATTERNS)


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

    def __init__(self, input_mode: str = "concurrent"):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self.input_mode = input_mode
        self._input_backend = create_input_backend(input_mode)
        self._project_id: Optional[str] = None  # Auto-detected from browser URL

    async def connect(self) -> None:
        from rebrowser_playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(config.CDP_URL)
        if not self._browser.contexts:
            raise RuntimeError("No browser contexts found. Is the browser open?")

        if await self._bind_existing_recruiter_page():
            print(
                f"  Connected to browser ({self._input_backend.status_label}). "
                f"Active page: {self._page.url}"
            )
            return

        # No Recruiter tab found
        all_urls = []
        for ctx in self._browser.contexts:
            for page in ctx.pages:
                try:
                    all_urls.append(page.url)
                except Exception:
                    all_urls.append("(unavailable tab url)")
        urls_text = "\n    ".join(all_urls) if all_urls else "(no tabs open)"
        raise RuntimeError(
            f"No LinkedIn Recruiter tab found.\n"
            f"  Open linkedin.com/talent in Chrome, then run again.\n"
            f"  Found {len(all_urls)} tab(s):\n    {urls_text}"
        )

    async def disconnect(self) -> None:
        await self._input_backend.shutdown()
        if self._playwright:
            await self._playwright.stop()

    async def _bind_existing_recruiter_page(self) -> bool:
        """Bind to the first healthy LinkedIn Recruiter tab in the attached browser."""
        if not self._browser:
            return False

        for ctx in self._browser.contexts:
            for page in ctx.pages:
                try:
                    url = page.url
                except Exception:
                    continue
                if "linkedin.com/talent" not in url:
                    continue
                self._context = ctx
                self._page = page
                m = re.search(r"/talent/hire/(\d+)", url)
                if m:
                    self._project_id = m.group(1)
                await self._input_backend.initialize(self._page)
                return True
        return False

    async def _ghost_click(self, selector: str) -> bool:
        """Click using ghost-cursor (Bézier trajectory + Fitts's Law timing).

        Falls back to JS eval click if ghost-cursor unavailable or fails.
        Returns True if ghost-cursor succeeded, False if fell back to JS.
        """
        return await self._input_backend.click_selector(self.page, selector)

    async def _ghost_move(self, selector: str) -> bool:
        """Move cursor to element without clicking. Returns True if succeeded."""
        return await self._input_backend.move_selector(self.page, selector)

    async def _ghost_click_locator(self, locator) -> bool:
        """Ghost-click a Playwright Locator (not a CSS selector)."""
        if await self._input_backend.click_locator(self.page, locator):
            return True
        # Fallback to Playwright click
        await locator.click(timeout=5000)
        return False

    async def _human_scroll(self, delta_y: int, *, channel: str) -> None:
        await self._input_backend.scroll(self.page, delta_y, channel=channel)

    async def _press_key(self, key: str) -> None:
        handled = await self._input_backend.press_key(self.page, key)
        if not handled:
            await self.page.keyboard.press(key)

    async def _send_os_refresh_shortcut(self) -> bool:
        """Best-effort macOS Cmd+R fallback when Playwright page methods are unhealthy."""
        if sys.platform != "darwin":
            return False

        script = (
            'tell application "Google Chrome" to activate\n'
            'tell application "System Events"\n'
            '  keystroke "r" using command down\n'
            'end tell'
        )
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                text=True,
            )
            await asyncio.sleep(4)
            return True
        except Exception as e:
            print(f"  [recovery] OS-level Cmd+R failed: {e}")
            return False

    async def refresh_active_tab(self) -> bool:
        """Try increasingly forceful refresh mechanisms for the active Recruiter tab."""
        try:
            await self.page.reload(wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(4000)
            return True
        except Exception as reload_error:
            print(f"  [recovery] Page reload failed: {reload_error}")

        try:
            await self._press_key("Meta+R")
            await self.page.wait_for_timeout(4000)
            return True
        except Exception as shortcut_error:
            print(f"  [recovery] Playwright Meta+R failed: {shortcut_error}")

        return await self._send_os_refresh_shortcut()

    async def recover_from_target_crash(self, recovery_url: str | None = None) -> bool:
        """Recover from a Chromium target crash by refreshing and rebinding the Recruiter page."""
        print("  [recovery] Detected browser target crash — attempting tab refresh...")
        if not await self.refresh_active_tab():
            return False

        for _ in range(3):
            try:
                rebound = await self._bind_existing_recruiter_page()
            except Exception:
                rebound = False

            if rebound:
                if recovery_url:
                    try:
                        current_url = self.page.url
                    except Exception:
                        current_url = ""
                    if "linkedin.com/talent" not in current_url or "/manage/" in current_url:
                        await self.navigate_to_search(recovery_url)
                return True
            await asyncio.sleep(2)
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
            _ = self.page.url
        except Exception as e:
            if _is_target_crash_error(e):
                return await self.recover_from_target_crash()
            return False

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
        except Exception as e:
            if _is_target_crash_error(e):
                return await self.recover_from_target_crash()
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
        # Wait for sidebar filters to render. LinkedIn's SPA can take 8-15s
        # to hydrate the sidebar after DOM content loads.
        await self.page.wait_for_timeout(4000)  # minimum wait for initial render
        # Poll for sidebar keyword controls or results summary
        sidebar_selectors = [
            'textarea[id*="free-text-single-value-input"]',
            'button[aria-label*="Profile keywords"]',
            'button[aria-label*="Edit Keywords"]',
            'button[aria-label*="keywords" i]',
            '.search-query-summary__title',
        ]
        for _ in range(12):  # up to ~12 more seconds
            for sel in sidebar_selectors:
                try:
                    if await self.page.locator(sel).first.is_visible(timeout=500):
                        return  # sidebar rendered
                except Exception:
                    continue
            await self.page.wait_for_timeout(500)

        # If we get here, sidebar never appeared
        final_url = self.page.url
        raise RuntimeError(
            f"navigate_to_search failed: sidebar elements not found after 16s. "
            f"Page URL: {final_url[:120]}"
        )

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
            # Step 1: Reveal the textarea.
            # The sidebar Keywords section can be in several states:
            #   - Collapsed with "Profile keywords" button (field empty)
            #   - Expanded with textarea visible (field empty or being edited)
            #   - Showing applied keywords with edit/clear buttons
            textarea = self.page.locator('textarea[id*="free-text-single-value-input"]').first

            if not await textarea.is_visible(timeout=1000):
                # Textarea not visible — try to expand the Keywords section.
                # Search the sidebar for any button related to keywords.
                expanded = False
                sidebar_keyword_selectors = [
                    'button[aria-label*="Edit Profile keywords"]',
                    'button[aria-label*="Profile keywords"]',
                    'button[aria-label*="Edit Keywords"]',
                    'button[aria-label*="keywords or boolean" i]',
                    'button:has-text("Profile keywords")',
                ]
                for selector in sidebar_keyword_selectors:
                    try:
                        btn = self.page.locator(selector).first
                        if await btn.is_visible(timeout=1500):
                            await btn.click()
                            await self.page.wait_for_timeout(1500)
                            if await textarea.is_visible(timeout=1500):
                                expanded = True
                                break
                    except Exception:
                        continue

                if not expanded:
                    # Last resort: dump sidebar DOM for debugging
                    try:
                        title = await self.page.title()
                        url = self.page.url
                        print(f"    [DOM-DEBUG] Page: {title} | URL: {url[:100]}")
                        sidebar = self.page.locator('.keywords-facet, [data-test-facet-keywords]').first
                        sidebar_html = await sidebar.inner_html(timeout=3000)
                        import re as _re
                        buttons = _re.findall(r'<button[^>]*aria-label="([^"]*)"[^>]*>', sidebar_html)
                        print(f"    [DOM-DEBUG] Sidebar buttons: {buttons[:15]}")
                    except Exception:
                        try:
                            all_btns = await self.page.locator('button[aria-label]').all()
                            labels = []
                            for b in all_btns[:20]:
                                try:
                                    labels.append(await b.get_attribute('aria-label', timeout=1000))
                                except Exception:
                                    pass
                            print(f"    [DOM-DEBUG] All page button labels: {labels[:20]}")
                        except Exception as dbg_err:
                            print(f"    [DOM-DEBUG] Could not read page: {dbg_err}")

            # Step 3: Fill the sidebar textarea (the ONLY correct target)
            await textarea.wait_for(state="visible", timeout=10000)
            await textarea.fill(boolean)

            # Step 4: Submit
            await self._press_key("Enter")

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
        """Scroll the results list to trigger LinkedIn's lazy loading.

        Scrolls in human-like increments, counting rendered article cards
        after each step. Stops when no new cards appear for 3 consecutive
        scrolls (the page bottom has been reached).
        """
        cards_selector = "ol.profile-list article.profile-list-item"

        if await self.page.locator("ol.profile-list").count() == 0:
            return 0

        MAX_SCROLLS = 50        # safety cap (50×400 = 20,000px, well beyond 26 cards)
        STABLE_ROUNDS = 3       # stop after 3 scrolls with no new cards

        total_scrolled = 0
        prev_count = await self.page.locator(cards_selector).count()
        stable = 0

        for scroll_num in range(1, MAX_SCROLLS + 1):
            if stable >= STABLE_ROUNDS:
                break

            step = random.randint(260, 560)
            await self._human_scroll(step, channel="results_list")
            total_scrolled += step

            # Occasional scan pause while reviewing newly exposed cards.
            if scroll_num % random.randint(4, 6) == 0:
                await asyncio.sleep(human_delay_correlated(0.5, channel="results_list_scan"))

            # Let DOM update after scroll
            await self.page.wait_for_timeout(300)

            current_count = await self.page.locator(cards_selector).count()
            if current_count > prev_count:
                prev_count = current_count
                stable = 0
                if random.random() < 0.35:
                    await asyncio.sleep(
                        human_delay_correlated(
                            random.uniform(0.5, 1.4),
                            channel="results_list_scan",
                        )
                    )
            else:
                stable += 1
                if random.random() < 0.25:
                    await asyncio.sleep(
                        human_delay_correlated(
                            random.uniform(0.15, 0.45),
                            channel="results_list_scan",
                        )
                    )

        # Final wait for remaining renders
        await self.page.wait_for_timeout(800)

        # Scroll back to top
        if total_scrolled > 0:
            await self._human_scroll(-total_scrolled, channel="results_list_return")
        await asyncio.sleep(human_delay_correlated(0.3, channel="results_list_return"))

        return await self.page.locator(cards_selector).count()

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
        """Get innerText of result list items that have rendered article cards."""
        if await self.page.locator("ol.profile-list").count() == 0:
            return ""
        async def _do():
            # Only include <li> elements that have a rendered <article> child
            rendered_li = self.page.locator(
                "ol.profile-list > li:has(article.profile-list-item)"
            )
            count = await rendered_li.count()
            if count == 0:
                return ""
            texts = []
            for i in range(count):
                texts.append(await rendered_li.nth(i).inner_text(timeout=5000))
            return "\n".join(texts)
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

    async def get_card_saved_status(self) -> list[bool]:
        """Check each rendered card for already-saved indicators.

        Saved candidates show 'Change stage' button instead of
        'Save to pipeline'. Returns list of bools in DOM order.
        """
        async def _do():
            cards = self.page.locator("ol.profile-list article.profile-list-item")
            count = await cards.count()
            statuses = []
            for i in range(count):
                card = cards.nth(i)
                try:
                    change_btn = card.locator(
                        ':is(button:has-text("Change stage"), '
                        'button[data-test-change-stage-button])'
                    ).first
                    is_saved = await change_btn.is_visible(timeout=500)
                except Exception:
                    is_saved = False
                statuses.append(is_saved)
            return statuses
        return await _retry(_do)

    async def get_card_slot_count(self) -> int:
        """Count result slots, including offscreen virtualized cards."""
        slots = self.page.locator("ol.profile-list > li")
        return await slots.count()

    async def _wait_for_result_slot(self, card_index: int, timeout_ms: int = 8000):
        """Wait for a specific results-list slot to exist after DOM re-hydration.

        Recruiter occasionally tears down and rebuilds the results list while the
        slide-in closes or while the viewport is being repositioned. During that
        window, `nth(card_index)` can temporarily stop resolving even though the
        page is still healthy. We wait for the slot count to recover instead of
        failing the whole string on a transient list rebuild.
        """
        list_root = self.page.locator("ol.profile-list").first
        await list_root.wait_for(state="visible", timeout=timeout_ms)

        slots = self.page.locator("ol.profile-list > li")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (timeout_ms / 1000.0)
        last_count = 0
        last_error: Exception | None = None

        while loop.time() < deadline:
            try:
                count = await slots.count()
                last_count = count
                if count > card_index:
                    li = slots.nth(card_index)
                    await li.wait_for(state="attached", timeout=1000)
                    return li
            except Exception as e:
                last_error = e

            await self.page.wait_for_timeout(200)

        details = f"Result slot {card_index + 1} unavailable after waiting (saw {last_count} slots)"
        if last_error:
            details = f"{details}: {last_error}"
        raise TimeoutError(details)

    async def get_card_count(self) -> int:
        cards = self.page.locator("ol.profile-list article.profile-list-item")
        return await cards.count()

    async def focus_card_for_review(self, card_index: int) -> None:
        """Bring a result card into a readable viewport position with visible scrolling."""
        li = await self._wait_for_result_slot(card_index)

        try:
            rect = await li.evaluate("""el => {
                const r = el.getBoundingClientRect();
                return { top: r.top, bottom: r.bottom, height: r.height };
            }""")
            viewport_h = await self.page.evaluate("() => window.innerHeight")
            target_top = random.randint(130, max(180, min(320, int(viewport_h * 0.35))))

            if rect:
                delta = rect["top"] - target_top
                if abs(delta) > 40:
                    await self._human_scroll(int(delta), channel="results_review")
                    if random.random() < 0.25:
                        correction = random.randint(12, 36)
                        await self._human_scroll(
                            -correction if delta > 0 else correction,
                            channel="results_review",
                        )
            await self.page.wait_for_timeout(450)
            article = li.locator("article.profile-list-item").first
            await article.wait_for(state="visible", timeout=3000)
        except Exception:
            li = await self._wait_for_result_slot(card_index)
            await li.scroll_into_view_if_needed(timeout=3000)
            await self.page.wait_for_timeout(600)
            article = li.locator("article.profile-list-item").first
            await article.wait_for(state="visible", timeout=4000)

    async def get_card_snapshot(self, card_index: int) -> dict:
        """Read one result card's rendered text plus stable DOM metadata."""
        async def _do():
            li = await self._wait_for_result_slot(card_index)
            article = li.locator("article.profile-list-item").first
            await article.wait_for(state="visible", timeout=5000)

            innertext = await article.inner_text(timeout=10000)

            name = ""
            url = ""
            try:
                name_el = article.locator('[class*="lockup__title"] a').first
                name = (await name_el.inner_text(timeout=2000)).strip()
                url = (await name_el.get_attribute("href")) or ""
            except Exception:
                try:
                    link = article.locator('a[href*="/talent/profile/"]').first
                    url = (await link.get_attribute("href")) or ""
                    name = (await link.inner_text(timeout=2000)).strip()
                except Exception:
                    pass

            already_saved = False
            try:
                change_btn = article.locator(
                    ':is(button:has-text("Change stage"), button[data-test-change-stage-button])'
                ).first
                already_saved = await change_btn.is_visible(timeout=500)
            except Exception:
                already_saved = False

            return {
                "innertext": innertext,
                "name": name,
                "url": url,
                "already_saved": already_saved,
            }

        return await _retry(_do)

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
            li = await self._wait_for_result_slot(card_index)
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

    # ── Profile reading patterns ────────────────────────────────────

    _CHUNK_SIZE = 400  # ~4-5 card heights

    _PATTERN_WEIGHTS = {
        "short":  [0.55, 0.05, 0.30, 0.10],
        "medium": [0.40, 0.25, 0.20, 0.15],
        "long":   [0.25, 0.30, 0.15, 0.30],
    }
    _PATTERN_NAMES = ["focused_reader", "skipper", "skimmer", "section_hopper"]

    # Base dwell values
    _BASE_SHORT_DWELL = 3.0
    _BASE_CHUNK_DWELL_LOW = 1.5
    _BASE_CHUNK_DWELL_HIGH = 4.0

    async def simulate_profile_read(self) -> None:
        """Scroll through profile panel to simulate a recruiter reading before extraction.

        Selects from 4 reading patterns (focused, skipper, skimmer, hopper)
        weighted by profile length. Produces realistic, varied scroll behavior.
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
            await asyncio.sleep(human_delay_correlated(self._BASE_SHORT_DWELL, channel="profile_read"))
            return

        if height <= viewport_h:
            # Profile fits in viewport, just dwell
            await asyncio.sleep(human_delay_correlated(self._BASE_SHORT_DWELL, channel="profile_read"))
            return

        scrollable = height - viewport_h
        chunk_count = max(1, scrollable // self._CHUNK_SIZE)

        if chunk_count <= 2:
            length_cat = "short"
        elif chunk_count <= 5:
            length_cat = "medium"
        else:
            length_cat = "long"

        pattern = random.choices(self._PATTERN_NAMES, weights=self._PATTERN_WEIGHTS[length_cat])[0]
        print(f"    [profile-read] {length_cat.title()} profile ({chunk_count} chunks) → Pattern: {pattern}")

        if pattern == "focused_reader":
            await self._read_focused(scrollable)
        elif pattern == "skipper":
            await self._read_skipper(scrollable)
        elif pattern == "skimmer":
            await self._read_skimmer(scrollable)
        else:
            await self._read_section_hopper(scrollable)

    async def _read_focused(self, scrollable: int) -> None:
        """Pattern A — Focused reader: top to bottom with careful/skim per chunk."""
        chunk_size = random.randint(300, 500)
        chunks = max(1, scrollable // chunk_size)
        reread_chunk = random.randint(0, chunks - 1)
        scrolled = 0

        for i in range(chunks):
            px = min(chunk_size, scrollable - scrolled)
            await self._human_scroll(px, channel="profile_read")
            scrolled += px

            if random.random() < 0.4:
                # Careful read: 2-4x base dwell
                base = random.uniform(self._BASE_CHUNK_DWELL_LOW, self._BASE_CHUNK_DWELL_HIGH)
                dwell = base * random.uniform(2.0, 4.0)
            else:
                # Skim: 0.3-0.5x base dwell
                base = random.uniform(self._BASE_CHUNK_DWELL_LOW, self._BASE_CHUNK_DWELL_HIGH)
                dwell = base * random.uniform(0.3, 0.5)

            await asyncio.sleep(human_delay_correlated(dwell, channel="profile_read"))

            if i == reread_chunk:
                # Re-read pause
                await asyncio.sleep(human_delay_correlated(random.uniform(2.0, 8.0), channel="profile_read"))

        # Scroll back to top
        await self._human_scroll(-scrolled, channel="profile_read_return")
        await asyncio.sleep(human_delay_correlated(0.5, channel="profile_read_return"))

    async def _read_skipper(self, scrollable: int) -> None:
        """Pattern B — Skipper: jump to bottom section, back up, then finish."""
        chunk_size = random.randint(300, 500)

        # 1. Fast scroll to ~60-70% height
        target_1 = int(scrollable * random.uniform(0.6, 0.7))
        chunks_down_1 = max(1, target_1 // chunk_size)
        scrolled = 0
        for _ in range(chunks_down_1):
            px = min(chunk_size, target_1 - scrolled)
            await self._human_scroll(px, channel="profile_read")
            scrolled += px
            base = random.uniform(self._BASE_CHUNK_DWELL_LOW, self._BASE_CHUNK_DWELL_HIGH)
            await asyncio.sleep(human_delay_correlated(base * 0.3, channel="profile_read"))

        # 2. Pause
        await asyncio.sleep(human_delay_correlated(random.uniform(3.0, 8.0), channel="profile_read"))

        # 3. Scroll back up to ~20-30%
        target_2 = int(scrollable * random.uniform(0.2, 0.3))
        scroll_up = scrolled - target_2
        if scroll_up > 0:
            chunks_up = max(1, scroll_up // chunk_size)
            for _ in range(chunks_up):
                px = min(chunk_size, scroll_up)
                await self._human_scroll(-px, channel="profile_read")
                scrolled -= px
                scroll_up -= px
                base = random.uniform(self._BASE_CHUNK_DWELL_LOW, self._BASE_CHUNK_DWELL_HIGH)
                await asyncio.sleep(human_delay_correlated(base * 0.5, channel="profile_read"))

        # 4. Pause
        await asyncio.sleep(human_delay_correlated(random.uniform(2.0, 5.0), channel="profile_read"))

        # 5. Scroll to bottom
        remaining = scrollable - scrolled
        if remaining > 0:
            chunks_rest = max(1, remaining // chunk_size)
            for _ in range(chunks_rest):
                px = min(chunk_size, remaining)
                await self._human_scroll(px, channel="profile_read")
                scrolled += px
                remaining -= px
                base = random.uniform(self._BASE_CHUNK_DWELL_LOW, self._BASE_CHUNK_DWELL_HIGH)
                await asyncio.sleep(human_delay_correlated(base, channel="profile_read"))

        # Scroll back to top
        await self._human_scroll(-scrolled, channel="profile_read_return")
        await asyncio.sleep(human_delay_correlated(0.5, channel="profile_read_return"))

    async def _read_skimmer(self, scrollable: int) -> None:
        """Pattern C — Skimmer: fast down, slow back up."""
        chunk_size = random.randint(300, 500)
        chunks = max(1, scrollable // chunk_size)
        scrolled = 0

        # 1. Fast scroll down
        for _ in range(chunks):
            px = min(chunk_size, scrollable - scrolled)
            await self._human_scroll(px, channel="profile_read")
            scrolled += px
            base = random.uniform(self._BASE_CHUNK_DWELL_LOW, self._BASE_CHUNK_DWELL_HIGH)
            await asyncio.sleep(human_delay_correlated(base * random.uniform(0.3, 0.8), channel="profile_read"))

        # 2. Bottom pause
        await asyncio.sleep(human_delay_correlated(random.uniform(1.0, 3.0), channel="profile_read"))

        # 3. Slow scroll back up
        scroll_remaining = scrolled
        while scroll_remaining > 0:
            px = min(chunk_size, scroll_remaining)
            await self._human_scroll(-px, channel="profile_read")
            scroll_remaining -= px
            base = random.uniform(self._BASE_CHUNK_DWELL_LOW, self._BASE_CHUNK_DWELL_HIGH)
            await asyncio.sleep(human_delay_correlated(base * random.uniform(1.5, 3.0), channel="profile_read"))

        await asyncio.sleep(human_delay_correlated(0.5, channel="profile_read_return"))

    async def _read_section_hopper(self, scrollable: int) -> None:
        """Pattern D — Section hopper: top to bottom with 1-2 backtracks."""
        chunk_size = random.randint(300, 500)
        chunks = max(1, scrollable // chunk_size)
        backtrack_points = sorted(random.sample(range(1, max(2, chunks)), min(random.randint(1, 2), chunks - 1)))
        scrolled = 0

        for i in range(chunks):
            px = min(chunk_size, scrollable - scrolled)
            await self._human_scroll(px, channel="profile_read")
            scrolled += px
            base = random.uniform(self._BASE_CHUNK_DWELL_LOW, self._BASE_CHUNK_DWELL_HIGH)
            await asyncio.sleep(human_delay_correlated(base, channel="profile_read"))

            if i in backtrack_points:
                # Backtrack: scroll UP 1 chunk, pause, then resume
                backtrack_px = min(chunk_size, scrolled)
                await self._human_scroll(-backtrack_px, channel="profile_read")
                scrolled -= backtrack_px
                await asyncio.sleep(human_delay_correlated(random.uniform(2.0, 4.0), channel="profile_read"))
                # Resume forward
                await self._human_scroll(backtrack_px, channel="profile_read")
                scrolled += backtrack_px

        # Scroll back to top
        await self._human_scroll(-scrolled, channel="profile_read_return")
        await asyncio.sleep(human_delay_correlated(0.5, channel="profile_read_return"))

    # ── Scroll helpers for post-evaluation dwell ─────────────────

    async def scroll_for_linger(self, chunks_back: int) -> int:
        """Scroll back up N chunks for re-reading, return actual pixels scrolled."""
        requested = chunks_back * random.randint(300, 500)
        try:
            current_top = int(
                await self.page.locator("div.profile__main-container").first.evaluate(
                    "el => el.scrollTop"
                )
            )
        except Exception:
            current_top = 0

        px = min(requested, max(0, current_top))
        if px > 0:
            await self._human_scroll(-px, channel="profile_linger")
        return px

    async def scroll_restore(self, px: int):
        """Scroll back down to restore position."""
        if px > 0:
            await self._human_scroll(px, channel="profile_linger")

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
                        await asyncio.sleep(human_delay_correlated(0.4, channel="profile_expand"))
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
            await self._press_key("Escape")
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
                'div.profile-slidein__container :is(button:has-text("Change stage"), '
                'button[data-test-change-stage-button])'
            ).first
            return await change_stage.is_visible(timeout=2000)
        except Exception:
            return False

    async def save_candidate(self) -> bool:
        """Click button.save-to-pipeline__button (NOT the dropdown trigger).

        Uses JS click to bypass artdeco-modal-outlet overlay elements
        that intercept pointer events inside the profile slide-in.
        After clicking, verifies the save persisted by checking that the
        button changed from 'Save to pipeline' to 'Change stage'.
        """
        async def _do():
            if await self.is_already_saved():
                return True

            slidein = self.page.locator("div.profile-slidein__container").first
            await slidein.wait_for(state="visible", timeout=5000)

            selector = "div.profile-slidein__container button.save-to-pipeline__button"
            save_btn = self.page.locator(selector).first
            try:
                await save_btn.wait_for(state="visible", timeout=5000)
            except Exception:
                if await self.is_already_saved():
                    return True
                # The slide-in occasionally lands mid-scroll after profile review.
                # Scroll back to the top-level action bar once before giving up.
                try:
                    container = self.page.locator("div.profile__main-container").first
                    await container.evaluate("el => { el.scrollTop = 0; }")
                    await self.page.wait_for_timeout(300)
                except Exception:
                    pass
                if await self.is_already_saved():
                    return True
                await save_btn.wait_for(state="visible", timeout=3000)
            # Ghost-cursor first (generates mouse trajectory), JS click as fallback
            if not await self._ghost_click(selector):
                await save_btn.evaluate("el => el.click()")
            await self.page.wait_for_timeout(2000)
            # Verify: button should now show "Change stage" instead of "Save to pipeline"
            if await self.is_already_saved():
                return True
            raise Exception("Save click did not persist — button still shows 'Save to pipeline'")
        try:
            return await _retry(_do)
        except Exception as e:
            try:
                if await self.is_already_saved():
                    return True
            except Exception:
                pass
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
