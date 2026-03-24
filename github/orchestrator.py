"""GitHub sourcing pipeline orchestrator.

Connects: strategy → multi-channel search → enrichment → evaluation → save.
No browser needed — pure API-based. Mirrors orchestrator.py's Pipeline pattern.

Usage:
    pipeline = GitHubPipeline(brief_path="config/brief-fdl-brazil-v3.json")
    await pipeline.run()
"""

from __future__ import annotations

import asyncio
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from github.client import GitHubClient
from github.enricher import GitHubEnricher
from github.schemas import (
    GitHubCandidate,
    GitHubSearchQuery,
    GitHubProgress,
    GitHubBatchReport,
)
from github.strategy import form_github_strategy, adapt_after_batch
from github.governor import (
    GitHubGovernor,
    GitHubGovernorLimitReached,
    GitHubSessionExpired,
)
from shared.contact_discovery import merge_profile_contact

from shared.schemas import CandidateSnippet, CandidateProfileSummary, OpusDecision
from shared.judger import facial_judge, full_judge, init_judger, github_facial_judge, github_full_judge
from github.outreach import generate_outreach
from shared.storage import append_jsonl, read_jsonl_set, log_event
from shared.brief_loader import load_brief, Brief
from shared.bias_controls import BiasMonitor, DecisionRecord
import github.config as gc


# Adaptation batch size — run adaptation after this many queries
_ADAPTATION_BATCH_SIZE = 5

# Checkpoint frequency — save progress after this many enrichments
_CHECKPOINT_EVERY = 10


class GitHubPipeline:
    """Orchestrates the GitHub multi-model sourcing pipeline."""

    def __init__(
        self,
        brief_path: str,
        output_dir: Optional[str] = None,
    ):
        self.brief_obj = load_brief(brief_path)
        self.output_dir = Path(output_dir) if output_dir else gc.GITHUB_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize judger with the Brief
        init_judger(self.brief_obj)

        # Output file paths
        self.candidates_path = self.output_dir / "candidates.jsonl"
        self.snippets_path = self.output_dir / "snippets.jsonl"
        self.facial_path = self.output_dir / "facial_judgments.jsonl"
        self.profiles_path = self.output_dir / "profile_summaries.jsonl"
        self.final_path = self.output_dir / "final_judgments.jsonl"
        self.progress_path = self.output_dir / "progress.json"
        self.log_path = self.output_dir / "run_log.jsonl"
        self.bias_path = self.output_dir / "bias_monitor.json"
        self.outreach_path = self.output_dir / "outreach.jsonl"

        # Dedup
        self._seen_usernames: set[str] = set()

        # Stats
        self.stats = {
            "candidates_discovered": 0,
            "candidates_enriched": 0,
            "facial_yes": 0,
            "facial_no": 0,
            "saved": 0,
            "rejected": 0,
            "insufficient": 0,
        }

        # Progress
        self._progress: Optional[GitHubProgress] = None

        # Governor
        self._governor = GitHubGovernor()

        # Bias monitor
        self._bias_monitor: Optional[BiasMonitor] = None
        if self.brief_obj.has_v2_schema:
            self._bias_monitor = BiasMonitor.from_brief(self.brief_obj._new_brief)

        # Shutdown flag
        self._shutdown_requested = False

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(self, resume: bool = False) -> dict:
        """Run the full autonomous GitHub sourcing pipeline.

        1. Strategy formation (Opus generates GitHub queries from brief)
        2. Multi-channel search execution
        3. Enrichment → facial judgment → full evaluation → save
        4. Adaptation after batches
        """
        print("=" * 60)
        print("GitHub Sourcing Pipeline")
        print(f"Brief: {self.brief_obj.id}")
        print("=" * 60)

        # Load dedup cache
        self._seen_usernames = read_jsonl_set(self.candidates_path, key="username")

        # Load or create progress
        progress = self._load_or_create_progress(resume)
        self._progress = progress

        # Install Ctrl+C handler
        self._install_signal_handler()

        log_event(self.log_path, "pipeline_start", mode="autonomous")

        async with GitHubClient() as client:
            enricher = GitHubEnricher(client, brief=self.brief_obj)

            # Step 1: Strategy (if not resuming with existing queries)
            if not progress.queries or not resume:
                queries = form_github_strategy(self.brief_obj)
                progress.queries = queries
                self._save_progress()
            else:
                print(f"  Resuming with {len(progress.queries)} queries from checkpoint")

            # Step 2: Execute queries
            try:
                await self._execute_queries(client, enricher, progress)
            except GitHubGovernorLimitReached as e:
                print(f"\n[governor] Session limit reached: {e.reason}")
            except KeyboardInterrupt:
                print("\n[shutdown] Graceful shutdown — saving progress...")
            except Exception as e:
                print(f"\n[error] Pipeline error: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc()
            finally:
                self._save_progress()
                log_event(self.log_path, "pipeline_end", stats=self.stats)

        self._print_summary()

        # Export CSV for Gem/Greenhouse import
        if self.stats["saved"] > 0:
            try:
                from github.export import export_saved_candidates_csv
                csv_path = export_saved_candidates_csv(self.output_dir)
                print(f"\n  CSV export: {csv_path}")
            except Exception as e:
                print(f"\n  [warn] CSV export failed: {e}")

        return self.stats

    # ------------------------------------------------------------------
    # Query execution loop
    # ------------------------------------------------------------------

    async def _execute_queries(
        self,
        client: GitHubClient,
        enricher: GitHubEnricher,
        progress: GitHubProgress,
    ):
        """Execute all queries in the queue with adaptation."""
        queries = progress.queries
        batch_start_idx = 0
        batch_stats: list[dict] = []

        for i, query in enumerate(queries):
            if self._shutdown_requested:
                break

            if query.status in ("done", "skipped"):
                continue

            # Check governor limits
            self._governor.check_limits_or_raise()

            # Check if we should enter enrichment-only mode
            if self._governor.should_enter_enrichment_only(client.limiter.remaining("rest")):
                print("  [governor] Low API budget — entering enrichment-only mode")
                break

            print(f"\n{'─' * 50}")
            print(f"  Query {query.id}/{len(queries)}: {query.name}")
            print(f"  Channel: {query.channel}")
            print(f"  {self._governor.status_line()}")
            print(f"  {client.status_line()}")

            query.status = "in_progress"
            progress.current_query_id = query.id

            try:
                await self._execute_single_query(client, enricher, query, progress)
            except GitHubGovernorLimitReached:
                raise
            except Exception as e:
                print(f"    [error] Query failed: {e}")
                query.notes = f"Error: {e}"

            query.status = "done"
            batch_stats.append({
                "query_id": query.id,
                "name": query.name,
                "saves": len(query.saves),
                "candidates": query.candidates_discovered,
            })

            self._save_progress()

            # Adaptation after batch
            if (i - batch_start_idx + 1) >= _ADAPTATION_BATCH_SIZE:
                remaining = [q for q in queries if q.status == "queued"]
                if remaining:
                    batch_report = self._build_batch_report(batch_stats)
                    new_queries = adapt_after_batch(self.brief_obj, batch_report, remaining)
                    if new_queries:
                        queries.extend(new_queries)
                        progress.queries = queries
                batch_start_idx = i + 1
                batch_stats = []

                # Process graph expansion queue between batches
                if progress.graph_expansion_queue:
                    await self._process_graph_expansion_queue(progress, queries)

    async def _execute_single_query(
        self,
        client: GitHubClient,
        enricher: GitHubEnricher,
        query: GitHubSearchQuery,
        progress: GitHubProgress,
    ):
        """Execute a single search query and process results."""
        usernames: list[str] = []

        if query.channel == "user_search":
            usernames = await self._search_users(client, query)
        elif query.channel == "code_search":
            usernames = await self._search_code(client, query)
        elif query.channel == "repo_mining":
            usernames = await self._mine_repo(client, query, progress)
        elif query.channel == "org_exploration":
            usernames = await self._explore_org(client, query)
        elif query.channel == "topic_search":
            usernames = await self._search_topics(client, query)
        elif query.channel == "stargazer_mining":
            usernames = await self._mine_stargazers(client, query)
        elif query.channel == "graph_expansion":
            usernames = await self._expand_graph(client, query, progress)

        query.result_count = len(usernames)
        print(f"    Found {len(usernames)} candidates (after dedup)")

        # Process each candidate
        for j, username in enumerate(usernames):
            if self._shutdown_requested:
                break
            self._governor.check_limits_or_raise()

            await self._process_candidate(
                enricher, username, query, progress,
                result_rank=j + 1,
            )

    # ------------------------------------------------------------------
    # Search channel implementations
    # ------------------------------------------------------------------

    async def _search_users(self, client: GitHubClient, query: GitHubSearchQuery) -> list[str]:
        """Execute a user search query. Returns deduplicated usernames."""
        total, items = await client.search_users(query.query)
        query.hit_result_cap = total > gc.MAX_RESULTS_PER_QUERY
        if query.hit_result_cap:
            print(f"    ⚠ Query hit 1,000 result cap ({total} total). Consider segmenting.")

        return self._dedup_usernames([item.get("login", "") for item in items])

    async def _search_code(self, client: GitHubClient, query: GitHubSearchQuery) -> list[str]:
        """Execute a code search query. Extract repo owners/contributors."""
        total, items = await client.search_code(query.query)

        # Extract unique repo owners from code results
        usernames = set()
        repos_seen = set()
        for item in items:
            repo = item.get("repository", {})
            full_name = repo.get("full_name", "")
            owner = repo.get("owner", {}).get("login", "")
            if owner:
                usernames.add(owner)
            # Also get top contributors for highly-starred repos
            if full_name and full_name not in repos_seen:
                repos_seen.add(full_name)
                stars = repo.get("stargazers_count", 0)
                if stars > 10 and len(repos_seen) <= 5:  # Limit API calls
                    try:
                        contributors = await client.get_repo_contributors(full_name, max_contributors=20)
                        for c in contributors:
                            login = c.get("login", "")
                            if login:
                                usernames.add(login)
                    except Exception:
                        pass

        return self._dedup_usernames(list(usernames))

    async def _mine_repo(self, client: GitHubClient, query: GitHubSearchQuery, progress: GitHubProgress) -> list[str]:
        """Mine contributors from a specific repository."""
        repo = query.target_repo
        if not repo:
            return []
        if repo in progress.mined_repos:
            print(f"    Skipping {repo} (already mined)")
            return []

        contributors = await client.get_repo_contributors(repo)
        progress.mined_repos.append(repo)

        return self._dedup_usernames([c.get("login", "") for c in contributors])

    async def _explore_org(self, client: GitHubClient, query: GitHubSearchQuery) -> list[str]:
        """Explore public members of an organization."""
        org = query.target_org
        if not org:
            return []

        members = await client.get_org_members(org)
        return self._dedup_usernames([m.get("login", "") for m in members])

    async def _search_topics(self, client: GitHubClient, query: GitHubSearchQuery) -> list[str]:
        """Search repos by topic, extract owner usernames."""
        total, items = await client.search_repos(query.query)
        usernames = set()
        for item in items:
            owner = item.get("owner", {}).get("login", "")
            if owner:
                usernames.add(owner)
        return self._dedup_usernames(list(usernames))

    async def _mine_stargazers(self, client: GitHubClient, query: GitHubSearchQuery) -> list[str]:
        """Mine stargazers from a specific repository."""
        repo = query.target_repo
        if not repo:
            return []
        stargazers = await client.get_stargazers(repo, max_results=gc.MAX_STARGAZERS_PER_REPO)
        usernames = [s.get("login", "") for s in stargazers]
        return self._dedup_usernames(usernames)

    async def _expand_graph(self, client: GitHubClient, query: GitHubSearchQuery, progress: GitHubProgress) -> list[str]:
        """Expand social graph from a seed username."""
        seed = query.query  # username stored in query field
        if not seed or seed in progress.graph_expansion_processed:
            return []

        followers = await client.get_followers(seed, max_results=gc.MAX_FOLLOWERS_PER_SEED)
        following = await client.get_following(seed, max_results=gc.MAX_FOLLOWERS_PER_SEED)

        usernames = set()
        for user in followers + following:
            login = user.get("login", "")
            if login:
                usernames.add(login)

        progress.graph_expansion_processed.append(seed)
        return self._dedup_usernames(list(usernames))

    # ------------------------------------------------------------------
    # Candidate processing
    # ------------------------------------------------------------------

    async def _process_candidate(
        self,
        enricher: GitHubEnricher,
        username: str,
        query: GitHubSearchQuery,
        progress: GitHubProgress,
        result_rank: int = 0,
    ):
        """Enrich and evaluate a single candidate."""
        progress.candidates_discovered += 1
        self.stats["candidates_discovered"] += 1

        # Enrich
        candidate = await enricher.enrich(
            username,
            source_strategy=query.channel,
            source_query=query.query or query.target_repo or query.target_org,
        )
        if not candidate:
            return

        # Merge contact info from profile
        candidate.contact = merge_profile_contact(
            candidate.contact,
            candidate.user.email,
            candidate.user.twitter_username,
            candidate.user.blog,
        )

        self._governor.record_enrichment()
        progress.candidates_enriched += 1
        self.stats["candidates_enriched"] += 1

        # Save raw candidate data
        append_jsonl(self.candidates_path, {
            "username": candidate.user.username,
            **candidate.to_dict(),
        })

        # Check data sufficiency
        if candidate.data_sufficiency == "insufficient":
            self.stats["insufficient"] += 1
            progress.candidates_insufficient += 1
            log_event(self.log_path, "insufficient_data", username=username)
            return

        # --- GitHub-native evaluation pipeline ---
        if self.brief_obj.has_v2_schema:
            # GitHub facial triage using portfolio text
            portfolio_text = candidate.to_portfolio_text()
            facial_decision = github_facial_judge(portfolio_text)
            facial_decision.candidate_name = candidate.user.name or username
            facial_decision.profile_url = candidate.user.profile_url
        else:
            # Fallback to LinkedIn-style facial (old briefs)
            snippet = candidate.to_snippet(
                source_string_id=query.id,
                source_string_name=query.name,
                result_rank=result_rank,
            )
            append_jsonl(self.snippets_path, snippet.to_dict())
            facial_decision = facial_judge(snippet)

        append_jsonl(self.facial_path, facial_decision.to_dict())

        if self._bias_monitor:
            self._bias_monitor.record(DecisionRecord(
                stage="facial",
                decision=facial_decision.decision,
                string_id=query.id,
            ))

        if facial_decision.decision == "FACIAL_NO":
            self.stats["facial_no"] += 1
            print(f"    ✗ {candidate.user.name or username} — FACIAL_NO ({facial_decision.rationale[:60]})")
            return

        self.stats["facial_yes"] += 1
        print(f"    → {candidate.user.name or username} — FACIAL_YES, evaluating full profile...")

        # Full evaluation
        if self.brief_obj.has_v2_schema:
            evidence_text = candidate.to_evidence_text()
            full_decision = github_full_judge(evidence_text)
            full_decision.candidate_name = candidate.user.name or username
            full_decision.profile_url = candidate.user.profile_url
        else:
            profile_summary = candidate.to_profile_summary()
            append_jsonl(self.profiles_path, profile_summary.to_dict())
            full_decision = full_judge(profile_summary)

        append_jsonl(self.final_path, full_decision.to_dict())

        if self._bias_monitor:
            self._bias_monitor.record(DecisionRecord(
                stage="full",
                decision=full_decision.decision,
                string_id=query.id,
            ))

        if full_decision.decision in ("SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE"):
            self.stats["saved"] += 1
            progress.candidates_saved += 1
            query.saves.append(candidate.user.name or username)
            contact_str = ", ".join(candidate.contact.emails[:2]) if candidate.contact.emails else "no email"
            print(f"    ✓ SAVE: {candidate.user.name or username} ({full_decision.confidence:.2f}) — {contact_str}")
            log_event(self.log_path, "save",
                      username=username,
                      name=candidate.user.name,
                      confidence=full_decision.confidence,
                      path=full_decision.path,
                      contact_emails=candidate.contact.emails,
                      query_id=query.id)

            # Generate and store outreach copy
            try:
                outreach = await generate_outreach(candidate, self.brief_obj, full_decision)
                if outreach:
                    candidate.outreach_copy = outreach
                    append_jsonl(self.outreach_path, outreach)
            except Exception as e:
                print(f"    [warn] Outreach generation failed: {e}")

            # Add to graph expansion queue
            import datetime
            progress.graph_expansion_queue.append({
                "username": username,
                "reason": full_decision.decision,
                "confidence": full_decision.confidence,
                "capability_area": full_decision.path,
                "added_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
        else:
            self.stats["rejected"] += 1
            progress.candidates_rejected += 1
            print(f"    ✗ REJECT: {candidate.user.name or username} ({full_decision.rationale[:60]})")

        # Checkpoint periodically
        if (progress.candidates_enriched % _CHECKPOINT_EVERY) == 0:
            self._save_progress()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _process_graph_expansion_queue(
        self,
        progress: GitHubProgress,
        queries: list[GitHubSearchQuery],
    ):
        """Process the graph expansion queue — add follower/following queries."""
        # Pick top seeds by confidence
        unprocessed = [
            entry for entry in progress.graph_expansion_queue
            if entry["username"] not in progress.graph_expansion_processed
        ]
        if not unprocessed:
            return

        # Sort by confidence, take top 5
        unprocessed.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        seeds = unprocessed[:5]

        next_id = max((q.id for q in queries), default=0) + 1
        new_count = 0
        for seed in seeds:
            username = seed["username"]
            queries.append(GitHubSearchQuery(
                id=next_id,
                name=f"Graph expansion: followers/following of {username}",
                query=username,
                channel="graph_expansion",
            ))
            next_id += 1
            new_count += 1

        if new_count:
            print(f"  [graph] Queued {new_count} expansion queries from saved candidates")
        progress.queries = queries

    def _dedup_usernames(self, usernames: list[str]) -> list[str]:
        """Filter out already-seen usernames."""
        new = []
        for u in usernames:
            if u and u not in self._seen_usernames:
                self._seen_usernames.add(u)
                new.append(u)
        return new

    def _load_or_create_progress(self, resume: bool = False) -> GitHubProgress:
        if resume and self.progress_path.exists():
            try:
                progress = GitHubProgress.from_file(str(self.progress_path))
                self._seen_usernames.update(progress.discovered_usernames)
                print(f"  Resumed: {progress.candidates_saved} saves, {progress.candidates_enriched} enriched")
                return progress
            except Exception as e:
                print(f"  [warn] Could not resume: {e}")

        return GitHubProgress(brief_name=self.brief_obj.id)

    def _save_progress(self):
        if self._progress:
            self._progress.discovered_usernames = list(self._seen_usernames)
            self._progress.api_calls_made = self._governor.api_calls_session
            self._progress.save(str(self.progress_path))

    def _build_batch_report(self, batch_stats: list[dict]) -> GitHubBatchReport:
        report = GitHubBatchReport(
            batch_name=f"Batch ({len(batch_stats)} queries)",
            queries_run=len(batch_stats),
            queries_with_saves=sum(1 for s in batch_stats if s["saves"] > 0),
            total_candidates_discovered=sum(s["candidates"] for s in batch_stats),
            total_saves=sum(s["saves"] for s in batch_stats),
            top_performing_queries=[s for s in batch_stats if s["saves"] > 0],
            zero_save_query_ids=[s["query_id"] for s in batch_stats if s["saves"] == 0],
        )
        return report

    def _install_signal_handler(self):
        def _handler(sig, frame):
            if self._shutdown_requested:
                print("\n[shutdown] Force exit!")
                sys.exit(1)
            self._shutdown_requested = True
            print("\n[shutdown] Graceful shutdown requested — finishing current candidate...")
        signal.signal(signal.SIGINT, _handler)

    def _print_summary(self):
        print("\n" + "=" * 60)
        print("GitHub Sourcing Pipeline — Summary")
        print("=" * 60)
        print(f"  Candidates discovered:  {self.stats['candidates_discovered']}")
        print(f"  Candidates enriched:    {self.stats['candidates_enriched']}")
        print(f"  Insufficient data:      {self.stats['insufficient']}")
        print(f"  Facial YES:             {self.stats['facial_yes']}")
        print(f"  Facial NO:              {self.stats['facial_no']}")
        print(f"  SAVED:                  {self.stats['saved']}")
        print(f"  REJECTED:               {self.stats['rejected']}")
        if self.stats['facial_yes'] > 0:
            precision = self.stats['saved'] / self.stats['facial_yes'] * 100
            print(f"  Save rate (of FACIAL_YES): {precision:.1f}%")
        print(f"\n  Output: {self.output_dir}")
        print("=" * 60)
