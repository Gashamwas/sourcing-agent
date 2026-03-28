"""GitHub sourcing pipeline orchestrator.

Connects: strategy → multi-channel search → enrichment → evaluation → save.
No browser needed — pure API-based. Mirrors orchestrator.py's Pipeline pattern.

Usage:
    pipeline = GitHubPipeline(brief_path="config/brief-fdl-brazil-v3.json")
    await pipeline.run()
"""

from __future__ import annotations

import asyncio
import datetime
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
from github.query_validator import ExhaustionState
from github.observability import SessionObserver
from shared.contact_discovery import merge_profile_contact

from shared.schemas import CandidateSnippet, CandidateProfileSummary, OpusDecision
from shared.judger import facial_judge, full_judge, init_judger, github_facial_judge, github_full_judge, extract_priority_rank
from github.outreach import generate_outreach
from shared.storage import append_jsonl, read_jsonl_set, log_event
from shared.brief_loader import load_brief, Brief
from shared.bias_controls import BiasMonitor, DecisionRecord
import github.config as gc


# Adaptation batch size — run adaptation after this many queries
_ADAPTATION_BATCH_SIZE = 10

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
        self.saves_path = self.output_dir / "saves.jsonl"

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

        # Exhaustion state
        self._exhaustion = ExhaustionState()

        # Client reference (set during run)
        self._client: Optional[GitHubClient] = None

        # Observer
        self._observer: Optional[SessionObserver] = None

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
        # Create session observer
        session_ts = time.strftime("%Y%m%d_%H%M%S")
        session_id = f"{self.brief_obj.id}_{session_ts}"
        self._observer = SessionObserver(session_id, self.output_dir, self.brief_obj)

        # Load dedup cache
        self._seen_usernames = read_jsonl_set(self.candidates_path, key="username")

        # Load or create progress
        progress = self._load_or_create_progress(resume)
        self._progress = progress

        # Install Ctrl+C handler
        self._install_signal_handler()

        log_event(self.log_path, "pipeline_start", mode="autonomous")

        async with GitHubClient() as client:
            self._client = client
            enricher = GitHubEnricher(client, brief=self.brief_obj)

            # Step 1: Strategy (if not resuming with existing queries)
            if not progress.queries or not resume:
                queries, rationale = form_github_strategy(self.brief_obj)
                progress.queries = queries
                self._save_progress()
                self._observer.on_strategy_formed(queries, rationale)
            else:
                self._observer.console.emit_info(
                    f"Resuming with {len(progress.queries)} queries from checkpoint"
                )

            self._observer.on_session_start(self.brief_obj, len(progress.queries))

            # Step 2: Execute queries
            try:
                await self._execute_queries(client, enricher, progress)
            except GitHubGovernorLimitReached as e:
                self._observer.console.emit_info(f"Governor limit reached: {e.reason}")
            except KeyboardInterrupt:
                self._observer.console.emit_info("Graceful shutdown — saving progress...")
            except Exception as e:
                self._observer.on_error("pipeline", e)
                import traceback
                traceback.print_exc()
            finally:
                self._save_progress()
                log_event(self.log_path, "pipeline_end", stats=self.stats)

        self._client = None

        # Session end — writes all layer files + report
        bias_summary = None
        self.stats["api_status"] = self._get_api_status()
        self._observer.on_session_end(self.stats, progress, bias_summary)

        # Export CSV for Gem/Greenhouse import
        if self.stats["saved"] > 0:
            try:
                from github.export import export_saved_candidates_csv
                csv_path = export_saved_candidates_csv(self.output_dir)
                self._observer.console.emit_info(f"CSV export: {csv_path}")
            except Exception as e:
                self._observer.console.emit_warn(f"CSV export failed: {e}")

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

            # Skip exhausted channel queries
            channel_stats = self._exhaustion.channels.get(query.channel)
            if channel_stats and channel_stats.status == "exhausted":
                query.status = "skipped"
                query.notes = f"Channel {query.channel} exhausted"
                self._observer.console.emit_info(
                    f"Skipping query #{query.id} — channel {query.channel} exhausted"
                )
                continue

            # Check governor limits
            self._governor.check_limits_or_raise()

            # Check if we should enter enrichment-only mode
            if self._governor.should_enter_enrichment_only(client.limiter.remaining("rest")):
                self._observer.on_enrichment_only_mode()
                break

            # Query start
            session_stats = {
                **self.stats,
                "total_queries": len(queries),
            }
            api_status = self._get_api_status()
            self._observer.on_query_start(query, session_stats, api_status)

            query.status = "in_progress"
            progress.current_query_id = query.id

            try:
                await self._execute_single_query(client, enricher, query, progress)
            except GitHubGovernorLimitReached:
                raise
            except Exception as e:
                self._observer.on_error("query", e, query)
                query.notes = f"Error: {e}"

            query.status = "done"
            batch_stats.append({
                "query_id": query.id,
                "name": query.name,
                "query_string": query.query,
                "channel": query.channel,
                "saves": len(query.saves),
                "candidates": query.candidates_discovered,
            })

            # Record result in exhaustion state
            pre_dedup = getattr(query, '_pre_dedup_count', query.result_count)
            self._exhaustion.record_query_result(
                channel=query.channel,
                saves=len(query.saves),
                candidates=query.candidates_discovered,
                pre_dedup=pre_dedup,
                post_dedup=query.result_count,
            )

            self._save_progress()

            # Adaptation after batch
            if (i - batch_start_idx + 1) >= _ADAPTATION_BATCH_SIZE:
                remaining = [q for q in queries if q.status == "queued"]
                if remaining:
                    batch_report = self._build_batch_report(batch_stats)
                    new_queries, rationale, skipped_ids = adapt_after_batch(
                        self.brief_obj, batch_report, remaining,
                        executed_queries=self._get_executed_query_strings(),
                        exhaustion_context=self._exhaustion.to_adaptation_context(),
                    )
                    if new_queries:
                        self._insert_queries_by_priority(queries, new_queries, i)
                        progress.queries = queries

                    self._observer.on_adaptation(
                        batch_report, new_queries, skipped_ids, rationale, self.stats
                    )

                    # Metrics checkpoint at adaptation time — act on stop signal
                    api_status = self._get_api_status()
                    stop_rec = self._observer.write_metrics_checkpoint(api_status, self.stats)
                    if stop_rec and stop_rec.startswith("STOP"):
                        self._observer.console.emit_info(f"Session stop: {stop_rec}")
                        return

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
        pre_dedup_count = 0

        if query.channel == "user_search":
            pre_dedup_count, usernames = await self._search_users(client, query)
        elif query.channel == "code_search":
            pre_dedup_count, usernames = await self._search_code(client, query)
        elif query.channel == "repo_mining":
            pre_dedup_count, usernames = await self._mine_repo(client, query, progress)
        elif query.channel == "org_exploration":
            pre_dedup_count, usernames = await self._explore_org(client, query)
        elif query.channel == "topic_search":
            pre_dedup_count, usernames = await self._search_topics(client, query)
        elif query.channel == "stargazer_mining":
            pre_dedup_count, usernames = await self._mine_stargazers(client, query)
        elif query.channel == "graph_expansion":
            pre_dedup_count, usernames = await self._expand_graph(client, query, progress)

        query.result_count = len(usernames)
        query.candidates_discovered = len(usernames)
        # Store pre-dedup count for exhaustion tracking
        query._pre_dedup_count = pre_dedup_count
        self._observer.on_query_results(query, usernames, pre_dedup_count)

        # Process each candidate with mid-query adaptation
        stats_before = {k: v for k, v in self.stats.items()}
        for j, username in enumerate(usernames):
            if self._shutdown_requested:
                break
            self._governor.check_limits_or_raise()

            self._observer.on_candidate_discovered(username, query)

            try:
                await self._process_candidate(
                    enricher, username, query, progress,
                    result_rank=j + 1,
                )
            except GitHubGovernorLimitReached:
                raise
            except Exception as e:
                self._observer.on_error("candidate", e, query)
                continue

            # Mid-query adaptation checkpoint every 25 candidates
            processed = j + 1
            if processed % 25 == 0 and processed < len(usernames):
                query_stats = {
                    k: self.stats[k] - stats_before.get(k, 0)
                    for k in ("saved", "rejected", "facial_yes", "facial_no")
                }
                query_stats["processed"] = processed
                query_stats["geo_filtered"] = self.stats.get("geo_filtered", 0) - stats_before.get("geo_filtered", 0)
                if self._should_stop_query(query_stats):
                    evaluated = processed - query_stats["geo_filtered"]
                    reason = f"{evaluated} evaluated, {query_stats['saved']} saves, {query_stats['facial_yes']} facial_yes"
                    self._observer.on_query_stopped_early(query, reason, processed, len(usernames))
                    break

        # Per-query summary
        if usernames:
            qd = {k: self.stats.get(k, 0) - stats_before.get(k, 0)
                  for k in ("candidates_discovered", "geo_filtered", "insufficient", "facial_no", "facial_yes", "saved", "rejected")}
            qd["found"] = len(usernames)
            self._observer.on_query_end(query, qd)

    # ------------------------------------------------------------------
    # Search channel implementations
    # ------------------------------------------------------------------

    async def _search_users(self, client: GitHubClient, query: GitHubSearchQuery) -> tuple[int, list[str]]:
        """Execute a user search query. Returns (pre_dedup_count, deduplicated usernames)."""
        total, items = await client.search_users(query.query)
        query.hit_result_cap = total > gc.MAX_RESULTS_PER_QUERY
        if query.hit_result_cap:
            self._observer.on_result_cap(query, total)

        all_logins = [item.get("login", "") for item in items]
        deduped = self._dedup_usernames(all_logins)
        return len(all_logins), deduped

    async def _search_code(self, client: GitHubClient, query: GitHubSearchQuery) -> tuple[int, list[str]]:
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

        all_usernames = list(usernames)
        deduped = self._dedup_usernames(all_usernames)
        return len(all_usernames), deduped

    async def _mine_repo(self, client: GitHubClient, query: GitHubSearchQuery, progress: GitHubProgress) -> tuple[int, list[str]]:
        """Mine contributors from a specific repository."""
        repo = query.target_repo
        if not repo:
            return 0, []
        if repo in progress.mined_repos:
            return 0, []

        contributors = await client.get_repo_contributors(repo)
        progress.mined_repos.append(repo)

        all_logins = [c.get("login", "") for c in contributors]
        deduped = self._dedup_usernames(all_logins)
        return len(all_logins), deduped

    async def _explore_org(self, client: GitHubClient, query: GitHubSearchQuery) -> tuple[int, list[str]]:
        """Explore public members of an organization."""
        org = query.target_org
        if not org:
            return 0, []

        members = await client.get_org_members(org)
        all_logins = [m.get("login", "") for m in members]
        deduped = self._dedup_usernames(all_logins)
        return len(all_logins), deduped

    async def _search_topics(self, client: GitHubClient, query: GitHubSearchQuery) -> tuple[int, list[str]]:
        """Search repos by topic, extract owner usernames."""
        total, items = await client.search_repos(query.query)
        usernames = set()
        for item in items:
            owner = item.get("owner", {}).get("login", "")
            if owner:
                usernames.add(owner)
        all_usernames = list(usernames)
        deduped = self._dedup_usernames(all_usernames)
        return len(all_usernames), deduped

    async def _mine_stargazers(self, client: GitHubClient, query: GitHubSearchQuery) -> tuple[int, list[str]]:
        """Mine stargazers from a specific repository."""
        repo = query.target_repo
        if not repo:
            return 0, []
        stargazers = await client.get_stargazers(repo, max_results=gc.MAX_STARGAZERS_PER_REPO)
        all_logins = [s.get("login", "") for s in stargazers]
        deduped = self._dedup_usernames(all_logins)
        return len(all_logins), deduped

    async def _expand_graph(self, client: GitHubClient, query: GitHubSearchQuery, progress: GitHubProgress) -> tuple[int, list[str]]:
        """Expand social graph from a seed username."""
        seed = query.query  # username stored in query field
        if not seed or seed in progress.graph_expansion_processed:
            return 0, []

        followers = await client.get_followers(seed, max_results=gc.MAX_FOLLOWERS_PER_SEED)
        following = await client.get_following(seed, max_results=gc.MAX_FOLLOWERS_PER_SEED)

        usernames = set()
        for user in followers + following:
            login = user.get("login", "")
            if login:
                usernames.add(login)

        progress.graph_expansion_processed.append(seed)
        all_usernames = list(usernames)
        deduped = self._dedup_usernames(all_usernames)
        return len(all_usernames), deduped

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
        """Enrich and evaluate a single candidate.

        For non-user_search channels (code_search, repo_mining, stargazer_mining,
        etc.), uses a light enrichment path: fetch only the user profile first,
        check geography, and only do full enrichment if the candidate passes.
        This avoids wasting ~10 API calls per geo-filtered candidate.
        """
        progress.candidates_discovered += 1
        self.stats["candidates_discovered"] += 1

        source_query = query.query or query.target_repo or query.target_org

        # --- Light enrich + pre-screen for all channels ---
        # For non-user_search: light enrich → geo gate → prescreen → full enrich
        # For user_search: light enrich → prescreen → full enrich (API already geo-filters)
        candidate = await enricher.light_enrich(
            username,
            source_strategy=query.channel,
            source_query=source_query,
        )
        if not candidate:
            return

        # Geography gate (skipped for user_search — API already handles it)
        if query.channel != "user_search":
            if not self._passes_geography_check(candidate, query):
                self.stats.setdefault("geo_filtered", 0)
                self.stats["geo_filtered"] += 1
                self.stats.setdefault("geo_filtered_light", 0)
                self.stats["geo_filtered_light"] += 1
                self._observer.on_geo_filtered(username, candidate.user.location or "no location", query, "light")
                return

        # Rule-based pre-screen using light data only
        prescreen = self._prescreen_light(candidate)
        if prescreen == "hard_skip":
            self.stats.setdefault("prescreen_filtered", 0)
            self.stats["prescreen_filtered"] += 1
            self._observer.on_prescreen_filtered(username, candidate, query)
            return

        # Full enrichment
        candidate = await enricher.full_enrich(candidate)

        # Merge contact info from profile
        candidate.contact = merge_profile_contact(
            candidate.contact,
            candidate.user.email,
            candidate.user.twitter_username,
            candidate.user.blog,
        )

        self._governor.record_enrichment()
        self._observer.on_enrichment()
        progress.candidates_enriched += 1
        self.stats["candidates_enriched"] += 1

        # Save raw candidate data
        append_jsonl(self.candidates_path, {
            "username": candidate.user.username,
            **candidate.to_dict(),
        })

        # Geography gate — catch any remaining edge cases (e.g. secondary proxy
        # signals that only appear after full enrichment)
        if not self._passes_geography_check(candidate, query):
            self.stats.setdefault("geo_filtered", 0)
            self.stats["geo_filtered"] += 1
            self._observer.on_geo_filtered(username, candidate.user.location or "no location", query, "full")
            return

        # Check data sufficiency
        if candidate.data_sufficiency == "insufficient":
            self.stats["insufficient"] += 1
            progress.candidates_insufficient += 1
            log_event(self.log_path, "insufficient_data", username=username)
            self._observer.on_insufficient_data(username, query)
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
            self._bias_monitor.record_decision(DecisionRecord(
                candidate_id=username,
                stage="facial",
                decision=facial_decision.decision,
                confidence=1.0,
                capability_area=None,
                string_id=str(query.id),
            ))

        if facial_decision.decision == "FACIAL_NO":
            self.stats["facial_no"] += 1
            self._observer.on_facial_decision(username, "FACIAL_NO", facial_decision.rationale, query)
            return

        self.stats["facial_yes"] += 1
        self._observer.on_facial_decision(username, "FACIAL_YES", "", query)

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
            self._bias_monitor.record_decision(DecisionRecord(
                candidate_id=username,
                stage="full",
                decision=full_decision.decision,
                confidence=full_decision.confidence,
                capability_area=getattr(full_decision, 'path', None),
                string_id=str(query.id),
            ))

        if full_decision.decision in ("SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE", "SIGNAL_SAVE"):
            self.stats["saved"] += 1
            progress.candidates_saved += 1
            query.saves.append(candidate.user.name or username)

            self._observer.on_save(username, candidate, full_decision, query)

            log_event(self.log_path, "save",
                      username=username,
                      name=candidate.user.name,
                      confidence=full_decision.confidence,
                      decision_path=full_decision.path,
                      contact_emails=candidate.contact.emails,
                      query_id=query.id)

            # Generate and store outreach copy
            outreach = await generate_outreach(candidate, self.brief_obj, full_decision)
            if outreach and outreach.get("message"):
                candidate.outreach_copy = outreach
                append_jsonl(self.outreach_path, outreach)
            else:
                self.stats.setdefault("outreach_failures", 0)
                self.stats["outreach_failures"] += 1
                self._observer.on_outreach_failure(username, query)

            # Write consolidated save record
            priority_rank = extract_priority_rank(full_decision.path)
            append_jsonl(self.saves_path, {
                "username": username,
                "name": candidate.user.name,
                "github_url": candidate.user.profile_url,
                "location": candidate.user.location,
                "bio": candidate.user.bio,
                "company": candidate.user.company,
                "emails": candidate.contact.emails,
                "blog": candidate.user.blog,
                "twitter": candidate.user.twitter_username,
                "decision": full_decision.decision,
                "confidence": full_decision.confidence,
                "decision_path": full_decision.path,
                "priority_rank": priority_rank,
                "rationale": full_decision.rationale,
                "outreach": candidate.outreach_copy if candidate.outreach_copy else None,
                "source_query": query.name,
                "source_channel": query.channel,
                "expansion_seed": query.query if query.channel == "graph_expansion" else None,
            })

            # Add to graph expansion queue (only above confidence threshold)
            if full_decision.confidence >= gc.GRAPH_EXPANSION_MIN_CONFIDENCE:
                progress.graph_expansion_queue.append({
                    "username": username,
                    "reason": full_decision.decision,
                    "confidence": full_decision.confidence,
                    "capability_area": full_decision.path,
                    "added_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                })
                self._observer.on_graph_expansion_queued(
                    username, full_decision.confidence, full_decision.path
                )
        else:
            self.stats["rejected"] += 1
            progress.candidates_rejected += 1
            self._observer.on_reject(username, candidate, full_decision, query)

        # Checkpoint periodically
        if (progress.candidates_enriched % _CHECKPOINT_EVERY) == 0:
            self._save_progress()

    # ------------------------------------------------------------------
    # Pre-screen (rule-based, light data only)
    # ------------------------------------------------------------------

    def _prescreen_light(self, candidate: GitHubCandidate) -> str:
        """Rule-based pre-screen using light_enrich data only.

        Returns: "pass" | "hard_skip"
        """
        user = candidate.user

        # Organization account — never a person
        if user.account_type == "Organization":
            return "hard_skip"

        # Zero repos AND no bio — nothing to evaluate
        if user.public_repos == 0 and not user.bio:
            return "hard_skip"

        # Bio keyword scan: if bio exists but has zero overlap with
        # capability area key_terms + generic ML terms, and <3 repos
        if user.bio and user.public_repos < 3:
            bio_lower = user.bio.lower()
            has_signal = False
            # Check capability area key_terms from brief
            if self.brief_obj.has_v2_schema and self.brief_obj._new_brief:
                for ca in self.brief_obj._new_brief.capability_areas:
                    if any(t.lower() in bio_lower for t in ca.key_terms):
                        has_signal = True
                        break
            # Generic ML/research terms as fallback
            if not has_signal:
                generic = [
                    "ml", "machine learning", "ai", "artificial intelligence",
                    "data science", "deep learning", "nlp", "computer vision",
                    "research", "phd", "neural", "model", "training", "llm",
                ]
                has_signal = any(t in bio_lower for t in generic)
            if not has_signal:
                return "hard_skip"

        return "pass"

    # ------------------------------------------------------------------
    # Mid-query adaptation
    # ------------------------------------------------------------------

    @staticmethod
    def _should_stop_query(query_stats: dict) -> bool:
        """Heuristic: abandon a query mid-processing if signal is too low.

        Uses evaluated count (processed minus geo-filtered) so that queries
        with many geo-filtered candidates aren't prematurely abandoned.
        """
        processed = query_stats.get("processed", 0)
        geo_filtered = query_stats.get("geo_filtered", 0)
        evaluated = processed - geo_filtered
        saves = query_stats.get("saved", 0)
        facial_yes = query_stats.get("facial_yes", 0)

        # Zero saves after 50 evaluated candidates — abandon
        if evaluated >= 50 and saves == 0:
            return True
        # <2% save rate after 100 evaluated candidates — abandon
        if evaluated >= 100 and (saves / evaluated) < 0.02:
            return True
        # Zero facial_yes after 50 evaluated — extremely noisy query, abandon
        if evaluated >= 50 and facial_yes == 0:
            return True
        return False

    # ------------------------------------------------------------------
    # Geography filter
    # ------------------------------------------------------------------

    _GEO_KEYWORDS: dict[str, list[str]] = {
        "Brazil": [
            "brazil", "brasil", "são paulo", "sao paulo", "rio de janeiro",
            "belo horizonte", "curitiba", "porto alegre", "recife", "salvador",
            "brasília", "brasilia", "fortaleza", "campinas", "florianópolis",
            "florianopolis", "manaus", "belém", "belem", "goiânia", "goiania",
        ],
        "Colombia": [
            "colombia", "bogotá", "bogota", "medellín", "medellin", "cali",
            "barranquilla", "cartagena", "bucaramanga",
        ],
    }

    # Top-level domains that signal geography
    _GEO_TLDS: dict[str, list[str]] = {
        "Brazil": [".br", ".com.br"],
        "Colombia": [".co", ".com.co"],
    }

    # Well-known companies headquartered in each geography
    _GEO_COMPANIES: dict[str, list[str]] = {
        "Brazil": [
            "nubank", "itaú", "itau", "bradesco", "stone", "pagseguro",
            "totvs", "vtex", "ifood", "mercado livre", "mercadolivre",
            "globo", "magazineluiza", "magalu", "b3", "xp inc", "creditas",
            "loft", "quintoandar", "quinto andar", "picpay", "inter",
            "embraer", "petrobras", "vale", "ambev",
        ],
        "Colombia": [
            "rappi", "bancolombia", "ecopetrol", "grupo nutresa",
            "mercado libre colombia", "platzi",
        ],
    }

    # High-frequency Portuguese words distinct from Spanish/English
    _PORTUGUESE_MARKERS: list[str] = [
        "não", "você", "também", "projeto", "desenvolvimento",
        "trabalho", "sistema", "aplicação", "dados", "utilizado",
        "implementação", "funcionalidades", "configuração", "usuário",
        "através", "ainda", "pode", "sobre", "como", "para",
        "repositório", "construído", "ferramenta", "objetivo",
        "ambiente", "executar", "utilizar", "necessário",
    ]

    def _passes_geography_check(
        self, candidate: GitHubCandidate, query: GitHubSearchQuery
    ) -> bool:
        """Check if a candidate's location matches the brief's target geography.

        Uses a multi-signal approach:
        1. User search channel → always pass (API already filters)
        2. Location field matches geo keywords → pass
        3. Location field explicitly non-matching → reject
        4. Location blank → check secondary proxies (bio, blog TLD, email
           domain, company, Portuguese text in repos/README) → pass if ANY
           matches, reject if none
        """
        # User search already filters by location at the API level
        if query.channel == "user_search":
            return True

        # No geography requirement in brief → pass everyone
        geo = ""
        if self.brief_obj.has_v2_schema and self.brief_obj._new_brief:
            geo = getattr(self.brief_obj._new_brief, "geography", "")
        if not geo:
            geo = self.brief_obj.permanent_filters.get("Location", "")
        if not geo:
            return True

        keywords = self._GEO_KEYWORDS.get(geo, [geo.lower()])

        location = (candidate.user.location or "").lower().strip()
        if location:
            # Location is set — check if it matches
            if any(kw in location for kw in keywords):
                return True
            # Explicitly non-matching location → reject
            return False

        # --- Location is blank — check secondary proxies ---

        # Bio mentions country/city
        bio = (candidate.user.bio or "").lower()
        if bio and any(kw in bio for kw in keywords):
            return True

        # Blog has country TLD
        blog = (candidate.user.blog or "").lower()
        if blog:
            tlds = self._GEO_TLDS.get(geo, [])
            if any(blog.rstrip("/").endswith(tld) or f"{tld}/" in blog for tld in tlds):
                return True

        # Email has country TLD
        if candidate.contact and candidate.contact.emails:
            tlds = self._GEO_TLDS.get(geo, [])
            for email in candidate.contact.emails:
                if any(email.lower().endswith(tld) for tld in tlds):
                    return True

        # Company matches known geo companies
        company = (candidate.user.company or "").lower().strip().lstrip("@")
        if company:
            geo_companies = self._GEO_COMPANIES.get(geo, [])
            if any(co_name in company for co_name in geo_companies):
                return True

        # Portuguese text detection (for Brazil)
        if geo == "Brazil" and self._has_portuguese_text(candidate):
            return True

        # No secondary signal found → reject
        return False

    def _has_portuguese_text(self, candidate: GitHubCandidate) -> bool:
        """Check if candidate's repos, README, or bio contain Portuguese text.

        Scans repo names/descriptions, profile README, and repo READMEs for
        high-frequency Portuguese words that are distinct from Spanish/English.
        Requires at least 2 marker hits to reduce false positives.
        """
        text_parts: list[str] = []

        # Repo names and descriptions
        for repo in candidate.top_repos:
            if repo.description:
                text_parts.append(repo.description.lower())
            text_parts.append(repo.name.lower().replace("-", " ").replace("_", " "))

        # Profile README
        if candidate.readme_text:
            text_parts.append(candidate.readme_text[:3000].lower())

        # Repo READMEs
        for readme in candidate.repo_readmes.values():
            if readme:
                text_parts.append(readme[:2000].lower())

        combined = " ".join(text_parts)
        if not combined:
            return False

        hits = sum(1 for marker in self._PORTUGUESE_MARKERS if marker in combined)
        return hits >= 2

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _process_graph_expansion_queue(
        self,
        progress: GitHubProgress,
        queries: list[GitHubSearchQuery],
    ):
        """Process the graph expansion queue — add follower/following queries.

        Uses _insert_queries_by_priority so expansion queries get interleaved
        after user_search queries rather than appended to the end of the queue.
        """
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
        new_queries = []
        for seed in seeds:
            username = seed["username"]
            new_queries.append(GitHubSearchQuery(
                id=next_id,
                name=f"Graph expansion: followers/following of {username}",
                query=username,
                channel="graph_expansion",
            ))
            next_id += 1

        if new_queries:
            # Find current execution position
            current_idx = max(
                (i for i, q in enumerate(queries) if q.status in ("done", "in_progress")),
                default=0,
            )
            self._insert_queries_by_priority(queries, new_queries, current_idx)
            self._observer.on_graph_expansion_processed(seeds, len(new_queries))
        progress.queries = queries

    @staticmethod
    def _insert_queries_by_priority(
        queries: list[GitHubSearchQuery],
        new_queries: list[GitHubSearchQuery],
        current_index: int,
    ):
        """Insert new queries with three priority tiers.

        Tier 1 (head): user_search — highest efficiency, geo-targeted.
        Tier 2 (after user_search): graph_expansion — known-good seeds.
        Tier 3 (tail): everything else (code_search, repo_mining, etc.).
        """
        geo_queries = [q for q in new_queries if q.channel == "user_search"]
        graph_queries = [q for q in new_queries if q.channel == "graph_expansion"]
        global_queries = [q for q in new_queries
                          if q.channel not in ("user_search", "graph_expansion")]

        # Find insertion point: first queued query after current_index
        insert_at = current_index + 1
        while insert_at < len(queries) and queries[insert_at].status != "queued":
            insert_at += 1

        # Insert geo queries at head
        for j, q in enumerate(geo_queries):
            queries.insert(insert_at + j, q)

        # Insert graph queries immediately after geo queries
        graph_insert = insert_at + len(geo_queries)
        for j, q in enumerate(graph_queries):
            queries.insert(graph_insert + j, q)

        # Append global queries at the end
        queries.extend(global_queries)

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
                return progress
            except Exception:
                pass

        return GitHubProgress(brief_name=self.brief_obj.id)

    def _save_progress(self):
        if self._progress:
            self._progress.discovered_usernames = list(self._seen_usernames)
            if self._client:
                self._progress.api_calls_made = self._client.limiter.total_calls
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
            query_details=[
                {
                    "query_id": s["query_id"],
                    "name": s["name"],
                    "query_string": s.get("query_string", ""),
                    "channel": s.get("channel", ""),
                    "saves": s["saves"],
                    "candidates": s["candidates"],
                }
                for s in batch_stats
            ],
        )
        return report

    def _get_executed_query_strings(self) -> set[str]:
        """Collect all query strings that have been executed."""
        if not self._progress:
            return set()
        return {
            q.query.lower().strip()
            for q in self._progress.queries
            if q.status in ("done", "in_progress") and q.query
        }

    def _get_api_status(self) -> dict:
        """Get current API budget status from client."""
        if self._client:
            return {
                "rest": self._client.limiter.remaining("rest"),
                "search": self._client.limiter.remaining("search"),
                "code_search": self._client.limiter.remaining("code_search"),
            }
        return {"rest": 0, "search": 0, "code_search": 0}

    def _install_signal_handler(self):
        def _handler(sig, frame):
            if self._shutdown_requested:
                print("\n[shutdown] Force exit!")
                sys.exit(1)
            self._shutdown_requested = True
            if self._observer:
                self._observer.console.emit_info("Graceful shutdown requested — finishing current candidate...")
            else:
                print("\n[shutdown] Graceful shutdown requested — finishing current candidate...")
        signal.signal(signal.SIGINT, _handler)
