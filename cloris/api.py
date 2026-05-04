"""Cloris HTTP surface.

Slice 1 endpoints (route declarations byte-identical here; only the body
``GET /`` returns has changed in Slice 5 — see below):

- ``GET /healthz`` — readiness probe used by :func:`cloris.app.run_app` and by
  external smoke checks. Stable JSON contract: ``status``, ``slice``,
  ``version``. The slice tag stays ``"v0-shell-slice-1"`` because this is a
  readiness probe, not a slice-version banner.
- ``GET /`` — returns the built Cloris UI's ``index.html``. See the Slice 5
  paragraph below.

Slice 2 endpoint (route body byte-identical, payload bumped to slice-4 by the
aggregator):

- ``GET /api/status`` — read-only aggregation across discovered
  ``output/state/<source>/*`` directories. Slice 4 enriches the payload with
  worker-sidecar provenance and a ``resumable`` hint, and bumps the slice
  tag in :class:`cloris.models.StatusResponse` to ``"v0-shell-slice-4"``.

Slice 3 endpoint (route body byte-identical):

- ``POST /api/launch/linkedin`` — spawn a detached
  ``python -m cloris.worker ...`` subprocess that writes ``worker.json``
  and ``execvp``s into ``linkedin.session_orchestrator``. LinkedIn-only,
  concurrent-only, fresh-only. The :class:`cloris.models.LaunchResponse`
  slice tag stays ``"v0-shell-slice-3"`` — the launch contract did not
  change in Slice 4.

Slice 4 endpoints:

- ``POST /api/stop/{source}/{state_key}`` — resolve the state dir via
  :func:`cloris.control_plane.enumerate_state_dirs` (path-traversal-safe
  lookup; raw URL segments cannot escape the discovered set), read
  ``worker.json``, and:

  - Missing sidecar ⇒ HTTP 200, ``worker_state="missing"``.
  - Stale sidecar (PID malformed / non-int / dead) ⇒ HTTP 200,
    ``worker_state="stale"``. The stale sidecar is **not** deleted; the
    next launch overwrites it via the existing Slice-3 stale-overwrite
    policy.
  - Alive PID ⇒ HTTP 202, ``worker_state="stopping"``. Send
    ``signal.SIGTERM`` exactly once and return immediately. **No** wait
    for exit. **No** SIGKILL escalation.
  - Unknown ``(source, state_key)`` ⇒ HTTP 404 with
    ``error="state_dir_not_found"``.

- ``POST /api/resume/linkedin`` — same request body as launch
  (:class:`LaunchLinkedInRequest`, ``brief_path``-only with
  ``extra="forbid"``). Spawns a detached worker with ``--mode resume``,
  which threads ``--resume`` into the orchestrator argv. Returns
  :class:`cloris.models.ResumeResponse` (HTTP 201) with ``slice``
  ``"v0-shell-slice-4"`` and ``mode="resume"``. The launch's stale-sidecar
  overwrite policy and ``WorkerAlreadyRunningError`` / ``BriefPathNotFoundError``
  shapes are reused identically.

Pause is still out of scope per ``docs/cloris-control-plane-spec.md`` §7.

Slice 5 surface change (no API contract changes):

- ``GET /`` now returns the built Svelte SPA from
  ``cloris/frontend/dist/index.html``. The Slice 1 inline placeholder is
  gone; the entry HTML is emitted by Vite at build time.
- :func:`mount_static` mounts ``cloris/frontend/dist/assets/`` at
  ``/assets/`` via :class:`fastapi.staticfiles.StaticFiles`. Vite emits
  hashed JS/CSS filenames there (e.g. ``index-DJcGuPNc.js``), plus the
  bundled OFL-licensed fonts under ``/assets/fonts/``. The mount is added
  by :func:`cloris.app.create_app` calling :func:`mount_static` after the
  router is included; existing API routes are unaffected. No slice tag in
  any payload bumps for Slice 5.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal, Optional

log = logging.getLogger("cloris.api")

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from cloris import __version__
from cloris import intake_sessions
from cloris.control_plane import (
    aggregate_briefs,
    aggregate_candidate_detail,
    aggregate_run_report,
    aggregate_status,
    aggregate_workspace,
    enumerate_state_dirs,
    resolve_legacy_workspace,
    state_dirs_for_brief_id,
)
from shared.runtime_state import read_models as _read_models
from cloris.launch_lock import (
    DEFAULT_LAUNCH_LOCK_TIMEOUT_S,
    DEFAULT_SIDECAR_WAIT_TIMEOUT_S,
    LaunchLockTimeoutError,
    state_dir_launch_lock,
    wait_for_sidecar,
)
from cloris.models import (
    ActiveRunSummary,
    BriefDetailResponse,
    BriefEditRequest,
    BriefInfo,
    BriefsListResponse,
    BriefVersionEntry,
    BriefVersionsResponse,
    CandidateDetailResponse,
    CandidateJudgmentAccuracyPatchRequest,
    CandidateNoteRequest,
    CandidateStatusPatchRequest,
    AcknowledgmentRequest,
    ChromeStatusResponse,
    CredentialUpsertRequest,
    OnboardingStatusResponse,
    IdentityCandidateLink,
    IdentityDecisionRequest,
    IdentityPendingDecision,
    IdentityPendingResponse,
    IdentityPerson,
    IdentityUnlinkRequest,
    IntakeSession,
    IntakeSessionCompleteResponse,
    IntakeSessionCreateRequest,
    IntakeSessionDeleteResponse,
    IntakeSessionListResponse,
    IntakeSessionPatchRequest,
    IntakeSessionResponse,
    LaunchReadinessBlocker,
    LaunchReadinessResponse,
    LaunchRequest,
    LaunchResponse,
    LegacyResolveResponse,
    MarketDetailResponse,
    MarketLane,
    MarketsListResponse,
    MarketSummary,
    MarketTalentPool,
    MarketThesis,
    MonitorIndexResponse,
    ReconciledRun,
    ReconcileResponse,
    ReflectionActiveResponse,
    ReflectionCommitRequest,
    ReflectionCommitResponse,
    ReflectionCreateRequest,
    ReflectionDiscardRequest,
    ReflectionResponse,
    ReflectionSession,
    ReflectionStartResearchRequest,
    ReflectionSteeringRequest,
    ResumeResponse,
    RunReportResponse,
    RunTelemetryResponse,
    SettingsBriefSaveSummary,
    SettingsCredential,
    SettingsGovernorLimit,
    SettingsResponse,
    StatusResponse,
    StopResponse,
    TelemetryAttemptRow,
    TelemetryEventRow,
    ToolEntry,
    ToolJobStatusWire,
    ToolRunAsyncWire,
    ToolRunRequest,
    ToolRunSyncWire,
    ToolsIndexResponse,
    WorkspaceResponse,
)
from cloris import reconciler
from cloris.worker import (
    BriefPathNotFoundError,
    WorkerAlreadyRunningError,
    is_pid_alive,
    read_sidecar,
)
from shared.runtime_state import read_models
from shared.runtime_state.store import RuntimeStateStore


class NoPendingWorkError(Exception):
    """Raised by ``_spawn_linkedin_worker(mode="resume")`` when the brief's
    state dir has no queued or in-progress work to resume.

    Phase 1.3 fix for the lying-success bug: previously ``POST /api/resume/linkedin``
    spawned a worker even when there was nothing to resume. The worker
    exited cleanly seconds later, but the API had already returned 201
    and the UI rendered "Resumed. PID 12345..." — a fake success.

    Now the route layer maps this to HTTP 422 so the UI can render an
    accurate "nothing to resume" message instead.
    """

    def __init__(self, state_dir: str) -> None:
        super().__init__(f"no pending work to resume in {state_dir}")
        self.state_dir = state_dir


router = APIRouter()

_DIST_DIR = Path(__file__).parent / "frontend" / "dist"
_PROJECT_ROOT = Path(__file__).parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"


def mount_static(app) -> None:
    """Mount the built Cloris UI's hashed asset bundle at ``/assets/``.

    Slice 5 ships a Vite-built Svelte SPA; Vite emits hashed JS/CSS
    filenames into ``cloris/frontend/dist/assets/``. Mounting StaticFiles
    there lets the browser fetch the bundled chunks (and bundled fonts)
    without any per-asset FastAPI route. Existing API routes are
    unaffected.
    """

    app.mount(
        "/assets",
        StaticFiles(directory=_DIST_DIR / "assets"),
        name="cloris-assets",
    )


def _send_sigterm(pid: int) -> None:
    """Module-level seam for the single SIGTERM dispatch in :func:`stop_worker`.

    Tests monkeypatch this symbol to a recorder so the SIGTERM dispatch
    can be observed without disturbing the unrelated ``os.kill(pid, 0)``
    liveness probe inside :func:`cloris.worker.is_pid_alive`. Production
    behavior is a single ``os.kill(pid, signal.SIGTERM)`` and nothing
    else.
    """

    os.kill(pid, signal.SIGTERM)


class StateDirNotFoundError(Exception):
    """Raised when ``stop_worker`` cannot resolve the requested state dir.

    The route maps this to HTTP 404 with
    ``{"error": "state_dir_not_found", "source": ..., "state_key": ...}``.
    Lives in :mod:`cloris.api` rather than :mod:`cloris.worker` because it
    is purely a routing-layer error: the worker module has no notion of
    URL-borne ``(source, state_key)`` lookups.
    """

    def __init__(self, source: str, state_key: str) -> None:
        super().__init__(
            f"state dir not found (source={source}, state_key={state_key})"
        )
        self.source = source
        self.state_key = state_key


class UnknownSourceError(Exception):
    """Raised by ``_spawn_worker_for_source`` when the source path
    parameter doesn't appear in :data:`cloris.launchers.LAUNCHERS`.

    The route maps this to HTTP 422 with
    ``{"error": "unknown_source", "source": ..., "allowed": [...]}``.
    Phase F Slice F1.
    """

    def __init__(self, source: str, allowed: tuple[str, ...]) -> None:
        super().__init__(
            f"unknown launch source '{source}'; allowed={list(allowed)}"
        )
        self.source = source
        self.allowed = allowed


class LaunchNotReadyError(Exception):
    """Raised when ``POST /api/launch/{source}`` is called without
    ``force=true`` and the launch-readiness probe (Phase D Slice D9)
    surfaces blockers. The route maps this to HTTP 422 with
    ``{"error": "launch_not_ready", "source": ..., "blockers": [...]}``.
    """

    def __init__(self, source: str, blockers: list) -> None:
        super().__init__(
            f"launch not ready for source={source}; "
            f"blockers={[b.kind for b in blockers]}"
        )
        self.source = source
        self.blockers = blockers


class BriefIdNotFoundError(Exception):
    """Raised when ``POST /api/launch/{source}`` receives a brief_id
    that doesn't resolve to any brief in the catalog.

    Distinct from :class:`BriefPathNotFoundError` (which fires on a
    legacy ``brief_path`` request payload) because the brief_id flow
    cannot meaningfully report the missing path. Route maps to HTTP 404.
    """

    def __init__(self, brief_id: str) -> None:
        super().__init__(f"no brief in catalog hashes to id '{brief_id}'")
        self.brief_id = brief_id


class LaunchLinkedInRequest(BaseModel):
    """Request body for ``POST /api/launch/linkedin`` and
    ``POST /api/resume/linkedin``.

    Slice 4 reuses this exact model for resume because the user-approved
    contract is "same request body shape as launch" — a single
    ``brief_path`` string. ``extra="forbid"`` rejects any unknown field
    (e.g. ``input_mode``, ``mode``) at the request boundary, which is how
    ``away`` and stray fields are rejected without ever reaching the
    helper.
    """

    model_config = ConfigDict(extra="forbid")
    brief_path: str


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Readiness probe used by the run_app lifecycle and tests."""

    return {
        "status": "ok",
        "slice": "v0-shell-slice-1",
        "version": __version__,
    }


@router.get("/api/chrome-status", response_model=ChromeStatusResponse)
def api_chrome_status() -> ChromeStatusResponse:
    """Phase 0 ``chrome-launcher`` slice. Read-only CDP / Chrome-profile
    health snapshot for the welcome surface's polling loop and the
    Settings "Cloris's hands" panel.

    Pure read; never spawns or kills. The welcome surface polls this
    every ~1s while the recipient is on first launch so it can
    transition from "Opening Chrome..." to "Sign into LinkedIn" the
    moment :func:`cloris.chrome_launcher.is_healthy` returns true.
    """

    from cloris.chrome_launcher import status

    snapshot = status()
    return ChromeStatusResponse(
        state=snapshot.state,  # type: ignore[arg-type]
        cdp_url=snapshot.cdp_url,
        profile_dir=snapshot.profile_dir,
        message=snapshot.message,
    )


@router.get("/api/onboarding/status", response_model=OnboardingStatusResponse)
def api_onboarding_status() -> OnboardingStatusResponse:
    """Phase 0 ``apikey-ui`` slice. Welcome-gate read endpoint.

    The frontend calls this on app mount; ``welcome_complete=False``
    means render Welcome.svelte, ``welcome_complete=True`` means
    fall through to the route table. Pure read — never writes.
    """

    from cloris.onboarding import onboarding_status

    s = onboarding_status()
    return OnboardingStatusResponse(
        welcome_complete=s.welcome_complete,
        anthropic_present=s.anthropic_present,
        acknowledged=s.acknowledged,
        acknowledged_at=s.acknowledged_at,
        env_path=s.env_path,
        acknowledgment_path=s.acknowledgment_path,
    )


@router.post("/api/onboarding/credential", response_model=OnboardingStatusResponse)
def api_onboarding_credential(
    req: CredentialUpsertRequest,
) -> OnboardingStatusResponse:
    """Phase 0 ``apikey-ui`` slice. Insert-or-update a credential in
    the user-data ``.env``.

    Atomicity + chmod 600 are owned by
    :func:`cloris.onboarding.upsert_credential`; this route is the
    HTTP entry, an unknown key surfaces as HTTP 422 with the allowed
    set so the welcome surface can render a precise diagnostic.

    Returns the post-write :class:`OnboardingStatusResponse` so the
    welcome surface doesn't need a follow-up GET to learn whether the
    write succeeded.
    """

    from cloris.onboarding import (
        UnknownCredentialKeyError,
        onboarding_status,
        upsert_credential,
    )

    try:
        upsert_credential(req.key, req.value)
    except UnknownCredentialKeyError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unknown_credential_key",
                "key": exc.key,
                "allowed": list(exc.allowed),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "empty_credential_value", "key": req.key, "message": str(exc)},
        ) from exc

    s = onboarding_status()
    return OnboardingStatusResponse(
        welcome_complete=s.welcome_complete,
        anthropic_present=s.anthropic_present,
        acknowledged=s.acknowledged,
        acknowledged_at=s.acknowledged_at,
        env_path=s.env_path,
        acknowledgment_path=s.acknowledgment_path,
    )


@router.post("/api/onboarding/acknowledge", response_model=OnboardingStatusResponse)
def api_onboarding_acknowledge(
    req: AcknowledgmentRequest,
) -> OnboardingStatusResponse:
    """Phase 0 ``apikey-ui`` / ``disclosure`` slice. Record the
    recipient's acknowledgment of Cloris's LinkedIn-Recruiter
    operational surface.

    Idempotent: re-acknowledging overwrites the timestamp + version
    with the current values. ``acknowledged=False`` in the request
    is rejected with HTTP 422 — the only way to reach this endpoint
    is the explicit checkbox-checked + Continue flow on the welcome
    surface.
    """

    from cloris.onboarding import onboarding_status, record_acknowledgment

    if not req.acknowledged:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "acknowledgment_required",
                "message": (
                    "Cloris cannot start until you check the acknowledgment "
                    "box and click Continue."
                ),
            },
        )

    record_acknowledgment(cloris_version=__version__)

    s = onboarding_status()
    return OnboardingStatusResponse(
        welcome_complete=s.welcome_complete,
        anthropic_present=s.anthropic_present,
        acknowledged=s.acknowledged,
        acknowledged_at=s.acknowledged_at,
        env_path=s.env_path,
        acknowledgment_path=s.acknowledgment_path,
    )


@router.post("/api/chrome-relaunch", response_model=ChromeStatusResponse)
def api_chrome_relaunch() -> ChromeStatusResponse:
    """Phase 0 ``chrome-launcher`` slice. Recycle the Cloris Chrome
    instance — only the dedicated profile, never the recipient's
    personal Chrome.

    Wired into the welcome surface's "Re-open Chrome" affordance and
    the Settings "Re-open Chrome" control. Returns the post-action
    :class:`ChromeStatusResponse` so the caller doesn't need to poll
    immediately to see whether the relaunch succeeded.
    """

    from cloris.chrome_launcher import ensure_running

    snapshot = ensure_running(force=True)
    return ChromeStatusResponse(
        state=snapshot.state,  # type: ignore[arg-type]
        cdp_url=snapshot.cdp_url,
        profile_dir=snapshot.profile_dir,
        message=snapshot.message,
    )


@router.get("/")
def index() -> FileResponse:
    """Serve the built Cloris UI's ``index.html`` from
    ``cloris/frontend/dist/``.

    Slice 5 replaced the Slice-1 inline placeholder with a Vite-built
    Svelte SPA; the entry HTML lives in
    ``cloris/frontend/dist/index.html`` and references hashed bundles
    under ``/assets/`` (mounted by :func:`mount_static`)."""

    return FileResponse(_DIST_DIR / "index.html", media_type="text/html")


@router.get("/api/status")
def api_status() -> StatusResponse:
    """Aggregate read-only status across LinkedIn and GitHub state dirs."""

    return aggregate_status()


def _scan_authored_briefs(config_dir: Path) -> list[BriefInfo]:
    """Walk ``config/**/brief-*.json`` and return one :class:`BriefInfo` per
    real authored brief.

    Excludes:
      - ``*-draft.json`` — the AGENTS.md guard pattern marks these as
        in-flight scratch; surfacing them in the picker would let a
        recruiter accidentally launch against an incomplete brief.
      - ``*.bak-*`` files — automated backups, never user intent.
      - Anything that doesn't parse as a JSON object.
      - Anything outside ``config_dir`` (defensive).

    Returned list is sorted most-recently-modified first so the picker
    reads as "what you're working on this week, then this month, then
    older" without manual ordering.
    """
    import json
    from datetime import datetime, timezone

    out: list[BriefInfo] = []
    if not config_dir.exists() or not config_dir.is_dir():
        return out
    # Phase D Slice D2: post-migration canonical filename in nested dirs
    # is `brief.json` (no dash); existing nested briefs use the legacy
    # `brief-*.json` pattern. Walk both, dedupe by absolute path so a
    # `brief-fde.json` next to a `brief.json` doesn't double-count.
    seen: set[Path] = set()

    def _candidates() -> Iterator[Path]:
        for p in config_dir.rglob("brief-*.json"):
            if p.is_file():
                yield p
        for p in config_dir.rglob("brief.json"):
            if p.is_file():
                yield p

    for path in _candidates():
        resolved_path = path.resolve()
        if resolved_path in seen:
            continue
        seen.add(resolved_path)
        name = path.name
        if name.endswith("-draft.json"):
            continue
        if ".bak-" in name:
            continue
        try:
            raw = path.read_text()
            data = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        linkedin_project_id = data.get("linkedin_project_id")
        if linkedin_project_id is not None and not isinstance(linkedin_project_id, str):
            linkedin_project_id = str(linkedin_project_id)
        try:
            modified_at = datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc
            ).isoformat()
        except OSError:
            modified_at = ""
        # Phase F Slice F5: target_modules drives LaunchForm's module
        # picker. Legacy briefs missing the key surface as None and the
        # frontend defaults to ["linkedin"] (matches BriefDetail.svelte
        # destinationModules behavior).
        raw_target_modules = data.get("target_modules")
        target_modules: list[str] | None = None
        if isinstance(raw_target_modules, list):
            target_modules = [str(m) for m in raw_target_modules if isinstance(m, str)]
        out.append(
            BriefInfo(
                path=str(path.relative_to(_PROJECT_ROOT)),
                role_title=data.get("role_title") if isinstance(data.get("role_title"), str) else None,
                linkedin_project=data.get("linkedin_project") if isinstance(data.get("linkedin_project"), str) else None,
                linkedin_project_id=linkedin_project_id,
                modified_at=modified_at,
                target_modules=target_modules,
            )
        )
    out.sort(key=lambda b: b.modified_at, reverse=True)
    return out


@router.get("/api/briefs", response_model=BriefsListResponse)
def api_briefs(decorate_runs: bool = True) -> BriefsListResponse:
    """List authored briefs from ``config/`` with optional run metadata.

    Two callers:
    - **Phase 4 BriefPicker** (LaunchForm): the picker only needs
      role_title + path. Pass ``?decorate_runs=false`` to skip the
      per-brief runtime-state lookup.
    - **Phase D Slice D1 — Brief library at ``#/briefs``**: needs the
      decorated shape (``brief_id`` + ``last_run_*`` + ``total_*``)
      so each card can render last-run status, save count, etc.

    Default is ``decorate_runs=True`` because (a) the library is the
    new primary surface, (b) the per-brief lookup is fast — one
    sqlite read per brief — and (c) callers that don't read the
    decorated fields just ignore them.
    """

    return BriefsListResponse(
        briefs=aggregate_briefs(decorate_runs=decorate_runs)
    )


# ---------------------------------------------------------------------------
# Phase D Slice D2 — Brief detail / edit at /api/brief/{brief_id}
# ---------------------------------------------------------------------------
#
# brief_id resolution. The recruiter URL `#/brief/<brief_id>` is keyed by
# the same hash that runs.brief_id carries — i.e. linkedin_state_key()
# computed from the brief catalog file. To resolve a brief_id back to a
# config-file path we walk the catalog and recompute the hash per brief
# until we hit a match. Cheaper than maintaining a reverse-index and
# avoids a stale-index failure mode if the catalog changes underneath.


def _resolve_brief_by_id(brief_id: str) -> tuple[Path, bool] | None:
    """Find the catalog file for a brief_id. Returns ``(path, was_flat)``
    or ``None`` if no brief in the catalog hashes to this id.

    ``was_flat`` is True iff the brief lives at ``config/<name>.json``
    (still in the legacy flat layout). False iff it's already nested at
    ``config/<dir>/brief-*.json``. The PUT handler uses this to decide
    whether to migrate the brief to the nested layout on first edit
    (Fork C).
    """

    from shared.output_paths import linkedin_state_key

    raw_briefs = _scan_authored_briefs(_CONFIG_DIR)
    for brief in raw_briefs:
        # `brief.path` is project-relative (`config/...`); reconstruct
        # the absolute path for both the hash computation and disk IO.
        abs_path = _PROJECT_ROOT / brief.path
        try:
            computed = linkedin_state_key(brief_path=str(abs_path))
        except Exception:
            continue
        if computed == brief_id:
            # Flat iff the parent dir IS the canonical config dir. Nested
            # iff the parent is some sub-directory under config/.
            was_flat = abs_path.parent.resolve() == _CONFIG_DIR.resolve()
            return abs_path, was_flat
    return None


@router.get("/api/brief/{brief_id}", response_model=BriefDetailResponse)
def api_brief_detail(brief_id: str) -> BriefDetailResponse:
    """Read a brief's V2 + legacy partition for editing. Phase D Slice D2.

    Walks the catalog, resolves brief_id → path, parses the JSON, runs
    :func:`shared.brief_v2_schema.merge_legacy_brief` to split V2 from
    legacy/unknown. Returns the full partition over the wire so PUT
    can roundtrip without backend disk re-read (architectural-fit
    critique catch from D2 planning).

    Errors:
      * 404 ``brief_not_found`` — no brief in the catalog hashes to
        this brief_id.
    """

    import json
    from datetime import datetime, timezone

    from shared.brief_v2_schema import BriefSchemaError, merge_legacy_brief

    resolved = _resolve_brief_by_id(brief_id)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "brief_not_found", "brief_id": brief_id},
        )
    abs_path, was_flat = resolved

    try:
        raw = json.loads(abs_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "brief_unreadable", "reason": str(exc)},
        ) from exc

    try:
        merged = merge_legacy_brief(raw)
    except BriefSchemaError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "brief_unparseable", "reason": str(exc)},
        ) from exc

    try:
        modified_at = datetime.fromtimestamp(
            abs_path.stat().st_mtime, timezone.utc
        ).isoformat()
    except OSError:
        modified_at = ""

    # Count existing versions in the sibling dir if it exists. For flat
    # briefs the versions dir won't exist yet (count = 0).
    versions_dir = abs_path.parent / "versions"
    version_count = 0
    if versions_dir.is_dir():
        version_count = sum(
            1 for p in versions_dir.glob("*.json") if p.is_file()
        )

    return BriefDetailResponse(
        brief_id=brief_id,
        path=str(abs_path.relative_to(_PROJECT_ROOT)),
        role_title=raw.get("role_title") if isinstance(raw.get("role_title"), str) else None,
        v2_data=merged.v2_data,
        preserved_legacy=merged.preserved_legacy,
        deprecated_keys=list(merged.deprecated_keys),
        unknown_keys=list(merged.unknown_keys),
        last_modified=modified_at,
        version_count=version_count,
        was_flat=was_flat,
    )


@router.put("/api/brief/{brief_id}", response_model=BriefDetailResponse)
def api_brief_edit(brief_id: str, request: BriefEditRequest) -> BriefDetailResponse:
    """Write a new version of a brief. Phase D Slice D2.

    Algorithm:
    1. Resolve brief_id → catalog path.
    2. Validate the V2 portion via :func:`validate_v2_brief`.
    3. Rebuild the full payload: ``v2_data ∪ preserved_legacy``.
    4. If the brief is currently flat (``was_flat=True``), migrate to
       nested layout: move ``config/<name>.json`` →
       ``config/<name>/brief.json``. Logged for observability.
    5. Atomic write: tempfile next to canonical → ``os.replace`` →
       canonical now carries the new payload. THEN copy the new
       canonical into ``versions/<timestamp>.json``. Order matters:
       the canonical must NEVER be stale relative to versions/.
       (Architectural-fit critique catch.)
    6. Return the freshly-read brief (round-trips through GET handler).

    Errors:
      * 404 ``brief_not_found``
      * 422 ``invalid_v2_brief`` — V2 portion fails validation; carries
        ``missing_keys`` and ``invalid_keys`` from the validator.
      * 500 ``brief_write_failed`` — atomic-write infrastructure
        problem (rare; surfaces the exception text).
    """

    import shutil

    from shared.brief_v2_schema import (
        BriefSchemaError,
        validate_v2_brief,
    )
    from shared.brief_writer import write_brief_atomic

    resolved = _resolve_brief_by_id(brief_id)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "brief_not_found", "brief_id": brief_id},
        )
    abs_path, was_flat = resolved

    # Step 2 — V2 validation.
    try:
        validate_v2_brief(request.v2_data)
    except BriefSchemaError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_v2_brief",
                "message": str(exc),
                "missing_keys": list(exc.missing_keys),
                "invalid_keys": list(exc.invalid_keys),
            },
        ) from exc

    # Step 3 — rebuild full payload. The frontend has already decided
    # which legacy keys to keep (preserved_legacy) and which to drop
    # (absent). The backend just writes the union; no second-guessing.
    full_payload = dict(request.preserved_legacy)
    full_payload.update(request.v2_data)  # V2 wins on key collision.

    # Step 4 — flat → nested migration. The canonical post-migration
    # path is `config/<stem>/brief.json` where <stem> is the original
    # flat filename minus extension. This keeps the brief's identity
    # stable (linkedin_state_key reads brief content not path; verified
    # in D2 substrate audit).
    if was_flat:
        stem = abs_path.stem
        nested_dir = abs_path.parent / stem
        nested_dir.mkdir(parents=True, exist_ok=True)
        nested_path = nested_dir / "brief.json"
        # Move first; we'll write fresh content via atomic rename below.
        shutil.move(str(abs_path), str(nested_path))
        log.info(
            "Flat brief promoted to nested layout: %s → %s "
            "(brief_id=%s; Phase D Slice D2)",
            abs_path,
            nested_path,
            brief_id,
        )
        abs_path = nested_path

    # Step 5 — atomic canonical-first write + versions/ snapshot. The
    # writer is shared with D3's intake-complete endpoint so the
    # contract stays single-sourced (D3 architectural-fit critique
    # risk #3).
    try:
        write_brief_atomic(abs_path=abs_path, payload=full_payload)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "brief_write_failed", "reason": str(exc)},
        ) from exc

    # Step 6 — return the freshly-read brief by routing through GET.
    return api_brief_detail(brief_id)


@router.get(
    "/api/brief/{brief_id}/versions",
    response_model=BriefVersionsResponse,
)
def api_brief_versions(brief_id: str) -> BriefVersionsResponse:
    """List the snapshot history under ``versions/`` for a brief.

    Phase D Slice D5 — read-only audit trail. Each PUT writes a
    timestamped snapshot via :func:`api_brief_edit`; this endpoint
    returns them ordered most-recent-first. The full diff view is
    deferred to a follow-up; this slice ships the listing so the
    recruiter can see the brief has a history.

    404 ``brief_not_found`` if the brief_id doesn't resolve to any
    catalog file. An empty ``versions: []`` is a valid response for a
    brief that has been authored but never edited via the API.
    """

    resolved = _resolve_brief_by_id(brief_id)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "brief_not_found", "brief_id": brief_id},
        )
    abs_path, _ = resolved

    versions_dir = abs_path.parent / "versions"
    versions: list[BriefVersionEntry] = []
    if versions_dir.is_dir():
        for snapshot in sorted(versions_dir.glob("*.json"), reverse=True):
            if not snapshot.is_file():
                continue
            stem = snapshot.stem
            # Filename format: ISO-8601 with ":" → "-" so the filename
            # is filesystem-safe. Decode by replacing the time-segment
            # dashes back to colons. Best-effort; if decode fails we
            # surface the raw stem as ``created_at`` rather than dropping
            # the row.
            created_at = stem
            if "T" in stem:
                date_part, _, time_part = stem.partition("T")
                # The time part may carry timezone offset like +00-00;
                # split on the offset sign to handle both pieces.
                # Replace the time-only dashes (positions 0,1 → :,:),
                # leave the offset dashes alone if any.
                # Simpler: convert all dashes after the FIRST T into ':'
                # except the last (offset minute boundary).
                created_at = (
                    date_part
                    + "T"
                    + time_part.replace("-", ":", 2)
                )
            try:
                size = snapshot.stat().st_size
            except OSError:
                size = 0
            versions.append(
                BriefVersionEntry(
                    version_id=stem,
                    created_at=created_at,
                    size_bytes=size,
                )
            )

    return BriefVersionsResponse(brief_id=brief_id, versions=versions)


# Phase E Slice E1: market viewer endpoints. The on-disk
# `MarketIntelArtifact` is rich (60 lanes, full evidence index,
# section-generation metadata); the wire shapes are trimmed to the
# recruiter-facing fields the viewer renders. Detail responses build
# from `market_intelligence.engine.load_artifact()`; the catalog list
# from `list_market_records()`.


@router.get("/api/markets", response_model=MarketsListResponse)
def api_markets_list() -> MarketsListResponse:
    """Catalog of every market with a parseable artifact on disk.

    Sorted most-recently-updated first by `freshness.artifact_updated_at`.
    Empty when no artifacts exist (no error — the route layer renders
    a Cloris-voice empty state).
    """

    from market_intelligence.engine import list_market_records

    records = list_market_records()
    return MarketsListResponse(
        markets=[
            MarketSummary(
                market_key=r.market_key,
                role_title=r.role_title,
                role_level=r.role_level,
                geography=r.geography,
                last_updated_at=r.last_updated_at,
                run_count=r.run_count,
                saved_count=r.saved_count,
                aggregate_save_rate=r.aggregate_save_rate,
            )
            for r in records
        ]
    )


@router.get(
    "/api/market/{market_key}",
    response_model=MarketDetailResponse,
)
def api_market_detail(market_key: str) -> MarketDetailResponse:
    """Per-market detail payload for the `#/market/<key>` viewer.

    404 ``market_not_found`` when no parseable artifact exists at the
    canonical path. The wire shape flattens the artifact to the
    recruiter-facing fields and drops the cloris-internal machinery
    (evidence_index, section_generation_metadata, etc.).
    """

    from market_intelligence.engine import load_artifact

    artifact = load_artifact(market_key)
    if artifact is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "market_not_found", "market_key": market_key},
        )

    identity = artifact.market_identity
    freshness = artifact.freshness or {}
    aggregate = artifact.aggregate_metrics or {}

    def _opt_float(value: object) -> float | None:
        try:
            return float(value) if value is not None else None  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _str_field(payload: dict, key: str) -> str:
        value = payload.get(key)
        return str(value) if isinstance(value, str) else ""

    lanes: list[MarketLane] = []
    for lane in artifact.lane_intelligence or []:
        if not isinstance(lane, dict):
            continue
        metrics = lane.get("metrics") or {}
        if not isinstance(metrics, dict):
            metrics = {}
        candidates_seen = int(metrics.get("candidates_seen") or 0)
        saves = int(metrics.get("saves") or 0)
        # R6: omit zero-evidence lanes from the detail wire so the
        # frontend never sees empty rows it would have to suppress.
        if candidates_seen == 0 and saves == 0:
            continue
        lanes.append(
            MarketLane(
                lane_key=str(lane.get("lane_key") or "").strip(),
                domain_lane=str(lane.get("domain_lane") or "").strip(),
                novelty_bucket=str(lane.get("novelty_bucket") or "").strip(),
                status=str(lane.get("status") or "").strip(),
                candidates_seen=candidates_seen,
                saves=saves,
                save_rate=_opt_float(metrics.get("save_rate")),
                why_it_works=(
                    str(lane.get("why_it_works")).strip()
                    if isinstance(lane.get("why_it_works"), str)
                    else None
                ),
                recommended_action=(
                    str(lane.get("recommended_action")).strip()
                    if isinstance(lane.get("recommended_action"), str)
                    else None
                ),
            )
        )

    talent_pools: list[MarketTalentPool] = []
    for pool in artifact.talent_pool_intelligence or []:
        if not isinstance(pool, dict):
            continue
        talent_pools.append(
            MarketTalentPool(
                pool_key=str(pool.get("pool_key") or "").strip(),
                label=str(pool.get("label") or "").strip(),
                signal_strength=str(pool.get("signal_strength") or "").strip(),
                status=str(pool.get("status") or "").strip(),
                evidence_summary=(
                    str(pool.get("evidence_summary")).strip()
                    if isinstance(pool.get("evidence_summary"), str)
                    else None
                ),
            )
        )

    thesis_data = artifact.market_thesis or {}
    thesis = MarketThesis(
        summary=_str_field(thesis_data, "summary"),
        supply_assessment=_str_field(thesis_data, "supply_assessment"),
        competition_assessment=_str_field(thesis_data, "competition_assessment"),
        external_context=_str_field(thesis_data, "external_context"),
    )

    # Engine emits brief_recommendations as a list of dicts on the
    # artifact. Surface it verbatim — the frontend's computeBriefDiff()
    # walks it as a fourth diff source. Filter out malformed entries
    # so the wire stays well-typed.
    brief_recommendations: list[dict] = [
        rec
        for rec in (artifact.brief_recommendations or [])
        if isinstance(rec, dict)
    ]

    return MarketDetailResponse(
        market_key=identity.market_key,
        role_title=identity.role_title,
        role_level=identity.role_level,
        geography=identity.geography,
        last_updated_at=str(freshness.get("artifact_updated_at") or "").strip(),
        run_count=int(aggregate.get("run_count") or 0),
        saved_count=int(aggregate.get("saved_count") or 0),
        rejected_count=int(aggregate.get("rejected_count") or 0),
        aggregate_save_rate=_opt_float(aggregate.get("save_rate")),
        facial_yes_rate=_opt_float(aggregate.get("facial_yes_rate")),
        lanes=lanes,
        talent_pools=talent_pools,
        market_thesis=thesis,
        brief_recommendations=brief_recommendations,
    )


@router.post("/api/reconcile", response_model=ReconcileResponse)
def api_reconcile() -> ReconcileResponse:
    """Reconcile runs marked ``status='running'`` whose workers have died.

    The aggregator (``GET /api/status``) is read-only and faithfully
    reports any contradiction it finds — a run can stay marked ``running``
    forever after the orchestrator process is killed by Mac sleep, an
    OOM, ``kill -9``, or a host reboot. This endpoint walks every state
    dir, classifies the worker as ``missing_sidecar`` / ``bad_sidecar`` /
    ``pid_dead``, and finalizes those runs as ``status='abandoned'`` with
    ``stop_reason='worker_missing'`` so the UI shows a "Lost track" pill
    instead of a lying "Working" one.

    The endpoint is intentionally explicit — the frontend calls it on
    app mount and on a slow timer — so test suites that monkeypatch
    ``aggregate_status`` are not perturbed by side effects on read.

    Idempotent: a re-run with no zombies returns ``applied=0`` and an
    empty mutation list.
    """

    applied, mutations = reconciler.reconcile_and_apply()
    return ReconcileResponse(
        applied=applied,
        mutations=[
            ReconciledRun(
                source=m.source,  # type: ignore[arg-type]
                state_key=m.state_key,
                run_id=m.run_id,
                new_status=m.new_status,
                stop_reason=m.stop_reason,
                reason=m.reason,
            )
            for m in mutations
        ],
    )


@router.get(
    "/api/run/{source}/{state_key}/{run_id}",
    response_model=RunReportResponse,
)
def api_run_report(
    source: str, state_key: str, run_id: int
) -> RunReportResponse:
    """Per-run report (Phase B).

    Aggregates run lifecycle, work-unit progress, attempt-health, and
    candidate decisions for a single ``run_id`` in the discovered
    ``(source, state_key)`` state dir.

    Errors:
      * 404 ``state_dir_not_found`` — no enumerated state dir matches
        ``(source, state_key)``.
      * 404 ``run_not_found`` — state dir resolves but the canonical
        SQLite has no row with this ``run_id`` (or the DB is missing /
        unreadable; we don't distinguish at the wire).
    """

    state_dir = _resolve_state_dir(source, state_key)
    if state_dir is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "state_dir_not_found",
                "source": source,
                "state_key": state_key,
            },
        )
    report = aggregate_run_report(
        state_dir, source=source, state_key=state_key, run_id=run_id
    )
    if report is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "run_not_found",
                "source": source,
                "state_key": state_key,
                "run_id": run_id,
            },
        )
    return report


# ---------------------------------------------------------------------------
# Phase G Slice G3: Live Monitor endpoints. Operational depth for runs in
# motion. Polled by Monitor.svelte at 1s while the worker is alive, 5s
# otherwise. The /telemetry endpoint surfaces raw candidate_attempts +
# events for the operator view — recruiters who want forensics drop into
# sqlite directly; this is a window, not a full audit trail.
# ---------------------------------------------------------------------------


@router.get(
    "/api/monitor/index",
    response_model=MonitorIndexResponse,
)
def api_monitor_index() -> MonitorIndexResponse:
    """List runs with a currently-alive worker process.

    Derived from ``aggregate_status``: filter to entries where
    ``worker_alive=True``. Cheap; no new query work over /api/status.
    """

    status = aggregate_status()
    active: list[ActiveRunSummary] = []
    for entry in status.entries:
        if entry.worker_alive is not True:
            continue
        latest = entry.latest_run
        active.append(
            ActiveRunSummary(
                source=entry.source,
                state_key=entry.state_key,
                run_id=latest.id if latest is not None else None,
                run_status=latest.status if latest is not None else None,
                stop_reason=latest.stop_reason if latest is not None else None,
                started_at=latest.started_at if latest is not None else None,
                ended_at=latest.ended_at if latest is not None else None,
                brief_id=entry.brief_id_from_run,
                brief_role_title=entry.brief_role_title,
                worker_pid=entry.worker_pid,
            )
        )
    # Most-recently-started first within the active set.
    active.sort(key=lambda r: r.started_at or "", reverse=True)
    return MonitorIndexResponse(slice="v0-monitor-index-1", active_runs=active)


_TELEMETRY_ATTEMPTS_LIMIT = 50
_TELEMETRY_EVENTS_LIMIT = 30


@router.get(
    "/api/run/{source}/{state_key}/{run_id}/telemetry",
    response_model=RunTelemetryResponse,
)
def api_run_telemetry(
    source: str, state_key: str, run_id: int
) -> RunTelemetryResponse:
    """Per-run operational telemetry: recent attempts + events.

    Bounded windowed view: 50 most-recent attempts, 30 most-recent events.
    Recruiters who need the full history use sqlite directly; this is a
    live monitor window, not a forensics surface.

    Errors:
      * 404 ``state_dir_not_found`` — unknown ``(source, state_key)``.
    """

    state_dir = _resolve_state_dir(source, state_key)
    if state_dir is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "state_dir_not_found",
                "source": source,
                "state_key": state_key,
            },
        )
    db_path = state_dir / "runtime_state.sqlite3"
    if not db_path.exists():
        return RunTelemetryResponse(
            slice="v0-run-telemetry-1",
            source=source,  # type: ignore[arg-type]
            state_key=state_key,
            run_id=run_id,
            attempts=[],
            events=[],
            last_event_at=None,
            attempts_total=0,
            events_total=0,
        )

    # Read-only path: route through ``read_models.run_telemetry`` instead
    # of instantiating ``RuntimeStateStore``. The store's __init__ runs
    # unconditional DDL plus an ``INSERT OR REPLACE INTO meta`` on every
    # call (shared/runtime_state/store.py:87) — using it here would make
    # this polling endpoint a writer against active runtime state. The
    # control-plane docstring (cloris/control_plane.py:10-15) explicitly
    # warns against this pattern; ``read_models.run_telemetry`` opens
    # the DB via the URI ``mode=ro`` pattern so the kernel refuses any
    # accidental write.
    from shared.runtime_state.read_models import run_telemetry

    telemetry = run_telemetry(
        db_path,
        run_id=run_id,
        attempts_limit=_TELEMETRY_ATTEMPTS_LIMIT,
        events_limit=_TELEMETRY_EVENTS_LIMIT,
    )

    attempts = [
        TelemetryAttemptRow(
            id=a.id,
            candidate_id=a.candidate_id,
            work_unit_id=a.work_unit_id,
            stage=a.stage,
            attempt_number=a.attempt_number,
            status=a.status,
            failure_kind=a.failure_kind,
            failure_reason=a.failure_reason,
            started_at=a.started_at,
            ended_at=a.ended_at,
        )
        for a in telemetry.attempts
    ]
    events = [
        TelemetryEventRow(
            id=e.id,
            event_type=e.event_type,
            candidate_id=e.candidate_id,
            attempt_id=e.attempt_id,
            payload_summary=_truncate_payload_for_telemetry(e.payload_json),
            created_at=e.created_at,
        )
        for e in telemetry.events
    ]
    return RunTelemetryResponse(
        slice="v0-run-telemetry-1",
        source=source,  # type: ignore[arg-type]
        state_key=state_key,
        run_id=run_id,
        attempts=attempts,
        events=events,
        last_event_at=telemetry.last_event_at,
        attempts_total=telemetry.attempts_total,
        events_total=telemetry.events_total,
    )


def _truncate_payload_for_telemetry(raw: object, *, max_chars: int = 240) -> str | None:
    """Compact stringification of an event payload for the Monitor row.

    The full payload_json may be megabytes (LLM transcripts, stale page
    snapshots). Telemetry rows just need a quick "what kind of payload"
    glance. We return the first ``max_chars`` of the raw string to keep
    the wire payload bounded.
    """

    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


@router.get(
    "/api/workspace/{brief_id}",
    response_model=WorkspaceResponse,
)
def api_workspace(brief_id: str) -> WorkspaceResponse:
    """Per-brief candidate workspace (Phase C-bis 0.1, brief-first).

    Aggregates every SAVE-class candidate for ``brief_id`` across every
    state_dir whose latest run carries that brief_id. Today that's
    typically one source; Phase F multi-module operation will fan out
    across LinkedIn + GitHub + Researcher in the same response.

    Errors:
      * 404 ``workspace_not_found`` — no state_dir's latest run carries
        this brief_id (or no runs exist at all).
    """

    workspace = aggregate_workspace(brief_id=brief_id)
    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "workspace_not_found",
                "brief_id": brief_id,
            },
        )
    return workspace


@router.get(
    "/api/candidate/{brief_id}/{candidate_id}",
    response_model=CandidateDetailResponse,
)
def api_candidate_detail(
    brief_id: str, candidate_id: int
) -> CandidateDetailResponse:
    """Per-candidate detail (Phase C-bis 0.1, brief-first).

    The aggregator finds which state_dir under this brief_id holds the
    candidate row and returns the detail. ``source`` and ``source_run``
    in the response carry the metadata the page needs (source eyebrow,
    run-report back-link) without polluting the URL contract.

    Errors:
      * 404 ``candidate_not_found`` — no state_dir under this brief_id
        contains a candidate with the given id (or the candidate's
        ``brief_id``/``source`` doesn't match the resolved state_dir's,
        which is a cross-source guard that prevents leaking foreign rows).
    """

    detail = aggregate_candidate_detail(
        brief_id=brief_id, candidate_id=candidate_id
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "candidate_not_found",
                "brief_id": brief_id,
                "candidate_id": candidate_id,
            },
        )
    return detail


# Phase C, slice C3: validated user_status values. NULL clears the override
# (Cloris's terminal_decision is the displayed status). Non-null must be in
# this set; any other value gets a 422.
_ALLOWED_USER_STATUSES: frozenset[str] = frozenset({
    "shortlist",
    "parked",
    "contacted",
    "hidden",
})


def _find_state_dir_for_candidate(
    brief_id: str, candidate_id: int
) -> Path | None:
    """Find the state_dir holding a (brief_id, candidate_id) pair, for
    mutation endpoints that need to instantiate :class:`RuntimeStateStore`
    on the right SQLite file. Returns ``None`` if no state_dir matches.
    """

    for source, state_dir in state_dirs_for_brief_id(brief_id):
        db_path = state_dir / "runtime_state.sqlite3"
        record = _read_models.candidate_by_id(db_path, candidate_id=candidate_id)
        if record is None:
            continue
        if record.brief_id == brief_id and record.source == source:
            return state_dir
    return None


@router.post(
    "/api/candidate/{brief_id}/{candidate_id}/note",
    response_model=CandidateDetailResponse,
)
def api_candidate_append_note(
    brief_id: str,
    candidate_id: int,
    request: CandidateNoteRequest,
) -> CandidateDetailResponse:
    """Append a recruiter-authored note to a candidate (brief-first).

    Notes are append-only; each note is timestamped at write time and
    rendered in reverse-chrono on the candidate-detail page. The route
    returns the full updated :class:`CandidateDetailResponse` so the
    client can re-render without a follow-up GET.

    Errors:
      * 404 ``candidate_not_found`` — no state_dir under this brief_id
        contains a candidate with the given id.
      * 422 ``empty_note_body`` — body is empty / whitespace-only.
    """

    body = request.body.strip()
    if not body:
        raise HTTPException(
            status_code=422,
            detail={"error": "empty_note_body"},
        )
    state_dir = _find_state_dir_for_candidate(brief_id, candidate_id)
    if state_dir is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "candidate_not_found",
                "brief_id": brief_id,
                "candidate_id": candidate_id,
            },
        )
    db_path = state_dir / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    try:
        store.append_candidate_note(candidate_id, body)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "candidate_not_found",
                "brief_id": brief_id,
                "candidate_id": candidate_id,
            },
        )
    detail = aggregate_candidate_detail(
        brief_id=brief_id, candidate_id=candidate_id
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "candidate_not_found"},
        )
    return detail


@router.patch(
    "/api/candidate/{brief_id}/{candidate_id}",
    response_model=CandidateDetailResponse,
)
def api_candidate_update_status(
    brief_id: str,
    candidate_id: int,
    request: CandidateStatusPatchRequest,
) -> CandidateDetailResponse:
    """Set or clear the recruiter-overridden status on a candidate (brief-first).

    Errors:
      * 404 ``candidate_not_found`` — no state_dir under this brief_id
        contains a candidate with the given id.
      * 422 ``invalid_user_status`` — the requested status isn't in the
        allowed set (``shortlist`` / ``parked`` / ``contacted`` /
        ``hidden`` / ``null``).
    """

    user_status = request.user_status
    if user_status is not None and user_status not in _ALLOWED_USER_STATUSES:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_user_status",
                "allowed": sorted(_ALLOWED_USER_STATUSES),
            },
        )
    state_dir = _find_state_dir_for_candidate(brief_id, candidate_id)
    if state_dir is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "candidate_not_found",
                "brief_id": brief_id,
                "candidate_id": candidate_id,
            },
        )
    db_path = state_dir / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    try:
        store.set_candidate_user_status(candidate_id, user_status)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "candidate_not_found",
                "brief_id": brief_id,
                "candidate_id": candidate_id,
            },
        )
    detail = aggregate_candidate_detail(
        brief_id=brief_id, candidate_id=candidate_id
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "candidate_not_found"},
        )
    return detail


# Phase C-bis 0.5: closed-loop feedback substrate. Allowed values for
# the recruiter's calibration signal — kept in sync with
# RuntimeStateStore.set_candidate_judgment_accuracy. NULL clears.
_ALLOWED_JUDGMENT_ACCURACIES: frozenset[str] = frozenset({
    "useful",
    "wrong",
    "off_rubric",
    "overstated_depth",
    "understated_depth",
})


@router.patch(
    "/api/candidate/{brief_id}/{candidate_id}/judgment-accuracy",
    response_model=CandidateDetailResponse,
)
def api_candidate_update_judgment_accuracy(
    brief_id: str,
    candidate_id: int,
    request: CandidateJudgmentAccuracyPatchRequest,
) -> CandidateDetailResponse:
    """Set or clear the recruiter's judgment-accuracy signal (brief-first).

    Phase C-bis Slice 0.5. Distinct from the user_status PATCH —
    judgment_accuracy captures whether Cloris's *judgment* was useful
    or off, not what pipeline action the recruiter is taking. Both
    columns coexist on the candidate row.

    Errors:
      * 404 ``candidate_not_found`` — no state_dir under this brief_id
        contains a candidate with the given id.
      * 422 ``invalid_judgment_accuracy`` — the requested value isn't
        in the allowed set.
    """

    judgment_accuracy = request.judgment_accuracy
    if (
        judgment_accuracy is not None
        and judgment_accuracy not in _ALLOWED_JUDGMENT_ACCURACIES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_judgment_accuracy",
                "allowed": sorted(_ALLOWED_JUDGMENT_ACCURACIES),
            },
        )
    state_dir = _find_state_dir_for_candidate(brief_id, candidate_id)
    if state_dir is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "candidate_not_found",
                "brief_id": brief_id,
                "candidate_id": candidate_id,
            },
        )
    db_path = state_dir / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    try:
        store.set_candidate_judgment_accuracy(candidate_id, judgment_accuracy)
    except ValueError as exc:
        # The store raises ValueError for two distinct cases — unknown
        # candidate_id and unknown accuracy value. The accuracy values
        # are pre-validated above, so a ValueError here is the
        # candidate-not-found case. Mirror the user_status pattern.
        message = str(exc)
        if "invalid judgment_accuracy" in message:
            # Defense-in-depth: store-side validation also fired. Surface
            # as 422 like the API-layer check.
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_judgment_accuracy",
                    "allowed": sorted(_ALLOWED_JUDGMENT_ACCURACIES),
                },
            )
        raise HTTPException(
            status_code=404,
            detail={
                "error": "candidate_not_found",
                "brief_id": brief_id,
                "candidate_id": candidate_id,
            },
        )
    detail = aggregate_candidate_detail(
        brief_id=brief_id, candidate_id=candidate_id
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "candidate_not_found"},
        )
    return detail


# ---------------------------------------------------------------------------
# Legacy URL resolvers (Phase C-bis 0.1).
#
# Old bookmarks pointing at the source-siloed URLs hit these endpoints to
# learn the brief_id. The frontend then rewrites the hash to the new
# brief-first URL. Cheap reads; no mutations. Both endpoints return the
# same shape (just `brief_id`); the candidate variant exists separately
# only because the legacy URL also carries a `candidate_id` segment that
# the frontend already has — so it doesn't need to be echoed back.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase G Slice G2: identity reconciliation endpoints. Recruiter-driven merge
# / keep-separate decisions over the F3 backend's pending_merge_decisions.
#
# Routes are brief-scoped because the identity service is brief-scoped: a
# pending decision is meaningful only in the context of a specific brief's
# saves. The UI lives at #/workspace/<brief_id>/identity.
# ---------------------------------------------------------------------------


def _identity_person_to_wire(
    person: "object",  # PersonWithEvidence — string-quoted to defer import
) -> IdentityPerson:
    """Convert a service-layer PersonWithEvidence to the wire IdentityPerson.

    Routes the link_kind enum through ``describe_merge_signal`` so the
    frontend never sees raw enums. Each candidate link gets its own
    editorial ``describe`` line.
    """

    from shared.identity_resolution_service import describe_merge_signal

    sources_wire: list[IdentityCandidateLink] = []
    for link in person.sources:
        sources_wire.append(
            IdentityCandidateLink(
                source=link.source,
                state_key=link.state_key,
                candidate_id=link.candidate_id,
                link_kind=link.link_kind,
                recruiter_locked=link.recruiter_locked,
                describe=describe_merge_signal(link.link_kind, link.match_signal),
            )
        )
    return IdentityPerson(
        person_id=person.person_id,
        canonical_name=person.canonical_name,
        canonical_handle=person.canonical_handle,
        sources=sources_wire,
    )


@router.get(
    "/api/brief/{brief_id}/identity/pending",
    response_model=IdentityPendingResponse,
)
def api_identity_pending(brief_id: str) -> IdentityPendingResponse:
    """List unresolved merge decisions for a brief, with person evidence
    and Cloris-voice signal_summary prose.

    Side effect: re-runs ``resolve_persons_for_brief`` on read so the
    pending list reflects any candidates added since the last launch.
    Idempotent — already-linked candidates and recruiter-locked rows
    are untouched.
    """

    from shared.identity_resolution_service import (
        brief_persons_with_evidence,
        pending_decisions_for_brief,
        resolve_persons_for_brief,
    )

    resolve_persons_for_brief(brief_id)
    persons = brief_persons_with_evidence(brief_id)
    decisions = pending_decisions_for_brief(brief_id)
    decisions_wire = [
        IdentityPendingDecision(
            decision_id=d.decision_id,
            person_a=_identity_person_to_wire(d.person_a),
            person_b=_identity_person_to_wire(d.person_b),
            signal_summary=d.signal_summary,
            created_at=d.created_at,
        )
        for d in decisions
    ]
    return IdentityPendingResponse(
        slice="v0-identity-pending-1",
        brief_id=brief_id,
        persons_total=len(persons),
        decisions=decisions_wire,
    )


@router.post(
    "/api/brief/{brief_id}/identity/decision",
    status_code=204,
)
def api_identity_decision(brief_id: str, req: IdentityDecisionRequest) -> Response:
    """Resolve one pending merge decision.

    422 cases:
      - decision_id doesn't exist for this brief
      - decision was already resolved (terminal)
      - choice is not in {"merge","keep_separate"} (caught by Pydantic)
    """

    from shared.identity_resolution_service import record_decision_by_id

    try:
        record_decision_by_id(
            brief_id=brief_id,
            decision_id=req.decision_id,
            decision=req.choice,
        )
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "identity_decision_not_found",
                "brief_id": brief_id,
                "decision_id": req.decision_id,
            },
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "identity_decision_already_resolved",
                "brief_id": brief_id,
                "decision_id": req.decision_id,
                "message": str(exc),
            },
        )
    return Response(status_code=204)


@router.post(
    "/api/brief/{brief_id}/identity/unlink",
    status_code=204,
)
def api_identity_unlink(brief_id: str, req: IdentityUnlinkRequest) -> Response:
    """Split a candidate off into its own person row.

    Locks the new link so auto-resolution doesn't merge it back.
    Idempotent: if the candidate is unknown, the call is a no-op rather
    than a 404 — the recruiter's intent is "make sure this is its own
    person," and the no-record case satisfies that.
    """

    from shared.identity_resolution_service import record_recruiter_unlink

    record_recruiter_unlink(
        source=req.source,
        state_key=req.state_key,
        candidate_id=req.candidate_id,
    )
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Phase G Slice G4: Tools index + execution.
# ---------------------------------------------------------------------------


def _tool_entry_for_wire(tool) -> ToolEntry:
    """Project a registry ToolDefinition into the wire ToolEntry shape.

    Includes a hand-crafted ``schema_fields`` summary so the frontend can
    render a form without re-introspecting Pydantic at runtime.
    """

    schema_fields: list[dict] = []
    if tool.args_schema is not None:
        model_schema = tool.args_schema.model_json_schema()
        properties = model_schema.get("properties", {}) or {}
        required = set(model_schema.get("required", []) or [])
        for name, prop in properties.items():
            field_type = prop.get("type") or prop.get("enum") or "string"
            schema_fields.append(
                {
                    "name": name,
                    "type": field_type if isinstance(field_type, str) else "enum",
                    "required": name in required,
                    "default": prop.get("default"),
                    "description": prop.get("description") or "",
                }
            )
    return ToolEntry(
        tool_id=tool.tool_id,
        tier=tool.tier,
        label=tool.label,
        pitch=tool.pitch,
        cli_command=tool.cli_command,
        execution_model=tool.execution_model,
        schema_fields=schema_fields,
    )


# ---------------------------------------------------------------------------
# Phase G Slice G5: Settings transparency surface. Read-only — credentials
# as ✓/✗ booleans, governor limits as constants with editorial explainers,
# brief save destinations summarized from V2 source_config.
# ---------------------------------------------------------------------------


_CREDENTIAL_LABELS: list[tuple[str, str, str]] = [
    (
        "anthropic_api_key",
        "Anthropic (Claude)",
        "Cloris uses Claude for the heavy reading and writing — judgment, brief drafting, market reads. Without it, runs can't think.",
    ),
    (
        "openai_api_key",
        "OpenAI",
        "OpenAI is a fallback for some judgment paths. Optional but recommended.",
    ),
    (
        "google_api_key",
        "Google (Gemini)",
        "Used for the design-consult workflow. Optional unless you're running the audit ensemble.",
    ),
    (
        "perplexity_api_key",
        "Perplexity",
        "Used for the external-evidence workflow during candidate research.",
    ),
    (
        "linkedin_cdp",
        "LinkedIn (Chrome session)",
        "Cloris connects to your authenticated Chrome session over CDP. Without it, LinkedIn runs fail at launch.",
    ),
]


def _credential_present(key: str) -> bool:
    """Return True iff the credential is set + non-empty.

    NEVER returns the value itself; the wire shape is boolean-only by
    design (R-rule for sensitive operational state).
    """

    import shared.config as cfg

    def _val_set(attr: str) -> bool:
        raw = getattr(cfg, attr, "")
        return isinstance(raw, str) and raw.strip() != ""

    if key == "anthropic_api_key":
        return _val_set("ANTHROPIC_API_KEY")
    if key == "openai_api_key":
        return _val_set("OPENAI_API_KEY")
    if key == "google_api_key":
        return _val_set("GOOGLE_API_KEY")
    if key == "perplexity_api_key":
        return _val_set("PERPLEXITY_API_KEY")
    if key == "linkedin_cdp":
        # CDP_URL is always set (default value), so we report presence
        # rather than reachability. Reachability is the job of D9's
        # launch-readiness probe — Settings is a transparency snapshot,
        # not an operational diagnosis.
        return _val_set("CDP_URL")
    return False


@router.get("/api/settings", response_model=SettingsResponse)
def api_settings() -> SettingsResponse:
    """Read-only operational snapshot. Credentials boolean-only; governor
    limits read as constants with editorial explainers; save destinations
    summarized from V2 ``source_config`` per brief."""

    credentials = [
        SettingsCredential(
            key=key,
            label=label,
            present=_credential_present(key),
            pitch=pitch,
        )
        for key, label, pitch in _CREDENTIAL_LABELS
    ]

    # Save destinations: walk the brief catalog and summarize per-brief
    # source_config. Reuses the brief loader from D1.
    #
    # No outer try/except: api_briefs() failing is a system-level fault
    # that should surface as 500, not silently degrade save_destinations
    # to []. The previous outer broad-except hid a NameError on a typo'd
    # function call (api_list_briefs vs api_briefs) for an unknown
    # period — every /api/settings response carried an empty
    # save_destinations until the typo was caught by code review. The
    # inner try/except below covers the only real degradation case
    # (per-brief loader/schema failure for one bad brief).
    #
    # Briefs whose ``brief_id`` is None are deliberately skipped:
    # ``aggregate_briefs`` returns brief_id=None when ``linkedin_state_key``
    # raises (malformed schema, unparseable JSON, etc.). Those briefs are
    # broken at a deeper level than save-destination configuration, and
    # surfacing them on the settings page with a missing id would mislead
    # the recruiter into thinking the brief is ready to save against.
    save_destinations: list[SettingsBriefSaveSummary] = []
    briefs_response = api_briefs()
    for b in briefs_response.briefs:
        if b.brief_id is None:
            continue
        target_modules = list(b.target_modules or [])
        linkedin_project_id = None
        try:
            from shared.brief_loader import load_brief

            data = load_brief(b.path)
            from shared.brief_v2_schema import linkedin_project_id_from_brief

            linkedin_project_id = linkedin_project_id_from_brief(data)
        except Exception:
            linkedin_project_id = None
        save_destinations.append(
            SettingsBriefSaveSummary(
                brief_id=b.brief_id,
                role_title=b.role_title,
                target_modules=target_modules,
                linkedin_project_id=linkedin_project_id,
            )
        )

    # Governor: read constants directly. Per shared/governor.py:
    # "do not make these configurable."
    import shared.governor as gov

    governor = [
        SettingsGovernorLimit(
            name="MAX_PROFILE_OPENS_PER_SESSION",
            label="Profiles per session",
            value=int(gov.MAX_PROFILE_OPENS_PER_SESSION),
            explainer="Tuned for safe LinkedIn cadence. Cloris won't open more than this in a single sitting.",
        ),
        SettingsGovernorLimit(
            name="MAX_PROFILE_OPENS_PER_24H",
            label="Profiles per 24h",
            value=int(gov.MAX_PROFILE_OPENS_PER_24H),
            explainer="Daily ceiling across all sessions. Hits this and Cloris stops until the rolling window clears.",
        ),
        SettingsGovernorLimit(
            name="MAX_SESSIONS_PER_DAY",
            label="Sessions per day",
            value=int(gov.MAX_SESSIONS_PER_DAY),
            explainer="Hard cap on session starts. Combined with the 24h profile ceiling, this keeps cadence below LinkedIn's eyebrow.",
        ),
        SettingsGovernorLimit(
            name="MAX_SESSION_DURATION_SECONDS",
            label="Max session duration",
            value=f"≈{int(gov.MAX_SESSION_DURATION_SECONDS / 60)} min (randomized 3.5–4.5h)",
            explainer="Wall-clock cap with jitter. Randomization is part of the safety profile; Cloris doesn't expose the exact value.",
        ),
    ]

    import shared.config as cfg

    return SettingsResponse(
        slice="v0-settings-1",
        credentials=credentials,
        save_destinations=save_destinations,
        governor=governor,
        cdp_url=str(getattr(cfg, "CDP_URL", "") or ""),
    )


@router.get("/api/tools", response_model=ToolsIndexResponse)
def api_tools_index() -> ToolsIndexResponse:
    """Return the catalog of tools — Tier A/B with UI runners + Tier B/C
    documentation entries (CLI only)."""

    from cloris.tools_registry import list_tools

    return ToolsIndexResponse(
        slice="v0-tools-index-1",
        tools=[_tool_entry_for_wire(t) for t in list_tools()],
    )


@router.post("/api/tools/{tool_id}")
async def api_tools_run(tool_id: str, req: ToolRunRequest):
    """Execute a tool. Sync tools return ``ToolRunSyncWire`` immediately;
    async tools return ``ToolRunAsyncWire`` with a job_id; cli_only tools
    return 422 (the catalog already shows them).
    """

    from cloris.tools_registry import find_tool
    from cloris.tools_runtime import execute_async, execute_sync

    tool = find_tool(tool_id)
    if tool is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "tool_not_found", "tool_id": tool_id},
        )
    if tool.execution_model == "cli_only":
        raise HTTPException(
            status_code=422,
            detail={
                "error": "tool_cli_only",
                "tool_id": tool_id,
                "cli_command": tool.cli_command,
            },
        )
    if tool.args_schema is None:
        raise HTTPException(
            status_code=500,
            detail={"error": "tool_misconfigured", "tool_id": tool_id},
        )
    try:
        args_model = tool.args_schema.model_validate(req.args)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "tool_args_invalid",
                "tool_id": tool_id,
                "message": str(exc),
            },
        )

    if tool.execution_model == "sync":
        result = await execute_sync(tool, args_model)
        return ToolRunSyncWire(
            slice="v0-tool-sync-1",
            tool_id=result.tool_id,
            exit_code=result.exit_code,
            stdout_tail=result.stdout_tail,
            stderr_tail=result.stderr_tail,
        )
    # async
    result = await execute_async(tool, args_model)
    return ToolRunAsyncWire(
        slice="v0-tool-async-1",
        tool_id=result.tool_id,
        job_id=result.job_id,
    )


@router.get(
    "/api/tools/jobs/{job_id}",
    response_model=ToolJobStatusWire,
)
async def api_tools_job_status(job_id: str) -> ToolJobStatusWire:
    """Poll for the status of an async tool job."""

    from cloris.tools_runtime import get_job_status

    status = await get_job_status(job_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "tool_job_not_found", "job_id": job_id},
        )
    return ToolJobStatusWire(
        slice="v0-tool-job-1",
        job_id=status.job_id,
        tool_id=status.tool_id,
        status=status.status,
        started_at=status.started_at,
        finished_at=status.finished_at,
        exit_code=status.exit_code,
        stdout_tail=status.stdout_tail,
        stderr_tail=status.stderr_tail,
        error_message=status.error_message,
    )


@router.get(
    "/api/resolve-legacy/workspace/{source}/{state_key}",
    response_model=LegacyResolveResponse,
)
def api_resolve_legacy_workspace(
    source: str, state_key: str
) -> LegacyResolveResponse:
    """Resolve a legacy workspace URL to its current brief_id."""

    brief_id = resolve_legacy_workspace(source, state_key)
    if brief_id is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "legacy_workspace_not_resolvable",
                "source": source,
                "state_key": state_key,
            },
        )
    return LegacyResolveResponse(brief_id=brief_id)


@router.get(
    "/api/resolve-legacy/candidate/{source}/{state_key}/{candidate_id}",
    response_model=LegacyResolveResponse,
)
def api_resolve_legacy_candidate(
    source: str, state_key: str, candidate_id: int
) -> LegacyResolveResponse:
    """Resolve a legacy candidate URL to its current brief_id.

    Same shape as the workspace resolver — the candidate_id stays
    unchanged across the rewrite, so the frontend just needs the
    brief_id to construct ``#/candidate/<brief_id>/<candidate_id>``.
    The ``candidate_id`` path segment is consumed for symmetry with the
    legacy URL and to enable a future variant that re-keys the id under
    a cross-module identity layer.
    """

    brief_id = resolve_legacy_workspace(source, state_key)
    if brief_id is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "legacy_candidate_not_resolvable",
                "source": source,
                "state_key": state_key,
                "candidate_id": candidate_id,
            },
        )
    return LegacyResolveResponse(brief_id=brief_id)


@dataclass(frozen=True)
class _SpawnResult:
    """Outcome of :func:`_spawn_linkedin_worker`.

    Decoupled from the response models because the route layer is what knows
    which response type to box this into (LaunchResponse vs ResumeResponse).
    Keeping the helper response-shape-agnostic means future modes can be added
    without forcing a new response type into the helper signature.
    """

    pid: int
    state_dir: Path
    worker_json_path: Path


def _frozen_worker_binary_path() -> Path | None:
    """Return the path to the frozen ``cloris-worker`` sibling binary,
    or ``None`` when not running inside a frozen .app.

    Phase 0 ``worker-binary`` slice. PyInstaller bundles the .app as
    ``Cloris.app`` with the main entry binary at
    ``Cloris.app/Contents/MacOS/Cloris``. The worker ships as a
    sibling binary at ``Cloris.app/Contents/MacOS/cloris-worker``
    (built from a separate PyInstaller spec that pulls in every
    orchestrator + dependency the worker needs at runtime).

    The api process can't ``python -m cloris.worker`` from a frozen
    .app because ``sys.executable`` is the main entry binary, not a
    Python interpreter — invoking it with ``-m`` would re-launch the
    UI. The sibling-binary path keeps the spawn pattern intact while
    using the right binary for each role.
    """

    if not getattr(sys, "frozen", False):
        return None
    candidate = Path(sys.executable).parent / "cloris-worker"
    if candidate.exists():
        return candidate
    log.warning(
        "cloris.api: frozen app detected but sibling cloris-worker not "
        "found at %s; falling back to python -m invocation. The launch "
        "will likely fail because the .app has no python interpreter.",
        candidate,
    )
    return None


def _build_worker_argv(
    *,
    source: str = "linkedin",
    brief_path: str,
    brief_id: str,
    state_dir: Path,
    mode: Literal["fresh", "resume"],
) -> list[str]:
    """Compose argv for the detached worker.

    Two shapes:

    - Frozen .app (Phase 0 ``worker-binary`` slice): invoke the
      sibling ``cloris-worker`` binary directly. ``sys.executable`` is
      the UI binary, not a python interpreter.
    - Dev / source install (the long-standing path):
      ``[sys.executable, "-m", "cloris.worker", ...]``. Test fixtures
      that monkeypatch ``subprocess.Popen`` continue to observe this
      shape because ``getattr(sys, 'frozen', False)`` is false outside
      the frozen .app.

    Phase F Slice F1: ``--source`` threads the source name into the
    worker so the wrapper can dispatch to the right per-source
    orchestrator argv builder via :data:`cloris.launchers.LAUNCHERS`.
    Slice 3 callers without ``--source`` continue to default to
    LinkedIn at the wrapper boundary.
    """

    worker_bin = _frozen_worker_binary_path()
    if worker_bin is not None:
        argv = [str(worker_bin)]
    else:
        argv = [sys.executable, "-m", "cloris.worker"]

    argv.extend(
        [
            "--source",
            source,
            "--brief",
            brief_path,
            "--brief-id",
            brief_id,
            "--state-dir",
            str(state_dir),
        ]
    )
    if mode == "resume":
        argv.extend(["--mode", "resume"])
    return argv


def _spawn_worker_for_source(
    *,
    source: str,
    brief_path: Path,
    mode: Literal["fresh", "resume"],
) -> _SpawnResult:
    """Spawn a detached worker for the given brief + source.

    Phase F Slice F1. Single source of truth for both launch and
    resume across every registered source. The per-source seam is the
    :data:`cloris.launchers.LAUNCHERS` registry, which maps
    ``source`` → ``(state_key_fn, state_dir_fn, orchestrator_argv_fn)``.

    Steps:

    1. Validate that ``brief_path`` exists on disk; raise
       :class:`BriefPathNotFoundError` if not (route maps to HTTP 400).
    2. Resolve the per-source state directory + brief id via the
       registry so the sidecar carries a truthful ``brief_id`` even
       before the orchestrator inserts a ``runs`` row.
    3. Probe any existing ``worker.json``: a present sidecar with an
       ``int`` ``pid`` field that is currently alive raises
       :class:`WorkerAlreadyRunningError` (route maps to HTTP 409). A
       missing sidecar, malformed sidecar, non-int ``pid``, or dead
       ``pid`` is treated as stale and silently overwritten by the new
       worker.
    4. Pre-flight resume against the read model. Spawning a worker
       for "resume" when there's no pending work would surface
       success in the UI before the worker silently exits.
    5. Spawn ``python -m cloris.worker --source <source> ...`` with
       ``start_new_session=True`` so the worker survives the API
       process exiting and is its own process-group leader. Stdio is
       fully detached.
    6. Return a :class:`_SpawnResult` with ``pid`` from ``Popen.pid`` —
       the same PID will belong to the per-source orchestrator after
       the worker ``execvp``s.
    """

    from cloris.launchers import LAUNCHERS

    if source not in LAUNCHERS:
        raise UnknownSourceError(source=source, allowed=tuple(sorted(LAUNCHERS.keys())))

    if not brief_path.exists():
        raise BriefPathNotFoundError(str(brief_path))

    launcher = LAUNCHERS[source]
    state_dir = launcher.state_dir_fn(str(brief_path))
    brief_id = launcher.state_key_fn(str(brief_path))

    # Phase 1.1: serialize read-sidecar + spawn across Cloris UI processes
    # on the same machine so two simultaneous launches cannot race-spawn two
    # workers for the same state dir. The lock release waits until the
    # spawned worker has written its sidecar (wait_for_sidecar), closing
    # the residual race between Popen-return and the worker's first write.
    with state_dir_launch_lock(state_dir, timeout=DEFAULT_LAUNCH_LOCK_TIMEOUT_S):
        existing = read_sidecar(state_dir)
        if existing is not None:
            existing_pid = existing.get("pid")
            if isinstance(existing_pid, int) and is_pid_alive(existing_pid):
                raise WorkerAlreadyRunningError(
                    pid=existing_pid,
                    state_dir=str(state_dir),
                )

        # Phase 1.3: pre-flight resume against the read model. Spawning a
        # worker for "resume" when there's no pending work would surface
        # success in the UI before the worker silently exits. Pending=None
        # (unknown — progress.json missing/malformed) is allowed through
        # so the orchestrator's own bias toward attempting resume can do
        # its thing; pending=False is a clean rejection.
        if mode == "resume":
            pending = read_models.has_pending_work(state_dir)
            if pending is False:
                raise NoPendingWorkError(state_dir=str(state_dir))

        argv = _build_worker_argv(
            source=source,
            brief_path=str(brief_path),
            brief_id=brief_id,
            state_dir=state_dir,
            mode=mode,
        )
        process = subprocess.Popen(
            argv,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )

        # Wait for the worker's first sidecar write before releasing the
        # lock. Bounded: if the worker fails before writing, the next
        # launcher sees no sidecar and proceeds normally.
        wait_for_sidecar(
            state_dir,
            expected_pid=process.pid,
            timeout=DEFAULT_SIDECAR_WAIT_TIMEOUT_S,
        )

    return _SpawnResult(
        pid=process.pid,
        state_dir=state_dir,
        worker_json_path=state_dir / "worker.json",
    )


def _spawn_linkedin_worker(
    req: LaunchLinkedInRequest,
    *,
    mode: Literal["fresh", "resume"],
) -> _SpawnResult:
    """Backward-compat shim around :func:`_spawn_worker_for_source`.

    Phase F Slice F1 generalized the spawn helper. Existing test
    fixtures import ``_spawn_linkedin_worker`` directly; this shim
    keeps them working while the new code path is what production
    actually uses.
    """

    brief_path = Path(req.brief_path)
    return _spawn_worker_for_source(
        source="linkedin", brief_path=brief_path, mode=mode
    )


def launch_linkedin_worker(req: LaunchLinkedInRequest) -> LaunchResponse:
    """Spawn a detached LinkedIn worker in fresh mode (legacy synonym).

    Phase F Slice F1 keeps this helper as a thin wrapper over the
    generalized :func:`_spawn_worker_for_source` so the legacy
    ``POST /api/launch/linkedin`` endpoint keeps its byte-for-byte
    contract while the new ``POST /api/launch/{source}`` endpoint
    consumes the same spawner.
    """

    brief_path = Path(req.brief_path)
    result = _spawn_worker_for_source(
        source="linkedin", brief_path=brief_path, mode="fresh"
    )
    return LaunchResponse(
        source="linkedin",
        input_mode="concurrent",
        mode="fresh",
        pid=result.pid,
        state_dir=str(result.state_dir),
        worker_json_path=str(result.worker_json_path),
    )


def resume_linkedin_worker(req: LaunchLinkedInRequest) -> ResumeResponse:
    """Spawn a detached LinkedIn worker in resume mode (legacy synonym).

    See :func:`launch_linkedin_worker`. Same generalized spawner;
    different mode + response shape so the legacy
    ``POST /api/resume/linkedin`` endpoint keeps its existing contract.
    """

    brief_path = Path(req.brief_path)
    result = _spawn_worker_for_source(
        source="linkedin", brief_path=brief_path, mode="resume"
    )
    return ResumeResponse(
        source="linkedin",
        input_mode="concurrent",
        pid=result.pid,
        state_dir=str(result.state_dir),
        worker_json_path=str(result.worker_json_path),
    )


def _resolve_state_dir(source: str, state_key: str) -> Optional[Path]:
    """Return the discovered state dir matching ``(source, state_key)``.

    Iterates :func:`cloris.control_plane.enumerate_state_dirs` rather than
    naively joining ``STATE_ROOT / source / state_key``. This is the
    path-traversal-safe lookup: any ``state_key`` that doesn't appear in
    the discovered set returns ``None``, which the route translates to
    HTTP 404.
    """

    for discovered_source, discovered_state_dir in enumerate_state_dirs():
        if discovered_source == source and discovered_state_dir.name == state_key:
            return discovered_state_dir
    return None


def stop_worker(source: str, state_key: str) -> StopResponse:
    """Resolve the state dir, classify the worker, optionally SIGTERM.

    Pure helper — no FastAPI imports beyond the type contract. Returns a
    :class:`cloris.models.StopResponse`; the route is responsible for
    setting the HTTP status code (202 when ``worker_state == "stopping"``,
    200 otherwise).

    Steps:

    1. Resolve ``state_dir`` via :func:`_resolve_state_dir`. If not
       found, raise :class:`StateDirNotFoundError`.
    2. Read ``worker.json`` via :func:`cloris.worker.read_sidecar`.
    3. Missing sidecar ⇒ ``worker_state="missing"``, ``pid=None``. **No
       signal sent.**
    4. Sidecar present, but ``pid`` is not a valid int OR
       :func:`cloris.worker.is_pid_alive` returns ``False`` ⇒
       ``worker_state="stale"``. **No signal sent. Sidecar not deleted.**
    5. Alive PID ⇒ ``os.kill(pid, signal.SIGTERM)`` exactly once and
       return ``worker_state="stopping"``. ``ProcessLookupError`` (race:
       process died between probe and signal) ⇒ treat as stale.
       ``PermissionError`` (we cannot signal it but it exists) ⇒ also
       treat as stale; the user-facing contract is "stop is best-effort
       against the worker we own".

    Slice 4 deliberately does **not** wait for SIGTERM to take effect
    and does **not** escalate to SIGKILL. Both are explicit non-goals
    per the operative plan.
    """

    state_dir = _resolve_state_dir(source, state_key)
    if state_dir is None:
        raise StateDirNotFoundError(source, state_key)

    sidecar = read_sidecar(state_dir)
    if sidecar is None:
        return StopResponse(
            source=source,  # type: ignore[arg-type]
            state_key=state_key,
            state_dir=str(state_dir),
            worker_state="missing",
            pid=None,
        )

    pid_raw = sidecar.get("pid")
    if not isinstance(pid_raw, int) or isinstance(pid_raw, bool):
        return StopResponse(
            source=source,  # type: ignore[arg-type]
            state_key=state_key,
            state_dir=str(state_dir),
            worker_state="stale",
            pid=None,
        )

    if not is_pid_alive(pid_raw):
        return StopResponse(
            source=source,  # type: ignore[arg-type]
            state_key=state_key,
            state_dir=str(state_dir),
            worker_state="stale",
            pid=pid_raw,
        )

    try:
        _send_sigterm(pid_raw)
    except ProcessLookupError:
        return StopResponse(
            source=source,  # type: ignore[arg-type]
            state_key=state_key,
            state_dir=str(state_dir),
            worker_state="stale",
            pid=pid_raw,
        )
    except PermissionError:
        return StopResponse(
            source=source,  # type: ignore[arg-type]
            state_key=state_key,
            state_dir=str(state_dir),
            worker_state="stale",
            pid=pid_raw,
        )

    return StopResponse(
        source=source,  # type: ignore[arg-type]
        state_key=state_key,
        state_dir=str(state_dir),
        worker_state="stopping",
        pid=pid_raw,
    )


@router.get(
    "/api/launch-readiness/{source}/{brief_id:path}",
    response_model=LaunchReadinessResponse,
)
def api_launch_readiness(source: str, brief_id: str) -> LaunchReadinessResponse:
    """Phase D Slice D9 (Ledger L4). Per-source launch-readiness probe.

    Surfaces blockers BEFORE worker spawn (LinkedIn browser session,
    GitHub token scope, missing per-brief save destinations). The
    recruiter sees specific remediation — "open linkedin.com/talent in
    a tab", "fill in the LinkedIn project ID under Where Cloris
    saves" — instead of generic launch failure after the worker dies.

    Phase F Slice F2 layered brief-level readiness on top of the
    source-level probe via the same ``_readiness_blockers`` aggregator
    F1's launch path uses, so this read endpoint and the launch path
    share one truth.

    Errors:
      * 422 ``unknown_source`` — ``source`` is not one of the
        registered modules (currently linkedin / github).
    """

    from cloris.launchers import LAUNCHERS

    if source not in LAUNCHERS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unknown_source",
                "source": source,
                "allowed": sorted(LAUNCHERS.keys()),
            },
        )

    blockers = _readiness_blockers(source, brief_id)
    return LaunchReadinessResponse(
        source=source,  # type: ignore[arg-type]
        brief_id=brief_id,
        ready=len(blockers) == 0,
        blockers=[
            LaunchReadinessBlocker(
                kind=b.kind,
                message=b.message,
                remediation=b.remediation,
            )
            for b in blockers
        ],
    )


# ---------------------------------------------------------------------------
# Phase F Slice F1 — Generic POST /api/launch/{source} + collapsed resume.
# ---------------------------------------------------------------------------
#
# The canonical launch endpoint as of Phase F. Accepts ``{brief_id, mode,
# force?}`` and dispatches to the per-source spawn function via
# :data:`cloris.launchers.LAUNCHERS`. Mode "resume" is folded into the same
# route so the legacy ``POST /api/resume/linkedin`` endpoint is just a
# synonym. The legacy ``POST /api/launch/linkedin`` likewise translates
# ``brief_path → brief_id`` and calls this same code path.


def _resolve_brief_path_or_raise(brief_id: str) -> Path:
    """Resolve a brief_id to its on-disk path or raise BriefIdNotFoundError.

    Phase F Slice F1. The brief_id is the universal Cloris brief
    identifier produced by the existing ``linkedin_state_key`` hash
    (which reads brief CONTENT, not path, so the value stays stable
    across flat→nested migrations regardless of source).
    """

    resolved = _resolve_brief_by_id(brief_id)
    if resolved is None:
        raise BriefIdNotFoundError(brief_id)
    abs_path, _was_flat = resolved
    return abs_path


def _readiness_blockers(source: str, brief_id: str) -> list:
    """Aggregate launch-readiness blockers across two layers.

    Phase D Slice D9 introduced source-level readiness probes (auth /
    config / net) at :mod:`linkedin.health` and :mod:`github.health`.
    Phase F Slice F2 layers brief-level readiness on top via
    :data:`cloris.launchers.LAUNCHERS[source].save_destination_blocker_fn`.

    Both layers are aggregated AND-style: any blocker on either layer
    blocks the launch (unless ``force=true`` at the caller). The two
    layers are kept separate so source-level probes stay brief-agnostic
    (they just check "can we connect at all?") and brief-level checks
    stay source-agnostic at the registry boundary.

    Returns an empty list when both layers are clear. Sources unknown
    to the probe return an empty list (probe doesn't know the source
    ⇒ caller handled UnknownSourceError already; defensive).
    """

    blockers: list = []

    # Layer 1 — source-level readiness (Phase D D9).
    if source == "linkedin":
        from linkedin.health import probe_linkedin_readiness

        report = probe_linkedin_readiness()
    elif source == "github":
        from github.health import probe_github_readiness

        report = probe_github_readiness()
    else:
        report = None

    if report is not None and not report.ready:
        blockers.extend(report.blockers)

    # Layer 2 — brief-level readiness (Phase F F2). Resolve the brief
    # path if possible; if it can't be resolved (bogus brief_id), let
    # the layer-2 check pass through — the launch handler will surface
    # a 404 separately.
    from cloris.launchers import LAUNCHERS

    launcher = LAUNCHERS.get(source)
    if launcher is not None:
        try:
            resolved = _resolve_brief_by_id(brief_id)
        except Exception:
            resolved = None
        if resolved is not None:
            abs_path, _was_flat = resolved
            try:
                brief_blocker = launcher.save_destination_blocker_fn(
                    str(abs_path)
                )
            except Exception:
                brief_blocker = None
            if brief_blocker is not None:
                blockers.append(brief_blocker)

    return blockers


def _launch_for_source_impl(source: str, req: LaunchRequest) -> LaunchResponse:
    """Phase F Slice F1 — generic launch dispatch (handler implementation).

    Extracted from the route decorator so the route registration can be
    moved AFTER the legacy literal routes (Starlette matches in route-
    declaration order; a path-param route declared first would shadow
    ``/api/launch/linkedin``). The actual ``@router.post`` for this
    handler lives at the bottom of the file, after the legacy routes.

    See route docstring (``launch_for_source``) for the full contract.
    """

    try:
        from cloris.launchers import LAUNCHERS

        if source not in LAUNCHERS:
            raise UnknownSourceError(
                source=source, allowed=tuple(sorted(LAUNCHERS.keys()))
            )

        brief_path = _resolve_brief_path_or_raise(req.brief_id)

        if not req.force:
            blockers = _readiness_blockers(source, req.brief_id)
            if blockers:
                raise LaunchNotReadyError(source=source, blockers=blockers)

        result = _spawn_worker_for_source(
            source=source, brief_path=brief_path, mode=req.mode
        )
    except UnknownSourceError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unknown_source",
                "source": exc.source,
                "allowed": list(exc.allowed),
            },
        ) from exc
    except BriefIdNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "brief_id_not_found", "brief_id": exc.brief_id},
        ) from exc
    except LaunchNotReadyError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "launch_not_ready",
                "source": exc.source,
                "blockers": [
                    {
                        "kind": b.kind,
                        "message": b.message,
                        "remediation": b.remediation,
                    }
                    for b in exc.blockers
                ],
            },
        ) from exc
    except BriefPathNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "brief_path_not_found", "brief_path": str(exc)},
        ) from exc
    except WorkerAlreadyRunningError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "worker_already_running",
                "pid": exc.pid,
                "state_dir": exc.state_dir,
            },
        ) from exc
    except NoPendingWorkError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "no_pending_work", "state_dir": exc.state_dir},
        ) from exc
    except LaunchLockTimeoutError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "launch_lock_timeout",
                "state_dir": exc.state_dir,
                "timeout_s": exc.timeout,
            },
        ) from exc

    return LaunchResponse(
        source=source,  # type: ignore[arg-type]
        input_mode="concurrent",
        mode=req.mode,
        pid=result.pid,
        state_dir=str(result.state_dir),
        worker_json_path=str(result.worker_json_path),
    )


@router.post("/api/launch/linkedin", status_code=201, response_model=LaunchResponse)
def launch_linkedin(req: LaunchLinkedInRequest) -> LaunchResponse:
    """Spawn a detached LinkedIn worker; map typed errors to HTTP codes.

    Phase F Slice F1: legacy synonym route. Kept for backward compat
    with clients posting ``{brief_path}``. Internally calls the same
    spawn helper as the canonical ``POST /api/launch/{source}``.
    Deprecation window: ~6 months from F1 ship.

    - :class:`BriefPathNotFoundError` → HTTP 400 with
      ``{"error": "brief_path_not_found", "brief_path": "..."}``.
    - :class:`WorkerAlreadyRunningError` → HTTP 409 with
      ``{"error": "worker_already_running", "pid": ..., "state_dir": "..."}``.
    """

    try:
        return launch_linkedin_worker(req)
    except BriefPathNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "brief_path_not_found", "brief_path": str(exc)},
        ) from exc
    except WorkerAlreadyRunningError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "worker_already_running",
                "pid": exc.pid,
                "state_dir": exc.state_dir,
            },
        ) from exc
    except LaunchLockTimeoutError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "launch_lock_timeout",
                "state_dir": exc.state_dir,
                "timeout_s": exc.timeout,
            },
        ) from exc


@router.post(
    "/api/resume/linkedin", status_code=201, response_model=ResumeResponse
)
def resume_linkedin(req: LaunchLinkedInRequest) -> ResumeResponse:
    """Spawn a detached LinkedIn worker in resume mode.

    Error mapping (Phase 1.3 adds the 422 case):

    - :class:`BriefPathNotFoundError` → HTTP 400.
    - :class:`WorkerAlreadyRunningError` → HTTP 409.
    - :class:`NoPendingWorkError` → HTTP 422 (no pending work — pre-flight
      from the canonical read model rejected this resume before any
      worker was spawned).
    - :class:`LaunchLockTimeoutError` → HTTP 503.
    """

    try:
        return resume_linkedin_worker(req)
    except BriefPathNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "brief_path_not_found", "brief_path": str(exc)},
        ) from exc
    except WorkerAlreadyRunningError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "worker_already_running",
                "pid": exc.pid,
                "state_dir": exc.state_dir,
            },
        ) from exc
    except NoPendingWorkError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "no_pending_work",
                "state_dir": exc.state_dir,
            },
        ) from exc
    except LaunchLockTimeoutError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "launch_lock_timeout",
                "state_dir": exc.state_dir,
                "timeout_s": exc.timeout,
            },
        ) from exc


@router.post(
    "/api/launch/{source}", status_code=201, response_model=LaunchResponse
)
def launch_for_source(source: str, req: LaunchRequest) -> LaunchResponse:
    """Phase F Slice F1. Generic per-source launch endpoint.

    Resolves ``brief_id`` to a brief on disk, runs the launch-readiness
    probe (skip if ``force=true``), then dispatches to the per-source
    spawn function via :data:`cloris.launchers.LAUNCHERS`. Returns
    :class:`LaunchResponse` with ``source``, ``mode``, and the spawned
    worker's ``pid`` / ``state_dir`` / ``worker_json_path``.

    The route is registered AFTER the legacy ``/api/launch/linkedin``
    and ``/api/resume/linkedin`` routes so Starlette matches the
    literal paths first; the path-param route catches all other
    sources (``github``, future Researcher, etc.).

    Error mapping:

    - :class:`UnknownSourceError` → HTTP 422 with allowed-sources list.
    - :class:`BriefIdNotFoundError` → HTTP 404.
    - :class:`LaunchNotReadyError` → HTTP 422 with structured blocker list
      (only when ``force=false``).
    - :class:`BriefPathNotFoundError` → HTTP 400 (defensive — the brief
      was resolved but disappeared between resolve and spawn).
    - :class:`WorkerAlreadyRunningError` → HTTP 409.
    - :class:`NoPendingWorkError` → HTTP 422 (only fires for ``mode="resume"``).
    - :class:`LaunchLockTimeoutError` → HTTP 503.
    """

    return _launch_for_source_impl(source, req)


@router.post("/api/stop/{source}/{state_key}", response_model=StopResponse)
def stop(source: str, state_key: str, response: Response) -> StopResponse:
    """Send SIGTERM to the worker for ``(source, state_key)`` if alive.

    Status code is dynamic:

    - 202 when the helper signaled an alive PID.
    - 200 when there was nothing to signal (``missing`` or ``stale``).
    - 404 when the state dir isn't in the discovered set.

    The body always carries the truthful ``worker_state``; clients should
    branch on the body, not on the status code.
    """

    try:
        result = stop_worker(source, state_key)
    except StateDirNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "state_dir_not_found",
                "source": exc.source,
                "state_key": exc.state_key,
            },
        ) from exc

    if result.worker_state == "stopping":
        response.status_code = 202
    return result


# --- Onboarding flow intake sessions (A24 trial plan, Slice 1B) ---
#
# The intake-session API is the persistence boundary for the brief-authoring
# conversation. All five endpoints route through :mod:`cloris.intake_sessions`,
# which talks to a dedicated global SQLite at
# ``output/intake/intake_sessions.sqlite3`` (resolved via
# :func:`shared.output_paths.resolve_intake_db_path`). The store opens
# read/write — distinct from the read-only ``mode=ro`` path used by
# :func:`cloris.control_plane.aggregate_status` for the status aggregator.


def _intake_db_path() -> Path:
    """Path to the intake-sessions SQLite store.

    Single seam shared by both the writer-instantiating
    :func:`_intake_store` (for POST/PATCH/DELETE handlers) and the
    read-only ``read_models`` calls in the GET handlers. Tests
    monkeypatch this helper to redirect both sides at the same tmp
    DB without instantiating the writer twice.
    """

    from shared.output_paths import resolve_intake_db_path

    return resolve_intake_db_path()


def _intake_store() -> RuntimeStateStore:
    """Resolve the canonical RuntimeStateStore for intake-session writes.

    A small helper kept inside :mod:`cloris.api` so the endpoints stay
    boring one-liners. Reads :func:`_intake_db_path` so callers that
    need the path directly (read-only GETs routing through
    ``read_models``) share the same monkeypatch seam as writers.
    """

    return RuntimeStateStore(_intake_db_path())


@router.post(
    "/api/intake/sessions",
    status_code=201,
    response_model=IntakeSessionResponse,
)
def create_intake_session_endpoint(
    req: IntakeSessionCreateRequest,
) -> IntakeSessionResponse:
    """Create a new intake session.

    The body is :class:`IntakeSessionCreateRequest` with a single optional
    ``role_title`` hint; everything else is server-set
    (``current_step="welcome"``, empty ``state_json``, fresh timestamps).
    Returns 201 with the hydrated session.
    """

    session = intake_sessions.create_intake_session(
        store=_intake_store(), role_title=req.role_title
    )
    return IntakeSessionResponse(
        slice="v0-onboarding-slice-1",
        session=IntakeSession.model_validate(session),
    )


@router.get(
    "/api/intake/sessions",
    response_model=IntakeSessionListResponse,
)
def list_intake_sessions_endpoint() -> IntakeSessionListResponse:
    """List active (non-archived) intake sessions, newest first.

    Read-only path: routes through ``read_models.list_intake_sessions``
    rather than instantiating the writer ``RuntimeStateStore``. The
    writer's __init__ runs DDL + ``INSERT OR REPLACE INTO meta`` on
    every call, which on a polled GET endpoint silently rewrites the
    schema_version row and serializes against any concurrent intake
    write. Uses ``_intake_db_path()`` so test monkeypatches that
    redirect intake to a tmp DB cover both the writer side
    (``_intake_store``) and this read side at the same seam.
    """

    from shared.runtime_state import read_models

    sessions = read_models.list_intake_sessions(_intake_db_path())
    return IntakeSessionListResponse(
        slice="v0-onboarding-slice-1",
        sessions=[IntakeSession.model_validate(row) for row in sessions],
    )


@router.get(
    "/api/intake/sessions/{session_id}",
    response_model=IntakeSessionResponse,
)
def get_intake_session_endpoint(session_id: int) -> IntakeSessionResponse:
    """Return one intake session by id, or 404 if missing.

    Read-only path: routes through ``read_models.get_intake_session``
    instead of the writer-instantiated ``_intake_store()``. See the
    list endpoint above for the rationale and seam-sharing.
    """

    from shared.runtime_state import read_models

    session = read_models.get_intake_session(
        _intake_db_path(), session_id=session_id
    )
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "intake_session_not_found", "id": session_id},
        )
    return IntakeSessionResponse(
        slice="v0-onboarding-slice-1",
        session=IntakeSession.model_validate(session),
    )


@router.patch(
    "/api/intake/sessions/{session_id}",
    response_model=IntakeSessionResponse,
)
def patch_intake_session_endpoint(
    session_id: int, req: IntakeSessionPatchRequest
) -> IntakeSessionResponse:
    """Partial-update an intake session.

    Any combination of ``current_step``, ``state_json``, ``role_title``
    can be sent. Missing fields are preserved. ``updated_at`` is always
    bumped.
    """

    session = intake_sessions.patch_intake_session(
        store=_intake_store(),
        session_id=session_id,
        current_step=req.current_step,
        state_json=req.state_json,
        role_title=req.role_title,
    )
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "intake_session_not_found", "id": session_id},
        )
    return IntakeSessionResponse(
        slice="v0-onboarding-slice-1",
        session=IntakeSession.model_validate(session),
    )


@router.delete(
    "/api/intake/sessions/{session_id}",
    response_model=IntakeSessionDeleteResponse,
)
def delete_intake_session_endpoint(
    session_id: int,
) -> IntakeSessionDeleteResponse:
    """Hard-delete an intake session by id; 404 if missing."""

    deleted = intake_sessions.delete_intake_session(
        store=_intake_store(), session_id=session_id
    )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": "intake_session_not_found", "id": session_id},
        )
    return IntakeSessionDeleteResponse(
        slice="v0-onboarding-slice-1", deleted=True, id=session_id
    )


@router.post(
    "/api/intake/sessions/{session_id}/complete",
    response_model=IntakeSessionCompleteResponse,
)
def complete_intake_session_endpoint(
    session_id: int,
) -> IntakeSessionCompleteResponse:
    """Finalize an intake session — write the V2 brief and stamp completed.

    Phase D Slice D3. The wizard's terminal call. The session must
    carry a parseable V2 brief at ``state_json["v2_draft"]``; this
    endpoint:

    1. Validates the V2 draft via :func:`validate_v2_brief`.
    2. Picks a target directory under ``config/``: prefers a
       slugified ``role_title`` (the wizard captures it early), falls
       back to ``intake-<session_id>`` so the write is always well-defined.
       If the target dir already contains a ``brief.json`` we treat
       that as a name collision and 409 — the recruiter must pick a
       different role title or edit the existing brief instead.
    3. Writes via :func:`shared.brief_writer.write_brief_atomic`
       (canonical-first + versions/ snapshot, matching D2's contract).
    4. Computes ``brief_id`` via :func:`linkedin_state_key` so the
       wizard can navigate to ``#/brief/<brief_id>`` and the value
       matches what runtime_state will use during runs.
    5. Marks the session ``current_step="completed"``,
       ``completed_at=now``, ``brief_id_draft=<computed>``.

    Errors:
      * 404 ``intake_session_not_found``
      * 422 ``invalid_v2_brief`` — draft missing or malformed
        (carries ``missing_keys`` / ``invalid_keys``)
      * 409 ``brief_already_exists`` — target dir name already has a
        ``brief.json``
      * 500 ``brief_write_failed`` — atomic-write infrastructure problem
    """

    from shared.brief_v2_schema import BriefSchemaError, validate_v2_brief
    from shared.brief_writer import write_brief_atomic
    from shared.output_paths import linkedin_state_key, slugify_output_component

    session = intake_sessions.get_intake_session(
        store=_intake_store(), session_id=session_id
    )
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "intake_session_not_found", "id": session_id},
        )

    state = session.get("state_json") or {}
    v2_draft = state.get("v2_draft")
    if not isinstance(v2_draft, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_v2_brief",
                "message": (
                    "Session has no v2_draft on state_json — the review "
                    "chapter must populate it before completion."
                ),
                "missing_keys": ["v2_draft"],
                "invalid_keys": [],
            },
        )

    try:
        validate_v2_brief(v2_draft)
    except BriefSchemaError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_v2_brief",
                "message": str(exc),
                "missing_keys": list(exc.missing_keys),
                "invalid_keys": list(exc.invalid_keys),
            },
        ) from exc

    role_title = (
        v2_draft.get("role_title")
        if isinstance(v2_draft.get("role_title"), str)
        else session.get("role_title")
    )
    slug_source = role_title or f"intake-{session_id}"
    slug = slugify_output_component(slug_source)
    target_dir = _CONFIG_DIR / slug
    target_path = target_dir / "brief.json"
    if target_path.exists():
        raise HTTPException(
            status_code=409,
            detail={
                "error": "brief_already_exists",
                "message": (
                    f"A brief already exists at config/{slug}/brief.json. "
                    f"Pick a different role title or edit the existing brief."
                ),
                "slug": slug,
            },
        )

    try:
        write_brief_atomic(abs_path=target_path, payload=v2_draft)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "brief_write_failed", "reason": str(exc)},
        ) from exc

    try:
        brief_id = linkedin_state_key(brief_path=str(target_path))
    except Exception as exc:
        # The brief is valid V2 (validate_v2_brief just succeeded), so
        # linkedin_state_key should always succeed too. If it doesn't,
        # the write succeeded — surface that the brief is on disk but
        # we can't pin its id; recovery is to re-fetch via the brief
        # library which recomputes the id on demand.
        log.error(
            "brief_id computation failed post-write at %s: %s",
            target_path,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "brief_id_computation_failed",
                "reason": str(exc),
                "brief_path": str(target_path.relative_to(_PROJECT_ROOT)),
            },
        ) from exc

    completed = intake_sessions.complete_intake_session(
        store=_intake_store(), session_id=session_id, brief_id=brief_id
    )
    if completed is None:
        # Race: the session was deleted between the get_intake_session
        # call at the top of this handler and the complete_intake_session
        # call here. write_brief_atomic already succeeded — the brief
        # file is on disk. Surface 410 Gone with structured detail so
        # the wizard can recover via the brief library (which scans
        # config/<slug>/brief.json regardless of session state).
        log.warning(
            "Intake session %d disappeared during completion; "
            "brief written at %s (brief_id=%s) but the session row "
            "was removed mid-flight",
            session_id,
            target_path,
            brief_id,
        )
        raise HTTPException(
            status_code=410,
            detail={
                "error": "intake_session_gone_after_complete",
                "message": (
                    "The brief was written but the intake draft was "
                    "removed before completion stamped through. "
                    "Refresh the brief library to find it."
                ),
                "brief_id": brief_id,
                "brief_path": str(target_path.relative_to(_PROJECT_ROOT)),
            },
        )

    log.info(
        "Intake session %d completed → brief_id=%s at %s "
        "(Phase D Slice D3)",
        session_id,
        brief_id,
        target_path,
    )

    return IntakeSessionCompleteResponse(
        slice="v0-onboarding-slice-1",
        session=IntakeSession.model_validate(completed),
        brief_id=brief_id,
        brief_path=str(target_path.relative_to(_PROJECT_ROOT)),
    )


# ---------------------------------------------------------------------------
# Brief polish + one-deep undo (Phase D Slice D4)
# ---------------------------------------------------------------------------
#
# The polish endpoint reshapes the recruiter's chapter captures into a
# polished V2 brief draft using the seven-route cascade in
# :mod:`market_intelligence.brief_polish`. The restore endpoint walks back
# the most recent polish via the one-deep undo buffer.
#
# State_json schema additions both endpoints touch:
#   - state_json["v2_draft"]: the canonical V2 brief draft (existing).
#   - state_json["v2_draft_polish_meta"]: {source, confidence, polished_at}
#     written by the polish endpoint, surfaced by the Reference Slip.
#   - state_json["v2_draft_prev"]: {v2_draft, polish_meta} snapshot of the
#     pre-polish state. Polish writes it; restore consumes it.
#
# All three are sibling keys, NOT nested under v2_draft, so v2_draft
# continues to pass :func:`validate_v2_brief` cleanly at completion time.


@router.post(
    "/api/intake/sessions/{session_id}/polish",
    response_model=IntakeSessionResponse,
)
def polish_intake_session_endpoint(
    session_id: int,
) -> IntakeSessionResponse:
    """Polish the in-flight v2_draft via the LLM cascade.

    Phase D Slice D4. Reads the recruiter's chapter captures from
    ``state_json``, snapshots the pre-polish state into the one-deep
    undo buffer, runs :class:`BriefPolishBackend`, and writes the
    polished v2_draft + polish_meta back. Returns the updated session.

    Snapshot ordering matters: the snapshot captures whatever v2_draft
    exists at the moment of the polish call. The frontend
    :func:`polishBrief` flushes pending debounced edits BEFORE invoking
    this endpoint, so any in-flight hand-edits are correctly captured
    into the undo buffer.

    Errors:
      * 404 ``intake_session_not_found``
      * 422 ``invalid_state_json`` — defensive; the session row's
        ``state_json`` should always be a dict per the schema.
    """

    from market_intelligence.brief_polish import BriefPolishBackend

    session = intake_sessions.get_intake_session(
        store=_intake_store(), session_id=session_id
    )
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "intake_session_not_found", "id": session_id},
        )

    state = session.get("state_json") or {}
    if not isinstance(state, dict):
        # Defensive — :func:`_row_to_session` collapses non-dict
        # state_json to {}, but a future schema drift could surface a
        # non-dict here. Surface 422 rather than crash.
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_state_json",
                "message": "Session state_json is not an object.",
            },
        )

    # Pull the chapter captures the polish backend reads from. We pass
    # the entire chapter_captures bag (rather than per-key fields) so
    # the backend stays the single source of truth for which keys it
    # consumes — adding a new chapter capture later doesn't require
    # touching this endpoint.
    chapter_captures: dict[str, object] = {}
    for chapter_id in ("role", "good_looks", "lookalikes", "where_to_look"):
        sub = state.get(chapter_id)
        if isinstance(sub, dict):
            chapter_captures[chapter_id] = sub

    # Snapshot the pre-polish state into the one-deep undo buffer
    # BEFORE calling the polish backend. Capturing both v2_draft and
    # polish_meta (when present) keeps lineage truthful — restoring back
    # to a prior LLM polish surfaces source=llm in the Reference Slip,
    # restoring back to the seed surfaces no polish_meta at all.
    prior_v2_draft = state.get("v2_draft")
    prior_polish_meta = state.get("v2_draft_polish_meta")
    if isinstance(prior_v2_draft, dict):
        prev_snapshot: dict[str, object] = {"v2_draft": prior_v2_draft}
        if isinstance(prior_polish_meta, dict):
            prev_snapshot["polish_meta"] = prior_polish_meta
        state["v2_draft_prev"] = prev_snapshot

    backend = BriefPolishBackend()
    result = backend.polish(
        chapter_captures=chapter_captures,
        role_title=session.get("role_title"),
        session_id=session_id,
    )

    state["v2_draft"] = result.v2_draft
    state["v2_draft_polish_meta"] = result.to_meta_dict()

    updated = intake_sessions.patch_intake_session(
        store=_intake_store(),
        session_id=session_id,
        state_json=state,
    )
    if updated is None:
        # Race: the session was deleted between the get and the patch.
        # Same shape as the complete endpoint's race handling at line 3018.
        raise HTTPException(
            status_code=410,
            detail={
                "error": "intake_session_gone_after_polish",
                "id": session_id,
            },
        )
    return IntakeSessionResponse(
        slice="v0-onboarding-slice-1",
        session=IntakeSession.model_validate(updated),
    )


@router.post(
    "/api/intake/sessions/{session_id}/restore_prev_draft",
    response_model=IntakeSessionResponse,
)
def restore_prev_draft_endpoint(
    session_id: int,
) -> IntakeSessionResponse:
    """Restore the pre-polish v2_draft from the one-deep undo buffer.

    Phase D Slice D4. Pops ``state_json["v2_draft_prev"]`` into
    ``state_json["v2_draft"]``; restores ``state_json["v2_draft_polish_meta"]``
    from the buffer's ``polish_meta`` field if non-null; deletes the meta
    key otherwise. The buffer is one-shot consume — ``v2_draft_prev`` is
    deleted, not retained.

    Errors:
      * 404 ``intake_session_not_found`` — session id doesn't exist.
      * 404 ``no_prev_draft`` — the session has no ``v2_draft_prev`` to
        restore from. The frontend hides the Restore link when the buffer
        is absent so this should never fire from the UI; defensive belt-
        and-suspenders for direct-API access.
      * 422 ``invalid_state_json`` — defensive; same reasoning as the
        polish endpoint.
    """

    session = intake_sessions.get_intake_session(
        store=_intake_store(), session_id=session_id
    )
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "intake_session_not_found", "id": session_id},
        )

    state = session.get("state_json") or {}
    if not isinstance(state, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_state_json",
                "message": "Session state_json is not an object.",
            },
        )

    prev = state.get("v2_draft_prev")
    if not isinstance(prev, dict) or "v2_draft" not in prev:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "no_prev_draft",
                "id": session_id,
                "message": (
                    "No prior draft to restore. Polish the brief at least "
                    "once to populate the undo buffer."
                ),
            },
        )

    state["v2_draft"] = prev.get("v2_draft")
    prior_meta = prev.get("polish_meta")
    if isinstance(prior_meta, dict):
        state["v2_draft_polish_meta"] = prior_meta
    else:
        # Restoring back to a state with no polish lineage (e.g. the
        # frontend seed) — clear polish_meta so the Reference Slip
        # doesn't lie about the lineage of the restored draft.
        state.pop("v2_draft_polish_meta", None)
    # One-shot consume: the buffer is deleted, not preserved as a stack.
    # Multi-deep undo is post-trial.
    state.pop("v2_draft_prev", None)

    updated = intake_sessions.patch_intake_session(
        store=_intake_store(),
        session_id=session_id,
        state_json=state,
    )
    if updated is None:
        raise HTTPException(
            status_code=410,
            detail={
                "error": "intake_session_gone_after_restore",
                "id": session_id,
            },
        )
    return IntakeSessionResponse(
        slice="v0-onboarding-slice-1",
        session=IntakeSession.model_validate(updated),
    )


# ---------------------------------------------------------------------------
# The Reflection — HITL Market Intelligence
# ---------------------------------------------------------------------------
#
# Two HITL gates around the market-intel pipeline:
#   Gate 1 — The Read   :: planner result + user steering (PATCH /steering)
#   Gate 2 — The Diff   :: proposed brief hunks (POST /commit | /discard)
#
# Long-running phase (research) executes in a background thread; the
# frontend polls GET /api/reflection/sessions/{id} for state transitions.
# Threads are sufficient for trial scope: one Cloris worker, one user,
# one active reflection per brief.
#
# Phase persistence lives in ``reflection_sessions.state_json`` (per the
# CRUD module). The engine phase functions in
# ``market_intelligence.reflection`` are pure with respect to the DB —
# the API layer owns the read/patch/transition cycle.


import threading

from market_intelligence import reflection as reflection_engine
from shared.runtime_state import reflection as reflection_store


# Reflection sessions live next to intake sessions in the same SQLite
# DB; reuse the same store factory so they share the migration path.
_reflection_store_factory = _intake_store


def _reflection_session_response(session: dict) -> ReflectionResponse:
    return ReflectionResponse(
        session=ReflectionSession.model_validate(session)
    )


def _resolve_run_dir_for_run_id(run_id: int) -> Path | None:
    """Best-effort lookup of the finalized run snapshot directory for a run.

    The runs table carries ``output_dir`` (the live state_dir) plus the
    finalized ``output_dir`` once the run completes. For trial scope we
    accept either: ``_resolve_market_intel_run_dir`` in the engine
    knows how to reconcile both. Returns ``None`` if the run id doesn't
    exist; the engine will then raise on missing run_dir which surfaces
    as a 422 to the frontend.

    Routed through ``read_models.run_by_id`` rather than instantiating
    ``RuntimeStateStore``: this is a SELECT-only lookup, and even
    though the only caller today (``create_reflection_session_endpoint``)
    is a POST, mixing the read with a writer instantiation triggers
    DDL + meta-write before the actual write path runs. The read helper
    keeps the lookup honest.
    """

    from shared.output_paths import resolve_runtime_state_path
    from shared.runtime_state import read_models

    try:
        run = read_models.run_by_id(
            resolve_runtime_state_path(), run_id=run_id
        )
    except Exception as exc:
        log.warning("reflection: run lookup failed for run_id=%s: %s", run_id, exc)
        return None
    if run is None or not run.output_dir:
        return None
    return Path(run.output_dir)


@router.post(
    "/api/reflection/sessions",
    status_code=201,
    response_model=ReflectionResponse,
)
def create_reflection_session_endpoint(
    req: ReflectionCreateRequest,
) -> ReflectionResponse:
    """Boot a new reflection session and run the planner phase synchronously.

    Resolves brief_id → brief_path, optionally maps source_run_id →
    run_dir (or accepts an explicit run_dir override), then runs the
    plan phase in-band so the response carries the editorial briefing
    + intentions the recruiter sees at Gate 1.

    Errors:
      * 404 ``brief_id_not_found`` — brief_id doesn't resolve
      * 409 ``reflection_already_active`` — there's already an
        in-flight reflection for this brief
      * 422 ``reflection_no_evidence`` — engine couldn't resolve a
        run_dir or the snapshot is empty
    """

    # Reject if there's already an active reflection for this brief.
    # The frontend should normally catch this via GET /active before
    # POSTing, but the API enforces the invariant so two tabs can't
    # both create.
    existing = reflection_store.get_active_reflection_for_brief(
        store=_reflection_store_factory(), brief_id=req.brief_id
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "reflection_already_active",
                "session_id": existing["id"],
                "current_phase": existing["current_phase"],
            },
        )

    try:
        brief_path = _resolve_brief_path_or_raise(req.brief_id)
    except BriefIdNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "brief_id_not_found", "brief_id": req.brief_id},
        ) from exc

    run_dir: Path | None = None
    if req.run_dir:
        run_dir = Path(req.run_dir)
    elif req.source_run_id is not None:
        run_dir = _resolve_run_dir_for_run_id(req.source_run_id)

    try:
        plan_state = reflection_engine.reflection_phase_plan(
            brief_path=brief_path,
            run_dir=run_dir,
            mode="post_run",
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "reflection_no_evidence",
                "message": str(exc),
            },
        ) from exc

    session = reflection_store.create_reflection_session(
        store=_reflection_store_factory(),
        brief_id=req.brief_id,
        source_run_id=req.source_run_id,
        initial_state=plan_state,
    )
    return _reflection_session_response(session)


# NOTE: /active must be declared BEFORE /{session_id} so the literal
# path matches before the int-typed catch-all.
@router.get(
    "/api/reflection/sessions/active",
    response_model=ReflectionActiveResponse,
)
def get_active_reflection_endpoint(brief_id: str) -> ReflectionActiveResponse:
    """Return the active (non-terminal) reflection for a brief, if any.

    Used by the workspace surface to decide whether to render the
    "Cloris read the market — review what she'd change" pickup card.
    Returns ``session=None`` when there's no active reflection
    (rather than 404) so the frontend doesn't have to distinguish
    error codes from absence.

    Read-only path: routes through
    ``read_models.get_active_reflection_for_brief`` against the
    intake DB (reflection sessions colocate with intake sessions per
    the existing ``_reflection_store_factory = _intake_store``
    aliasing). See the intake list endpoint for the writer-on-read
    rationale.
    """

    from shared.runtime_state import read_models

    session = read_models.get_active_reflection_for_brief(
        _intake_db_path(), brief_id=brief_id
    )
    if session is None:
        return ReflectionActiveResponse(session=None)
    return ReflectionActiveResponse(
        session=ReflectionSession.model_validate(session)
    )


@router.get(
    "/api/reflection/sessions/{session_id}",
    response_model=ReflectionResponse,
)
def get_reflection_session_endpoint(session_id: int) -> ReflectionResponse:
    """Return one reflection session by id, or 404 if missing.

    Used both for in-flight resume (recruiter closes tab and comes
    back) and for short-interval polling during the research phase.
    The endpoint is cheap (single SQLite read) so polling at 2-3s
    intervals is fine — but this is also exactly what makes the
    writer-on-read pattern especially toxic here. Each poll formerly
    rewrote the schema_version meta row; routing through
    ``read_models.get_reflection_session`` keeps the polling honest.
    """

    from shared.runtime_state import read_models

    session = read_models.get_reflection_session(
        _intake_db_path(), session_id=session_id
    )
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "reflection_session_not_found", "id": session_id},
        )
    return _reflection_session_response(session)


@router.patch(
    "/api/reflection/sessions/{session_id}/steering",
    response_model=ReflectionResponse,
)
def patch_reflection_steering_endpoint(
    session_id: int, req: ReflectionSteeringRequest
) -> ReflectionResponse:
    """Add a steering note and re-run the planner phase.

    Each call bumps ``steering_iterations`` by 1. The 3-iteration cap
    is enforced server-side: the 4th attempt returns 409 with
    structured detail so the frontend can surface the
    "you've refined three times — trust the plan or discard" message.

    Empty / whitespace-only notes degenerate to a no-op (the cap
    isn't bumped, the planner isn't re-run). This protects against
    accidental empty-submit clicks.
    """

    session = reflection_store.get_reflection_session(
        store=_reflection_store_factory(), session_id=session_id
    )
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "reflection_session_not_found", "id": session_id},
        )
    if session["current_phase"] != "planning":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "reflection_phase_locked",
                "current_phase": session["current_phase"],
                "message": (
                    "Steering only applies during the planning gate; "
                    "this session has already moved past Gate 1."
                ),
            },
        )

    note = (req.note or "").strip()
    if not note:
        return _reflection_session_response(session)

    if session["steering_iterations"] >= reflection_engine.MAX_STEERING_ITERATIONS:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "reflection_steering_capped",
                "max_iterations": reflection_engine.MAX_STEERING_ITERATIONS,
                "message": (
                    "You've refined this plan three times. "
                    "Trust the plan and start reading, or discard and try again later."
                ),
            },
        )

    state = session["state_json"] or {}
    context = state.get("context") or {}
    history = list(state.get("steering_history") or [])
    notes = [item["note"] for item in history if isinstance(item, dict) and item.get("note")]
    notes.append(note)

    try:
        new_state = reflection_engine.reflection_phase_plan(
            brief_path=context.get("brief_path"),
            run_dir=context.get("run_dir"),
            mode=context.get("mode", "post_run"),
            steering_notes=notes,
        )
    except Exception as exc:
        log.exception(
            "reflection: re-plan failed for session=%s after steering: %s",
            session_id,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "reflection_plan_failed",
                "message": "I lost my train of thought — start the reflection over.",
            },
        ) from exc

    updated = reflection_store.patch_reflection_state(
        store=_reflection_store_factory(),
        session_id=session_id,
        state_json=new_state,
        bump_steering=True,
    )
    if updated is None:
        raise HTTPException(
            status_code=410,
            detail={
                "error": "reflection_session_gone",
                "id": session_id,
            },
        )
    return _reflection_session_response(updated)


def _run_research_in_background(session_id: int) -> None:
    """Background-thread worker for the research + propose phases.

    Reads the session, runs research → propose, persists the result,
    transitions to ``awaiting_diff``. On error, persists
    ``research_error`` and leaves the session in ``researching`` so the
    user can retry (or discard).

    Defensive: if the session was discarded mid-flight, exits without
    further work (the engine call is wasted but the result is dropped).
    Mirrors the plan's edge case 2 ("recruiter discards mid-research").
    """

    store = _reflection_store_factory()
    session = reflection_store.get_reflection_session(
        store=store, session_id=session_id
    )
    if session is None:
        log.warning(
            "reflection: research worker found no session id=%s", session_id
        )
        return

    try:
        researched_state = reflection_engine.reflection_phase_research(
            state=session["state_json"]
        )
    except Exception as exc:
        log.exception(
            "reflection: research phase failed for session=%s: %s",
            session_id,
            exc,
        )
        try:
            reflection_store.patch_reflection_state(
                store=store,
                session_id=session_id,
                research_error=(
                    "Cloris had trouble reaching her sources. "
                    "Try again, or skip the research and propose changes "
                    "from what's already on disk."
                ),
            )
        except ValueError:
            pass  # session went terminal mid-flight
        return

    # Re-read the session — the user may have discarded while research
    # was running. The discard endpoint is idempotent and the patch
    # below will raise ValueError on a terminal session, which we
    # swallow because the discard already won the race.
    current = reflection_store.get_reflection_session(
        store=store, session_id=session_id
    )
    if current is None or current["current_phase"] in {"committed", "discarded"}:
        log.info(
            "reflection: research finished but session id=%s is terminal "
            "(phase=%s); dropping result",
            session_id,
            current["current_phase"] if current else "missing",
        )
        return

    try:
        proposed_state = reflection_engine.reflection_phase_propose(
            state=researched_state
        )
    except Exception as exc:
        log.exception(
            "reflection: propose phase failed for session=%s: %s",
            session_id,
            exc,
        )
        try:
            reflection_store.patch_reflection_state(
                store=store,
                session_id=session_id,
                research_error=(
                    "Cloris read the market but couldn't synthesize the "
                    "findings. Try again or discard."
                ),
            )
        except ValueError:
            pass
        return

    try:
        reflection_store.patch_reflection_state(
            store=store,
            session_id=session_id,
            state_json=proposed_state,
            current_phase="awaiting_diff",
            clear_research_error=True,
        )
    except ValueError:
        # Session went terminal between phases; drop result silently.
        pass


@router.post(
    "/api/reflection/sessions/{session_id}/start_research",
    response_model=ReflectionResponse,
)
def start_reflection_research_endpoint(
    session_id: int, req: ReflectionStartResearchRequest
) -> ReflectionResponse:
    """Approve the plan; kick off research in a background thread.

    State transition: ``planning`` → ``plan_approved`` → (immediately)
    ``researching``. The intermediate ``plan_approved`` state is
    momentary — we transition straight to ``researching`` and spawn
    the worker thread. The frontend polls GET /sessions/{id} every
    2-3s and pivots to Gate 2 when the phase becomes ``awaiting_diff``.
    """

    session = reflection_store.get_reflection_session(
        store=_reflection_store_factory(), session_id=session_id
    )
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "reflection_session_not_found", "id": session_id},
        )
    if session["current_phase"] != "planning":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "reflection_phase_locked",
                "current_phase": session["current_phase"],
                "message": (
                    "Research can only start from the planning gate; "
                    "this session is already past Gate 1."
                ),
            },
        )

    updated = reflection_store.patch_reflection_state(
        store=_reflection_store_factory(),
        session_id=session_id,
        current_phase="researching",
        clear_research_error=True,
    )
    if updated is None:
        raise HTTPException(
            status_code=410,
            detail={"error": "reflection_session_gone", "id": session_id},
        )

    # Spawn the research worker. Daemon thread so it doesn't block
    # process exit if the worker is mid-call when Cloris shuts down
    # (acceptable: the result would be dropped anyway).
    worker = threading.Thread(
        target=_run_research_in_background,
        args=(session_id,),
        name=f"reflection-research-{session_id}",
        daemon=True,
    )
    worker.start()

    return _reflection_session_response(updated)


@router.post(
    "/api/reflection/sessions/{session_id}/commit",
    response_model=ReflectionCommitResponse,
)
def commit_reflection_endpoint(
    session_id: int, req: ReflectionCommitRequest
) -> ReflectionCommitResponse:
    """Apply accepted hunks to the brief; tombstone the session.

    Errors:
      * 404 ``reflection_session_not_found``
      * 409 ``reflection_phase_locked`` — not in awaiting_diff
      * 422 ``reflection_commit_no_hunks`` — accepted_hunk_ids empty
        (the frontend disables the CTA in this case but server enforces)
      * 500 ``reflection_commit_failed`` — write_brief_atomic blew up
    """

    session = reflection_store.get_reflection_session(
        store=_reflection_store_factory(), session_id=session_id
    )
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "reflection_session_not_found", "id": session_id},
        )
    if session["current_phase"] != "awaiting_diff":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "reflection_phase_locked",
                "current_phase": session["current_phase"],
                "message": (
                    "Commit can only happen from the diff gate; "
                    "this session isn't ready for changes yet."
                ),
            },
        )
    if not req.accepted_hunk_ids:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "reflection_commit_no_hunks",
                "message": (
                    "No changes accepted. Discard the reflection or "
                    "approve at least one change before filing."
                ),
            },
        )

    try:
        commit_result = reflection_engine.reflection_commit(
            state=session["state_json"],
            accepted_hunk_ids=req.accepted_hunk_ids,
            edited_hunks=req.edited_hunks or {},
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "reflection_commit_failed",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        log.exception(
            "reflection: commit failed for session=%s: %s", session_id, exc
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "reflection_commit_failed",
                "message": (
                    "I couldn't file the new brief. The previous brief is "
                    "still in place. Try again or discard."
                ),
            },
        ) from exc

    final_state = dict(session["state_json"] or {})
    final_state["commit_result"] = {
        "accepted_hunk_ids": list(req.accepted_hunk_ids),
        "edited_hunk_ids": list((req.edited_hunks or {}).keys()),
        "applied_hunks": commit_result["applied_hunks"],
    }
    committed = reflection_store.commit_reflection(
        store=_reflection_store_factory(),
        session_id=session_id,
        brief_version_path=commit_result["brief_version_path"],
        final_state=final_state,
    )
    if committed is None:
        raise HTTPException(
            status_code=410,
            detail={"error": "reflection_session_gone", "id": session_id},
        )
    return ReflectionCommitResponse(
        session=ReflectionSession.model_validate(committed),
        brief_version_path=commit_result["brief_version_path"],
        applied_hunks=commit_result["applied_hunks"],
    )


@router.post(
    "/api/reflection/sessions/{session_id}/discard",
    response_model=ReflectionResponse,
)
def discard_reflection_endpoint(
    session_id: int, req: ReflectionDiscardRequest
) -> ReflectionResponse:
    """Tombstone the session; brief untouched.

    Idempotent: discarding an already-discarded session returns the
    existing tombstone. Discarding a committed session is also
    idempotent — discard is a no-op against terminal rows. The
    frontend uses this to silently transition out of the reflection
    surface back to the workspace.
    """

    session = reflection_store.get_reflection_session(
        store=_reflection_store_factory(), session_id=session_id
    )
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "reflection_session_not_found", "id": session_id},
        )
    discarded = reflection_store.discard_reflection(
        store=_reflection_store_factory(), session_id=session_id
    )
    if discarded is None:
        raise HTTPException(
            status_code=410,
            detail={"error": "reflection_session_gone", "id": session_id},
        )
    return _reflection_session_response(discarded)
