"""Session Governor — enforces hard safety limits on sourcing sessions.

All limits are constants. No flags, no env vars, no "just five more" escape hatches.
"""

import datetime
import random
import time
from typing import Optional

import cooldown

# ──────────────────────────────────────────────────────────────────────
# HARD LIMITS (do not make these configurable)
# ──────────────────────────────────────────────────────────────────────

MAX_SESSION_DURATION_SECONDS = 3 * 3600          # 3 hours wall clock
MAX_PROFILE_OPENS_PER_SESSION = 200
MAX_PROFILE_OPENS_PER_24H = 400
TIME_OF_DAY_START_HOUR = 7                        # 7:00 AM local
TIME_OF_DAY_END_HOUR = 23                         # 11:00 PM local (hard ceiling — no jitter past this)
MAX_SESSIONS_PER_DAY = 3
CHECK_INTERVAL_SECONDS = 10 * 60                  # Check time-of-day every 10 min


class GovernorLimitReached(Exception):
    """Raised when a governor limit is hit."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class SessionExpired(Exception):
    """Raised when the session duration cap is reached cooperatively."""
    def __init__(self, reason: str = "session_duration_cap"):
        self.reason = reason
        super().__init__(reason)


class SessionGovernor:
    """Enforces hard limits for a single sourcing session."""

    def __init__(self):
        self._session_start: float = 0.0
        self._profile_opens_session: int = 0
        self._active: bool = False
        self._shutdown_reason: Optional[str] = None
        self._original_open_profile = None
        self._original_open_profile_by_url = None

        # Time-of-day jitter: sampled once per governor instance so sessions
        # don't always start at exactly 7:00 AM. End hour is rigid (safety).
        self._tod_start_jitter_minutes = random.randint(-30, 30)

    # ── Pre-session checks ──────────────────────────────────────────

    def can_start_session(self) -> tuple[bool, str]:
        """Check all preconditions before starting a session.
        Returns (ok, reason).
        """
        # Time-of-day window
        if not self._in_time_window():
            return False, f"Outside time-of-day window"

        # Daily session cap
        sessions_today = cooldown.get_sessions_today()
        if sessions_today >= MAX_SESSIONS_PER_DAY:
            return False, f"Daily session cap reached ({sessions_today}/{MAX_SESSIONS_PER_DAY})"

        # 24h profile open cap
        opens_24h = cooldown.get_profile_opens_24h()
        if opens_24h >= MAX_PROFILE_OPENS_PER_24H:
            return False, f"24h profile open cap reached ({opens_24h}/{MAX_PROFILE_OPENS_PER_24H})"

        return True, "ok"

    # ── Session lifecycle ───────────────────────────────────────────

    def start_session(self):
        """Mark session start. Call can_start_session() first."""
        self._session_start = time.time()
        self._profile_opens_session = 0
        self._active = True
        self._shutdown_reason = None

    def end_session(self) -> dict:
        """Mark session end. Returns summary dict."""
        self._active = False
        return {
            "profile_opens_session": self._profile_opens_session,
            "profile_opens_24h": cooldown.get_profile_opens_24h(),
            "duration_seconds": int(time.time() - self._session_start),
            "shutdown_reason": self._shutdown_reason or "normal",
        }

    # ── Profile open hook ───────────────────────────────────────────

    def wrap_browser(self, browser):
        """Monkeypatch browser.open_profile and open_profile_by_url to count opens.

        The patched methods check limits BEFORE delegating to the real impl.
        This is the single source of truth for profile open counting.
        """
        self._original_open_profile = browser.open_profile
        self._original_open_profile_by_url = browser.open_profile_by_url

        governor = self

        async def counted_open_profile(candidate_name: str):
            governor._check_limits_or_raise()
            await governor._original_open_profile(candidate_name)
            governor._record_open()

        async def counted_open_profile_by_url(profile_url: str):
            governor._check_limits_or_raise()
            await governor._original_open_profile_by_url(profile_url)
            governor._record_open()

        browser.open_profile = counted_open_profile
        browser.open_profile_by_url = counted_open_profile_by_url

    def unwrap_browser(self, browser):
        """Restore original browser methods."""
        if self._original_open_profile:
            browser.open_profile = self._original_open_profile
        if self._original_open_profile_by_url:
            browser.open_profile_by_url = self._original_open_profile_by_url

    def _record_open(self):
        self._profile_opens_session += 1
        cooldown.record_profile_open()

    # ── Limit checks ───────────────────────────────────────────────

    def _check_limits_or_raise(self):
        """Check all limits. Raises GovernorLimitReached if any exceeded."""
        if not self._active:
            return

        # Session duration
        elapsed = time.time() - self._session_start
        if elapsed >= MAX_SESSION_DURATION_SECONDS:
            self._shutdown_reason = f"session_duration ({elapsed/3600:.1f}h)"
            raise GovernorLimitReached(self._shutdown_reason)

        # Session profile opens
        if self._profile_opens_session >= MAX_PROFILE_OPENS_PER_SESSION:
            self._shutdown_reason = f"session_profile_cap ({self._profile_opens_session}/{MAX_PROFILE_OPENS_PER_SESSION})"
            raise GovernorLimitReached(self._shutdown_reason)

        # 24h profile opens
        opens_24h = cooldown.get_profile_opens_24h()
        if opens_24h >= MAX_PROFILE_OPENS_PER_24H:
            self._shutdown_reason = f"24h_profile_cap ({opens_24h}/{MAX_PROFILE_OPENS_PER_24H})"
            raise GovernorLimitReached(self._shutdown_reason)

        # Time-of-day window
        if not self._in_time_window():
            self._shutdown_reason = "time_of_day_window_closed"
            raise GovernorLimitReached(self._shutdown_reason)

    def check_limits(self) -> Optional[str]:
        """Non-raising limit check. Returns reason string or None."""
        try:
            self._check_limits_or_raise()
            return None
        except GovernorLimitReached as e:
            return e.reason

    def _in_time_window(self) -> bool:
        """Check if current time is within the operating window.

        Start hour is jittered ±30 min per instance to avoid exact-hour patterns.
        End hour is rigid at 11 PM (hard safety ceiling).
        """
        now = datetime.datetime.now()
        start = now.replace(
            hour=TIME_OF_DAY_START_HOUR, minute=0, second=0, microsecond=0
        ) + datetime.timedelta(minutes=self._tod_start_jitter_minutes)
        end = now.replace(
            hour=TIME_OF_DAY_END_HOUR, minute=0, second=0, microsecond=0
        )
        return start <= now < end

    # ── Status ──────────────────────────────────────────────────────

    @property
    def profile_opens_session(self) -> int:
        return self._profile_opens_session

    @property
    def elapsed_seconds(self) -> float:
        if self._session_start == 0:
            return 0
        return time.time() - self._session_start

    @property
    def shutdown_reason(self) -> Optional[str]:
        return self._shutdown_reason

    def status_line(self) -> str:
        """One-line status for console output."""
        elapsed = self.elapsed_seconds
        h, m, s = int(elapsed // 3600), int((elapsed % 3600) // 60), int(elapsed % 60)
        opens_24h = cooldown.get_profile_opens_24h()
        max_h = MAX_SESSION_DURATION_SECONDS // 3600
        return (
            f"Profile opens: {self._profile_opens_session}/{MAX_PROFILE_OPENS_PER_SESSION} (session) | "
            f"{opens_24h}/{MAX_PROFILE_OPENS_PER_24H} (24h) | "
            f"Time: {h}:{m:02d}:{s:02d}/{max_h}:00:00"
        )
