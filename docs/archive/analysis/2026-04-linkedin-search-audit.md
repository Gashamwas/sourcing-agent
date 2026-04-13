# LinkedIn Search Agent: Search Construction & Adaptation Audit (April 2026 Snapshot)

Historical audit preserved for context. Code line references in this file are point-in-time and may drift as implementation evolves.

## A. Search String Construction

### Where search strings are first created

Search strings originate in `linkedin/strategy.py:form_strategy()` (line 24). This function is called once at the start of `run_full()` (orchestrator.py:363):

```python
self._execution_plan = form_strategy(self.brief_obj, self._kit_strings, prior_data)
```

**Inputs to `form_strategy()`:**
- `brief`: Brief dataclass with role_title, role_description, minimum_bar, archetypes, noise_archetypes, known_noise_patterns, permanent_filters, search_priorities, jd_text, intake_notes, instructions
- `kit_strings`: List of `KitString` objects extracted from Supabase (via `shared/kit_extractor.py:extract_kit_strings()`). Each KitString has: id, block, subblock (Concepts/Methods/Tools), string_type (Recall/Precision), boolean (the actual search terms)
- `prior_run_data`: Optional progress.json from a previous run (for resume context)

**Output:** `ExecutionPlan` dataclass with:
- `strategy_rationale`: Free text explaining the overall approach
- `generated_strings`: Array of compound Booleans with rationale, in priority order
- `coverage_gaps`: Populations not covered by generated strings, with optional executable Booleans
- `noise_predictions`: Terms and collision patterns expected

### How strings are generated

Strings are **freeform LLM-generated** by Opus. There is no template system or mechanical construction. The strategy system prompt (`strategy.py:_build_strategy_system()`, lines 63-238) encodes:

1. **Role context** injected from the brief (title, description, minimum bar, archetypes, noise archetypes, known noise patterns, permanent filters)
2. **Kit vocabulary framing**: Kit strings are explicitly labeled as VOCABULARY ONLY — Opus must synthesize compound Booleans from kit blocks, never execute kit strings directly
3. **String type requirements** (lines 105-128):
   - Type A (Recall): 10-15 strings, broad, 500-5000 results, AND-gate 2-3 skill clusters
   - Type B (Precision/Sniper): 5-15 strings, narrow, 20-500 results, specific tool/framework/benchmark names
4. **Sequencing rule**: Backload RL/RLHF strings to second half; front-load other capability areas
5. **LinkedIn Boolean rules** (lines 129-207): No stemming ("model" ≠ "models"), substring-embedded, case-insensitive, bare generic terms forbidden, abbreviation collision filter, blacklisted terms (PyTorch, TensorFlow, "machine learning", "deep learning", etc.)

The user prompt (`_build_strategy_user()`, lines 241-285) provides:
- Kit strings grouped by block (if available)
- JD text, intake notes, search priorities, sourcing instructions (if no kit)

### String structure

Generated strings are **compound Boolean queries** designed for LinkedIn Recruiter's Keywords field. Example structure (from the prompt instructions):

```
("reward model" OR "reward modeling" OR "reward models") AND ("RLHF" OR "reinforcement learning from human feedback" OR "preference optimization" OR "DPO" OR "PPO")
```

They use parenthetical OR groups connected by AND operators. The agent does NOT use LinkedIn's structured filters (title, company, etc.) for search — only the Keywords textarea plus permanent Field of Study filters applied at session start.

### Pre-built vs. on-the-fly

**All strings are prepared before execution begins.** `form_strategy()` returns the full set of 15-30 compounds plus coverage gap strings. These are queued via `orchestrator.py:_build_ordered_search_strings()` (line 1370):

```python
def _build_ordered_search_strings(self) -> list[SearchString]:
    """Build execution queue from Opus-generated compound strings only."""
    next_id = 1
    ordered: list[SearchString] = []
    batch_size = 5
    # ... compounds batched into groups of 5, coverage gaps appended
```

New strings can only enter the queue through two adaptation mechanisms:
1. **Block-level adaptation** (`adapt_after_block()`, strategy.py:327) — injects new compounds after every ~5 strings
2. **Page-level narrowing** (`_page_adapt()`, orchestrator.py:949) — generates a narrowed Boolean mid-string, but this replaces the current string rather than adding to the queue

### What the brief contributes

The brief provides ALL role-specific content:
- **Capability areas** (7 areas with builder/user signal distinction) — shape what Opus considers "signal" vs "noise"
- **Archetypes** — ideal candidate profiles that strings should surface
- **Noise archetypes** — profiles that look adjacent but aren't (annotation ops, RPA, pure SWE)
- **Known noise patterns** — documented collision terms (e.g., "DPO" → Data Protection Officer)
- **Permanent filters** — Field of Study filter values applied to all searches
- **Search priorities** — which capability areas to front-load

The brief does NOT contain search strings. String construction is entirely autonomous (Opus generates them from kit vocabulary or JD context).

---

## B. Search Execution

### How a search string is physically entered

`linkedin/browser.py:enter_search_string()` (lines 242-318):

```python
async def enter_search_string(self, search_string: str) -> None:
    # 1. Find the Keywords textarea in the left sidebar
    # 2. Expand it if collapsed (click to expand)
    # 3. Fill with the Boolean string
    # 4. Press Enter to execute
```

The method uses multiple selector strategies to locate the Keywords field:
- Primary: `textarea[aria-label="Add keywords"]` or similar
- Fallback: finds the sidebar, locates the "Keywords" label, clicks the associated input

The Boolean goes into the **sidebar Keywords textarea** — NOT the global search bar at the top of LinkedIn. This is enforced by the operational instructions in `agent-workspace/AGENTS.md` (lines 219-267): "Paste booleans ONLY into Keywords filter in left sidebar. NEVER use top navigation search bar."

### Result count checking

After entering a search string, the orchestrator immediately reads the result count:

```python
# orchestrator.py:571-574
result_count_text = await self.browser.get_results_count_text()
result_count = await self.browser.get_results_count()
search_string.result_count = result_count
```

`browser.py:get_results_count()` (line 392) parses the "N RESULTS" text from `.search-query-summary__title`, handling K+ and M+ suffixes. `get_results_count_text()` (line 414) returns the raw text string.

The result count determines the **phase**:
- `result_count >= 3000` → "scout" phase (explore page 1 first, then decide)
- `result_count < 3000` → "paginate" phase (proceed directly)

Guard: if `result_count <= 0`, the string is skipped entirely (orchestrator.py:579-584).

### Results reviewed per search

**A full page is always reviewed.** The per-page loop (orchestrator.py:618-873):

1. `browser.scroll_to_load_all_results()` — forces LinkedIn's lazy-loading to render all ~25 cards
2. `browser.get_results_list_innertext()` — extracts the full page's innerText
3. `extract_snippets_from_list_dom()` — cheap model parses ALL snippets from the page
4. Every non-duplicate snippet is evaluated sequentially

There is no early exit from a page. The only way to skip remaining candidates on a page is if the profile panel gets stuck (line 713-716).

### Data extracted from results list (before clicking profiles)

`shared/extractors.py:extract_snippets_from_list_innertext()` (line 79) uses GPT-4o-mini to parse the results list innerText into `CandidateSnippet` objects:

```python
# Each CandidateSnippet contains:
name, headline, current_title, current_company, location,
education_snippet, profile_url, result_rank, experience_entries
# experience_entries: Array of "Title at Company (dates)" strings
```

Additionally, `browser.get_card_name_url_pairs()` (line 478) extracts name+URL pairs atomically from the DOM (since innerText strips hrefs). These are matched back to snippets by name (orchestrator.py:656-674).

### Scanning vs. evaluating

There is a clear two-stage distinction:

**Stage 1 — Facial Triage** (from snippet data only, no profile open):
- `shared/judger.py:facial_judge()` (line 332) — Opus evaluates the CandidateSnippet
- Uses `linkedin/judgment_templates.py:FACIAL_TRIAGE_TEMPLATE` (line 32) — quick filter checking career trajectory against fast-exit patterns, trajectory YES/NO/AMBIGUOUS patterns
- Decision: FACIAL_YES (open profile) or FACIAL_NO (skip)
- Expected pass-through: 25-60% depending on search quality

**Stage 2 — Full Evaluation** (profile opened, scrolled, read):
- Profile is opened via `browser.open_profile_by_url()` or `open_profile()` (lines 609-721)
- Human-like reading simulated: `browser.simulate_profile_read()` (line 723) — 8-20s of scrolling
- Profile text extracted: `browser.get_profile_innertext()` (line 758) — expands all "read more" sections first
- Structured extraction: `extractors.py:extract_profile_from_innertext()` (line 168) — cheap model parses into CandidateProfileSummary
- Final judgment: `shared/judger.py:full_judge()` (line 388) — Opus evaluates using the full 4-step procedure (sparse profile check, capability mapping, depth test, transferability, decision)

There is also a **Stage 0 — Employer Blacklist** check (no LLM) at the start of `_evaluate_snippet()` (orchestrator.py:1185): if current_company matches `brief.employer_blacklist`, returns FACIAL_NO immediately.

---

## C. Adaptation Loop

### What triggers adaptation

**Page-level adaptation** is triggered after EVERY page completion (orchestrator.py:771):

```python
# After all candidates on a page are evaluated:
adapt_action = await self._page_adapt(
    search_string, current_boolean, result_count_text,
    all_candidates, string_stats,
)
```

This happens unconditionally — there is no threshold or trigger condition. Every page gets an Opus adaptation call.

**Block-level adaptation** is triggered by block name transition (orchestrator.py:407-413):

```python
if search_string.block and search_string.block != current_block:
    if current_block and block_strings:
        await self._run_block_adaptation(
            current_block, block_strings, progress, adapt_after_block
        )
```

Since strings are batched into groups of 5 (via `_build_ordered_search_strings()`), this fires approximately every 5 strings.

### Information passed to page-level adaptation

`_page_adapt()` (orchestrator.py:949-1107) receives and passes to Opus:

**System prompt** (lines 1026-1054):
- Role title and description
- Minimum bar
- Instruction that strings are "nets, not archetype filters"
- Phase-specific action menu (scout vs. paginate)
- LinkedIn Boolean rules for writing refined Booleans

**User prompt** (lines 1056-1074):
```
## Current Boolean
{current_boolean}

## Result Count
{result_count_text}

## Refinement History (if any)
  Original: ...
  Refinement 1: ...
  Current (active): ...

## Accumulated Stats (across N pages)
- Candidates evaluated: X
- Duplicates skipped: X
- SAVES: X
- REJECTS (opened profile, then rejected): X
- Facial YES (opened for full review): X
- Facial NO (skipped from preview): X
- Save rate: X%

## All Candidates So Far
  p1 | save       | Name | Title at Company | rationale[:80]
  p1 | facial_no  | Name | Title at Company | rationale[:80]
  p1 | reject     | Name | Title at Company | rationale[:80]
  ...
```

### Possible adaptation outcomes

**Scout phase** (page 1 of broad strings, result_count >= 3000):
1. `"paginate"` — Page 1 shows good signal. Commit to paginating deeper.
2. `"narrow"` — Too broad/noisy. Opus provides a modified Boolean with added AND clauses.
3. `"abandon"` — Fundamentally wrong results. Skip this string entirely.

**Paginate phase** (ongoing pagination):
1. `"continue"` — Proceed to next page
2. `"narrow"` — Getting noisy. Push current Boolean onto refinement stack, enter narrower one.
3. `"stop"` — Signal exhausted, move to next string
4. `"abandon"` — String is unproductive, skip entirely
5. `"broaden"` — Last narrowing was too aggressive. Pop refinement stack, revert to previous Boolean.

**Minimum pagination enforcement** (orchestrator.py:777-789): If Opus wants to abandon/stop but `page_num < min_pages`, `_force_narrow_adapt()` is called instead — forcing Opus to provide a narrowed Boolean rather than quitting early.

### Adaptation scope

**Page-level adaptation is per-string.** It operates on the current search string's accumulated data. When narrowing/broadening, the page counter and accumulated stats are reset (orchestrator.py:825-828, 852-856):

```python
# On narrow:
page_num = 1
all_candidates.clear()
string_stats = {"pages": 0, "candidates": 0, "duplicates": 0,
                "facial_yes": 0, "facial_no": 0, "saves": 0, "rejects": 0}
```

**Block-level adaptation is per-session.** `adapt_after_block()` (strategy.py:327) sees:
- `block_report`: Summary of completed block's performance (strings_run, total_saves, top_performers, zero_save_string_ids, string_details)
- `remaining_strings`: Queued strings not yet executed
- `kit_vocabulary`: Full kit for synthesizing new compounds

It can: inject new strings, skip remaining strings (mark "skipped"), reorder strings ("next" or "last"), update noise classifications.

**Adaptation cannot happen mid-page.** The per-candidate evaluation loop (orchestrator.py:684-764) runs to completion before `_page_adapt()` is called. The only mid-page exit is the panel-stuck error handler (line 713-716).

### What Opus vs. Haiku sees

| Component | Model | What it receives |
|-----------|-------|-----------------|
| Strategy formation | Opus | Brief (full role context), kit vocabulary, prior run data |
| Snippet extraction | Cheap (GPT-4o-mini) | Raw innerText from results list, search context |
| Facial triage | Opus | Candidate snippet (name, headline, title, company, education, career history), full brief context |
| Profile extraction | Cheap (GPT-4o-mini) | Raw innerText from profile slide-in panel |
| Full evaluation | Opus | Structured profile summary (experiences with bullets, education, skills), full brief context |
| Page adaptation | Opus | Current Boolean, result count, refinement history, accumulated stats, all candidate outcomes |
| Block adaptation | Opus | Block report (aggregate stats), remaining queue, kit vocabulary |
| Force-narrow | Opus | Current Boolean, result count, stats, all candidate outcomes |

### "This approach isn't working" vs. "This string needs tweaking"

**String-level:** `_page_adapt()` handles this via abandon/stop/narrow. Opus sees per-string performance and can kill a string.

**Approach-level:** This does not exist in the code. `adapt_after_block()` operates on block-level aggregates and can modify the queue, but there is no mechanism for Opus to say "the entire search philosophy is wrong — we should switch from broad recall strings to precision sniper strings" or "we're over-indexing on one capability area." The block adapter can inject new strings and skip existing ones, but it doesn't have a concept of "search architecture" to pivot between.

---

## D. Strategy Layer

### What decisions Opus makes

**`form_strategy()`** (strategy.py:24-60):
- Synthesizes 15-30 compound Boolean strings from kit vocabulary or JD context
- Assigns string type (Recall/Precision) and sequencing priority
- Identifies coverage gaps with optional executable Booleans
- Predicts noise patterns and collision terms

**`adapt_after_block()`** (strategy.py:327-411):
- Generates NEW compound strings (synthesized from kit vocabulary + observed patterns)
- Identifies strings to SKIP (redundant/low-signal based on block performance)
- Suggests REORDER of remaining queue ("next" or "last")
- Updates noise classifications (confirmed_signal, confirmed_noise, mixed)

**`_page_adapt()`** (orchestrator.py:949-1107):
- Chooses tactical action for current string (continue/narrow/stop/abandon/broaden/paginate)
- When narrowing, writes a new Boolean with added AND clauses

### When Opus is invoked

| Invocation point | Function | Frequency |
|-----------------|----------|-----------|
| Run start | `form_strategy()` | Once per run |
| Every page | `_page_adapt()` | After each page of results (~25 candidates) |
| Min-pages override | `_force_narrow_adapt()` | When abandon/stop blocked by min pagination |
| Every ~5 strings | `adapt_after_block()` | After block transition |
| Every facial triage | `facial_judge()` | Per candidate (from snippet) |
| Every full evaluation | `full_judge()` | Per candidate that passes facial |

### Opus context

**Strategy formation** receives the richest context:
- Full brief (role, archetypes, noise patterns, known noise, permanent filters, search priorities)
- Complete kit vocabulary grouped by block
- JD text, intake notes, sourcing instructions
- Prior run data (if resuming)

**Page adaptation** receives operational context:
- Role title, description, minimum bar
- Current Boolean and refinement history
- Result count
- All candidate outcomes accumulated across pages (name, title, company, outcome, rationale)
- Running statistics (saves, rejects, facial_yes/no, duplicates, save rate)

**Block adaptation** receives aggregate context:
- Brief (role context)
- Block report (strings run, total saves, top/bottom performers, per-string details)
- Remaining queue (string IDs and truncated Booleans)
- Kit vocabulary (for synthesizing new compounds)

### Output format

All Opus calls use `expect_json=True`. Outputs are structured JSON:

**Strategy:** `{"strategy_rationale": str, "generated_strings": [{boolean, rationale, string_type}], "coverage_gaps": [{gap, suggested_boolean}], "noise_predictions": [{term, collision}]}`

**Page adaptation:** `{"action": str, "rationale": str, "refined_boolean": str|null}`

**Block adaptation:** `{"new_strings": [{boolean, rationale}], "skip_remaining": [str_id], "reorder": [{string_id, position}], "noise_updates": [{term, status}]}`

### Does Opus change approach?

**No.** Opus modifies individual strings (narrow/broaden) and modifies the queue (inject/skip/reorder), but never fundamentally changes the search approach. There is no concept of:
- Switching from broad recall to precision sniper mid-run
- Deciding "we should search by company instead of by skill"
- Recognizing "we're in a sparse market, switch to dragnet" or "we're in a dense market, switch to titration"
- Evaluating whether the string TYPE distribution is optimal

The closest thing is block-level adaptation generating entirely new compounds, but these are generated within the same paradigm — Opus is never asked "is your overall approach working?" only "given these results, what strings should we add/remove?"

---

## E. Hardcoded Constraints

### Constants and thresholds

| Constant | Location | Value | Governs |
|----------|----------|-------|---------|
| `MIN_PAGES_BY_RESULT_COUNT` | shared/config.py:58-67 | [(500, 3), (100, 2), (30, 1), (0, 1)] | Minimum pages before abandon/stop is allowed |
| `MAX_PAGES_PER_STRING` | shared/config.py:49 | 0 (→ 999) | Maximum pages per string (effectively unlimited) |
| `PAGE_DELAY_SECONDS` | shared/config.py:50 | 3.0 | Human-like delay between page loads |
| `PROFILE_DELAY_SECONDS` | shared/config.py:51 | 2.0 | Human-like delay between profile opens |
| `CADENCE_INTERVAL_MINUTES` | shared/config.py:52 | 30 | Anti-detection pause interval |
| `CADENCE_PAUSE_SECONDS` | shared/config.py:53 | 120 | Anti-detection pause duration |
| Scout threshold | orchestrator.py:590 | `result_count >= 3000` | When to enter scout phase vs. paginate directly |
| Block batch size | orchestrator.py:1379 | 5 | Strings per block (triggers block adaptation) |
| Max readmore clicks | browser.py:776 | 15 | Profile "see more" expansion limit |
| Circuit breaker | orchestrator.py:692 | 5 consecutive API errors | Pauses 60s before retrying |
| Chunk threshold | extractors.py:89 | 10KB innertext | When to split snippet extraction into chunks |
| Cards per chunk | extractors.py:51 | 10 | Max candidate cards per extraction chunk |
| Strategy strings | strategy.py:105-128 | 15-30 total (10-15 Recall + 5-15 Precision) | Encoded in Opus system prompt |

### Behaviors that block micro-iteration

1. **Full page review is mandatory.** The evaluation loop (orchestrator.py:684-764) iterates through ALL snippets on a page before adaptation runs. There is no "glance at the page, decide it's noise, reformulate" path.

2. **Adaptation only runs after page completion.** `_page_adapt()` (line 771) is called outside the per-candidate loop. There is no way to break out of evaluation mid-page based on observed patterns.

3. **Snippet extraction is all-or-nothing.** `extract_snippets_from_list_dom()` parses the entire page into snippets in one call. There is no "extract first 5, check quality, decide whether to continue" path.

4. **Scout phase still reviews all of page 1.** Even when `result_count >= 3000` triggers scout mode, page 1 is fully evaluated before the scout→paginate/narrow/abandon decision.

5. **Minimum pagination enforcement.** Even if Opus wants to abandon after page 1, `MIN_PAGES_BY_RESULT_COUNT` can force continued pagination (up to 3 pages for 500+ results).

### Exit conditions for a search session

- All strings in queue processed (status "done" or "skipped")
- `SessionExpired` event set by `session_orchestrator.py` (cooperative check at orchestrator.py:749)
- `GovernorLimitReached` exception from SessionGovernor (hard safety limit)
- `KeyboardInterrupt` (Ctrl+C)
- Browser crash with failed reconnect
- Per-string: Opus says "abandon" or "stop" (and min-pages met), OR no more pages, OR `MAX_PAGES_PER_STRING` reached

---

## F. Gap Analysis

### Where search philosophy selection should be inserted

**Insertion point:** Between `form_strategy()` and `_build_ordered_search_strings()` in `orchestrator.py:363-376`.

Currently:
```python
# orchestrator.py:363
self._execution_plan = form_strategy(self.brief_obj, self._kit_strings, prior_data)
# ...
# orchestrator.py:376
search_strings = self._build_ordered_search_strings()
```

This is where Opus has the maximum downstream impact. A philosophy selection step here would:
1. Receive the brief, kit vocabulary, and market density signals
2. Choose an architecture (sniper, dragnet, titration, negative-space, company-first, title-first)
3. Pass the architecture choice INTO `form_strategy()` as a constraint on string generation
4. Persist the architecture choice in `ExecutionPlan` so adaptation decisions can reference it

Alternatively, philosophy selection could be embedded IN `form_strategy()` itself — the strategy system prompt (`strategy.py:_build_strategy_system()`, lines 63-238) already instructs Opus to generate a mix of Recall and Precision strings. Adding an architecture selection step within this prompt would be a **prompt-only change** — Opus would first declare its architecture, then generate strings consistent with that architecture.

**For approach-level pivoting**, the architecture choice needs to be re-evaluated at block adaptation time. `adapt_after_block()` (strategy.py:327) currently sees block performance but doesn't have an architecture context. Adding the current architecture to its input and allowing it to recommend "switch to architecture X" would enable approach-level pivots.

### Where micro-iteration should be inserted

**Primary insertion point:** Inside the page loop (orchestrator.py:618), AFTER snippet extraction but BEFORE the per-candidate evaluation loop.

Currently:
```python
# orchestrator.py:646-649
snippets = extract_snippets_from_list_dom(innertext, ...)
# orchestrator.py:684 (immediately after URL matching)
for snippet in snippets:
    # ... evaluate each candidate
```

A micro-iteration "glance" step would go between these:

```python
snippets = extract_snippets_from_list_dom(innertext, ...)
# NEW: Glance assessment
glance_decision = await self._glance_assess(snippets, search_string, string_stats)
if glance_decision.startswith("reformulate:"):
    # Skip evaluation, go straight to adaptation with glance data
    ...
elif glance_decision == "early_exit":
    # Systematic miss detected, break page loop
    break
# else: proceed with normal evaluation
```

**Secondary insertion point:** WITHIN the per-candidate evaluation loop, after N candidates. A "mid-page checkpoint" after evaluating 5-10 candidates could trigger early reformulation:

```python
for i, snippet in enumerate(snippets):
    decision = await self._evaluate_snippet(snippet, page_report)
    # ... track outcomes
    if i >= 5 and string_stats["facial_no"] / max(string_stats["candidates"], 1) > 0.8:
        # 80%+ facial_no after 5 candidates — likely systematic miss
        break  # proceed to adaptation
```

**For bidirectional string modification**, the `_page_adapt()` function already supports both narrow (add AND clauses) and broaden (pop refinement stack). The missing piece is feeding glance-level data into `_page_adapt()` before full evaluation, so Opus can reformulate based on what it SEES on the page (titles, companies, headlines) rather than what it evaluates.

### Data available but unused

1. **Result count is not used in strategy formation.** `form_strategy()` generates strings blind — it doesn't know what typical result counts are for this market. If the first 3 strings all return 50K+ results, that's a signal the market is noisy and the approach should be more sniper-oriented. This data becomes available after the first string executes but is never fed back to strategy.

2. **Snippet-level data from results list.** After `extract_snippets_from_list_dom()` runs, the agent has structured data on ALL ~25 candidates (name, headline, current_title, current_company, education, experience_entries). This data is used for individual facial triage but NEVER aggregated for search quality assessment. A "glance" function could analyze the distribution of titles, companies, and headlines to detect systematic mismatches without opening a single profile.

3. **Running save rates per capability area.** The `OpusDecision` from `full_judge()` includes a `path` field with capability area information (e.g., "DIRECT:3. Agentic Systems"). This data is logged per candidate but never aggregated to answer "which capability areas are we finding people for, and which are we missing?"

4. **Facial triage pass rate.** `string_stats["facial_yes"]` and `string_stats["facial_no"]` are tracked and passed to `_page_adapt()`, but the system prompt doesn't explicitly instruct Opus to use this as a string quality signal. A facial_no rate of 90%+ is a strong signal the string is hitting the wrong population, but this isn't called out.

5. **Experience entries from snippets.** The `experience_entries` field on CandidateSnippet contains "Title at Company (dates)" strings for all visible experience. This is richer than current_title/current_company and could reveal patterns like "everyone on this page is a Data Protection Officer" or "everyone is a backend engineer" — useful for micro-iteration without opening profiles.

6. **Refinement depth as a strategy signal.** The `refinement_stack` tracks how many times a string has been narrowed, but this depth is never aggregated across strings to detect "we're narrowing everything, which means our initial strings were all too broad — our approach is wrong."

### What the Opus strategy prompt currently does vs. what it needs

**Currently does:**
- Receives kit vocabulary and brief context
- Generates 15-30 compound Booleans with type (Recall/Precision) and sequencing
- Identifies coverage gaps
- Predicts noise patterns
- At block adaptation: modifies queue (add/skip/reorder), updates noise classifications

**Does NOT do:**
- Select a search architecture or philosophy
- Declare WHY it chose the string mix it did (beyond per-string rationale)
- Set expectations for what "success" looks like at the architecture level
- Define criteria for when the architecture should pivot
- Express a theory about the market (dense/sparse, skill-searchable vs. company-searchable)

**Would need to support philosophy selection:**
1. New field in `ExecutionPlan`: `architecture` (e.g., "sniper", "dragnet", "titration", "negative-space", "company-first", "title-first")
2. Architecture-specific generation constraints in the system prompt (e.g., "You chose 'titration' — generate strings that start maximally broad and systematically narrow")
3. Architecture-specific adaptation heuristics passed to `_page_adapt()` (e.g., "In titration mode, narrow aggressively after each page; in dragnet mode, keep paginating even at low save rates")
4. Architecture re-evaluation at block adaptation: "Given block performance, should we stay with this architecture or switch?"

---

## Recommended Implementation Sequence

### 1. Micro-iteration glance step (highest leverage, moderate structural change)

**What:** After snippet extraction, run a cheap "glance assessment" on the page's titles/headlines/companies before committing to per-candidate evaluation. If the page is dominated by a systematic mismatch (wrong domain, wrong seniority, wrong function), reformulate immediately.

**Where to change:**
- `orchestrator.py:_process_string()` — add glance assessment between snippet extraction (line 649) and evaluation loop (line 684)
- New function `_glance_assess()` — takes snippets and current string context, returns proceed/reformulate/early-exit
- Modify `_page_adapt()` — accept glance-only data (snippet summaries without full evaluation results) as an alternate input mode

**Prompt vs. structural:** Mostly structural (new function, modified control flow), with a new prompt for the glance assessment.

**Why first:** This is the single highest-leverage change. Currently, every page costs 25 candidate evaluations (each involving an Opus facial triage call) before the agent can adapt. A glance step that catches systematic mismatches could save 80%+ of those calls on bad pages, dramatically reducing cost and time per string.

### 2. Mid-page early exit (medium leverage, small structural change)

**What:** After evaluating N candidates (e.g., 5-8), check if the facial_no rate is extreme (>80%) and trigger early adaptation instead of finishing the page.

**Where to change:**
- `orchestrator.py:_process_string()` — add a checkpoint inside the per-candidate loop (after line 744)
- The `_page_adapt()` function can be reused as-is with partial page data

**Prompt vs. structural:** Purely structural — add a conditional break with a threshold check.

**Why second:** This catches the cases where the glance step didn't flag a problem but evaluation reveals systematic mismatches. It's a safety net for the glance assessment.

### 3. Search philosophy layer (high leverage, prompt-heavy change)

**What:** Before generating strings, Opus selects a search architecture (sniper, dragnet, titration, negative-space, company-first, title-first) based on brief characteristics and market signals. The architecture governs string generation parameters and adaptation heuristics.

**Where to change:**
- `strategy.py:_build_strategy_system()` — add architecture selection as the FIRST task before string generation
- `strategy.py:ExecutionPlan` — add `architecture` field
- `strategy.py:adapt_after_block()` — add architecture re-evaluation
- `orchestrator.py:_page_adapt()` — inject architecture-specific adaptation heuristics into the system prompt
- `shared/config.py` — add architecture-specific parameter sets (e.g., min_pages overrides, scout thresholds)

**Prompt vs. structural:** Primarily prompt changes (modify system prompts for form_strategy, adapt_after_block, _page_adapt). Small structural change to add architecture field to ExecutionPlan and thread it through.

**Why third:** The philosophy layer has the broadest downstream impact but also the most risk. It changes how the agent THINKS about search, not just what it does. Implementing it after the micro-iteration loop means the agent already has the mechanical ability to act on philosophy changes (reformulate quickly, exit early), so the philosophy layer has something to drive.

### 4. Approach-level pivoting (high leverage, moderate structural change)

**What:** At block adaptation points, Opus evaluates whether the ENTIRE approach is working — not just individual strings. If aggregate signals (save rate, capability area coverage, narrowing frequency) suggest the architecture is wrong, Opus can recommend switching.

**Where to change:**
- `strategy.py:adapt_after_block()` — add architecture-level assessment to the prompt
- `orchestrator.py:run_full()` — handle architecture pivot response (may require regenerating remaining queue)
- New aggregation logic — compute cross-string statistics (narrowing frequency, save rate by capability area, facial_no rates across strings)

**Prompt vs. structural:** Mixed. New aggregation logic is structural. Architecture pivot handling is structural. The assessment itself is prompt-driven.

**Why last:** This requires all previous changes to be in place. The philosophy layer defines the architecture, the micro-iteration loop provides the rapid feedback data, and this step closes the loop by allowing the architecture itself to change.

### Summary

| Step | Change type | Risk | Leverage | Dependencies |
|------|------------|------|----------|-------------|
| 1. Glance step | Structural + prompt | Medium | Highest | None |
| 2. Mid-page exit | Structural | Low | Medium | None (but pairs with #1) |
| 3. Philosophy layer | Prompt + light structural | Medium | High | None (but #1 and #2 make it actionable) |
| 4. Approach pivoting | Structural + prompt | High | High | #3 required |
