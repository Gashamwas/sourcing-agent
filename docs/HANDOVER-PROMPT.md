# Task: Remove pre-Opus hard filters + Implement autonomous search evolution

You are modifying an existing Python pipeline at `~/multi-model-pipeline/`. The pipeline connects to a Chrome browser via CDP, reads LinkedIn Recruiter search results, extracts candidate data with a cheap model (GPT-4o-mini), and sends structured snippets to Claude Opus for evaluation. It is working end-to-end — tests pass, live browser test completed successfully.

**Do as much as you can on both tasks before asking me anything.** Read every file in `docs/` and `config/` first. The reference materials are authoritative.

---

## Task 1: Remove pre-Opus hard filter layer

### Decision (already made — do not revisit)

The hard filter layer (`hard_filters.py`) is being removed. It was built around the Brazil FDL brief's patterns (annotation companies, RPA titles) and broke immediately when we switched to the Head of AI Lab brief. The cost math doesn't justify it: Opus facial calls are ~200 tokens per candidate, ~$0.15 for a full page of 25. The expensive calls are full profile reads (~1500 tokens), and Opus already gates those effectively — on the first live test, 25 candidates → 4 facial YES → 4 profiles opened → 0 saves. The facial judgment IS the filter.

### Changes required

1. **Delete `hard_filters.py`** entirely.

2. **Update `orchestrator.py`:**
   - Remove `from hard_filters import hard_filter` import
   - Remove the hard filter step from `_evaluate_snippet()` — candidates go straight from extraction to Opus facial judgment
   - Remove `hard_filtered` from stats tracking
   - Remove hard filter references from page reports and run summary
   - Remove the `brief` parameter being passed to `hard_filter()` calls

3. **Update `test_extractors.py`:**
   - Remove all hard filter tests (test_hard_filter_annotation_company, test_hard_filter_rpa, test_gate1_*, test_gate3_*, etc.)
   - Keep the judger prompt generation tests — those still matter
   - Add a test confirming that `orchestrator.py` does NOT import `hard_filters`

4. **Update `run.py`:**
   - Remove any hard_filter references in the rejudge flow if present

5. **Verify:** `python3 -m pytest test_extractors.py -v` passes, `python3 -c "from orchestrator import Pipeline"` works, no references to `hard_filters` remain in any `.py` file.

---

## Task 2: Implement autonomous search evolution

### Context

The pipeline currently works in two modes:
- `--test-single-page`: reads whatever's on screen, evaluates candidates
- `--rejudge-from`: re-runs Opus on existing extractions

It cannot yet: load a search kit, enter Boolean strings, paginate, or adapt its search strategy. This task builds that capability.

### Architecture

```
Brief (JSON) ──→ Opus: Strategy Formation ──→ Execution Plan (JSON)
                                                    │
Search Kit (extracted strings) ─────────────────────┘
                                                    │
                                                    ▼
                                    ┌───────────────────────────┐
                                    │   EXECUTION LOOP          │
                                    │                           │
                                    │   For each string:        │
                                    │   1. GPT-4o-mini enters   │
                                    │      Boolean into LI      │
                                    │   2. GPT-4o-mini extracts │
                                    │      candidate snippets   │
                                    │   3. Opus facial judgment  │
                                    │   4. Opus full judgment    │
                                    │   5. Save/skip            │
                                    │   6. Log results          │
                                    │                           │
                                    │   After each block:       │
                                    │   → Report to Opus        │
                                    │   → Opus adapts plan      │
                                    └───────────────────────────┘
```

### What to build

#### A. Kit Extractor (`kit_extractor.py` — new file)

The Search Kit Library is a Next.js app at `search-kit-library.vercel.app/kit/{id}`. Each kit has:
- Multiple **blocks** (e.g., "Post-Training & RLHF", "RL Environments", "Agent Development")
- Each block has **subblocks**: Concepts, Methods, Tools
- Each subblock has **Recall** strings (broad OR-groups) and **Precision** strings (narrow AND-gated terms)
- Each string is a Boolean parenthetical

The kit extractor must:
1. Navigate to the kit URL in the browser (the same Chrome instance connected via CDP)
2. Wait for the React app to render
3. Expand all sections (blocks → subblocks → Recall/Precision)
4. Extract every Boolean string with its metadata: block name, subblock (Concepts/Methods/Tools), type (Recall/Precision), and the Boolean text
5. Return a structured list that maps to the `SearchString` schema in `schemas.py`

**Implementation approach:** Use the browser (Playwright via CDP, same as the LinkedIn automation) to navigate to the kit URL. Use `page.inner_text()` or the cheap model to parse the rendered page. The kit page is public — no auth needed. The cheap model is ideal here: send it the page text, ask it to extract all Boolean strings with their block/subblock/type metadata as JSON.

**The brief has the kit reference:**
- Brazil brief: `"kit_url": "https://search-kit-library.vercel.app/kit/527ad0b5-6b37-481b-a75c-414c45ee503a"`
- Head of AI Lab brief: `"search_kit_id": "10c0183e-f28b-49a0-b10f-680c73ab6fba"` (construct URL: `https://search-kit-library.vercel.app/kit/{id}`)

Add a helper in `kit_extractor.py` that resolves either format to a URL.

#### B. Strategy Formation (`strategy.py` — new file)

After the kit is extracted, Opus receives:
1. The full brief (role description, minimum_bar, archetypes, noise_archetypes, known_noise_patterns)
2. The full kit structure (all strings organized by block/subblock/type)
3. Any prior run data if resuming (string performance from progress file)

Opus returns an **execution plan** as JSON:
```json
{
  "strategy_rationale": "Why this ordering and these priorities",
  "phases": [
    {
      "phase": 1,
      "name": "High-signal precision blocks",
      "strings": [
        {"string_id": 5, "priority": "high", "note": "SWE-bench — highly discriminating"},
        {"string_id": 12, "priority": "high", "note": "RLHF + language model compound"}
      ]
    },
    {
      "phase": 2,
      "name": "Broad recall with noise patterns",
      "strings": [
        {"string_id": 1, "priority": "medium", "note": "Post-training recall — expect DPO noise in Brazil"},
      ]
    }
  ],
  "skip_strings": [
    {"string_id": 45, "reason": "Generic SWE vocabulary — will match every engineer"}
  ],
  "noise_predictions": [
    {"term": "DPO", "expected_collision": "Data Protection Officer in Brazil", "mitigation": "Check for LGPD context"}
  ]
}
```

The strategy call is ONE Opus call at the start of a run. It costs ~3000-5000 tokens (brief + kit summary). This replaces the human step of manually ordering strings and predicting noise.

#### C. Adaptation Loop (modify `orchestrator.py`)

After completing each **block** (not each string — that's too frequent), the orchestrator sends Opus a summary:
```
Block "Post-Training & RLHF" complete.
- 8 strings run, 3 produced saves
- 5 strings produced zero results or all noise
- Top performers: String #2 "preference optimization" (3 saves from 41 results), String #5 "RLHF + language model" (2 saves from 28 results)
- Zero-save strings: #1, #3, #4, #6, #8
- Noise patterns observed: DPO → Data Protection Officer (3 occurrences), "post training" → L&D professionals (7 occurrences)
- New signal observed: "GRPO" appeared on 2 saved profiles
```

Opus responds with adaptations:
```json
{
  "new_strings": [
    {"boolean": "(\"GRPO\" OR \"group relative policy optimization\") AND (\"LLM\" OR \"language model\")", "rationale": "GRPO appearing on saved profiles — worth a targeted search"}
  ],
  "skip_remaining": [
    {"string_id": 22, "reason": "Same generic SWE vocabulary as zero-save strings in this block"}
  ],
  "reorder": [
    {"string_id": 30, "move_to": "next", "reason": "Based on GRPO signal, embodied AI strings may surface similar frontier profiles"}
  ],
  "noise_updates": [
    {"term": "GRPO", "status": "confirmed_signal", "note": "High-precision term for post-training practitioners"}
  ]
}
```

This is the Session 7A behavior from the article, systematized. The agent diagnosed Coding Precision failures and built replacement strings. This makes that a loop.

#### D. Full Run Mode (modify `orchestrator.py` and `run.py`)

Wire it all together into a `run_full()` method:

1. Load brief
2. Extract kit (kit_extractor)
3. Form strategy (strategy.py → Opus)
4. Create progress file
5. Execute strings in strategy order:
   - Enter Boolean into Keywords field (browser.py)
   - Paginate through results (browser.py)
   - Extract → facial → profile → full judgment (existing flow)
   - Log per-string results to progress file
6. After each block completes → adaptation call (strategy.py → Opus)
7. Apply adaptations: add new strings, skip flagged strings, reorder
8. Continue until all phases complete
9. Generate final report

`run.py` changes:
- `--full-run` flag (or make it the default when `--test-single-page` is not set)
- `--kit-url` now actually triggers kit extraction instead of printing a stub message
- `--resume` flag loads existing progress file and skips completed strings

#### E. Update `schemas.py`

Add schemas for:
- `ExecutionPlan` — the strategy output
- `BlockReport` — the per-block summary sent to Opus
- `AdaptationResponse` — Opus's mid-run adjustments
- `KitString` — extracted string with block/subblock/type metadata

#### F. Update `browser.py`

Add the missing methods that the full run needs:
- `enter_search_string(boolean)` — already exists but needs the correct selector (`input[aria-label*="keyword" i]`), verify it works
- `clear_keywords()` — clear the Keywords field only (NOT "Clear Search" which wipes all filters). Use the dedicated "Clear" button next to the Keywords field.
- `apply_permanent_filters(filters)` — set Location, Field of Study, etc. from the brief. This is complex UI automation — implement what you can, stub the rest with clear TODOs and console logging.
- `get_result_count()` — parse the "N RESULTS" text from the page
- `go_to_next_page()` / `has_next_page()` — verify `button[aria-label="Next"]` works

### Reference: DOM selectors (verified)

All in `docs/linkedin-recruiter-dom-map.md`. Key ones:
- Results list: `ol.profile-list`
- Result card: `article.profile-list-item`
- Keywords input: `input[aria-label*="keyword" i]`
- Clear keywords: the "Clear" button adjacent to Keywords section (NOT "Clear search" at bottom)
- Save button: `button.save-to-pipeline__button` (NOT the dropdown trigger)
- Pagination: `button[aria-label="Next"]`, `button[aria-label="Previous"]`
- Profile slide-in: `div.profile.profile-slidein__profile`
- Profile main: `div.profile__main-container`
- Result count: text containing "N RESULTS" near top

### Reference: SKILL.md execution workflow

Read `docs/SKILL-reference.md` Phase 1 and Phase 2 for how the OpenClaw agent extracted strings and executed searches. The pipeline should replicate this flow programmatically.

### Reference: Protocol.md reporting format

Read `docs/protocol-reference.md` for the page report format. The console output should match this structure: header, page overview, saved candidates (detailed), skipped candidates (opened, detailed), skipped from preview (grouped), running totals.

---

## Task 3: Standardize brief JSON schema

### Problem

The two real briefs use incompatible schemas. The pipeline code must handle both — and any future brief — with a single code path. Currently:

| Field | Brazil brief | Head of AI Lab brief |
|-------|-------------|---------------------|
| ID | `"name": "fdl-brazil"` | `"brief_id": "head-applied-ai-lab-nyc"` |
| Kit reference | `"kit_url": "https://search-kit-library.vercel.app/kit/..."` | `"search_kit_id": "10c0183e-..."` (no URL) |
| Role description | `"description": "..."` | `"role_summary": "..."` |
| Evaluation | `"evaluation": {"save_threshold": ..., "experience_floor": {...}}` | `"minimum_bar": {"years_experience": 15, "technical_depth": ..., "bfsi_domain": ...}` |
| Archetypes | `"archetypes": [{name, pattern, save_signals, skip_signals}]` | `"sweet_spot": {"archetypes": ["string descriptions"]}` |
| Skip rules | `"hard_skips": ["string"]`, `"clear_skips_from_review": ["string"]` | `"hard_skips": ["string"]`, `"clear_skips_from_review": [{pattern, reason, example}]` |
| Filters | `"permanent_filters": {"Location": "Brazil"}` | `"permanent_filters": {"location": "...", "seniority": [...], "years_experience": "15-30"}` |
| Save instructions | `"save_instructions": {method, destination, notes}` | `"linkedin_project": "...", "linkedin_project_id": "..."` |

### Changes required

1. **Create `brief_loader.py`** — a normalization layer that reads any brief and returns a standardized `Brief` dataclass:

```python
@dataclass
class Brief:
    id: str
    role_title: str
    role_description: str
    kit_url: str  # Always a full URL, constructed from search_kit_id if needed
    linkedin_project: str
    linkedin_project_id: str
    minimum_bar: str  # Unified text description
    archetypes: list[dict]  # Normalized: always [{name, pattern, save_signals, skip_signals}]
    noise_archetypes: list[dict]  # [{name, description, signals}]
    hard_skips: list[str]
    clear_skips_from_review: list[str]  # Flattened to strings if originally dicts
    known_noise_patterns: list[dict]
    permanent_filters: dict
    save_instructions: dict
    experience_floor: dict
    # Strategy hints (new — for autonomous search evolution)
    search_priorities: list[str]  # Optional: block ordering hints from the user
    noise_predictions: list[dict]  # Optional: known noise patterns specific to this geography/role
    raw: dict  # The original JSON, preserved for Opus prompts that need the full context
```

2. **Normalize both briefs on load.** The loader maps each brief's idiosyncratic field names to the standard schema. Examples:
   - `brief.get("name") or brief.get("brief_id")` → `Brief.id`
   - `brief.get("kit_url") or f"https://search-kit-library.vercel.app/kit/{brief.get('search_kit_id')}"` → `Brief.kit_url`
   - `brief.get("description") or brief.get("role_summary")` → `Brief.role_description`
   - Head of AI Lab's `"sweet_spot": {"archetypes": ["string descriptions"]}` → convert to `[{"name": "Sweet Spot Archetype 1", "pattern": "string description", "save_signals": [], "skip_signals": []}]`
   - Head of AI Lab's `"clear_skips_from_review": [{pattern, reason, example}]` → flatten to `["pattern: reason"]`

3. **Update all modules to use `Brief` dataclass** instead of raw dict access:
   - `judger.py`: use `brief.archetypes`, `brief.minimum_bar`, etc.
   - `orchestrator.py`: use `brief.kit_url`, `brief.linkedin_project`, etc.
   - `strategy.py`: use `brief.role_description`, `brief.archetypes`, `brief.noise_predictions`, etc.
   - `kit_extractor.py`: use `brief.kit_url`

4. **Update both real brief files** (`config/brief-brazil-real.json` and `config/brief-head-ai-lab-real.json`) to add missing fields needed by the new architecture. Where the brief doesn't have a field, add it with sensible defaults:
   - Add `"kit_url"` to Head of AI Lab brief (constructed from search_kit_id)
   - Add `"linkedin_project"` and `"linkedin_project_id"` to Brazil brief if missing
   - Add `"save_instructions"` to Head of AI Lab brief
   - Do NOT restructure the briefs to match each other — the loader handles normalization. Adding missing fields is fine; renaming existing fields breaks backward compatibility with OpenClaw.

5. **Add tests:**
   - Load Brazil brief → verify all Brief fields populated
   - Load Head of AI Lab brief → verify all Brief fields populated
   - Verify `kit_url` is a valid URL for both
   - Verify `archetypes` is a list of dicts with `name` and `pattern` keys for both

---

### Do NOT build
- WhatsApp integration (out of scope)
- LinkedIn login automation (user logs in manually)
- CAPTCHA solving

### Quality bar
- All existing tests pass (minus the deleted hard filter tests)
- `python3 -c "from orchestrator import Pipeline"` works
- `python3 run.py --brief config/brief-brazil-real.json --test-single-page` still works
- Both briefs load through `brief_loader.py` with all fields populated and no KeyErrors
- Kit extraction works against both kit URLs in the briefs
- Strategy formation produces a valid ExecutionPlan from both briefs
- `--full-run` enters at least one string, paginates, and evaluates candidates end-to-end

### Deliverables
Print a summary of:
1. Files created/changed and why
2. What works end-to-end
3. What's stubbed/TODO
4. Recommended test sequence for live browser validation
