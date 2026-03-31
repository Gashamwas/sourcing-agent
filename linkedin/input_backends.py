"""Session-scoped input backends for concurrent and away-from-keyboard modes."""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.util
import math
import random
import sys
from typing import TYPE_CHECKING

from decoy.actions._utils import human_scroll
from shared.human_timing import human_delay_correlated

if TYPE_CHECKING:
    from rebrowser_playwright.async_api import Locator, Page


def normalize_input_mode(mode: str | None) -> str:
    raw = (mode or "concurrent").strip().lower().replace("-", "_")
    aliases = {
        "concurrent": "concurrent",
        "synthetic": "concurrent",
        "ghostcursor": "concurrent",
        "ghost_cursor": "concurrent",
        "away": "away",
        "takeover": "away",
        "away_from_keyboard": "away",
        "afk": "away",
    }
    if raw not in aliases:
        raise ValueError(f"Unsupported input mode: {mode}")
    return aliases[raw]


class InputBackend:
    """Abstract browser input backend."""

    mode = "concurrent"
    status_label = "uninitialized"

    async def initialize(self, page: "Page") -> None:  # pragma: no cover - interface
        raise NotImplementedError

    async def shutdown(self) -> None:
        return None

    async def click_selector(self, page: "Page", selector: str) -> bool:
        raise NotImplementedError

    async def move_selector(self, page: "Page", selector: str) -> bool:
        raise NotImplementedError

    async def click_locator(self, page: "Page", locator: "Locator") -> bool:
        raise NotImplementedError

    async def scroll(self, page: "Page", delta_y: int, *, channel: str = "scroll") -> None:
        raise NotImplementedError

    async def press_key(self, page: "Page", key: str) -> bool:
        raise NotImplementedError


class ConcurrentInputBackend(InputBackend):
    """Current synthetic-input mode: Playwright + ghost cursor."""

    mode = "concurrent"

    def __init__(self):
        self._cursor = None
        self.status_label = "ghost-cursor unavailable"

    async def initialize(self, page: "Page") -> None:
        try:
            from python_ghost_cursor.playwright_async import create_cursor

            self._cursor = create_cursor(page)
            self.status_label = "ghost-cursor active"
        except Exception as e:  # pragma: no cover - depends on optional dependency
            self._cursor = None
            self.status_label = f"ghost-cursor unavailable: {e}"

    async def click_selector(self, page: "Page", selector: str) -> bool:
        if self._cursor:
            try:
                await asyncio.wait_for(self._cursor.click(selector), timeout=5.0)
                return True
            except Exception:
                pass
        return False

    async def move_selector(self, page: "Page", selector: str) -> bool:
        if self._cursor:
            try:
                await asyncio.wait_for(self._cursor.move(selector), timeout=5.0)
                return True
            except Exception:
                pass
        return False

    async def click_locator(self, page: "Page", locator: "Locator") -> bool:
        if self._cursor:
            try:
                handle = await locator.element_handle(timeout=3000)
                if handle:
                    await asyncio.wait_for(self._cursor.click(handle), timeout=5.0)
                    return True
            except Exception:
                pass
        return False

    async def scroll(self, page: "Page", delta_y: int, *, channel: str = "scroll") -> None:
        await human_scroll(page, delta_y, channel=channel)

    async def press_key(self, page: "Page", key: str) -> bool:
        await page.keyboard.press(key)
        return True


class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CoreGraphicsBridge:
    """Tiny ctypes bridge for the subset of CoreGraphics we need."""

    kCGHIDEventTap = 0
    kCGEventLeftMouseDown = 1
    kCGEventLeftMouseUp = 2
    kCGEventMouseMoved = 5
    kCGEventKeyDown = 10
    kCGEventKeyUp = 11
    kCGMouseButtonLeft = 0
    kCGScrollEventUnitPixel = 1

    def __init__(self):
        if sys.platform != "darwin":
            raise RuntimeError("Away mode currently supports macOS only.")

        app_services = ctypes.util.find_library("ApplicationServices")
        core_foundation = ctypes.util.find_library("CoreFoundation")
        if not app_services or not core_foundation:
            raise RuntimeError("CoreGraphics frameworks not available on this machine.")

        self._cg = ctypes.CDLL(app_services)
        self._cf = ctypes.CDLL(core_foundation)

        self._cg.CGEventCreate.argtypes = [ctypes.c_void_p]
        self._cg.CGEventCreate.restype = ctypes.c_void_p

        self._cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]
        self._cg.CGEventGetLocation.restype = _CGPoint

        self._cg.CGEventCreateMouseEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            _CGPoint,
            ctypes.c_uint32,
        ]
        self._cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p

        self._cg.CGEventCreateKeyboardEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint16,
            ctypes.c_bool,
        ]
        self._cg.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p

        self._cg.CGEventCreateScrollWheelEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_int32,
        ]
        self._cg.CGEventCreateScrollWheelEvent.restype = ctypes.c_void_p

        self._cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        self._cg.CGEventPost.restype = None

        self._cf.CFRelease.argtypes = [ctypes.c_void_p]
        self._cf.CFRelease.restype = None

    def _release(self, ref: int | None) -> None:
        if ref:
            self._cf.CFRelease(ref)

    def current_location(self) -> tuple[float, float]:
        event = self._cg.CGEventCreate(None)
        if not event:
            return 0.0, 0.0
        try:
            point = self._cg.CGEventGetLocation(event)
            return point.x, point.y
        finally:
            self._release(event)

    def post_mouse(self, event_type: int, x: float, y: float) -> None:
        event = self._cg.CGEventCreateMouseEvent(
            None,
            event_type,
            _CGPoint(x, y),
            self.kCGMouseButtonLeft,
        )
        if not event:
            raise RuntimeError("Failed to create CoreGraphics mouse event.")
        try:
            self._cg.CGEventPost(self.kCGHIDEventTap, event)
        finally:
            self._release(event)

    def post_key(self, key_code: int, is_down: bool) -> None:
        event = self._cg.CGEventCreateKeyboardEvent(None, key_code, is_down)
        if not event:
            raise RuntimeError("Failed to create CoreGraphics keyboard event.")
        try:
            self._cg.CGEventPost(self.kCGHIDEventTap, event)
        finally:
            self._release(event)

    def post_scroll(self, delta_y: int) -> None:
        # CoreGraphics uses positive values for up and negative for down. Our
        # browser helpers use positive delta_y for down to match Playwright.
        event = self._cg.CGEventCreateScrollWheelEvent(
            None,
            self.kCGScrollEventUnitPixel,
            1,
            int(-delta_y),
        )
        if not event:
            raise RuntimeError("Failed to create CoreGraphics scroll event.")
        try:
            self._cg.CGEventPost(self.kCGHIDEventTap, event)
        finally:
            self._release(event)


class AwayInputBackend(InputBackend):
    """Real macOS takeover mode using CoreGraphics events."""

    mode = "away"
    KEY_CODES = {
        "Enter": 36,
        "Escape": 53,
        "Tab": 48,
        "Space": 49,
    }

    def __init__(self):
        self._cg = _CoreGraphicsBridge()
        self.status_label = "CoreGraphics takeover active"

    async def initialize(self, page: "Page") -> None:
        return None

    async def click_selector(self, page: "Page", selector: str) -> bool:
        locator = page.locator(selector).first
        return await self.click_locator(page, locator)

    async def move_selector(self, page: "Page", selector: str) -> bool:
        locator = page.locator(selector).first
        point = await self._locator_screen_point(page, locator)
        if point is None:
            return False
        await self._move_mouse(point[0], point[1], channel="os_pointer")
        return True

    async def click_locator(self, page: "Page", locator: "Locator") -> bool:
        point = await self._locator_screen_point(page, locator)
        if point is None:
            return False

        await self._move_mouse(point[0], point[1], channel="os_pointer")
        await asyncio.sleep(
            human_delay_correlated(random.uniform(0.04, 0.14), channel="os_pointer")
        )
        self._cg.post_mouse(_CoreGraphicsBridge.kCGEventLeftMouseDown, point[0], point[1])
        await asyncio.sleep(
            human_delay_correlated(random.uniform(0.03, 0.09), channel="os_pointer")
        )
        self._cg.post_mouse(_CoreGraphicsBridge.kCGEventLeftMouseUp, point[0], point[1])
        return True

    async def scroll(self, page: "Page", delta_y: int, *, channel: str = "scroll") -> None:
        if delta_y == 0:
            return

        direction = 1 if delta_y > 0 else -1
        remaining = abs(delta_y)
        while remaining > 0:
            chunk = min(remaining, max(20, int(random.lognormvariate(math.log(85), 0.35))))
            self._cg.post_scroll(chunk * direction)
            remaining -= chunk
            await asyncio.sleep(
                human_delay_correlated(0.03, spread=0.45, channel=f"{channel}_micro")
            )

    async def press_key(self, page: "Page", key: str) -> bool:
        key_code = self.KEY_CODES.get(key)
        if key_code is None:
            return False
        self._cg.post_key(key_code, True)
        await asyncio.sleep(
            human_delay_correlated(random.uniform(0.03, 0.08), channel="os_key")
        )
        self._cg.post_key(key_code, False)
        return True

    async def _locator_screen_point(
        self,
        page: "Page",
        locator: "Locator",
    ) -> tuple[float, float] | None:
        try:
            await locator.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass

        box = await locator.bounding_box()
        if not box:
            return None

        metrics = await page.evaluate("""() => ({
            screenX: window.screenX,
            screenY: window.screenY
        })""")
        return (
            float(metrics["screenX"]) + float(box["x"]) + float(box["width"]) / 2.0,
            float(metrics["screenY"]) + float(box["y"]) + float(box["height"]) / 2.0,
        )

    async def _move_mouse(self, end_x: float, end_y: float, *, channel: str) -> None:
        start_x, start_y = self._cg.current_location()
        dx = end_x - start_x
        dy = end_y - start_y
        distance = math.hypot(dx, dy)

        if distance < 1.0:
            self._cg.post_mouse(_CoreGraphicsBridge.kCGEventMouseMoved, end_x, end_y)
            return

        steps = max(8, min(28, int(distance / random.uniform(18.0, 32.0))))
        duration = min(0.95, max(0.18, 0.10 + distance / 1400.0 + random.uniform(0.08, 0.18)))

        ctrl1 = (
            start_x + dx * random.uniform(0.18, 0.32) + random.uniform(-24.0, 24.0),
            start_y + dy * random.uniform(0.18, 0.32) + random.uniform(-24.0, 24.0),
        )
        ctrl2 = (
            start_x + dx * random.uniform(0.62, 0.82) + random.uniform(-24.0, 24.0),
            start_y + dy * random.uniform(0.62, 0.82) + random.uniform(-24.0, 24.0),
        )

        for step in range(1, steps + 1):
            t = step / steps
            inv = 1.0 - t
            x = (
                inv ** 3 * start_x
                + 3 * inv ** 2 * t * ctrl1[0]
                + 3 * inv * t ** 2 * ctrl2[0]
                + t ** 3 * end_x
            )
            y = (
                inv ** 3 * start_y
                + 3 * inv ** 2 * t * ctrl1[1]
                + 3 * inv * t ** 2 * ctrl2[1]
                + t ** 3 * end_y
            )
            self._cg.post_mouse(_CoreGraphicsBridge.kCGEventMouseMoved, x, y)
            await asyncio.sleep(
                human_delay_correlated(
                    max(0.004, duration / steps),
                    spread=0.35,
                    channel=f"{channel}_micro",
                )
            )


def create_input_backend(mode: str | None) -> InputBackend:
    normalized = normalize_input_mode(mode)
    if normalized == "concurrent":
        return ConcurrentInputBackend()
    return AwayInputBackend()
