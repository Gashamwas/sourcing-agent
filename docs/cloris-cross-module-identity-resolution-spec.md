# Cloris Cross-Module Identity Resolution Spec

Status: draft
Owner: Sam
Last updated: 2026-04-29

This spec defines how Cloris resolves "this Researcher candidate is the same person as that LinkedIn candidate" — and equivalently for every other cross-module pair. It is the platform's largest single architectural-prerequisite gap for multi-module operation: without cross-module identity, a person who appears in three modules appears as three unmerged rows in Run Review, and the recruiter sees the same name three times.

For the architectural commitment, see `Cloris-Architecture-North-Star.md` §10. For the workspace surface that consumes person records, see `docs/cloris-candidate-workspace-spec.md`. For the pre-existing single-source identity work this spec generalizes from, see `linkedin/recruiter_identity_resolver.py` and `GitHub-LinkedIn-Reconciliation-Source-of-Truth.md` (the GitHub→LinkedIn reconciliation pattern).

The cross-module identity layer is the platform's reconciliation moat. Every other recruiting tool tracks candidates per source; Cloris tracks them per person. Building this well is a competitive advantage; building it poorly degrades the multi-module value proposition to "more rows, same data."

## 1. Problem and goal

The substrate's `candidates` table at `shared/runtime_state/store.py:182` enforces `UNIQUE(brief_id, source, identity_key)`. A researcher with ORCID `0000-0001-2345-6789` discovered via OpenAlex is one row with `source="researcher"`, `identity_key="0000-0001-2345-6789"`. The same person on LinkedIn is another row with `source="linkedin"`, `identity_key="https://www.linkedin.com/in/janedoe/"`. The same person on GitHub is a third row with `source="github"`, `identity_key="janedoe"`. Three rows. Three independent evaluations. Three independent saves. Three editorial cards in Run Review for what the recruiter experiences as one candidate.

This is correct at the storage layer (per-source identity is a stable primary key for that source) and incorrect at the product layer (the recruiter works with people, not source-rows).

The goal: a `person` record that aggregates candidates across sources for a brief. Run Review and the candidate workspace render persons as the primary entity; per-source candidates appear as the evidence sources for the person. Cross-source dedup is automatic at high confidence; ambiguous cases surface for recruiter review.

## 2. Scope

### 2.1 In scope

- **`person` and `person_candidate` tables** in `shared/runtime_state/store.py`.
- **Per-source-pair resolution adapters** at `shared/cross_module_identity/<source_a>_<source_b>.py`.
- **Offline reconciliation pass** that runs after a multi-module run, populating `person_id` on workspace entries.
- **Ambiguity surface** in the candidate workspace and Run Review for cases where automatic resolution is low-confidence.
- **Confidence scoring and resolution-method enumeration** so every person↔candidate link is auditable.
- **Brief-scoped persons** — a person is unique within a brief, not across briefs (a candidate the recruiter is working for two roles is two persons in two workspaces; cross-brief person aggregation is deferred).

### 2.2 Out of scope

- **Real-time resolution during a run.** Resolution runs as a post-stage, not inside the discovery pipeline. Real-time matching adds latency and is unnecessary; offline reconciliation against the canonical store is sufficient.
- **Cross-brief person aggregation.** Per `docs/cloris-candidate-workspace-spec.md` §2.2, the workspace is brief-scoped. Cross-brief is v2.
- **Manual person creation.** Persons are created by the resolution layer or by the recruiter merging candidates manually. There is no "add person" workflow without an underlying candidate.
- **Identity resolution against external systems** (LinkedIn's internal IDs, ATS records). The layer resolves across Cloris's own per-source candidate rows; it does not reach outside.

## 3. Data model

### 3.1 `person` table

```sql
CREATE TABLE IF NOT EXISTS person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id TEXT NOT NULL,
    canonical_display_name TEXT NOT NULL,
    canonical_profile_url TEXT,                     -- typically the LinkedIn URL when known
    canonical_email TEXT,                            -- optional; populated when discovered via commit logs, etc.
    identity_evidence_json TEXT NOT NULL DEFAULT '{}',  -- ORCID, GitHub username, patent inventor key, etc.
    review_status TEXT NOT NULL DEFAULT 'auto_resolved', -- 'auto_resolved' | 'recruiter_confirmed' | 'recruiter_rejected' | 'ambiguous'
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(brief_id, canonical_profile_url)
);

CREATE INDEX IF NOT EXISTS idx_person_brief
    ON person(brief_id);
```

Notes:

- `canonical_profile_url` is the LinkedIn profile URL when the person has been resolved via LinkedIn (the canonical reconciliation surface per `GitHub-LinkedIn-Reconciliation-Source-of-Truth.md`). Persons not yet resolved to LinkedIn have `canonical_profile_url = NULL`.
- `identity_evidence_json` carries source-specific identity anchors: `{"orcid": "0000-0001-2345-6789", "github_username": "janedoe", "primary_affiliation": "MIT CSAIL"}`. Each adapter populates the fields it produces.
- `review_status` distinguishes automatic resolution from recruiter-confirmed merges and explicit splits. Important for the feedback loop — a `recruiter_rejected` link informs future resolutions.

### 3.2 `person_candidate` linking table

```sql
CREATE TABLE IF NOT EXISTS person_candidate (
    person_id INTEGER NOT NULL,
    candidate_id INTEGER NOT NULL,
    confidence REAL NOT NULL,
    resolution_method TEXT NOT NULL,    -- 'orcid_match' | 'name_affiliation_match' | 'github_email_match' | 'manual_merge' | etc.
    resolution_payload_json TEXT NOT NULL DEFAULT '{}',  -- evidence used for the match
    created_at TEXT NOT NULL,
    PRIMARY KEY(person_id, candidate_id),
    FOREIGN KEY(person_id) REFERENCES person(id) ON DELETE CASCADE,
    FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
);
```

Notes:

- One person can have many candidates (one per source). One candidate maps to at most one person (constraint enforced by the resolution algorithm; not in SQL because manual splits can re-link).
- `confidence` is in [0.0, 1.0]. Auto-resolution requires confidence ≥ 0.85; below that is surfaced as ambiguous.
- `resolution_method` is enumerated in section 5; new adapters add new method names.

### 3.3 Workspace integration

The `workspace_entries` table (`docs/cloris-candidate-workspace-spec.md` §3.1) carries `person_id INTEGER` (nullable). Populated post-resolution. Run Review and the workspace UI group entries by `person_id`; entries with `person_id = NULL` render per-source until resolved.

## 4. Resolution layer architecture

```
shared/cross_module_identity/
  __init__.py
  base.py                          # IdentityResolver protocol; ResolutionResult dataclass
  orchestrator.py                  # CrossModuleResolutionOrchestrator
  researcher_to_linkedin.py        # adapter: researcher candidates → LinkedIn candidates
  github_to_linkedin.py            # adapter: GitHub candidates → LinkedIn candidates
  defense_to_linkedin.py           # adapter: defense candidates → LinkedIn candidates
  designer_to_linkedin.py          # adapter: designer candidates → LinkedIn candidates
  researcher_to_github.py          # cross-non-LinkedIn pair (researchers with GitHub footprint)
  defense_to_researcher.py         # cross-non-LinkedIn pair (defense engineers with publications)
  manual_merge.py                  # recruiter-driven manual link/split logic
```

The orchestrator runs after a brief's runs complete (or on a scheduled basis for active briefs). For each pair of sources active under the brief, the orchestrator invokes the relevant adapter, which returns `ResolutionResult` records.

```python
@dataclass
class ResolutionResult:
    candidate_a_id: int
    candidate_b_id: int
    confidence: float
    resolution_method: str
    payload: dict[str, Any]  # evidence used
```

Results with `confidence ≥ 0.85` are auto-applied: a `person` row is created (if neither candidate already has one) or extended (if one does), and `person_candidate` rows are written.

Results with `0.5 ≤ confidence < 0.85` are surfaced as ambiguous. The candidate workspace renders them as candidate cards with a "Possibly the same person as: [other candidate]" prompt. Recruiter confirms or rejects; their action writes a high-confidence `manual_merge` resolution.

Results with `confidence < 0.5` are discarded.

## 5. Per-source-pair resolution algorithms

### 5.1 Researcher → LinkedIn

The strongest cross-source pair because researchers often link ORCID to LinkedIn directly, and ORCID is a global identifier.

**Inputs.** Researcher candidate (display_name, ORCID, last_known_institutions, top papers, co-author network). LinkedIn candidate (display_name, current_employer, education entries, profile_url).

**Methods, in priority order:**

1. **`orcid_match`** (confidence 0.95-1.0). LinkedIn profile contains an explicit ORCID link in the contact section. Browser-extracted during `linkedin/recruiter_identity_resolver.py`'s identity-resolution flow.
2. **`name_plus_affiliation_match`** (confidence 0.7-0.9). Display names match (with normalization for nicknames, middle initials, transliteration), and the LinkedIn current employer matches one of the researcher's `last_known_institutions` ROR entries.
3. **`name_plus_education_match`** (confidence 0.6-0.85). Display names match, and the LinkedIn education entries include the researcher's PhD-granting institution. Useful for industry researchers whose current employer doesn't match their academic affiliation.
4. **`name_plus_publication_evidence`** (confidence 0.55-0.75). Display names match, and the LinkedIn profile mentions specific paper titles, conference talks, or publication venues that match the researcher's publication record.

Common-name collision handling. "Wei Wang" with no ORCID and a generic affiliation is unresolvable automatically. The adapter returns no match; the candidate stays per-source. Recruiter can manually merge if they verify identity through other channels.

### 5.2 GitHub → LinkedIn

Inputs. GitHub candidate (username, display_name, bio, location, blog/website, email-from-commits if discovered). LinkedIn candidate.

**Methods:**

1. **`github_email_match`** (confidence 0.9-1.0). Email discovered from GitHub commit history matches an email visible on the LinkedIn profile (rare; usually requires the recruiter to have already confirmed identity).
2. **`github_url_in_linkedin_profile`** (confidence 0.95-1.0). LinkedIn profile contains a github.com link to the candidate's username in the contact or "featured" section.
3. **`name_plus_company_match`** (confidence 0.7-0.85). Display names match (with username/handle normalization) and GitHub `company` field matches LinkedIn current employer.
4. **`name_plus_blog_match`** (confidence 0.6-0.8). Display names match and the GitHub `blog` field matches a website linked from LinkedIn.
5. **`username_only_match`** (confidence 0.4-0.6). GitHub username is plausibly derivable from LinkedIn display name (e.g., "Jane Doe" → "janedoe"). Surfaced as ambiguous.

The existing `linkedin/recruiter_identity_resolver.py` already implements `name_plus_company_match` for the GitHub→LinkedIn flow per `GitHub-LinkedIn-Reconciliation-Source-of-Truth.md`; the adapter generalizes that pattern.

### 5.3 Defense → LinkedIn

Inputs. Defense candidate (PI name from SBIR, inventor name from patents, conference author name, employer history from SBIR institution + patent assignee). LinkedIn candidate.

**Methods:**

1. **`patent_assignee_plus_name_match`** (confidence 0.75-0.9). Display names match and the patent assignee at the time of filing matches a LinkedIn employer entry within the appropriate timeframe.
2. **`sbir_pi_plus_institution_match`** (confidence 0.7-0.85). Display names match and the SBIR PI institution matches a LinkedIn employer entry.
3. **`name_plus_publication_venue_match`** (confidence 0.6-0.8). Display names match and LinkedIn mentions specific defense conferences or programs.
4. **`name_plus_clearance_disclosure_match`** (confidence 0.5-0.7). Display names match and LinkedIn voluntarily discloses clearance status consistent with the defense work history. Note: the adapter only consumes voluntarily-disclosed clearance signal; it does not seek clearance information.

### 5.4 Designer → LinkedIn

Inputs. Designer candidate (Behance username/display_name, specializations, tools, location, portfolio URL, linked social accounts). LinkedIn candidate.

**Methods:**

1. **`behance_url_in_linkedin_profile`** (confidence 0.95-1.0). LinkedIn profile contains a behance.net link to the candidate's username.
2. **`portfolio_url_match`** (confidence 0.85-0.95). Designer's portfolio URL appears as a LinkedIn website entry.
3. **`name_plus_company_plus_specialization_match`** (confidence 0.65-0.8). Display names match, current employer matches, and LinkedIn role mentions the designer's specialization (UX/UI Design, Product Design, etc.).

### 5.5 Cross-non-LinkedIn pairs

Researcher ↔ GitHub, Defense ↔ Researcher, Designer ↔ Researcher, etc. These adapters use the same building blocks (name normalization, affiliation matching, URL cross-references) but typically produce lower base confidence because the canonical reconciliation surface (LinkedIn) isn't on either side. Useful primarily for collapsing duplicate workspace entries before LinkedIn resolution runs.

## 6. Resolution orchestrator behavior

The orchestrator (`shared/cross_module_identity/orchestrator.py`) runs:

1. **On run completion.** When a module's run finishes (`status="completed"` written to the `runs` table), the orchestrator scans for new candidates that don't have a `person_id` yet. For each, it invokes the relevant adapters against existing candidates from other sources for the same brief.
2. **On a scheduled basis** for active briefs. A nightly job catches up any missed reconciliations (e.g., when adapter logic is updated, when new candidates appeared after the run completion trigger).
3. **On manual trigger** via `tools/cross_module_identity_admin.py` for repair operations.

For each candidate-pair with a confident resolution, the orchestrator either creates a new `person` row or extends an existing one. Conflicts (e.g., candidate A is auto-resolved to person 1; candidate B is auto-resolved to the same person 1; candidate A and candidate B are also auto-resolved to each other but lower confidence) are reported to the audit log; the highest-confidence resolution wins.

The orchestrator is idempotent. Re-running on the same data produces the same `person_candidate` links; existing links are not overwritten unless the resolution method's confidence is materially higher.

## 7. UI surfaces

### 7.1 Run Review and workspace person-first rendering

Per `docs/cloris-candidate-workspace-spec.md` §5.4, post-resolution candidates render as person cards with aggregated source evidence. The cross-module identity layer is what makes that rendering possible.

### 7.2 Ambiguity surface

For workspace entries with `0.5 ≤ confidence < 0.85` resolutions, the candidate workspace renders an "Ambiguous match" prompt:

> Cloris isn't sure if this is the same person as another candidate in this workspace. Possibly: **Jane Doe** (LinkedIn). Why Cloris thinks they might be the same: name match + employer at MIT + publication record. Confirm or reject.
>
> [Confirm same person] [Reject — different people] [Need more evidence]

Recruiter actions:

- **Confirm same person** — writes a `manual_merge` resolution with confidence 1.0; merges the persons.
- **Reject — different people** — writes a `manual_split` resolution with confidence 1.0; ensures the two never merge in future passes.
- **Need more evidence** — defers; the prompt re-surfaces if additional evidence accrues.

### 7.3 Manual merge / split tooling

Beyond the prompt-driven flow, the workspace allows recruiter-initiated merges and splits:

- "Merge with..." action on a candidate card opens a search dialog within the workspace.
- "Split" action on a person card with multiple candidates allows the recruiter to remove specific candidates from the person.

Manual actions write `person_candidate` rows with `resolution_method = "manual_merge"` or `"manual_split"` and confidence 1.0. The audit log captures them.

## 8. Feedback to adapters

Recruiter actions in §7.2-7.3 inform the resolution layer's calibration:

- A pattern of `recruiter_rejected` results for a particular adapter at a particular confidence band indicates the adapter is over-confident; the band is recalibrated downward.
- A pattern of `recruiter_confirmed` results in the ambiguous band indicates the adapter is under-confident; the band is recalibrated upward.

V1 ships without automated calibration adjustment; the adapter authors review feedback periodically and update thresholds. Automated calibration is deferred to v2.

## 9. Migration and rollout

- New tables (`person`, `person_candidate`) added via `_migrate` in `shared/runtime_state/store.py`.
- `workspace_entries.person_id` column added (nullable).
- Resolution orchestrator built at `shared/cross_module_identity/`.
- First two adapters: `researcher_to_linkedin.py` and `github_to_linkedin.py` (the existing `linkedin/recruiter_identity_resolver.py` informs the latter).
- Backfill: existing LinkedIn candidates get one-to-one `person` rows on first orchestrator pass after the migration.
- UI: workspace and Run Review render person-first when `person_id` is set, per-source otherwise. The UI handles the transition gracefully.

Phase target: ships in `Cloris-Multi-Module-Roadmap.md` Phase 3 (months 5-7), in parallel with the Healthcare extension.

## 10. Known hard cases

Documented for visibility; they constrain v1 expectations.

- **Common names.** "Wei Wang", "John Smith", "Maria Garcia" — without strong identity anchors (ORCID, GitHub URL on LinkedIn), automatic resolution is unsafe. These cases stay per-source until the recruiter manually merges.
- **Researcher → GitHub for ORCID-less researchers.** Common in non-CS fields. LinkedIn is usually the bridge, not direct researcher-GitHub matching.
- **Privacy-aware candidates.** Some candidates deliberately don't link their profiles (security researchers, founders, public-figure exceptions). Cloris respects the lack of cross-references; the candidate stays per-source.
- **Multiple GitHub accounts.** A single person may have a personal account and a corporate account. The adapter treats them as separate candidates; recruiter manually merges if appropriate.
- **Stale affiliations.** A researcher's OpenAlex affiliation lags real life by 6-24 months. The adapter accepts current LinkedIn employer as more recent than OpenAlex affiliation; this is a feature, not a bug.

## 11. Decisions captured here

- 2026-04-29 — Cross-module identity is brief-scoped. Cross-brief person aggregation deferred.
- 2026-04-29 — Resolution runs offline (post-run, scheduled, or manual), not real-time during discovery.
- 2026-04-29 — Auto-resolution threshold is confidence ≥ 0.85. Below that is surfaced as ambiguous.
- 2026-04-29 — LinkedIn is the canonical reconciliation surface. Other-pair adapters are useful but secondary.
- 2026-04-29 — Recruiter manual merges and splits write to the same `person_candidate` table with confidence 1.0; they are not a separate data path.
- 2026-04-29 — Adapter calibration adjustment is manual in v1; automated in v2.
