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
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from shared.human_timing import human_delay, human_delay_correlated

from shared.schemas import (
    CandidateSnippet, CandidateProfileSummary, OpusDecision,
    SearchString, Progress, KitString, BlockReport, AdaptationResponse,
    ExecutionPlan,
)
from linkedin.browser import LinkedInBrowser
from shared.extractors import extract_snippets_from_list_dom, extract_profile_from_dom
from shared.judger import facial_judge, full_judge, init_judger
from shared.storage import append_jsonl, read_jsonl, read_jsonl_set, log_event, write_json, read_json
from shared.brief_loader import load_brief, Brief
from shared.bias_controls import BiasMonitor, DecisionRecord
from shared import config


class Pipeline:
    """Orchestrates the multi-model sourcing pipeline."""

    def __init__(
        self,
        brief_path: str,
        search_config_path: str | None = None,
        output_dir: Optional[str] = None,
        test_mode: bool = False,
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

        # Initialize judger with the Brief dataclass
        init_judger(self.brief_obj)

        # Output file paths
        self.snippets_path = self.output_dir / "snippets.jsonl"
        self.facial_path = self.output_dir / "facial_judgments.jsonl"
        self.profiles_path = self.output_dir / "profile_summaries.jsonl"
        self.final_path = self.output_dir / "final_judgments.jsonl"
        self.progress_path = self.output_dir / "progress.json"
        self.log_path = self.output_dir / "run_log.jsonl"

        # Browser
        self.browser = LinkedInBrowser()

        # Dedup cache (loaded once, updated in memory — avoids O(n^2) file reads)
        self._seen_urls: set[str] = set()

        # Stats
        self.stats = {
            "snippets_extracted": 0,
            "facial_yes": 0,
            "facial_no": 0,
            "saved": 0,
            "rejected": 0,
        }

        # Progress ref for Ctrl+C handler
        self._progress: Optional[Progress] = None

        # Kit strings (populated by run_full)
        self._kit_strings: list[KitString] = []
        self._execution_plan: Optional[ExecutionPlan] = None

        # Bias monitor (V2 briefs only — uses brief's BiasControls + FacialCalibration)
        self._bias_monitor: Optional[BiasMonitor] = None
        self.bias_checkpoint_path = self.output_dir / "bias_monitor.json"
        if self.brief_obj.has_v2_schema:
            self._bias_monitor = BiasMonitor.from_brief(self.brief_obj._new_brief)

        # Cadence pause — anti-detection idle breaks
        self._last_pause_time: float = time.time()

        # URL snapshot — last known good URL for recovery fallback
        self._last_good_url: str = ""

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run the pipeline across all search strings from search_config."""
        print("=" * 60)
        print("LinkedIn Recruiter Multi-Model Sourcing Pipeline")
        print(f"Brief: {self.brief_obj.id}")
        print("=" * 60)

        await self.browser.connect()
        log_event(self.log_path, "pipeline_start", mode="full")

        # Load dedup cache once
        self._seen_urls = read_jsonl_set(self.snippets_path)

        progress = self._load_or_create_progress()
        self._progress = progress

        # Ctrl+C handler — only install if not running under session_orchestrator
        def _sigint_handler(sig, frame):
            print("\n\n  [!] Interrupted. Saving progress...")
            if self._progress:
                self._progress.save(str(self.progress_path))
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
                progress.save(str(self.progress_path))
                log_event(self.log_path, "string_complete", string_id=search_string.id, **self.stats)

        except KeyboardInterrupt:
            print("\n\n  [!] Interrupted. Progress saved.")
        except Exception as e:
            print(f"\n  [ERROR] {e}")
            log_event(self.log_path, "pipeline_error", error=str(e))
            raise
        finally:
            progress.save(str(self.progress_path))
            await self.browser.disconnect()
            self._print_summary()
            log_event(self.log_path, "pipeline_end", **self.stats)

    async def run_single_page(self) -> None:
        """Test mode: process only the current page of results visible in the browser."""
        print("=" * 60)
        print("TEST MODE: Processing current results page only")
        print(f"Brief: {self.brief_obj.id}")
        print("=" * 60)

        await self.browser.connect()
        log_event(self.log_path, "pipeline_start", mode="single_page_test")

        try:
            print("  Scrolling to load all results...")
            card_count = await self.browser.scroll_to_load_all_results()
            print(f"  {card_count} cards loaded")
            print("  Reading results page innerText...")
            innertext = await self.browser.get_results_list_innertext()
            print(f"  Text size: {len(innertext) / 1024:.0f} KB")

            print("  Extracting candidate snippets (cheap model)...")
            snippets = extract_snippets_from_list_dom(innertext, string_id=0, string_name="test", page=1)
            print(f"  Found {len(snippets)} candidates")

            page_report = _PageReport(string_id=0, string_name="test", page=1, result_count=-1)

            for i, snippet in enumerate(snippets, 1):
                print(f"\n  [{i}/{len(snippets)}] {snippet.name}")
                print(f"    Title: {snippet.current_title} at {snippet.current_company}")
                print(f"    Headline: {snippet.headline}")

                decision = await self._evaluate_snippet(snippet, page_report)

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

    async def run_full(self, resume: bool = False, restart_string_id: int | None = None) -> None:
        """Autonomous search evolution: extract kit → strategy → execute → adapt."""
        from shared.kit_extractor import extract_kit_strings
        from linkedin.strategy import form_strategy, adapt_after_block

        print("=" * 60)
        print(f"FULL RUN: Autonomous Search Evolution{' (RESUMING)' if resume else ''}")
        print(f"Brief: {self.brief_obj.id}")
        print(f"Kit URL: {self.brief_obj.kit_url}")
        print("=" * 60)

        await self.browser.connect()
        log_event(self.log_path, "pipeline_start", mode="full_run_resume" if resume else "full_run")

        # Navigate to the project search page if we're not already there
        project_url = self._get_project_url()
        if project_url and "/talent/hire/" not in self.browser.page.url:
            print(f"  Navigating to project search page...")
            await self.browser.navigate_to_search(project_url)
        elif "linkedin.com/talent" not in self.browser.page.url:
            print(f"  Navigating to LinkedIn Recruiter...")
            await self.browser.navigate_to_search("https://www.linkedin.com/talent/search")

        # Start with empty dedup set — only dedup within this run, not across runs.
        # Prior runs may have different evaluation criteria or candidates may have updated profiles.
        self._seen_urls = set()

        # Ctrl+C handler — only install if not running under session_orchestrator
        def _sigint_handler(sig, frame):
            print("\n\n  [!] Interrupted. Saving progress...")
            if self._progress:
                self._progress.save(str(self.progress_path))
            raise KeyboardInterrupt

        if not hasattr(self, '_session_expired'):
            signal.signal(signal.SIGINT, _sigint_handler)

        try:
            if resume and self.progress_path.exists():
                # --- Resume: skip kit extraction, strategy, queue building ---
                print("\n--- Resuming from progress.json ---")
                progress = Progress.from_file(str(self.progress_path))
                self._progress = progress

                # If restarting a specific string, reset it and clean up its output
                if restart_string_id is not None:
                    self._restart_string(progress, restart_string_id)

                # Rebuild dedup set from this run's snippets so we don't re-evaluate
                if self.snippets_path.exists():
                    self._seen_urls = read_jsonl_set(self.snippets_path)
                    print(f"  Loaded {len(self._seen_urls)} URLs into dedup set from current run")

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

                progress = Progress(
                    brief_name=self.brief_obj.id,
                    strings=search_strings,
                )
                progress.save(str(self.progress_path))
                self._progress = progress

            # --- Execution ---
            print(f"\n--- Execution ({len(progress.strings)} strings) ---")
            current_block = ""
            block_strings: list[SearchString] = []

            # On resume, prioritize any in_progress string (it was interrupted mid-run)
            if resume:
                in_progress = [s for s in progress.strings if s.status == "in_progress"]
                if in_progress:
                    for ip_string in in_progress:
                        # Move to front of iteration by resetting to queued
                        # (it will be picked up first in the loop below)
                        print(f"\n  Resuming interrupted string #{ip_string.id}: {ip_string.name[:60]}")
                        ip_string.status = "queued"
                        # Move it to right after the last done string
                        progress.strings.remove(ip_string)
                        insert_idx = 0
                        for i, s in enumerate(progress.strings):
                            if s.status == "done":
                                insert_idx = i + 1
                        progress.strings.insert(insert_idx, ip_string)

            for search_string in progress.strings:
                if search_string.status == "done":
                    print(f"\n  [skip] String #{search_string.id}: {search_string.name} (already done)")
                    continue
                if search_string.status == "skipped":
                    print(f"\n  [skip] String #{search_string.id}: {search_string.name} (skipped by strategy)")
                    continue

                # Block transition → adaptation
                if search_string.block and search_string.block != current_block:
                    if current_block and block_strings:
                        await self._run_block_adaptation(
                            current_block, block_strings, progress, adapt_after_block
                        )
                    current_block = search_string.block
                    block_strings = []

                print(f"\n{'─' * 60}")
                print(f"  String #{search_string.id}: {search_string.name}")
                print(f"  [{search_string.block} / {search_string.subblock} / {search_string.string_type}]")
                print(f"{'─' * 60}")

                search_string.status = "in_progress"
                progress.current_string_id = search_string.id

                try:
                    await self._process_string(search_string, progress)
                except Exception as e:
                    err_msg = str(e).lower()
                    if "target crashed" in err_msg or "connection closed" in err_msg or "broken pipe" in err_msg:
                        print(f"\n  [!] Browser crashed during string #{search_string.id}. Attempting reconnect...")
                        progress.save(str(self.progress_path))
                        reconnected = await self._attempt_reconnect()
                        if reconnected:
                            print(f"  [!] Reconnected. Marking string #{search_string.id} as done (partial) and continuing.")
                            search_string.status = "done"
                            search_string.notes = (search_string.notes or "") + f" Partial — browser crashed mid-string."
                            block_strings.append(search_string)
                            progress.save(str(self.progress_path))
                            log_event(self.log_path, "browser_crash_recovered", string_id=search_string.id)
                            self._print_session_summary(progress)
                            continue
                        else:
                            print(f"  [!] Reconnect failed. Saving progress and exiting.")
                            raise
                    else:
                        raise

                search_string.status = "done"
                block_strings.append(search_string)
                progress.save(str(self.progress_path))
                if self._bias_monitor:
                    self._bias_monitor.save_checkpoint(str(self.bias_checkpoint_path))
                log_event(self.log_path, "string_complete", string_id=search_string.id, **self.stats)
                self._print_session_summary(progress)

            # Final block adaptation
            if current_block and block_strings:
                await self._run_block_adaptation(
                    current_block, block_strings, progress, adapt_after_block
                )

        except KeyboardInterrupt:
            print("\n\n  [!] Interrupted. Progress saved.")
        except Exception as e:
            print(f"\n  [ERROR] {e}")
            log_event(self.log_path, "pipeline_error", error=str(e))
            raise
        finally:
            if self._progress:
                self._progress.save(str(self.progress_path))
            if self._bias_monitor:
                self._bias_monitor.save_checkpoint(str(self.bias_checkpoint_path))
            await self.browser.disconnect()
            self._print_summary()
            if self._progress:
                self._generate_run_report(self._progress)
            log_event(self.log_path, "pipeline_end", **self.stats)

    # ------------------------------------------------------------------
    # Browser crash recovery
    # ------------------------------------------------------------------

    async def _attempt_reconnect(self, max_attempts: int = 6, wait_seconds: int = 10) -> bool:
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
                print(f"  [reconnect] Success — reconnected to LinkedIn Recruiter.")
                return True
            except Exception as e:
                print(f"  [reconnect] Failed: {e}")
        return False

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    async def _process_string(self, search_string: SearchString, progress: Progress) -> None:
        # Initialize refinement tracking
        if not search_string.original_boolean:
            search_string.original_boolean = search_string.boolean

        # Emergency recovery check before starting
        await self._ensure_browser_healthy()

        current_boolean = search_string.boolean
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

            card_count = await self.browser.scroll_to_load_all_results()
            print(f"  {card_count} cards loaded after scroll", flush=True)

            if card_count == 0:
                print("  0 cards on page. Skipping string.")
                break

            innertext = await self.browser.get_results_list_innertext()
            print(f"  Text size: {len(innertext) / 1024:.0f} KB", flush=True)

            snippets = extract_snippets_from_list_dom(
                innertext, search_string.id, search_string.name, page_num
            )
            print(f"  Extracted {len(snippets)} candidates", flush=True)

            if not snippets:
                print("  No candidates found on this page. Moving on.")
                break

            # Get name+URL pairs atomically from DOM (innerText strips hrefs)
            card_pairs = await self.browser.get_card_name_url_pairs()
            url_by_name: dict[str, str] = {}
            index_by_name: dict[str, int] = {}
            for i, pair in enumerate(card_pairs):
                key = pair["name"].strip().lower() if pair["name"] else ""
                if key and pair["url"]:
                    url_by_name[key] = pair["url"]
                if key:
                    index_by_name[key] = i
            matched = 0
            for snippet in snippets:
                key = snippet.name.strip().lower()
                if key in url_by_name:
                    snippet.profile_url = url_by_name[key]
                    matched += 1
                if key in index_by_name:
                    snippet.card_index = index_by_name[key]
            if matched < len(snippets):
                print(f"  [warn] URL match: {matched}/{len(snippets)} snippets matched to DOM cards")

            page_report = _PageReport(
                string_id=search_string.id,
                string_name=search_string.name,
                page=page_num,
                result_count=result_count,
            )

            consecutive_api_errors = 0
            for snippet in snippets:
                if snippet.profile_url and snippet.profile_url in self._seen_urls:
                    print(f"    [dup] {snippet.name} — already processed")
                    page_report.add_skip_preview(snippet.name, "duplicate")
                    string_stats["duplicates"] += 1
                    continue

                # Circuit breaker: pause on sustained API failures
                if consecutive_api_errors >= 5:
                    print(f"    [CIRCUIT BREAKER] {consecutive_api_errors} consecutive API failures — pausing 60s")
                    log_event(self.log_path, "circuit_breaker", consecutive_errors=consecutive_api_errors)
                    await asyncio.sleep(60)
                    consecutive_api_errors = 0

                if snippet.profile_url:
                    self._seen_urls.add(snippet.profile_url)
                append_jsonl(self.snippets_path, snippet.to_dict())
                self.stats["snippets_extracted"] += 1
                string_stats["candidates"] += 1

                decision = await self._evaluate_snippet(snippet, page_report)

                # Track API error fallbacks for circuit breaker
                if decision and hasattr(decision, 'rationale') and '[API error fallback' in (decision.rationale or ''):
                    consecutive_api_errors += 1
                else:
                    consecutive_api_errors = 0

                # If go_back_to_results failed, panel is still open — skip remaining candidates on this page
                if decision and getattr(decision, '_panel_stuck', False):
                    print(f"    [ERROR] Panel stuck after {snippet.name} — skipping remaining candidates on this page")
                    log_event(self.log_path, "panel_stuck", name=snippet.name, page=page_num)
                    break

                outcome = "error"
                if decision:
                    if decision.stage == "facial" and decision.decision == "FACIAL_NO":
                        outcome = "facial_no"
                        string_stats["facial_no"] += 1
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

                # Cooperative session expiry check.
                # If session_orchestrator's duration timer has fired, exit gracefully
                # at this safe checkpoint instead of being hard-cancelled mid-operation.
                if hasattr(self, '_session_expired') and self._session_expired.is_set():
                    progress.save(str(self.progress_path))
                    from shared.governor import SessionExpired
                    raise SessionExpired("session_duration_cap")

                # Cooperative yield point for decoy interleaving.
                # If session_orchestrator has set _pause_requested, we pause here
                # (between candidates, after evaluation is complete and results are safe).
                if hasattr(self, '_pause_requested') and self._pause_requested.is_set():
                    self._pause_requested.clear()  # Acknowledge the pause
                    progress.save(str(self.progress_path))
                    await self._resume_event.wait()  # Block until decoy burst completes

            string_stats["pages"] = page_num
            search_string.pages_reviewed = page_num
            progress.save(str(self.progress_path))
            page_report.print_report(self.stats)

            # --- Two-phase adaptation ---
            adapt_action = await self._page_adapt(
                search_string, current_boolean, result_count_text,
                all_candidates, string_stats,
            )

            # Enforce minimum pagination depth — override premature stop/abandon
            if adapt_action in ("abandon", "stop"):
                min_pages = self._get_min_pages(result_count)
                if page_num < min_pages:
                    print(f"  [pagination] Opus wants to {adapt_action}, but page {page_num} < min {min_pages} for {result_count} results. Continuing.")
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
                await asyncio.sleep(human_delay_correlated(config.PAGE_DELAY_SECONDS))
            else:
                break

    @staticmethod
    def _get_min_pages(result_count: int) -> int:
        """Get minimum pages to review before allowing stop/abandon."""
        for threshold, min_pages in config.MIN_PAGES_BY_RESULT_COUNT:
            if result_count >= threshold:
                return min_pages
        return 1

    async def _ensure_browser_healthy(self) -> None:
        """Check for error states, attempt recovery, and enforce cadence pauses."""
        # --- Cadence pause: human-like idle break ---
        await self._maybe_cadence_pause()

        # --- Snapshot current URL as known-good before checking for errors ---
        try:
            current_url = self.browser.page.url
            if "linkedin.com/talent" in current_url and "/login" not in current_url:
                self._last_good_url = current_url
        except Exception:
            pass

        # --- Error recovery ---
        recovered = await self.browser.check_and_recover()
        if recovered:
            # Try project URL first, then last known good URL
            recovery_url = self._get_project_url() or self._last_good_url
            if recovery_url:
                print(f"  [recovery] Re-navigating to: {recovery_url[:60]}...")
                await self.browser.navigate_to_search(recovery_url)
            else:
                print("  [recovery] No recovery URL available — continuing from current page.")

    def _get_project_url(self) -> str:
        """Construct LinkedIn Recruiter project URL from brief fields."""
        pid = self.brief_obj.linkedin_project_id
        if pid:
            return f"https://www.linkedin.com/talent/hire/{pid}"
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

    async def _page_adapt(
        self,
        search_string: SearchString,
        current_boolean: str,
        result_count_text: str,
        all_candidates: list[dict],
        string_stats: dict,
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
        from shared.llm_clients import opus_llm

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

        # Phase-specific action menu
        if is_scout:
            actions_section = """Choose ONE action:

1. "paginate" — Page 1 shows good signal. Commit to paginating this Boolean deeper.
2. "narrow" — Too broad/noisy. Add AND clauses to focus the search. Provide a modified Boolean that narrows from the current one.
3. "abandon" — Fundamentally wrong results (wrong domain, wrong seniority band, mostly noise). Skip this string entirely.

## How a sourcer thinks about scout phase
- This is page 1 — the BEST results LinkedIn will show. If page 1 is mostly noise, deeper pages will be worse.
- A high result count (3K+) means the Boolean is broad. That's fine IF page 1 quality is good.
- If you see 1-2 saves or strong facial YES candidates on page 1, the string has promise — paginate.
- If page 1 is dominated by wrong-domain, wrong-seniority, or irrelevant profiles, narrow or abandon.
- When narrowing, add AND terms to exclude the dominant noise pattern. Be specific about which terms you're adding and why.
- Abandon is for strings where the core concept is wrong, not just noisy. Prefer narrow when the signal exists but is buried."""
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
- Duplicates are expected and not a problem unless >30%."""

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
## Accumulated Stats (across {string_stats['pages']} page(s))
- Candidates evaluated: {string_stats['candidates']}
- Duplicates skipped: {string_stats['duplicates']}
- SAVES: {string_stats['saves']}
- REJECTS (opened profile, then rejected): {string_stats['rejects']}
- Facial YES (opened for full review): {string_stats['facial_yes']}
- Facial NO (skipped from preview): {string_stats['facial_no']}
- Save rate: {string_stats['saves'] / max(string_stats['candidates'], 1) * 100:.1f}%

## All Candidates So Far
{candidates_text}

What next?"""

        try:
            result = opus_llm(system, user_prompt, expect_json=True)
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

    async def _evaluate_snippet(
        self, snippet: CandidateSnippet, page_report: _PageReport | None = None,
    ) -> Optional[OpusDecision]:
        """Run snippet through facial judgment -> full profile -> final judgment."""

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
                    return OpusDecision(
                        stage="facial", decision="FACIAL_NO", path="employer_blacklist",
                        confidence=1.0, rationale=f"Employer blacklist: {blocked}",
                        candidate_name=snippet.name, profile_url=snippet.profile_url,
                    )

        # --- Facial judgment (Opus) ---
        print(f"    Facial judgment (Opus)...")
        try:
            facial = facial_judge(snippet, self.brief_obj)
        except Exception as e:
            print(f"    [ERROR] Facial judgment failed: {e}")
            log_event(self.log_path, "facial_error", name=snippet.name, error=str(e))
            # Fallback: default to FACIAL_YES so candidate isn't permanently lost
            facial = OpusDecision(
                stage="facial", decision="FACIAL_YES", path="none", confidence=0.0,
                rationale=f"[API error fallback — defaulting to YES] {str(e)[:100]}",
                candidate_name=snippet.name, profile_url=snippet.profile_url,
            )

        append_jsonl(self.facial_path, facial.to_dict())

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

        if facial.decision == "FACIAL_NO":
            print(f"    [FACIAL_NO] {facial.rationale}")
            self.stats["facial_no"] += 1
            if page_report:
                page_report.add_skip_preview(snippet.name, f"FACIAL_NO: {facial.rationale}")
            return facial

        print(f"    [FACIAL_YES] {facial.rationale}")
        self.stats["facial_yes"] += 1

        # --- Full profile extraction (cheap model) ---
        # Emergency recovery check before browser interaction
        await self._ensure_browser_healthy()

        print(f"    Opening profile for full evaluation...")
        # Pre-open pause — simulate scanning the snippet before deciding to click
        scan_time = random.uniform(1.5, 4.0)
        await asyncio.sleep(human_delay_correlated(scan_time))

        try:
            # Re-render the target card's article (LinkedIn virtual scrolling de-renders offscreen)
            if snippet.card_index >= 0:
                await self.browser.ensure_card_rendered(snippet.card_index)

            opened = False
            if snippet.profile_url:
                try:
                    await self.browser.open_profile_by_url(snippet.profile_url)
                    opened = True
                except Exception as url_err:
                    print(f"    [warn] URL-based open failed ({url_err}), falling back to name match...")
            if not opened:
                await self.browser.open_profile(snippet.name)
            # Simulate human reading — scroll through profile sections with dwell
            await self.browser.simulate_profile_read()
            profile_text = await self.browser.get_profile_innertext()
            print(f"    Profile text size: {len(profile_text) / 1024:.0f} KB")

            summary = extract_profile_from_dom(profile_text, snippet.profile_url)
            append_jsonl(self.profiles_path, summary.to_dict())

        except Exception as e:
            print(f"    [ERROR] Profile extraction failed: {e}")
            log_event(self.log_path, "profile_error", name=snippet.name, error=str(e))
            try:
                await self.browser.go_back_to_results()
            except Exception:
                pass
            return facial

        # --- Final judgment (Opus) ---
        print(f"    Final judgment (Opus)...")
        try:
            final = full_judge(summary, self.brief_obj)
        except Exception as e:
            print(f"    [ERROR] Final judgment failed: {e}")
            log_event(self.log_path, "final_error", name=snippet.name, error=str(e))
            try:
                await self.browser.go_back_to_results()
            except Exception:
                print(f"    [warn] go_back_to_results also failed after judgment error")
            return facial

        append_jsonl(self.final_path, final.to_dict())

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
            self.stats["saved"] += 1

            if not self.test_mode:
                already_saved = await self.browser.is_already_saved()
                if already_saved:
                    print(f"    Already in LinkedIn pipeline (skipping save click)")
                    saved = True
                else:
                    saved = await self.browser.save_candidate()
                    if saved:
                        print(f"    Saved to LinkedIn pipeline")
                    else:
                        print(f"    [warn] LinkedIn save may have failed")
                    # Post-save pause — simulate the decision moment
                    await asyncio.sleep(human_delay_correlated(3.0))
                log_event(self.log_path, "candidate_saved", name=snippet.name, linkedin_save=saved)

            if page_report:
                page_report.add_saved(snippet, final)
        else:
            print(f"    [REJECT] {final.rationale}")
            self.stats["rejected"] += 1
            if page_report:
                page_report.add_skipped_opened(snippet, final)

        try:
            await self.browser.go_back_to_results()
            await asyncio.sleep(human_delay_correlated(0.8))
        except Exception as e:
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
            )
            ordered.append(ss)
            next_id += 1

        gap_count = len(ordered) - compound_count
        print(f"  {compound_count} compound strings + {gap_count} coverage gap strings queued")

        return ordered

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
                }
                for s in sorted(strings_with_saves, key=lambda x: len(x.saves), reverse=True)[:3]
            ],
            zero_save_string_ids=[s.id for s in block_strings if not s.saves],
        )

        print(f"  {report.to_summary_text()}")

        # Get remaining unexecuted search strings
        remaining = [s for s in progress.strings if s.status == "queued"]

        if not remaining:
            print("  No remaining strings — skipping adaptation.")
            return

        try:
            adaptation = adapt_fn(
                self.brief_obj, report, remaining,
                kit_vocabulary=self._kit_strings,
            )

            # Apply adaptations
            if adaptation.skip_remaining:
                skip_ids = {s["string_id"] for s in adaptation.skip_remaining}
                for ss in progress.strings:
                    if ss.id in skip_ids and ss.status == "queued":
                        ss.status = "skipped"
                        ss.notes = f"Skipped by adaptation: {next((s['reason'] for s in adaptation.skip_remaining if s['string_id'] == ss.id), '')}"
                        print(f"    [adapt] Skipping #{ss.id}: {ss.notes}")

            if adaptation.new_strings:
                max_id = max(s.id for s in progress.strings) if progress.strings else 0
                for ns in adaptation.new_strings:
                    max_id += 1
                    new_ss = SearchString(
                        id=max_id,
                        name=f"Adaptive / {ns.get('rationale', 'new')}",
                        boolean=ns["boolean"],
                        block=block_name,
                        string_type="Adaptive",
                    )
                    progress.strings.append(new_ss)
                    print(f"    [adapt] Added new string #{max_id}: {ns['boolean'][:60]}...")

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

            progress.save(str(self.progress_path))
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
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        for path in [self.snippets_path, self.facial_path, self.profiles_path, self.final_path]:
            if path.exists() and path.stat().st_size > 0:
                backup = path.with_name(f"{path.stem}-{ts}{path.suffix}")
                path.rename(backup)
                print(f"  Archived {path.name} → {backup.name}")

    # ------------------------------------------------------------------
    # String restart
    # ------------------------------------------------------------------

    def _restart_string(self, progress: Progress, string_id: int) -> None:
        """Reset a specific search string to page 1 and clean up its output files."""
        target = None
        for s in progress.strings:
            if s.id == string_id:
                target = s
                break

        if not target:
            print(f"  [warn] String #{string_id} not found in progress — ignoring --restart-string")
            return

        print(f"\n  --- Restarting String #{string_id}: {target.name[:60]} ---")
        print(f"  Previous state: status={target.status}, pages_reviewed={target.pages_reviewed}, saves={len(target.saves)}")

        # 1. Reset the string in progress
        target.status = "queued"
        target.pages_reviewed = 0
        target.phase = "scout"
        target.saves = []
        target.notes = ""
        target.refinement_stack = []

        # 2. Collect profile URLs from this string's snippets for cross-referencing
        urls_to_remove = set()
        if self.snippets_path.exists():
            all_snippets = read_jsonl(self.snippets_path)
            kept_snippets = []
            for snip in all_snippets:
                if snip.get("source_string_id") == string_id:
                    url = snip.get("profile_url", "")
                    if url:
                        urls_to_remove.add(url)
                else:
                    kept_snippets.append(snip)
            # Rewrite snippets file without this string's entries
            self._rewrite_jsonl(self.snippets_path, kept_snippets)
            print(f"  Removed {len(urls_to_remove)} snippets for string #{string_id}")

        # 3. Filter other JSONL files by removing entries matching removed URLs
        for path in [self.facial_path, self.final_path, self.profiles_path]:
            if path.exists():
                records = read_jsonl(path)
                kept = [r for r in records if r.get("profile_url", "") not in urls_to_remove]
                removed = len(records) - len(kept)
                if removed > 0:
                    self._rewrite_jsonl(path, kept)
                    print(f"  Removed {removed} entries from {path.name}")

        # 4. Save updated progress
        progress.save(str(self.progress_path))
        print(f"  String #{string_id} reset to page 1. Ready for re-evaluation.")

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
        if self.progress_path.exists():
            existing = Progress.from_file(str(self.progress_path))
            if existing.brief_name == self.brief_obj.id:
                print("  Resuming from existing progress file...")
                return existing
            else:
                print(f"  Progress file is for '{existing.brief_name}', not '{self.brief_obj.id}'. Starting fresh.")

        strings = []
        for s in self.search_config.get("strings", []):
            strings.append(SearchString(
                id=s["id"],
                name=s["name"],
                boolean=s["boolean"],
            ))

        progress = Progress(
            brief_name=self.brief_obj.id,
            strings=strings,
        )
        progress.save(str(self.progress_path))
        return progress

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

    def _generate_run_report(self, progress: Progress | None) -> None:
        """Generate an Opus-written end-of-run debrief report."""
        if not progress or not progress.strings:
            return

        from shared.llm_clients import opus_llm

        # Build per-string performance data
        string_lines = []
        for s in progress.strings:
            if s.status == "done":
                save_rate = f"{len(s.saves) / max(s.pages_reviewed * 25, 1) * 100:.1f}%" if s.pages_reviewed else "n/a"
                saves_text = ", ".join(s.saves[:5])
                if len(s.saves) > 5:
                    saves_text += f" (+{len(s.saves) - 5} more)"
                string_lines.append(
                    f"  #{s.id} [{s.status}] {s.name[:80]}\n"
                    f"    Results: {s.result_count} | Pages: {s.pages_reviewed} | "
                    f"Saves: {len(s.saves)} ({save_rate}) | Notes: {s.notes or 'none'}\n"
                    f"    Saved: {saves_text or 'none'}"
                )
            elif s.status == "skipped":
                string_lines.append(
                    f"  #{s.id} [skipped] {s.name[:80]}\n    {s.notes or 'Skipped by adaptation'}"
                )
        strings_text = "\n".join(string_lines)

        # Load saves from final judgments file for richer context
        saves_detail = ""
        if self.final_path.exists():
            try:
                saves = []
                for line in self.final_path.read_text().strip().split("\n"):
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    if d.get("decision") in ("SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE"):
                        saves.append(d)
                if saves:
                    detail_lines = []
                    for sv in saves:
                        detail_lines.append(
                            f"  - {sv.get('candidate_name', '?')} | "
                            f"Path: {sv.get('path', '?')} | "
                            f"Confidence: {sv.get('confidence', '?')}\n"
                            f"    {sv.get('rationale', '')[:200]}"
                        )
                    saves_detail = "\n".join(detail_lines)
            except Exception:
                pass

        done_count = sum(1 for s in progress.strings if s.status == "done")
        skipped_count = sum(1 for s in progress.strings if s.status == "skipped")
        total_saves = sum(len(s.saves) for s in progress.strings)
        total_results = sum(s.result_count for s in progress.strings if s.result_count > 0)
        total_pages = sum(s.pages_reviewed for s in progress.strings)

        system = f"""You are a senior sourcing strategist writing an end-of-run debrief report.

Role: {self.brief_obj.role_title}
{self.brief_obj.role_description}

Write a comprehensive debrief report in markdown covering:

1. **Executive Summary** — Total saves, total candidates evaluated, overall save rate, run duration in strings/pages
2. **Top Performing Strings** — Which strings produced the most saves and why? What made them effective?
3. **Underperforming Strings** — Which strings were stopped early or produced zero saves? What went wrong?
4. **Candidate Profile** — What patterns emerge among the saved candidates? Common employers, titles, backgrounds, archetype distribution
5. **Noise Patterns Observed** — What were the dominant noise categories? (e.g., product managers, strategy/GTM, non-domain backgrounds)
6. **Adaptation Decisions** — How did the agent adapt during the run? Were refinements effective? Were strings correctly skipped?
7. **Recommendations for Next Run** — What Boolean strategies should be tried next? What should be avoided? Any gaps in coverage?

Be specific — cite string IDs, candidate names, and concrete patterns. This report should be actionable for planning the next sourcing run."""

        user_prompt = f"""## Run Statistics
- Strings executed: {done_count} ({skipped_count} skipped)
- Total results across all strings: {total_results}
- Total pages reviewed: {total_pages}
- Candidates evaluated: {self.stats['snippets_extracted']}
- Facial YES: {self.stats['facial_yes']}
- Facial NO: {self.stats['facial_no']}
- SAVED: {self.stats['saved']}
- REJECTED: {self.stats['rejected']}
- Overall save rate: {self.stats['saved'] / max(self.stats['snippets_extracted'], 1) * 100:.1f}%
{self._bias_summary_for_report()}
## Per-String Performance
{strings_text}

## Saved Candidates Detail
{saves_detail or "No detailed save data available."}

Write the debrief report."""

        try:
            print(f"\n{'=' * 60}")
            print("  Generating end-of-run debrief report (Opus)...")
            print(f"{'=' * 60}")
            report = opus_llm(system, user_prompt, expect_json=False, max_tokens=8192)

            # Save to file
            report_path = self.output_dir / "run-report.md"
            report_path.write_text(report)
            print(f"\n{report}")
            print(f"\n  Report saved to: {report_path}")
            log_event(self.log_path, "run_report_generated", path=str(report_path))
        except Exception as e:
            print(f"  [warn] Report generation failed: {e}")


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
