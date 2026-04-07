"""Checkpoint snapshots for LinkedIn sourcing session state."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.brief_loader import load_brief
from shared.runtime_state import RuntimeStateStore, rebuild_compat_projections

CHECKPOINTS_DIRNAME = "session-checkpoints"
MANIFEST_FILENAME = "manifest.json"
RESTORE_BACKUPS_DIRNAME = "_restore_backups"
RUNTIME_DB_FILENAME = "runtime_state.sqlite3"


def _checkpoints_dir(output_dir: str | Path) -> Path:
    return Path(output_dir) / CHECKPOINTS_DIRNAME


def _manifest_path(output_dir: str | Path) -> Path:
    return _checkpoints_dir(output_dir) / MANIFEST_FILENAME


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _load_manifest(output_dir: str | Path) -> dict[str, Any]:
    manifest_path = _manifest_path(output_dir)
    if not manifest_path.exists():
        return {"checkpoints": []}
    return json.loads(manifest_path.read_text())


def _save_manifest(output_dir: str | Path, manifest: dict[str, Any]) -> None:
    manifest_path = _manifest_path(output_dir)
    _ensure_parent(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2))


def _next_checkpoint_id(manifest: dict[str, Any]) -> int:
    existing = manifest.get("checkpoints", [])
    if not existing:
        return 1
    return max(int(entry.get("id", 0)) for entry in existing) + 1


def _resolve_brief_metadata(brief_path: str | Path) -> tuple[str, str]:
    brief = load_brief(str(brief_path))
    brief_id = brief.linkedin_project_id or Path(str(brief_path)).stem
    return brief.id, brief_id


def _managed_runtime_files(brief_id: str) -> list[str]:
    runtime_files = [
        "progress.json",
        "execution_plan.json",
        "kit_strings.json",
        "snippets.jsonl",
        "facial_judgments.jsonl",
        "final_judgments.jsonl",
        "profile_summaries.jsonl",
        f"candidate_history-{brief_id}.jsonl",
        f"bias_monitor-{brief_id}.json",
        f"search_memory-{brief_id}.json",
        f"noise_discoveries-{brief_id}.jsonl",
    ]
    runtime_files.extend(_runtime_db_sidecars())
    return runtime_files


def _runtime_db_sidecars() -> list[str]:
    return [
        RUNTIME_DB_FILENAME,
        f"{RUNTIME_DB_FILENAME}-wal",
        f"{RUNTIME_DB_FILENAME}-shm",
    ]


def create_checkpoint(
    output_dir: str | Path,
    brief_path: str | Path,
    *,
    label: str = "",
    shutdown_reason: str = "",
    stats: dict[str, Any] | None = None,
    session_slot: int | None = None,
    checkpoint_id: int | None = None,
) -> dict[str, Any]:
    """Create a restorable snapshot of the current LinkedIn sourcing state."""
    output_dir = Path(output_dir)
    manifest = _load_manifest(output_dir)
    brief_name, brief_id = _resolve_brief_metadata(brief_path)
    checkpoint_id = checkpoint_id or _next_checkpoint_id(manifest)
    created_at = datetime.now(timezone.utc).isoformat()

    checkpoint_dir = _checkpoints_dir(output_dir) / f"{checkpoint_id:04d}"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    present_files: list[str] = []
    absent_files: list[str] = []
    for rel_path in _managed_runtime_files(brief_id):
        src = output_dir / rel_path
        dest = checkpoint_dir / rel_path
        if src.exists():
            _ensure_parent(dest)
            shutil.copy2(src, dest)
            present_files.append(rel_path)
        else:
            absent_files.append(rel_path)

    progress_summary: dict[str, Any] = {}
    progress_path = output_dir / "progress.json"
    if progress_path.exists():
        progress = json.loads(progress_path.read_text())
        progress_summary = {
            "current_string_id": progress.get("current_string_id"),
            "current_page": progress.get("current_page"),
            "pending_block_name": progress.get("pending_block_name", ""),
            "pending_block_string_ids": progress.get("pending_block_string_ids", []),
            "pending_block_ready": progress.get("pending_block_ready", False),
        }

    entry = {
        "id": checkpoint_id,
        "label": label or f"session-{session_slot}" if session_slot is not None else f"checkpoint-{checkpoint_id}",
        "created_at": created_at,
        "brief_path": str(brief_path),
        "brief_name": brief_name,
        "brief_id": brief_id,
        "session_slot": session_slot,
        "shutdown_reason": shutdown_reason,
        "stats": stats or {},
        "present_files": present_files,
        "absent_files": absent_files,
        "progress_summary": progress_summary,
    }

    runtime_db_path = output_dir / RUNTIME_DB_FILENAME
    if runtime_db_path.exists():
        store = RuntimeStateStore(runtime_db_path)
        latest_run = store.get_latest_run(source="linkedin", brief_id=brief_name)
        if latest_run:
            entry["runtime_state_run_id"] = int(latest_run["id"])
            entry["runtime_state_source"] = latest_run["source"]

    checkpoints = [cp for cp in manifest.get("checkpoints", []) if int(cp.get("id", 0)) != checkpoint_id]
    checkpoints.append(entry)
    checkpoints.sort(key=lambda cp: int(cp.get("id", 0)))
    manifest["checkpoints"] = checkpoints
    _save_manifest(output_dir, manifest)
    return entry


def list_checkpoints(output_dir: str | Path) -> list[dict[str, Any]]:
    manifest = _load_manifest(output_dir)
    return sorted(manifest.get("checkpoints", []), key=lambda cp: int(cp.get("id", 0)))


def restore_checkpoint(output_dir: str | Path, checkpoint_id: int) -> dict[str, Any]:
    """Restore a checkpoint into the active output directory."""
    output_dir = Path(output_dir)
    manifest = _load_manifest(output_dir)
    entry = next(
        (cp for cp in manifest.get("checkpoints", []) if int(cp.get("id", 0)) == int(checkpoint_id)),
        None,
    )
    if not entry:
        raise ValueError(f"Checkpoint {checkpoint_id} not found")

    checkpoint_dir = _checkpoints_dir(output_dir) / f"{int(checkpoint_id):04d}"
    if not checkpoint_dir.exists():
        raise ValueError(f"Checkpoint directory missing for {checkpoint_id}")

    restore_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = _checkpoints_dir(output_dir) / RESTORE_BACKUPS_DIRNAME / restore_stamp

    managed_paths = set(entry.get("present_files", [])) | set(entry.get("absent_files", []))
    for rel_path in sorted(managed_paths):
        live_path = output_dir / rel_path
        if live_path.exists():
            backup_path = backup_dir / rel_path
            _ensure_parent(backup_path)
            shutil.copy2(live_path, backup_path)

    for rel_path in entry.get("present_files", []):
        src = checkpoint_dir / rel_path
        dest = output_dir / rel_path
        _ensure_parent(dest)
        shutil.copy2(src, dest)

    for rel_path in entry.get("absent_files", []):
        live_path = output_dir / rel_path
        if live_path.exists():
            live_path.unlink()

    runtime_run_id = entry.get("runtime_state_run_id")
    runtime_db_path = output_dir / RUNTIME_DB_FILENAME
    if runtime_run_id and runtime_db_path.exists():
        store = RuntimeStateStore(runtime_db_path)
        rebuild_compat_projections(
            store,
            run_id=int(runtime_run_id),
            output_dir=output_dir,
        )

    return {
        "checkpoint": entry,
        "backup_dir": str(backup_dir),
    }
