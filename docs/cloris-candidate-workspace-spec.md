# Cloris Candidate Workspace Spec

Status: ready-to-implement
Owner: Sam
Last updated: 2026-04-29

The candidate workspace is the Cloris-native saved-candidate surface. It is the destination for non-LinkedIn module saves, the working surface where recruiters review and act on saves across modules, and the integration point for the closed feedback loop that drives the platform's compounding evaluation quality.

This spec defines the workspace's data model, UI surface, API endpoints, and integration with the existing Cloris UI surfaces. The implementation plan is in `plans/multi-module-foundation.md` (Slice 6).

For why this exists, see `Cloris-Architecture-North-Star.md` §9 (save destination abstraction) and `Cloris-Product-North-Star.md` §9 (closed feedback loop). For the save destination interface this workspace implements, see `docs/cloris-save-destination-abstraction.md`. For the cross-module identity layer the workspace surfaces, see `docs/cloris-cross-module-identity-resolution-spec.md`.

## 1. Problem and goal

Today, "SAVE" for the LinkedIn module means the orchestrator clicks "Save to Pipeline" in LinkedIn Recruiter and writes a row to `runtime_state.sqlite3:candidates`. The recruiter's working surface for those saves is LinkedIn Recruiter itself.

For non-LinkedIn modules — Researcher, OSS Maintainers, Defense, Designer, Healthcare — there is no LinkedIn Recruiter to click. Saves currently land in `output/state/<source>/<brief_state_key>/saves.jsonl` and the recruiter has nowhere inside Cloris to actually work the candidates: no list, no notes, no outreach tracking, no manual review marks, no cross-module aggregation.

This is a shipping blocker. A non-LinkedIn module that "produces saves" without a working surface for those saves ships engineering but not product.

The goal: a Cloris-native workspace that holds saved candidates from any source, presents them as editorial candidate cards with the recruiter context they need to act, supports recruiter notes and outreach status tracking, and integrates with the closed feedback loop so review marks propagate back to the brief.

## 2. Scope and non-goals

### 2.1 Scope

- **Saved-candidate aggregation across sources for one brief.** The workspace is brief-scoped. Saves from any source targeting that brief land in the same workspace.
- **Editorial candidate cards** following the visual primitives in `docs/cloris-ui-spec.md:271-279`.
- **Recruiter notes and outreach status tracking** at the candidate level, source level, and person level (once cross-module identity resolution lands).
- **Manual review marks** for HITL flow (e.g., Designer's `surface_type: "hitl_visual_review"` candidates).
- **Outreach copy** rendered from `<module>/outreach.py` generators (existing pattern in `github/outreach.py`).
- **Read access for the Run Review surface** so a run's saves appear inline in the run summary.

### 2.2 Non-goals

- **Outreach automation** — sending emails, drip campaigns, sequenced outreach. Out of scope per `Cloris-Product-North-Star.md` §3.
- **ATS integration** — exporting candidates to Greenhouse/Lever/Workday. Optional CSV export only; no API integration in v1.
- **Cross-brief aggregation** — the workspace is brief-scoped. A candidate the recruiter saved for two different briefs appears as two workspace entries (one per brief). Cross-brief candidate views are deferred.
- **Candidate communication history** — the workspace tracks outreach *status* (sent, replied, declined), not the message content. Message content lives in the recruiter's email/messaging tool.
- **Recruiter collaboration features** — multi-recruiter assignments, internal notes-on-notes. Cloris is single-recruiter v1.

## 3. Data model

The workspace adds three tables to `shared/runtime_state/store.py` via the canonical migration path. Schemas are additive; existing tables and lifecycle invariants are unchanged.

### 3.1 `workspace_entries`

The primary workspace row. One per (brief, candidate) pair. Created when a save destination dispatch writes to the workspace.

```sql
CREATE TABLE IF NOT EXISTS workspace_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id TEXT NOT NULL,
    candidate_id INTEGER NOT NULL,
    person_id INTEGER,                          -- nullable; populated after cross-module identity resolution
    surface_type TEXT NOT NULL DEFAULT 'save', -- 'save' | 'hitl_visual_review' | 'manual_review' | 'inferential_save'
    save_decision TEXT NOT NULL,                -- 'SAVE' | 'INFERENTIAL_SAVE' | 'TRANSFERABLE_SAVE' | 'SIGNAL_SAVE'
    save_confidence REAL,
    save_rationale TEXT NOT NULL DEFAULT '',
    save_path TEXT NOT NULL DEFAULT '',         -- e.g., 'DIRECT:1. Capability Area Name'
    review_status TEXT NOT NULL DEFAULT 'unreviewed',  -- 'unreviewed' | 'confirmed' | 'rejected' | 'borderline'
    review_marked_at TEXT,
    outreach_status TEXT NOT NULL DEFAULT 'none',  -- 'none' | 'queued' | 'sent' | 'replied' | 'declined'
    outreach_marked_at TEXT,
    recruiter_notes TEXT NOT NULL DEFAULT '',
    contextualization_payload_json TEXT NOT NULL DEFAULT '{}',  -- HITL context for visual review modules
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(brief_id, candidate_id),
    FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
    FOREIGN KEY(person_id) REFERENCES person(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_workspace_brief
    ON workspace_entries(brief_id, review_status, outreach_status);
```

Notes on the schema choices:

- `candidate_id` is the foreign key into the existing `candidates` table; the workspace doesn't duplicate candidate identity, it points at it.
- `person_id` is nullable because cross-module identity resolution may not have run yet, or may not have produced a confident match. Run Review handles unresolved entries by displaying them as per-source rows; once `person_id` is populated, the entry merges into a person card.
- `surface_type` distinguishes regular saves from HITL visual-review candidates (Designer module) and other future review surfaces. `hitl_visual_review` is the Designer module's canonical value.
- `review_status` is the recruiter's mark after seeing the saved candidate. The closed feedback loop reads this — `confirmed` saves and `rejected` saves both feed brief revision proposals.
- `outreach_status` is a state machine: `none → queued → sent → replied | declined`. Cloris does not send the outreach itself; the recruiter marks the status.
- `contextualization_payload_json` carries module-specific context that doesn't fit the standard candidate evidence model. For Designer's HITL flow it carries `portfolio_url`, `specialization_summary`, `tool_depth_assessment`. Other modules may extend it.

### 3.2 `workspace_review_events`

Append-only event log for review actions. Drives the feedback artifact for Next Run Learning.

```sql
CREATE TABLE IF NOT EXISTS workspace_review_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_entry_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,            -- 'review_marked' | 'outreach_status_changed' | 'note_added' | 'note_edited'
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(workspace_entry_id) REFERENCES workspace_entries(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workspace_review_events_entry
    ON workspace_review_events(workspace_entry_id, created_at);
```

Notes:

- Append-only by convention; never updated. UI edits to notes write a new `note_edited` event with the diff.
- The events feed `shared/brief_iteration.py:862-910`'s context builder when generating brief revision proposals.

### 3.3 `workspace_outreach_artifacts`

Optional outreach copy stored per workspace entry. Populated when the module generates outreach (e.g., `github/outreach.py:generate_outreach`).

```sql
CREATE TABLE IF NOT EXISTS workspace_outreach_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_entry_id INTEGER NOT NULL,
    generator_module TEXT NOT NULL,      -- 'github' | 'researcher' | etc.
    template_version TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(workspace_entry_id) REFERENCES workspace_entries(id) ON DELETE CASCADE
);
```

Read-only from the recruiter's perspective in v1. The recruiter copies the body, edits it in their email tool, and sends it. Future versions may allow editing in place; not v1.

## 4. Save destination integration

The workspace implements `AbstractSaveDestination` per `docs/cloris-save-destination-abstraction.md`. The implementation:

- `CandidateWorkspaceSaveDestination.save(envelope, decision, payload)` writes a `workspace_entries` row.
- `surface_type` is derived from the decision and any module-specific flags. `SAVE` → `surface_type = "save"` by default; `surface_type = "hitl_visual_review"` when the payload contains `{"surface_type": "hitl_visual_review"}` (Designer module).
- `INFERENTIAL_SAVE` and other save-family decisions populate `surface_type = "inferential_save"`, `surface_type = "transferable_save"`, etc., so the UI can render them differently.
- Outreach generation, if the module supports it, runs after the workspace entry is written and populates `workspace_outreach_artifacts`.

LinkedIn briefs typically declare `save_destinations: ["linkedin_recruiter", "candidate_workspace"]` so saves land in both LinkedIn Recruiter and the Cloris workspace; non-LinkedIn briefs declare `save_destinations: ["candidate_workspace"]` only.

## 5. UI surface

### 5.1 Workspace view

The workspace view is a top-level Cloris UI route accessed from Ambient Home and from any Run Review surface. URL: `/brief/<brief_state_key>/workspace`.

Layout (per `docs/cloris-ui-spec.md:96-128` editorial primitives):

- **Section header** (top of page): brief name, brief role title, `target_modules` badges, save count, review status counts (unreviewed / confirmed / rejected / borderline).
- **Filter row** (sticky): module filter (all sources / specific source), review-status filter, outreach-status filter, search by name.
- **Candidate list** (main content): editorial cards per workspace entry. Sort options: most recent save, highest confidence, alphabetical, by source.
- **Empty state**: when the workspace has no entries, prose-style message ("No saves yet for this brief. Run a discovery pass to populate the workspace.") with a primary action button to launch a run.

### 5.2 Editorial candidate card

Per workspace entry. The card layout uses `docs/cloris-ui-spec.md:271-279`'s candidate-entry primitive.

Above the fold:

- **Name** (Fraunces serif, large).
- **Source badge(s)** (mono metadata, inline) — `linkedin`, `researcher`, `github+maintainer`, etc. Multi-source badges appear when `person_id` resolves multiple candidates.
- **Confidence + decision pill** — `SAVE 0.84`, `INFERENTIAL_SAVE 0.42`, etc., color-coded by confidence band.
- **Path** — the matching capability area (`DIRECT:1. Post-Training and RLHF Pipelines`). Mono.
- **Save rationale** (Fraunces, 1-2 sentence prose).
- **Surface type indicator** — for HITL entries (Designer's `hitl_visual_review`), a "Pending Visual Review" prose banner per `docs/cloris-ui-spec.md:267-268`.

Below the fold (expandable):

- **Evidence section** — module-specific. For LinkedIn: profile URL, current title/company, top experience entries. For Researcher: ORCID, top papers, h-index, current affiliation. For Maintainer: top maintained packages with download counts, GitHub profile URL. For Designer: portfolio URL prominent, specialization summary, notable project descriptions, tool depth assessment.
- **Cross-source identity** — if `person_id` is set, list of other source candidates merged into this person.
- **Recruiter notes** — editable text field. Saves on blur via `PATCH /api/workspace/entry/{id}`.
- **Review marks** — buttons: "Confirm", "Reject", "Borderline", "Reset". Saves immediately and writes a `workspace_review_events` row.
- **Outreach** — outreach status buttons (`Queue → Sent → Replied | Declined`), outreach copy if generated (read-only render of `workspace_outreach_artifacts.body`), copy-to-clipboard action.

### 5.3 Run Review integration

Each run's review surface (`docs/cloris-ui-spec.md:218-232`) shows the run's saves inline. The integration is read-only from Run Review into the workspace:

- Run Review queries `workspace_entries WHERE brief_id = ? AND candidate_id IN (run.saved_candidate_ids)`.
- Saved candidates render with the same editorial card primitive as in the workspace view.
- A "View in workspace" link on each card jumps to the workspace view scoped to that brief.
- Review marks made from Run Review write to the workspace tables (same backend) so the workspace view reflects them.

There is no separate "run-scoped saves" data model; the workspace is the saves data model.

### 5.4 Person-first rendering when cross-module identity resolution lands

Once `docs/cloris-cross-module-identity-resolution-spec.md` ships, candidates that resolve to the same `person_id` collapse into a single editorial card. The card shows:

- **Name** — canonical name from the `person` row.
- **Source badges** — every source that surfaced this person, with confidence per source.
- **Aggregated evidence** — evidence sections from each source rendered in tabs or stacked sections.
- **Highest-confidence save** drives the primary decision pill; lower-confidence saves are rendered as supplementary signals.

Pre-resolution, candidates render per-source. The transition is visual only — the data model already supports both states (`person_id` is nullable).

## 6. API endpoints

All endpoints are under `cloris/api.py`. Read endpoints are public to the local Cloris UI; write endpoints accept the standard local-API auth (none in v1, future hardening).

### 6.1 Read

- **`GET /api/workspace/{brief_state_key}`** — list workspace entries for a brief. Query params: `module=`, `review_status=`, `outreach_status=`, `search=`, `sort=`, `limit=`, `offset=`. Returns paginated `WorkspaceEntry` Pydantic models.
- **`GET /api/workspace/{brief_state_key}/entry/{entry_id}`** — full detail for one entry, including evidence, recruiter notes, review event history, outreach artifact.
- **`GET /api/workspace/{brief_state_key}/persons`** — list workspace entries grouped by `person_id` (post-resolution), with unresolved entries as singleton groups.

### 6.2 Write

- **`PATCH /api/workspace/entry/{entry_id}`** — update `review_status`, `outreach_status`, `recruiter_notes`. Writes a `workspace_review_events` row for each changed field.
- **`POST /api/workspace/{brief_state_key}/entry`** — internal-use creation endpoint called by `CandidateWorkspaceSaveDestination`. Not exposed to the frontend (modules write through the save destination interface, not the API).
- **`DELETE /api/workspace/entry/{entry_id}`** — soft-delete (writes a `review_status='deleted'` event, hides from default views). Hard-delete reserved for admin tooling.

### 6.3 Read models

`cloris/models.py` adds:

```python
class WorkspaceEntrySummary(BaseModel):
    id: int
    brief_id: str
    source: Literal["linkedin", "github", "researcher", "designer", ...]
    surface_type: Literal["save", "hitl_visual_review", "manual_review", "inferential_save", ...]
    save_decision: str
    save_confidence: float | None
    save_path: str
    save_rationale: str
    review_status: Literal["unreviewed", "confirmed", "rejected", "borderline", "deleted"]
    outreach_status: Literal["none", "queued", "sent", "replied", "declined"]
    display_name: str
    profile_url: str
    person_id: int | None
    created_at: str
    updated_at: str

class WorkspaceEntryDetail(WorkspaceEntrySummary):
    evidence: dict  # module-specific, source-keyed
    contextualization_payload: dict
    recruiter_notes: str
    review_events: list[WorkspaceReviewEvent]
    outreach_artifact: WorkspaceOutreachArtifact | None
    cross_source_candidates: list[WorkspaceEntrySummary]  # populated when person_id is set
```

## 7. Feedback loop integration

The Next Run Learning surface (`docs/cloris-ui-spec.md:235-249`) consumes workspace review events via `shared/brief_iteration.py`. The flow:

1. Recruiter reviews workspace entries; marks `confirmed`, `rejected`, `borderline`.
2. Each mark writes a `workspace_review_events` row.
3. After a run completes, the brief iteration context builder reads the run's review events plus the candidate's evidence and decision rationale. Builds a feedback summary.
4. Brief revision proposal is generated, presented in the Next Run Learning surface.
5. Recruiter approves the revision; next run uses the revised brief.

The closed loop is the platform's long-term moat (`Cloris-Product-North-Star.md` §9). Workspace review events are the input to the loop. Without the workspace, the loop has no input.

## 8. Migration and rollout

The workspace ships in Phase 1 (`Cloris-Multi-Module-Roadmap.md` Phase 1, Slice 6 of `plans/multi-module-foundation.md`). Migration is forward-only:

- New SQLite tables added via `_migrate` in `shared/runtime_state/store.py`.
- Existing LinkedIn briefs gain `save_destinations: ["linkedin_recruiter", "candidate_workspace"]` by default (back-fill via brief loader hydration; existing briefs without the field get the default).
- Existing LinkedIn `SAVE` decisions back-fill workspace entries on next run start. (No replay of historical saves; only future saves populate the workspace.)
- Cloris UI gains the workspace route. Run Review surface gains the inline workspace integration.

Rollback strategy: the workspace tables are isolated. Disabling the workspace route in the UI hides it; the data is retained. Reverting the `CandidateWorkspaceSaveDestination` registration stops new writes. No data loss.

## 9. Open questions

- **Bulk operations.** Should the workspace support batch review-marking (e.g., "Confirm all candidates from this run")? V1: no. V2: probably.
- **Saved searches and views.** Should recruiters be able to save filter combinations as named views? V1: no. V2: yes if customers ask.
- **Cross-brief duplicate alerts.** When a recruiter saves a candidate for one brief and the same person was previously saved for a different brief, should the workspace surface that? Useful but adds cross-brief query complexity. Defer to v2.
- **Outreach copy editing in place.** V1: copy-to-clipboard, edit elsewhere. V2: in-app editing if customers ask.
- **Multi-recruiter collaboration.** Out of scope per §2.2; revisit if customer pull emerges.

## 10. Decisions captured here

- 2026-04-29 — Workspace is brief-scoped. Cross-brief candidate views deferred to v2.
- 2026-04-29 — Workspace tables are additive to `runtime_state.sqlite3`; not a separate database.
- 2026-04-29 — `workspace_review_events` is append-only and is the canonical input to the closed feedback loop via `shared/brief_iteration.py`.
- 2026-04-29 — Outreach status is recruiter-marked, not Cloris-marked. Cloris generates copy, recruiter sends.
- 2026-04-29 — `surface_type` field accommodates HITL flows (Designer's `hitl_visual_review`) without inventing new decision values.
- 2026-04-29 — Person-first rendering is a UI presentation concern; data model supports both pre- and post-resolution states via nullable `person_id`.
