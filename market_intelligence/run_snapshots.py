"""Run snapshot helpers for market-intelligence ingestion."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from market_intelligence.research_context import maybe_build_and_persist_research_packet
from market_intelligence.schema import MarketEvidenceBatch
from shared.brief_loader import Brief, load_brief
from shared.output_paths import (
    derive_market_key_from_brief,
    github_state_key,
    is_run_dir,
    linkedin_state_key,
    resolve_run_dir,
    slugify_output_component,
    utc_stamp,
)
from shared.runtime_state.projections import (
    write_github_progress_projection,
    write_github_stage_projections,
    write_linkedin_progress_projection,
    write_linkedin_search_memory_projection,
    write_linkedin_stage_projections,
)
from shared.runtime_state.store import RuntimeStateStore
from shared.storage import read_json, read_jsonl, write_json


RUNTIME_DB_FILENAMES = (
    "runtime_state.sqlite3",
    "runtime_state.sqlite3-wal",
    "runtime_state.sqlite3-shm",
)

SNAPSHOT_PATTERNS: dict[str, tuple[str, ...]] = {
    "linkedin": (
        "run-report-input.json",
        "run-report.json",
        "run-report.md",
        "final_judgments.jsonl",
        "profile_summaries.jsonl",
        "snippets.jsonl",
        "facial_judgments.jsonl",
        "run_log.jsonl",
        "progress.json",
        "execution_plan.json",
        "kit_strings.json",
        "market-intel-research-input.json",
        "market_intel/*.json",
        "market_intel/*.jsonl",
        "search_memory-*.json",
        "bias_monitor-*.json",
        "noise_discoveries-*.jsonl",
        "candidate_history-*.jsonl",
        *RUNTIME_DB_FILENAMES,
    ),
    "github": (
        "final_judgments.jsonl",
        "profile_summaries.jsonl",
        "snippets.jsonl",
        "facial_judgments.jsonl",
        "candidates.jsonl",
        "outreach.jsonl",
        "saves.jsonl",
        "run_log.jsonl",
        "progress.json",
        "market-intel-research-input.json",
        "market_intel/*.json",
        "market_intel/*.jsonl",
        "session_*_candidates.json",
        "session_*_graph.json",
        "session_*_metrics.jsonl",
        "session_*_report.md",
        "session_*_strategy.jsonl",
        *RUNTIME_DB_FILENAMES,
    ),
}

SCOPED_ARTIFACT_PREFIXES: dict[str, tuple[str, ...]] = {
    "linkedin": (
        "search_memory-",
        "bias_monitor-",
        "noise_discoveries-",
        "candidate_history-",
    ),
}


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _artifact_matches_brief_scope(*, source: str, path: Path, brief_id: str | None) -> bool:
    if not brief_id:
        return True
    prefixes = SCOPED_ARTIFACT_PREFIXES.get(source, ())
    name = path.name
    for prefix in prefixes:
        if not name.startswith(prefix):
            continue
        remainder = name[len(prefix) :]
        return remainder == brief_id or remainder.startswith(f"{brief_id}.") or remainder.startswith(
            f"{brief_id}-"
        )
    return True


def _copy_artifacts(
    source_dir: Path,
    run_dir: Path,
    patterns: tuple[str, ...],
    *,
    source: str,
    brief_id: str | None = None,
) -> list[str]:
    copied: list[str] = []
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(source_dir.glob(pattern))
    for src in _dedupe_paths(sorted(matches)):
        if not src.exists() or src.is_dir():
            continue
        if not _artifact_matches_brief_scope(source=source, path=src, brief_id=brief_id):
            continue
        try:
            relative = src.relative_to(source_dir)
        except ValueError:
            relative = Path(src.name)
        dest = run_dir / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(str(relative))
    return sorted(set(copied))


def _best_run_record(
    *,
    source_dir: Path,
    source: str,
    brief_id: str,
    requested_run_id: int | None,
) -> dict[str, Any]:
    db_path = source_dir / "runtime_state.sqlite3"
    if not db_path.exists():
        return {}
    store = RuntimeStateStore(db_path)
    if requested_run_id is not None:
        return store.get_run(int(requested_run_id)) or {}
    latest = store.get_latest_run(source=source, brief_id=brief_id)
    if latest:
        return latest
    rows = store.list_runs(source=source, brief_id=brief_id)
    return rows[0] if rows else {}


def _compact_run_stamp(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return utc_stamp()
    return (
        text.replace(":", "-")
        .replace("+00:00", "Z")
        .replace(" ", "T")
        .replace(".", "-")
    )


def _parse_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _filter_run_log_to_window(
    *,
    run_dir: Path,
    started_at: str,
    ended_at: str,
) -> None:
    path = run_dir / "run_log.jsonl"
    if not path.exists():
        return
    start_dt = _parse_timestamp(started_at)
    end_dt = _parse_timestamp(ended_at)
    if not start_dt and not end_dt:
        return

    filtered: list[dict[str, Any]] = []
    for record in read_jsonl(path):
        if not isinstance(record, dict):
            continue
        event_dt = _parse_timestamp(str(record.get("timestamp", "")))
        if event_dt is None:
            continue
        if start_dt and event_dt < start_dt:
            continue
        if end_dt and event_dt > end_dt:
            continue
        filtered.append(record)

    with path.open("w") as handle:
        for record in filtered:
            handle.write(f"{json.dumps(record, sort_keys=True)}\n")


def _coerce_run_id(value: int | str | None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_optional_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return read_json(path)


def _brief_match_keys(*, brief_path: Path, brief: Brief, raw: dict) -> set[str]:
    return {
        slugify_output_component(brief.role_title),
        slugify_output_component(brief.id),
        slugify_output_component(str(raw.get("linkedin_project_id", ""))),
        slugify_output_component(brief_path.stem),
    }


def _metadata_matches_brief(
    metadata: dict | None,
    *,
    brief_path: Path,
    brief: Brief,
    raw: dict,
) -> bool:
    if not metadata:
        return False
    expected = _brief_match_keys(brief_path=brief_path, brief=brief, raw=raw)
    values = (
        metadata.get("role_title"),
        metadata.get("brief_name"),
        metadata.get("linkedin_project_id"),
    )
    for value in values:
        if slugify_output_component(str(value or "")) in expected:
            return True
    return False


def _scrub_mismatched_report_files(
    *,
    run_dir: Path,
    brief_path: Path,
    brief: Brief,
    raw: dict,
) -> None:
    for filename in ("run-report.json", "run-report-input.json"):
        path = run_dir / filename
        if not path.exists():
            continue
        payload = _load_optional_json(path) or {}
        metadata = payload.get("run_metadata") if isinstance(payload, dict) else None
        if _metadata_matches_brief(metadata, brief_path=brief_path, brief=brief, raw=raw):
            continue
        path.unlink(missing_ok=True)


def _runtime_brief_id(*, source: str, brief: Brief, raw: dict, brief_path: Path) -> str:
    if source == "linkedin":
        return str(raw.get("linkedin_project_id") or brief.linkedin_project_id or brief.id or brief_path.stem)
    return str(brief.id or brief.role_title or brief_path.stem)


def _rebuild_run_scoped_projections(
    *,
    source: str,
    run_dir: Path,
    source_dir: Path,
    brief_id: str,
    run_id: int | None,
) -> None:
    def _try_projection(builder: Any, /, *args: Any, **kwargs: Any) -> None:
        # Legacy runtime payloads are not always shape-stable enough to rebuild
        # every compatibility projection. Snapshot creation should preserve the
        # run whenever possible instead of failing the whole import.
        try:
            builder(*args, **kwargs)
        except (TypeError, ValueError, KeyError):
            return

    if run_id is None:
        return
    db_path = source_dir / "runtime_state.sqlite3"
    if not db_path.exists():
        return
    store = RuntimeStateStore(db_path)
    if source == "linkedin":
        _try_projection(write_linkedin_progress_projection, store, run_id, run_dir / "progress.json")
        _try_projection(
            write_linkedin_stage_projections,
            store,
            brief_id=brief_id,
            output_dir=run_dir,
            run_id=run_id,
        )
        _try_projection(
            write_linkedin_search_memory_projection,
            store,
            brief_id=brief_id,
            path=run_dir / f"search_memory-{brief_id}.json",
            run_id=run_id,
        )
        return
    _try_projection(write_github_progress_projection, store, run_id, run_dir / "progress.json")
    _try_projection(
        write_github_stage_projections,
        store,
        brief_id=brief_id,
        output_dir=run_dir,
        run_id=run_id,
    )


def _metrics_summary_from_report(report: dict | None, final_records: list[dict]) -> dict:
    report_metrics = (report or {}).get("metrics_summary", {})
    candidate_volume = int(report_metrics.get("candidates_evaluated", 0) or 0)
    saved = int(report_metrics.get("saved", 0) or 0)
    rejected = int(report_metrics.get("rejected", 0) or 0)
    facial_yes = int(report_metrics.get("facial_yes", 0) or 0)
    facial_no = int(report_metrics.get("facial_no", 0) or 0)
    if final_records and candidate_volume <= 0:
        candidate_volume = len(final_records)
    return {
        "run_count": 1,
        "candidate_volume": candidate_volume,
        "saved": saved,
        "rejected": rejected,
        "facial_yes": facial_yes,
        "facial_no": facial_no,
    }


def _research_batch_from_run_dir(
    *,
    brief_path: Path,
    brief: Brief,
    raw: dict,
    source: str,
    run_dir: Path,
    run_id: int | None,
    brief_version: str,
    generated_at: str,
    reconstruct_report_analysis: bool,
) -> MarketEvidenceBatch:
    report = _load_optional_json(run_dir / "run-report.json")
    report_input = _load_optional_json(run_dir / "run-report-input.json")
    if report and not _metadata_matches_brief(
        report.get("run_metadata"),
        brief_path=brief_path,
        brief=brief,
        raw=raw,
    ):
        report = None
        report_input = None
    elif report_input and not _metadata_matches_brief(
        report_input.get("run_metadata"),
        brief_path=brief_path,
        brief=brief,
        raw=raw,
    ):
        report_input = None
    final_records = read_jsonl(run_dir / "final_judgments.jsonl")
    search_memory = None
    search_memory_paths = sorted(run_dir.glob("search_memory-*.json"))
    if search_memory_paths:
        search_memory = read_json(search_memory_paths[0])
    batch = MarketEvidenceBatch(
        run_ref=f"{source}:{run_dir}",
        source=source,
        output_dir=str(run_dir),
        run_id=run_id,
        brief_version=brief_version,
        generated_at=generated_at,
        report=report,
        report_input=report_input,
        search_memory=search_memory,
        final_judgments=final_records,
        metrics_summary=_metrics_summary_from_report(report, final_records),
        is_complete=True,
    )
    if source == "linkedin":
        batch = maybe_build_and_persist_research_packet(
            batch,
            reconstruct_report_analysis=reconstruct_report_analysis,
        )
    return batch


def _write_manifest(
    *,
    run_dir: Path,
    source: str,
    brief_path: str | Path,
    brief_id: str,
    market_key: str,
    run_id: int | str | None,
    started_at: str,
    ended_at: str,
    state_dir: str,
    artifacts_present: list[str],
    analysis_provenance: str,
    context_quality: str,
    imported_from: str = "",
) -> Path:
    manifest = {
        "source": source,
        "brief_id": brief_id,
        "brief_path": str(Path(brief_path).resolve()),
        "market_key": market_key,
        "run_id": run_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "state_dir": state_dir,
        "analysis_provenance": analysis_provenance,
        "context_quality": context_quality,
        "artifacts_present": artifacts_present,
        "research_input_path": str(run_dir / "market-intel-research-input.json"),
    }
    if imported_from:
        manifest["imported_from"] = imported_from
    path = run_dir / "run-manifest.json"
    write_json(path, manifest)
    return path


def _brief_namespace_key(
    *,
    source: str,
    brief_path: str | Path,
    brief: Brief,
    raw: dict,
) -> str:
    if source == "linkedin":
        return linkedin_state_key(brief_path=brief_path, brief=brief, raw=raw)
    return github_state_key(brief_path=brief_path, brief=brief)


def finalize_run_snapshot(
    *,
    source: str,
    brief_path: str | Path,
    state_dir: str | Path,
    run_id: int | None = None,
    output_root: str | Path | None = None,
) -> Path:
    brief_path = Path(brief_path)
    state_dir = Path(state_dir).resolve()
    brief = load_brief(str(brief_path))
    raw = read_json(brief_path)
    brief_key = _brief_namespace_key(source=source, brief_path=brief_path, brief=brief, raw=raw)
    market_key = derive_market_key_from_brief(brief_path=brief_path, brief=brief, raw=raw)
    runtime_brief_id = _runtime_brief_id(source=source, brief=brief, raw=raw, brief_path=brief_path)

    run_record = _best_run_record(
        source_dir=state_dir,
        source=source,
        brief_id=runtime_brief_id,
        requested_run_id=run_id,
    )
    started_at = str(run_record.get("started_at", "") or "")
    ended_at = str(run_record.get("ended_at", "") or "")
    actual_run_id = run_record.get("id", run_id)
    run_stamp = _compact_run_stamp(ended_at or started_at or utc_stamp())

    run_dir = resolve_run_dir(
        source=source,
        brief_id=brief_key,
        run_stamp=run_stamp,
        run_id=actual_run_id,
        output_root=output_root or state_dir,
    )
    artifacts_present = _copy_artifacts(
        state_dir,
        run_dir,
        SNAPSHOT_PATTERNS[source],
        source=source,
        brief_id=runtime_brief_id,
    )
    scoped_run_id = _coerce_run_id(actual_run_id)
    _rebuild_run_scoped_projections(
        source=source,
        run_dir=run_dir,
        source_dir=state_dir,
        brief_id=runtime_brief_id,
        run_id=scoped_run_id,
    )
    _scrub_mismatched_report_files(
        run_dir=run_dir,
        brief_path=brief_path,
        brief=brief,
        raw=raw,
    )
    _filter_run_log_to_window(
        run_dir=run_dir,
        started_at=started_at,
        ended_at=ended_at,
    )
    batch = _research_batch_from_run_dir(
        brief_path=brief_path,
        brief=brief,
        raw=raw,
        source=source,
        run_dir=run_dir,
        run_id=scoped_run_id,
        brief_version=str(raw.get("version", "")),
        generated_at=ended_at or started_at or utc_stamp(),
        reconstruct_report_analysis=source == "linkedin" and not (run_dir / "run-report.json").exists(),
    )
    if batch.research_input_path:
        artifacts_present = sorted(set(artifacts_present + ["market-intel-research-input.json"]))
    _write_manifest(
        run_dir=run_dir,
        source=source,
        brief_path=brief_path,
        brief_id=brief_key,
        market_key=market_key,
        run_id=actual_run_id,
        started_at=started_at,
        ended_at=ended_at,
        state_dir=str(state_dir),
        artifacts_present=artifacts_present,
        analysis_provenance=batch.analysis_provenance or "none",
        context_quality=batch.context_quality or "",
    )
    return run_dir


def import_legacy_run_snapshot(
    *,
    brief_path: str | Path,
    legacy_output_dir: str | Path,
    source: str = "linkedin",
    run_id: int | None = None,
    reconstruct_report_analysis: bool = False,
    legacy_index: int = 1,
) -> Path:
    brief_path = Path(brief_path)
    legacy_output_dir = Path(legacy_output_dir).resolve()
    brief = load_brief(str(brief_path))
    raw = read_json(brief_path)
    brief_key = _brief_namespace_key(source=source, brief_path=brief_path, brief=brief, raw=raw)
    market_key = derive_market_key_from_brief(brief_path=brief_path, brief=brief, raw=raw)
    runtime_brief_id = _runtime_brief_id(source=source, brief=brief, raw=raw, brief_path=brief_path)

    run_record = _best_run_record(
        source_dir=legacy_output_dir,
        source=source,
        brief_id=runtime_brief_id,
        requested_run_id=run_id,
    )
    started_at = str(run_record.get("started_at", "") or "")
    ended_at = str(run_record.get("ended_at", "") or "")
    actual_run_id = run_record.get("id", run_id)
    run_stamp = _compact_run_stamp(ended_at or started_at or utc_stamp())

    run_dir = resolve_run_dir(
        source=source,
        brief_id=brief_key,
        run_stamp=run_stamp,
        run_id=actual_run_id,
        imported=True,
        legacy_index=legacy_index,
        output_root=legacy_output_dir,
    )
    artifacts_present = _copy_artifacts(
        legacy_output_dir,
        run_dir,
        SNAPSHOT_PATTERNS[source],
        source=source,
        brief_id=runtime_brief_id,
    )
    scoped_run_id = _coerce_run_id(actual_run_id)
    _rebuild_run_scoped_projections(
        source=source,
        run_dir=run_dir,
        source_dir=legacy_output_dir,
        brief_id=runtime_brief_id,
        run_id=scoped_run_id,
    )
    _scrub_mismatched_report_files(
        run_dir=run_dir,
        brief_path=brief_path,
        brief=brief,
        raw=raw,
    )
    _filter_run_log_to_window(
        run_dir=run_dir,
        started_at=started_at,
        ended_at=ended_at,
    )
    batch = _research_batch_from_run_dir(
        brief_path=brief_path,
        brief=brief,
        raw=raw,
        source=source,
        run_dir=run_dir,
        run_id=scoped_run_id,
        brief_version=str(raw.get("version", "")),
        generated_at=ended_at or started_at or utc_stamp(),
        reconstruct_report_analysis=reconstruct_report_analysis,
    )
    if batch.research_input_path:
        artifacts_present = sorted(set(artifacts_present + ["market-intel-research-input.json"]))
    _write_manifest(
        run_dir=run_dir,
        source=source,
        brief_path=brief_path,
        brief_id=brief_key,
        market_key=market_key,
        run_id=actual_run_id,
        started_at=started_at,
        ended_at=ended_at,
        state_dir=str(legacy_output_dir),
        artifacts_present=artifacts_present,
        analysis_provenance=batch.analysis_provenance or "none",
        context_quality=batch.context_quality or "",
        imported_from=str(legacy_output_dir),
    )
    return run_dir


def load_run_manifest(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    manifest_path = run_dir / "run-manifest.json"
    if not manifest_path.exists():
        return {}
    return read_json(manifest_path)


def validate_run_dir_for_ingestion(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir).resolve()
    if not is_run_dir(run_dir):
        raise ValueError(f"Expected a finalized run_dir under output/runs/, got: {run_dir}")
    if not (run_dir / "run-manifest.json").exists():
        raise ValueError(f"Run dir is missing run-manifest.json: {run_dir}")
    return run_dir
