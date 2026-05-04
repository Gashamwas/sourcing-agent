"""Per-source launcher registry — Phase F Slice F1.

The single source-of-truth that maps a `source` string (``"linkedin"``,
``"github"``, …) to the runtime callables a worker spawn needs:

- ``state_key_fn(brief_path) -> str`` — derive the canonical state-key
  from the brief content (NOT path), so the key stays stable across
  flat→nested brief migrations.
- ``state_dir_fn(brief_path) -> Path`` — resolve the on-disk state
  directory (``output/state/<source>/<state_key>``).
- ``orchestrator_argv_fn(brief_path, state_dir, *, resume) -> list[str]``
  — compose the argv ``cloris.worker`` execvp's into. This is the
  source-specific seam; everything else upstream is generic.

What the registry deliberately does NOT carry:

- Editorial taxonomy (display labels, deck copy). Those live in
  ``cloris/frontend/src/lib/sources.ts`` so copy iteration doesn't
  touch the spawn path.
- Per-source readiness probes — those live in
  ``linkedin/health.py`` / ``github/health.py`` and are dispatched
  separately by ``GET /api/launch-readiness/{source}/{brief_id}``.
- Per-brief save destinations (Phase F Slice F2) — those will be
  added to the registry as a fourth callable when F2 ships.

Contract notes:

- All callables are pure with respect to the registry; they may read
  the brief from disk and may compute state-key hashes, but they
  must be free of side effects.
- The registry is module-scope and immutable post-import; sources
  cannot be added at runtime.
- Sources that return ``None`` from ``state_key_fn`` (e.g., a brief
  that lacks the source-specific identifier) signal "this source
  cannot launch for this brief"; the API layer surfaces a 422 in
  that case.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class SaveDestinationBlocker:
    """Per-brief save-destination blocker for the launch-readiness probe.

    Phase F Slice F2. Mirrors :class:`linkedin.health.ReadinessBlocker`
    so the API handler can aggregate brief-readiness blockers alongside
    source-readiness blockers without conversion. ``kind`` is always
    ``"config"`` for save-destination blockers — the recruiter needs
    to fill in a configuration value before launch can proceed.
    """

    kind: str
    message: str
    remediation: str


@dataclass(frozen=True)
class LauncherEntry:
    """One source's runtime contract.

    See module docstring for what each callable owns.

    Phase F Slice F2 adds ``save_destination_blocker_fn``: given a
    brief on disk, returns a :class:`SaveDestinationBlocker` if the
    brief lacks the per-source destination needed to launch, else
    ``None``. The API handler aggregates this with the source-level
    readiness probe so a brief without a configured destination
    blocks launch before the worker spawns.
    """

    state_key_fn: Callable[[str], str]
    state_dir_fn: Callable[[str], Path]
    orchestrator_argv_fn: Callable[..., list[str]]
    save_destination_blocker_fn: Callable[
        [str], SaveDestinationBlocker | None
    ] = lambda brief_path: None


def _linkedin_state_key(brief_path: str) -> str:
    """Compute the canonical brief id for a LinkedIn launch.

    Reads the brief content (`linkedin_project_id` / `id` / stem
    fallback) so the value stays stable across flat→nested migrations.
    """

    from shared.output_paths import linkedin_state_key

    return linkedin_state_key(brief_path=brief_path)


def _linkedin_state_dir(brief_path: str) -> Path:
    from shared.output_paths import resolve_linkedin_state_dir

    return resolve_linkedin_state_dir(brief_path=brief_path)


def _linkedin_orchestrator_argv(
    brief_path: str,
    state_dir: str,
    *,
    resume: bool,
    python_executable: str = sys.executable,
) -> list[str]:
    """LinkedIn execvp argv.

    Mirrors the existing :func:`cloris.worker.build_session_orchestrator_argv`
    contract. Kept here as a thin wrapper so the registry holds one
    callable per source rather than reaching into ``cloris.worker``.
    """

    from cloris.worker import build_session_orchestrator_argv

    return build_session_orchestrator_argv(
        brief_path=brief_path,
        state_dir=state_dir,
        resume=resume,
        python_executable=python_executable,
    )


def _linkedin_save_destination_blocker(
    brief_path: str,
) -> SaveDestinationBlocker | None:
    """Block LinkedIn launches when the brief lacks a project_id.

    Phase F Slice F2. Reads the V2 ``source_config.linkedin.project_id``
    field, falling back to the flat ``linkedin_project_id`` for briefs
    not yet migrated. Returns ``None`` (no blocker) when the project id
    is configured. The blocker's remediation is recruiter-actionable —
    points them at ``BriefDetail`` to fill in the destination.
    """

    from shared.brief_v2_schema import linkedin_project_id_from_brief
    from shared.storage import read_json

    try:
        raw = read_json(brief_path)
    except Exception:
        # If the brief can't be read at all, the launch will fail
        # downstream with a clearer error; don't double-report here.
        return None

    if not isinstance(raw, dict):
        return None

    project_id = linkedin_project_id_from_brief(raw)
    if project_id:
        return None

    return SaveDestinationBlocker(
        kind="config",
        message=(
            "Cloris doesn't yet know which LinkedIn project to save into "
            "for this brief."
        ),
        remediation=(
            "Paste your Recruiter project URL — either inline here, or from "
            "the brief's \"Where Cloris saves\" section."
        ),
    )


def _github_state_key(brief_path: str) -> str:
    from shared.output_paths import github_state_key

    return github_state_key(brief_path=brief_path)


def _github_state_dir(brief_path: str) -> Path:
    from shared.output_paths import resolve_github_state_dir

    return resolve_github_state_dir(brief_path=brief_path)


def _github_orchestrator_argv(
    brief_path: str,
    state_dir: str,
    *,
    resume: bool,
    python_executable: str = sys.executable,
) -> list[str]:
    """GitHub execvp argv.

    The GitHub orchestrator's CLI accepts ``--brief``, ``--state-dir``,
    and an optional ``--resume`` flag (per
    ``github/session_orchestrator.py:main``). It does not accept
    ``--input-mode`` — Cloris v0 is concurrent-only and the GitHub
    orchestrator's session model already runs concurrently. The
    ``cloris.worker`` wrapper writes the sidecar with
    ``input_mode="concurrent"`` regardless of source so the on-wire
    contract stays uniform.
    """

    argv: list[str] = [
        python_executable,
        "-m",
        "github.session_orchestrator",
        "--brief",
        brief_path,
        "--state-dir",
        state_dir,
    ]
    if resume:
        argv.append("--resume")
    return argv


def _researcher_state_key(brief_path: str) -> str:
    from shared.output_paths import researcher_state_key

    return researcher_state_key(brief_path=brief_path)


def _researcher_state_dir(brief_path: str) -> Path:
    from shared.output_paths import resolve_researcher_state_dir

    return resolve_researcher_state_dir(brief_path=brief_path)


def _researcher_orchestrator_argv(
    brief_path: str,
    state_dir: str,
    *,
    resume: bool,
    python_executable: str = sys.executable,
) -> list[str]:
    """Researcher execvp argv.

    Mirrors the GitHub argv shape; the researcher orchestrator's CLI
    accepts ``--brief``, ``--state-dir``, and an optional ``--resume``
    flag (matched by `researcher.session_orchestrator.main`). Slice 1
    ships the stub; Slice 6 wires the real pipeline.
    """

    argv: list[str] = [
        python_executable,
        "-m",
        "researcher.session_orchestrator",
        "--brief",
        brief_path,
        "--state-dir",
        state_dir,
    ]
    if resume:
        argv.append("--resume")
    return argv


def _researcher_save_destination_blocker(
    brief_path: str,
) -> SaveDestinationBlocker | None:
    """Researcher saves always land in the workspace (no per-brief destination).

    Per Researcher Module Spec Opinion 4: researchers without LinkedIn
    profiles can't be saved to LinkedIn Recruiter; every saved researcher
    is a `candidates` row with SAVE-class `terminal_decision`. Workspace
    is always available, so no readiness blocker fires.
    """

    return None


def _designer_state_key(brief_path: str) -> str:
    from shared.output_paths import designer_state_key

    return designer_state_key(brief_path=brief_path)


def _designer_state_dir(brief_path: str) -> Path:
    from shared.output_paths import resolve_designer_state_dir

    return resolve_designer_state_dir(brief_path=brief_path)


def _designer_orchestrator_argv(
    brief_path: str,
    state_dir: str,
    *,
    resume: bool,
    python_executable: str = sys.executable,
) -> list[str]:
    """Designer execvp argv.

    Mirrors the GitHub argv shape; the designer orchestrator's CLI
    accepts ``--brief``, ``--state-dir``, and an optional ``--resume``
    flag (matched by `designer.session_orchestrator.main`). Slice 1
    ships the stub with placeholder evaluator; Slices 2-5 wire the
    real source adapters and vision pipeline.
    """

    argv: list[str] = [
        python_executable,
        "-m",
        "designer.session_orchestrator",
        "--brief",
        brief_path,
        "--state-dir",
        state_dir,
    ]
    if resume:
        argv.append("--resume")
    return argv


def _designer_save_destination_blocker(
    brief_path: str,
) -> SaveDestinationBlocker | None:
    """Designer saves always land in the workspace (no per-brief destination).

    Mirrors the Researcher posture: the workspace is the implicit save
    destination — Designer-evaluated candidates are `candidates` rows
    with SAVE-class `terminal_decision` and `surface_type:
    "hitl_visual_review"` in `terminal_payload_json`. No per-brief
    destination configuration to gate on.
    """

    return None


def _exec_search_state_key(brief_path: str) -> str:
    from shared.output_paths import exec_search_state_key

    return exec_search_state_key(brief_path=brief_path)


def _exec_search_state_dir(brief_path: str) -> Path:
    from shared.output_paths import resolve_exec_search_state_dir

    return resolve_exec_search_state_dir(brief_path=brief_path)


def _exec_search_orchestrator_argv(
    brief_path: str,
    state_dir: str,
    *,
    resume: bool,
    python_executable: str = sys.executable,
) -> list[str]:
    """Executive Search execvp argv.

    Mirrors the GitHub argv shape; the exec_search orchestrator's CLI
    accepts ``--brief``, ``--state-dir``, and an optional ``--resume``
    flag (matched by `exec_search.session_orchestrator.main`). Slice 1
    ships the stub (`main()` exits 0); Slices 2-10 wire the real
    pipeline (LinkedIn evaluation pipeline extension + off-LinkedIn
    signals + Cloris-native shortlist destination).
    """

    argv: list[str] = [
        python_executable,
        "-m",
        "exec_search.session_orchestrator",
        "--brief",
        brief_path,
        "--state-dir",
        state_dir,
    ]
    if resume:
        argv.append("--resume")
    return argv


# Module-scope source registry. Adding a new source is a single-line
# append below. Keep keys lowercase to match the URL path convention.
#
# Phase F Slice F2: ``save_destination_blocker_fn`` is added per source.
# GitHub returns ``None`` (no per-brief destination concept today —
# saves are JSONL on disk in the run folder, addressable without
# recruiter input). LinkedIn requires a project_id; the blocker fires
# when the brief lacks ``source_config.linkedin.project_id`` (fallback
# to the flat ``linkedin_project_id`` is handled by the helper).
# Researcher returns ``None`` (workspace-only saves per Spec Opinion 4).
# Designer returns ``None`` (workspace-only saves; the visual judgment
# payload lands in `terminal_payload_json` for the HITL visual review
# surface).
# Executive Search (Slice 1): no blocker yet — the Cloris-native
# shortlist destination ships in Slice 7 (which depends on
# multi-module-foundation Slices 6-7). Until then, exec_search uses
# the default no-op blocker so launches don't fail readiness.
LAUNCHERS: dict[str, LauncherEntry] = {
    "linkedin": LauncherEntry(
        state_key_fn=_linkedin_state_key,
        state_dir_fn=_linkedin_state_dir,
        orchestrator_argv_fn=_linkedin_orchestrator_argv,
        save_destination_blocker_fn=_linkedin_save_destination_blocker,
    ),
    "github": LauncherEntry(
        state_key_fn=_github_state_key,
        state_dir_fn=_github_state_dir,
        orchestrator_argv_fn=_github_orchestrator_argv,
    ),
    "researcher": LauncherEntry(
        state_key_fn=_researcher_state_key,
        state_dir_fn=_researcher_state_dir,
        orchestrator_argv_fn=_researcher_orchestrator_argv,
        save_destination_blocker_fn=_researcher_save_destination_blocker,
    ),
    "designer": LauncherEntry(
        state_key_fn=_designer_state_key,
        state_dir_fn=_designer_state_dir,
        orchestrator_argv_fn=_designer_orchestrator_argv,
        save_destination_blocker_fn=_designer_save_destination_blocker,
    ),
    "exec_search": LauncherEntry(
        state_key_fn=_exec_search_state_key,
        state_dir_fn=_exec_search_state_dir,
        orchestrator_argv_fn=_exec_search_orchestrator_argv,
    ),
}


def known_sources() -> tuple[str, ...]:
    """Return the registered source names, in stable ascending order.

    Used by the API layer to compose a 422 ``allowed`` list when an
    unknown source is requested, and by F5's module picker / F7's
    home aggregator to enumerate sources without re-declaring the set.
    """

    return tuple(sorted(LAUNCHERS.keys()))


def get_launcher(source: str) -> LauncherEntry:
    """Return the registered :class:`LauncherEntry` for ``source``.

    Raises :class:`KeyError` for unknown sources; callers that need to
    surface a structured 422 should check ``source in LAUNCHERS`` first
    and use :func:`known_sources` for the allow-list payload.
    """

    return LAUNCHERS[source]
