"""Main pipeline orchestration. Connects extraction → filtering → judgment → save.

Usage:
    pipeline = Pipeline(brief_path="briefs/brazil-v2.json", search_config_path="search_config.json")
    await pipeline.run()
    await pipeline.run_single_page()  # test mode
"""

from __future__ import annotations
import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from schemas import (
    CandidateSnippet, CandidateProfileSummary, OpusDecision,
    SearchString, Progress,
)
from browser import LinkedInBrowser
from extractors import extract_snippets_from_list_dom, extract_profile_from_dom
from hard_filters import hard_filter
from judger import facial_judge, full_judge
from storage import append_jsonl, read_jsonl_set, log_event, write_json, read_json
import config


class Pipeline:
    """Orchestrates the multi-model sourcing pipeline."""

    def __init__(
        self,
        brief_path: str,
        search_config_path: str = "search_config.json",
        output_dir: Optional[str] = None,
        test_mode: bool = False,
    ):
        self.brief = read_json(brief_path)
        self.search_config = read_json(search_config_path)
        self.output_dir = Path(output_dir) if output_dir else config.OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.test_mode = test_mode

        # Output file paths
        self.snippets_path = self.output_dir / "snippets.jsonl"
        self.facial_path = self.output_dir / "facial_judgments.jsonl"
        self.profiles_path = self.output_dir / "profile_summaries.jsonl"
        self.final_path = self.output_dir / "final_judgments.jsonl"
        self.progress_path = self.output_dir / "progress.json"
        self.log_path = self.output_dir / "run_log.jsonl"

        # Browser
        self.browser = LinkedInBrowser()

        # Stats
        self.stats = {
            "snippets_extracted": 0,
            "hard_filtered": 0,
            "facial_yes": 0,
            "facial_no": 0,
            "saved": 0,
            "rejected": 0,
        }

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run the full pipeline across all search strings."""
        print("=" * 60)
        print("LinkedIn Recruiter Multi-Model Sourcing Pipeline")
        print("=" * 60)

        await self.browser.connect()
        log_event(self.log_path, "pipeline_start", mode="full")

        # Load or create progress
        progress = self._load_or_create_progress()

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
        """Test mode: process only the current page of results visible in the browser.
        
        Does NOT enter a search string — assumes the browser is already showing results.
        """
        print("=" * 60)
        print("TEST MODE: Processing current results page only")
        print("=" * 60)

        await self.browser.connect()
        log_event(self.log_path, "pipeline_start", mode="single_page_test")

        try:
            # Get DOM of current results
            print("  Reading results page DOM...")
            dom = await self.browser.get_results_page_dom()
            dom_kb = len(dom) / 1024
            print(f"  DOM size: {dom_kb:.0f} KB")

            # Extract snippets
            print("  Extracting candidate snippets (cheap model)...")
            snippets = extract_snippets_from_list_dom(dom, string_id=0, string_name="test", page=1)
            print(f"  Found {len(snippets)} candidates")

            # Process each snippet
            for i, snippet in enumerate(snippets, 1):
                print(f"\n  [{i}/{len(snippets)}] {snippet.name}")
                print(f"    Title: {snippet.current_title} at {snippet.current_company}")
                print(f"    Headline: {snippet.headline}")

                await self._evaluate_snippet(snippet)

        except Exception as e:
            print(f"\n  [ERROR] {e}")
            raise
        finally:
            await self.browser.disconnect()
            self._print_summary()

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    async def _process_string(self, search_string: SearchString, progress: Progress) -> None:
        """Process a single search string: enter Boolean, paginate, extract, judge."""

        # Enter the Boolean into the Keywords field
        print(f"  Entering Boolean: {search_string.boolean[:80]}...")
        await self.browser.enter_search_string(search_string.boolean)

        # Get result count
        result_count = await self.browser.get_results_count()
        search_string.result_count = result_count
        print(f"  Results: {result_count if result_count >= 0 else 'unknown'}")

        # Paginate through results
        page_num = 1
        max_pages = config.MAX_PAGES_PER_STRING or 999

        while page_num <= max_pages:
            print(f"\n  --- Page {page_num} ---")
            progress.current_page = page_num

            # Read DOM
            dom = await self.browser.get_results_page_dom()
            print(f"  DOM size: {len(dom) / 1024:.0f} KB")

            # Extract snippets
            snippets = extract_snippets_from_list_dom(
                dom, search_string.id, search_string.name, page_num
            )
            print(f"  Extracted {len(snippets)} candidates")

            if not snippets:
                print("  No candidates found on this page. Moving on.")
                break

            # Evaluate each snippet
            for snippet in snippets:
                # Deduplicate against existing snippets
                existing_urls = read_jsonl_set(self.snippets_path)
                if snippet.profile_url in existing_urls:
                    print(f"    [dup] {snippet.name} — already processed")
                    continue

                # Save snippet
                append_jsonl(self.snippets_path, snippet.to_dict())
                self.stats["snippets_extracted"] += 1

                # Evaluate
                decision = await self._evaluate_snippet(snippet)
                if decision and decision.decision == "SAVE":
                    search_string.saves.append(snippet.name)

            search_string.pages_reviewed = page_num

            # Try next page
            if page_num < max_pages:
                has_next = await self.browser.go_to_next_page()
                if not has_next:
                    print("  No more pages.")
                    break
                page_num += 1
                await asyncio.sleep(config.PAGE_DELAY_SECONDS)
            else:
                break

    async def _evaluate_snippet(self, snippet: CandidateSnippet) -> Optional[OpusDecision]:
        """Run a single snippet through hard filters → facial judgment → full profile → final judgment."""

        # --- Hard filter ---
        should_skip, reason = hard_filter(snippet)
        if should_skip:
            print(f"    [HARD SKIP] {reason}")
            self.stats["hard_filtered"] += 1
            log_event(self.log_path, "hard_filter", name=snippet.name, reason=reason)
            return None

        # --- Facial judgment (Opus) ---
        print(f"    Facial judgment (Opus)...")
        try:
            facial = facial_judge(snippet)
        except Exception as e:
            print(f"    [ERROR] Facial judgment failed: {e}")
            log_event(self.log_path, "facial_error", name=snippet.name, error=str(e))
            return None

        append_jsonl(self.facial_path, facial.to_dict())

        if facial.decision == "FACIAL_NO":
            print(f"    [FACIAL_NO] {facial.rationale}")
            self.stats["facial_no"] += 1
            return facial

        print(f"    [FACIAL_YES] {facial.rationale}")
        self.stats["facial_yes"] += 1

        # --- Full profile extraction (cheap model) ---
        print(f"    Opening profile for full evaluation...")
        try:
            await self.browser.open_profile(snippet.profile_url)
            await asyncio.sleep(config.PROFILE_DELAY_SECONDS)
            profile_dom = await self.browser.get_profile_dom()
            print(f"    Profile DOM size: {len(profile_dom) / 1024:.0f} KB")

            summary = extract_profile_from_dom(profile_dom, snippet.profile_url)
            append_jsonl(self.profiles_path, summary.to_dict())

        except Exception as e:
            print(f"    [ERROR] Profile extraction failed: {e}")
            log_event(self.log_path, "profile_error", name=snippet.name, error=str(e))
            # Navigate back to results
            try:
                await self.browser.go_back_to_results()
            except Exception:
                pass
            return facial

        # --- Final judgment (Opus) ---
        print(f"    Final judgment (Opus)...")
        try:
            final = full_judge(summary)
        except Exception as e:
            print(f"    [ERROR] Final judgment failed: {e}")
            log_event(self.log_path, "final_error", name=snippet.name, error=str(e))
            await self.browser.go_back_to_results()
            return facial

        append_jsonl(self.final_path, final.to_dict())

        if final.decision == "SAVE":
            print(f"    ✅ [SAVE] {final.rationale}")
            self.stats["saved"] += 1

            # Save to LinkedIn pipeline
            if not self.test_mode:
                saved = await self.browser.save_candidate()
                if saved:
                    print(f"    💾 Saved to LinkedIn pipeline")
                else:
                    print(f"    [warn] LinkedIn save may have failed — check manually")
                log_event(self.log_path, "candidate_saved", name=snippet.name, linkedin_save=saved)
        else:
            print(f"    ❌ [REJECT] {final.rationale}")
            self.stats["rejected"] += 1

        # Navigate back to results
        try:
            await self.browser.go_back_to_results()
        except Exception:
            pass

        return final

    # ------------------------------------------------------------------
    # Progress management
    # ------------------------------------------------------------------

    def _load_or_create_progress(self) -> Progress:
        """Load existing progress or create fresh from search config."""
        if self.progress_path.exists():
            print("  Resuming from existing progress file...")
            return Progress.from_file(str(self.progress_path))

        # Create fresh progress from search config
        strings = []
        for s in self.search_config.get("strings", []):
            strings.append(SearchString(
                id=s["id"],
                name=s["name"],
                boolean=s["boolean"],
            ))

        progress = Progress(
            brief_name=self.brief.get("role", "unknown"),
            strings=strings,
        )
        progress.save(str(self.progress_path))
        return progress

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _print_summary(self) -> None:
        """Print final run summary."""
        print(f"\n{'=' * 60}")
        print("  Run Summary")
        print(f"{'=' * 60}")
        print(f"  Snippets extracted:  {self.stats['snippets_extracted']}")
        print(f"  Hard filtered:       {self.stats['hard_filtered']}")
        print(f"  Facial YES:          {self.stats['facial_yes']}")
        print(f"  Facial NO:           {self.stats['facial_no']}")
        print(f"  SAVED:               {self.stats['saved']}")
        print(f"  REJECTED:            {self.stats['rejected']}")
        print(f"{'=' * 60}")
