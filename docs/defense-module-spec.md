# Defense Engineering Module Spec

Status: ready-to-implement
Owner: Sam
Last updated: 2026-04-29

The Defense module surfaces and evaluates engineers working on defense-relevant systems whose technical depth is documented in voluntarily-published public records — specifically, federal SBIR/STTR awards, USPTO patents, and IEEE/AIAA conference publications. It is structurally a Researcher module variant, with three new source adapters and defense-specific brief calibration vocabulary, plus an explicit compliance posture.

This spec follows the shape in `docs/cloris-module-template.md`. For the parent Researcher module spec, see `docs/researcher-module-spec.md`. For the brief schema additions, see `docs/cloris-brief-multi-module-extensions.md`.

## 1. Target population

PhD and MS engineers with 5+ years experience in defense-relevant technical domains whose technical depth is documented in public records:

- Radar and EW (electronic warfare) signal processing engineers.
- Autonomy and perception engineers for contested environments (the cohort Anduril, Shield AI, Saronic, Joby Defense, Castelion are competing to hire).
- Communications and signal processing engineers with defense program experience.
- Hypersonics, propulsion, and directed-energy systems engineers (mostly identified via patents and IEEE/AIAA publications).
- RF and microwave engineering specialists.
- Sensor fusion and ISR (intelligence, surveillance, reconnaissance) engineers.

The defining signals: SBIR/STTR award PI history, USPTO patent inventor records in defense-adjacent CPC classifications, IEEE/AIAA conference publication record, optionally DTIC unclassified report authorship.

Excluded: defense engineers whose work is entirely classified with no public footprint (Cloris cannot evaluate them); contractors in non-technical roles (program managers, business development); engineers with public records but in non-defense-relevant domains.

This module identifies engineers whose technical depth is *publicly documented*. It does not identify cleared engineers per se, and it does not seek clearance signals. Some engineers in the target population hold clearances; some do not. The module evaluates their public technical record only.

## 2. Buyer persona

- Defense recruiting firms (FedHired, ClearedJobs.net's recruiter clients, MoxxiSecure, Insperity Professional Services, plus boutique cleared-talent firms).
- Defense primes (Raytheon, Lockheed Martin, Northrop Grumman, General Dynamics, Boeing Defense, BAE Systems, L3Harris).
- Defense-tech startups (Anduril, Shield AI, Rebellion Defense, Hadrian, Hermeus, Castelion, Saronic, Joby Defense). The highest-energy buyer because their hiring constraint dominates growth.
- Dual-use AI companies with growing defense programs (Palantir, Scale AI, Sarcos).

Pricing: $30K-$80K annual for boutique recruiting firms; $100K+ for enterprise (defense primes, large defense-tech startups). Defense primes have 12+ month sales cycles with security review at procurement; expect commercial revenue from this module on a 2027 timeline even if the engineering ships in 2026.

Why these buyers cannot solve the problem with existing tools: defense engineering recruiting is currently relationship-driven, with no algorithmic surfacing tools that work on public-only data. ClearedJobs.net, ClearanceJobs, and similar platforms surface job postings to cleared candidates but do not help recruiters discover candidates by technical depth. The signal foundation (cross-referencing SBIR PI history with USPTO patent inventor records and IEEE publications) is unique.

## 3. Differentiation thesis

Strong. Patent-based and SBIR-based sourcing of engineers is novel. The data foundation — particularly SBIR — is unique to Cloris among recruiting tools because nobody else has indexed this data for recruiting use. SBIR award abstracts describe what was actually built at a level of detail that LinkedIn never reaches.

Cloris's calibration-driven evaluation pipeline applies directly. The brief carries `DefenseCalibration` (patent count floor, classification codes, SBIR agency focus, phase floor) which the evaluation procedure consumes. The narrowing from "all defense engineers in public records" to "engineers with documented depth in [target capability area] who built things the buyer wants more of" is the commercial pitch.

## 4. Strategic priority and roadmap fit

Priority **#4** in `Cloris-Module-Strategy.md` §4. Build alongside Healthcare in Phase 3.

Roadmap fit: Phase 3 (August-November 2026) for engineering; commercial revenue is a 2027 outcome due to defense buyer sales cycles.

Prerequisites:

- Researcher module v1 shipped and stable (Defense is a Researcher variant).
- Phase 1 foundation work complete.
- Defense customer development (Phase 2-3) producing 2+ committed customers before engineering launch.
- Brief IP/export-control review of the compliance posture before non-US marketing.

## 5. Data foundation

### 5.1 SBIR.gov (anchor)

API: `api.sbir.gov`. Free, public, no authentication. Documented at `www.sbir.gov/api`.

Coverage: every federal SBIR and STTR award since the early 1980s. ~200K+ records. Includes PI name, institution, agency code (DARPA, AFRL, ONR, ARL, NAVSEA, etc.), program topic, award amount, phase (Phase I or Phase II), award abstract, fiscal year. Updates rolling as new awards are announced.

Identity quality: structured PI name + institutional affiliation. Multiple awards by the same PI link via name + institution match (no global PI ID, but the structured affiliation makes disambiguation easier than with arXiv).

ToS: US government data. Freely usable including commercial. No restrictions.

Verdict: anchor source for the Defense module. The technical abstracts describe what was built; this is the highest-signal-density data source available for defense engineering recruiting.

### 5.2 USPTO PatentSearch (anchor)

API: post-March-2026 endpoint at `data.uspto.gov`. Free, government-published. AI-disambiguated inventor records. Coverage: all USPTO patents, with assignee history, classification codes (CPC and IPC), filing dates, abstracts.

Identity quality: structured inventor name + assignee at filing time + city/state. AI-disambiguated inventor records are much improved over the legacy PatentsView API. ORCID cross-references where the inventor has linked.

ToS: US government data. Freely usable including commercial.

Bulk option: Google Patents Public Datasets on BigQuery — free first 1TB/month, harmonized inventor records with country codes, disambiguated since 2018. Useful for bulk discovery.

Verdict: anchor source for the Defense module alongside SBIR.

### 5.3 IEEE Xplore metadata API (enrichment)

API: `developer.ieee.org`. Free with API key. Returns title, abstract, keywords, publication venue, author names, affiliations. Metadata-only — no full text.

Coverage: IEEE conference proceedings (MILCOM, FUSION, ICASSP, IEEE Aerospace Conference, etc.) and journals. Author affiliations are at publication time, not current.

ToS: free for metadata; bulk redistribution restricted. Recruiting use case is per-candidate enrichment, not bulk redistribution; permissive.

Verdict: enrichment source. Used to surface IEEE publication record for confirmed candidates from SBIR/USPTO.

### 5.4 DTIC (Defense Technical Information Center)

API: `discover.dtic.mil`. Free, public access search.

Coverage: ~1M unclassified DoD-affiliated technical documents. Title, abstract, author, contracting agency.

Status as of April 2026: the August 2025 USDR&E directive cut DTIC civilian staff from 154 to 40. The platform is in disrepair; expect degraded service through 2026. Functional but inconsistent.

Verdict: enrichment source, lower-priority than IEEE due to platform degradation. Defer integration to v2 if customer signal indicates value.

### 5.5 AIAA (American Institute of Aeronautics and Astronautics)

API: limited; AIAA's publication catalog is searchable via web but no clean API. Manual indexing of high-value AIAA papers as a brief-author resource is more practical than building an adapter.

Verdict: not a programmatic source for v1. Brief authors can populate `publication_venue_signals` with specific AIAA conferences if relevant.

### 5.6 Sources considered and rejected

- **SAM.gov contractor records.** Lists awarded federal contractors, but identity granularity is at the company level not the engineer level. Not useful for recruiting.
- **DoDLive / Defense.gov press releases.** Editorial, not data foundation.
- **Cleared-talent databases (ClearanceJobs, ClearedJobs.net).** These are job-posting platforms, not candidate databases. They are buyers of Cloris, not sources for it.
- **LinkedIn voluntary clearance disclosures.** Cloris does not seek clearance signals. The module's evaluation does not require clearance status.

## 6. Source-specific brief calibration

Per `docs/cloris-brief-multi-module-extensions.md`:

**Capability area extensions** (`shared/brief_schema.py:CapabilityArea`):

- `patent_classification_codes: list[str]` — CPC codes (e.g., `["G01S 13", "H04K 3"]`).
- `sbir_agency_signals: list[str]` — agency names (`["DARPA", "AFRL", "ONR", "ARL"]`).
- `publication_venue_signals: list[str]` — already used by Researcher; defense values are e.g., `["MILCOM", "FUSION", "IEEE Aerospace Conference"]`.

**Module-level calibration** (`shared/brief_schema.py:DefenseCalibration`):

```python
@dataclass
class DefenseCalibration:
    patent_count_floor: int = 0
    patent_filing_window_years: int = 10
    patent_first_inventor_minimum: int = 0
    sbir_agency_focus: list[str] = field(default_factory=list)
    sbir_phase_floor: str = ""  # "" | "phase_i" | "phase_ii"
    sbir_pi_minimum_count: int = 0  # number of awards as PI
    require_us_person_status: bool = False  # filter for explicitly-US-citizen-disclosed candidates
```

`require_us_person_status` defaults False. Some defense buyers will require the filter; the brief explicitly opts in. Note: this filter only consumes voluntarily-disclosed citizenship status from public sources (e.g., LinkedIn voluntary disclosure); the module does not infer citizenship.

Pre-built brief templates (`config/brief-templates/defense/`):

- `radar-engineer-darpa-experienced.json`
- `autonomy-perception-contested-environments.json`
- `rf-microwave-defense-prime.json`
- `signal-processing-isr.json`
- `propulsion-engineer-hypersonics.json`

## 7. Evaluation pipeline mapping

**Snippet evidence.** Engineer summary plus structured public-record extract:

```
Name: Jane Doe
Current Affiliation: Raytheon Missile Systems (Principal RF Engineer, 2018-present)
Patent Portfolio: 4 granted patents in millimeter-wave radar (G01S 13/xx); assignees: Raytheon (3), L3Harris (1)
SBIR/STTR History: PI on 2 DARPA Phase II awards in autonomous radar; 1 AFRL Phase I in EW signal detection
IEEE Publications: 6 papers at MILCOM and FUSION (2018-2024)
Career: PhD MIT 2010 → Lockheed Skunk Works 2010-2015 → AFRL contractor 2015-2018 → Raytheon 2018-present
```

**Full evidence.** Per-patent abstracts, per-SBIR-award abstracts (the highest-detail technical descriptions available), per-paper abstracts and keywords, complete career history, optional DTIC unclassified report authorship.

**Depth distinction translation.** Builder = active inventor on patents within target classification codes, PI on SBIR awards in target agency-and-phase tier, first or senior author on IEEE/AIAA papers in target venues. User = engineer who has been listed on patents as one of many co-inventors without leading the technical work, or whose conference presence is workshop-only or as a non-presenting co-author.

**Decision contract.** Standard `SAVE` / `REJECT` / `INFERENTIAL_SAVE`. `INFERENTIAL_SAVE` for cases where the public record is strong but current employment is unclear (common with engineers who left the public-program path 2-3 years ago).

## 8. State machine fit

Existing Researcher lifecycle. Same work-unit kinds (`RESEARCHER_AUTHOR_QUERY_KIND` for SBIR PI queries and IEEE author queries; new `DEFENSE_PATENT_QUERY_KIND = "defense_patent_query"` for USPTO patent searches because the discovery shape is patent-classification-driven rather than author-name-driven).

## 9. Identity disambiguation

SBIR records have structured PI name + institution; disambiguation is much easier than arXiv. Patent records have structured inventor name + assignee + city/state at filing; disambiguation across patents within a single inventor is solved by USPTO's AI-disambiguation. Cross-source matching (same person on SBIR + USPTO + IEEE) uses name + employer-history overlap.

Common-name collisions at the source level are rare in defense engineering due to the smaller cohort size and richer affiliation data. When they occur, the disambiguation pass uses the same Perplexity-augmented identity check as Researcher.

## 10. Reconciliation strategy

Defense candidates reconcile to LinkedIn via `defense/recruiter_identity_resolver.py` plus `shared/cross_module_identity/defense_to_linkedin.py`.

Resolution methods, per `docs/cloris-cross-module-identity-resolution-spec.md` §5.3:

1. `patent_assignee_plus_name_match` (confidence 0.75-0.9).
2. `sbir_pi_plus_institution_match` (confidence 0.7-0.85).
3. `name_plus_publication_venue_match` (confidence 0.6-0.8).
4. `name_plus_clearance_disclosure_match` (confidence 0.5-0.7) — consumes voluntarily-disclosed clearance only; does not seek it.

Defense engineers without LinkedIn presence are rare (most have professional LinkedIn presence); the candidate stays per-source in the workspace if no match is found.

## 11. Save destination

Standard: `["candidate_workspace"]` for defense-only briefs; `["linkedin_recruiter", "candidate_workspace"]` for multi-module briefs.

Module-specific outreach generation at `defense/outreach.py`. Outreach copy references specific patents or SBIR awards (the candidate's strongest public-record signal), frames the role as continuation of their published work, and is more formal than the standard outreach (defense engineering is a more formal recruiting culture).

## 12. Build effort estimate

Total: **3-4 weeks** atop the existing Researcher framework, plus **1 week** for the compliance audit shell. ~5 weeks total for engineering.

Breakdown:

- `researcher/sources/sbir.py`: 4 days. SBIR.gov API client, PI search, agency filtering.
- `researcher/sources/patents.py`: 5 days. USPTO PatentSearch client, BigQuery option for bulk, CPC classification filtering.
- `researcher/sources/ieee.py`: 3 days. IEEE Xplore metadata client.
- Brief schema additions (`DefenseCalibration`, capability area extensions): 1 day.
- Defense-specific facial calibration and brief templates: 2 days.
- `defense/recruiter_identity_resolver.py`: 3 days.
- Compliance audit shell (immutable evidence logs, audit-trail surface, contractual reps document, provenance disclosure UI element): 5 days.
- Tests: 4 days.

Total: ~27 person-days = ~5-6 calendar weeks at split-attention pace.

Critical: the SBIR adapter alone is high-signal enough to validate the module before the patent and IEEE adapters land. Ship SBIR-only as a beta to first defense customer; add patents and IEEE incrementally.

## 13. First-customer demonstration scope

Demo brief: "Senior radar engineer, 8+ years experience, with at least one SBIR Phase II award as PI in radar signal processing in the last 5 years, US-only."

What the module produces: SBIR queries return ~50-100 PIs; patent search returns ~20-40 inventors in radar CPC classifications; IEEE search returns ~30-60 MILCOM/FUSION authors. Cross-source dedup produces a unified candidate list of ~30-60 engineers. Facial triage narrows to ~15-30; full evaluation produces ~8-15 saves.

Compliance: every saved candidate's evidence trail shows the public source (SBIR award number, USPTO patent ID, IEEE DOI). The "data provenance" indicator is visible to the recruiter. No clearance signal sought or stored.

## 14. Ship-quality scope

Beyond the demo: full SOC 2-style audit trail; immutable evidence logs available to defense customer security-review teams; export-controlled CPC code awareness (warning when a brief targets export-controlled patent classifications and is being used by a non-US customer); cross-module dedup with Researcher candidates (defense engineers who also publish in academic venues).

## 15. Failure modes and edge cases

- **SBIR.gov degraded service.** API has occasionally been unstable. Strategy: cache per-PI summaries; degrade gracefully when API is down (run with reduced coverage and inform the recruiter).
- **USPTO migration disruption.** PatentsView API was discontinued May 2025; PatentSearch transition through March 2026. Build expects PatentSearch as canonical; backup path uses Google Patents BigQuery if PatentSearch is unstable.
- **Engineer changes employer mid-program.** Patents at filing time list one assignee; the engineer may have left that company by now. Strategy: cross-reference current LinkedIn employer for any saved candidate.
- **Export-controlled CPC codes.** Some patent classifications imply export-controlled technology (e.g., F02K rocket propulsion, certain G01S radar subclasses). Strategy: brief warns at authoring time; non-US customer accounts are flagged with restricted CPC code visibility.
- **Bot or organization SBIR PIs.** SBIR PIs are always individuals, not bots. Less of an issue than for OSS Maintainers.
- **Engineers with classified-only public footprint.** Some senior defense engineers have minimal public records because their work is classified. The module cannot help find them; the brief should explicitly include a `non_fit_pattern` for this case so the recruiter understands the limitation.

## 16. Open questions

- **Compliance audit shell scope.** What level of audit trail satisfies defense prime procurement teams? Investigate via customer development; the v1 shell may need extension based on first-customer feedback.
- **DTIC integration timeline.** DTIC platform recovery is uncertain. Defer DTIC integration to v2; revisit in mid-2027 when the platform's status is clearer.
- **Live CPC classification updates.** USPTO classifications evolve. Strategy formation should reference the current CPC taxonomy. Snapshot vs. live integration TBD; v1 uses snapshot updated quarterly.
- **Non-US patent integration.** EPO (European Patent Office), JPO (Japan), KIPO (Korea) data could expand coverage to non-US engineers. V1 is US-only via USPTO; v2 if customer signal indicates need.

## 17. Decisions captured here

- 2026-04-29 — Defense ships as a Researcher framework variant with three new source adapters, not a standalone module.
- 2026-04-29 — SBIR is the anchor; USPTO is co-anchor; IEEE is enrichment; DTIC is deferred to v2.
- 2026-04-29 — Module does not seek clearance signals; voluntarily-disclosed clearance status is consumed when present, never inferred.
- 2026-04-29 — Compliance audit shell is part of v1 engineering, not a post-ship addition.
- 2026-04-29 — V1 is US-only via USPTO. Non-US patent integration deferred.
- 2026-04-29 — V1 build target is 5-6 calendar weeks at split-attention pace, including compliance shell.
- 2026-04-29 — Commercial revenue is a 2027 expectation; engineering ships in 2026.
