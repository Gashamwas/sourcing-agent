# Healthcare / Life Sciences Extension Spec

Status: ready-to-implement
Owner: Sam
Last updated: 2026-04-29

The Healthcare extension adds biomedical-researcher discovery to the Researcher module. It is structurally identical to Researcher with PubMed as the primary source instead of (and additionally to) OpenAlex, plus biomedical-specific brief calibration vocabulary. Architecturally, this is a 1-2 week extension after Researcher v1 ships, not a separate module.

This spec follows the shape in `docs/cloris-module-template.md`. For the parent Researcher module spec, see `docs/researcher-module-spec.md`. For the brief schema additions this requires, see `docs/cloris-brief-multi-module-extensions.md`.

## 1. Target population

Computational biologists and bioinformaticians (PhD or equivalent industry experience, 3-8 years) for biopharma roles; MD-PhDs bridging clinical research and AI; clinical data scientists with biobank or EHR experience; structural biologists with drug discovery focus; epidemiologists for public-health AI applications; regulatory scientists with FDA-engagement experience.

The defining signals: PubMed authorship within target MeSH categories, OpenAlex citation depth in biomedical concepts, ClinicalTrials.gov investigator records, current affiliation at biopharma/biotech/academic medical center.

Excluded: pure clinical practitioners with no research output; lab technicians without first-author publication record; regulatory consultants without FDA-public-record evidence.

## 2. Buyer persona

- Biopharma companies doing data-science hiring (AstraZeneca, Pfizer, Genentech, Vertex, Regeneron, smaller publicly-listed biotechs).
- AI-in-healthcare startups (Recursion, Insitro, Tempus, Flatiron, Insilico, AbridgeAI).
- Biotech recruiting firms (Slone Partners, Klein Hersh, Bowdoin Group's life-sci practice, Coda Search).
- Academic medical centers building research teams.

Pricing: per-search $250-$600 supplemental; firm-level $20K-$80K annual; enterprise $100K+ for biopharma.

The category is real and growing. Biopharma's competition for computational scientists is comparable in intensity to frontier AI's competition for ML researchers, and life-sciences candidates are systematically underrepresented in LinkedIn-centric sourcing because their identity lives more in publication record than career history.

## 3. Differentiation thesis

Same as Researcher. PubMed + OpenAlex evidence-grounded evaluation has no real competition. Existing tools (LinkedIn, biotech-specific recruiter tools) discover but do not evaluate; academic search tools evaluate papers but not researchers-for-hire.

The Healthcare extension is positioned as an additive surface within the Researcher module rather than a competing module. A biopharma customer onboarding to Cloris gets Researcher with the Healthcare extension enabled; no separate license SKU.

## 4. Strategic priority and roadmap fit

Priority **#3** in `Cloris-Module-Strategy.md` §4. Build third, after Researcher v1 ships.

Roadmap fit: Phase 3 (August-November 2026), in parallel with cross-module identity resolution. Prerequisites:

- Researcher module v1 shipped and stable.
- Phase 1 foundation work complete (already done before Researcher).

## 5. Data foundation

### 5.1 PubMed E-utilities (anchor)

API: `eutils.ncbi.nlm.nih.gov/entrez/eutils/` — `esearch`, `efetch`, `esummary`, `elink` endpoints. Free with NCBI API key. 10 req/s with key.

Coverage: comprehensive for biomedical research. ~36M+ citations indexed. Includes preprint cross-links to bioRxiv/medRxiv.

Identity quality: best biomedical author-affiliation data of any free source. Per-author affiliations stored since 2014. ORCID present in post-2017 records. Corresponding-author email occasionally embedded in `<AffiliationInfo>` strings — the closest free source to email contact data anywhere in academic publication metadata.

ToS: US government data, freely usable including commercial. No restrictions.

Verdict: anchor source for Healthcare extension.

### 5.2 OpenAlex (already in Researcher module)

Used for citation depth and h-index validation. The Researcher module's existing OpenAlex adapter covers biomedical works as well as ML works; no separate adapter needed.

### 5.3 ClinicalTrials.gov

API: `clinicaltrials.gov/api/v2/` (REST, structured). Free. Returns trial metadata including investigators (named), sponsors, study locations, phase, condition.

Useful for: identifying clinical investigators by trial history. A computational biologist who has been listed as an investigator on Phase 2 oncology trials at a target institution is a strong fit for a biopharma role in oncology.

Verdict: enrichment for Healthcare extension. Used to surface clinical-trial-investigator history when a candidate's profile references trial work.

### 5.4 bioRxiv / medRxiv (via PubMed cross-links)

Preprint feeds. Already linked from PubMed records. No separate adapter — PubMed integration covers cross-references.

### 5.5 Sources considered and rejected

- **Embase, Web of Science, Scopus.** Commercial, expensive ($10K+/year minimum). PubMed + OpenAlex coverage is sufficient for v1 of the Healthcare extension. Revisit in v2 if customer signal indicates coverage gaps.
- **MedRxiv as primary source.** Better as a cross-link via PubMed; the discovery surface is PubMed.

## 6. Source-specific brief calibration

The Healthcare extension uses the same `ResearcherCalibration` dataclass and `arxiv_category_signals` capability-area extension as the parent Researcher module. The MeSH-specific extensions:

```python
# in shared/brief_schema.py:CapabilityArea
mesh_term_signals: list[str] = field(default_factory=list)  # e.g., ["Oncology", "Drug Discovery", "Genomics"]
clinical_trial_phase_signals: list[str] = field(default_factory=list)  # ["Phase 1", "Phase 2", etc.]
```

For Healthcare-targeting briefs, the brief author populates `mesh_term_signals` instead of (or in addition to) `arxiv_category_signals`. The Researcher module's evaluation procedure consumes both; PubMed adapter searches by MeSH terms, OpenAlex adapter searches by concepts.

Module-level calibration (existing `ResearcherCalibration`) gains optional Healthcare fields:

```python
# in shared/brief_schema.py:ResearcherCalibration
clinical_trial_investigator_minimum: int = 0
clinical_trial_phase_floor: str = ""  # "" | "phase_1" | "phase_2" | "phase_3"
mesh_canonical_terms: list[str] = field(default_factory=list)
```

These are inert when the brief targets non-healthcare research; only Healthcare-targeting briefs populate them.

Pre-built brief templates (`config/brief-templates/healthcare/`):

- `computational-biologist-biopharma.json`
- `bioinformatician-academic-medical-center.json`
- `clinical-data-scientist.json`
- `md-phd-translational-research.json`
- `regulatory-scientist-fda-experienced.json`

## 7. Evaluation pipeline mapping

Identical to Researcher. Snippet evidence is author summary plus top 5 PubMed papers; full evidence is complete publication record plus abstracts plus affiliation history plus optionally ClinicalTrials.gov investigator history.

Depth distinction translates: builder = active biomedical researcher publishing first-author papers in target capability areas, optionally including clinical-trial investigation; user = clinical practitioner or industry-applied person citing research without producing it.

Decision contract: standard `SAVE` / `REJECT` / `INFERENTIAL_SAVE`. No new types.

## 8. State machine fit

Existing Researcher lifecycle maps directly. Same work-unit kind (`RESEARCHER_AUTHOR_QUERY_KIND`) used for Healthcare queries — no new kind needed because the discovery pattern is identical. The PubMed adapter is just another `researcher/sources/<source>.py` file alongside OpenAlex, Semantic Scholar, dblp, arXiv.

## 9. Identity disambiguation

Common-name disambiguation strategy is identical to Researcher. PubMed has the advantage of better affiliation data than arXiv (per-author affiliations stored since 2014), so disambiguation is moderately easier in biomedical fields than in CS / ML. ORCID coverage in PubMed is higher than in arXiv (post-2017 records widely include ORCID).

Cross-source identity within the Healthcare extension: PubMed author IDs, OpenAlex author IDs, dblp PIDs (if applicable for computational biologists), ClinicalTrials.gov investigator IDs. Cross-referenced via ORCID when present, or via name + affiliation + co-author patterns otherwise.

## 10. Reconciliation strategy

Same as Researcher: reconcile to LinkedIn via `researcher/recruiter_identity_resolver.py` plus `shared/cross_module_identity/researcher_to_linkedin.py`.

For biomedical researchers without LinkedIn (academic-track researchers, especially clinicians whose LinkedIn presence is minimal), the candidate stays per-source. Recruiter outreach happens via institutional email (often discoverable via PubMed `<AffiliationInfo>`) or via co-author network introductions.

## 11. Save destination

Standard: `["candidate_workspace"]` for healthcare-only briefs; `["linkedin_recruiter", "candidate_workspace"]` for multi-module briefs that include LinkedIn.

Outreach generation extends `researcher/outreach.py` with biomedical-specific copy: references specific publications, optional reference to clinical-trial work if applicable, framing of industrial vs. academic opportunity.

## 12. Build effort estimate

Total: **1-2 weeks** atop Researcher.

Breakdown:

- `researcher/sources/pubmed.py`: 4 days. NCBI E-utilities client, MeSH-term search, author affiliation extraction, ORCID cross-linkage.
- `researcher/sources/clinical_trials.py`: 2 days. ClinicalTrials.gov investigator search.
- Brief schema additions (`mesh_term_signals`, `clinical_trial_*`): 1 day.
- Healthcare-specific facial calibration patterns (research vs. clinical practitioner discrimination): 1 day.
- Pre-built Healthcare brief templates (5 templates): 2 days.
- Tests: 2 days.

Total: ~12 person-days = ~2 calendar weeks at split-attention pace.

## 13. First-customer demonstration scope

Demo brief: "Senior Computational Biologist for a Series-C biopharma in oncology drug discovery. PhD or equivalent, 5+ years industry or academic-translational experience, first-author publications in genomics or computational drug discovery within the last 24 months, US or EU."

What the module produces: PubMed-discovered authors filtered by MeSH terms (oncology, drug discovery, genomics), cross-validated against OpenAlex citation graph, evaluated using the standard Researcher evaluation procedure with biomedical brief calibration. Saves include named researchers with publication history, current affiliation (often a biopharma or academic medical center), LinkedIn match where available.

## 14. Ship-quality scope

Beyond the demo: ClinicalTrials.gov investigator integration, MeSH-driven query strategy (vs. OpenAlex concept-driven), biomedical-specific brief authoring tooling, integration with the closed feedback loop.

## 15. Failure modes and edge cases

- **PubMed identity ambiguity for clinicians.** Many clinicians publish under slightly varied name forms (Jane M. Doe, J.M. Doe, Jane Doe MD). PubMed disambiguation is decent but imperfect. Strategy: require ORCID or affiliation match for high-confidence identification; otherwise surface as ambiguous.
- **Translation between MeSH and OpenAlex concepts.** OpenAlex uses its own concept hierarchy; PubMed uses MeSH. The brief author populates both via `arxiv_category_signals` (for OpenAlex concepts) and `mesh_term_signals`. The strategy formation step queries both APIs in their native vocabularies.
- **Clinical investigators who don't publish.** Some MDs participate in trials without authoring papers. They appear in ClinicalTrials.gov but not in PubMed. The module surfaces them via the trial-investigator path; the evaluation may flag them as `INFERENTIAL_SAVE` due to thin publication evidence.

## 16. Open questions

- **Embase / Scopus integration in v2.** Customer-driven; revisit if biopharma customers report coverage gaps from PubMed alone.
- **MD-PhD specific brief patterns.** This cohort straddles clinical practice and research; evaluation calibration may need MD-PhD-specific patterns. V1 covers them adequately via existing brief schema; v2 may add explicit support.

## 17. Decisions captured here

- 2026-04-29 — Healthcare ships as a Researcher extension, not a standalone module.
- 2026-04-29 — PubMed is the anchor; ClinicalTrials.gov is enrichment.
- 2026-04-29 — V1 ships PubMed + ClinicalTrials.gov adapters atop the existing Researcher module; commercial paid-source integration (Embase, Scopus) deferred to v2.
- 2026-04-29 — V1 build target is 1-2 calendar weeks atop Researcher v1.
