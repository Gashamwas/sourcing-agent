# Task: Build the multi-model LinkedIn Recruiter sourcing pipeline

You are building a Python pipeline that replaces a single-model AI sourcing agent (OpenClaw + Claude Opus) with a cost-efficient two-model architecture. A cheap model (GPT-4o-mini or Gemini Flash) handles all browser automation and DOM extraction. Opus handles only candidate evaluation. The goal is to cut Opus token usage by ~90%.

## Project location
~/multi-model-pipeline/

This folder contains a scaffold with the right overall architecture but wrong implementation details. You will fix and complete it. Do NOT start from scratch — preserve the module structure (schemas, config, storage, orchestrator pattern) and fix what's broken.

## Reference materials (READ ALL BEFORE WRITING CODE)

Read these files first. They are the authoritative source for how the system should work:

1. `docs/linkedin-recruiter-dom-map.md` — Verified CSS selectors and DOM structure for LinkedIn Recruiter. Every selector in browser.py is wrong. This file has the correct ones.
2. `docs/SKILL-reference.md` — The OpenClaw agent's instructions. This defines the execution workflow, evaluation gates, filter application, and error recovery that the pipeline must replicate.
3. `docs/protocol-reference.md` — The WhatsApp communication protocol. The pipeline must send status updates via WhatsApp (or at minimum, structured console output that matches this format).
4. `docs/PREFLIGHT-reference.md` — Forbidden actions and allowed clicks. The pipeline must respect these constraints.
5. `docs/mistakes-reference.md` — Documented failure modes from prior agent sessions. The pipeline must not repeat these.
6. `config/brief-brazil-real.json` — The real Brazil FDL sourcing brief with 5 archetypes, 5 noise archetypes, 7 noise patterns, 4-gate evaluation, and specific save instructions. This is the canonical example of what a brief looks like.
7. `config/brief-head-ai-lab-real.json` — The Head of Applied AI Lab brief. Proves the system must be brief-agnostic — evaluation logic comes from the brief, not hardcoded prompts.
8. `config/evaluation-rubric.json` — An older rubric. The real briefs supersede this. The judger must load evaluation criteria from the brief, not from a separate rubric file.

## Critical bugs to fix first

1. **Hyphenated filenames.** `llm-clients.py`, `hard-filters.py`, `test-extractors.py` cannot be imported. Rename to `llm_clients.py`, `hard_filters.py`, `test_extractors.py`.
2. **run.py imports `from pipeline import Pipeline`** — the class is in `orchestrator.py`. Fix the import.
3. **Rubric path mismatch.** `judger.py` loads `Path(__file__).parent / "rubric.json"` which doesn't exist. The rubric is at `config/evaluation-rubric.json`. But more importantly, the judger should load evaluation criteria from the BRIEF, not a separate rubric. The brief is the single source of truth.

## Architecture

```
Search Kit URL → [Fetch kit, extract strings]
  ↓
For each string:
  → [Cheap model: enter Boolean into Keywords field]
  → [Read ol.profile-list innerText per card]
  → [Hard filters: gates 1-3 from brief]
  → For candidates passing hard filters:
    → [Cheap model: extract snippet from card innerText] → CandidateSnippet
    → [Opus: facial judgment on snippet] → FACIAL_YES / FACIAL_NO
    → If FACIAL_YES:
      → [Click candidate name → profile slide-in opens]
      → [Cheap model: extract profile from div.profile__main-container innerText] → CandidateProfileSummary
      → [Opus: full judgment on profile summary] → SAVE / REJECT
      → If SAVE: [click button.save-to-pipeline__button in profile panel]
      → [Navigate back to results or click Next candidate]
  → [Update progress file]
  → [Send page report]
→ Next string
```

## What to fix in each module

### browser.py — Rewrite selectors, fix profile navigation model
- Results list: `ol.profile-list`, items: `article.profile-list-item`
- Keywords input: `input[aria-label*="keyword" i]` (NOT placeholder-based)
- Save button: `button.save-to-pipeline__button` (NOT generic "Save" text match — the dropdown trigger `save-to-pipeline__dropdown-trigger` must NOT be clicked)
- Pagination: `button[aria-label="Next"]` and `button[aria-label="Previous"]`
- Profile is a SLIDE-IN PANEL, not a page navigation. Clicking a candidate name link opens `div.profile-slidein__container` as an overlay. `open_profile()` should click the name link, not `page.goto()`. `go_back_to_results()` should close/dismiss the panel or press back, not assume a new page loaded.
- Profile container: `div.profile.profile-slidein__profile` → `div.profile__main-container`
- Profile prev/next: `button.skyline-pagination-button`
- Result count: parse "N RESULTS" text from page
- Add innerText extraction methods: `get_card_innertext(card_index)` and `get_profile_innertext()`
- Add retry logic: 3 retries with 5-second waits on any browser action failure (per SKILL.md error recovery)
- Add filter application: method to set Field of Study and Location filters from the brief's permanent_filters
- FORBIDDEN actions (from PREFLIGHT): never click "Clear Search" / "Clear All", never click "Similar Profiles", never use the top nav search bar, never click the AI search chat textarea

### extractors.py — Use innerText, not HTML
- The cheap model receives card innerText (clean, labeled, ~300-500 tokens) or profile innerText (sectioned, ~2000-4000 tokens after trimming)
- Do NOT send raw HTML to the cheap model. Send innerText only.
- Trim profile innerText: only include header lockup + Summary + Experience + Education sections. Skip Accomplishments, Volunteer Experience, Personal Information, Similar Profiles, tabs.
- The extraction prompts are fine structurally. Update them to expect innerText format instead of HTML/DOM.

### hard_filters.py — Implement all 4 gates from the brief
Current code only covers gate 2 (hard_skips — annotation companies, skip titles). Add:
- Gate 1: minimum_bar check — BUILD vs USE distinction. If headline/title clearly indicates application-layer work (LangChain, RAG, prompt engineering, RPA) with no training infrastructure signal, skip. This is a cheap text match, not an LLM call.
- Gate 3: clear_skips_from_review — patterns from the brief's `clear_skips_from_review` array. These need slightly more signal than gate 2 (e.g., "fintech ML at Nubank doing credit scoring" requires checking company + title + headline together).
- Load gate definitions from the brief at runtime, not hardcoded. Different briefs have different gates.
- Gate 4 (archetype match) stays with Opus — that's the whole point.

### judger.py — Brief-driven, not hardcoded
- Remove the hardcoded FACIAL_SYSTEM and FULL_SYSTEM prompts that mention specific role details ("partner with researchers at OpenAI, Anthropic, and DeepMind...")
- Instead, build prompts dynamically from the brief: role description, minimum_bar, archetypes with save_signals and skip_signals, noise_archetypes, known_noise_patterns, experience_floor
- Load the brief once at Pipeline init, pass it to the judger
- The facial judgment prompt should include: minimum_bar, hard_skips, archetypes (names + patterns only — not full signals), noise_archetypes (names + descriptions)
- The full judgment prompt should include: everything above PLUS full archetype save_signals and skip_signals, experience_floor, capability_areas
- Keep the JSON response format (decision, path, confidence, rationale)

### orchestrator.py — Add resilience and reporting
- Import fix: hard_filters not hard-filters
- Add structured console output matching protocol.md format: per-page reports with header, overview, saved candidates (detailed), skipped candidates (detailed), skipped from preview (grouped), running totals
- Add progress file format matching OpenClaw's actual format (see the progress files in config/ — they use `block`, `domain`, `cluster` fields, and `decisions` array with per-candidate logs)
- Add resume capability: detect existing progress file, skip completed strings
- Add Ctrl+C handler: save progress immediately on interrupt
- The dedup check reads the entire snippets JSONL on every candidate — this is O(n²). Load the set once per string, update in memory.

### config.py — Add brief path
- Add BRIEF_PATH config option
- Add NODE_TLS_REJECT_UNAUTHORIZED=0 note for Turing corporate proxy

### run.py — Fix import, add kit loader stub
- Fix `from pipeline import Pipeline` → `from orchestrator import Pipeline`
- Add a `--kit-url` flag that accepts a Search Kit Library URL. For now, just validate the URL format and print a message that the kit loader is not yet implemented. The kit fetcher is a separate task (it requires navigating to search-kit-library.vercel.app and extracting strings from the React page).

### test_extractors.py — Uncomment and wire up
- Uncomment the existing test cases
- Add a test for hard_filters with the Brazil brief's gate definitions
- Add a test for judger prompt generation from a brief

## Do NOT build
- WhatsApp integration (that requires OpenClaw's messaging layer — out of scope)
- Search Kit Library fetcher (complex — separate task)
- Filter application UI automation (complex — separate task, mark as TODO)
- Automatic retry/reconnect for CDP connection drops (mark as TODO with the pattern from SKILL.md error recovery)

## Quality bar
- Every module must import cleanly: `python -c "from orchestrator import Pipeline"` must work
- `python run.py --brief config/brief-brazil-real.json --test-single-page` must run without import errors (it will fail at browser connection, which is expected without a running browser)
- `python run.py --brief config/brief-brazil-real.json --rejudge-from output/snippets.jsonl` must work end-to-end if API keys are set (no browser needed)
- Hard filter tests must pass: annotation workers get caught, ML engineers pass through
- Brief-driven prompts must include actual content from the brief, not generic placeholders

## Deliverables
When done, print a summary of:
1. Files changed and why
2. What works end-to-end now
3. What's stubbed/TODO
4. What to test first when connecting to a live browser
