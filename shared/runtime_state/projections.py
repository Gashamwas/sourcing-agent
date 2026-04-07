"""Compatibility projections derived from runtime_state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from github.schemas import GitHubProgress
from shared.schemas import Progress, SearchString
from shared.search_memory import update_search_memory

from .store import GITHUB_QUERY_KIND, LINKEDIN_STRING_KIND, RuntimeStateStore


def project_github_progress(store: RuntimeStateStore, run_id: int) -> GitHubProgress:
    return store.load_github_progress(run_id)


def write_github_progress_projection(store: RuntimeStateStore, run_id: int, path: str | Path) -> GitHubProgress:
    progress = project_github_progress(store, run_id)
    _write_json_atomic(path, progress.to_dict())
    return progress


def project_linkedin_progress(store: RuntimeStateStore, run_id: int) -> Progress:
    run = store.get_run(run_id)
    if not run:
        raise ValueError(f"run not found: {run_id}")
    resume_state = _json_loads(run.get("resume_state_json"))
    work_units = store.list_work_units(run_id, kind=LINKEDIN_STRING_KIND)
    strings = []
    for row in work_units:
        payload = _json_loads(row["payload_json"])
        payload.update(
            {
                "status": row["status"],
                "result_count": row["result_count"],
                "pages_reviewed": _json_loads(row["checkpoint_json"]).get("pages_reviewed", payload.get("pages_reviewed", 0)),
                "facial_yes_count": row["facial_yes_count"],
                "facial_no_count": row["facial_no_count"],
                "candidates_count": row["candidates_discovered"],
                "duplicates_count": _json_loads(row["checkpoint_json"]).get("duplicates_count", payload.get("duplicates_count", 0)),
                "notes": row["notes"] or payload.get("notes", ""),
                "family_key": row["family_key"],
                "novelty_bucket": row["novelty_bucket"],
                "domain_lane": row["domain_lane"],
            }
        )
        strings.append(SearchString.from_dict(payload))
    return Progress(
        brief_name=resume_state.get("brief_name", run["brief_id"]),
        strings=strings,
        candidates_saved=int(resume_state.get("candidates_saved", 0)),
        candidates_rejected=int(resume_state.get("candidates_rejected", 0)),
        current_string_id=resume_state.get("current_string_id"),
        current_page=int(resume_state.get("current_page", 0)),
        pending_block_name=resume_state.get("pending_block_name", ""),
        pending_block_string_ids=list(resume_state.get("pending_block_string_ids", [])),
        pending_block_ready=bool(resume_state.get("pending_block_ready", False)),
        pivot_count=int(resume_state.get("pivot_count", 0)),
    )


def write_linkedin_progress_projection(store: RuntimeStateStore, run_id: int, path: str | Path) -> Progress:
    progress = project_linkedin_progress(store, run_id)
    _write_json_atomic(path, progress.to_dict())
    return progress


def project_linkedin_candidate_history(store: RuntimeStateStore, *, brief_id: str) -> list[dict]:
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT identity_key, display_name, profile_url, terminal_decision, terminal_payload_json, last_seen_at
            FROM candidates
            WHERE source = 'linkedin' AND brief_id = ? AND terminal_decision IS NOT NULL
            ORDER BY last_seen_at ASC, id ASC
            """,
            (brief_id,),
        ).fetchall()
    history = []
    for row in rows:
        payload = _json_loads(row["terminal_payload_json"])
        history.append(
            {
                "profile_url": row["profile_url"] or row["identity_key"],
                "candidate_name": row["display_name"],
                "outcome": row["terminal_decision"],
                "confidence": payload.get("confidence", 0.0),
                "source_string_id": payload.get("source_string_id"),
                "timestamp": payload.get("timestamp", row["last_seen_at"]),
            }
        )
    return history


def write_linkedin_candidate_history_projection(
    store: RuntimeStateStore,
    *,
    brief_id: str,
    path: str | Path,
) -> list[dict]:
    history = project_linkedin_candidate_history(store, brief_id=brief_id)
    _write_jsonl_atomic(path, history)
    return history


def project_linkedin_search_memory(store: RuntimeStateStore, *, brief_id: str) -> dict:
    memory: dict = {}
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT payload_json, checkpoint_json, family_key, novelty_bucket, domain_lane, result_count,
                   candidates_discovered, facial_yes_count, facial_no_count, saves_count, notes
            FROM work_units
            WHERE source = 'linkedin' AND brief_id = ? AND kind = ? AND status = 'done'
            ORDER BY ordering_index ASC, id ASC
            """,
            (brief_id, LINKEDIN_STRING_KIND),
        ).fetchall()
    strings = []
    for row in rows:
        payload = _json_loads(row["payload_json"])
        checkpoint = _json_loads(row["checkpoint_json"])
        strings.append(
            SearchString.from_dict(
                {
                    "id": payload.get("id"),
                    "name": payload.get("name", ""),
                    "boolean": payload.get("boolean", ""),
                    "status": "done",
                    "result_count": row["result_count"],
                    "pages_reviewed": checkpoint.get("pages_reviewed", payload.get("pages_reviewed", 0)),
                    "saves": list(payload.get("saves", [])),
                    "notes": row["notes"] or payload.get("notes", ""),
                    "block": payload.get("block", ""),
                    "subblock": payload.get("subblock", ""),
                    "string_type": payload.get("string_type", ""),
                    "facial_yes_count": row["facial_yes_count"],
                    "facial_no_count": row["facial_no_count"],
                    "candidates_count": row["candidates_discovered"],
                    "duplicates_count": checkpoint.get("duplicates_count", payload.get("duplicates_count", 0)),
                    "phase": payload.get("phase", "scout"),
                    "original_boolean": payload.get("original_boolean", ""),
                    "refinement_stack": payload.get("refinement_stack", []),
                    "family_key": row["family_key"],
                    "novelty_bucket": row["novelty_bucket"],
                    "domain_lane": row["domain_lane"],
                }
            )
        )
    if strings:
        memory = update_search_memory(memory, brief_id, strings)
    return memory


def write_linkedin_search_memory_projection(
    store: RuntimeStateStore,
    *,
    brief_id: str,
    path: str | Path,
) -> dict:
    memory = project_linkedin_search_memory(store, brief_id=brief_id)
    _write_json_atomic(path, memory)
    return memory


def _write_json_atomic(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def _write_jsonl_atomic(path: str | Path, records: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    tmp.replace(path)


def _json_loads(raw: str | None) -> Any:
    if not raw:
        return {}
    return json.loads(raw)
