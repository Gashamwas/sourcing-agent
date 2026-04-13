# Engineering Spec: M0-M1 for Reviewed-Candidate Memory + HITL Outreach

This spec covers only:
- **M0**: contracts and storage spine
- **M1**: reviewed-memory capture and historical backfill

It does **not** implement:
- same-market run-time lookup behavior
- recruiter outreach import flows
- market-intel consumption
- semantic/RAG retrieval

## Summary
Ship the minimum durable substrate for reviewed-candidate memory without changing LinkedIn run behavior yet.

The core outcome of M0-M1 is:
- every successful LinkedIn full Opus review writes an exact-profile reviewed-memory record
- historical LinkedIn full reviews can be backfilled into the same memory store
- a market-level artifact is materialized at:
  - `output/market_intelligence/<market-key>/reviewed-candidate-memory.jsonl`

The key design decision for this phase is:
- **reviewed memory gets its own canonical global store**

It should **not** live only inside the existing per-project `runtime_state.sqlite3`, because same-market memory must work across LinkedIn project IDs.

## Canonical Storage Design

### Global reviewed-memory DB
Create a dedicated reviewed-memory SQLite DB at:

`output/state/linkedin_reviewed_memory/runtime_state.sqlite3`

Add a helper in `/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/shared/output_paths.py`:

- `resolve_linkedin_reviewed_memory_db_path(*, output_root: str | Path | None = None) -> Path`

Implementation:
- parent dir = `source_state_root("linkedin_reviewed_memory", output_root=output_root)`
- db path = `<parent>/runtime_state.sqlite3`

This DB may reuse `RuntimeStateStore`, but it is a **separate store instance** from any per-project LinkedIn state DB.

### New table
Add this table to `/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/shared/runtime_state/store.py` migration path and bump the schema version from `3` to `4`.

```sql
CREATE TABLE IF NOT EXISTS reviewed_candidate_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    market_key TEXT NOT NULL,
    identity_key TEXT NOT NULL,
    profile_url TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    origin_brief_id TEXT NOT NULL DEFAULT '',
    origin_project_id TEXT NOT NULL DEFAULT '',
    full_decision TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    decision_path TEXT NOT NULL DEFAULT '',
    source_string_id TEXT NOT NULL DEFAULT '',
    profile_summary_json TEXT NOT NULL DEFAULT '{}',
    full_decision_json TEXT NOT NULL DEFAULT '{}',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    first_reviewed_at TEXT NOT NULL,
    last_reviewed_at TEXT NOT NULL,
    last_run_id INTEGER,
    last_work_unit_id INTEGER,
    last_attempt_id INTEGER,
    UNIQUE(source, market_key, identity_key)
);
```

Add indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_reviewed_candidate_memory_market_recent
ON reviewed_candidate_memory(source, market_key, last_reviewed_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_reviewed_candidate_memory_origin_project
ON reviewed_candidate_memory(source, origin_project_id, identity_key);
```

### Column meanings
- `source`: always `"linkedin"` in this phase
- `market_key`: derived from the brief via the existing market-key logic
- `identity_key`: exact candidate identity; for LinkedIn this must equal `profile_url`
- `origin_brief_id`: stable normalized brief slug; use `brief_obj.id` when available, else brief path stem
- `origin_project_id`: LinkedIn project ID / current LinkedIn runtime `brief_id`
- `full_decision`: terminal full-review decision such as `SAVE`, `REJECT`, `INFERENTIAL_SAVE`
- `confidence`: copied from `OpusDecision.confidence`
- `decision_path`: copied from `OpusDecision.path`
- `source_string_id`: string ID that produced the candidate in the originating run
- `profile_summary_json`: full serialized `CandidateProfileSummary`
- `full_decision_json`: full serialized `OpusDecision`
- `provenance_json`: JSON object with `run_id`, `attempt_id`, `work_unit_id`, and `reviewed_at`
- `first_reviewed_at`: first time this exact profile was recorded in this market
- `last_reviewed_at`: latest full review time for this exact profile in this market

## Public/Internal Interfaces

### New constants
Add to `/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/shared/contracts.py`:
- `LINKEDIN_OUTREACH_FEEDBACK_EFFECT_TYPE = "linkedin_outreach_feedback"`
- `LINKEDIN_OUTREACH_FEEDBACK_STATUSES = {"reached_out", "not_reached_out_low_quality", "not_reached_out_capacity_or_timing"}`

M0-M1 only freezes the vocabulary; it does **not** implement the importer yet.

### RuntimeStateStore API additions
Add these methods to `/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/shared/runtime_state/store.py`:

- `upsert_reviewed_candidate_memory(...) -> int`
- `get_reviewed_candidate_memory(*, source: str, market_key: str, identity_key: str) -> dict | None`
- `list_reviewed_candidate_memory(*, source: str, market_key: str | None = None, origin_project_id: str | None = None, identity_key: str | None = None, limit: int | None = None) -> list[dict]`
- `get_reviewed_candidate_memory_batch(*, source: str, market_key: str, identity_keys: list[str]) -> dict[str, dict]`

Exact signature for `upsert_reviewed_candidate_memory`:

```python
def upsert_reviewed_candidate_memory(
    self,
    *,
    source: str,
    market_key: str,
    identity_key: str,
    profile_url: str,
    display_name: str,
    origin_brief_id: str,
    origin_project_id: str,
    full_decision: str,
    confidence: float,
    decision_path: str,
    source_string_id: int | str | None,
    profile_summary: dict | None,
    full_decision_payload: dict,
    provenance: dict | None,
    reviewed_at: str,
    run_id: int | None,
    work_unit_id: int | None,
    attempt_id: int | None,
) -> int:
    ...
```

Upsert rules:
- unique key is `(source, market_key, identity_key)`
- on first insert:
  - set both `first_reviewed_at` and `last_reviewed_at` to `reviewed_at`
- on conflict:
  - preserve the existing `first_reviewed_at`
  - overwrite all other mutable fields with the new snapshot
  - set `last_reviewed_at` to `reviewed_at`

### Reviewed-memory service module
Add a new module:

`/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/shared/runtime_state/reviewed_memory.py`

It should own:
- creation of the global reviewed-memory store
- path resolution for market artifacts
- capture helpers
- backfill helpers
- artifact rebuild helpers

Expose:
- `open_linkedin_reviewed_memory_store(*, output_root: str | Path | None = None) -> RuntimeStateStore`
- `resolve_reviewed_candidate_memory_artifact_path(*, market_key: str, output_root: str | Path | None = None) -> Path`
- `record_linkedin_reviewed_candidate(...) -> int`
- `backfill_linkedin_reviewed_candidate_memory(...) -> dict`
- `rebuild_reviewed_candidate_memory_artifact(...) -> Path`

### Bridge constructor changes
Update `/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/shared/runtime_state/linkedin.py` so `LinkedInRuntimeStateBridge.__init__` accepts:

- `market_key: str`
- `origin_brief_id: str`
- `reviewed_memory_store: RuntimeStateStore | None = None`

Final signature:

```python
def __init__(
    self,
    *,
    store: RuntimeStateStore,
    output_dir: str | Path,
    brief_id: str,
    brief_name: str,
    market_key: str,
    origin_brief_id: str,
    reviewed_memory_store: RuntimeStateStore | None = None,
):
```

Behavior:
- if `reviewed_memory_store` is `None`, open the global reviewed-memory DB using the output root derived from `output_dir`
- store `market_key` and `origin_brief_id` on the bridge

### Full-review capture hook
In `/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/shared/runtime_state/linkedin.py`, extend `finish_stage_success(...)`:

- after the existing runtime-state write completes
- if `stage == "full"`
- and `snippet.profile_url` is non-empty

call a new bridge helper:

- `record_reviewed_candidate_memory(...)`

Exact behavior:
- build `reviewed_at` from the decision timestamp helper already used in the bridge
- write one exact-profile reviewed-memory snapshot into the global reviewed-memory store
- then rebuild the market artifact for `self.market_key`

No reviewed-memory writes should happen for:
- `stage == "facial"`
- missing `profile_url`
- failed full-review attempts

### Output/artifact changes
Add to `/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/shared/runtime_state/artifacts.py`:

- `ArtifactContract("reviewed-candidate-memory.jsonl", ArtifactOwnership.PROJECTION_OWNED, "Projected reviewed-candidate memory")`

Artifact write path:

`output/market_intelligence/<market-key>/reviewed-candidate-memory.jsonl`

Projection format per line:

```json
{
  "profile_url": "/talent/profile/ada",
  "candidate_name": "Ada Lovelace",
  "market_key": "forward_deployed_engineer__new_york__ic5_ic6",
  "origin_brief_id": "forward-deployed-engineer-us-v1.4",
  "origin_project_id": "1990251114",
  "full_decision": "SAVE",
  "confidence": 0.93,
  "decision_path": "direct_experience",
  "source_string_id": 16,
  "reviewed_at": "2026-04-13T02:13:00+00:00",
  "headline": "Forward Deployed Engineer at Example",
  "rationale": "Strong direct evidence across deployment-heavy roles.",
  "skills_snippet": ["Python", "LLMs", "Deployment"]
}
```

Projection rules:
- newest records first by `last_reviewed_at DESC, id DESC`
- `headline` comes from `profile_summary_json.headline`
- `rationale` comes from `full_decision_json.rationale`
- `skills_snippet` comes from `profile_summary_json.skills_snippet`

## Command Surface

Add a new admin tool:

`/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/tools/reviewed_candidate_memory_admin.py`

### Command 1: Inspect
```bash
python3 tools/reviewed_candidate_memory_admin.py inspect \
  --market-key <market-key> \
  [--identity-key <profile-url>] \
  [--limit 100]
```

Behavior:
- opens the global reviewed-memory store
- prints JSON rows
- filters by `market_key` and optional `identity_key`

### Command 2: Backfill
```bash
python3 tools/reviewed_candidate_memory_admin.py backfill \
  --brief /absolute/path/to/brief.json \
  [--state-dir /absolute/path/to/output/state/linkedin/<project-key>] \
  [--run-id <runtime-run-id>] \
  [--dry-run]
```

Behavior:
- resolves the LinkedIn project state dir from `--brief` if `--state-dir` is omitted
- opens the per-project LinkedIn `runtime_state.sqlite3`
- derives the `market_key` from the brief
- backfills all eligible full-review records for:
  - the specific run if `--run-id` is provided
  - otherwise every LinkedIn run in that state DB for that project
- writes to the global reviewed-memory store
- rebuilds the market artifact unless `--dry-run`

Backfill eligibility rules:
- candidate has a terminal full-review decision
- candidate identity key / profile URL is non-empty
- candidate attempt payload includes a full decision payload

Backfill output:
- `inserted`
- `updated`
- `skipped_missing_profile_url`
- `skipped_missing_full_decision`
- `market_key`
- artifact path

## Implementation Steps

### Step 1: Paths and contracts
- add output-path helper for the global reviewed-memory DB
- add artifact contract for `reviewed-candidate-memory.jsonl`
- add outreach feedback constants to `shared/contracts.py`
- update `tests/test_phase0_contracts.py` to freeze the new vocabulary

### Step 2: Store migration
- bump runtime-state schema version to `4`
- add the new table + indexes in `RuntimeStateStore.initialize()`
- add CRUD/batch methods for reviewed memory

### Step 3: Reviewed-memory service
- create `shared/runtime_state/reviewed_memory.py`
- centralize:
  - global store opening
  - market artifact path resolution
  - projection writer
  - backfill orchestration

### Step 4: LinkedIn bridge capture
- extend `LinkedInRuntimeStateBridge` constructor with `market_key` and `origin_brief_id`
- update all bridge instantiations and tests
- hook reviewed-memory capture into full-stage success only

### Step 5: Backfill/admin tooling
- add `tools/reviewed_candidate_memory_admin.py`
- implement `inspect` and `backfill`
- keep all writes idempotent

## Exact Test Plan

### New test file
Add:

`/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/tests/test_reviewed_candidate_memory.py`

Cover:
- global reviewed-memory DB path resolution
- table migration exists and schema version is `4`
- insert path writes one new reviewed-memory row
- upsert preserves `first_reviewed_at` and updates `last_reviewed_at`
- batch lookup returns a dict keyed by `profile_url`
- projection writes newest-first market artifact

### Extend existing LinkedIn runtime-state tests
Update:

`/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/tests/test_linkedin_runtime_state.py`

Add:
- full-stage success writes reviewed-memory record
- facial-stage success does not write reviewed-memory record
- missing `profile_url` never writes reviewed-memory record
- bridge constructor accepts `market_key` and `origin_brief_id`
- reviewed-memory artifact is rebuilt after full-stage success

### Add admin/tool tests
Add:

`/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/tests/test_reviewed_candidate_memory_admin.py`

Cover:
- `inspect` prints filtered rows
- `backfill --dry-run` reports counts without writing
- `backfill` from a temp LinkedIn runtime DB seeds the global reviewed-memory store
- rerunning backfill is idempotent

### Extend output-path/artifact tests
Update:
- `/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/tests/test_output_paths.py`
- `/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/tests/test_phase0_contracts.py`

Add assertions for:
- reviewed-memory DB path helper
- artifact classification for `reviewed-candidate-memory.jsonl`
- frozen outreach-feedback status vocabulary

## Acceptance Criteria
- Fresh LinkedIn full reviews create one exact-profile reviewed-memory record in the global store.
- Historical LinkedIn full reviews can be backfilled without duplicates.
- The per-market `reviewed-candidate-memory.jsonl` artifact is always derivable from the canonical store.
- No existing LinkedIn sourcing behavior changes in M0-M1.
- Same-project dedupe remains untouched.

## Defaults and Non-Goals
- Identity is exact `profile_url` only.
- `identity_key == profile_url` for all LinkedIn reviewed-memory records in this phase.
- The global reviewed-memory store is canonical; per-project runtime DBs are sources for capture/backfill only.
- No same-market auto-skip or advisory lookup is enabled yet.
- No recruiter outreach import exists yet; only the constants are reserved in this phase.
