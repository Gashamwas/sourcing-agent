"""LinkedIn-specific runtime-state bridge and legacy import helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from linkedin.search_intelligence import (
    LinkedInExperimentState,
    bootstrap_experiment_state,
    reset_experiment_state,
)
from shared.runtime_state.admin import rebuild_compat_projections
from shared.runtime_state.linkedin_progress_sync import sync_linkedin_progress
from shared.runtime_state.projections import (
    project_linkedin_candidate_history,
    project_linkedin_progress,
    project_linkedin_search_memory,
)
from shared.runtime_state.store import LINKEDIN_STRING_KIND, RuntimeStateStore
from shared.schemas import CandidateProfileSummary, CandidateSnippet, OpusDecision, Progress, SearchString
from shared.storage import read_jsonl

SAVE_DECISIONS = {"SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE", "SIGNAL_SAVE"}


@dataclass(frozen=True)
class LinkedInResumeState:
    brief_name: str
    current_string_id: int | None = None
    current_page: int = 0
    pending_block_name: str = ""
    pending_block_string_ids: list[int] | None = None
    pending_block_ready: bool = False
    candidates_saved: int = 0
    candidates_rejected: int = 0
    pivot_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pending_block_string_ids"] = list(self.pending_block_string_ids or [])
        return payload


class LinkedInRuntimeStateBridge:
    """Keeps LinkedIn runtime semantics DB-authoritative while preserving projections."""

    def __init__(
        self,
        *,
        store: RuntimeStateStore,
        output_dir: str | Path,
        brief_id: str,
        brief_name: str,
    ):
        self.store = store
        self.output_dir = Path(output_dir)
        self.brief_id = brief_id
        self.brief_name = brief_name
        self.progress_path = self.output_dir / "progress.json"
        self.history_path = self.output_dir / f"candidate_history-{brief_id}.jsonl"
        self.search_memory_path = self.output_dir / f"search_memory-{brief_id}.json"
        self.snippets_path = self.output_dir / "snippets.jsonl"
        self.facial_path = self.output_dir / "facial_judgments.jsonl"
        self.profiles_path = self.output_dir / "profile_summaries.jsonl"
        self.final_path = self.output_dir / "final_judgments.jsonl"
        from shared.execution import CandidateExecutionEngine

        self._execution_engine = CandidateExecutionEngine(
            store=self.store,
            output_dir=str(self.output_dir),
            brief_id=self.brief_id,
            source="linkedin",
        )

    def has_runtime_state(self) -> bool:
        latest_run = self.store.get_latest_run(source="linkedin", brief_id=self.brief_id)
        return bool(latest_run or self.store.has_candidates(source="linkedin", brief_id=self.brief_id))

    def has_legacy_state(self) -> bool:
        return bool(self._read_legacy_progress() or self.history_path.exists() or self.search_memory_path.exists())

    def start_or_resume_run(
        self,
        *,
        resume: bool,
        initial_progress: Progress | None = None,
        experiment_states: dict[int, LinkedInExperimentState] | None = None,
    ) -> tuple[int, Progress]:
        self.store.reconcile_open_attempts(source="linkedin", brief_id=self.brief_id)
        self.store.reconcile_pending_side_effects(source="linkedin", brief_id=self.brief_id)
        latest_run = self.store.get_latest_run(source="linkedin", brief_id=self.brief_id)
        had_runtime_before = bool(
            latest_run or self.store.has_candidates(source="linkedin", brief_id=self.brief_id)
        )

        if resume and latest_run and self.store.has_work_units(int(latest_run["id"])):
            run_id = self.store.start_run(
                source="linkedin",
                brief_id=self.brief_id,
                output_dir=str(self.output_dir),
                mode="resume",
                resume_state=self.store.get_run_resume_state(int(latest_run["id"])),
                resumed_from_run_id=int(latest_run["id"]),
                clone_work_units_from_run_id=int(latest_run["id"]),
            )
            self.rebuild_artifacts(run_id)
            return run_id, project_linkedin_progress(self.store, run_id)

        run_id = self.store.start_run(
            source="linkedin",
            brief_id=self.brief_id,
            output_dir=str(self.output_dir),
            mode="resume" if resume else "fresh",
            resume_state=LinkedInResumeState(brief_name=self.brief_name).to_dict(),
            resumed_from_run_id=int(latest_run["id"]) if resume and latest_run else None,
        )

        if resume and not had_runtime_before and self._legacy_state_exists():
            self.import_legacy_state(run_id)
            self.rebuild_artifacts(run_id)
            return run_id, project_linkedin_progress(self.store, run_id)

        if initial_progress is not None:
            self.sync_progress(run_id, initial_progress, experiment_states=experiment_states)
            return run_id, project_linkedin_progress(self.store, run_id)

        progress = Progress(brief_name=self.brief_name)
        self.sync_progress(run_id, progress, experiment_states=experiment_states)
        return run_id, progress

    def sync_progress(
        self,
        run_id: int,
        progress: Progress,
        *,
        experiment_states: dict[int, LinkedInExperimentState] | None = None,
    ) -> None:
        sync_linkedin_progress(
            store=self.store,
            run_id=run_id,
            brief_id=self.brief_id,
            progress=progress,
            experiment_states=experiment_states,
            rebuild_artifacts=self.rebuild_artifacts,
            work_unit_metrics=self._work_unit_metrics,
        )

    def load_progress(self, run_id: int) -> Progress:
        return project_linkedin_progress(self.store, run_id)

    def load_experiment_states(
        self,
        run_id: int,
        *,
        progress: Progress | None = None,
    ) -> dict[int, LinkedInExperimentState]:
        states: dict[int, LinkedInExperimentState] = {}
        progress_lookup = {item.id: item for item in (progress.strings if progress else [])}
        for row in self.store.list_work_units(run_id, kind=LINKEDIN_STRING_KIND):
            payload = _json_loads(row["payload_json"])
            checkpoint = _json_loads(row["checkpoint_json"])
            search_string = progress_lookup.get(int(payload.get("id") or row["source_unit_id"]))
            if search_string is None:
                search_string = SearchString.from_dict(payload)
            state = LinkedInExperimentState.from_dict(checkpoint.get("experiment_state"))
            if state is None:
                state = bootstrap_experiment_state(search_string)
            state.apply_shadow(search_string)
            states[search_string.id] = state
        return states

    def load_search_memory(self) -> dict:
        return project_linkedin_search_memory(self.store, brief_id=self.brief_id)

    def load_history(self) -> tuple[set[str], dict[str, str], set[str]]:
        blocked_urls = set(self.store.list_terminal_identity_keys(source="linkedin", brief_id=self.brief_id))
        prior_outcomes: dict[str, str] = {}
        saved_urls: set[str] = set()
        for record in project_linkedin_candidate_history(self.store, brief_id=self.brief_id):
            url = record.get("profile_url", "")
            outcome = record.get("outcome", "")
            if url:
                prior_outcomes[url] = outcome
                if outcome in SAVE_DECISIONS:
                    saved_urls.add(url)
        return blocked_urls, prior_outcomes, saved_urls

    def record_missing_identity(
        self,
        *,
        run_id: int,
        search_string: SearchString,
        snippet: CandidateSnippet,
        reason: str = "missing_profile_url",
    ) -> None:
        work_unit_id = self.store.get_work_unit_id(
            run_id,
            kind=LINKEDIN_STRING_KIND,
            source_unit_id=str(search_string.id),
        )
        self.store.record_event(
            run_id=run_id,
            work_unit_id=work_unit_id,
            event_type="linkedin_missing_identity",
            payload={
                "reason": reason,
                "candidate_name": snippet.name,
                "source_string_id": snippet.source_string_id,
                "page": snippet.page,
                "result_rank": snippet.result_rank,
            },
        )

    def record_snippet_extracted(
        self,
        *,
        run_id: int,
        search_string: SearchString,
        snippet: CandidateSnippet,
    ) -> int | None:
        if not snippet.profile_url:
            self.record_missing_identity(run_id=run_id, search_string=search_string, snippet=snippet)
            return None
        envelope = self._execution_engine.envelope(
            source="linkedin",
            brief_id=self.brief_id,
            run_id=run_id,
            work_unit_kind=LINKEDIN_STRING_KIND,
            work_unit_source_id=str(search_string.id),
            identity_key=snippet.profile_url,
            display_name=snippet.name,
            profile_url=snippet.profile_url,
            snippet=snippet,
            source_cursor=self._cursor(search_string, snippet),
        )
        payload = {
            "cursor": envelope.source_cursor,
            "snippet": snippet.to_dict(),
        }
        self._execution_engine.runtime.record_discovery(
            envelope,
            payload=payload["cursor"],
        )
        return self._execution_engine.runtime.record_snippet_extracted(
            envelope,
            payload=payload,
        )

    def start_stage_attempt(
        self,
        *,
        run_id: int,
        search_string: SearchString,
        snippet: CandidateSnippet,
        stage: str,
        payload: dict | None = None,
    ) -> int | None:
        if not snippet.profile_url:
            return None
        attempt_payload = {
            "cursor": self._cursor(search_string, snippet),
            "snippet": snippet.to_dict(),
        }
        if payload:
            attempt_payload.update(payload)
        envelope = self._execution_engine.envelope(
            source="linkedin",
            brief_id=self.brief_id,
            run_id=run_id,
            work_unit_kind=LINKEDIN_STRING_KIND,
            work_unit_source_id=str(search_string.id),
            identity_key=snippet.profile_url,
            display_name=snippet.name,
            profile_url=snippet.profile_url,
            snippet=snippet,
            source_cursor=attempt_payload["cursor"],
        )
        return self._execution_engine.runtime.start_stage(
            envelope,
            stage=stage,
            payload=attempt_payload,
        )

    def finish_stage_success(
        self,
        *,
        run_id: int,
        attempt_id: int | None,
        stage: str,
        snippet: CandidateSnippet,
        decision: OpusDecision,
        profile_summary: CandidateProfileSummary | None = None,
    ) -> None:
        if not attempt_id:
            return
        envelope = self._execution_engine.envelope(
            source="linkedin",
            brief_id=self.brief_id,
            run_id=run_id,
            work_unit_kind=LINKEDIN_STRING_KIND,
            work_unit_source_id=str(snippet.source_string_id),
            identity_key=snippet.profile_url,
            display_name=snippet.name,
            profile_url=snippet.profile_url,
            snippet=snippet,
            source_cursor=self._cursor(search_string=SearchString(id=snippet.source_string_id, name=snippet.source_string_name, boolean=""), snippet=snippet),
        )
        self._execution_engine.runtime.finish_stage_success(
            attempt_id=attempt_id,
            envelope=envelope,
            stage=stage,
            decision=decision,
            extra_payload={
                "source_string_id": snippet.source_string_id,
                "timestamp": self._timestamp_from_decision_payload(decision),
            },
            profile_summary=profile_summary,
        )

    def finish_stage_failure(
        self,
        *,
        run_id: int,
        attempt_id: int | None,
        snippet: CandidateSnippet,
        error: Exception,
        payload: dict | None = None,
    ) -> None:
        if not attempt_id:
            return
        envelope = self._execution_engine.envelope(
            source="linkedin",
            brief_id=self.brief_id,
            run_id=run_id,
            work_unit_kind=LINKEDIN_STRING_KIND,
            work_unit_source_id=str(snippet.source_string_id),
            identity_key=snippet.profile_url,
            display_name=snippet.name,
            profile_url=snippet.profile_url,
            snippet=snippet,
            source_cursor=self._cursor(SearchString(id=snippet.source_string_id, name=snippet.source_string_name, boolean=""), snippet),
        )
        self._execution_engine.runtime.finish_stage_failure(
            attempt_id=attempt_id,
            envelope=envelope,
            stage="full",
            error_or_failure_decision=error,
            extra_payload=payload,
        )

    def finish_failure_decision(
        self,
        *,
        run_id: int,
        attempt_id: int | None,
        snippet: CandidateSnippet,
        decision: OpusDecision,
        payload: dict | None = None,
    ) -> None:
        if not attempt_id:
            return
        envelope = self._execution_engine.envelope(
            source="linkedin",
            brief_id=self.brief_id,
            run_id=run_id,
            work_unit_kind=LINKEDIN_STRING_KIND,
            work_unit_source_id=str(snippet.source_string_id),
            identity_key=snippet.profile_url,
            display_name=snippet.name,
            profile_url=snippet.profile_url,
            snippet=snippet,
            source_cursor=self._cursor(SearchString(id=snippet.source_string_id, name=snippet.source_string_name, boolean=""), snippet),
        )
        self._execution_engine.runtime.finish_stage_failure(
            attempt_id=attempt_id,
            envelope=envelope,
            stage=decision.stage,
            error_or_failure_decision=decision,
            extra_payload=payload,
        )

    def record_side_effect_result(
        self,
        *,
        run_id: int,
        search_string: SearchString,
        snippet: CandidateSnippet,
        attempt_id: int | None,
        effect_type: str,
        status: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        envelope = self._execution_engine.envelope(
            source="linkedin",
            brief_id=self.brief_id,
            run_id=run_id,
            work_unit_kind=LINKEDIN_STRING_KIND,
            work_unit_source_id=str(search_string.id),
            identity_key=snippet.profile_url,
            display_name=snippet.name,
            profile_url=snippet.profile_url,
            snippet=snippet,
            source_cursor=self._cursor(search_string, snippet),
        )
        self._execution_engine.runtime.record_side_effect_result(
            envelope=envelope,
            attempt_id=attempt_id,
            effect_type=effect_type,
            status=status,
            payload=payload,
        )

    def begin_candidate_side_effect(
        self,
        *,
        run_id: int,
        search_string: SearchString,
        snippet: CandidateSnippet,
        attempt_id: int | None,
        effect_type: str,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        envelope = self._execution_engine.envelope(
            source="linkedin",
            brief_id=self.brief_id,
            run_id=run_id,
            work_unit_kind=LINKEDIN_STRING_KIND,
            work_unit_source_id=str(search_string.id),
            identity_key=snippet.profile_url,
            display_name=snippet.name,
            profile_url=snippet.profile_url,
            snippet=snippet,
            source_cursor=self._cursor(search_string, snippet),
        )
        return self._execution_engine.runtime.begin_candidate_side_effect(
            envelope=envelope,
            attempt_id=attempt_id,
            effect_type=effect_type,
            idempotency_key=idempotency_key,
            payload=payload,
        )

    def complete_candidate_side_effect(
        self,
        *,
        side_effect_id: int,
        status: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._execution_engine.runtime.complete_candidate_side_effect(
            side_effect_id=side_effect_id,
            status=status,
            payload=payload,
        )

    def rebuild_artifacts(self, run_id: int) -> None:
        rebuild_compat_projections(
            self.store,
            run_id=run_id,
            output_dir=self.output_dir,
        )

    def record_event(
        self,
        *,
        event_type: str,
        payload: dict[str, Any] | None = None,
        run_id: int | None = None,
        work_unit_id: int | None = None,
    ) -> None:
        self.store.record_event(
            run_id=run_id,
            work_unit_id=work_unit_id,
            event_type=event_type,
            payload=payload,
        )

    def import_legacy_state(self, run_id: int) -> None:
        with self.store.connect() as conn:
            imported = conn.execute(
                """
                SELECT 1
                FROM events
                WHERE run_id = ? AND event_type = 'linkedin_legacy_import_complete'
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            if imported:
                return

        progress = self._read_legacy_progress()
        if progress:
            self.sync_progress(run_id, progress)

        snippets_by_url: dict[str, list[dict]] = {}
        facial_by_url: dict[str, dict] = {}
        profiles_by_url: dict[str, dict] = {}
        finals_by_url: dict[str, dict] = {}

        if self.snippets_path.exists():
            for record in read_jsonl(self.snippets_path):
                url = record.get("profile_url", "")
                if not url:
                    continue
                snippets_by_url.setdefault(url, []).append(record)

        if self.facial_path.exists():
            for record in read_jsonl(self.facial_path):
                url = record.get("profile_url", "")
                if url:
                    facial_by_url[url] = record

        if self.profiles_path.exists():
            for record in read_jsonl(self.profiles_path):
                url = record.get("profile_url", "")
                if url:
                    profiles_by_url[url] = record

        if self.final_path.exists():
            for record in read_jsonl(self.final_path):
                url = record.get("profile_url", "")
                if url:
                    finals_by_url[url] = record

        for url, snippet_records in snippets_by_url.items():
            for record in snippet_records:
                snippet = CandidateSnippet.from_dict(record)
                self.record_snippet_extracted(
                    run_id=run_id,
                    search_string=self._search_string_for_id(progress, snippet.source_string_id) if progress else SearchString(id=snippet.source_string_id, name=snippet.source_string_name, boolean=""),
                    snippet=snippet,
                )

            facial_record = facial_by_url.get(url)
            if facial_record:
                snippet = CandidateSnippet.from_dict(snippet_records[-1])
                search_string = self._search_string_for_id(progress, snippet.source_string_id) if progress else SearchString(id=snippet.source_string_id, name=snippet.source_string_name, boolean="")
                attempt_id = self.start_stage_attempt(
                    run_id=run_id,
                    search_string=search_string,
                    snippet=snippet,
                    stage="facial",
                )
                decision = OpusDecision.from_dict(facial_record)
                if decision.decision in {"PARSE_FAILURE", "JUDGMENT_FAILURE"}:
                    self.finish_failure_decision(
                        run_id=run_id,
                        attempt_id=attempt_id,
                        snippet=snippet,
                        decision=decision,
                    )
                else:
                    self.finish_stage_success(
                        run_id=run_id,
                        attempt_id=attempt_id,
                        stage="facial",
                        snippet=snippet,
                        decision=decision,
                    )

            final_record = finals_by_url.get(url)
            if final_record:
                snippet = CandidateSnippet.from_dict(snippet_records[-1])
                search_string = self._search_string_for_id(progress, snippet.source_string_id) if progress else SearchString(id=snippet.source_string_id, name=snippet.source_string_name, boolean="")
                profile_summary = None
                if url in profiles_by_url:
                    profile_summary = CandidateProfileSummary.from_dict(profiles_by_url[url])
                candidate = self.store.get_candidate(
                    source="linkedin",
                    brief_id=self.brief_id,
                    identity_key=url,
                )
                if candidate and candidate["current_lifecycle_state"] not in {"facial_terminal", "full_started", "full_terminal"}:
                    self.store.set_candidate_state(
                        run_id=run_id,
                        source="linkedin",
                        brief_id=self.brief_id,
                        identity_key=url,
                        new_state="facial_terminal",
                        terminal_decision="FACIAL_YES",
                        terminal_payload={"source_string_id": snippet.source_string_id},
                    )
                attempt_id = self.start_stage_attempt(
                    run_id=run_id,
                    search_string=search_string,
                    snippet=snippet,
                    stage="full",
                    payload={"profile_summary": profile_summary.to_dict() if profile_summary else {}},
                )
                decision = OpusDecision.from_dict(final_record)
                if decision.decision in {"PARSE_FAILURE", "JUDGMENT_FAILURE"}:
                    self.finish_failure_decision(
                        run_id=run_id,
                        attempt_id=attempt_id,
                        snippet=snippet,
                        decision=decision,
                        payload={"profile_summary": profile_summary.to_dict() if profile_summary else {}},
                    )
                else:
                    self.finish_stage_success(
                        run_id=run_id,
                        attempt_id=attempt_id,
                        stage="full",
                        snippet=snippet,
                        decision=decision,
                        profile_summary=profile_summary,
                    )

        if self.history_path.exists():
            for record in read_jsonl(self.history_path):
                url = record.get("profile_url", "")
                outcome = record.get("outcome", "")
                if not url or not outcome:
                    continue
                if not self.store.get_candidate(source="linkedin", brief_id=self.brief_id, identity_key=url):
                    self.store.record_candidate_discovery(
                        run_id=run_id,
                        work_unit_id=None,
                        source="linkedin",
                        brief_id=self.brief_id,
                        identity_key=url,
                        display_name=record.get("candidate_name", ""),
                        profile_url=url,
                        payload={"legacy_import": True},
                    )
                candidate = self.store.get_candidate(
                    source="linkedin",
                    brief_id=self.brief_id,
                    identity_key=url,
                )
                current_state = candidate["current_lifecycle_state"] if candidate else "discovered"
                if current_state == "discovered":
                    self.store.set_candidate_state(
                        run_id=run_id,
                        source="linkedin",
                        brief_id=self.brief_id,
                        identity_key=url,
                        new_state="snippet_extracted",
                    )
                    current_state = "snippet_extracted"
                if current_state == "snippet_extracted":
                    self.store.set_candidate_state(
                        run_id=run_id,
                        source="linkedin",
                        brief_id=self.brief_id,
                        identity_key=url,
                        new_state="facial_started",
                    )
                    current_state = "facial_started"
                if outcome in SAVE_DECISIONS or outcome == "REJECT":
                    if current_state == "facial_started":
                        self.store.set_candidate_state(
                            run_id=run_id,
                            source="linkedin",
                            brief_id=self.brief_id,
                            identity_key=url,
                            new_state="facial_terminal",
                            terminal_decision="FACIAL_YES",
                            terminal_payload={
                                "legacy_import": True,
                                "source_string_id": record.get("source_string_id"),
                            },
                        )
                        current_state = "facial_terminal"
                    if current_state == "facial_terminal":
                        self.store.set_candidate_state(
                            run_id=run_id,
                            source="linkedin",
                            brief_id=self.brief_id,
                            identity_key=url,
                            new_state="full_started",
                        )
                    state = "full_terminal"
                else:
                    state = "facial_terminal"
                self.store.set_candidate_state(
                    run_id=run_id,
                    source="linkedin",
                    brief_id=self.brief_id,
                    identity_key=url,
                    new_state=state,
                    terminal_decision=outcome,
                    terminal_payload={
                        "confidence": record.get("confidence", 0.0),
                        "source_string_id": record.get("source_string_id"),
                        "timestamp": record.get("timestamp"),
                    },
                )
        self.store.record_event(
            run_id=run_id,
            event_type="linkedin_legacy_import_complete",
            payload={
                "progress_exists": self.progress_path.exists(),
                "history_exists": self.history_path.exists(),
                "search_memory_exists": self.search_memory_path.exists(),
            },
        )

    def restart_string(self, *, run_id: int, progress: Progress, string_id: int) -> None:
        target = next((search_string for search_string in progress.strings if search_string.id == string_id), None)
        if not target:
            return
        reset_state: LinkedInExperimentState | None = None
        work_unit = self.store.get_work_unit_by_source_id(
            run_id,
            kind=LINKEDIN_STRING_KIND,
            source_unit_id=str(string_id),
        )
        attempt_ids: list[int] = []
        candidate_keys_to_clear: set[str] = set()
        candidate_ids: set[int] = set()
        if work_unit:
            ordering_index = int(work_unit["ordering_index"])
            payload = _json_loads(work_unit["payload_json"])
            checkpoint = _json_loads(work_unit["checkpoint_json"])
            work_unit_id = int(work_unit["id"])
            with self.store.connect() as conn:
                candidate_rows = conn.execute(
                    """
                    SELECT id, identity_key, terminal_payload_json, last_work_unit_id
                    FROM candidates
                    WHERE source = 'linkedin' AND brief_id = ?
                    """,
                    (self.brief_id,),
                ).fetchall()
                for row in candidate_rows:
                    terminal_payload = _json_loads(row["terminal_payload_json"])
                    source_string_id = terminal_payload.get("source_string_id")
                    if source_string_id == string_id or row["last_work_unit_id"] == work_unit_id:
                        candidate_ids.add(int(row["id"]))
                        candidate_keys_to_clear.add(str(row["identity_key"]))
                rows = conn.execute(
                    """
                    SELECT ca.id, ca.payload_json, ca.source_cursor_json, c.id AS candidate_id, c.identity_key
                    FROM candidate_attempts ca
                    JOIN candidates c ON c.id = ca.candidate_id
                    WHERE c.source = 'linkedin' AND c.brief_id = ?
                    """,
                    (self.brief_id,),
                ).fetchall()
                for row in rows:
                    payload = _json_loads(row["payload_json"])
                    cursor = _json_loads(row["source_cursor_json"])
                    source_string_id = (
                        payload.get("source_string_id")
                        or payload.get("cursor", {}).get("source_string_id")
                        or cursor.get("source_string_id")
                    )
                    if source_string_id == string_id or row["candidate_id"] in candidate_ids:
                        attempt_ids.append(int(row["id"]))
                        candidate_keys_to_clear.add(str(row["identity_key"]))
                        candidate_ids.add(int(row["candidate_id"]))
                for attempt_id in attempt_ids:
                    conn.execute("DELETE FROM candidate_attempts WHERE id = ?", (attempt_id,))
            experiment_state = LinkedInExperimentState.from_dict(checkpoint.get("experiment_state"))
            experiment_state = reset_experiment_state(target, experiment_state)
            reset_state = experiment_state
            experiment_state.apply_shadow(target)
            payload.update(
                {
                    **target.to_dict(),
                    "status": "queued",
                    "pages_reviewed": 1,
                    "phase": "scout",
                    "saves": [],
                    "notes": "",
                    "refinement_stack": [],
                    "search_intent": experiment_state.intent.to_dict(),
                }
            )
            for identity_key in candidate_keys_to_clear:
                self.store.clear_candidate_terminal_state(
                    source="linkedin",
                    brief_id=self.brief_id,
                    identity_key=identity_key,
                )
                self.store.invalidate_candidate_side_effects(
                    source="linkedin",
                    brief_id=self.brief_id,
                    identity_key=identity_key,
                )
            self.store.upsert_work_unit(
                run_id=run_id,
                source="linkedin",
                brief_id=self.brief_id,
                kind=LINKEDIN_STRING_KIND,
                source_unit_id=str(string_id),
                display_name=target.name,
                ordering_index=ordering_index,
                status="queued",
                payload=payload,
                checkpoint={
                    "pages_reviewed": 1,
                    "duplicates_count": 0,
                    "phase": "scout",
                    "refinement_stack": [],
                    "experiment_state": experiment_state.to_dict(),
                },
                metrics={
                    **self._work_unit_metrics(target, pages_reviewed=1, duplicates_count=0, block_generated=0, exhausted=0),
                    "experiment_summary": experiment_state.metrics_summary(),
                    "variant_metrics": experiment_state.metrics_summary().get("variants", {}),
                },
                family_key=target.family_key,
                novelty_bucket=target.novelty_bucket,
                domain_lane=target.domain_lane,
                counters={
                    "result_count": 0,
                    "candidates_discovered": 0,
                    "facial_yes_count": 0,
                    "facial_no_count": 0,
                    "saves_count": 0,
                    "rejected_count": 0,
                },
                notes="",
            )
            self.store.record_event(
                run_id=run_id,
                work_unit_id=work_unit_id,
                event_type="linkedin_string_restarted",
                payload={"string_id": string_id, "candidate_ids_cleared": sorted(candidate_ids)},
            )

        target.status = "queued"
        target.pages_reviewed = 1
        target.phase = "scout"
        target.saves = []
        target.notes = ""
        target.refinement_stack = []
        target.result_count = 0
        if reset_state is not None:
            reset_state.apply_shadow(target)
        if string_id in progress.pending_block_string_ids or progress.pending_block_name == target.block:
            progress.pending_block_name = ""
            progress.pending_block_string_ids = []
            progress.pending_block_ready = False
        if progress.current_string_id == string_id:
            progress.current_string_id = None
            progress.current_page = 0
        self.sync_progress(run_id, progress)

    def _legacy_state_exists(self) -> bool:
        return self.has_legacy_state()

    def _read_legacy_progress(self) -> Progress | None:
        if not self.progress_path.exists():
            return None
        progress = Progress.from_file(str(self.progress_path))
        if progress.brief_name != self.brief_name:
            return None
        return progress

    def _search_string_for_id(self, progress: Progress | None, string_id: int) -> SearchString:
        if progress:
            existing = next((item for item in progress.strings if item.id == string_id), None)
            if existing:
                return existing
        return SearchString(id=string_id, name=f"Imported #{string_id}", boolean="")

    @staticmethod
    def _timestamp_from_decision_payload(decision: OpusDecision) -> str | None:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _cursor(search_string: SearchString, snippet: CandidateSnippet) -> dict[str, Any]:
        return {
            "source_string_id": search_string.id,
            "source_string_name": search_string.name,
            "page": snippet.page,
            "result_rank": snippet.result_rank,
        }

    @staticmethod
    def _work_unit_metrics(
        search_string: SearchString,
        *,
        pages_reviewed: int | None = None,
        duplicates_count: int | None = None,
        block_generated: int | None = None,
        exhausted: int | None = None,
    ) -> dict[str, Any]:
        return {
            "pages_reviewed": search_string.pages_reviewed if pages_reviewed is None else pages_reviewed,
            "profiles_seen": search_string.result_count,
            "profiles_processed": search_string.candidates_count,
            "facial_yes": search_string.facial_yes_count,
            "facial_no": search_string.facial_no_count,
            "facial_skip": max(0, search_string.candidates_count - search_string.facial_yes_count - search_string.facial_no_count),
            "full_save": len(search_string.saves),
            "full_reject": 0,
            "duplicates_count": search_string.duplicates_count if duplicates_count is None else duplicates_count,
            "exhausted": int(exhausted or 0),
            "block_generated": int(block_generated or 0),
        }


def _json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    return json.loads(raw)
