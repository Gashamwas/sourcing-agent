#!/usr/bin/env python3
"""Session Orchestrator — parent wrapper for the sourcing pipeline.

This is the single entry point. It manages:
  - Session Governor (hard safety limits)
  - Sourcing Agent (existing pipeline, with pause/resume for decoy interleaving)
  - Decoy Agent (passive LinkedIn browsing, runs during and between sessions)
  - Multi-Session Cycling (sprint → dormant → sprint)

Usage:
    python session_orchestrator.py --brief config/brief-X.json --search-config config/search.json
    python session_orchestrator.py --brief config/brief-X.json --search-config config/search.json --single-session
    python session_orchestrator.py --decoy-only
    python session_orchestrator.py --status
"""

import argparse
import asyncio
import json
import math
import os
import random
import signal
import sys
import time
from pathlib import Path

os.environ.setdefault("AGENT_KEY_PREFIX", "LINKEDIN")
from shared import config
from shared import cooldown
from shared.console_tee import enable_console_tee
from shared.governor import (
    SessionGovernor,
    SessionExpired,
    GovernorLimitReached,
    MAX_PROFILE_OPENS_PER_24H,
    MAX_SESSIONS_PER_DAY,
)
from decoy.agent import DecoyAgent
from decoy.scheduler import BurstScheduler
from shared.human_timing import human_delay


# ──────────────────────────────────────────────────────────────────────
# Session duration sampling
# ──────────────────────────────────────────────────────────────────────

def _sample_session_duration() -> float:
    """Log-normal session duration: median ~4h, range 3.5-5h (in seconds)."""
    mu = math.log(14400)  # 4 hours in seconds
    sigma = 0.12
    raw = math.exp(mu + sigma * random.gauss(0, 1))
    return max(12600, min(18000, raw))  # Clamp 3.5h - 5h


def _sample_dormant_duration() -> float:
    """Log-normal dormant period: median ~110 min, range 75-180 min (in seconds)."""
    mu = math.log(6600)  # 110 min in seconds
    sigma = 0.3
    raw = math.exp(mu + sigma * random.gauss(0, 1))
    return max(4500, min(10800, raw))  # Clamp 75 min - 180 min


# ──────────────────────────────────────────────────────────────────────
# Console output
# ──────────────────────────────────────────────────────────────────────

def _print_governor(msg: str):
    print(f"[governor] {msg}", flush=True)


def _print_decoy(msg: str):
    print(f"[decoy] {msg}", flush=True)


def _classify_session_exception(exc: BaseException) -> str:
    """Normalize orchestrator-level failures for session accounting."""
    if isinstance(exc, KeyboardInterrupt):
        return "interrupted: KeyboardInterrupt"
    return f"error: {type(exc).__name__}"


def _resume_has_pending_work(output_dir: str | None) -> bool:
    """Return True when progress.json still has queued or in-progress work.

    If the file is missing or unreadable, err on the side of attempting resume.
    """
    progress_dir = Path(output_dir) if output_dir else config.OUTPUT_DIR
    progress_path = progress_dir / "progress.json"
    if not progress_path.exists():
        return True

    try:
        progress = json.loads(progress_path.read_text())
    except Exception:
        return True

    strings = progress.get("strings", [])
    if progress.get("pending_block_string_ids"):
        return True
    if not strings:
        return False

    return any(s.get("status") in {"queued", "in_progress"} for s in strings)


def _parse_restart_strings_arg(raw: str | None) -> list[int]:
    """Parse a comma-separated list of string ids from --restart-strings."""
    if not raw:
        return []

    string_ids: list[int] = []
    for chunk in raw.split(","):
        part = chunk.strip()
        if not part:
            continue
        try:
            string_ids.append(int(part))
        except ValueError as exc:
            raise ValueError(f"Invalid string id '{part}' in --restart-strings") from exc
    return string_ids


# ──────────────────────────────────────────────────────────────────────
# Sourcing session runner
# ──────────────────────────────────────────────────────────────────────

async def _run_sourcing_session(
    brief_path: str,
    search_config: str | None,
    output_dir: str | None,
    resume: bool,
    input_mode: str,
    governor: SessionGovernor,
    decoy: DecoyAgent,
    session_duration: float,
    restart_string_id: int | None = None,
    restart_string_ids: list[int] | None = None,
) -> dict:
    """Run one sourcing session with governor limits and decoy interleaving.

    Returns the pipeline's stats dict.
    """
    from linkedin.orchestrator import Pipeline

    pipeline = Pipeline(
        brief_path=brief_path,
        search_config_path=search_config,
        output_dir=output_dir,
        input_mode=input_mode,
    )

    await pipeline.browser.connect()
    governor.wrap_browser(pipeline.browser)

    # Set up pause/resume events for decoy interleaving
    pause_requested = asyncio.Event()
    resume_event = asyncio.Event()
    resume_event.set()  # Start unpaused

    # Inject events into pipeline for cooperative yielding
    pipeline._pause_requested = pause_requested
    pipeline._resume_event = resume_event

    # Interleave scheduler
    interleave_scheduler = BurstScheduler(mode="interleave")
    session_start = time.time()
    last_status_print = session_start
    stop_interleave = asyncio.Event()

    async def _interleave_loop():
        """Periodically request pause, run decoy burst, then resume sourcing."""
        while not stop_interleave.is_set():
            interval = interleave_scheduler.next_interval()
            # Wait in small chunks
            waited = 0.0
            while waited < interval and not stop_interleave.is_set():
                chunk = min(5.0, interval - waited)
                await asyncio.sleep(chunk)
                waited += chunk

            if stop_interleave.is_set():
                break

            # Request sourcing to pause
            resume_event.clear()
            pause_requested.set()

            # Wait for pipeline to actually pause (it will clear pause_requested
            # when it reaches a safe checkpoint)
            for _ in range(60):  # Max 60s wait
                if not pause_requested.is_set():
                    break
                await asyncio.sleep(1)
            else:
                # Pipeline didn't pause in time — skip this burst.
                # Clear pause_requested to prevent stale flag from causing
                # an unexpected pause next time pipeline hits the checkpoint.
                pause_requested.clear()
                resume_event.set()
                continue

            # Run decoy burst
            _print_decoy("Interleave burst starting...")
            results = await decoy.execute_burst()
            summary = ", ".join(f"{r['type']} ({r.get('duration', 0)}s)" for r in results)
            _print_decoy(f"Activity burst: {summary}")

            # Resume sourcing
            pause_requested.clear()
            resume_event.set()

    # Start interleave loop in background
    interleave_task = asyncio.create_task(_interleave_loop())

    # Status printer
    async def _status_loop():
        nonlocal last_status_print
        while not stop_interleave.is_set():
            await asyncio.sleep(30)
            now = time.time()
            if now - last_status_print >= 300:  # Every 5 minutes
                _print_governor(governor.status_line())
                last_status_print = now

    status_task = asyncio.create_task(_status_loop())

    # Cooperative session duration cap — sets a flag that the pipeline checks
    # at its next safe checkpoint, instead of hard-cancelling mid-operation.
    session_expired = asyncio.Event()
    pipeline._session_expired = session_expired

    async def _session_timer():
        """Sleep for session duration, then signal expiry."""
        waited = 0.0
        while waited < session_duration and not stop_interleave.is_set():
            chunk = min(5.0, session_duration - waited)
            await asyncio.sleep(chunk)
            waited += chunk
        session_expired.set()

    timer_task = asyncio.create_task(_session_timer())

    # Run the sourcing pipeline
    shutdown_reason = None
    try:
        if search_config:
            await pipeline.run()
        else:
            await pipeline.run_full(
                resume=resume,
                restart_string_id=restart_string_id,
                restart_string_ids=restart_string_ids,
            )
        shutdown_reason = "pipeline_complete"

    except SessionExpired:
        shutdown_reason = "session_duration_cap"
        _print_governor(f"Session duration cap reached ({session_duration/3600:.1f}h)")

    except GovernorLimitReached as e:
        shutdown_reason = e.reason
        _print_governor(f"Governor limit: {e.reason}")

    except Exception as e:
        shutdown_reason = f"error: {e}"
        _print_governor(f"Session error: {e}")

    finally:
        # Stop background tasks
        stop_interleave.set()
        session_expired.set()
        for task in (interleave_task, status_task, timer_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Ensure pipeline saves progress
        if pipeline._progress:
            pipeline._progress.save(str(pipeline.progress_path))

        # Unwrap governor hooks and disconnect
        governor.unwrap_browser(pipeline.browser)

    return {
        "stats": pipeline.stats,
        "shutdown_reason": shutdown_reason or governor.shutdown_reason or "unknown",
    }


# ──────────────────────────────────────────────────────────────────────
# Multi-session cycle
# ──────────────────────────────────────────────────────────────────────

async def run_day_cycle(
    brief_path: str,
    search_config: str | None,
    output_dir: str | None,
    input_mode: str = "concurrent",
    single_session: bool = False,
    resume: bool = False,
    restart_string_id: int | None = None,
    restart_string_ids: list[int] | None = None,
):
    """Run a full day cycle: sourcing sessions interleaved with dormant periods."""

    governor = SessionGovernor()
    stop_event = asyncio.Event()

    # Graceful first Ctrl+C, hard second Ctrl+C
    _shutting_down = False

    def _signal_handler(sig, frame):
        nonlocal _shutting_down
        if _shutting_down:
            _print_governor("Force shutdown. Saving progress...")
            raise KeyboardInterrupt
        _shutting_down = True
        _print_governor("Shutdown signal received. Finishing current activity... (Ctrl+C again to force)")
        stop_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    if resume and not _resume_has_pending_work(output_dir):
        _print_governor("No queued sourcing work remains in progress.json. Nothing to resume.")
        return

    # Connect to browser for decoy agent
    from rebrowser_playwright.async_api import async_playwright
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(config.CDP_URL)
    contexts = browser.contexts
    if not contexts:
        _print_governor("No browser contexts found. Is Chrome open?")
        return

    # Use the first context (shared with sourcing agent)
    decoy = DecoyAgent(contexts[0])

    session_num = 0
    # resume is passed in from CLI; subsequent sessions always resume

    while not stop_event.is_set():
        if resume and not _resume_has_pending_work(output_dir):
            _print_governor("No queued sourcing work remains in progress.json. Stopping day cycle.")
            break

        # Pre-session checks
        can_start, reason = governor.can_start_session(session_type="linkedin_sourcing")
        if not can_start:
            _print_governor(f"Cannot start session: {reason}")
            # Session cap means we're done for the day.
            if "session cap" in reason.lower():
                break
            # If 24h cap, run decoy until budget refreshes or window closes
            _print_governor("Running decoy-only until conditions change...")
            await decoy.run_dormant_loop(stop_event, 3600)  # Check again in 1h
            continue

        session_num += 1
        session_id = cooldown.record_session_start(session_type="linkedin_sourcing")
        session_slot = cooldown.get_sessions_today(session_type="linkedin_sourcing")
        opens_remaining = MAX_PROFILE_OPENS_PER_24H - cooldown.get_profile_opens_24h()
        session_duration = _sample_session_duration()

        _print_governor(
            f"Session {session_slot}/{MAX_SESSIONS_PER_DAY} starting — "
            f"{opens_remaining} profile opens remaining in 24h budget"
        )

        governor.start_session()

        result = {"shutdown_reason": "unknown", "stats": {}}
        try:
            result = await _run_sourcing_session(
                brief_path=brief_path,
                search_config=search_config,
                output_dir=output_dir,
                resume=resume,
                input_mode=input_mode,
                governor=governor,
                decoy=decoy,
                session_duration=session_duration,
                restart_string_id=restart_string_id,
                restart_string_ids=restart_string_ids,
            )
        except KeyboardInterrupt as e:
            result = {"shutdown_reason": _classify_session_exception(e), "stats": {}}
        except Exception as e:
            result = {"shutdown_reason": _classify_session_exception(e), "stats": {}}
        finally:
            summary = governor.end_session()
            cooldown.record_session_end(
                session_num=session_id,
                profile_opens=summary["profile_opens_session"],
                reason=result.get("shutdown_reason", "unknown"),
                stats=result.get("stats", {}),
            )

            _print_governor(
                f"Session {session_slot}/{MAX_SESSIONS_PER_DAY} ended — "
                f"{summary['profile_opens_session']} profile opens | "
                f"Reason: {result.get('shutdown_reason', 'unknown')}"
            )

        # After first session, subsequent sessions should resume (without restart)
        resume = True
        restart_string_id = None
        restart_string_ids = None

        if single_session or stop_event.is_set():
            break

        if not _resume_has_pending_work(output_dir):
            _print_governor("No queued sourcing work remains in progress.json. Day cycle complete.")
            break

        # Check if we can do another session
        can_continue, reason = governor.can_start_session(session_type="linkedin_sourcing")
        if not can_continue:
            _print_governor(f"No more sessions available: {reason}")
            break

        # Dormant period with decoy
        dormant_duration = _sample_dormant_duration()
        dormant_min = dormant_duration / 60
        next_time = time.strftime("%I:%M %p", time.localtime(time.time() + dormant_duration))
        _print_governor(f"Dormant period: ~{dormant_min:.0f} minutes (next session ~{next_time})")

        await decoy.run_dormant_loop(stop_event, dormant_duration)

    # Cleanup
    await decoy.close()
    await pw.stop()
    _print_governor("Day cycle complete.")


# ──────────────────────────────────────────────────────────────────────
# Decoy-only mode
# ──────────────────────────────────────────────────────────────────────

async def run_decoy_only():
    """Run only the decoy agent — no sourcing. Useful for cool-down days."""
    _print_governor("Decoy-only mode — passive browsing only, no sourcing.")

    from rebrowser_playwright.async_api import async_playwright
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(config.CDP_URL)
    contexts = browser.contexts
    if not contexts:
        _print_governor("No browser contexts found. Is Chrome open?")
        return

    decoy = DecoyAgent(contexts[0])
    stop_event = asyncio.Event()

    def _signal_handler(sig, frame):
        _print_decoy("Shutdown signal received. Finishing current burst...")
        stop_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Run until stopped.
    while not stop_event.is_set():
        # Run in 1 hour chunks so shutdown signals are handled promptly.
        await decoy.run_dormant_loop(stop_event, 3600)

    await decoy.close()
    await pw.stop()
    _print_governor("Decoy-only session complete.")


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Session Orchestrator — sourcing pipeline with safety governor"
    )
    parser.add_argument("--brief", help="Path to sourcing brief JSON")
    parser.add_argument("--search-config", default=None, help="Path to search config JSON")
    parser.add_argument("--output-dir", default=None, help="Output directory")
    parser.add_argument("--single-session", action="store_true", help="Run one session only (no cycling)")
    parser.add_argument("--decoy-only", action="store_true", help="Run decoy agent only (no sourcing)")
    parser.add_argument("--status", action="store_true", help="Print current 24h stats")
    parser.add_argument("--resume", action="store_true", help="Resume from existing progress")
    parser.add_argument("--restart-string", type=int, default=None, help="Reset a specific string to page 1 (use with --resume)")
    parser.add_argument(
        "--restart-strings",
        default=None,
        help="Reset multiple strings to page 1 before resuming, e.g. 4,11,12,16,27",
    )
    parser.add_argument(
        "--input-mode",
        choices=["concurrent", "away"],
        default="concurrent",
        help="Browser input mode for sourcing sessions",
    )

    args = parser.parse_args()

    if args.status:
        cooldown.print_status()
        return

    enable_console_tee(Path(args.output_dir) if args.output_dir else config.OUTPUT_DIR)

    if args.decoy_only:
        asyncio.run(run_decoy_only())
        return

    if not args.brief:
        parser.error("--brief is required (unless using --decoy-only or --status)")

    if not Path(args.brief).exists():
        print(f"Error: Brief file not found: {args.brief}")
        sys.exit(1)

    try:
        restart_string_ids = _parse_restart_strings_arg(args.restart_strings)
    except ValueError as exc:
        parser.error(str(exc))

    if args.restart_string is not None:
        restart_string_ids.append(args.restart_string)

    # Any restart request implies --resume
    if (args.restart_string is not None or restart_string_ids) and not args.resume:
        args.resume = True

    asyncio.run(run_day_cycle(
        brief_path=args.brief,
        search_config=args.search_config,
        output_dir=args.output_dir,
        input_mode=args.input_mode,
        single_session=args.single_session,
        resume=args.resume,
        restart_string_id=args.restart_string,
        restart_string_ids=restart_string_ids,
    ))


if __name__ == "__main__":
    main()
