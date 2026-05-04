# Cloris Save Destination Abstraction

Status: ready-to-implement
Owner: Sam
Last updated: 2026-04-29

This spec defines `AbstractSaveDestination`, the interface separating "how a save is recorded" from "what a save means." It enables non-LinkedIn modules to ship without inventing parallel save semantics, and it allows LinkedIn briefs to declare multiple save destinations (LinkedIn Recruiter for the recruiter's working surface, candidate workspace for the Cloris-native surface).

For the architectural commitment, see `Cloris-Architecture-North-Star.md` §9. For the workspace this abstraction primarily writes to, see `docs/cloris-candidate-workspace-spec.md`. For the brief-level declaration mechanism, see `docs/cloris-brief-multi-module-extensions.md`.

## 1. Problem

Today, the LinkedIn module's `SAVE` decision triggers a hardcoded sequence in `linkedin/side_effects.py:handle_save_decision`:

1. Click "Save to Pipeline" in LinkedIn Recruiter via humanized browser interaction.
2. Linger for 8-12 seconds simulating recruiter deliberation.
3. Write side-effect record to `runtime_state.sqlite3:side_effects` with the LinkedIn-specific idempotency key.
4. Append to `<state_dir>/saves.jsonl` artifact.

The GitHub module's `SAVE` decision in `github/side_effects.py` writes to a `saves.jsonl` artifact and optionally generates outreach but does not click anything (no LinkedIn Recruiter equivalent for GitHub).

The two implementations are parallel rather than abstracted. A new module — Researcher, OSS Maintainers — has to invent its own save flow from scratch and either duplicate the parallel logic or short-circuit to a JSONL output that nobody can actually work with.

The fix: an abstract interface, with the existing two behaviors as implementations, and a new `CandidateWorkspaceSaveDestination` that writes to the workspace tables defined in `docs/cloris-candidate-workspace-spec.md`.

## 2. The interface

```python
# shared/save_destination/__init__.py

from abc import ABC, abstractmethod
from typing import Any
from shared.execution.types import CandidateExecutionEnvelope
from shared.schemas import OpusDecision


class AbstractSaveDestination(ABC):
    """Pluggable destination for SAVE-family decisions.

    A module's side-effects service dispatches each SAVE-family decision
    (SAVE, INFERENTIAL_SAVE, TRANSFERABLE_SAVE, SIGNAL_SAVE) to one or
    more destinations declared in the brief. Each destination implements
    its own persistence, side-effect, and idempotency semantics.
    """

    name: str  # canonical destination name; e.g., "linkedin_recruiter", "candidate_workspace"

    @abstractmethod
    def supports(self, brief, source: str) -> bool:
        """Whether this destination is applicable for the given brief + source.

        E.g., LinkedInRecruiterSaveDestination.supports() returns False
        when source != "linkedin", because clicking in Recruiter only
        makes sense for LinkedIn-discovered candidates.
        """

    @abstractmethod
    def save(
        self,
        *,
        envelope: CandidateExecutionEnvelope,
        decision: OpusDecision,
        evidence_payload: dict[str, Any],
        attempt_id: int | None,
    ) -> SaveResult:
        """Record the save. Implementations are responsible for:

        - Idempotency (don't double-save on retry).
        - Side-effect record creation in runtime_state.sqlite3:side_effects.
        - Destination-specific writes (browser click, workspace row, artifact append).
        - Failure handling (return SaveResult.failed on recoverable errors;
          raise on unrecoverable).
        """


@dataclass
class SaveResult:
    destination: str
    status: str  # "succeeded" | "failed" | "skipped"
    side_effect_id: int | None
    payload: dict[str, Any]
    error: str | None = None
```

The interface lives at `shared/save_destination/__init__.py`. Implementations live at `shared/save_destination/<destination_name>.py`.

## 3. Implementations

### 3.1 `LinkedInRecruiterSaveDestination`

Wraps the existing `linkedin/side_effects.py:handle_save_decision` behavior. The refactor is:

- Move the browser-click + linger + idempotency logic out of `linkedin/side_effects.py:handle_save_decision` and into `shared/save_destination/linkedin_recruiter.py:LinkedInRecruiterSaveDestination.save()`.
- `linkedin/side_effects.py` retains the LinkedIn-specific browser interaction primitives but delegates the save-orchestration to the destination.
- `supports()` returns `True` only when `source == "linkedin"` and the brief has a non-empty `linkedin_project`.
- The browser instance is injected via the orchestrator at destination instantiation; the destination does not manage the browser lifecycle.

This is a behavior-preserving extraction (per `plans/_template.md:25` — "prefer behavior-preserving extraction over new abstraction when feasible"). The LinkedIn save behavior must be byte-identical post-refactor; existing tests in `tests/test_linkedin_pipeline.py` are the regression gate.

### 3.2 `CandidateWorkspaceSaveDestination`

Writes a `workspace_entries` row per `docs/cloris-candidate-workspace-spec.md` §3.

- `supports()` returns `True` for any source, any brief.
- `save()` writes the workspace entry, generates outreach copy if the module supports it (calls `<module>.outreach.generate_outreach` when available), records the side effect.
- Idempotency: `UNIQUE(brief_id, candidate_id)` on the workspace table prevents double-rows. Re-saves are no-ops (return `SaveResult.skipped`).

### 3.3 `CSVExportSaveDestination` (optional, future)

Writes a CSV row to a per-brief export file. Useful for ATS handoff workflows. Not required in v1; included as an example of how destinations extend.

### 3.4 `WebhookSaveDestination` (optional, future)

POSTs to a configured webhook URL. Useful for customer-side automation. Not required in v1.

## 4. Brief-level declaration

A brief declares its save destinations in `shared/brief_schema.py:Brief.save_destinations: list[str]`. Default is `["linkedin_recruiter", "candidate_workspace"]` for LinkedIn briefs and `["candidate_workspace"]` for non-LinkedIn briefs (set by the brief loader based on `target_modules`).

```python
@dataclass
class Brief:
    # ...existing fields...
    save_destinations: list[str] = field(default_factory=lambda: ["candidate_workspace"])
```

The brief loader hydrates `save_destinations` from V2 brief JSON. If the field is missing, the default is set based on `target_modules`:

- If `target_modules == ["linkedin"]`: `["linkedin_recruiter", "candidate_workspace"]`.
- Otherwise: `["candidate_workspace"]`.

Custom destinations can be added per brief (e.g., `["candidate_workspace", "csv_export"]`) without code changes.

## 5. Dispatch logic

The orchestrator's side-effects service iterates over the brief's declared destinations on each SAVE-family decision:

```python
# in <module>/side_effects.py

def handle_save_decision(
    self,
    *,
    envelope: CandidateExecutionEnvelope,
    decision: OpusDecision,
    evidence_payload: dict,
    attempt_id: int | None,
) -> list[SaveResult]:
    results = []
    for destination in self._save_destinations:
        if not destination.supports(self._brief, envelope.source):
            results.append(SaveResult(
                destination=destination.name,
                status="skipped",
                side_effect_id=None,
                payload={"reason": "not_supported_for_source"},
            ))
            continue
        try:
            result = destination.save(
                envelope=envelope,
                decision=decision,
                evidence_payload=evidence_payload,
                attempt_id=attempt_id,
            )
            results.append(result)
        except Exception as exc:
            # Destination errors do not block other destinations; log and continue.
            self._safety.record_save_destination_failure(...)
            results.append(SaveResult(
                destination=destination.name,
                status="failed",
                side_effect_id=None,
                payload={},
                error=str(exc),
            ))
    return results
```

`self._save_destinations` is constructed at orchestrator init from the brief's `save_destinations` list and a registry of available destinations (in `shared/save_destination/registry.py`).

## 6. Idempotency contract

Every destination is responsible for its own idempotency:

- **LinkedIn Recruiter** — uses `idempotency_key = f"linkedin_save:{candidate_url}:{brief_state_key}"`. Existing `runtime_state.sqlite3:side_effects` `UNIQUE(candidate_id, effect_type, idempotency_key)` enforces. A retry of the same save produces a no-op (`status="skipped"`).
- **Candidate Workspace** — `UNIQUE(brief_id, candidate_id)` on `workspace_entries`. Retry is a no-op.
- **CSV Export / Webhook** — destination-specific keys; retry must be safe.

The shared `runtime_state.sqlite3:side_effects` table records every destination's outcome via `begin_candidate_side_effect` / `complete_candidate_side_effect` (existing pattern in `shared/runtime_state/store.py`).

## 7. Failure handling

Destination failures are isolated. A LinkedIn Recruiter save that fails (browser disconnected, save button not found) does not prevent the candidate workspace save. The dispatch loop logs the failure, records it via `RunSafetyCoordinator`, and continues to the next destination.

If all destinations fail, the orchestrator records the candidate's `terminal_decision` as `SAVE` (the judgment is unchanged) but the side-effect status is `failed`. The recruiter is informed via the run review surface ("This candidate was judged a save but the destination write failed; details: ..."). Manual recovery is available via `tools/runtime_state_admin.py`.

## 8. Migration and rollout

Phase 1 (`plans/multi-module-foundation.md`) ships the abstraction:

1. Define `AbstractSaveDestination` and `SaveResult` at `shared/save_destination/__init__.py`.
2. Implement `LinkedInRecruiterSaveDestination` at `shared/save_destination/linkedin_recruiter.py` by extracting the existing `linkedin/side_effects.py:handle_save_decision` logic. Update `linkedin/side_effects.py` to delegate.
3. Implement `CandidateWorkspaceSaveDestination` at `shared/save_destination/candidate_workspace.py`.
4. Add `save_destinations` field to `Brief` schema. Brief loader hydration.
5. Add `_save_destinations` construction in orchestrators (LinkedIn, GitHub).
6. Update `linkedin/side_effects.py:handle_save_decision` to dispatch via destinations.
7. Update `github/side_effects.py:handle_full_decision` to dispatch via destinations.
8. Test contract: existing LinkedIn save behavior is byte-identical; new workspace writes verified.

Rollback: revert step 6+ to point back at the legacy save-orchestration code paths; the legacy paths remain intact during the phase-1 ship (deletion is deferred until ~Phase 2 once the abstraction is proven).

## 9. Open questions

- **Per-decision destination overrides.** Should a brief be able to send `INFERENTIAL_SAVE` to the workspace only (not LinkedIn Recruiter, since the recruiter wants to manually verify before pushing into the pipeline)? Probably yes, v2. V1: all SAVE-family decisions dispatch to all destinations.
- **Destination ordering.** Currently the dispatch order is the order in `save_destinations`. If LinkedIn Recruiter fails, the workspace still saves. Reverse order would prioritize workspace consistency over LinkedIn Recruiter. V1: brief-declared order; v2: configurable.
- **Cross-destination consistency.** If LinkedIn Recruiter save succeeds and workspace save fails, the candidate is in LinkedIn Recruiter but not in the Cloris workspace. The recruiter sees the discrepancy in Run Review. V1: tolerated (each destination is independent). V2: optional consistency mode.

## 10. Decisions captured here

- 2026-04-29 — `AbstractSaveDestination` is the canonical interface for all save destinations. New destinations implement the interface, not parallel logic in module side-effects.
- 2026-04-29 — Briefs declare their destinations in `save_destinations: list[str]`. Defaults set by brief loader based on `target_modules`.
- 2026-04-29 — Destinations are isolated. One destination's failure does not block others.
- 2026-04-29 — LinkedIn behavior is byte-identical post-refactor; tests in `tests/test_linkedin_pipeline.py` are the regression gate.
- 2026-04-29 — V1 supports `LinkedInRecruiterSaveDestination` and `CandidateWorkspaceSaveDestination`. CSV/webhook destinations are documented as extension points but not implemented.
