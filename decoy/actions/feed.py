"""Feed scrolling — passive, no engagement."""

import asyncio
import random
import time
from human_timing import human_delay, human_delay_correlated


async def scroll_feed(page) -> dict:
    """Scroll the LinkedIn feed passively.

    No likes, comments, shares, or expansions. Variable scroll depth.
    Dwell on ~30-50% of posts as they scroll into view.

    Args:
        page: Playwright page object (on linkedin.com/feed)

    Returns:
        dict with action metadata (type, duration)
    """
    start = time.time()

    # Navigate to feed if not already there
    if "/feed" not in page.url:
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        await asyncio.sleep(human_delay(1.5, 3.0))

    viewport = await page.evaluate("JSON.stringify({w: window.innerWidth, h: window.innerHeight})")
    import json
    vp = json.loads(viewport)
    vh = vp["h"]

    # Variable scroll depth: 3-10 screen-heights
    screen_heights = random.randint(3, 10)
    total_scroll = screen_heights * vh
    scrolled = 0

    while scrolled < total_scroll:
        # Scroll one partial screen-height
        scroll_amount = int(vh * random.uniform(0.3, 0.8))

        # Use mouse wheel via CDP for isTrusted events
        cdp = await page.context.new_cdp_session(page)
        try:
            # Break into smaller wheel events for realism
            remaining = scroll_amount
            while remaining > 0:
                chunk = min(remaining, random.randint(40, 150))
                await cdp.send("Input.dispatchMouseEvent", {
                    "type": "mouseWheel",
                    "x": vp["w"] // 2,
                    "y": vh // 2,
                    "deltaX": 0,
                    "deltaY": chunk,
                })
                remaining -= chunk
                await asyncio.sleep(random.uniform(0.015, 0.06))
        finally:
            await cdp.detach()

        scrolled += scroll_amount

        # Dwell on ~30-50% of scroll stops (simulating reading a post)
        if random.random() < random.uniform(0.3, 0.5):
            await asyncio.sleep(random.uniform(1, 5))
        else:
            await asyncio.sleep(human_delay(0.3, 1.0))

    duration = round(time.time() - start, 1)
    return {"type": "feed_scroll", "screen_heights": screen_heights, "duration": duration}
