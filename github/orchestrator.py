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

from github.client import GitHubAuthError, GitHubClient
from github.acquisition import GitHubAcquisitionService
from github.enricher import GitHubEnricher
from github.schemas import (
    GitHubCandidate,
    GitHubSearchQuery,
    GitHubProgress,
    GitHubBatchReport,
)
from github.side_effects import GitHubSideEffectsService
from github.strategy import form_github_strategy, adapt_after_batch
from github.work_units import GitHubWorkUnitService
from github.governor import (
    GitHubGovernor,
    GitHubGovernorLimitReached,
    GitHubSessionExpired,
)
from github.query_validator import ExhaustionState
from github.observability import SessionObserver
from shared.contact_discovery import merge_profile_contact
from shared.output_paths import resolve_github_state_dir

from shared.failures import judgment_failure_decision
from shared.execution import CandidateExecutionEngine
from shared.execution.types import CandidateExecutionEnvelope
from shared.runtime_state import GitHubRuntimeStateBridge, RuntimeStateLock, RuntimeStateStore
from shared.runtime_state.store import GITHUB_QUERY_KIND
from shared.safety import RunSafetyCoordinator, RunStopReason
from shared.schemas import CandidateSnippet, CandidateProfileSummary, OpusDecision
from shared.judger import facial_judge, full_judge, init_judger, github_facial_judge, github_facial_judge_batch, github_full_judge, extract_priority_rank, is_failure_decision
from github.outreach import generate_outreach
from shared.storage import append_jsonl, read_jsonl_set, log_event
from shared.brief_loader import load_brief, Brief
from shared.bias_controls import BiasMonitor, DecisionRecord
import github.config as gc


# Adaptation batch size — run adaptation after this many queries
_ADAPTATION_BATCH_SIZE = 10

# Checkpoint frequency — save progress after this many enrichments
_CHECKPOINT_EVERY = 10

# GitHub V2 facial batching — keep batches modest to avoid oversized prompts.
_GITHUB_FACIAL_BATCH_SIZE = 10


class GitHubPipeline:
    """Orchestrates the GitHub multi-model sourcing pipeline."""

    def __init__(
        self,
        brief_path: str,
        output_dir: Optional[str] = None,
    ):
        self.brief_path = str(brief_path)
        self.brief_obj = load_brief(brief_path)
        self.state_dir = resolve_github_state_dir(
            brief_path=self.brief_path,
            brief=self.brief_obj,
            state_dir=output_dir,
        )
        self.output_dir = self.state_dir
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
        self.runtime_db_path = self.output_dir / "runtime_state.sqlite3"

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
        self._runtime_state = RuntimeStateStore(self.runtime_db_path)
        self._runtime_lock = RuntimeStateLock(self.output_dir)
        self._runtime_run_id: Optional[int] = None
        self._runtime_bridge = GitHubRuntimeStateBridge(
            store=self._runtime_state,
            output_dir=self.output_dir,
            brief_id=self.brief_obj.id,
            brief_name=self.brief_obj.id,
            brief_path=self.brief_path,
        )
        self._execution_engine = CandidateExecutionEngine(
            store=self._runtime_state,
            output_dir=str(self.output_dir),
            brief_id=self.brief_obj.id,
            source="github",
        )
        self._safety = RunSafetyCoordinator(
            store=self._runtime_state,
            output_dir=self.output_dir,
            source="github",
            brief_id=self.brief_obj.id,
        )
        self._work_unit_service = GitHubWorkUnitService(self)
        self._acquisition_service = GitHubAcquisitionService(self)
        self._side_effects_service = GitHubSideEffectsService(self)

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
        self._ensure_runtime_state()
        self._ensure_services()

        # Create session observer
        session_ts = time.strftime("%Y%m%d_%H%M%S")
        session_id = f"{self.brief_obj.id}_{session_ts}"
        self._observer = SessionObserver(session_id, self.output_dir, self.brief_obj)

        # Dedup sets — _seen_usernames holds terminal outcomes only (loaded from
        # progress checkpoint on resume).  _in_flight_usernames tracks candidates
        # currently being processed and is deliberately NOT persisted.
        self._seen_usernames: set[str] = set()
        self._in_flight_usernames: set[str] = set()

        progress: Optional[GitHubProgress] = None
        run_status = "completed"
        stop_reason = RunStopReason.NORMAL
        lock_acquired = False

        try:
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

            # Load or create progress
            progress = self._load_or_create_progress(resume)
            self._progress = progress

            # Install Ctrl+C handler
            self._install_signal_handler()

            async with GitHubClient() as client:
                self._client = client
                await client.validate_credentials()

                log_event(self.log_path, "pipeline_start", mode="autonomous")
                self._governor.start_session()

                enricher = GitHubEnricher(
                    client,
                    brief=self.brief_obj,
                    safety_event_recorder=self._record_safety_event,
                )

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
                    if self._shutdown_requested:
                        run_status = "interrupted"
                        stop_reason = RunStopReason.OPERATOR_STOP
                except GitHubGovernorLimitReached as e:
                    run_status = "governor_limit_reached"
                    stop_reason = RunStopReason.GOVERNOR_LIMIT
                    if getattr(self, "_runtime_run_id", None):
                        self._safety.record_governor_limit(
                            run_id=self._runtime_run_id,
                            reason=e.reason,
                        )
                    self._observer.console.emit_info(f"Governor limit reached: {e.reason}")
                except KeyboardInterrupt:
                    run_status = "interrupted"
                    stop_reason = RunStopReason.OPERATOR_STOP
                    self._observer.console.emit_info("Graceful shutdown — saving progress...")
                except Exception as e:
                    run_status = "error"
                    stop_reason = RunStopReason.FATAL_RUNTIME_ERROR
                    self._observer.on_error("pipeline", e)
                    import traceback
                    traceback.print_exc()
                finally:
                    self._governor.end_session()
                    self._save_progress()
                    log_event(self.log_path, "pipeline_end", stats=self.stats)
        except GitHubAuthError as e:
            run_status = "error"
            stop_reason = RunStopReason.FATAL_RUNTIME_ERROR
            self._observer.on_error("github_auth", e)
            log_event(self.log_path, "github_auth_failed", error=str(e))
            raise
        finally:
            self._client = None
            if getattr(self, "_runtime_run_id", None):
                self._safety.finish_run(
                    run_id=self._runtime_run_id,
                    status=run_status,
                    stop_reason=stop_reason,
                )
            if lock_acquired:
                self._runtime_lock.release()

        # Session end — writes all layer files + report
        bias_summary = None
        self.stats["api_status"] = self._get_api_status()
        self._observer.on_session_end(self.stats, progress or GitHubProgress(brief_name=self.brief_obj.id), bias_summary)
        self._finalize_run_snapshot()

        # Export CSV for Gem/Greenhouse import
        if self.stats["saved"] > 0:
            self._side_effects_service.export_saved_candidates_csv()

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
        batch_stats: list[dict] = []
        executed_since_batch = 0

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
                self._save_progress()
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
            self._save_progress()

            try:
                await self._execute_single_query(client, enricher, query, progress)
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
            except GitHubGovernorLimitReached:
                raise
            except GitHubAuthError:
                raise
            except Exception as e:
                self._observer.on_error("query", e, query)
                query.notes = f"Error: {e}"
                query.status = "error"

            self._save_progress()
            executed_since_batch += 1

            # Adaptation after batch
            if executed_since_batch >= _ADAPTATION_BATCH_SIZE:
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

                executed_since_batch = 0
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
        if self.brief_obj.has_v2_schema:
            batch_candidates: list[tuple[str, GitHubCandidate]] = []

            for j, username in enumerate(usernames):
                if self._shutdown_requested:
                    break
                self._governor.check_limits_or_raise()

                self._observer.on_candidate_discovered(username, query)

                try:
                    candidate = await self._prepare_candidate_for_evaluation(
                        enricher, username, query, progress, result_rank=j + 1,
                    )
                except GitHubGovernorLimitReached:
                    raise
                except Exception as e:
                    self._observer.on_error("candidate", e, query)
                    continue

                if candidate:
                    batch_candidates.append((username, candidate))

                processed = j + 1
                should_flush = len(batch_candidates) >= _GITHUB_FACIAL_BATCH_SIZE
                if processed % 25 == 0 or processed == len(usernames):
                    should_flush = should_flush or bool(batch_candidates)

                if should_flush and batch_candidates:
                    await self._process_v2_candidates_batch(batch_candidates, query, progress)
                    batch_candidates = []

                # Mid-query adaptation checkpoint every 25 discovered candidates
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
        else:
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

    async def _prepare_candidate_for_evaluation(
        self,
        enricher: GitHubEnricher,
        username: str,
        query: GitHubSearchQuery,
        progress: GitHubProgress,
        result_rank: int = 0,
    ) -> GitHubCandidate | None:
        self._ensure_services()
        result = await self._acquisition_service.prepare_candidate_for_evaluation(
            enricher,
            username,
            query,
            progress,
            result_rank=result_rank,
        )
        return result.candidate

    async def _process_v2_candidates_batch(
        self,
        batch_candidates: list[tuple[str, GitHubCandidate]],
        query: GitHubSearchQuery,
        progress: GitHubProgress,
    ) -> None:
        """Batch the GitHub V2 facial stage, then run full eval sequentially."""
        portfolio_texts = [
            (candidate.user.name or username, candidate.user.profile_url, candidate.to_portfolio_text())
            for username, candidate in batch_candidates
        ]
        facial_decisions = github_facial_judge_batch(portfolio_texts, self.brief_obj)

        for (username, candidate), facial_decision in zip(batch_candidates, facial_decisions):
            try:
                candidate_record = self._candidate_record(candidate)
                envelope = self._execution_envelope(
                    username=username,
                    query=query,
                    result_rank=0,
                    candidate=candidate,
                    metadata={"candidate_record": candidate_record},
                )
                facial_decision.candidate_name = candidate.user.name or username
                facial_decision.profile_url = candidate.user.profile_url
                facial_attempt_id = self._start_stage_attempt(
                    username=username,
                    stage="facial",
                    query=query,
                    candidate=candidate,
                    result_rank=0,
                    payload={
                        "cursor": envelope.source_cursor,
                        "candidate_record": candidate_record,
                    },
                )

                if self._bias_monitor:
                    self._bias_monitor.record_decision(DecisionRecord(
                        candidate_id=username,
                        stage="facial",
                        decision=facial_decision.decision,
                        confidence=facial_decision.confidence,
                        capability_area=None,
                        string_id=str(query.id),
                    ))

                if is_failure_decision(facial_decision.decision):
                    self.stats.setdefault("parse_failures", 0)
                    self.stats["parse_failures"] += 1
                    self._finish_failure_decision_attempt(
                        attempt_id=facial_attempt_id,
                        username=username,
                        stage="facial",
                        decision=facial_decision,
                        query=query,
                        result_rank=0,
                        candidate=candidate,
                        candidate_record=candidate_record,
                    )
                    self._observer.on_facial_decision(username, facial_decision.decision, facial_decision.rationale, query)
                    continue

                if facial_decision.decision == "FACIAL_NO":
                    self.stats["facial_no"] += 1
                    self._execution_engine.runtime.finish_stage_success(
                        attempt_id=facial_attempt_id,
                        envelope=envelope,
                        stage="facial",
                        decision=facial_decision,
                        extra_payload={"candidate_record": candidate_record},
                    )
                    self._observer.on_facial_decision(username, "FACIAL_NO", facial_decision.rationale, query)
                    self._mark_terminal(username)
                    continue

                self.stats["facial_yes"] += 1
                self._execution_engine.runtime.finish_stage_success(
                    attempt_id=facial_attempt_id,
                    envelope=envelope,
                    stage="facial",
                    decision=facial_decision,
                    extra_payload={"candidate_record": candidate_record},
                )
                self._observer.on_facial_decision(username, "FACIAL_YES", "", query)

                evidence_text = candidate.to_evidence_text()
                full_attempt_id = self._start_stage_attempt(
                    username=username,
                    stage="full",
                    query=query,
                    candidate=candidate,
                    result_rank=0,
                    payload={
                        "cursor": envelope.source_cursor,
                        "candidate_record": candidate_record,
                        "facial_decision": facial_decision.to_dict(),
                    },
                )
                try:
                    full_decision = github_full_judge(evidence_text)
                except Exception as e:
                    full_decision = judgment_failure_decision(
                        stage="full",
                        candidate_name=candidate.user.name or username,
                        profile_url=candidate.user.profile_url,
                        error=e,
                        source="judgment",
                    )
                full_decision.candidate_name = candidate.user.name or username
                full_decision.profile_url = candidate.user.profile_url

                if self._bias_monitor:
                    self._bias_monitor.record_decision(DecisionRecord(
                        candidate_id=username,
                        stage="full",
                        decision=full_decision.decision,
                        confidence=full_decision.confidence,
                        capability_area=getattr(full_decision, "path", None),
                        string_id=str(query.id),
                    ))

                if is_failure_decision(full_decision.decision):
                    self.stats.setdefault("parse_failures", 0)
                    self.stats["parse_failures"] += 1
                    self._finish_failure_decision_attempt(
                        attempt_id=full_attempt_id,
                        username=username,
                        stage="full",
                        decision=full_decision,
                        query=query,
                        result_rank=0,
                        candidate=candidate,
                        candidate_record=candidate_record,
                    )
                    continue

                await self._side_effects_service.handle_full_decision(
                    username=username,
                    candidate=candidate,
                    query=query,
                    progress=progress,
                    full_decision=full_decision,
                    envelope=envelope,
                    full_attempt_id=full_attempt_id,
                )

                self._execution_engine.runtime.finish_stage_success(
                    attempt_id=full_attempt_id,
                    envelope=envelope,
                    stage="full",
                    decision=full_decision,
                    extra_payload={"candidate_record": candidate_record},
                )
                self._mark_terminal(username)

                if (progress.candidates_enriched % _CHECKPOINT_EVERY) == 0:
                    self._save_progress()
            except GitHubGovernorLimitReached:
                raise
            except Exception as e:
                self._observer.on_error("candidate", e, query)

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
        candidate = await self._prepare_candidate_for_evaluation(
            enricher, username, query, progress, result_rank=result_rank,
        )
        if not candidate:
            return

        # --- GitHub-native evaluation pipeline ---
        if self.brief_obj.has_v2_schema:
            # GitHub facial triage using portfolio text
            portfolio_text = candidate.to_portfolio_text()
            candidate_record = self._candidate_record(candidate)
            envelope = self._execution_envelope(
                username=username,
                query=query,
                result_rank=result_rank,
                candidate=candidate,
                metadata={"candidate_record": candidate_record},
            )
            facial_attempt_id = self._start_stage_attempt(
                username=username,
                stage="facial",
                query=query,
                candidate=candidate,
                result_rank=result_rank,
                payload={
                    "cursor": envelope.source_cursor,
                    "candidate_record": candidate_record,
                },
            )
            try:
                facial_decision = github_facial_judge(portfolio_text)
            except Exception as e:
                facial_decision = judgment_failure_decision(
                    stage="facial",
                    candidate_name=candidate.user.name or username,
                    profile_url=candidate.user.profile_url,
                    error=e,
                    source="judgment",
                )
            facial_decision.candidate_name = candidate.user.name or username
            facial_decision.profile_url = candidate.user.profile_url
        else:
            # Fallback to LinkedIn-style facial (old briefs)
            snippet = candidate.to_snippet(
                source_string_id=query.id,
                source_string_name=query.name,
                result_rank=result_rank,
            )
            candidate_record = self._candidate_record(candidate)
            envelope = self._execution_envelope(
                username=username,
                query=query,
                result_rank=result_rank,
                candidate=candidate,
                snippet=snippet,
                metadata={"candidate_record": candidate_record},
            )
            facial_attempt_id = self._start_stage_attempt(
                username=username,
                stage="facial",
                query=query,
                candidate=candidate,
                result_rank=result_rank,
                snippet=snippet,
                payload={
                    "cursor": envelope.source_cursor,
                    "candidate_record": candidate_record,
                    "snippet": snippet.to_dict(),
                },
            )
            try:
                facial_decision = facial_judge(snippet)
            except Exception as e:
                facial_decision = judgment_failure_decision(
                    stage="facial",
                    candidate_name=snippet.name,
                    profile_url=snippet.profile_url,
                    error=e,
                    source="judgment",
                )

        if self._bias_monitor:
            self._bias_monitor.record_decision(DecisionRecord(
                candidate_id=username,
                stage="facial",
                decision=facial_decision.decision,
                confidence=1.0,
                capability_area=None,
                string_id=str(query.id),
            ))

        if is_failure_decision(facial_decision.decision):
            self.stats.setdefault("parse_failures", 0)
            self.stats["parse_failures"] += 1
            self._finish_failure_decision_attempt(
                attempt_id=facial_attempt_id,
                username=username,
                stage="facial",
                decision=facial_decision,
                query=query,
                result_rank=result_rank,
                candidate=candidate,
                candidate_record=candidate_record,
                snippet=snippet if not self.brief_obj.has_v2_schema else None,
                extra_payload={"snippet": snippet.to_dict()} if not self.brief_obj.has_v2_schema else None,
            )
            self._observer.on_facial_decision(username, facial_decision.decision, facial_decision.rationale, query)
            return

        if facial_decision.decision == "FACIAL_NO":
            self.stats["facial_no"] += 1
            self._execution_engine.runtime.finish_stage_success(
                attempt_id=facial_attempt_id,
                envelope=envelope,
                stage="facial",
                decision=facial_decision,
                extra_payload={
                    "candidate_record": candidate_record,
                    **({"snippet": snippet.to_dict()} if not self.brief_obj.has_v2_schema else {}),
                },
            )
            self._observer.on_facial_decision(username, "FACIAL_NO", facial_decision.rationale, query)
            self._mark_terminal(username)
            return

        self.stats["facial_yes"] += 1
        self._execution_engine.runtime.finish_stage_success(
            attempt_id=facial_attempt_id,
            envelope=envelope,
            stage="facial",
            decision=facial_decision,
            extra_payload={
                "candidate_record": candidate_record,
                **({"snippet": snippet.to_dict()} if not self.brief_obj.has_v2_schema else {}),
            },
        )
        self._observer.on_facial_decision(username, "FACIAL_YES", "", query)

        # Full evaluation
        full_attempt_id = self._start_stage_attempt(
            username=username,
            stage="full",
            query=query,
            candidate=candidate,
            result_rank=result_rank,
            payload={
                "cursor": envelope.source_cursor,
                "candidate_record": candidate_record,
                "facial_decision": facial_decision.to_dict(),
            },
        )
        if self.brief_obj.has_v2_schema:
            evidence_text = candidate.to_evidence_text()
            try:
                full_decision = github_full_judge(evidence_text)
            except Exception as e:
                full_decision = judgment_failure_decision(
                    stage="full",
                    candidate_name=candidate.user.name or username,
                    profile_url=candidate.user.profile_url,
                    error=e,
                    source="judgment",
                )
            full_decision.candidate_name = candidate.user.name or username
            full_decision.profile_url = candidate.user.profile_url
        else:
            profile_summary = candidate.to_profile_summary()
            try:
                full_decision = full_judge(profile_summary)
            except Exception as e:
                full_decision = judgment_failure_decision(
                    stage="full",
                    candidate_name=profile_summary.name,
                    profile_url=profile_summary.profile_url,
                    error=e,
                    source="judgment",
                )

        if self._bias_monitor:
            self._bias_monitor.record_decision(DecisionRecord(
                candidate_id=username,
                stage="full",
                decision=full_decision.decision,
                confidence=full_decision.confidence,
                capability_area=getattr(full_decision, 'path', None),
                string_id=str(query.id),
            ))

        if is_failure_decision(full_decision.decision):
            self.stats.setdefault("parse_failures", 0)
            self.stats["parse_failures"] += 1
            self._finish_failure_decision_attempt(
                attempt_id=full_attempt_id,
                username=username,
                stage="full",
                decision=full_decision,
                query=query,
                result_rank=result_rank,
                candidate=candidate,
                candidate_record=candidate_record,
                snippet=snippet if not self.brief_obj.has_v2_schema else None,
                extra_payload={"profile_summary": profile_summary.to_dict()} if not self.brief_obj.has_v2_schema else None,
            )
            return

        self._execution_engine.runtime.finish_stage_success(
            attempt_id=full_attempt_id,
            envelope=envelope,
            stage="full",
            decision=full_decision,
            extra_payload={"candidate_record": candidate_record},
            profile_summary=profile_summary if not self.brief_obj.has_v2_schema else None,
        )
        self._mark_terminal(username)

        await self._side_effects_service.handle_full_decision(
            username=username,
            candidate=candidate,
            query=query,
            progress=progress,
            full_decision=full_decision,
            envelope=envelope,
            full_attempt_id=full_attempt_id,
        )

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
        self._ensure_services()
        await self._work_unit_service.process_graph_expansion_queue(progress, queries)

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

    def _mark_terminal(self, username: str):
        """Promote username from in-flight to permanent dedup."""
        self._in_flight_usernames.discard(username)
        self._seen_usernames.add(username)

    def _dedup_usernames(self, usernames: list[str]) -> list[str]:
        self._ensure_services()
        return self._work_unit_service.dedup_usernames(usernames)

    def _load_or_create_progress(self, resume: bool = False) -> GitHubProgress:
        self._ensure_services()
        return self._work_unit_service.load_or_create_progress(resume=resume)

    def _save_progress(self):
        self._ensure_services()
        self._work_unit_service.save_progress()

    def _finalize_run_snapshot(self) -> None:
        """Freeze the current state_dir into an immutable run_dir snapshot."""
        if not getattr(self, "_runtime_run_id", None):
            return
        try:
            from market_intelligence.run_snapshots import finalize_run_snapshot

            run_dir = finalize_run_snapshot(
                source="github",
                brief_path=self.brief_path,
                state_dir=self.state_dir,
                run_id=int(self._runtime_run_id),
            )
            log_event(
                self.log_path,
                "run_snapshot_finalized",
                run_id=int(self._runtime_run_id),
                run_dir=str(run_dir),
            )
            if self._observer:
                self._observer.console.emit_info(f"Run snapshot: {run_dir}")
        except Exception as exc:
            if self._observer:
                self._observer.console.emit_warn(f"Run snapshot finalization failed: {exc}")
            else:
                print(f"[warn] Run snapshot finalization failed: {exc}")

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

    def _ensure_runtime_state(self) -> None:
        output_dir = Path(self.output_dir)
        if not hasattr(self, "runtime_db_path") or self.runtime_db_path is None:
            self.runtime_db_path = output_dir / "runtime_state.sqlite3"
        if not hasattr(self, "_runtime_state") or self._runtime_state is None:
            self._runtime_state = RuntimeStateStore(self.runtime_db_path)
        if not hasattr(self, "_runtime_lock") or self._runtime_lock is None:
            self._runtime_lock = RuntimeStateLock(output_dir)
        if not hasattr(self, "_runtime_bridge") or self._runtime_bridge is None:
            self._runtime_bridge = GitHubRuntimeStateBridge(
                store=self._runtime_state,
                output_dir=output_dir,
                brief_id=self.brief_obj.id,
                brief_name=self.brief_obj.id,
                brief_path=self.brief_path,
            )
        if not hasattr(self, "_execution_engine") or self._execution_engine is None:
            self._execution_engine = CandidateExecutionEngine(
                store=self._runtime_state,
                output_dir=str(output_dir),
                brief_id=self.brief_obj.id,
                source="github",
            )
        if not hasattr(self, "_runtime_run_id"):
            self._runtime_run_id = None
        if not hasattr(self, "_safety") or self._safety is None:
            self._safety = RunSafetyCoordinator(
                store=self._runtime_state,
                output_dir=output_dir,
                source="github",
                brief_id=self.brief_obj.id,
            )
        self._ensure_services()

    def _ensure_services(self) -> None:
        if not hasattr(self, "_work_unit_service") or self._work_unit_service is None:
            self._work_unit_service = GitHubWorkUnitService(self)
        if not hasattr(self, "_acquisition_service") or self._acquisition_service is None:
            self._acquisition_service = GitHubAcquisitionService(self)
        if not hasattr(self, "_side_effects_service") or self._side_effects_service is None:
            self._side_effects_service = GitHubSideEffectsService(self)

    def _get_query_work_unit_id(self, query: GitHubSearchQuery) -> int | None:
        if not getattr(self, "_runtime_run_id", None):
            return None
        return self._runtime_state.get_work_unit_id(
            self._runtime_run_id,
            kind=GITHUB_QUERY_KIND,
            source_unit_id=str(query.id),
        )

    @staticmethod
    def _candidate_record(candidate: GitHubCandidate) -> dict:
        return {"username": candidate.user.username, **candidate.to_dict()}

    @staticmethod
    def _build_runtime_cursor(query: GitHubSearchQuery, result_rank: int) -> dict:
        return {
            "query_id": query.id,
            "query_name": query.name,
            "query_string": query.query,
            "channel": query.channel,
            "result_rank": result_rank,
        }

    def _execution_envelope(
        self,
        *,
        username: str,
        query: GitHubSearchQuery,
        result_rank: int,
        candidate: GitHubCandidate | None = None,
        snippet: CandidateSnippet | None = None,
        metadata: dict | None = None,
    ):
        display_name = username
        profile_url = f"https://github.com/{username}"
        if candidate is not None:
            display_name = candidate.user.name or username
            profile_url = candidate.user.profile_url
        elif snippet is not None:
            display_name = snippet.name
            profile_url = snippet.profile_url
        return CandidateExecutionEnvelope(
            source="github",
            brief_id=self.brief_obj.id,
            run_id=getattr(self, "_runtime_run_id", 0) or 0,
            work_unit_kind=GITHUB_QUERY_KIND,
            work_unit_source_id=str(query.id),
            identity_key=username,
            display_name=display_name,
            profile_url=profile_url,
            snippet=snippet,
            source_cursor=self._build_runtime_cursor(query, result_rank),
            metadata=metadata or {},
        )

    def _record_safety_event(self, event_type: str, payload: dict) -> None:
        if getattr(self, "_runtime_run_id", None):
            self._runtime_state.record_event(
                run_id=self._runtime_run_id,
                event_type=event_type,
                payload=payload,
            )

    def _start_stage_attempt(
        self,
        *,
        username: str,
        stage: str,
        query: GitHubSearchQuery,
        candidate: GitHubCandidate,
        result_rank: int = 0,
        snippet: CandidateSnippet | None = None,
        payload: dict | None = None,
    ) -> int | None:
        if not getattr(self, "_runtime_run_id", None):
            return None
        envelope = self._execution_envelope(
            username=username,
            query=query,
            result_rank=result_rank,
            candidate=candidate,
            snippet=snippet,
        )
        return self._execution_engine.runtime.start_stage(
            envelope,
            stage=stage,
            payload=payload or {},
        )

    def _finish_failure_decision_attempt(
        self,
        *,
        attempt_id: int | None,
        username: str,
        stage: str,
        decision: OpusDecision,
        query: GitHubSearchQuery,
        result_rank: int,
        candidate: GitHubCandidate,
        candidate_record: dict,
        snippet: CandidateSnippet | None = None,
        extra_payload: dict | None = None,
    ) -> None:
        if not attempt_id:
            return
        envelope = self._execution_envelope(
            username=username,
            query=query,
            result_rank=result_rank,
            candidate=candidate,
            snippet=snippet,
            metadata={"candidate_record": candidate_record},
        )
        payload = {"candidate_record": candidate_record}
        if extra_payload:
            payload.update(extra_payload)
        self._execution_engine.runtime.finish_stage_failure(
            attempt_id=attempt_id,
            envelope=envelope,
            stage=stage,
            error_or_failure_decision=decision,
            extra_payload=payload,
        )
        self._in_flight_usernames.discard(candidate_record.get("username", ""))

    def _finish_runtime_failure(
        self,
        *,
        attempt_id: int | None,
        username: str,
        query: GitHubSearchQuery,
        result_rank: int,
        candidate: GitHubCandidate | None = None,
        snippet: CandidateSnippet | None = None,
        error: Exception,
        payload: dict | None = None,
    ) -> None:
        if not attempt_id:
            return
        envelope = self._execution_envelope(
            username=username,
            query=query,
            result_rank=result_rank,
            candidate=candidate,
            snippet=snippet,
        )
        self._execution_engine.runtime.finish_stage_failure(
            attempt_id=attempt_id,
            envelope=envelope,
            stage="preparation",
            error_or_failure_decision=error,
            extra_payload=payload or {},
        )

    def _finish_preparation_terminal(
        self,
        *,
        attempt_id: int | None,
        username: str,
        decision: str,
        query: GitHubSearchQuery,
        candidate: GitHubCandidate,
        result_rank: int,
        candidate_record: dict | None = None,
    ) -> None:
        if not attempt_id:
            return
        envelope = self._execution_envelope(
            username=username,
            query=query,
            result_rank=result_rank,
            candidate=candidate,
            metadata={"candidate_record": candidate_record or self._candidate_record(candidate)},
        )
        payload = {
            "cursor": self._build_runtime_cursor(query, result_rank),
            "candidate_record": candidate_record or self._candidate_record(candidate),
            "terminal_reason": decision,
        }
        self._execution_engine.runtime.record_terminal_runtime_decision(
            attempt_id=attempt_id,
            envelope=envelope,
            decision=decision,
            payload=payload,
        )
