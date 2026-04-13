"""Shared output-directory contract helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from shared import config
from shared.brief_loader import Brief, load_brief
from shared.storage import read_json


OUTPUT_ROOT = config.OUTPUT_DIR
STATE_ROOT = OUTPUT_ROOT / "state"
RUNS_ROOT = OUTPUT_ROOT / "runs"
MARKET_INTELLIGENCE_ROOT = OUTPUT_ROOT / "market_intelligence"
EXPORTS_ROOT = OUTPUT_ROOT / "exports"
ARCHIVE_ROOT = OUTPUT_ROOT / "archive"
CACHE_ROOT = OUTPUT_ROOT / "cache"
DEBUG_ROOT = OUTPUT_ROOT / "debug"

for _root in (
    STATE_ROOT,
    RUNS_ROOT,
    MARKET_INTELLIGENCE_ROOT,
    EXPORTS_ROOT,
    ARCHIVE_ROOT,
    CACHE_ROOT,
    DEBUG_ROOT,
):
    _root.mkdir(parents=True, exist_ok=True)


def slugify_output_component(value: str) -> str:
    lowered = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or ""))
    while "__" in lowered:
        lowered = lowered.replace("__", "_")
    return lowered.strip("_") or "unknown"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _parts_after_output(path: str | Path) -> tuple[Path, tuple[str, ...]] | None:
    resolved = Path(path).resolve()
    parts = resolved.parts
    try:
        index = len(parts) - 1 - list(reversed(parts)).index("output")
    except ValueError:
        return None
    return resolved, parts[index + 1 :]


def output_root_for_path(path: str | Path | None) -> Path:
    if path is None:
        return OUTPUT_ROOT
    parsed = _parts_after_output(path)
    if parsed is None:
        return OUTPUT_ROOT
    resolved, tail = parsed
    return resolved if not tail else resolved.parents[len(tail) - 1]


def classify_output_location(path: str | Path | None) -> str:
    if path is None:
        return "unknown"
    parsed = _parts_after_output(path)
    if parsed is None:
        return "external"
    _, tail = parsed
    if not tail:
        return "output_root"
    if tail[0] == "state":
        return "state_dir" if len(tail) >= 3 else "state_root"
    if tail[0] == "runs":
        return "run_dir" if len(tail) >= 4 else "runs_root"
    if tail[0] == "market_intelligence":
        return "market_dir" if len(tail) >= 2 else "market_root"
    if tail[0] == "exports":
        return "exports_dir"
    if tail[0] == "archive":
        return "archive_dir"
    if tail[0] == "cache":
        return "cache_dir"
    if tail[0] == "debug":
        return "debug_dir"
    return "legacy_output"


def is_output_root(path: str | Path | None) -> bool:
    return classify_output_location(path) == "output_root"


def is_state_dir(path: str | Path | None) -> bool:
    return classify_output_location(path) == "state_dir"


def is_run_dir(path: str | Path | None) -> bool:
    return classify_output_location(path) == "run_dir"


def source_state_root(source: str, *, output_root: str | Path | None = None) -> Path:
    root = output_root_for_path(output_root)
    path = root / "state" / slugify_output_component(source)
    path.mkdir(parents=True, exist_ok=True)
    return path


def source_runs_root(
    source: str,
    brief_id: str,
    *,
    output_root: str | Path | None = None,
) -> Path:
    root = output_root_for_path(output_root)
    path = root / "runs" / slugify_output_component(source) / slugify_output_component(brief_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def source_exports_root(
    source: str,
    brief_id: str,
    *,
    output_root: str | Path | None = None,
) -> Path:
    root = output_root_for_path(output_root)
    path = root / "exports" / slugify_output_component(source) / slugify_output_component(brief_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def source_archive_root(
    source: str,
    brief_id: str,
    *,
    output_root: str | Path | None = None,
) -> Path:
    root = output_root_for_path(output_root)
    path = root / "archive" / slugify_output_component(source) / slugify_output_component(brief_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def linkedin_state_key(
    *,
    brief_path: str | Path,
    brief: Brief | None = None,
    raw: dict | None = None,
) -> str:
    brief_path = Path(brief_path)
    raw = raw or read_json(brief_path)
    brief = brief or load_brief(str(brief_path))
    return slugify_output_component(
        str(raw.get("linkedin_project_id") or brief.linkedin_project_id or brief.id or brief_path.stem)
    )


def github_state_key(
    *,
    brief_path: str | Path,
    brief: Brief | None = None,
) -> str:
    brief_path = Path(brief_path)
    brief = brief or load_brief(str(brief_path))
    return slugify_output_component(brief.id or brief.role_title or brief_path.stem)


def derive_market_key_from_brief(
    *,
    brief_path: str | Path,
    brief: Brief | None = None,
    raw: dict | None = None,
) -> str:
    brief_path = Path(brief_path)
    raw = raw or read_json(brief_path)
    brief = brief or load_brief(str(brief_path))
    role_level = str(
        raw.get("role_level")
        or getattr(getattr(brief, "_new_brief", None), "role_level", "")
        or ""
    ).strip()
    geography = str(
        raw.get("geography")
        or brief.permanent_filters.get("Location")
        or ""
    ).strip()
    return "__".join(
        [
            slugify_output_component(brief.role_title),
            slugify_output_component(geography),
            slugify_output_component(role_level),
        ]
    )


def resolve_linkedin_state_dir(
    *,
    brief_path: str | Path,
    brief: Brief | None = None,
    raw: dict | None = None,
    state_dir: str | Path | None = None,
) -> Path:
    if state_dir:
        path = Path(state_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    key = linkedin_state_key(brief_path=brief_path, brief=brief, raw=raw)
    path = source_state_root("linkedin") / key
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_github_state_dir(
    *,
    brief_path: str | Path,
    brief: Brief | None = None,
    state_dir: str | Path | None = None,
) -> Path:
    if state_dir:
        path = Path(state_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    key = github_state_key(brief_path=brief_path, brief=brief)
    path = source_state_root("github") / key
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_run_dir(
    *,
    source: str,
    brief_id: str,
    run_stamp: str,
    run_id: int | str | None,
    imported: bool = False,
    legacy_index: int | None = None,
    output_root: str | Path | None = None,
) -> Path:
    parent = source_runs_root(source, brief_id, output_root=output_root)
    if imported:
        suffix = f"__legacy-{int(legacy_index or 1)}"
        name = f"imported-{run_stamp}{suffix}"
    else:
        suffix = f"__run-{run_id}" if run_id is not None else ""
        name = f"{run_stamp}{suffix}"
    path = parent / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def looks_like_finalized_run_dir(path: str | Path | None) -> bool:
    if not is_run_dir(path):
        return False
    if path is None:
        return False
    candidate = Path(path)
    if (candidate / "run-manifest.json").exists():
        return True
    required = (
        candidate / "final_judgments.jsonl",
        candidate / "runtime_state.sqlite3",
        candidate / "run-report.json",
    )
    return any(item.exists() for item in required)
