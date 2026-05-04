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

# A24 trial plan, Slice 1B: intake sessions are global (not per-state-dir
# and not per-source) because the brief-authoring conversation pre-dates
# any commitment to source or state_key.
INTAKE_ROOT = OUTPUT_ROOT / "intake"
INTAKE_DB_FILENAME = "intake_sessions.sqlite3"

# Phase F Slice F3: cross-module identity lives outside per-state-dir DBs
# because cross-source identity is, by definition, structurally incapable
# of being seen from within a single source's state_dir. The `_identity`
# prefix sits alongside `linkedin/` + `github/` under `state/` but starts
# with an underscore so `enumerate_state_dirs()` (which iterates only the
# canonical `_SOURCES = ("linkedin", "github")` tuple) never accidentally
# treats the identity DB's parent dir as a state_dir.
IDENTITY_ROOT = STATE_ROOT / "_identity"
IDENTITY_DB_FILENAME = "identity.sqlite3"

for _root in (
    STATE_ROOT,
    RUNS_ROOT,
    MARKET_INTELLIGENCE_ROOT,
    EXPORTS_ROOT,
    ARCHIVE_ROOT,
    CACHE_ROOT,
    DEBUG_ROOT,
    INTAKE_ROOT,
    IDENTITY_ROOT,
):
    _root.mkdir(parents=True, exist_ok=True)


def resolve_identity_db_path() -> Path:
    """Path to the global cross-module identity SQLite store.

    Cross-source identity (Phase F Slice F3) is fundamentally global —
    it merges duplicates across `output/state/linkedin/<key>/` and
    `output/state/github/<key>/`. Storing the persons table inside any
    one of those state-dirs would be structurally incapable of seeing
    the others, so F3 ships a separate global DB.

    Resolved against the live :data:`IDENTITY_ROOT` so tests that
    monkeypatch :data:`OUTPUT_ROOT` must also monkeypatch
    :data:`IDENTITY_ROOT` (mirrors the
    :func:`resolve_intake_db_path` pattern).
    """

    return IDENTITY_ROOT / IDENTITY_DB_FILENAME


def resolve_intake_db_path() -> Path:
    """Path to the global intake-sessions SQLite store.

    Distinct from per-state-dir ``runtime_state.sqlite3`` files: intake
    sessions are authored before any (source, state_key) commitment is
    made. The DB lives at ``output/intake/intake_sessions.sqlite3``.

    Resolved against the live :data:`INTAKE_ROOT` so tests that
    monkeypatch :data:`OUTPUT_ROOT` still need to write through this
    helper after also monkeypatching :data:`INTAKE_ROOT` (mirrors the
    pattern used by other output-path helpers — derived constants are
    not auto-recomputed when the root is patched).
    """

    return INTAKE_ROOT / INTAKE_DB_FILENAME


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
    """Derive the canonical LinkedIn state-key from brief content.

    Phase F Slice F2 added the `source_config.linkedin.project_id`
    lookup ahead of the flat `linkedin_project_id` fallback so the
    same hash holds across the migration: a brief that's been edited
    via F2's UI (writing the nested path) and one that still carries
    only the flat field produce the same state-key. Without the
    fallback, every existing state_dir would be orphaned the moment
    F2 introduced the new path.

    Resolution order:
      1. ``source_config.linkedin.project_id`` (V2 shape, F2 onward)
      2. ``linkedin_project_id`` flat field (Phase D and earlier)
      3. ``brief.linkedin_project_id`` from the parsed Brief
      4. ``brief.id``
      5. ``brief_path.stem`` (last-resort)
    """

    from shared.brief_v2_schema import linkedin_project_id_from_brief

    brief_path = Path(brief_path)
    raw = raw or read_json(brief_path)
    brief = brief or load_brief(str(brief_path))
    candidate = (
        linkedin_project_id_from_brief(raw)
        or brief.linkedin_project_id
        or brief.id
        or brief_path.stem
    )
    return slugify_output_component(str(candidate))


def github_state_key(
    *,
    brief_path: str | Path,
    brief: Brief | None = None,
) -> str:
    brief_path = Path(brief_path)
    brief = brief or load_brief(str(brief_path))
    return slugify_output_component(brief.id or brief.role_title or brief_path.stem)


def designer_state_key(
    *,
    brief_path: str | Path,
    brief: Brief | None = None,
) -> str:
    """Derive the canonical Designer state-key from brief content.

    Designer briefs don't carry a per-source identifier (no
    LinkedIn-style project_id) — same posture as GitHub. State-key
    falls back through brief.id → role_title → brief filename stem.
    """

    brief_path = Path(brief_path)
    brief = brief or load_brief(str(brief_path))
    return slugify_output_component(brief.id or brief.role_title or brief_path.stem)


def exec_search_state_key(
    *,
    brief_path: str | Path,
    brief: Brief | None = None,
) -> str:
    """Derive the canonical Executive Search state-key from brief content.

    Executive Search briefs reuse the LinkedIn evaluation pipeline but
    carry their own state directory under ``output/state/exec_search/``
    (separate from LinkedIn's so confidential briefs don't aggregate
    into the LinkedIn home view). Mirrors GitHub's posture: state-key
    falls back through brief.id → role_title → brief filename stem.
    No project_id concept — saves land in the Cloris-native shortlist
    destination shipping in Slice 7.
    """

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


def resolve_designer_state_dir(
    *,
    brief_path: str | Path,
    brief: Brief | None = None,
    state_dir: str | Path | None = None,
) -> Path:
    """Resolve the per-brief state directory for a Designer run.

    Mirrors :func:`resolve_github_state_dir`. The Designer state-key
    derives from brief content (no per-source identifier), and the
    state-dir lives under ``output/state/designer/<state_key>/``.
    Caches the SQLite asset blob, the canonical
    ``runtime_state.sqlite3``, and the JSONL projection files for the
    Designer module's lifetime + 30 days.
    """

    if state_dir:
        path = Path(state_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    key = designer_state_key(brief_path=brief_path, brief=brief)
    path = source_state_root("designer") / key
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_exec_search_state_dir(
    *,
    brief_path: str | Path,
    brief: Brief | None = None,
    state_dir: str | Path | None = None,
) -> Path:
    """Resolve the per-brief state directory for an Executive Search run.

    Mirrors :func:`resolve_github_state_dir`. State-dir lives under
    ``output/state/exec_search/<state_key>/``, separate from
    ``output/state/linkedin/`` so confidential briefs don't aggregate
    into LinkedIn's shared per-source views.
    """

    if state_dir:
        path = Path(state_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    key = exec_search_state_key(brief_path=brief_path, brief=brief)
    path = source_state_root("exec_search") / key
    path.mkdir(parents=True, exist_ok=True)
    return path


def researcher_state_key(
    *,
    brief_path: str | Path,
    brief: Brief | None = None,
) -> str:
    """Derive the canonical Researcher state-key from brief content.

    Researcher has no per-brief project_id concept (workspace is the
    only save destination per Researcher Module Spec Opinion 4), so the
    key resolves from ``brief.id`` → ``brief.role_title`` → file stem,
    mirroring :func:`github_state_key`.
    """

    brief_path = Path(brief_path)
    brief = brief or load_brief(str(brief_path))
    return slugify_output_component(brief.id or brief.role_title or brief_path.stem)


def resolve_researcher_state_dir(
    *,
    brief_path: str | Path,
    brief: Brief | None = None,
    state_dir: str | Path | None = None,
) -> Path:
    if state_dir:
        path = Path(state_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    key = researcher_state_key(brief_path=brief_path, brief=brief)
    path = source_state_root("researcher") / key
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
