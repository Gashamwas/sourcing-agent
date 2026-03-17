"""Shared utilities for decoy actions — ghost-cursor clicks and human scrolling."""

import asyncio
import random
from human_timing import human_delay


async def ghost_click(cursor, page, selector_or_locator):
    """Click using ghost-cursor Bézier trajectory, fallback to Playwright .click().

    Mirrors LinkedInBrowser._ghost_click() from browser.py — same timeout,
    same fallback pattern, so both agents produce identical click signatures.

    Args:
        cursor: python_ghost_cursor cursor instance (or None)
        page: Playwright page object
        selector_or_locator: CSS selector string, Playwright Locator, or ElementHandle
    """
    if cursor:
        try:
            # ghost-cursor accepts CSS selectors and ElementHandles
            await asyncio.wait_for(cursor.click(selector_or_locator), timeout=5.0)
            return
        except Exception:
            pass

    # Fallback: use Playwright click
    if isinstance(selector_or_locator, str):
        locator = page.locator(selector_or_locator).first
        await locator.click(timeout=5000)
    else:
        # ElementHandle or Locator
        await selector_or_locator.click(timeout=5000)


async def human_scroll(page, delta_y):
    """Scroll using chunked page.mouse.wheel() calls for realistic behavior.

    Uses page.mouse.wheel() which dispatches isTrusted:true mouseWheel events
    via Playwright's internal CDP channel — no manual CDP session management.

    Args:
        page: Playwright page object
        delta_y: Total scroll distance in pixels (positive = down)
    """
    direction = 1 if delta_y > 0 else -1
    remaining = abs(delta_y)

    while remaining > 0:
        chunk = min(remaining, random.randint(40, 150))
        await page.mouse.wheel(0, chunk * direction)
        remaining -= chunk
        await asyncio.sleep(random.uniform(0.015, 0.06))
