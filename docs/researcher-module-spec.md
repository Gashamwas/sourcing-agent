# Researcher Module Spec

> **SUPERSEDED BY** [`plans/researcher-module-spec.md`](../plans/researcher-module-spec.md) (2026-05-03). The successor engages with the architecture that actually shipped (launcher registry, V2 brief schema, `candidates`-table workspace) — see its "Why the existing artifacts are stale" section. This document is preserved for product-strategy context.

Status: superseded
Owner: Sam
Last updated: 2026-04-29

The Researcher module discovers and evaluates ML researchers (and, via the Healthcare extension, biomedical researchers) using academic publication records as the primary evidence layer. It is the first non-LinkedIn discovery module Cloris ships and the de-risking case for the platform's modular extension pattern.

This spec follows the shape in `docs/cloris-module-template.md`. For implementation, see `plans/researcher-module-build.md`.

## 1. Target population

ML researchers with a documented publication record whose primary professional signal is what they have built and published in research environments rather than what LinkedIn says about their job title.

Specifically:

- First-author or co-first-author authors at NeurIPS, ICML, ICLR, ACL, EMNLP, COLM, CVPR, AAAI within the last 24 months, with at least 2 publications in that window.
- Research scientists at frontier AI labs (current or former) with a continuing public academic footprint (arXiv preprints, conference papers, GitHub).
- Late-stage PhD students and recent graduates (post-2024) in computational fields with frontier-relevant first-author papers; pre-LinkedIn but productively documented on arXiv and Semantic Scholar.
- Staff-level researchers at national labs (MIT Lincoln Lab, MILA, AI2, FAIR offshoots) whose LinkedIn profiles are sparse but whose Semantic Scholar / OpenAlex / dblp footprint is rich.

Excluded:

- Pure academic faculty unlikely to move to industry. The brief author can flag this via `non_fit_patterns`; the module does not bias against academic candidates by default because some are recruitable.
- Applied ML practitioners without publication signal (LinkedIn covers them).
- Data scientists who participated in a Kaggle competition and self-identify as researchers without publication record.
- Engineers at frontier labs whose work is implementation-focused without research output (the OSS Maintainers module is a better fit for some of these).

## 2. Buyer persona

Three primary buyer types, listed in commercial priority:

**(a) Frontier AI labs and AI-native companies hiring research scientists.** ~30-50 named labs and growth-stage AI companies, each willing to pay enterprise rates ($50K-$200K+/seat-year). Specific examples: Anthropic, OpenAI, Google DeepMind, Meta, xAI, Mistral, Cohere, Inflection, Adept, Reka, Magic, Imbue, Sakana, Together, Modal, Anyscale, Cresta. Mis-hire cost is $1M+ in compensation plus 12+ months of lost time; willingness to pay is high.

**(b) AI-focused executive search firms** doing researcher placement at senior levels. Daversa, Riviera Partners, ZRG's AI practice, Heidrick & Struggles's AI practice, True Search's AI practice. Per-placement supplemental pricing ($300-$600 supplemental on placements) or firm-level annual licenses ($40K-$120K).

**(c) AI strategy consulting firms** that build bespoke research teams for corporate clients. Smaller buyer pool but enterprise-grade contracts.

Why these buyers cannot solve the problem with existing tools: LinkedIn alone is poor at researcher identification because the strongest signal (publication record) is not on LinkedIn. Semantic Scholar / arXiv search is poor at recruiter use cases because they are paper-search tools, not researcher-recruiting tools — no brief, no evaluation, no calibration. The category is open.

Pricing range supportable: $1.5K-$4K/seat-month for in-house teams; $40K-$120K firm-level annual; $100K+ enterprise.

## 3. Differentiation thesis

Cloris's calibration-driven evaluation pipeline (`shared/brief_schema.py:179`) is the right substrate for evaluating researchers. The four-step structural template — capability mapping, depth test, transferability test, decision — applies to publication records as cleanly as it applies to LinkedIn profiles.

The "builder vs. user" depth distinction translates directly: builder = active researcher publishing original work in capability areas; user = industry-applied person citing research without producing it. Non-fit patterns translate: applied ML at companies whose research output doesn't transfer back to research environments. Capability areas translate: research areas mapped to OpenAlex concepts, arXiv categories, and target conference venues.

The data is open (OpenAlex CC0; Semantic Scholar free; dblp CC0; arXiv polite-pool). The competitive moat is not "we have data nobody else has." It is "we evaluate publication records the way a senior research recruiter would, calibrated to your specific role, at scale, with the closed feedback loop that improves brief calibration over time."

## 4. Strategic priority and roadmap fit

Priority **#1** in `Cloris-Module-Strategy.md` §4. Build first.

Roadmap fit: ships in `Cloris-Multi-Module-Roadmap.md` Phase 2 (June-August 2026). Prerequisites:

- Phase 1 foundation work (`plans/multi-module-foundation.md`) complete: `linkedin_project` default-empty fix, `target_modules` field, per-source nested calibration, candidate workspace v1, save destination abstraction, `cloris/worker.py:196` parameterization.
- Calibration vertical-agnostic refactor Slices 2-5 (`plans/calibration-layer-vertical-agnostic.md`) complete so the substrate is genuinely vertical-agnostic.

Customer development for 5+ named frontier-lab and exec-search conversations is a parallel workstream during foundation work; first customers should be onboarded within 2-3 weeks of the module shipping.

## 5. Data foundation

### 5.1 OpenAlex (spine)

API: `api.openalex.org/works`, `/authors`, `/institutions`, `/sources`, `/topics`. Free. Polite pool by email parameter; 100K calls/day, 10 req/s. Bulk daily snapshots on S3 for backfill.

Coverage: ~250M+ works, ~90M authors, ~109K institutions (ROR-linked). Built from MAG, Crossref, PubMed, ORCID, publisher feeds. Daily updates. Backfilled affiliation strings as of 2026.

Identity quality: best-in-class for free sources. Author objects include `display_name`, `display_name_alternatives`, `orcid`, `last_known_institutions` (ROR-IDed for clean geography), `affiliations` (history), `works_count`, `cited_by_count`, `summary_stats` (h-index, i10-index, 2yr mean citedness), topic concepts. Institutions are ROR-IDed which gives clean country and geography data.

ToS for commercial recruiting: explicit CC0 — public domain. Commercial use allowed. Recruiting use is fine. Attribution appreciated, not required.

Detection risk: zero. Public API.

Verdict: anchor source. Every researcher candidate originates from OpenAlex.

### 5.2 Semantic Scholar

API: `api.semanticscholar.org/graph/v1/`. Free with API key (free key on application; ~1 req/s sustained). Public pool ~100 req/5min unauthenticated. Bulk dataset (S2ORC) available.

Coverage: ~214M+ papers; strong in CS/AI and biomedicine; weaker in humanities. S2AND author disambiguation is decent but imperfect — common-name collisions and Asian-language authors are weaker.

Identity quality: name + parsed affiliation + sometimes homepage URL. ORCID is exposed when known. Citation counts and h-index are exposed.

ToS: free including commercial use. Allen AI is non-profit; expect attribution and reasonable behavior.

Detection risk: zero. Public API.

Verdict: enrichment. Used for paper similarity (SPECTER2 embeddings), recommendations, h-index cross-validation against OpenAlex.

### 5.3 dblp

API: `dblp.org/search/{publ,author,venue}/api`. Free. Soft rate limits with 429 + Retry-After. Bulk XML dump under CC0; encouraged for non-trivial use.

Coverage: comprehensive for CS — journals, conferences (NeurIPS, ICML, ICLR, ACL, EMNLP all covered), workshops. ML conference coverage is excellent and current. Less comprehensive for non-CS fields.

Identity quality: best-in-class for CS author disambiguation. Manually curated, persistent author IDs (PIDs), affiliation notes, ORCID where known, homepage links. Author homepage links are surprisingly often present.

ToS: CC0. Commercial use allowed.

Verdict: enrichment specifically for ML/CS. Used for high-confidence author disambiguation when OpenAlex matching is ambiguous, and for PID-based identity anchoring.

### 5.4 arXiv

API: `export.arxiv.org/api/query`. Atom-based query API; OAI-PMH for bulk; full bulk dumps via S3 (requester-pays).

Rate limits: 1 request / 3 seconds, single connection.

Identity quality: author *names only* in standard feed. Affiliation is an optional free-text field most submitters leave blank; what's there is unnormalized strings. ORCID queryable via `arxiv.org/a/<ORCID>` if linked but coverage is partial. The COMET project published an open author-affiliation dataset for arXiv through Dec 2025 — for backfilling affiliations, COMET is the merge target rather than parsing arXiv directly.

ToS for commercial: allowed but explicit — register as an arXiv affiliate before launching the product. Not hostile, but expect to register/announce.

Verdict: discovery feed for fresh preprints. Identity weaknesses are compensated by OpenAlex/dblp cross-references.

### 5.5 PubMed (Healthcare extension only)

API: NCBI E-utilities (`esearch`, `efetch`, `esummary`, `elink`). Free; 10 req/s with API key.

Coverage: excellent for life sciences/healthcare. Includes preprint cross-links to bioRxiv/medRxiv.

Identity quality: per-author affiliations stored since 2014; ORCID present in post-2017 records; corresponding-author email occasionally embedded in `<AffiliationInfo>` strings. Best biomedical author affiliation data of any free source.

ToS: US government data, freely usable including commercial. No restrictions.

Verdict: anchor source for the Healthcare extension. Pair with OpenAlex for citation depth.

### 5.6 Sources considered and rejected

- **Google Scholar.** No API. Aggressive bot detection; commercial scraping vendors exist but ToS exposure and ban risk are not worth it. OpenAlex coverage in 2026 is sufficient for ML; Scholar's marginal coverage advantage doesn't justify the risk.
- **ResearchGate.** Cloudflare-hostile, no API, hostile to scraping. The unique value (self-claimed profiles) is exactly what they protect hardest. LinkedIn covers self-claimed researcher profiles better.
- **Dimensions.ai / Lens.org.** Commercial; would be viable as paid alternatives if OpenAlex coverage proves insufficient. Not in v1; revisit if customer signal indicates coverage gaps.

## 6. Source-specific brief calibration

Per `docs/cloris-brief-multi-module-extensions.md`:

**Capability area extensions** (`shared/brief_schema.py:CapabilityArea`):

- `arxiv_category_signals: list[str]` — e.g., `["cs.LG", "cs.CL", "cs.AI"]` for an ML capability area.
- `publication_venue_signals: list[str]` — e.g., `["NeurIPS", "ICML", "ICLR"]`.

**Module-level calibration** (`shared/brief_schema.py:ResearcherCalibration`):

```python
@dataclass
class ResearcherCalibration:
    canonical_venue_patterns: list[str] = field(default_factory=list)
    edge_case_venue_patterns: list[str] = field(default_factory=list)
    h_index_floor: int = 0
    papers_in_window_floor: int = 0
    papers_in_window_months: int = 24
    first_or_senior_author_minimum: int = 0
    minimum_citation_velocity: float = 0.0
```

**Facial calibration source-specific patterns** (`FacialCalibration.sources["researcher"]`):

```python
SourceCalibration(
    fast_exit_patterns=[
        "Profile shows zero post-PhD industry/lab tenure",
        "Affiliation is corporate non-research with no publication record",
        "Publications are entirely in non-ML domains (chemistry, biology) without ML methodology emphasis",
    ],
    portfolio_yes_patterns=[
        "First-author papers at canonical ML venues within papers_in_window_months",
        "Co-author of training/evaluation framework adopted at frontier labs",
        "Recent affiliation at frontier lab or top-tier industry research org",
    ],
    portfolio_ambiguous_patterns=[
        "Publication-strong but only at workshop or non-canonical venues",
        "Recent transition from research to applied role; trajectory unclear",
    ],
    portfolio_no_patterns=[
        "All publications in non-target capability areas",
        "Single first-author paper from >24mo ago, no recent activity",
    ],
)
```

Author-level brief authoring guidance for these patterns lives in `docs/brief-authoring-guide.md` (existing) extended with researcher examples.

## 7. Evaluation pipeline mapping

**Snippet evidence** (light, used for facial triage). Author summary plus top 5 papers:

```
Name: Jane Doe
Current Affiliation: MIT CSAIL (Postdoctoral Researcher)
H-index: 12 | Total citations: 1,847 | Papers: 23
Top 3 papers:
- "Constitutional AI: Harmlessness from AI Feedback" (NeurIPS 2022, 1,200 citations)
- "Training Language Models to Follow Instructions with Human Feedback" (NeurIPS 2022, 4,400 citations)
- "Direct Preference Optimization" (ICLR 2024, 380 citations)
arXiv categories: cs.LG, cs.CL
ORCID: 0000-0001-2345-6789
Career: PhD Stanford 2020 → Postdoc MIT CSAIL 2024-present; OpenAI internship 2022; Google Brain internship 2023
```

**Full evidence** (deep, used for full evaluation). Complete publication record with abstracts, affiliation history, co-author network top 10, GitHub link if available, personal website if available, OpenAlex topic concepts.

**Depth distinction translation.** From the brief's `depth_distinction.builder_definition`: "researchers who design novel post-training methods, build training/evaluation infrastructure adopted at scale, and publish first-author papers at canonical venues." From `user_definition`: "applied ML practitioners who fine-tune existing models for product use cases without producing original methods or infrastructure."

**Decision contract.** Standard `SAVE` / `REJECT` / `INFERENTIAL_SAVE` / `TRANSFERABLE_SAVE`. No new decision types.

`INFERENTIAL_SAVE` use case for researchers: candidate has strong publication record but ambiguous current employment (e.g., last public affiliation 18mo ago, no LinkedIn). Cloris saves and flags for recruiter to verify current employment.

`TRANSFERABLE_SAVE` use case: candidate has strong builder depth in adjacent capability area (e.g., RL theory rather than RLHF post-training) and the brief's transferability examples support the transfer.

## 8. State machine fit

The existing lifecycle (`shared/runtime_state/store.py:62-71`) maps directly:

- `discovered` — author surfaced from OpenAlex search.
- `snippet_extracted` — author summary + top 5 papers fetched.
- `facial_started` / `facial_terminal` — researcher facial triage on snippet.
- `full_started` / `full_terminal` — full evaluation on complete publication record.
- `failed_retryable` / `failed_terminal` — standard failure semantics.

No new lifecycle states.

Work-unit kind: `RESEARCHER_AUTHOR_QUERY_KIND = "researcher_author_query"`. One work unit per OpenAlex search query (e.g., a query for "post-training researchers at frontier labs in the last 24 months" is one work unit; the unit's payload contains the query parameters; results are paginated through the unit's `checkpoint_json`).

Optional: `RESEARCHER_VENUE_GRAPH_SEED_KIND` for graph expansion from a seed paper or seed author. Deferred to a v2 expansion of the module if customer signal indicates need; not in v1.

## 9. Identity disambiguation

Within the OpenAlex/dblp/Semantic Scholar/arXiv data, researchers are identified by:

- **ORCID** when present (highest-confidence anchor).
- **OpenAlex author ID** (S2-disambiguated; reliable for English-name researchers, weaker for Asian-language and very common names).
- **dblp PID** (manually curated; best-in-class for CS).
- **Name + last_known_institution + topic concepts** (good for moderately common names).

Common-name collisions (e.g., "Wei Wang", "John Smith") are surfaced by the disambiguation pass before facial triage. The strategy:

1. OpenAlex search returns N candidate authors for the name.
2. Filter by brief geography (ROR country match) — drops candidates not in the target geography.
3. Filter by brief capability area arXiv categories — drops candidates whose primary topics don't overlap.
4. Filter by `papers_in_window_floor` — drops candidates without sufficient recent activity.
5. If 0 candidates remain, skip. If 1 candidate remains, accept. If 2+ candidates remain, run a Perplexity-augmented identity check (existing `shared/external_evidence/provider.py` infrastructure) using ORCID + affiliation + paper titles to disambiguate. If still ambiguous, surface as `INFERENTIAL_SAVE` with manual-review flag.

The disambiguation pass is not a new lifecycle state; it runs before `record_candidate_discovery()` and produces either a confirmed candidate identity, a deferred candidate, or a skip.

## 10. Reconciliation strategy

Researcher candidates reconcile to LinkedIn via `researcher/recruiter_identity_resolver.py` (mirroring `linkedin/recruiter_identity_resolver.py`'s pattern) and via the cross-module identity layer's `shared/cross_module_identity/researcher_to_linkedin.py` adapter.

Resolution methods, per `docs/cloris-cross-module-identity-resolution-spec.md` §5.1:

1. `orcid_match` (confidence 0.95-1.0).
2. `name_plus_affiliation_match` (confidence 0.7-0.9).
3. `name_plus_education_match` (confidence 0.6-0.85).
4. `name_plus_publication_evidence` (confidence 0.55-0.75).

The reconciliation pass runs after the researcher-module run completes. The orchestrator opens LinkedIn Recruiter (browser-based, humanized, per the existing `linkedin/recruiter_identity_resolver.py` four-step pattern) and resolves each saved researcher to a LinkedIn profile. Reconciled candidates' workspace entries are populated with `person_id` linking to the unified person record.

For researchers who genuinely aren't on LinkedIn (some academic researchers, some pre-LinkedIn early-career researchers): the candidate stays per-source in the workspace. The recruiter outreaches via email (typically findable through the researcher's institutional page) or through a co-author network introduction. The workspace surfaces this case explicitly with a "no LinkedIn match found" indicator.

## 11. Save destination

Default `save_destinations: ["candidate_workspace"]` for researcher-only briefs. For multi-module briefs targeting LinkedIn + Researcher: `save_destinations: ["linkedin_recruiter", "candidate_workspace"]` (the LinkedIn save destination is dispatched only for candidates resolved to LinkedIn).

Module-specific outreach generation lives at `researcher/outreach.py`. Outreach copy is calibrated for the academic context: references specific papers, suggests a 30-minute conversation about research overlap, signals industrial opportunity without overpressure. Pre-built outreach templates per common researcher profile (postdoctoral, PhD-final-year, research scientist).

## 12. Build effort estimate

Total: **4 weeks** for v1 (single founder + AI-assisted engineering).

Breakdown:

- OpenAlex client and acquisition: 4 days. Includes pagination, rate limiting, polite-pool email registration.
- Semantic Scholar client (cross-validation, embeddings): 2 days.
- dblp client (CS author disambiguation): 2 days.
- arXiv client (preprint feed): 2 days.
- `researcher/strategy.py`: 3 days. Opus-driven query generation from brief.
- `researcher/judgment_templates.py`: 3 days. Mirrors `github/judgment_templates.py`.
- `shared/judger.py` extension (`researcher_facial_judge`, `researcher_full_judge`, batch variants): 2 days.
- Brief schema additions (`ResearcherCalibration`, capability area extensions, facial calibration source patterns): 1 day.
- `researcher/orchestrator.py` and `session_orchestrator.py`: 4 days.
- `researcher/work_units.py`, `enricher.py`, `acquisition.py`, `side_effects.py`, `governor.py`: 4 days.
- `researcher/recruiter_identity_resolver.py`: 3 days.
- `shared/runtime_state/researcher.py` runtime bridge: 1 day.
- Cloris control plane registration: 1 day.
- Tests (`tests/test_researcher_*`): 4 days.

Total: ~36 person-days = ~7-8 calendar weeks at solo founder pace including context-switching, customer development, and architectural correction overhead. Compresses to 4 calendar weeks in dedicated focus mode.

Healthcare extension: +1-2 weeks (PubMed adapter, biomedical brief calibration vocabulary).

## 13. First-customer demonstration scope

Demo brief: "Find me ML research scientists at non-frontier-lab industry orgs (Series-B-funded ML startups) with 3+ first-author NeurIPS or ICML papers in the last 24 months who haven't been at their current employer for more than 18 months. US/EU only."

What the module produces:

- Strategy-formed OpenAlex queries surfacing ~200-500 plausible candidates after dedup.
- Disambiguation pass narrows to ~80-150 confidently-identified candidates.
- Facial triage produces ~30-70 facial-pass candidates.
- Full evaluation produces ~10-25 saves with structured rationale (capability mapping, depth assessment, transferability where applicable).
- Reconciliation produces LinkedIn matches for ~80% of saves.
- Candidate workspace surfaces all saves with editorial cards, evidence sections per source, and outreach copy.

What the recruiter sees in the workspace: a list of 10-25 named researchers with publication-grounded rationale, links to top papers, current affiliation, LinkedIn URL, and outreach copy. The recruiter reviews, marks confirmed/rejected, and moves the confirmed candidates into outreach.

What's missing in the demo (acceptable for first customer): cross-module identity merging with GitHub-discovered candidates (Phase 3 work); brief-iteration feedback loop (Phase 1 work but UI not polished); concurrent multi-brief operation; advanced graph expansion from confirmed saves.

## 14. Ship-quality scope

Beyond the demo:

- Concurrent operation against 5+ briefs without resource contention.
- Identity disambiguation resilience for common-name researchers via Perplexity-augmented checks.
- Audit-clean evidence trails for every candidate (every paper cited, every affiliation transition recorded with timestamp).
- Stop / resume / repair via existing `RuntimeStateLock` pattern.
- Brief-iteration feedback loop closing — workspace review marks feed brief revision proposals via `shared/brief_iteration.py`.
- Telemetry: facial pass rate, full eval pass rate, reconciliation success rate, save-to-confirmation rate per brief over time.
- Cross-module dedup with GitHub candidates once cross-module identity layer ships.
- Healthcare extension (PubMed adapter + biomedical calibration).

## 15. Failure modes and edge cases

- **OpenAlex outage.** Backoff and retry per existing `shared/rate_limiter.py` pattern. If sustained, run pauses with `governor_limit_reached` stop reason; resumes when API recovers.
- **Common-name collision.** Disambiguation pass surfaces unresolvable candidates. Surfaced to recruiter as `INFERENTIAL_SAVE` with manual-review flag; recruiter resolves by reviewing publication history side-by-side.
- **Affiliation drift.** OpenAlex affiliation lags real-life by 6-24 months. Reconciliation phase fetches current LinkedIn employer; the workspace shows both ("Last known: MIT CSAIL; Current per LinkedIn: Anthropic"). Acceptable; the candidate is correctly identified.
- **Researcher with no LinkedIn.** Candidate stays per-source in the workspace; reconciliation marks "no LinkedIn match found." Recruiter outreaches via institutional email or co-author intro. Acceptable.
- **Multiple OpenAlex author IDs for the same person.** OpenAlex occasionally produces duplicate author IDs (S2AND disambiguation imperfection). Detected by the disambiguation pass when two candidates have same ORCID or same publication set; merged at the reconciliation phase. Workspace shows merged person with both IDs noted.
- **Strategy formation produces noisy queries.** Adaptation phase (`researcher/strategy.py:adapt_after_batch`) reads run-level signal and refines queries. If pass rate stays low after 3 batches, brief may need calibration; surface to recruiter via Run Review.
- **arXiv affiliate registration not yet completed.** Module functional without arXiv (OpenAlex covers arXiv content via DOI cross-references); register as part of customer-launch readiness.

## 16. Open questions

- **Graph expansion in v1 vs. v2.** Co-author network expansion from confirmed saves is a powerful pattern. V1 doesn't include it (kept simple). V2 adds it as `RESEARCHER_VENUE_GRAPH_SEED_KIND` work units. Decision deferred until v1 ship + first-customer signal.
- **OpenReview integration.** OpenReview hosts ICLR submission histories with reviewer identity. Useful for high-value senior-researcher recruiting (people who reviewed for ICLR are typically senior researchers themselves). API exists. Defer to v2.
- **Industry-applied researcher edge case.** Some researchers transition to applied ML roles for 1-3 years and back to research. Are they builders or users during the applied period? Brief authoring captures this in the `transferability_examples`. If common-enough pattern, surface a brief-template addition.

## 17. Decisions captured here

- 2026-04-29 — OpenAlex is the spine; Semantic Scholar/dblp/arXiv are enrichment.
- 2026-04-29 — Common-name disambiguation runs before `record_candidate_discovery()`, not as a new lifecycle state.
- 2026-04-29 — V1 does not include graph expansion. Deferred to v2.
- 2026-04-29 — Healthcare extension ships as a sub-module (PubMed adapter + biomedical brief calibration), not as a separate Researcher-Healthcare module.
- 2026-04-29 — V1 build target is 4 calendar weeks at dedicated-focus pace; ~7-8 calendar weeks at split-attention pace including customer development.
- 2026-04-29 — Reconciliation to LinkedIn happens post-run; researchers without LinkedIn stay per-source in the workspace.
