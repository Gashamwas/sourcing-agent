"""Main pipeline orchestration. Connects extraction -> facial judgment -> full profile -> save.

Usage:
    pipeline = Pipeline(brief_path="config/brief-brazil-real.json")
    await pipeline.run()
    await pipeline.run_single_page()  # test mode
    await pipeline.run_full()  # autonomous search evolution
"""

from __future__ import annotations
import asyncio
import json
import random
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from shared.human_timing import human_delay, human_delay_correlated

from shared.schemas import (
    CandidateSnippet, CandidateProfileSummary, OpusDecision,
    SearchString, Progress, KitString, BlockReport, AdaptationResponse,
    ExecutionPlan, GlanceResult,
)
from linkedin.acquisition import LinkedInAcquisitionService
from linkedin.browser import LinkedInBrowser
from linkedin.side_effects import LinkedInSideEffectsService
from linkedin.work_units import LinkedInWorkUnitService
from shared.extractors import (
    extract_snippet_from_card_innertext,
    extract_profile_from_dom,
)
from shared.failures import judgment_failure_decision
from shared.judger import facial_judge, full_judge, init_judger, is_failure_decision
from shared.runtime_state import LinkedInRuntimeStateBridge, RuntimeStateLock, RuntimeStateStore
from shared.safety import LinkedInRecoveryService, RunSafetyCoordinator, RunStopReason
from shared.storage import append_jsonl, read_jsonl, read_jsonl_set, log_event, write_json, read_json
from shared.brief_loader import load_brief, Brief
from shared.bias_controls import BiasMonitor, DecisionRecord
from shared.search_memory import (
    build_search_memory_summary,
    extract_dominant_anchors,
    infer_domain_lane,
    normalize_family_key,
    normalize_novelty_bucket,
    update_search_memory,
)
from shared.run_report_schema import (
    RunDebriefAnalysis,
    StructuredRunReport,
    render_run_report_markdown,
)
from shared import config
from shared.governor import GovernorLimitReached, SessionExpired

import re as _re

# --- Glance assessment: title normalization ---

_SENIORITY_PREFIXES = _re.compile(
    r'^(senior|sr\.?|lead|principal|staff|junior|jr\.?|associate|chief|head of|director of|vp of)\s+',
    _re.IGNORECASE,
)
_TRAILING_LEVELS = _re.compile(r'\s+(i{1,4}|iv|[1-6])$', _re.IGNORECASE)

_TITLE_SYNONYMS: dict[str, str] = {
    "software developer": "software engineer",
    "swe": "software engineer",
    "ml engineer": "machine learning engineer",
    "ai engineer": "machine learning engineer",
    "dev ops": "devops engineer",
    "data science": "data scientist",
    "programme manager": "program manager",
}


def _normalize_title_family(title: str) -> str:
    """Collapse a job title to a canonical family for clustering."""
    t = title.strip().lower()
    t = _SENIORITY_PREFIXES.sub('', t)
    t = _TRAILING_LEVELS.sub('', t)
    t = t.strip()
    for pattern, canonical in _TITLE_SYNONYMS.items():
        if t == pattern:
            t = canonical
            break
    return t


_PARENS_SUFFIX = _re.compile(r"\s*\([^)]*\)")
_NON_ALNUM = _re.compile(r"[^a-z0-9]+")
_BROWSER_DISCONNECT_PATTERNS = (
    "target crashed",
    "target closed",
    "connection closed",
    "session closed",
    "broken pipe",
    "browser has been closed",
    "page closed",
    "context closed",
    "page.createisolatedworld",
    "page.addscripttoevaluateonnewdocument",
    "cannot get world",
)


def _normalize_candidate_name_key(name: str) -> str:
    """Collapse minor punctuation/parenthetical variants when matching saved profiles."""
    t = _PARENS_SUFFIX.sub("", (name or "").lower())
    t = t.replace(".", " ")
    t = _NON_ALNUM.sub(" ", t)
    return " ".join(t.split())


def _is_browser_disconnect_error(error: BaseException | str) -> bool:
    """Detect browser/CDP failures that should trigger reconnect logic."""
    text = str(error).lower()
    return any(pattern in text for pattern in _BROWSER_DISCONNECT_PATTERNS)


class Pipeline:
    """Orchestrates the multi-model sourcing pipeline."""

    def __init__(
        self,
        brief_path: str,
        search_config_path: str | None = None,
        output_dir: Optional[str] = None,
        test_mode: bool = False,
        input_mode: str = "concurrent",
    ):
        self.brief_obj = load_brief(brief_path)
        self.search_config = (
            read_json(search_config_path)
            if search_config_path and Path(search_config_path).exists()
            else {"strings": []}
        )
        self.output_dir = Path(output_dir) if output_dir else config.OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.test_mode = test_mode
        self.input_mode = input_mode

        # Initialize judger with the Brief dataclass
        init_judger(self.brief_obj)

        # Output file paths
        self.snippets_path = self.output_dir / "snippets.jsonl"
        self.facial_path = self.output_dir / "facial_judgments.jsonl"
        self.profiles_path = self.output_dir / "profile_summaries.jsonl"
        self.final_path = self.output_dir / "final_judgments.jsonl"
        self.progress_path = self.output_dir / "progress.json"
        self.log_path = self.output_dir / "run_log.jsonl"
        self.runtime_db_path = self.output_dir / "runtime_state.sqlite3"

        # Browser
        self.browser = LinkedInBrowser(input_mode=input_mode)

        # Brief identifier for cross-session file scoping
        self._brief_id = self.brief_obj.linkedin_project_id or Path(brief_path).stem

        # Cross-session candidate history (brief-scoped, never archived)
        self.history_path = self.output_dir / f"candidate_history-{self._brief_id}.jsonl"

        # Cross-session noise discoveries (brief-scoped, never archived)
        self.noise_path = self.output_dir / f"noise_discoveries-{self._brief_id}.jsonl"
        self.search_memory_path = self.output_dir / f"search_memory-{self._brief_id}.json"
        self._search_memory: dict = {}

        # Dedup cache (loaded once, updated in memory — avoids O(n^2) file reads)
        self._seen_urls: set[str] = set()       # terminal outcomes only
        self._in_flight_urls: set[str] = set()  # currently being evaluated, NOT persisted

        # Prior session outcomes — URL → most recent outcome (for skip-on-prior-reject)
        self._prior_outcomes: dict[str, str] = {}

        # Save dedup — tracks profile URLs already saved in this session
        self._saved_urls: set[str] = set()

        # Stats
        self.stats = {
            "snippets_extracted": 0,
            "facial_yes": 0,
            "facial_no": 0,
            "saved": 0,
            "save_attempts": 0,
            "rejected": 0,
        }

        # Progress ref for Ctrl+C handler
        self._progress: Optional[Progress] = None
        self._runtime_state = RuntimeStateStore(self.runtime_db_path)
        self._runtime_lock = RuntimeStateLock(self.output_dir)
        self._runtime_run_id: int | None = None
        self._runtime_bridge = LinkedInRuntimeStateBridge(
            store=self._runtime_state,
            output_dir=self.output_dir,
            brief_id=self._brief_id,
            brief_name=self.brief_obj.id,
        )
        self._safety = RunSafetyCoordinator(
            store=self._runtime_state,
            output_dir=self.output_dir,
            source="linkedin",
            brief_id=self._brief_id,
        )
        self._recovery_service = LinkedInRecoveryService(
            coordinator=self._safety,
            browser=self.browser,
        )
        self._work_unit_service = LinkedInWorkUnitService(self)
        self._acquisition_service = LinkedInAcquisitionService(self)
        self._side_effects_service = LinkedInSideEffectsService(self)
        self._governor = None

        # Kit strings (populated by run_full)
        self._kit_strings: list[KitString] = []
        self._execution_plan: Optional[ExecutionPlan] = None

        # Bias monitor (V2 briefs only — uses brief's BiasControls + FacialCalibration)
        self._bias_monitor: Optional[BiasMonitor] = None
        if self.brief_obj.has_v2_schema:
            # Brief-scoped bias checkpoint (survives across sessions)
            self.bias_checkpoint_path = self.output_dir / f"bias_monitor-{self._brief_id}.json"
            if self.bias_checkpoint_path.exists():
                self._bias_monitor = BiasMonitor.from_brief(self.brief_obj._new_brief)
                self._bias_monitor.load_checkpoint(str(self.bias_checkpoint_path))
                print(f"  [bias] Loaded bias monitor from prior session ({len(self._bias_monitor._decisions)} decisions)")
            else:
                self._bias_monitor = BiasMonitor.from_brief(self.brief_obj._new_brief)
        else:
            self.bias_checkpoint_path = self.output_dir / f"bias_monitor-{self._brief_id}.json"

        # Cadence pause — anti-detection idle breaks
        self._last_pause_time: float = time.time()

        # URL snapshot — last known good URL for recovery fallback
        self._last_good_url: str = ""

    # ------------------------------------------------------------------
    # Cross-session history
    # ------------------------------------------------------------------

    def _load_candidate_history(self) -> None:
        """Load cross-session candidate history into dedup set and prior outcomes dict.

        Called after per-session dedup loading in all three init paths.
        Additive — merges history URLs into _seen_urls alongside current-session files.
        """
        if self._runtime_bridge and self._runtime_bridge.has_runtime_state():
            blocked_urls, prior_outcomes, saved_urls = self._runtime_bridge.load_history()
            self._seen_urls = set(blocked_urls)
            self._prior_outcomes = dict(prior_outcomes)
            self._saved_urls.update(saved_urls)
            saves = sum(1 for outcome in self._prior_outcomes.values() if outcome in ("SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE", "SIGNAL_SAVE"))
            rejects = sum(1 for outcome in self._prior_outcomes.values() if outcome == "REJECT")
            print(f"  [dedup] Runtime history: {len(self._prior_outcomes)} candidates ({saves} saves, {rejects} rejects)")
            return
        if not self.history_path.exists():
            return
        for entry in read_jsonl(self.history_path):
            url = entry.get("profile_url", "")
            if url:
                self._seen_urls.add(url)
                self._prior_outcomes[url] = entry.get("outcome", "")
        saves = sum(1 for o in self._prior_outcomes.values() if o in ("SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE"))
        rejects = sum(1 for o in self._prior_outcomes.values() if o == "REJECT")
        print(f"  [dedup] Cross-session history: {len(self._prior_outcomes)} candidates ({saves} saves, {rejects} rejects)")

    def _mark_terminal(self, url: str):
        """Promote URL from in-flight to permanent dedup."""
        self._in_flight_urls.discard(url)
        if url:
            self._seen_urls.add(url)

    def _load_search_memory(self) -> None:
        """Load brief-scoped search family memory if present."""
        self._ensure_services()
        self._search_memory = self._work_unit_service.load_search_memory()

    def _save_search_memory(self) -> None:
        """Persist brief-scoped search family memory."""
        self._ensure_services()
        self._search_memory = self._work_unit_service.save_search_memory()

    def _update_search_memory_from_block(self, block_strings: list[SearchString]) -> None:
        """Update family memory with the completed block's observed performance."""
        self._ensure_services()
        self._search_memory = self._work_unit_service.update_search_memory_from_block(block_strings)

    def _hydrate_search_string_metadata(self, search_string: SearchString) -> None:
        """Backfill family metadata for older progress files or unlabeled strings."""
        if not search_string.family_key:
            search_string.family_key = normalize_family_key(
                None,
                search_string.boolean,
                search_string.name,
            )
        if not search_string.novelty_bucket:
            search_string.novelty_bucket = normalize_novelty_bucket(
                None,
                search_string.boolean,
                search_string.name,
            )
        if not search_string.domain_lane:
            search_string.domain_lane = infer_domain_lane(
                None,
                search_string.boolean,
                search_string.name,
            )

    def _checkpoint_progress(
        self,
        progress: Progress | None,
        search_string: SearchString | None = None,
        page_num: int | None = None,
    ) -> None:
        """Persist current run state without waiting for a full page to finish."""
        self._ensure_services()
        self._work_unit_service.checkpoint_progress(
            progress,
            search_string=search_string,
            page_num=page_num,
        )

    def _ensure_runtime_state(self) -> None:
        output_dir = Path(self.output_dir)
        if not hasattr(self, "runtime_db_path") or self.runtime_db_path is None:
            self.runtime_db_path = output_dir / "runtime_state.sqlite3"
        if not hasattr(self, "_runtime_state") or self._runtime_state is None:
            self._runtime_state = RuntimeStateStore(self.runtime_db_path)
        if not hasattr(self, "_runtime_lock") or self._runtime_lock is None:
            self._runtime_lock = RuntimeStateLock(output_dir)
        if not hasattr(self, "_runtime_bridge") or self._runtime_bridge is None:
            self._runtime_bridge = LinkedInRuntimeStateBridge(
                store=self._runtime_state,
                output_dir=output_dir,
                brief_id=self._brief_id,
                brief_name=self.brief_obj.id,
            )
        if not hasattr(self, "_runtime_run_id"):
            self._runtime_run_id = None
        if not hasattr(self, "_safety") or self._safety is None:
            self._safety = RunSafetyCoordinator(
                store=self._runtime_state,
                output_dir=output_dir,
                source="linkedin",
                brief_id=self._brief_id,
            )
        if not hasattr(self, "_recovery_service") or self._recovery_service is None:
            self._recovery_service = LinkedInRecoveryService(
                coordinator=self._safety,
                browser=self.browser,
            )
        self._ensure_services()

    def _record_safety_event(self, event_type: str, payload: dict) -> None:
        if self._runtime_run_id:
            self._runtime_state.record_event(
                run_id=self._runtime_run_id,
                event_type=event_type,
                payload=payload,
            )

    def _ensure_services(self) -> None:
        if not hasattr(self, "_work_unit_service") or self._work_unit_service is None:
            self._work_unit_service = LinkedInWorkUnitService(self)
        if not hasattr(self, "_acquisition_service") or self._acquisition_service is None:
            self._acquisition_service = LinkedInAcquisitionService(self)
        if not hasattr(self, "_side_effects_service") or self._side_effects_service is None:
            self._side_effects_service = LinkedInSideEffectsService(self)

    def _record_runtime_snippet(self, search_string: SearchString, snippet: CandidateSnippet) -> None:
        if self._runtime_bridge and self._runtime_run_id:
            self._runtime_bridge.record_snippet_extracted(
                run_id=self._runtime_run_id,
                search_string=search_string,
                snippet=snippet,
            )

    def _start_runtime_stage_attempt(
        self,
        *,
        search_string: SearchString,
        snippet: CandidateSnippet,
        stage: str,
        payload: dict | None = None,
    ) -> int | None:
        if not self._runtime_bridge or not self._runtime_run_id:
            return None
        return self._runtime_bridge.start_stage_attempt(
            run_id=self._runtime_run_id,
            search_string=search_string,
            snippet=snippet,
            stage=stage,
            payload=payload,
        )

    def _finish_runtime_stage_success(
        self,
        *,
        attempt_id: int | None,
        stage: str,
        snippet: CandidateSnippet,
        decision: OpusDecision,
        profile_summary: CandidateProfileSummary | None = None,
    ) -> None:
        if self._runtime_bridge and self._runtime_run_id:
            self._runtime_bridge.finish_stage_success(
                run_id=self._runtime_run_id,
                attempt_id=attempt_id,
                stage=stage,
                snippet=snippet,
                decision=decision,
                profile_summary=profile_summary,
            )

    def _finish_runtime_stage_failure(
        self,
        *,
        attempt_id: int | None,
        snippet: CandidateSnippet,
        error: Exception,
        payload: dict | None = None,
    ) -> None:
        if self._runtime_bridge and self._runtime_run_id:
            self._runtime_bridge.finish_stage_failure(
                run_id=self._runtime_run_id,
                attempt_id=attempt_id,
                snippet=snippet,
                error=error,
                payload=payload,
            )

    def _finish_runtime_failure_decision(
        self,
        *,
        attempt_id: int | None,
        snippet: CandidateSnippet,
        decision: OpusDecision,
        payload: dict | None = None,
    ) -> None:
        if self._runtime_bridge and self._runtime_run_id:
            self._runtime_bridge.finish_failure_decision(
                run_id=self._runtime_run_id,
                attempt_id=attempt_id,
                snippet=snippet,
                decision=decision,
                payload=payload,
            )

    def _set_pending_block_adaptation(
        self,
        progress: Progress | None,
        block_name: str,
        block_strings: list[SearchString],
        *,
        ready: bool,
    ) -> None:
        """Persist the current block context across resume boundaries."""
        self._ensure_services()
        self._work_unit_service.set_pending_block_adaptation(
            progress,
            block_name,
            block_strings,
            ready=ready,
        )

    def _clear_pending_block_adaptation(self, progress: Progress | None) -> None:
        """Clear any persisted block-adaptation checkpoint."""
        self._ensure_services()
        self._work_unit_service.clear_pending_block_adaptation(progress)

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run the pipeline across all search strings from search_config."""
        print("=" * 60)
        print("LinkedIn Recruiter Multi-Model Sourcing Pipeline")
        print(f"Brief: {self.brief_obj.id}")
        print("=" * 60)

        self._ensure_runtime_state()
        lock_acquired = False
        run_status = "completed"
        stop_reason = RunStopReason.NORMAL
        try:
            self._runtime_lock.acquire()
            lock_acquired = True
        except RuntimeError as exc:
            stop_reason = RunStopReason.LOCK_CONFLICT
            self._runtime_state.record_event(
                event_type="runtime_lock_conflict",
                payload={"error": str(exc), "output_dir": str(self.output_dir)},
            )
            raise

        await self.browser.connect()
        log_event(self.log_path, "pipeline_start", mode="full")

        # Load dedup cache from cross-session history only
        self._seen_urls = set()
        self._in_flight_urls = set()
        self._prior_outcomes = {}
        self._load_candidate_history()
        self._load_search_memory()

        progress = self._load_or_create_progress()
        self._progress = progress

        # Ctrl+C handler — only install if not running under session_orchestrator
        def _sigint_handler(sig, frame):
            print("\n\n  [!] Interrupted. Saving progress...")
            if self._progress:
                self._checkpoint_progress(self._progress)
            raise KeyboardInterrupt

        if not hasattr(self, '_session_expired'):
            signal.signal(signal.SIGINT, _sigint_handler)

        try:
            for search_string in progress.strings:
                if search_string.status == "done":
                    print(f"\n  [skip] String #{search_string.id}: {search_string.name} (already done)")
                    continue

                print(f"\n{'─' * 60}")
                print(f"  String #{search_string.id}: {search_string.name}")
                print(f"{'─' * 60}")

                search_string.status = "in_progress"
                progress.current_string_id = search_string.id

                await self._process_string(search_string, progress)

                search_string.status = "done"
                self._checkpoint_progress(progress, search_string=search_string)
                log_event(self.log_path, "string_complete", string_id=search_string.id, **self.stats)

        except KeyboardInterrupt:
            print("\n\n  [!] Interrupted. Progress saved.")
            run_status = "interrupted"
            stop_reason = RunStopReason.OPERATOR_STOP
        except Exception as e:
            print(f"\n  [ERROR] {e}")
            log_event(self.log_path, "pipeline_error", error=str(e))
            run_status = "error"
            stop_reason = RunStopReason.FATAL_RUNTIME_ERROR
            raise
        finally:
            self._checkpoint_progress(progress)
            await self.browser.disconnect()
            self._print_summary()
            log_event(self.log_path, "pipeline_end", **self.stats)
            if self._runtime_run_id:
                self._safety.finish_run(
                    run_id=self._runtime_run_id,
                    status=run_status,
                    stop_reason=stop_reason,
                )
            if lock_acquired:
                self._runtime_lock.release()

    async def run_single_page(self) -> None:
        """Test mode: process only the current page of results visible in the browser."""
        print("=" * 60)
        print("TEST MODE: Processing current results page only")
        print(f"Brief: {self.brief_obj.id}")
        print("=" * 60)

        await self.browser.connect()
        log_event(self.log_path, "pipeline_start", mode="single_page_test")

        try:
            search_string = SearchString(id=0, name="test", boolean="(test)")
            page_report = _PageReport(string_id=0, string_name="test", page=1, result_count=-1)
            string_stats = {
                "pages": 1,
                "candidates": 0,
                "duplicates": 0,
                "facial_yes": 0,
                "facial_no": 0,
                "saves": 0,
                "rejects": 0,
            }
            all_candidates: list[dict] = []

            await self._review_page_sequentially(
                search_string=search_string,
                page_num=1,
                result_count=-1,
                page_report=page_report,
                all_candidates=all_candidates,
                string_stats=string_stats,
                progress=None,
            )

            page_report.print_report(self.stats)

        except Exception as e:
            print(f"\n  [ERROR] {e}")
            raise
        finally:
            await self.browser.disconnect()
            self._print_summary()

    async def rejudge_from_file(self, snippets_path: str) -> None:
        """Re-run judgments on existing snippet extractions. No browser needed."""
        from shared.storage import read_jsonl

        print("=" * 60)
        print("RE-JUDGE MODE: Processing existing snippets with brief-driven prompts")
        print(f"Brief: {self.brief_obj.id}")
        print("=" * 60)

        snippets_data = read_jsonl(snippets_path)
        print(f"  Loaded {len(snippets_data)} snippets from {snippets_path}")

        rejudge_path = self.output_dir / "rejudged_facial.jsonl"
        stats = {"total": 0, "facial_yes": 0, "facial_no": 0, "errors": 0}

        for i, data in enumerate(snippets_data, 1):
            snippet = CandidateSnippet.from_dict(data)
            stats["total"] += 1

            print(f"\n  [{i}/{len(snippets_data)}] {snippet.name}")
            print(f"    {snippet.current_title} at {snippet.current_company}")

            try:
                decision = facial_judge(snippet, self.brief_obj)
                append_jsonl(rejudge_path, decision.to_dict())

                if decision.decision == "FACIAL_YES":
                    print(f"    [FACIAL_YES] {decision.rationale}")
                    stats["facial_yes"] += 1
                else:
                    print(f"    [FACIAL_NO] {decision.rationale}")
                    stats["facial_no"] += 1
            except Exception as e:
                print(f"    [ERROR] {e}")
                stats["errors"] += 1

        print(f"\n{'=' * 60}")
        print(f"  Re-judge Summary")
        print(f"  Total: {stats['total']}, "
              f"YES: {stats['facial_yes']}, NO: {stats['facial_no']}, Errors: {stats['errors']}")
        print(f"  Results written to: {rejudge_path}")
        print(f"{'=' * 60}")

    async def run_full(
        self,
        resume: bool = False,
        restart_string_id: int | None = None,
        restart_string_ids: list[int] | None = None,
    ) -> None:
        """Autonomous search evolution: extract kit → strategy → execute → adapt."""
        from shared.kit_extractor import extract_kit_strings
        from linkedin.strategy import form_strategy, adapt_after_block

        print("=" * 60)
        print(f"FULL RUN: Autonomous Search Evolution{' (RESUMING)' if resume else ''}")
        print(f"Brief: {self.brief_obj.id}")
        print(f"Kit URL: {self.brief_obj.kit_url}")
        print("=" * 60)

        self._ensure_runtime_state()
        lock_acquired = False
        run_status = "completed"
        stop_reason = RunStopReason.NORMAL
        try:
            self._runtime_lock.acquire()
            lock_acquired = True
        except RuntimeError as exc:
            stop_reason = RunStopReason.LOCK_CONFLICT
            self._runtime_state.record_event(
                event_type="runtime_lock_conflict",
                payload={"error": str(exc), "output_dir": str(self.output_dir)},
            )
            raise

        await self.browser.connect()
        log_event(self.log_path, "pipeline_start", mode="full_run_resume" if resume else "full_run")

        # Navigate to the project search page if we're not already there.
        # Must be on a search page (not a profile page) for the Keywords sidebar.
        current_url = self.browser.page.url
        project_url = self._get_project_url()
        on_search_page = "/discover/" in current_url or "/talent/search" in current_url
        if project_url and not on_search_page:
            print(f"  Navigating to project search page...")
            await self.browser.navigate_to_search(project_url)
        elif not on_search_page:
            print(f"  Navigating to LinkedIn Recruiter search...")
            await self.browser.navigate_to_search("https://www.linkedin.com/talent/search")

        # Capture initial good URL for error recovery
        try:
            self._last_good_url = self.browser.page.url
        except Exception:
            pass

        # Load dedup cache from cross-session history only
        self._seen_urls = set()
        self._in_flight_urls = set()
        self._prior_outcomes = {}
        self._load_candidate_history()
        self._load_search_memory()

        # Ctrl+C handler — only install if not running under session_orchestrator
        def _sigint_handler(sig, frame):
            print("\n\n  [!] Interrupted. Saving progress...")
            if self._progress:
                self._checkpoint_progress(self._progress)
            raise KeyboardInterrupt

        if not hasattr(self, '_session_expired'):
            signal.signal(signal.SIGINT, _sigint_handler)

        try:
            if resume and (
                (self._runtime_bridge and self._runtime_bridge.has_runtime_state())
                or self.progress_path.exists()
            ):
                # --- Resume: skip kit extraction, strategy, queue building ---
                print("\n--- Resuming from runtime_state ---")
                self._runtime_run_id, progress = self._runtime_bridge.start_or_resume_run(resume=True)
                self._progress = progress

                # Preserve persisted queue order. Adaptive strings may be inserted
                # "next in queue", which is not always the same as numeric ID order.

                restart_ids: list[int] = []
                if restart_string_ids:
                    restart_ids.extend(restart_string_ids)
                elif restart_string_id is not None:
                    restart_ids.append(restart_string_id)

                if restart_ids:
                    self._restart_strings(progress, restart_ids)

                # Rebuild dedup set from cross-session history only
                self._seen_urls = set()
                self._in_flight_urls = set()
                self._prior_outcomes = {}
                self._load_candidate_history()
                self._load_search_memory()

                # Load kit strings for adaptation vocabulary
                kit_path = self.output_dir / "kit_strings.json"
                if kit_path.exists():
                    kit_data = read_json(str(kit_path))
                    self._kit_strings = [KitString.from_dict(ks) for ks in kit_data]
                    print(f"  Loaded {len(self._kit_strings)} kit vocabulary strings")

                # Load execution plan for reference
                plan_path = self.output_dir / "execution_plan.json"
                if plan_path.exists():
                    self._execution_plan = ExecutionPlan.from_dict(read_json(str(plan_path)))

                # Load bias monitor checkpoint
                if self._bias_monitor and self.bias_checkpoint_path.exists():
                    self._bias_monitor.load_checkpoint(str(self.bias_checkpoint_path))
                    print(f"  Resumed bias monitor from checkpoint")

                for search_string in progress.strings:
                    self._hydrate_search_string_metadata(search_string)

                done_count = sum(1 for s in progress.strings if s.status == "done")
                total_count = len(progress.strings)
                print(f"  {done_count}/{total_count} strings already complete")
            else:
                # --- Fresh run: archive stale output files ---
                self._archive_stale_outputs()

                # --- Phase 0: Sourcing Preflight (if JD provided without full eval criteria) ---
                if self.brief_obj.needs_preflight():
                    print("\n--- Phase 0: Sourcing Preflight (V2 structured) ---")
                    self._run_preflight_v2()

                # --- Phase 1: Extract kit strings (if kit URL provided) ---
                print("\n--- Phase 1: Kit Extraction ---")
                if not self.brief_obj.kit_url:
                    print("  No kit URL provided — strategy will generate strings from JD context only.")
                    self._kit_strings = []
                else:
                    self._kit_strings = extract_kit_strings(self.brief_obj.kit_url)
                    if not self._kit_strings:
                        print("  [warn] No strings extracted from kit — proceeding with JD context only.")

                # Save extracted kit for reference
                if self._kit_strings:
                    kit_data = [ks.to_dict() for ks in self._kit_strings]
                    write_json(self.output_dir / "kit_strings.json", kit_data)
                    print(f"  Kit strings saved to {self.output_dir / 'kit_strings.json'}")

                # --- Phase 2: Strategy formation ---
                print("\n--- Phase 2: Strategy Formation (Opus) ---")
                prior_data = None
                if self.progress_path.exists():
                    prior_data = read_json(str(self.progress_path))

                # Load noise discoveries from prior sessions
                if self.noise_path.exists():
                    noise_entries = read_jsonl(self.noise_path)
                    if noise_entries:
                        if prior_data is None:
                            prior_data = {}
                        prior_data["noise_discoveries"] = noise_entries

                if self._search_memory:
                    if prior_data is None:
                        prior_data = {}
                    prior_data["search_memory_summary"] = build_search_memory_summary(
                        self._search_memory
                    )

                self._execution_plan = form_strategy(self.brief_obj, self._kit_strings, prior_data)
                write_json(self.output_dir / "execution_plan.json", self._execution_plan.to_dict())
                print(f"  Strategy: {self._execution_plan.strategy_rationale[:120]}...")
                source = "kit vocabulary" if self._kit_strings else "JD context"
                print(f"  {len(self._execution_plan.generated_strings)} compound strings synthesized from {source}")
                if self._execution_plan.coverage_gaps:
                    gap_with_boolean = sum(1 for g in self._execution_plan.coverage_gaps if g.get("suggested_boolean"))
                    print(f"  {len(self._execution_plan.coverage_gaps)} coverage gaps identified ({gap_with_boolean} with executable strings)")

                # --- Phase 2b: Verbose strategy logging ---
                self._print_strategy_details()

                # --- Phase 3: Build execution order from plan ---
                search_strings = self._build_ordered_search_strings()
                for search_string in search_strings:
                    self._hydrate_search_string_metadata(search_string)

                progress = Progress(
                    brief_name=self.brief_obj.id,
                    strings=search_strings,
                )
                self._runtime_run_id, progress = self._runtime_bridge.start_or_resume_run(
                    resume=False,
                    initial_progress=progress,
                )
                self._progress = progress

            # --- Execution ---
            print(f"\n--- Execution ({len(progress.strings)} strings) ---")
            current_block = ""
            block_strings: list[SearchString] = []

            if resume:
                for s in progress.strings:
                    if s.status == "in_progress":
                        print(f"\n  Resuming interrupted string #{s.id}: {s.name[:60]}")

                if progress.pending_block_name and progress.pending_block_string_ids:
                    pending_by_id = {s.id: s for s in progress.strings}
                    pending_block_strings = [
                        pending_by_id[sid]
                        for sid in progress.pending_block_string_ids
                        if sid in pending_by_id and pending_by_id[sid].status == "done"
                    ]
                    if pending_block_strings:
                        if progress.pending_block_ready:
                            print(
                                f"\n  Resuming pending adaptation for "
                                f"{progress.pending_block_name} ({len(pending_block_strings)} strings)"
                            )
                            await self._run_block_adaptation(
                                progress.pending_block_name,
                                pending_block_strings,
                                progress,
                                adapt_after_block,
                            )
                        else:
                            current_block = progress.pending_block_name
                            block_strings = pending_block_strings
                            print(
                                f"\n  Restored block context for {current_block} "
                                f"({len(block_strings)} completed strings)"
                            )
                    else:
                        self._clear_pending_block_adaptation(progress)
                        self._checkpoint_progress(progress)

            string_index = 0
            while string_index < len(progress.strings):
                search_string = progress.strings[string_index]
                if search_string.status == "done":
                    print(f"\n  [skip] String #{search_string.id}: {search_string.name} (already done)")
                    string_index += 1
                    continue
                if search_string.status == "skipped":
                    print(f"\n  [skip] String #{search_string.id}: {search_string.name} (skipped by strategy)")
                    string_index += 1
                    continue

                # Block transition → adaptation
                if search_string.block and search_string.block != current_block:
                    if current_block and block_strings:
                        await self._run_block_adaptation(
                            current_block, block_strings, progress, adapt_after_block
                        )
                        block_strings = []
                        # Re-evaluate this position because adaptation may have
                        # inserted replacement strings or re-ordered the queue.
                        continue
                    current_block = search_string.block
                    block_strings = []

                print(f"\n{'─' * 60}")
                print(f"  String #{search_string.id}: {search_string.name}")
                print(f"  [{search_string.block} / {search_string.subblock} / {search_string.string_type}]")
                print(f"{'─' * 60}")

                search_string.status = "in_progress"
                progress.current_string_id = search_string.id
                browser_recovery_attempts = 0
                advance_to_next_string = False
                while True:
                    try:
                        await self._process_string(search_string, progress)
                        break
                    except SessionExpired:
                        stop_reason = RunStopReason.SESSION_EXPIRED
                        self._checkpoint_progress(
                            progress,
                            search_string=search_string,
                            page_num=progress.current_page or None,
                        )
                        if self._bias_monitor:
                            self._bias_monitor.save_checkpoint(str(self.bias_checkpoint_path))
                        raise
                    except GovernorLimitReached as e:
                        print(f"\n  [GOVERNOR] Session limit reached: {e.reason}")
                        stop_reason = RunStopReason.GOVERNOR_LIMIT
                        if self._runtime_run_id:
                            self._safety.record_governor_limit(
                                run_id=self._runtime_run_id,
                                reason=e.reason,
                                payload={"string_id": search_string.id},
                            )
                        self._checkpoint_progress(
                            progress,
                            search_string=search_string,
                            page_num=progress.current_page or None,
                        )
                        raise
                    except Exception as e:
                        if _is_browser_disconnect_error(e):
                            browser_recovery_attempts += 1
                            print(
                                f"\n  [!] Browser crashed during string #{search_string.id}. "
                                f"Recovery attempt {browser_recovery_attempts}/2..."
                            )
                            self._checkpoint_progress(
                                progress,
                                search_string=search_string,
                                page_num=progress.current_page or None,
                            )
                            recovery_url = self._last_good_url or self._get_project_url()
                            recovered = await self._recovery_service.recover(
                                run_id=self._runtime_run_id,
                                recovery_url=recovery_url,
                            )
                            if recovered and browser_recovery_attempts <= 2:
                                print(
                                    f"  [!] Recovery succeeded. Retrying string #{search_string.id} "
                                    f"from saved progress."
                                )
                                log_event(
                                    self.log_path,
                                    "browser_crash_recovered",
                                    string_id=search_string.id,
                                    attempt=browser_recovery_attempts,
                                )
                                continue

                            print(f"  [!] Recovery failed. Saving progress and exiting.")
                            stop_reason = RunStopReason.BROWSER_DISCONNECT_UNRECOVERED
                            raise

                        # Non-crash error: mark string as failed, save, continue to next
                        print(f"\n  [!] String #{search_string.id} failed: {e}")
                        search_string.status = "done"
                        search_string.notes = (search_string.notes or "") + f" Error: {e}"
                        self._checkpoint_progress(progress, search_string=search_string)
                        log_event(self.log_path, "string_error", string_id=search_string.id, error=str(e))
                        string_index += 1
                        advance_to_next_string = True
                        break

                if advance_to_next_string:
                    continue

                search_string.status = "done"
                block_strings.append(search_string)
                next_active = next(
                    (
                        candidate
                        for candidate in progress.strings[string_index + 1:]
                        if candidate.status not in {"done", "skipped"}
                    ),
                    None,
                )
                self._set_pending_block_adaptation(
                    progress,
                    current_block or search_string.block,
                    block_strings,
                    ready=next_active is None or next_active.block != (current_block or search_string.block),
                )
                self._checkpoint_progress(progress, search_string=search_string)
                if self._bias_monitor:
                    self._bias_monitor.save_checkpoint(str(self.bias_checkpoint_path))
                log_event(self.log_path, "string_complete", string_id=search_string.id, **self.stats)
                self._print_session_summary(progress)
                string_index += 1

            # Final block adaptation
            if current_block and block_strings:
                await self._run_block_adaptation(
                    current_block, block_strings, progress, adapt_after_block
                )

        except SessionExpired:
            print("\n\n  [!] Session duration cap reached. Progress saved.")
            run_status = "interrupted"
            stop_reason = RunStopReason.SESSION_EXPIRED
            raise
        except GovernorLimitReached as e:
            print(f"\n\n  [!] Governor limit reached: {e.reason}. Progress saved.")
            run_status = "governor_limit_reached"
            stop_reason = RunStopReason.GOVERNOR_LIMIT
            raise
        except KeyboardInterrupt:
            print("\n\n  [!] Interrupted. Progress saved.")
            run_status = "interrupted"
            stop_reason = RunStopReason.OPERATOR_STOP
        except Exception as e:
            print(f"\n  [ERROR] {e}")
            log_event(self.log_path, "pipeline_error", error=str(e))
            run_status = (
                "interrupted"
                if stop_reason == RunStopReason.BROWSER_DISCONNECT_UNRECOVERED
                else "error"
            )
            if stop_reason == RunStopReason.NORMAL:
                stop_reason = RunStopReason.FATAL_RUNTIME_ERROR
            raise
        finally:
            if self._progress:
                self._checkpoint_progress(self._progress)
            if self._bias_monitor:
                self._bias_monitor.save_checkpoint(str(self.bias_checkpoint_path))
            await self.browser.disconnect()
            self._print_summary()
            if self._progress:
                self._generate_run_report(self._progress)
            log_event(self.log_path, "pipeline_end", **self.stats)
            if self._runtime_run_id:
                self._safety.finish_run(
                    run_id=self._runtime_run_id,
                    status=run_status,
                    stop_reason=stop_reason,
                )
            if lock_acquired:
                self._runtime_lock.release()

    # ------------------------------------------------------------------
    # Browser crash recovery
    # ------------------------------------------------------------------

    async def _attempt_reconnect(
        self,
        recovery_url: str | None = None,
        max_attempts: int = 6,
        wait_seconds: int = 10,
    ) -> bool:
        """Try to reconnect to Chrome after a crash.

        Waits for the user to refresh LinkedIn Recruiter, then reconnects.
        Tries up to max_attempts times with wait_seconds between each.
        """
        import asyncio
        for attempt in range(max_attempts):
            print(f"  [reconnect] Attempt {attempt + 1}/{max_attempts} — waiting {wait_seconds}s for Chrome...")
            await asyncio.sleep(wait_seconds)
            try:
                await self.browser.disconnect()
            except Exception:
                pass
            try:
                await self.browser.connect()
                if recovery_url:
                    try:
                        await self.browser.navigate_to_search(recovery_url)
                    except Exception as nav_error:
                        print(f"  [reconnect] Reconnected but could not restore search page: {nav_error}")
                print(f"  [reconnect] Success — reconnected to LinkedIn Recruiter.")
                return True
            except Exception as e:
                print(f"  [reconnect] Failed: {e}")
        return False

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    async def _process_string(self, search_string: SearchString, progress: Progress) -> None:
        # Reset triage tightening state per string
        self._triage_tightened = False
        self._tightening_prefix = ""

        # Initialize refinement tracking
        if not search_string.original_boolean:
            search_string.original_boolean = search_string.boolean

        # Emergency recovery check before starting
        await self._ensure_browser_healthy()

        current_boolean = search_string.boolean
        resuming = search_string.pages_reviewed > 0

        if resuming:
            print(f"  Resuming string (interrupted on page {search_string.pages_reviewed})")

            # Dismiss any open profile panel
            try:
                await self.browser.go_back_to_results()
            except Exception:
                pass

            # Ensure we're on a search page
            current_page_url = self.browser.page.url
            if "/manage/" in current_page_url or "/talent/hire/" not in current_page_url:
                project_url = self._get_project_url()
                if project_url:
                    print(f"  Wrong page ({current_page_url[:60]}...). Navigating to search...")
                    await self.browser.navigate_to_search(project_url)
                else:
                    print(f"  Wrong page and no project URL. Reloading...")
                    await self.browser.page.reload(wait_until="domcontentloaded", timeout=30000)
                    await self.browser.page.wait_for_timeout(4000)

            # Always re-enter keywords — browser state is not trustworthy on resume
            print(f"  Re-entering Boolean: {current_boolean[:80]}...")
            await self.browser.enter_search_string(current_boolean)
            result_count_text = await self.browser.get_results_count_text()
            result_count = await self.browser.get_results_count()
            search_string.result_count = result_count
            print(f"  Results: {result_count_text or 'unknown'}")

            log_event(self.log_path, "string_resumed", string_id=search_string.id,
                      pages_done=search_string.pages_reviewed,
                      result_count=result_count, result_count_text=result_count_text)
        else:
            # Fresh string — enter the boolean
            print(f"  Entering Boolean: {current_boolean[:80]}...")
            await self.browser.enter_search_string(current_boolean)

            # Snapshot URL after search entry — known good state for recovery
            try:
                self._last_good_url = self.browser.page.url
            except Exception:
                pass

            result_count_text = await self.browser.get_results_count_text()
            result_count = await self.browser.get_results_count()
            search_string.result_count = result_count
            print(f"  Results: {result_count_text or 'unknown'} (parsed: {result_count})")
            log_event(self.log_path, "string_results", string_id=search_string.id,
                      result_count=result_count, result_count_text=result_count_text)

        # Guard: don't proceed with invalid result count
        if result_count <= 0:
            print(f"  No results detected (result_count={result_count}). Skipping string.")
            search_string.status = "skipped"
            search_string.notes = (search_string.notes or "") + " Skipped: no results on entry."
            self._checkpoint_progress(progress, search_string=search_string)
            return

        # Determine starting phase
        # If resuming with an existing refinement stack, go straight to paginate
        if search_string.refinement_stack:
            search_string.phase = "paginate"
        elif result_count >= 3000:
            search_string.phase = "scout"
            print(f"  [phase] SCOUT — {result_count} results, exploring page 1 first")
        else:
            search_string.phase = "paginate"
            print(f"  [phase] PAGINATE — {result_count} results, proceeding directly")

        # Accumulating context for page-level adaptation
        all_candidates: list[dict] = []
        string_stats = {"pages": 0, "candidates": 0, "duplicates": 0,
                        "facial_yes": 0, "facial_no": 0, "saves": 0, "rejects": 0}

        page_num = 1
        max_pages = config.MAX_PAGES_PER_STRING or 999

        # On resume, skip to the interrupted page (re-process it; dupe filter handles already-seen)
        if resuming and search_string.pages_reviewed > 1:
            target_page = search_string.pages_reviewed
            print(f"  Advancing to page {target_page}...")
            for _ in range(target_page - 1):
                has_next = await self.browser.go_to_next_page()
                if not has_next:
                    print("  No more pages after resume point.")
                    search_string.status = "done"
                    self._checkpoint_progress(progress, search_string=search_string)
                    return
            page_num = target_page

        while page_num <= max_pages:
            # Emergency recovery check before each page
            await self._ensure_browser_healthy()

            phase_label = search_string.phase.upper()
            refinement_depth = len(search_string.refinement_stack)
            print(f"\n  --- Page {page_num} [{phase_label}] (refinement depth: {refinement_depth}) ---")
            progress.current_page = page_num

            # Check for 0-result page before trying to scroll/extract
            try:
                no_results = self.browser.page.locator('text="No search results"').first
                if await no_results.is_visible(timeout=2000):
                    print("  No search results for this string. Skipping.")
                    break
            except Exception:
                pass

            # Review the page top-to-bottom, card by card.
            page_report = _PageReport(
                string_id=search_string.id,
                string_name=search_string.name,
                page=page_num,
                result_count=result_count,
            )

            glance_result = await self._review_page_sequentially(
                search_string=search_string,
                page_num=page_num,
                result_count=result_count,
                page_report=page_report,
                all_candidates=all_candidates,
                string_stats=string_stats,
                progress=progress,
            )

            string_stats["pages"] = page_num
            self._checkpoint_progress(progress, search_string=search_string, page_num=page_num)
            page_report.print_report(self.stats)

            # --- Two-phase adaptation ---
            adapt_action = await self._page_adapt(
                search_string, current_boolean, result_count_text,
                all_candidates, string_stats,
                glance_summary=(glance_result.summary
                                if glance_result and glance_result.action == "reformulate"
                                else None),
                architecture=(self._execution_plan.architecture
                              if self._execution_plan else ""),
            )

            # Enforce minimum pagination depth.
            # Forced narrow is allowed only once in scout when page 1 is clearly all-noise.
            if adapt_action in ("abandon", "stop"):
                min_pages = self._get_min_pages(result_count)
                if page_num < min_pages:
                    if self._should_force_narrow_in_scout(
                        search_string=search_string,
                        page_num=page_num,
                        result_count=result_count,
                        string_stats=string_stats,
                        glance_result=glance_result,
                    ):
                        print(
                            f"  [pagination] Opus wants to {adapt_action}, but page {page_num} "
                            f"< min {min_pages} for {result_count} results. Attempting scout narrow..."
                        )
                        narrow_result = await self._force_narrow_adapt(
                            search_string, current_boolean, result_count_text,
                            all_candidates, string_stats,
                        )
                        if narrow_result:
                            adapt_action = narrow_result
                        else:
                            print(
                                f"  [pagination] Scout narrow unavailable. "
                                f"Continuing despite {adapt_action}."
                            )
                            adapt_action = "continue"
                    else:
                        print(
                            f"  [pagination] Opus wants to {adapt_action}, but page {page_num} "
                            f"< min {min_pages} for {result_count} results. Continuing."
                        )
                        adapt_action = "continue"

            if adapt_action == "abandon":
                print(f"  [adapt] Opus says ABANDON this string entirely.")
                search_string.notes = (search_string.notes or "") + f" Abandoned after page {page_num}."
                break

            elif adapt_action == "stop":
                print(f"  [adapt] Opus says STOP — signal exhausted.")
                search_string.notes = (search_string.notes or "") + f" Stopped after page {page_num}."
                break

            elif isinstance(adapt_action, str) and adapt_action.startswith("narrow:"):
                new_boolean = adapt_action[len("narrow:"):]
                # Push current boolean onto refinement stack
                search_string.refinement_stack.append(current_boolean)
                current_boolean = new_boolean
                search_string.boolean = new_boolean
                search_string.phase = "paginate"
                depth = len(search_string.refinement_stack)
                print(f"  [adapt] NARROW (depth {depth}): {new_boolean[:80]}...")
                search_string.notes = (search_string.notes or "") + f" Narrowed on page {page_num} (depth {depth})."
                try:
                    await self.browser.enter_search_string(new_boolean)
                    result_count_text = await self.browser.get_results_count_text()
                    result_count = await self.browser.get_results_count()
                    search_string.result_count = result_count
                    print(f"  Results after narrow: {result_count_text or 'unknown'} (parsed: {result_count})")
                except Exception as e:
                    print(f"  [ERROR] Narrow failed: {e} — reverting to previous boolean")
                    log_event(self.log_path, "narrow_failed", string=search_string.name, error=str(e))
                    search_string.refinement_stack.pop()  # Undo the push
                    current_boolean = search_string.refinement_stack[-1] if search_string.refinement_stack else search_string.boolean
                    search_string.boolean = current_boolean
                    break
                # Reset page counter and accumulated data for the narrowed search
                page_num = 1
                all_candidates.clear()
                string_stats = {"pages": 0, "candidates": 0, "duplicates": 0,
                                "facial_yes": 0, "facial_no": 0, "saves": 0, "rejects": 0}
                continue

            elif adapt_action == "broaden":
                if not search_string.refinement_stack:
                    print(f"  [adapt] BROADEN requested but stack is empty — continuing instead.")
                else:
                    previous_boolean = search_string.refinement_stack.pop()
                    current_boolean = previous_boolean
                    search_string.boolean = previous_boolean
                    depth = len(search_string.refinement_stack)
                    print(f"  [adapt] BROADEN (depth now {depth}): reverting to {previous_boolean[:80]}...")
                    search_string.notes = (search_string.notes or "") + f" Broadened on page {page_num} (depth {depth})."
                    try:
                        await self.browser.enter_search_string(previous_boolean)
                        result_count_text = await self.browser.get_results_count_text()
                        result_count = await self.browser.get_results_count()
                        search_string.result_count = result_count
                        print(f"  Results after broaden: {result_count_text or 'unknown'} (parsed: {result_count})")
                    except Exception as e:
                        print(f"  [ERROR] Broaden failed: {e} — abandoning string")
                        log_event(self.log_path, "broaden_failed", string=search_string.name, error=str(e))
                        search_string.notes = (search_string.notes or "") + f" Broaden failed on page {page_num}."
                        break
                    # Reset page counter — broadened search starts fresh
                    page_num = 1
                    all_candidates.clear()
                    string_stats = {"pages": 0, "candidates": 0, "duplicates": 0,
                                    "facial_yes": 0, "facial_no": 0, "saves": 0, "rejects": 0}
                    continue

            elif adapt_action == "paginate":
                # Scout phase complete — transition to paginate
                search_string.phase = "paginate"
                print(f"  [adapt] Scout complete → PAGINATE")

            # "continue" or "paginate" — proceed to next page
            if page_num < max_pages:
                has_next = await self.browser.go_to_next_page()
                if not has_next:
                    print("  No more pages.")
                    break
                page_num += 1
                await asyncio.sleep(human_delay_correlated(config.PAGE_DELAY_SECONDS, channel="page_turn"))
            else:
                break

        # Persist transient facial stats onto SearchString for block-level aggregation
        search_string.facial_yes_count = string_stats["facial_yes"]
        search_string.facial_no_count = string_stats["facial_no"]
        search_string.candidates_count = string_stats["candidates"]
        search_string.duplicates_count = string_stats["duplicates"]
        self._hydrate_search_string_metadata(search_string)

    async def _extract_card_snippet(
        self,
        search_string: SearchString,
        page_num: int,
        card_index: int,
    ) -> CandidateSnippet | None:
        self._ensure_services()
        result = await self._acquisition_service.extract_card_snippet(
            search_string,
            page_num,
            card_index,
        )
        return result.snippet if result else None

    async def _preview_skip_pause(self, reason: str) -> None:
        """Pause on visible skips so the review flow does not feel bursty."""
        if reason == "facial_no":
            dwell = human_delay_correlated(random.uniform(0.8, 2.0), channel="preview_no")
        elif reason == "facial_skip":
            dwell = human_delay_correlated(random.uniform(0.7, 1.6), channel="preview_skip")
        elif reason in {"already_saved", "duplicate"}:
            dwell = human_delay_correlated(random.uniform(0.2, 0.6), channel="preview_skip")
        else:
            dwell = human_delay_correlated(random.uniform(0.2, 0.5), channel="preview_skip")
        await asyncio.sleep(dwell)

    async def _review_page_sequentially(
        self,
        search_string: SearchString,
        page_num: int,
        result_count: int,
        page_report: "_PageReport",
        all_candidates: list[dict],
        string_stats: dict,
        progress: Progress | None = None,
    ) -> GlanceResult | None:
        """Review the current results page top-to-bottom, card by card."""
        # V2 briefs: use batch facial triage (one LLM call for all candidates on page)
        if self.brief_obj and self.brief_obj.has_v2_schema:
            return await self._review_page_batch(
                search_string, page_num, result_count, page_report,
                all_candidates, string_stats, progress,
            )

        slot_count = await self.browser.get_card_slot_count()
        if slot_count == 0:
            # Fallback if the list has not hydrated yet.
            fallback_count = await self.browser.scroll_to_load_all_results()
            slot_count = fallback_count or await self.browser.get_card_count()

        print(f"  Reviewing {slot_count} card slots sequentially", flush=True)
        if slot_count == 0:
            return None

        glance_result = None
        preview_snippets: list[CandidateSnippet] = []
        consecutive_api_errors = 0
        page_evaluated = 0
        page_facial_no = 0

        for card_index in range(slot_count):
            snippet = await self._extract_card_snippet(search_string, page_num, card_index)
            if not snippet:
                continue

            preview_snippets.append(snippet)
            print(
                f"    [card {card_index + 1}/{slot_count}] {snippet.name} — "
                f"{snippet.current_title or snippet.headline or 'preview only'}"
            )

            if not snippet.profile_url:
                print(f"    [skip] {snippet.name} — missing durable profile URL")
                if page_report:
                    page_report.add_skip_preview(snippet.name, "missing_profile_url")
                if self._runtime_bridge and self._runtime_run_id:
                    self._runtime_bridge.record_missing_identity(
                        run_id=self._runtime_run_id,
                        search_string=search_string,
                        snippet=snippet,
                    )
                continue

            url = snippet.profile_url
            if url and (url in self._seen_urls or url in self._in_flight_urls):
                if url in self._seen_urls:
                    prior = self._prior_outcomes.get(url, "")
                    if prior in ("SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE"):
                        print(f"    [dup] {snippet.name} — saved in prior session")
                    elif prior == "REJECT":
                        print(f"    [dup] {snippet.name} — rejected in prior session")
                    elif prior in ("FACIAL_NO", "FACIAL_SKIP"):
                        print(f"    [dup] {snippet.name} — {prior} in prior session")
                    elif prior == "FACIAL_YES":
                        print(f"    [re-eval] {snippet.name} — facial YES in prior session, completing evaluation")
                        self._seen_urls.discard(url)
                    else:
                        print(f"    [dup] {snippet.name} — already processed")
                if url in self._seen_urls or url in self._in_flight_urls:
                    page_report.add_skip_preview(snippet.name, "duplicate")
                    string_stats["duplicates"] += 1
                    await self._preview_skip_pause("duplicate")
                    continue

            if snippet.already_saved:
                print(f"    [skip] {snippet.name} — already saved in LinkedIn pipeline")
                page_report.add_skip_preview(snippet.name, "already_saved")
                string_stats.setdefault("already_saved_skips", 0)
                string_stats["already_saved_skips"] += 1
                await self._preview_skip_pause("already_saved")
                continue

            if consecutive_api_errors >= 5:
                print(f"    [CIRCUIT BREAKER] {consecutive_api_errors} consecutive API failures — pausing 60s")
                log_event(self.log_path, "circuit_breaker", consecutive_errors=consecutive_api_errors)
                await asyncio.sleep(60)
                consecutive_api_errors = 0

            if snippet.profile_url:
                self._in_flight_urls.add(snippet.profile_url)
            self._record_runtime_snippet(search_string, snippet)
            self.stats["snippets_extracted"] += 1
            string_stats["candidates"] += 1

            decision = await self._evaluate_snippet(snippet, page_report, search_string)

            if decision and hasattr(decision, "rationale") and "[API error" in (decision.rationale or ""):
                consecutive_api_errors += 1
            else:
                consecutive_api_errors = 0

            if decision and getattr(decision, "_panel_stuck", False):
                print(f"    [ERROR] Panel stuck after {snippet.name} — skipping remaining candidates on this page")
                log_event(self.log_path, "panel_stuck", name=snippet.name, page=page_num)
                break

            outcome = "error"
            if decision:
                if decision.stage == "facial" and decision.decision == "FACIAL_NO":
                    outcome = "facial_no"
                    string_stats["facial_no"] += 1
                elif decision.stage == "facial" and decision.decision == "FACIAL_SKIP":
                    outcome = "facial_skip"
                    string_stats.setdefault("facial_skip", 0)
                    string_stats["facial_skip"] += 1
                elif decision.decision == "SAVE":
                    outcome = "save"
                    string_stats["facial_yes"] += 1
                    string_stats["saves"] += 1
                    search_string.saves.append(snippet.name)
                elif decision.decision == "REJECT":
                    outcome = "reject"
                    string_stats["facial_yes"] += 1
                    string_stats["rejects"] += 1
                elif decision.stage == "facial" and decision.decision == "FACIAL_YES":
                    outcome = "facial_yes"
                    string_stats["facial_yes"] += 1

            all_candidates.append({
                "name": snippet.name,
                "title": snippet.current_title,
                "company": snippet.current_company,
                "headline": snippet.headline,
                "outcome": outcome,
                "rationale": decision.rationale if decision else "",
                "page": page_num,
            })

            if outcome == "facial_no":
                page_facial_no += 1
                await self._preview_skip_pause("facial_no")
            elif outcome == "facial_skip":
                await self._preview_skip_pause("facial_skip")

            if outcome in ("facial_no", "save", "reject", "facial_yes"):
                page_evaluated += 1

            self._checkpoint_progress(progress, search_string=search_string, page_num=page_num)

            if glance_result is None and len(preview_snippets) >= config.GLANCE_MIN_SNIPPETS:
                glance_result = self._glance_assess(preview_snippets)
                log_event(
                    self.log_path,
                    "glance_assess",
                    string_id=search_string.id,
                    page=page_num,
                    action=glance_result.action,
                    confidence=glance_result.confidence,
                    signals=glance_result.signals,
                )
                print(
                    f"  [glance] {glance_result.action} ({glance_result.confidence:.2f}): "
                    f"{glance_result.summary}"
                )
                if glance_result.action == "reformulate":
                    print("    [glance] Sequential review found strong reformulation signal — breaking page")
                    break

            if page_evaluated >= config.EARLY_EXIT_MIN_CANDIDATES:
                page_no_rate = page_facial_no / page_evaluated
                if page_no_rate >= self._get_early_exit_rate():
                    print(
                        f"    [early-exit] {page_facial_no}/{page_evaluated} "
                        f"facial_no ({page_no_rate:.0%}) — breaking page"
                    )
                    log_event(
                        self.log_path,
                        "early_exit",
                        string_id=search_string.id,
                        page=page_num,
                        evaluated=page_evaluated,
                        facial_no=page_facial_no,
                        rate=round(page_no_rate, 2),
                    )
                    break

            if progress and hasattr(self, "_session_expired") and self._session_expired.is_set():
                self._checkpoint_progress(progress)
                raise SessionExpired("session_duration_cap")

            if progress and hasattr(self, "_pause_requested") and self._pause_requested.is_set():
                self._pause_requested.clear()
                self._checkpoint_progress(progress)
                try:
                    await asyncio.wait_for(self._resume_event.wait(), timeout=300)
                except asyncio.TimeoutError:
                    print("  [!] Resume timeout (5 min) — continuing without decoy burst.")
                    self._resume_event.set()

        return glance_result

    async def _review_page_batch(
        self,
        search_string: SearchString,
        page_num: int,
        result_count: int,
        page_report: "_PageReport",
        all_candidates: list[dict],
        string_stats: dict,
        progress: Progress | None = None,
    ) -> GlanceResult | None:
        """Batch-mode page review for V2 briefs.

        Three phases:
          1. Extract all card snippets (browser interaction, no LLM calls)
          2. Batch facial triage (one LLM call for all eligible snippets)
          3. Full evaluation for FACIAL_YES candidates (sequential profile opens)
        """
        from shared.judger import facial_judge_batch, is_failure_decision

        slot_count = await self.browser.get_card_slot_count()
        if slot_count == 0:
            fallback_count = await self.browser.scroll_to_load_all_results()
            slot_count = fallback_count or await self.browser.get_card_count()

        print(f"  Reviewing {slot_count} card slots (batch mode)", flush=True)
        if slot_count == 0:
            return None

        # ── Phase 1: Extract all card snippets ──────────────────────────
        glance_result = None
        preview_snippets: list[CandidateSnippet] = []
        eligible_snippets: list[CandidateSnippet] = []

        for card_index in range(slot_count):
            snippet = await self._extract_card_snippet(search_string, page_num, card_index)
            if not snippet:
                continue

            preview_snippets.append(snippet)
            print(
                f"    [card {card_index + 1}/{slot_count}] {snippet.name} — "
                f"{snippet.current_title or snippet.headline or 'preview only'}"
            )

            if not snippet.profile_url:
                print(f"    [skip] {snippet.name} — missing durable profile URL")
                if page_report:
                    page_report.add_skip_preview(snippet.name, "missing_profile_url")
                if self._runtime_bridge and self._runtime_run_id:
                    self._runtime_bridge.record_missing_identity(
                        run_id=self._runtime_run_id,
                        search_string=search_string,
                        snippet=snippet,
                    )
                continue

            # Dedup check
            url = snippet.profile_url
            if url and (url in self._seen_urls or url in self._in_flight_urls):
                if url in self._seen_urls:
                    prior = self._prior_outcomes.get(url, "")
                    if prior in ("SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE"):
                        print(f"    [dup] {snippet.name} — saved in prior session")
                    elif prior == "REJECT":
                        print(f"    [dup] {snippet.name} — rejected in prior session")
                    elif prior in ("FACIAL_NO", "FACIAL_SKIP"):
                        print(f"    [dup] {snippet.name} — {prior} in prior session")
                    elif prior == "FACIAL_YES":
                        print(f"    [re-eval] {snippet.name} — facial YES in prior session, completing evaluation")
                        self._seen_urls.discard(url)
                    else:
                        print(f"    [dup] {snippet.name} — already processed")
                if url in self._seen_urls or url in self._in_flight_urls:
                    page_report.add_skip_preview(snippet.name, "duplicate")
                    string_stats["duplicates"] += 1
                    await self._preview_skip_pause("duplicate")
                    continue

            if snippet.already_saved:
                print(f"    [skip] {snippet.name} — already saved in LinkedIn pipeline")
                page_report.add_skip_preview(snippet.name, "already_saved")
                string_stats.setdefault("already_saved_skips", 0)
                string_stats["already_saved_skips"] += 1
                await self._preview_skip_pause("already_saved")
                continue

            # Employer blacklist check (no LLM call)
            blacklisted = False
            if self.brief_obj.employer_blacklist and snippet.current_company:
                company_lower = snippet.current_company.lower()
                for blocked in self.brief_obj.employer_blacklist:
                    if blocked.lower() in company_lower:
                        print(f"    [BLACKLIST] {snippet.name} — '{snippet.current_company}' matches '{blocked}'")
                        self.stats.setdefault("blacklist_skips", 0)
                        self.stats["blacklist_skips"] += 1
                        if page_report:
                            page_report.add_skip_preview(snippet.name, f"BLACKLIST: {blocked}")
                        bl_decision = OpusDecision(
                            stage="facial", decision="FACIAL_NO", path="employer_blacklist",
                            confidence=1.0, rationale=f"Employer blacklist: {blocked}",
                            candidate_name=snippet.name, profile_url=snippet.profile_url,
                        )
                        facial_attempt_id = self._start_runtime_stage_attempt(
                            search_string=search_string,
                            snippet=snippet,
                            stage="facial",
                        )
                        self._finish_runtime_stage_success(
                            attempt_id=facial_attempt_id,
                            stage="facial",
                            snippet=snippet,
                            decision=bl_decision,
                        )
                        self._prior_outcomes[snippet.profile_url] = "FACIAL_NO"
                        self._mark_terminal(snippet.profile_url)
                        all_candidates.append({
                            "name": snippet.name, "title": snippet.current_title,
                            "company": snippet.current_company, "headline": snippet.headline,
                            "outcome": "facial_no", "rationale": bl_decision.rationale,
                            "page": page_num,
                        })
                        string_stats["facial_no"] += 1
                        blacklisted = True
                        break
            if blacklisted:
                continue

            # Eligible for batch facial
            if snippet.profile_url:
                self._in_flight_urls.add(snippet.profile_url)
            self._record_runtime_snippet(search_string, snippet)
            self.stats["snippets_extracted"] += 1
            string_stats["candidates"] += 1
            eligible_snippets.append(snippet)

            # Glance assessment
            if glance_result is None and len(preview_snippets) >= config.GLANCE_MIN_SNIPPETS:
                glance_result = self._glance_assess(preview_snippets)
                log_event(
                    self.log_path, "glance_assess", string_id=search_string.id,
                    page=page_num, action=glance_result.action,
                    confidence=glance_result.confidence, signals=glance_result.signals,
                )
                print(
                    f"  [glance] {glance_result.action} ({glance_result.confidence:.2f}): "
                    f"{glance_result.summary}"
                )
                if glance_result.action == "reformulate":
                    print("    [glance] Batch extraction found strong reformulation signal — stopping extraction")
                    break

            if progress and hasattr(self, "_session_expired") and self._session_expired.is_set():
                self._checkpoint_progress(progress)
                raise SessionExpired("session_duration_cap")

        if not eligible_snippets:
            return glance_result

        # ── Phase 2: Batch facial triage ────────────────────────────────
        print(f"  Batch facial triage: {len(eligible_snippets)} candidates in one call", flush=True)

        decisions = facial_judge_batch(
            eligible_snippets, self.brief_obj, prompt_prefix=self._tightening_prefix,
        )

        facial_yes_snippets: list[CandidateSnippet] = []
        page_evaluated = 0
        page_facial_no = 0

        for snippet, facial in zip(eligible_snippets, decisions):
            facial_attempt_id = self._start_runtime_stage_attempt(
                search_string=search_string,
                snippet=snippet,
                stage="facial",
            )

            # Handle parse/judgment failures
            if is_failure_decision(facial.decision):
                print(f"    [PARSE_FAILURE] {snippet.name}: {facial.rationale}")
                self.stats.setdefault("parse_failures", 0)
                self.stats["parse_failures"] += 1
                if self._bias_monitor:
                    self._bias_monitor.record_decision(DecisionRecord(
                        candidate_id=f"{snippet.source_string_id}_p{snippet.page}_r{snippet.result_rank}",
                        string_id=str(snippet.source_string_id),
                        stage="facial", decision=facial.decision,
                        confidence=facial.confidence, capability_area=None,
                ))
                self._finish_runtime_failure_decision(
                    attempt_id=facial_attempt_id,
                    snippet=snippet,
                    decision=facial,
                )
                self._in_flight_urls.discard(snippet.profile_url)
                all_candidates.append({
                    "name": snippet.name, "title": snippet.current_title,
                    "company": snippet.current_company, "headline": snippet.headline,
                    "outcome": "error", "rationale": facial.rationale, "page": page_num,
                })
                continue

            self._prior_outcomes[snippet.profile_url] = facial.decision
            self._mark_terminal(snippet.profile_url)
            self._finish_runtime_stage_success(
                attempt_id=facial_attempt_id,
                stage="facial",
                snippet=snippet,
                decision=facial,
            )

            # Bias monitoring
            if self._bias_monitor:
                self._bias_monitor.record_decision(DecisionRecord(
                    candidate_id=f"{snippet.source_string_id}_p{snippet.page}_r{snippet.result_rank}",
                    string_id=str(snippet.source_string_id),
                    stage="facial", decision=facial.decision,
                    confidence=facial.confidence, capability_area=None,
                ))

            if facial.decision in ("FACIAL_NO", "FACIAL_SKIP"):
                tag = "FACIAL_NO" if facial.decision == "FACIAL_NO" else "FACIAL_SKIP"
                print(f"    [{tag}] {snippet.name}: {facial.rationale}")
                if facial.decision == "FACIAL_NO":
                    self.stats["facial_no"] += 1
                    page_facial_no += 1
                else:
                    self.stats.setdefault("facial_skip", 0)
                    self.stats["facial_skip"] += 1
                if page_report:
                    page_report.add_skip_preview(snippet.name, f"{tag}: {facial.rationale}")
                all_candidates.append({
                    "name": snippet.name, "title": snippet.current_title,
                    "company": snippet.current_company, "headline": snippet.headline,
                    "outcome": "facial_no" if facial.decision == "FACIAL_NO" else "facial_skip",
                    "rationale": facial.rationale, "page": page_num,
                })
                page_evaluated += 1
            else:
                # FACIAL_YES
                print(f"    [FACIAL_YES] {snippet.name}: {facial.rationale}")
                self.stats["facial_yes"] += 1
                facial_yes_snippets.append(snippet)
                all_candidates.append({
                    "name": snippet.name, "title": snippet.current_title,
                    "company": snippet.current_company, "headline": snippet.headline,
                    "outcome": "facial_yes", "rationale": facial.rationale, "page": page_num,
                })
                page_evaluated += 1

        # Tightening check (applies to NEXT page — batch processes current page at once)
        if not self._triage_tightened and self._bias_monitor:
            tightening = self._bias_monitor.get_tightening_status(str(snippet.source_string_id))
            if tightening:
                self._triage_tightened = True
                self._tightening_prefix = (
                    f"⚠ TRIAGE TIGHTENING ACTIVE: The facial YES rate on this search string is running "
                    f"{tightening['actual_rate']:.0%}, which is {tightening['multiplier']:.1f}x above the expected "
                    f"maximum of {tightening['expected_high']:.0%}. Apply stricter filtering: require TWO strong "
                    f"positive signals for FACIAL_YES instead of one.\n\n"
                )
                print(f"    [bias] Tightening facial criteria for next page "
                      f"(YES rate: {tightening['actual_rate']:.0%}, expected max: {tightening['expected_high']:.0%})")

        # Early exit check (after all batch results are known)
        if page_evaluated >= config.EARLY_EXIT_MIN_CANDIDATES:
            page_no_rate = page_facial_no / page_evaluated
            if page_no_rate >= self._get_early_exit_rate():
                print(
                    f"    [early-exit] {page_facial_no}/{page_evaluated} "
                    f"facial_no ({page_no_rate:.0%}) — skipping full evals"
                )
                log_event(
                    self.log_path, "early_exit", string_id=search_string.id,
                    page=page_num, evaluated=page_evaluated,
                    facial_no=page_facial_no, rate=round(page_no_rate, 2),
                )
                facial_yes_snippets.clear()

        self._checkpoint_progress(progress, search_string=search_string, page_num=page_num)

        # ── Phase 3: Full evaluation for FACIAL_YES candidates ──────────
        consecutive_api_errors = 0

        for snippet in facial_yes_snippets:
            if progress and hasattr(self, "_session_expired") and self._session_expired.is_set():
                self._checkpoint_progress(progress)
                raise SessionExpired("session_duration_cap")

            if consecutive_api_errors >= 5:
                print(f"    [CIRCUIT BREAKER] {consecutive_api_errors} consecutive API failures — pausing 60s")
                log_event(self.log_path, "circuit_breaker", consecutive_errors=consecutive_api_errors)
                await asyncio.sleep(60)
                consecutive_api_errors = 0

            decision = await self._full_evaluate(snippet, page_report, search_string)

            if decision and hasattr(decision, "rationale") and "[API error" in (decision.rationale or ""):
                consecutive_api_errors += 1
            else:
                consecutive_api_errors = 0

            if decision and getattr(decision, "_panel_stuck", False):
                print(f"    [ERROR] Panel stuck after {snippet.name} — skipping remaining full evals")
                log_event(self.log_path, "panel_stuck", name=snippet.name, page=page_num)
                break

            # Update the candidate entry in all_candidates with full eval outcome
            if decision:
                if decision.decision in ("SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE"):
                    outcome = "save"
                    string_stats["saves"] += 1
                    string_stats["facial_yes"] += 1
                    search_string.saves.append(snippet.name)
                elif decision.decision == "REJECT":
                    outcome = "reject"
                    string_stats["rejects"] += 1
                    string_stats["facial_yes"] += 1
                elif decision.stage == "full" and is_failure_decision(decision.decision):
                    outcome = "error"
                else:
                    outcome = "facial_yes"
                    string_stats["facial_yes"] += 1

                for c in all_candidates:
                    if c["name"] == snippet.name and c["page"] == page_num and c["outcome"] == "facial_yes":
                        c["outcome"] = outcome
                        c["rationale"] = decision.rationale
                        break

            self._checkpoint_progress(progress, search_string=search_string, page_num=page_num)

            if progress and hasattr(self, "_pause_requested") and self._pause_requested.is_set():
                self._pause_requested.clear()
                self._checkpoint_progress(progress)
                try:
                    await asyncio.wait_for(self._resume_event.wait(), timeout=300)
                except asyncio.TimeoutError:
                    print("  [!] Resume timeout (5 min) — continuing without decoy burst.")
                    self._resume_event.set()

        return glance_result

    def _get_min_pages(self, result_count: int) -> int:
        """Get minimum pages to review before allowing stop/abandon."""
        overrides = {}
        if self._execution_plan and self._execution_plan.architecture:
            overrides = config.ARCHITECTURE_OVERRIDES.get(self._execution_plan.architecture, {})
        thresholds = overrides.get("min_pages_by_result_count", config.MIN_PAGES_BY_RESULT_COUNT)
        for threshold, min_pages in thresholds:
            if result_count >= threshold:
                return min_pages
        return 1

    def _should_force_narrow_in_scout(
        self,
        *,
        search_string: SearchString,
        page_num: int,
        result_count: int,
        string_stats: dict,
        glance_result: GlanceResult | None,
    ) -> bool:
        """Allow forced narrow only for page-1 scout strings that show zero signal."""
        return (
            search_string.phase == "scout"
            and page_num == 1
            and result_count >= 500
            and not search_string.refinement_stack
            and string_stats.get("saves", 0) == 0
            and string_stats.get("facial_yes", 0) == 0
            and glance_result is not None
            and glance_result.action == "reformulate"
        )

    def _get_early_exit_rate(self) -> float:
        """Get facial_no rate threshold for mid-page early exit.

        Derives from brief's facial_calibration when available:
        formula: 1.0 - (expected_yes_rate_low * 0.5)
        Meaning: exit when NO rate is so extreme that even the most pessimistic
        expected YES rate is halved. Architecture overrides can only tighten (raise)
        this floor, never loosen it.
        """
        # Brief-derived threshold
        brief_rate = None
        if (self.brief_obj and self.brief_obj.has_v2_schema
                and self.brief_obj._new_brief.facial_calibration):
            fc = self.brief_obj._new_brief.facial_calibration
            brief_rate = 1.0 - (fc.expected_yes_rate_low * 0.5)

        # Architecture override from config
        arch_rate = config.EARLY_EXIT_FACIAL_NO_RATE
        if self._execution_plan and self._execution_plan.architecture:
            overrides = config.ARCHITECTURE_OVERRIDES.get(self._execution_plan.architecture, {})
            arch_rate = overrides.get("early_exit_facial_no_rate", config.EARLY_EXIT_FACIAL_NO_RATE)

        if brief_rate is not None:
            # Architecture can tighten (raise) but not loosen (lower) beyond brief floor
            return max(arch_rate, brief_rate)
        return arch_rate

    async def _ensure_browser_healthy(self) -> None:
        """Check for error states, attempt recovery, and enforce cadence pauses."""
        # --- Cadence pause: human-like idle break ---
        await self._maybe_cadence_pause()

        # --- Snapshot current URL as known-good before checking for errors ---
        try:
            current_url = self.browser.page.url
            if "linkedin.com/talent" in current_url and "/login" not in current_url and "/manage/" not in current_url:
                self._last_good_url = current_url
        except Exception:
            pass

        # --- Error recovery ---
        recovered = await self.browser.check_and_recover()
        if recovered:
            # Try project URL first, then last known good URL
            recovery_url = self._last_good_url or self._get_project_url()
            if recovery_url:
                print(f"  [recovery] Re-navigating to: {recovery_url[:60]}...")
                await self.browser.navigate_to_search(recovery_url)
            else:
                print("  [recovery] No recovery URL available — continuing from current page.")

    def _get_project_url(self) -> str:
        """Construct LinkedIn Recruiter project URL from brief or auto-detected browser URL."""
        pid = self.brief_obj.linkedin_project_id
        if not pid and hasattr(self.browser, '_project_id'):
            pid = self.browser._project_id
        if pid:
            return f"https://www.linkedin.com/talent/hire/{pid}/discover/recruiterSearch"
        return ""

    async def _maybe_cadence_pause(self) -> None:
        """Pause if enough continuous activity time has elapsed (anti-detection).

        When running under session_orchestrator, decoy interleave bursts serve as
        cadence breaks — skip the independent timer to avoid double-pausing.
        """
        # Decoy interleaving replaces cadence pauses when session_orchestrator is active
        if hasattr(self, '_pause_requested'):
            return

        if config.CADENCE_INTERVAL_MINUTES <= 0:
            return

        elapsed = (time.time() - self._last_pause_time) / 60.0
        # Jitter the interval ±20% so it's not metronomic
        jittered_interval = human_delay(
            config.CADENCE_INTERVAL_MINUTES * 0.8,
            config.CADENCE_INTERVAL_MINUTES * 1.4,
        )

        if elapsed >= jittered_interval:
            # Jitter the pause duration ±25%
            pause_secs = human_delay(
                config.CADENCE_PAUSE_SECONDS * 0.6,
                config.CADENCE_PAUSE_SECONDS * 2.0,
            )
            print(f"\n  [cadence] {elapsed:.0f}min of activity — pausing {pause_secs:.0f}s to look human...")
            log_event(self.log_path, "cadence_pause", elapsed_minutes=round(elapsed, 1),
                      pause_seconds=round(pause_secs, 1))
            await asyncio.sleep(pause_secs)
            self._last_pause_time = time.time()
            print(f"  [cadence] Resuming.")

    # ------------------------------------------------------------------
    # Glance assessment — page-level pre-filter
    # ------------------------------------------------------------------

    def _get_glance_key_terms(self) -> list[str]:
        """Extract key terms from the brief for glance keyword scanning."""
        nb = self.brief_obj._new_brief
        if nb is not None:
            # V2 brief: collect key_terms from all capability_areas
            terms = []
            for ca in nb.capability_areas:
                terms.extend(t.lower() for t in ca.key_terms)
            return terms
        # Old brief: extract from archetypes save_signals
        terms = []
        for arch in self.brief_obj.archetypes:
            for sig in arch.get("save_signals", []):
                # Each save_signal is a short phrase — use as-is
                terms.append(sig.lower())
        return terms

    def _glance_assess(self, snippets: list[CandidateSnippet]) -> GlanceResult:
        """Fast page-level assessment from snippet metadata. No per-candidate LLM calls."""
        signals = {}
        noise_count = 0

        # --- Signal 1: Title clustering ---
        title_families: dict[str, int] = {}
        for s in snippets:
            family = _normalize_title_family(s.current_title) if s.current_title else ""
            if family:
                title_families[family] = title_families.get(family, 0) + 1

        if title_families:
            top_family = max(title_families, key=title_families.get)
            top_ratio = title_families[top_family] / len(snippets)
            signals["title_cluster"] = {
                "top_family": top_family,
                "ratio": round(top_ratio, 2),
            }
            if top_ratio >= config.GLANCE_NOISE_TITLE_THRESHOLD:
                # Check if top family matches a known non-fit pattern
                is_noise_title = False
                nb = self.brief_obj._new_brief
                if nb is not None:
                    for nf in nb.non_fit_patterns:
                        nf_lower = [ex.lower() for ex in nf.examples]
                        if any(top_family in ex or ex in top_family for ex in nf_lower):
                            is_noise_title = True
                            break
                        if top_family in nf.label.lower() or top_family in nf.description.lower():
                            is_noise_title = True
                            break
                else:
                    for na in self.brief_obj.noise_archetypes:
                        na_name = na.get("name", "").lower()
                        na_desc = na.get("description", "").lower()
                        na_signals = [s.lower() for s in na.get("signals", [])]
                        if (top_family in na_name or top_family in na_desc
                                or any(top_family in sig or sig in top_family for sig in na_signals)):
                            is_noise_title = True
                            break
                if is_noise_title:
                    signals["title_cluster"]["noise"] = True
                    noise_count += 1

        # --- Signal 2: Keyword scan ---
        key_terms = self._get_glance_key_terms()
        if key_terms:
            hits = 0
            for s in snippets:
                text = " ".join([
                    s.headline or "",
                    s.current_title or "",
                    " ".join(s.experience_entries),
                ]).lower()
                if any(term in text for term in key_terms):
                    hits += 1
            signals["keyword_scan"] = {"hits": hits, "total": len(snippets)}
            if hits <= config.GLANCE_KEYWORD_MISS_THRESHOLD:
                signals["keyword_scan"]["noise"] = True
                noise_count += 1

        # --- Signal 3: Non-fit pattern scan ---
        nb = self.brief_obj._new_brief
        nf_examples: list[str] = []
        if nb is not None:
            for nf in nb.non_fit_patterns:
                nf_examples.extend(ex.lower() for ex in nf.examples)
        else:
            for na in self.brief_obj.noise_archetypes:
                nf_examples.extend(s.lower() for s in na.get("signals", []))

        if nf_examples:
            nf_matches = 0
            for s in snippets:
                text = " ".join([
                    s.headline or "",
                    s.current_title or "",
                    " ".join(s.experience_entries),
                ]).lower()
                if any(ex in text for ex in nf_examples):
                    nf_matches += 1
            nf_ratio = nf_matches / len(snippets) if snippets else 0
            signals["non_fit_scan"] = {
                "matches": nf_matches,
                "total": len(snippets),
                "ratio": round(nf_ratio, 2),
            }
            if nf_ratio > 0.5:
                signals["non_fit_scan"]["noise"] = True
                noise_count += 1

        # --- Decision ---
        if noise_count >= 3:
            titles_summary = ", ".join(
                f"{f} ({c})" for f, c in sorted(title_families.items(), key=lambda x: -x[1])[:5]
            )
            return GlanceResult(
                action="reformulate",
                summary=f"3/3 noise signals. Top titles: {titles_summary}. "
                        f"0/{len(snippets)} keyword hits." if key_terms else f"3/3 noise signals. Top titles: {titles_summary}.",
                confidence=0.9,
                signals=signals,
            )
        elif noise_count == 0:
            return GlanceResult(
                action="proceed",
                summary="No noise signals detected.",
                confidence=0.95,
                signals=signals,
            )
        else:
            # 1-2 signals: use cheap LLM to disambiguate
            llm_verdict = self._glance_llm_check(snippets, signals)
            if llm_verdict == "noise":
                titles_summary = ", ".join(
                    f"{f} ({c})" for f, c in sorted(title_families.items(), key=lambda x: -x[1])[:5]
                )
                return GlanceResult(
                    action="reformulate",
                    summary=f"{noise_count}/3 noise signals + LLM confirms noise. Top titles: {titles_summary}.",
                    confidence=0.7,
                    signals=signals,
                )
            else:
                return GlanceResult(
                    action="proceed",
                    summary=f"{noise_count}/3 noise signals but LLM says proceed.",
                    confidence=0.6,
                    signals=signals,
                )

    def _glance_llm_check(self, snippets: list[CandidateSnippet], signal_details: dict) -> str:
        """Cheap LLM call to disambiguate ambiguous glance signals. Returns 'noise' or 'proceed'."""
        from shared.llm_clients import cheap_llm

        # Format first 10 snippets
        snippet_lines = []
        for s in snippets[:10]:
            company = f" at {s.current_company}" if s.current_company else ""
            snippet_lines.append(f"- {s.name} | {s.current_title}{company} | {s.headline}")
        snippets_text = "\n".join(snippet_lines)

        # Format signal details
        signal_lines = []
        for name, details in signal_details.items():
            if details.get("noise"):
                signal_lines.append(f"  {name}: NOISE — {details}")
            else:
                signal_lines.append(f"  {name}: OK — {details}")
        signals_text = "\n".join(signal_lines)

        system = f"""You are a sourcing quality checker. Decide whether a LinkedIn search results page is hitting the right population or is noise.

Role: {self.brief_obj.role_title}
{self.brief_obj.role_description}

Minimum bar: {self.brief_obj.minimum_bar}

Respond with ONLY the word "noise" or "proceed". Nothing else."""

        user = f"""Here are the first {len(snippets[:10])} search result snippets from this page:
{snippets_text}

Automated signal analysis:
{signals_text}

Is this page mostly noise (wrong population) or does it have plausible candidates? Reply "noise" or "proceed"."""

        try:
            result = cheap_llm(system, user, expect_json=False)
            verdict = result.strip().lower() if isinstance(result, str) else str(result).strip().lower()
            return "noise" if "noise" in verdict else "proceed"
        except Exception as e:
            print(f"    [glance-llm] Error: {e} — defaulting to proceed")
            return "proceed"

    def _format_arch_context(self, architecture: str) -> str:
        """Format architecture context for injection into _page_adapt system prompt."""
        if not architecture:
            return ""

        # Derive expected NO range from brief calibration
        fc = None
        if (self.brief_obj and self.brief_obj.has_v2_schema
                and self.brief_obj._new_brief.facial_calibration):
            fc = self.brief_obj._new_brief.facial_calibration

        if fc:
            expected_no_low = 1.0 - fc.expected_yes_rate_high   # normal floor
            expected_no_high = 1.0 - fc.expected_yes_rate_low    # normal ceiling
        else:
            expected_no_low = 0.45
            expected_no_high = 0.75

        noise_map = {
            "sniper": "low", "dragnet": "high", "titration": "high",
            "negative_space": "medium", "company_first": "medium", "title_first": "low",
        }
        noise_tol = noise_map.get(architecture, "medium")
        if noise_tol == "high":
            return f"""
## Architecture: {architecture}
High noise tolerance. Facial NO rates up to {expected_no_high:.0%} are expected and acceptable for this brief. Only abandon if there is ZERO signal (no saves AND no facial_yes across multiple pages). Paginate through noise."""
        elif noise_tol == "low":
            return f"""
## Architecture: {architecture}
Low noise tolerance. Facial NO rates above {expected_no_high:.0%} suggest the string needs narrowing. Be aggressive about stopping unproductive strings."""
        else:
            return f"""
## Architecture: {architecture}
Medium noise tolerance. Facial NO rates between {expected_no_low:.0%} and {expected_no_high:.0%} are normal for this brief."""

    async def _page_adapt(
        self,
        search_string: SearchString,
        current_boolean: str,
        result_count_text: str,
        all_candidates: list[dict],
        string_stats: dict,
        glance_summary: str | None = None,
        architecture: str = "",
    ) -> str:
        """Two-phase adaptation: scout (page 1 of broad strings) or paginate (ongoing).

        Returns:
            "continue"  — proceed to next page (paginate phase)
            "paginate"  — scout complete, transition to paginate phase
            "stop"      — signal exhausted, move to next string
            "abandon"   — string is fundamentally wrong, skip entirely
            "narrow:<boolean>" — push narrower Boolean onto refinement stack
            "broaden"   — pop last refinement (revert to previous Boolean)
        """
        from shared.llm_clients import opus_llm_cached

        # Build compact candidate summary
        candidate_lines = []
        for c in all_candidates:
            candidate_lines.append(
                f"  p{c['page']} | {c['outcome']:10s} | {c['name']} | {c['title']} at {c['company']} | {c['rationale'][:80]}"
            )
        candidates_text = "\n".join(candidate_lines)

        # Build refinement history for Opus context
        refinement_history = ""
        if search_string.refinement_stack or search_string.original_boolean != current_boolean:
            history_lines = [f"  Original: {search_string.original_boolean[:120]}"]
            for i, b in enumerate(search_string.refinement_stack, 1):
                history_lines.append(f"  Refinement {i}: {b[:120]}")
            history_lines.append(f"  Current (active): {current_boolean[:120]}")
            refinement_history = "\n## Refinement History\n" + "\n".join(history_lines) + "\n"

        is_scout = search_string.phase == "scout"
        can_broaden = len(search_string.refinement_stack) > 0

        # Derive expected NO range from brief calibration for triage awareness notes
        fc = None
        if (self.brief_obj and self.brief_obj.has_v2_schema
                and self.brief_obj._new_brief.facial_calibration):
            fc = self.brief_obj._new_brief.facial_calibration
        if fc:
            expected_no_low = 1.0 - fc.expected_yes_rate_high
            expected_no_high = 1.0 - fc.expected_yes_rate_low
        else:
            expected_no_low = 0.45
            expected_no_high = 0.75

        triage_note = f"- IMPORTANT: Facial triage is intentionally strict — ambiguity defaults to NO. A high facial NO rate ({expected_no_low:.0%}-{expected_no_high:.0%}) is EXPECTED and normal for this brief. Only consider a string unproductive when SAVES dry up, not when facial NO is high. High facial NO + occasional saves = healthy string under strict triage."

        # Phase-specific action menu
        if is_scout:
            actions_section = f"""Choose ONE action:

1. "paginate" — Page 1 shows good signal. Commit to paginating this Boolean deeper.
2. "narrow" — Too broad/noisy. Add AND clauses to focus the search. Provide a modified Boolean that narrows from the current one.
3. "abandon" — Fundamentally wrong results (wrong domain, wrong seniority band, mostly noise). Skip this string entirely.

## How a sourcer thinks about scout phase
- This is page 1 — the BEST results LinkedIn will show. If page 1 is mostly noise, deeper pages will be worse.
- A high result count (3K+) means the Boolean is broad. That's fine IF page 1 quality is good.
- If you see 1-2 saves or strong facial YES candidates on page 1, the string has promise — paginate.
- If page 1 is dominated by wrong-domain, wrong-seniority, or irrelevant profiles, narrow or abandon.
- When narrowing, add AND terms to exclude the dominant noise pattern. Be specific about which terms you're adding and why.
- Abandon is for strings where the core concept is wrong, not just noisy. Prefer narrow when the signal exists but is buried.
{triage_note}"""
        else:
            broaden_text = ""
            if can_broaden:
                broaden_text = f"""
5. "broaden" — The last narrowing was too aggressive or cut off good candidates. Revert to the previous Boolean (pop the last refinement). The refinement stack has {len(search_string.refinement_stack)} level(s) — you can broaden {len(search_string.refinement_stack)} time(s)."""

            actions_section = f"""Choose ONE action:

1. "continue" — The search is producing useful signal. Move to the next page.
2. "narrow" — The search is getting noisy. Add AND clauses to focus. Provide a modified Boolean. This pushes the current query onto a stack so it can be reversed later.
3. "stop" — Signal exhausted, only noise/duplicates remain. Move to the next search string.
4. "abandon" — The string is fundamentally unproductive. Skip entirely.{broaden_text}

## How a sourcer thinks about pagination
- SAVES are the primary metric, but Facial YES also matters — it means the profile looked promising enough to open.
- A string producing many Facial YES but few saves may mean the evaluation criteria are too strict, not that the string is unproductive. Consider this before abandoning.
- Save rate below ~3% across 3+ pages suggests signal may be thinning. But weigh this against Facial YES rate — high facial pass with low save rate is a calibration signal, not a string quality signal.
- When saves or strong Facial YES appeared recently (last 1-2 pages), keep going. When both dry up for 2+ pages, stop or narrow.
- When narrowing, prefer adding AND terms to the current Boolean rather than rewriting.
- Broaden ONLY when a recent narrowing clearly went too far (e.g., zero results, or cut off a category of good candidates).
- Duplicates are expected and not a problem unless >30%.
{triage_note}"""

        system = f"""You are a senior sourcing strategist monitoring a live LinkedIn Recruiter search.

Role: {self.brief_obj.role_title}
{self.brief_obj.role_description}

## Minimum Bar
{self.brief_obj.minimum_bar}

## IMPORTANT: Strings are nets, not archetype filters
Each Boolean string surfaces candidates for the ENTIRE role — any archetype, any combination of archetypes.
A string built from post-training vocabulary might surface a STEM reasoning engineer or an RL environment builder.
Judge string productivity by total saves and facial YES rates across ALL archetypes, not just one.

## Current Phase: {"SCOUT (page 1 exploration)" if is_scout else "PAGINATE (deep pagination)"}
{self._format_arch_context(architecture)}
{actions_section}

## LinkedIn Boolean Rules (MANDATORY when writing refined Booleans)
- LinkedIn does NOT stem: "model" ≠ "models" — include all morphological variants as separate OR terms
- LinkedIn IS substring-embedded: "reward model" matches "reward model development" — never add superstrings
- LinkedIn IS case-insensitive: never add case-only variants
- Bare ambiguous terms MUST be qualified: "agent" → "AI agent", "alignment" → "AI alignment"
- Abbreviations with common non-domain meanings must include spelled-out form
- Tool/library names are proper nouns — do not fabricate compound expansions

Return JSON only:
- "action": the chosen action
- "rationale": Detailed explanation including: (1) what patterns you see in the candidates, (2) save rate analysis, (3) if narrowing, what specific terms you're adding/removing and why, (4) if broadening, why the last narrowing was too aggressive
- "refined_boolean": The new Boolean string (required if action is "narrow", null otherwise)"""

        user_prompt = f"""## Current Boolean
{current_boolean}

## Result Count
{result_count_text}
{refinement_history}
{f"""## Glance Assessment (page was NOT individually evaluated)
This page was assessed via fast glance and found to be likely noise.
Candidates were NOT individually evaluated — the signals are from search result snippets only.
Glance summary: {glance_summary}

Because this page was glance-skipped, the stats below reflect only previously-evaluated pages.
This is strong evidence the current Boolean is hitting the wrong population.

""" if glance_summary else ""}## Accumulated Stats (across {string_stats['pages']} page(s))
- Candidates evaluated: {string_stats['candidates']}
- Duplicates skipped: {string_stats['duplicates']}
- SAVES: {string_stats['saves']}
- REJECTS (opened profile, then rejected): {string_stats['rejects']}
- Facial YES (opened for full review): {string_stats['facial_yes']}
- Facial NO (skipped from preview): {string_stats['facial_no']}
- Facial SKIP (API/parse errors): {string_stats.get('facial_skip', 0)}
- Save rate: {string_stats['saves'] / max(string_stats['candidates'], 1) * 100:.1f}%

## All Candidates So Far
{candidates_text}

What next?"""

        try:
            result = opus_llm_cached(system, user_prompt, expect_json=True)
            action = result.get("action", "continue")
            rationale = result.get("rationale", "")
            print(f"  [adapt] Opus ({search_string.phase}): {action} — {rationale}")
            log_event(self.log_path, "page_adapt", string_id=search_string.id,
                      page=string_stats["pages"], phase=search_string.phase,
                      action=action, rationale=rationale,
                      refinement_depth=len(search_string.refinement_stack))

            if action == "narrow":
                new_boolean = result.get("refined_boolean", "")
                if not new_boolean:
                    print(f"  [adapt] No refined Boolean provided — continuing.")
                    return "continue" if not is_scout else "paginate"
                return f"narrow:{new_boolean}"
            elif action == "broaden":
                if not can_broaden:
                    print(f"  [adapt] Broaden requested but no refinement stack — continuing.")
                    return "continue"
                return "broaden"
            elif action == "abandon":
                return "abandon"
            elif action == "stop":
                return "stop"
            elif action == "paginate":
                return "paginate"
            else:
                return "continue"
        except Exception as e:
            print(f"  [adapt] Adaptation call failed ({e}) — continuing.")
            return "continue" if not is_scout else "paginate"

    async def _force_narrow_adapt(
        self,
        search_string: SearchString,
        current_boolean: str,
        result_count_text: str,
        all_candidates: list[dict],
        string_stats: dict,
    ) -> str | None:
        """Called when abandon/stop is blocked by min-pages. Forces Opus to attempt a narrow.

        Returns:
            "narrow:<boolean>" if Opus provides a narrowed Boolean, None if it can't.
        """
        from shared.llm_clients import opus_llm_cached

        candidate_lines = []
        for c in all_candidates:
            candidate_lines.append(
                f"  p{c['page']} | {c['outcome']:10s} | {c['name']} | {c['title']} at {c['company']} | {c['rationale'][:80]}"
            )
        candidates_text = "\n".join(candidate_lines)

        system = f"""You are a senior sourcing strategist. Your previous recommendation to abandon this search was blocked because minimum pagination requirements haven't been met.

Role: {self.brief_obj.role_title}
{self.brief_obj.role_description}

## Minimum Bar
{self.brief_obj.minimum_bar}

## Your task
Instead of abandoning, you MUST provide a narrowed Boolean that filters out the dominant noise pattern. The current string has {result_count_text} results — there may be signal buried under noise if you add the right AND clauses.

Analyze the candidate outcomes below and identify the dominant noise pattern (wrong domain? wrong seniority? wrong function?). Then add AND terms to exclude that noise.

## LinkedIn Boolean Rules (MANDATORY)
- LinkedIn does NOT stem: "model" ≠ "models" — include all morphological variants
- LinkedIn IS substring-embedded: "reward model" matches "reward model development"
- LinkedIn IS case-insensitive
- Bare ambiguous terms MUST be qualified

Return JSON:
- "action": must be "narrow"
- "rationale": What noise pattern you identified and what AND terms you're adding to exclude it
- "refined_boolean": The narrowed Boolean string"""

        user_prompt = f"""## Current Boolean
{current_boolean}

## Result Count
{result_count_text}

## Stats ({string_stats['pages']} pages)
- Candidates: {string_stats['candidates']} | Saves: {string_stats['saves']} | Facial YES: {string_stats['facial_yes']} | Facial NO: {string_stats['facial_no']}

## Candidates
{candidates_text}

Provide a narrowed Boolean."""

        try:
            result = opus_llm_cached(system, user_prompt, expect_json=True)
            new_boolean = result.get("refined_boolean", "")
            rationale = result.get("rationale", "")
            if new_boolean:
                print(f"  [adapt] Forced narrow: {rationale}")
                log_event(self.log_path, "forced_narrow", string_id=search_string.id,
                          rationale=rationale, new_boolean=new_boolean[:100])
                return f"narrow:{new_boolean}"
            else:
                print(f"  [adapt] Forced narrow returned no Boolean — honoring abandon.")
                return None
        except Exception as e:
            print(f"  [adapt] Forced narrow failed ({e}) — honoring abandon.")
            return None

    async def _evaluate_snippet(
        self,
        snippet: CandidateSnippet,
        page_report: _PageReport | None = None,
        search_string: SearchString | None = None,
    ) -> Optional[OpusDecision]:
        """Run snippet through facial judgment -> full profile -> final judgment."""
        runtime_search_string = search_string or SearchString(
            id=snippet.source_string_id,
            name=snippet.source_string_name,
            boolean="",
        )
        facial_attempt_id: int | None = None

        # --- Employer blacklist check (no LLM call) ---
        if self.brief_obj.employer_blacklist and snippet.current_company:
            company_lower = snippet.current_company.lower()
            for blocked in self.brief_obj.employer_blacklist:
                if blocked.lower() in company_lower:
                    print(f"    [BLACKLIST] {snippet.name} — current employer '{snippet.current_company}' matches '{blocked}'")
                    self.stats.setdefault("blacklist_skips", 0)
                    self.stats["blacklist_skips"] += 1
                    if page_report:
                        page_report.add_skip_preview(snippet.name, f"BLACKLIST: {blocked}")
                    blacklist_decision = OpusDecision(
                        stage="facial", decision="FACIAL_NO", path="employer_blacklist",
                        confidence=1.0, rationale=f"Employer blacklist: {blocked}",
                        candidate_name=snippet.name, profile_url=snippet.profile_url,
                    )
                    facial_attempt_id = self._start_runtime_stage_attempt(
                        search_string=runtime_search_string,
                        snippet=snippet,
                        stage="facial",
                    )
                    self._finish_runtime_stage_success(
                        attempt_id=facial_attempt_id,
                        stage="facial",
                        snippet=snippet,
                        decision=blacklist_decision,
                    )
                    self._prior_outcomes[snippet.profile_url] = "FACIAL_NO"
                    self._mark_terminal(snippet.profile_url)
                    return blacklist_decision

        # --- Facial judgment (Opus) ---
        print(f"    Facial judgment (Opus)...")
        facial_attempt_id = self._start_runtime_stage_attempt(
            search_string=runtime_search_string,
            snippet=snippet,
            stage="facial",
        )
        try:
            facial = facial_judge(snippet, self.brief_obj, prompt_prefix=self._tightening_prefix)
        except Exception as e:
            print(f"    [ERROR] Facial judgment failed: {e}")
            log_event(self.log_path, "facial_error", name=snippet.name, error=str(e))
            facial = judgment_failure_decision(
                stage="facial",
                candidate_name=snippet.name,
                profile_url=snippet.profile_url,
                error=e,
                source="judgment",
            )

        # Intercept parse/judgment failures — log but do NOT persist to cross-session history
        if is_failure_decision(facial.decision):
            print(f"    [PARSE_FAILURE] {facial.rationale}")
            self.stats.setdefault("parse_failures", 0)
            self.stats["parse_failures"] += 1
            if self._bias_monitor:
                self._bias_monitor.record_decision(DecisionRecord(
                    candidate_id=f"{snippet.source_string_id}_p{snippet.page}_r{snippet.result_rank}",
                    string_id=str(snippet.source_string_id),
                    stage="facial",
                    decision=facial.decision,
                    confidence=facial.confidence,
                    capability_area=None,
                ))
            # Non-terminal: allow retry later in this session or on resume
            self._finish_runtime_failure_decision(
                attempt_id=facial_attempt_id,
                snippet=snippet,
                decision=facial,
            )
            self._in_flight_urls.discard(snippet.profile_url)
            return facial

        self._prior_outcomes[snippet.profile_url] = facial.decision
        self._mark_terminal(snippet.profile_url)
        self._finish_runtime_stage_success(
            attempt_id=facial_attempt_id,
            stage="facial",
            snippet=snippet,
            decision=facial,
        )

        # Record facial decision for bias monitoring
        if self._bias_monitor:
            self._bias_monitor.record_decision(DecisionRecord(
                candidate_id=f"{snippet.source_string_id}_p{snippet.page}_r{snippet.result_rank}",
                string_id=str(snippet.source_string_id),
                stage="facial",
                decision=facial.decision,
                confidence=facial.confidence,
                capability_area=None,
            ))
            # Check if triage should be tightened for this string
            if not self._triage_tightened:
                tightening = self._bias_monitor.get_tightening_status(str(snippet.source_string_id))
                if tightening:
                    self._triage_tightened = True
                    self._tightening_prefix = (
                        f"⚠ TRIAGE TIGHTENING ACTIVE: The facial YES rate on this search string is running "
                        f"{tightening['actual_rate']:.0%}, which is {tightening['multiplier']:.1f}x above the expected "
                        f"maximum of {tightening['expected_high']:.0%}. Apply stricter filtering: require TWO strong "
                        f"positive signals for FACIAL_YES instead of one. Generic seniority + AI keywords is insufficient. "
                        f"Example of insufficient: 'VP of Digital Transformation at Accenture' — senior title + consulting firm "
                        f"mentioning AI, but no specific ML/data work visible. Example of sufficient: 'ML Engineer at DeepMind' "
                        f"+ 'Research Scientist at Google Brain' — two positions with direct capability area connections.\n\n"
                    )
                    print(f"    [bias] Tightening facial criteria for remaining candidates on this string "
                          f"(YES rate: {tightening['actual_rate']:.0%}, expected max: {tightening['expected_high']:.0%})")

        if facial.decision in ("FACIAL_NO", "FACIAL_SKIP"):
            tag = "FACIAL_NO" if facial.decision == "FACIAL_NO" else "FACIAL_SKIP"
            print(f"    [{tag}] {facial.rationale}")
            if facial.decision == "FACIAL_NO":
                self.stats["facial_no"] += 1
            else:
                self.stats.setdefault("facial_skip", 0)
                self.stats["facial_skip"] += 1
            if page_report:
                page_report.add_skip_preview(snippet.name, f"{tag}: {facial.rationale}")
            return facial

        print(f"    [FACIAL_YES] {facial.rationale}")
        self.stats["facial_yes"] += 1

        return await self._full_evaluate(snippet, page_report, runtime_search_string)

    async def _full_evaluate(
        self,
        snippet: CandidateSnippet,
        page_report: "_PageReport | None" = None,
        search_string: SearchString | None = None,
    ) -> Optional[OpusDecision]:
        """Open profile, extract, and run full evaluation. Called after facial triage passes."""
        runtime_search_string = search_string or SearchString(
            id=snippet.source_string_id,
            name=snippet.source_string_name,
            boolean="",
        )
        full_attempt_id = self._start_runtime_stage_attempt(
            search_string=runtime_search_string,
            snippet=snippet,
            stage="full",
        )

        try:
            self._ensure_services()
            acquisition = await self._acquisition_service.extract_profile_summary(snippet)
            summary = acquisition.profile_summary
        except GovernorLimitReached:
            raise
        except Exception as e:
            if _is_browser_disconnect_error(e):
                print(f"    [ERROR] Browser session dropped during profile extraction: {e}")
                log_event(self.log_path, "profile_browser_disconnect", name=snippet.name, error=str(e))
                raise
            print(f"    [ERROR] Profile extraction failed: {e}")
            log_event(self.log_path, "profile_error", name=snippet.name, error=str(e))
            self._finish_runtime_stage_failure(
                attempt_id=full_attempt_id,
                snippet=snippet,
                error=e,
                payload={"profile_extraction_failed": True},
            )
            try:
                await self.browser.go_back_to_results()
            except Exception:
                pass
            return judgment_failure_decision(
                stage="full",
                candidate_name=snippet.name,
                profile_url=snippet.profile_url,
                error=e,
                source="profile_extraction",
            )

        # --- Final judgment (Opus) ---
        print(f"    Final judgment (Opus)...")
        try:
            final = full_judge(summary, self.brief_obj)
        except Exception as e:
            print(f"    [ERROR] Final judgment failed: {e}")
            log_event(self.log_path, "final_error", name=snippet.name, error=str(e))
            final = judgment_failure_decision(
                stage="full",
                candidate_name=snippet.name,
                profile_url=snippet.profile_url,
                error=e,
                source="judgment",
            )

        # Intercept parse/judgment failures — do NOT persist to cross-session history
        if is_failure_decision(final.decision):
            print(f"    [{final.decision}] {final.rationale}")
            self.stats.setdefault("parse_failures", 0)
            self.stats["parse_failures"] += 1
            if self._bias_monitor:
                self._bias_monitor.record_decision(DecisionRecord(
                    candidate_id=f"{snippet.source_string_id}_p{snippet.page}_r{snippet.result_rank}",
                    string_id=str(snippet.source_string_id),
                    stage="full",
                    decision=final.decision,
                    confidence=final.confidence,
                    capability_area=None,
                ))
            # Non-terminal: allow same-session retry if candidate appears again
            self._finish_runtime_failure_decision(
                attempt_id=full_attempt_id,
                snippet=snippet,
                decision=final,
                payload={"profile_summary": summary.to_dict()},
            )
            self._in_flight_urls.discard(snippet.profile_url)
            try:
                await self.browser.go_back_to_results()
                await asyncio.sleep(human_delay_correlated(0.8, channel="panel_close"))
            except Exception:
                final._panel_stuck = True
            return final

        self._prior_outcomes[snippet.profile_url] = final.decision
        self._mark_terminal(snippet.profile_url)
        self._finish_runtime_stage_success(
            attempt_id=full_attempt_id,
            stage="full",
            snippet=snippet,
            decision=final,
            profile_summary=summary,
        )

        # Record full eval decision and check bias alerts
        if self._bias_monitor:
            self._bias_monitor.record_decision(DecisionRecord(
                candidate_id=f"{snippet.source_string_id}_p{snippet.page}_r{snippet.result_rank}",
                string_id=str(snippet.source_string_id),
                stage="full",
                decision=final.decision,
                confidence=final.confidence,
                capability_area=final.path if final.path != "none" else None,
            ))
            alerts = self._bias_monitor.check_alerts(str(snippet.source_string_id))
            for alert in alerts:
                if alert.severity == "pause":
                    print(f"\n    ⚠ BIAS PAUSE: {alert.message}")
                    log_event(self.log_path, "bias_alert", severity="pause",
                              alert_type=alert.alert_type, message=alert.message,
                              string_id=alert.string_id)
                elif alert.severity == "flag":
                    print(f"    ⚡ BIAS FLAG: {alert.message}")
                    log_event(self.log_path, "bias_alert", severity="flag",
                              alert_type=alert.alert_type, message=alert.message,
                              string_id=alert.string_id)
                elif alert.severity == "info":
                    print(f"    ℹ BIAS INFO: {alert.message}")

        if final.decision in ("SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE"):
            tag = final.decision if final.decision in ("INFERENTIAL_SAVE", "TRANSFERABLE_SAVE") else "SAVE"
            print(f"    [{tag}] {final.rationale}")
            self.stats["save_attempts"] += 1
            await self._side_effects_service.handle_save_decision(
                snippet=snippet,
                runtime_search_string=runtime_search_string,
                attempt_id=full_attempt_id,
            )

            if page_report:
                page_report.add_saved(snippet, final)
        else:
            print(f"    [REJECT] {final.rationale}")
            self.stats["rejected"] += 1
            if page_report:
                page_report.add_skipped_opened(snippet, final)
            # Quick exit — saw enough, moving on
            reject_dwell = max(0.2, min(2.0, human_delay_correlated(0.5, channel="reject_close")))
            await asyncio.sleep(reject_dwell)
            print(f"    [profile-read] REJECT verdict → closing in {reject_dwell:.1f}s")

        try:
            await self.browser.go_back_to_results()
            await asyncio.sleep(human_delay_correlated(0.8, channel="panel_close"))
        except Exception as e:
            if _is_browser_disconnect_error(e):
                print(f"    [ERROR] Browser session dropped while closing profile: {e}")
                log_event(self.log_path, "panel_close_browser_disconnect", name=snippet.name, error=str(e))
                raise
            print(f"    [ERROR] go_back_to_results failed: {e} — panel may still be open")
            log_event(self.log_path, "go_back_error", name=snippet.name, error=str(e))
            # Tag the result so the page loop knows state is corrupted
            final._panel_stuck = True

        return final

    # ------------------------------------------------------------------
    # Full run: build execution order from strategy
    # ------------------------------------------------------------------

    def _build_ordered_search_strings(self) -> list[SearchString]:
        """Build execution queue from Opus-generated compound strings only.

        Kit strings are vocabulary — they NEVER appear in the execution queue.
        Only generated compounds and coverage gap strings are queued.
        Strings are assigned to blocks of ~5 so block-level adaptation triggers mid-run.
        """
        next_id = 1
        ordered: list[SearchString] = []
        batch_size = 5

        if not self._execution_plan:
            return ordered

        # --- Generated compound strings (in priority order from Opus) ---
        compound_idx = 0
        for gs in self._execution_plan.generated_strings:
            boolean = gs.get("boolean", "")
            if not boolean:
                continue
            compound_idx += 1
            batch_num = (compound_idx - 1) // batch_size + 1
            rationale = gs.get("rationale", "")
            ss = SearchString(
                id=next_id,
                name=f"Compound / {rationale[:60]}" if rationale else "Compound",
                boolean=boolean,
                block=f"Compound Batch {batch_num}",
                subblock="Compound",
                string_type="Precision",
                family_key=gs.get("family_key", ""),
                novelty_bucket=gs.get("novelty_bucket", ""),
                domain_lane=gs.get("domain_lane", ""),
            )
            ordered.append(ss)
            next_id += 1

        compound_count = len(ordered)

        # --- Coverage gap strings ---
        for gap in self._execution_plan.coverage_gaps:
            boolean = gap.get("suggested_boolean")
            if not boolean:
                continue
            gap_desc = gap.get("gap", "coverage gap")
            ss = SearchString(
                id=next_id,
                name=f"Coverage Gap / {gap_desc[:60]}",
                boolean=boolean,
                block="Coverage Gaps",
                subblock="Coverage Gap",
                string_type="Recall",
                family_key=gap.get("family_key", ""),
                novelty_bucket=gap.get("novelty_bucket", ""),
                domain_lane=gap.get("domain_lane", ""),
            )
            ordered.append(ss)
            next_id += 1

        gap_count = len(ordered) - compound_count
        print(f"  {compound_count} compound strings + {gap_count} coverage gap strings queued")

        return ordered

    # ------------------------------------------------------------------
    # Block aggregate statistics (for architecture evaluation)
    # ------------------------------------------------------------------

    def _compute_block_aggregate(self, block_strings: list[SearchString]) -> str:
        """Compute cross-string aggregate statistics for architecture evaluation."""
        total_facial_no = sum(s.facial_no_count for s in block_strings)
        total_facial_yes = sum(s.facial_yes_count for s in block_strings)
        total_seen = total_facial_no + total_facial_yes
        total_saves = sum(len(s.saves) for s in block_strings)
        total_duplicates = sum(s.duplicates_count for s in block_strings)
        edge_case_saves = sum(
            len(s.saves) for s in block_strings if s.novelty_bucket == "edge_case"
        )
        canonical_saves = sum(
            len(s.saves) for s in block_strings if s.novelty_bucket == "canonical"
        )

        facial_no_rate = total_facial_no / total_seen if total_seen else 0
        save_rate = total_saves / total_facial_yes if total_facial_yes else 0

        strings_below_20 = sum(1 for s in block_strings if s.result_count < 20)

        lines = [
            "## Block Aggregate Statistics",
            f"- Candidates seen (facial triage): {total_seen}",
            f"- Passed facial triage: {total_facial_yes}",
            f"- Facial NO rate: {facial_no_rate:.1%}",
            f"- Saves: {total_saves}",
            f"- Save rate (per evaluated): {save_rate:.1%}",
            f"- Duplicates skipped: {total_duplicates}",
            f"- Novelty mix: edge_case={edge_case_saves}, canonical={canonical_saves}",
            f"- Strings with <20 results: {strings_below_20}/{len(block_strings)}",
        ]

        return "\n".join(lines)

    def _load_profile_index_for_adaptation(self) -> dict[str, dict]:
        """Index saved profile summaries by normalized candidate name."""
        if not self.profiles_path.exists():
            return {}

        index: dict[str, dict] = {}
        for entry in read_jsonl(self.profiles_path):
            key = _normalize_candidate_name_key(entry.get("name", ""))
            if key and key not in index:
                index[key] = entry
        return index

    def _saved_profile_snapshots(
        self,
        saved_names: list[str],
        profile_index: dict[str, dict],
    ) -> list[dict]:
        """Small LinkedIn-facing snapshots so adaptation can judge novelty, not just counts."""
        snapshots: list[dict] = []
        seen: set[str] = set()

        for name in saved_names:
            key = _normalize_candidate_name_key(name)
            if not key or key in seen:
                continue
            entry = profile_index.get(key)
            if not entry:
                continue
            seen.add(key)
            current = (entry.get("experiences") or [{}])[0] or {}
            snapshots.append(
                {
                    "name": entry.get("name", name),
                    "title": current.get("title", ""),
                    "company": current.get("company", ""),
                    "headline": entry.get("headline", ""),
                }
            )

        return snapshots

    # ------------------------------------------------------------------
    # Full run: block-level adaptation
    # ------------------------------------------------------------------

    async def _run_block_adaptation(
        self,
        block_name: str,
        block_strings: list[SearchString],
        progress: Progress,
        adapt_fn,
    ) -> None:
        """After a batch of strings completes, send summary to Opus and apply adaptations."""
        print(f"\n{'═' * 60}")
        print(f"  Adaptation checkpoint (after {len(block_strings)} strings)")
        print(f"{'═' * 60}")

        profile_index = self._load_profile_index_for_adaptation()
        for search_string in block_strings:
            self._hydrate_search_string_metadata(search_string)

        # Build block report
        strings_with_saves = [s for s in block_strings if s.saves]
        report = BlockReport(
            block_name=block_name,
            strings_run=len(block_strings),
            strings_with_saves=len(strings_with_saves),
            total_results=sum(s.result_count for s in block_strings if s.result_count > 0),
            total_saves=sum(len(s.saves) for s in block_strings),
            top_performers=[
                {
                    "string_id": s.id,
                    "name": s.name,
                    "saves": len(s.saves),
                    "results": s.result_count,
                    "family_key": s.family_key,
                    "novelty_bucket": s.novelty_bucket,
                    "domain_lane": s.domain_lane,
                }
                for s in sorted(strings_with_saves, key=lambda x: len(x.saves), reverse=True)[:3]
            ],
            zero_save_string_ids=[s.id for s in block_strings if not s.saves],
            string_details=[
                {
                    "string_id": s.id,
                    "name": s.name,
                    "boolean": s.boolean,
                    "original_boolean": s.original_boolean or s.boolean,
                    "result_count": s.result_count,
                    "pages_reviewed": s.pages_reviewed,
                    "candidates": s.candidates_count,
                    "duplicates": s.duplicates_count,
                    "saves": len(s.saves),
                    "save_names": s.saves[:5],
                    "saved_profiles": self._saved_profile_snapshots(s.saves[:5], profile_index),
                    "facial_yes": s.facial_yes_count,
                    "facial_no": s.facial_no_count,
                    "family_key": s.family_key,
                    "novelty_bucket": s.novelty_bucket,
                    "domain_lane": s.domain_lane,
                    "notes": s.notes,
                }
                for s in block_strings
            ],
        )

        print(f"  {report.to_summary_text()}")
        self._update_search_memory_from_block(block_strings)

        # Get remaining unexecuted search strings
        remaining = [s for s in progress.strings if s.status == "queued"]
        for search_string in remaining:
            self._hydrate_search_string_metadata(search_string)

        if not remaining:
            self._clear_pending_block_adaptation(progress)
            self._checkpoint_progress(progress)
            print("  No remaining strings — skipping adaptation.")
            return

        try:
            block_aggregate = self._compute_block_aggregate(block_strings)

            adaptation = adapt_fn(
                self.brief_obj, report, remaining,
                kit_vocabulary=self._kit_strings,
                execution_plan=self._execution_plan,
                pivot_count=progress.pivot_count,
                block_aggregate=block_aggregate,
                search_memory_summary=build_search_memory_summary(self._search_memory),
            )

            # Apply adaptations
            if adaptation.skip_remaining:
                skip_ids = {s["string_id"] for s in adaptation.skip_remaining}
                for ss in progress.strings:
                    if ss.id in skip_ids and ss.status == "queued":
                        ss.status = "skipped"
                        ss.notes = f"Skipped by adaptation: {next((s['reason'] for s in adaptation.skip_remaining if s['string_id'] == ss.id), '')}"
                        print(f"    [adapt] Skipping #{ss.id}: {ss.notes}")

            inserted_ids: set[int] = set()

            if adaptation.new_strings:
                max_id = max(s.id for s in progress.strings) if progress.strings else 0
                # Insert adaptive strings at front of queue (before first queued string)
                insert_idx = next(
                    (i for i, s in enumerate(progress.strings) if s.status == "queued"),
                    len(progress.strings),
                )
                for ns in adaptation.new_strings:
                    max_id += 1
                    new_ss = SearchString(
                        id=max_id,
                        name=f"Adaptive / {ns.get('rationale', 'new')}",
                        boolean=ns["boolean"],
                        block=block_name,
                        string_type="Adaptive",
                        family_key=ns.get("family_key", ""),
                        novelty_bucket=ns.get("novelty_bucket", ""),
                        domain_lane=ns.get("domain_lane", ""),
                    )
                    self._hydrate_search_string_metadata(new_ss)
                    progress.strings.insert(insert_idx, new_ss)
                    inserted_ids.add(max_id)
                    insert_idx += 1
                    print(f"    [adapt] Inserted new string #{max_id} (next in queue): {ns['boolean'][:60]}...")

            if adaptation.reorder:
                for ro in adaptation.reorder:
                    sid = ro["string_id"]
                    for i, ss in enumerate(progress.strings):
                        if ss.id == sid and ss.status == "queued":
                            progress.strings.pop(i)
                            if ro.get("move_to") == "next":
                                # Find first queued string and insert before it
                                for j, ss2 in enumerate(progress.strings):
                                    if ss2.status == "queued":
                                        progress.strings.insert(j, ss)
                                        break
                                else:
                                    progress.strings.append(ss)
                            else:
                                progress.strings.append(ss)
                            print(f"    [adapt] Reordered #{sid} to {ro.get('move_to', 'last')}")
                            break

            if adaptation.noise_updates:
                for nu in adaptation.noise_updates:
                    print(f"    [adapt] Noise update: {nu['term']} → {nu['status']}: {nu.get('note', '')}")
                    if nu['status'] in ("confirmed_noise", "confirmed_signal"):
                        append_jsonl(self.noise_path, {
                            "term": nu.get("term", ""),
                            "status": nu["status"],
                            "note": nu.get("note", ""),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

            # Architecture pivot handling
            if adaptation.pivot_to_architecture:
                # Titration gets 2 pivots (recon-then-commit is its design), others get 1
                max_pivots = 2 if (self._execution_plan and
                                   self._execution_plan.original_architecture == "titration") else 1

                if progress.pivot_count < max_pivots:
                    old_arch = self._execution_plan.architecture if self._execution_plan else "unknown"
                    new_arch = adaptation.pivot_to_architecture
                    print(f"\n  {'!' * 40}")
                    print(f"  ARCHITECTURE PIVOT: {old_arch} → {new_arch}")
                    print(f"  Rationale: {adaptation.pivot_rationale}")
                    print(f"  {'!' * 40}")

                    if self._execution_plan:
                        self._execution_plan.architecture = new_arch
                        self._execution_plan.architecture_rationale = adaptation.pivot_rationale
                        write_json(self.output_dir / "execution_plan.json", self._execution_plan.to_dict())

                    # Clear remaining queued strings but keep the replacement strings
                    # we just injected for the new architecture.
                    for ss in progress.strings:
                        if ss.status == "queued" and ss.id not in inserted_ids:
                            ss.status = "skipped"
                            ss.notes = f"Skipped by architecture pivot: {old_arch} → {new_arch}"

                    progress.pivot_count += 1
                    log_event(self.log_path, "architecture_pivot",
                              old=old_arch, new=new_arch,
                              rationale=adaptation.pivot_rationale, block=block_name)
                else:
                    print(f"  [adapt] Pivot to {adaptation.pivot_to_architecture} recommended "
                          f"but max pivots ({max_pivots}) reached — ignoring.")
                    log_event(self.log_path, "pivot_blocked", reason="max_pivots_reached",
                              recommended=adaptation.pivot_to_architecture)

            self._clear_pending_block_adaptation(progress)
            self._checkpoint_progress(progress)
            log_event(self.log_path, "block_adaptation", block=block_name, report=report.to_dict())

        except Exception as e:
            print(f"  [warn] Adaptation failed: {e} — continuing without adaptation")
            log_event(self.log_path, "adaptation_error", block=block_name, error=str(e))

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------

    def _run_preflight_v2(self) -> None:
        """Run V2 structured preflight: Opus answers specific questions → V2 brief JSON.

        Generates a V2-compatible brief from the JD, saves it, and reloads the brief
        so the pipeline uses structural templates + bias controls instead of freeform archetypes.
        """
        from shared.preflight_v2 import generate_preflight_prompt, parse_preflight_response, preflight_to_brief_json
        from shared.llm_clients import opus_llm
        import sys

        jd_text = self.brief_obj.jd_text
        geography = self.brief_obj.permanent_filters.get("Location", "")

        prompt = generate_preflight_prompt(jd_text, geography or None)
        print("  Preflight V2... (Opus generating structured eval criteria from JD)")

        try:
            raw_response = opus_llm(
                "You are generating structured evaluation criteria for an autonomous sourcing agent. "
                "Respond with ONLY the JSON object requested. No preamble.",
                prompt,
                expect_json=False,
                max_tokens=16384,
            )
            preflight_data = parse_preflight_response(raw_response)
        except Exception as e:
            print(f"  [warn] Preflight V2 failed ({e}) — falling back to old preflight", file=sys.stderr)
            from shared.preflight import run_preflight, apply_preflight_to_brief
            preflight_result = run_preflight(
                jd_text=jd_text,
                intake_notes=self.brief_obj.intake_notes,
                instructions=self.brief_obj.instructions or None,
                existing_archetypes=self.brief_obj.archetypes or None,
                existing_minimum_bar=self.brief_obj.minimum_bar,
            )
            apply_preflight_to_brief(self.brief_obj, preflight_result)
            init_judger(self.brief_obj)
            if preflight_result:
                write_json(self.output_dir / "preflight_output.json", preflight_result)
            return

        # Apply overrides from the brief's existing fields
        overrides = {}
        if self.brief_obj.linkedin_project:
            overrides["linkedin_project"] = self.brief_obj.linkedin_project
        if geography:
            overrides["geography"] = geography
        if self.brief_obj.kit_url:
            overrides["kit_url"] = self.brief_obj.kit_url
        if self.brief_obj.employer_blacklist:
            overrides["employer_blacklist"] = self.brief_obj.employer_blacklist

        brief_json = preflight_to_brief_json(preflight_data, overrides)

        # Save the generated V2 brief for operator review and debugging
        generated_path = self.output_dir / "preflight_v2_brief.json"
        write_json(str(generated_path), brief_json)
        print(f"  Preflight V2 brief saved to: {generated_path}")
        print(f"  Capability areas: {len(brief_json.get('capability_areas', []))}")
        print(f"  Non-fit patterns: {len(brief_json.get('non_fit_patterns', []))}")

        # Reload as a V2 brief
        from shared.brief_loader import _load_v2_brief
        self.brief_obj = _load_v2_brief(brief_json)
        init_judger(self.brief_obj)

        # Initialize bias monitor now that we have a V2 brief
        if self.brief_obj.has_v2_schema:
            self._bias_monitor = BiasMonitor.from_brief(self.brief_obj._new_brief)

        print("  Preflight V2 complete — pipeline will use structural templates + bias controls")

    def _archive_stale_outputs(self) -> None:
        """Rename existing output JSONL files to timestamped backups before a fresh run."""
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        for path in [self.snippets_path, self.facial_path, self.profiles_path, self.final_path]:
            if path.exists() and path.stat().st_size > 0:
                backup = path.with_name(f"{path.stem}-{ts}{path.suffix}")
                path.rename(backup)
                print(f"  Archived {path.name} → {backup.name}")

        # Prune old archives (keep last 5)
        for stem in ["snippets", "facial_judgments", "profile_summaries", "final_judgments"]:
            self._prune_old_archives(stem)

    def _prune_old_archives(self, stem: str, keep: int = 5) -> None:
        """Keep only the N most recent archived versions of a file."""
        pattern = list(self.output_dir.glob(f"{stem}-*.jsonl"))
        # Exclude brief-scoped persistent files (candidate_history-*, noise_discoveries-*, bias_monitor-*)
        archives = sorted(
            [p for p in pattern if not any(p.stem.startswith(pref) for pref in
             ("candidate_history", "noise_discoveries", "bias_monitor"))],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_file in archives[keep:]:
            old_file.unlink()
            print(f"  [cleanup] Removed old archive: {old_file.name}")

    # ------------------------------------------------------------------
    # String restart
    # ------------------------------------------------------------------

    def _restart_string(self, progress: Progress, string_id: int) -> None:
        self._ensure_services()
        self._work_unit_service.restart_string(progress, string_id)

    def _restart_strings(self, progress: Progress, string_ids: list[int]) -> None:
        self._ensure_services()
        self._work_unit_service.restart_strings(progress, string_ids)

    @staticmethod
    def _rewrite_jsonl(path, records: list[dict]) -> None:
        """Rewrite a JSONL file with the given records."""
        with open(path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

    # ------------------------------------------------------------------
    # Progress management
    # ------------------------------------------------------------------

    def _load_or_create_progress(self) -> Progress:
        self._ensure_services()
        return self._work_unit_service.load_or_create_progress()

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _print_strategy_details(self) -> None:
        """Print every generated compound string and coverage gap with rationale."""
        if not self._execution_plan:
            return

        gs = self._execution_plan.generated_strings
        if gs:
            print(f"\n  Compound strings ({len(gs)}):")
            for i, s in enumerate(gs, 1):
                boolean = s.get("boolean", "")
                rationale = s.get("rationale", "")[:100]
                print(f"    #{i}: {boolean}")
                print(f"        → {rationale}")

        gaps = self._execution_plan.coverage_gaps
        if gaps:
            executable = [g for g in gaps if g.get("suggested_boolean")]
            if executable:
                print(f"\n  Coverage gaps ({len(executable)}):")
                for i, g in enumerate(executable, 1):
                    boolean = g.get("suggested_boolean", "")
                    gap_desc = g.get("gap", "")[:100]
                    print(f"    #{i}: {boolean}")
                    print(f"        → Gap: {gap_desc}")

    def _print_session_summary(self, progress: Progress) -> None:
        """Print running session summary after each string completes."""
        done = sum(1 for s in progress.strings if s.status == "done")
        total = len(progress.strings)
        refined = sum(1 for s in progress.strings if s.notes and "Refined" in s.notes)
        print(f"\n  Session: {done}/{total} strings | "
              f"{self.stats['snippets_extracted']} evaluated | "
              f"{self.stats['facial_yes']} facial YES | "
              f"{self.stats['saved']} saves | "
              f"{refined} refined")

    def _print_summary(self) -> None:
        print(f"\n{'=' * 60}")
        print("  Run Summary")
        print(f"{'=' * 60}")
        print(f"  Snippets extracted:  {self.stats['snippets_extracted']}")
        print(f"  Facial YES:          {self.stats['facial_yes']}")
        print(f"  Facial NO:           {self.stats['facial_no']}")
        print(f"  SAVED:               {self.stats['saved']}")
        if self.stats.get("save_attempts", 0) != self.stats["saved"]:
            print(f"  Save attempts:       {self.stats['save_attempts']}")
        print(f"  REJECTED:            {self.stats['rejected']}")
        if self._bias_monitor:
            summary = self._bias_monitor.session_summary()
            if summary.get("total_decisions", 0) > 0:
                print(f"  ---")
                print(f"  Facial YES rate:     {summary.get('facial_yes_rate', 0):.1%}")
                print(f"  Full save rate:      {summary.get('save_rate', 0):.1%}")
                print(f"  Parse failures:      {summary.get('parse_failures', 0)} ({summary.get('parse_failure_rate', 0):.1%})")
                print(f"  Bias alerts fired:   {len(summary.get('alerts_fired', []))}")
        print(f"{'=' * 60}")

    def _bias_summary_for_report(self) -> str:
        """Format bias monitor summary for injection into the run report prompt."""
        if not self._bias_monitor:
            return ""
        summary = self._bias_monitor.session_summary()
        if summary.get("total_decisions", 0) == 0:
            return ""
        lines = [
            "",
            "## Bias Monitor Metrics",
            f"- Facial YES rate: {summary.get('facial_yes_rate', 0):.1%}",
            f"- Full save rate: {summary.get('save_rate', 0):.1%}",
            f"- Parse failures: {summary.get('parse_failures', 0)} ({summary.get('parse_failure_rate', 0):.1%})",
            f"- Alerts fired: {len(summary.get('alerts_fired', []))}",
        ]
        per_string = summary.get("per_string", {})
        if per_string:
            flagged = [(sid, s) for sid, s in per_string.items() if s.get("save_rate", 0) > 0.5 and s.get("total_full_evals", 0) >= 5]
            if flagged:
                lines.append("- High save-rate strings:")
                for sid, s in flagged:
                    lines.append(f"  - String {sid}: {s['save_rate']:.0%} save rate ({s['saves']} saves / {s['total_full_evals']} evals)")
        return "\n".join(lines) + "\n"

    def _load_run_report_decisions(
        self,
        decision_filter: set[str],
        limit: int = 20,
    ) -> list[dict]:
        """Load a compact set of final-judgment examples for debrief generation."""
        if not self.final_path.exists():
            return []
        records: list[dict] = []
        try:
            for row in read_jsonl(self.final_path):
                if not isinstance(row, dict):
                    continue
                if row.get("decision") not in decision_filter:
                    continue
                records.append(
                    {
                        "candidate_name": row.get("candidate_name", ""),
                        "decision": row.get("decision", ""),
                        "path": row.get("path", ""),
                        "confidence": row.get("confidence", 0.0),
                        "rationale": _normalize_text_for_report(row.get("rationale", ""))[:280],
                    }
                )
                if len(records) >= limit:
                    break
        except Exception:
            return []
        return records

    def _build_run_report_snapshot(self, progress: Progress) -> dict:
        """Build a deterministic raw snapshot for structured debrief generation."""
        done_count = sum(1 for s in progress.strings if s.status == "done")
        skipped_count = sum(1 for s in progress.strings if s.status == "skipped")
        total_results = sum(s.result_count for s in progress.strings if s.result_count > 0)
        total_pages = sum(s.pages_reviewed for s in progress.strings)
        candidates_evaluated = self.stats["snippets_extracted"]
        overall_save_rate = self.stats["saved"] / max(candidates_evaluated, 1)
        facial_yes_rate = self.stats["facial_yes"] / max(candidates_evaluated, 1)

        string_performance = []
        for s in progress.strings:
            if s.status not in {"done", "skipped"}:
                continue
            save_rate = len(s.saves) / max(s.candidates_count or (s.pages_reviewed * 25), 1)
            string_performance.append(
                {
                    "string_id": s.id,
                    "name": s.name,
                    "status": s.status,
                    "result_count": s.result_count,
                    "pages_reviewed": s.pages_reviewed,
                    "saves": len(s.saves),
                    "save_rate": round(save_rate, 4),
                    "saved_candidates": s.saves[:10],
                    "notes": s.notes or "",
                    "facial_yes_count": s.facial_yes_count,
                    "facial_no_count": s.facial_no_count,
                    "candidates_count": s.candidates_count,
                    "duplicates_count": s.duplicates_count,
                    "family_key": s.family_key,
                    "novelty_bucket": s.novelty_bucket,
                    "domain_lane": s.domain_lane,
                }
            )

        return {
            "schema_version": 1,
            "run_metadata": {
                "role_title": self.brief_obj.role_title,
                "brief_name": progress.brief_name,
                "brief_version": self.brief_obj.raw.get("version", ""),
                "linkedin_project": self.brief_obj.linkedin_project,
                "linkedin_project_id": self.brief_obj.linkedin_project_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "overall_summary": (
                    f"Run covered {done_count} executed strings over {total_pages} pages, "
                    f"evaluated {candidates_evaluated} candidates, and saved {self.stats['saved']}."
                ),
            },
            "metrics_summary": {
                "strings_executed": done_count,
                "strings_skipped": skipped_count,
                "total_results": total_results,
                "total_pages_reviewed": total_pages,
                "candidates_evaluated": candidates_evaluated,
                "facial_yes": self.stats["facial_yes"],
                "facial_no": self.stats["facial_no"],
                "saved": self.stats["saved"],
                "rejected": self.stats["rejected"],
                "overall_save_rate": round(overall_save_rate, 4),
                "facial_yes_rate": round(facial_yes_rate, 4),
            },
            "string_performance": string_performance,
            "saved_candidate_summaries": self._load_run_report_decisions(
                {"SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE", "SIGNAL_SAVE"},
                limit=24,
            ),
            "rejected_candidate_summaries": self._load_run_report_decisions({"REJECT"}, limit=24),
            "bias_monitor_summary": self._bias_summary_for_report().strip(),
            "search_memory_summary": build_search_memory_summary(self._search_memory)
            if self._search_memory
            else None,
        }

    def _run_report_analysis_system(self) -> str:
        return """You are a senior sourcing strategist analyzing an end-of-run sourcing snapshot.

Return valid JSON only with these exact top-level keys:
- winning_lanes
- underperforming_lanes
- coverage_gaps
- noise_patterns
- saved_candidate_patterns
- adaptation_assessment
- recommendations
- brief_iteration_hints

Rules:
- Do NOT re-state run_metadata, metrics_summary, or string_performance; those are deterministic and already captured.
- Use only evidence available in the snapshot.
- Cite concrete strings, candidates, and patterns when possible.
- Keep lists concise and high-signal.
- brief_iteration_hints may only suggest mutable brief fields:
  instructions, search_priorities, additional_search_terms, intake_notes, depth_distinction,
  non_fit_patterns, minimum_bar_description, facial_calibration, employer_signal_rules,
  calibration_examples, notes, version.
- Do NOT suggest changes to geography, minimum_years_experience, role identity, LinkedIn project mapping, capability areas, or market density.
- If suggesting employer signal rules, keep save_on_employer_alone false.
- If suggesting facial calibration changes, keep them modest and explicitly evidence-based.

Expected inner shapes:
- winning_lanes: [{"lane","string_ids","candidate_examples","evidence","why_it_worked","recommended_action"}]
- underperforming_lanes: [{"lane","string_ids","issue","evidence","recommended_action"}]
- coverage_gaps: [{"gap","why_it_matters","suggested_search_strategy"}]
- noise_patterns: [{"pattern","evidence","mitigation"}]
- saved_candidate_patterns: {
    "standout_candidates": [{"name","why"}],
    "common_employers": [{"employer","count","note"}],
    "common_titles": [{"title_family","count","note"}],
    "archetype_distribution": [{"archetype","count","note"}],
    "seniority_notes": ["..."]
  }
- adaptation_assessment: {
    "summary": "string",
    "effective_refinements": ["..."],
    "questionable_or_skipped": ["..."],
    "operational_notes": ["..."]
  }
- recommendations: {
    "try_next": ["..."],
    "avoid_next": ["..."],
    "prioritize_pipeline": ["..."]
  }
- brief_iteration_hints: {
    "instructions": ["..."],
    "search_priorities": ["..."],
    "additional_search_terms": ["..."],
    "intake_notes": "string",
    "depth_distinction": {"builder_definition","user_definition","edge_case_guidance"},
    "non_fit_patterns": [{"label","description","why_not","examples"}],
    "minimum_bar_description": "string",
    "facial_calibration": {
      "expected_yes_rate_low": 0.0,
      "expected_yes_rate_high": 0.0,
      "fast_exit_patterns": ["..."],
      "trajectory_yes_patterns": ["..."],
      "trajectory_ambiguous_patterns": ["..."],
      "trajectory_no_patterns": ["..."]
    },
    "employer_signal_rules": [{"tier","employer_patterns","evidence_required","save_on_employer_alone"}],
    "calibration_examples": {
      "strong_saves": [{"name","why"}],
      "incorrect_saves": [{"name","why"}],
      "borderline_verify": [{"name","why"}]
    },
    "notes": "string",
    "locked_field_cautions": ["..."]
  }"""

    def _generate_run_report(self, progress: Progress | None) -> None:
        """Generate structured and markdown end-of-run debrief artifacts."""
        if not progress or not progress.strings:
            return

        from shared.llm_clients import opus_llm

        report_input = self._build_run_report_snapshot(progress)
        report_input_path = self.output_dir / "run-report-input.json"
        report_json_path = self.output_dir / "run-report.json"
        report_md_path = self.output_dir / "run-report.md"

        try:
            write_json(report_input_path, report_input)
            print(f"\n{'=' * 60}")
            print("  Generating end-of-run debrief report (Opus)...")
            print(f"{'=' * 60}")
            analysis_raw = opus_llm(
                self._run_report_analysis_system(),
                json.dumps(report_input, indent=2),
                expect_json=True,
                max_tokens=12000,
            )
            analysis = RunDebriefAnalysis.from_dict(analysis_raw)
            report = StructuredRunReport.from_parts(report_input, analysis)
            write_json(report_json_path, report.to_dict())
            markdown = render_run_report_markdown(report)
            report_md_path.write_text(markdown)
            print(f"\n{markdown}")
            print(f"\n  Report input saved to: {report_input_path}")
            print(f"  Report JSON saved to:  {report_json_path}")
            print(f"  Report saved to:       {report_md_path}")
            log_event(
                self.log_path,
                "run_report_generated",
                report_input_path=str(report_input_path),
                report_json_path=str(report_json_path),
                report_path=str(report_md_path),
            )
        except Exception as e:
            print(f"  [warn] Report generation failed: {e}")


def _normalize_text_for_report(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


# ---------------------------------------------------------------------------
# Page report (structured console output per protocol.md format)
# ---------------------------------------------------------------------------

class _PageReport:
    """Collects per-page data and prints a structured report."""

    def __init__(self, string_id: int, string_name: str, page: int, result_count: int):
        self.string_id = string_id
        self.string_name = string_name
        self.page = page
        self.result_count = result_count
        self.saved: list[tuple[CandidateSnippet, OpusDecision]] = []
        self.skipped_opened: list[tuple[CandidateSnippet, OpusDecision]] = []
        self.skipped_preview: list[tuple[str, str]] = []  # (name, reason)

    def add_saved(self, snippet: CandidateSnippet, decision: OpusDecision):
        self.saved.append((snippet, decision))

    def add_skipped_opened(self, snippet: CandidateSnippet, decision: OpusDecision):
        self.skipped_opened.append((snippet, decision))

    def add_skip_preview(self, name: str, reason: str):
        self.skipped_preview.append((name, reason))

    def print_report(self, running_stats: dict) -> None:
        rc = self.result_count if self.result_count >= 0 else "?"
        print(f"\n  {'─' * 50}")
        print(f"  PAGE REPORT: String #{self.string_id} | {self.string_name} | "
              f"Page {self.page} | {rc} results")
        print(f"  {'─' * 50}")

        if self.saved:
            print(f"\n  SAVED ({len(self.saved)}):")
            for snippet, decision in self.saved:
                print(f"    + {snippet.name} — {snippet.current_title} at {snippet.current_company}")
                print(f"      Path: {decision.path} | Confidence: {decision.confidence:.2f}")
                print(f"      {decision.rationale}")

        if self.skipped_opened:
            print(f"\n  SKIPPED — profiles opened ({len(self.skipped_opened)}):")
            for snippet, decision in self.skipped_opened:
                print(f"    - {snippet.name} — {snippet.current_title} at {snippet.current_company}")
                print(f"      {decision.rationale}")

        if self.skipped_preview:
            # Group by reason category
            groups: dict[str, list[str]] = {}
            for name, reason in self.skipped_preview:
                key = reason.split(":")[0] if ":" in reason else reason
                groups.setdefault(key, []).append(name)

            print(f"\n  Skipped from preview ({len(self.skipped_preview)}):")
            for category, names in groups.items():
                if len(names) <= 3:
                    print(f"    {category}: {', '.join(names)}")
                else:
                    print(f"    {category}: {len(names)} candidates")

        print(f"\n  Running totals — Saved: {running_stats['saved']} | "
              f"Facial YES: {running_stats['facial_yes']}")
