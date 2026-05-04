"""Tests for checkpoint snapshots backed by runtime_state."""

from __future__ import annotations

import json

from shared.runtime_state import RuntimeStateStore
from shared.runtime_state.store import LINKEDIN_STRING_KIND
from shared.schemas import SearchString
from shared.session_checkpoints import create_checkpoint, restore_checkpoint


def test_restore_rebuilds_projections_from_runtime_state(tmp_path, monkeypatch):
    output_dir = tmp_path / "linkedin-output"
    output_dir.mkdir()

    monkeypatch.setattr(
        "shared.session_checkpoints._resolve_brief_metadata",
        lambda brief_path: ("brief-1", "brief-1"),
    )

    store = RuntimeStateStore(output_dir / "runtime_state.sqlite3")
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-1",
        output_dir=str(output_dir),
        mode="fresh",
        resume_state={"brief_name": "brief-1"},
    )
    store.update_run_resume_state(
        run_id,
        {
            "brief_name": "brief-1",
            "current_string_id": 1,
            "current_page": 2,
            "pending_block_name": "Builders",
            "pending_block_string_ids": [1],
            "pending_block_ready": True,
            "candidates_saved": 1,
        },
    )
    search_string = SearchString(
        id=1,
        name="Payments edge case",
        boolean="payments AND fednow",
        status="done",
        result_count=5,
        pages_reviewed=2,
        saves=["Alice"],
        family_key="payments",
        novelty_bucket="edge_case",
        domain_lane="payments",
        candidates_count=4,
        duplicates_count=1,
        facial_yes_count=1,
        facial_no_count=2,
        facial_borderline_count=1,
    )
    store.upsert_work_unit(
        run_id=run_id,
        source="linkedin",
        brief_id="brief-1",
        kind=LINKEDIN_STRING_KIND,
        source_unit_id="1",
        display_name=search_string.name,
        ordering_index=0,
        status="done",
        payload=search_string.to_dict(),
        checkpoint={"pages_reviewed": 2, "duplicates_count": 1},
        family_key=search_string.family_key,
        novelty_bucket=search_string.novelty_bucket,
        domain_lane=search_string.domain_lane,
        counters={
            "result_count": search_string.result_count,
            "candidates_discovered": search_string.candidates_count,
            "facial_yes_count": search_string.facial_yes_count,
            "facial_no_count": search_string.facial_no_count,
            "facial_borderline_count": search_string.facial_borderline_count,
            "saves_count": len(search_string.saves),
        },
    )
    store.record_candidate_discovery(
        run_id=run_id,
        work_unit_id=None,
        source="linkedin",
        brief_id="brief-1",
        identity_key="https://linkedin.com/in/alice",
        display_name="Alice",
        profile_url="https://linkedin.com/in/alice",
    )
    store.set_candidate_state(
        run_id=run_id,
        source="linkedin",
        brief_id="brief-1",
        identity_key="https://linkedin.com/in/alice",
        new_state="failed_terminal",
        terminal_decision="SAVE",
        terminal_payload={
            "confidence": 0.95,
            "source_string_id": 1,
            "timestamp": "2026-04-06T00:00:00+00:00",
        },
    )

    checkpoint = create_checkpoint(output_dir, "ignored.json")
    assert "runtime_state.sqlite3" in checkpoint["present_files"]
    assert checkpoint["runtime_state_run_id"] == run_id

    (output_dir / "progress.json").write_text(json.dumps({"brief_name": "corrupt", "strings": []}))
    history_path = output_dir / "candidate_history-brief-1.jsonl"
    memory_path = output_dir / "search_memory-brief-1.json"
    if history_path.exists():
        history_path.unlink()
    if memory_path.exists():
        memory_path.unlink()

    result = restore_checkpoint(output_dir, checkpoint["id"])

    assert result["checkpoint"]["id"] == checkpoint["id"]
    progress = json.loads((output_dir / "progress.json").read_text())
    assert progress["current_string_id"] == 1
    assert progress["pending_block_ready"] is True
    assert "Alice" in history_path.read_text()
    assert json.loads(memory_path.read_text())["project_id"] == "brief-1"
    # C2 (slice 15): facial_borderline_count round-trips through the canonical
    # SQLite store and out via the progress projection.
    restored_string = next(s for s in progress["strings"] if s["id"] == 1)
    assert restored_string["facial_yes_count"] == 1
    assert restored_string["facial_no_count"] == 2
    assert restored_string["facial_borderline_count"] == 1
