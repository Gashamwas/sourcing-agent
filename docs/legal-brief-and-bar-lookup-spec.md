# Legal Brief and Bar Lookup Spec

Status: opportunistic
Owner: Sam
Last updated: 2026-04-29

Legal recruiting in Cloris does not warrant a separate module. The LinkedIn module already covers legal-professional discovery well — attorney profiles on LinkedIn are unusually rich, with self-reported practice areas, deal experience, and bar admissions stated more clearly than most engineers describe their technical work. What's missing for serious legal recruiting use is (a) a calibrated brief vocabulary for legal practice areas and (b) a verification side effect that confirms bar admission status from official sources.

This spec is the smallest unit of work that makes Cloris credible as a legal recruiting tool. It is not a module build; it is brief-template authoring plus a lightweight side-effect addition.

For the strategic context, see `Cloris-Module-Strategy.md` §2.8. For the LinkedIn module this spec extends, see the existing `linkedin/` directory.

## 1. Target population

Associates (3-8 PQE, post-qualification experience), partners at AmLaw 100/200 firms, in-house counsel at mid-to-large companies, federal law clerks transitioning to practice. Specifically:

- M&A associates with cross-border deal experience.
- IP litigators with semiconductor or biotech specialization.
- Privacy and regulatory counsel (data privacy, financial services regulatory).
- General counsel candidates for Series B/C technology companies.
- Federal law clerks transitioning to firm or in-house practice.

Excluded: paralegals, legal operations roles, trial consultants, public defenders (different recruiting market with limited LinkedIn signal).

## 2. Buyer persona

Legal search firms (Major Lindsey & Africa, Lateral Link, BCG Attorney Search, Macrae, boutique firms specializing in IP / privacy / financial services regulatory). In-house legal recruiting at F500 and high-growth tech companies. Law schools' Office of Career Services teams doing alumni placement.

Pricing: in line with the LinkedIn module ($1.5K-$4K/seat-month). The legal addition is a brief-template + bar-lookup convenience, not a premium module.

Why these buyers cannot solve the problem with existing tools: LinkedIn search alone returns too many false positives for legal roles ("counsel" appears on many LinkedIn titles in non-attorney contexts). Bar admission verification is currently a manual step in the recruiter's workflow. The two enhancements (calibrated brief + bar lookup) materially improve the LinkedIn module's legal recruiting use case without requiring a separate module.

## 3. Differentiation thesis

Modest. The existing LinkedIn module is already adequate for legal recruiting; the brief templates and bar lookup polish the use case rather than create a category-defining product. Don't lead with this in commercial positioning; offer it as a quality-of-life improvement for legal-recruiting-firm customers.

## 4. Strategic priority and roadmap fit

Priority **#9** in `Cloris-Module-Strategy.md` §4. Opportunistic — ships when customer pull emerges, not on a scheduled phase.

If a legal recruiting firm becomes a paying customer in 2026, prioritize the brief templates immediately (~1-2 days of work) and add the bar lookup over the following 1-2 weeks. If no legal customer signal materializes by early 2027, defer indefinitely.

## 5. Data foundation

### 5.1 LinkedIn (existing module)

Primary discovery surface. The LinkedIn module's existing evaluation pipeline handles legal candidates with appropriate brief calibration; no source-adapter changes needed.

### 5.2 State bar admission databases

Each US state bar publishes an attorney lookup web interface. ~44 states publish online; some require captcha or have ToS restrictions on programmatic access. None offer a unified API.

Examples:
- California: `apps.calbar.ca.gov`. Web form lookup, returns admission date, status (active/inactive/disciplined), bar number.
- New York: `iapps.courts.state.ny.us/attorneyservices/`. Similar.
- Texas: `www.texasbar.com/AM/Template.cfm?Section=Find_a_Lawyer`. Similar.

Implementation strategy for the bar lookup side effect: per-state polite scraping with caching. Each lookup is a single attorney by name; the recruiter triggers it after Cloris surfaces a candidate. Not bulk; not on every save automatically.

ToS posture: most state bars permit lookup for legitimate professional purposes; bulk redistribution is restricted. The recruiting use case (per-candidate verification) is well within reasonable use.

### 5.3 Federal court records (CourtListener / RECAP)

`courtlistener.com` exposes a free REST API (5,000 queries/hour authenticated). RECAP archive mirrors PACER. Useful for verifying named litigators by case history.

Integration scope: enrichment side effect for IP-litigation-focused briefs. Surface each saved candidate's named-attorney appearances in federal cases over the last 5 years.

Verdict: enrichment, not anchor. Use for litigation-specific briefs only.

### 5.4 Sources considered and rejected

- **PACER direct.** $0.10/page billing makes bulk use cost-prohibitive. CourtListener/RECAP covers the federal-court use case at no marginal cost.
- **Martindale-Hubbell.** Commercial directory; data quality is mid-2010s vintage. Not a useful primary source for 2026 legal recruiting.
- **Westlaw / Lexis Profilers.** Paid-enterprise; integration cost not justified by the recruiting use case.
- **Vault rankings / Above the Law editorial.** Useful market context, not candidate data. Brief author can reference these manually when calibrating an AmLaw-firm brief.
- **AmLaw firm bio scraping.** Cloudflare-hostile in 2026; high detection risk; ToS unfriendly. Skip.

## 6. Source-specific brief calibration

No new schema fields required beyond what exists in the V2 brief schema. Legal-specific calibration is encoded entirely via existing fields:

- `capability_areas` populated for legal practice areas (e.g., "M&A Transactional", "IP Litigation", "Privacy and Data Regulation").
- `employer_signal_rules` calibrated for AmLaw firm tiers (V100, V20, AmLaw 50, etc.).
- `non_fit_patterns` filtering out paralegals, legal-ops roles, and non-attorney legal staff.
- `instructions` field includes legal-specific evaluation guidance ("PQE matters more than AmLaw rank for laterals; clerkship signals are strong for transactional and litigation alike").

Pre-built brief templates (`config/brief-templates/legal/`):

- `senior-ma-associate-amlaw-100.json`
- `ip-litigator-semiconductor-focus.json`
- `privacy-counsel-tech-saas.json`
- `general-counsel-series-b-tech.json`
- `federal-clerk-transitioning-to-firm.json`

Each template populates the V2 brief schema with worked legal exemplars. The brief authoring guide (`docs/brief-authoring-guide.md`) gains a section on legal-specific brief calibration (PQE handling, clerkship-as-pedigree, AmLaw-tier signaling).

## 7. Evaluation pipeline mapping

Standard LinkedIn pipeline. The evaluation procedure works without modification — capability mapping (M&A vs. IP vs. privacy), depth test (transactional builder vs. document-reviewer), transferability (cross-border experience as transferable methodology), employer signal rules (AmLaw tier weighting).

The brief's instructions field guides the model on legal-specific edge cases:

> Bar admission status is verified by a separate side effect, not by your evaluation. Treat self-reported bar admission on LinkedIn as preliminary evidence; flag candidates whose self-reported admission cannot be verified via the bar lookup side effect for recruiter follow-up.

## 8. State machine fit

No changes. Standard LinkedIn lifecycle.

## 9. Identity disambiguation

Standard LinkedIn identity disambiguation. Attorney names are typically distinct on LinkedIn; common-name handling via existing `linkedin/recruiter_identity_resolver.py`.

The bar lookup side effect uses the verified candidate name (post-LinkedIn-resolution) plus state(s) where the candidate self-reports admission. Lookup confirms admission date, status, and bar number; mismatches are surfaced as a `verification_warning` flag in the workspace.

## 10. Reconciliation strategy

Standard LinkedIn reconciliation. Cross-module identity bridges not needed (legal attorneys rarely overlap with researcher / GitHub / defense candidates).

## 11. Save destination

Standard: `["linkedin_recruiter", "candidate_workspace"]`. The workspace renders the bar admission verification result alongside the standard LinkedIn evidence:

```
Bar admissions verified:
- New York: admitted 2018, active, bar #5612345
- California: admitted 2021, active, bar #345678
Self-reported on LinkedIn: NY, CA — match.
```

Or, when verification fails:

```
Bar admissions verified:
- New York: admitted 2018, active, bar #5612345
Self-reported on LinkedIn: NY, CA — partial match (CA not found).
```

The recruiter sees the discrepancy and follows up with the candidate.

For litigation-focused briefs, an optional CourtListener side effect surfaces the candidate's named-attorney case history:

```
CourtListener federal case appearances (last 5 years): 14 cases, primarily SDNY and DDel; case types: patent infringement (10), commercial disputes (4).
```

## 12. Build effort estimate

Total: **1-2 weeks** for everything.

Breakdown:

- Pre-built legal brief templates (5 templates) plus brief authoring guide section: 3 days.
- Bar lookup side effect at `shared/side_effects/bar_lookup.py`: 5 days. Per-state lookup logic with polite scraping, caching, ToS-compliant rate limits. 3-5 highest-volume states in v1 (CA, NY, TX, FL, IL); other states added on customer request.
- CourtListener side effect at `shared/side_effects/court_listener.py` (optional, only if litigation-focused customer): 3 days.
- Workspace rendering for bar verification results: 2 days.
- Tests: 2 days.

Total: ~15 person-days = ~2-3 calendar weeks at opportunistic pace.

## 13. First-customer demonstration scope

Demo brief: "Senior M&A associate, 5-7 PQE, AmLaw 100 firm currently, NY or DE bar admission, cross-border deal experience preferred."

What the workflow produces: LinkedIn discovery surfaces ~50-150 candidates; standard evaluation produces ~15-30 saves; bar lookup side effect verifies admission status for each save; workspace cards show LinkedIn evidence plus bar verification status. Recruiter reviews verified candidates first, follows up on partial-verification candidates.

## 14. Ship-quality scope

Beyond the demo: bar lookup coverage for all 50 states; CourtListener integration for litigation briefs; cross-validation between bar admission dates and LinkedIn-self-reported timeline; integration with brief iteration feedback loop.

## 15. Failure modes and edge cases

- **State bar website changes.** State bar sites occasionally redesign; per-state lookup logic is brittle. Strategy: monitor for failed lookups via telemetry; degrade gracefully (show "verification unavailable" rather than "verification failed").
- **Bar admission under different name.** Attorneys sometimes practice under maiden names or married names; legal name on the bar may differ. Strategy: surface ambiguity to recruiter; use birth-year cross-reference if available.
- **Disciplined or inactive attorneys.** Bar lookup returns active/inactive/disciplined status. Active disciplined status is a recruiter-relevant red flag; surface prominently.
- **Multiple bar admissions across states.** Many attorneys are admitted in 2-4 states. Strategy: lookup each state in parallel; render all results.
- **CourtListener thin coverage.** Federal court coverage is excellent; state court coverage varies. Strategy: limit case history to federal cases for v1.

## 16. Open questions

- **State coverage prioritization.** V1 covers CA, NY, TX, FL, IL (highest-volume states for legal recruiting). Other states added in priority order based on customer signal.
- **AmLaw firm bio scraping for partner-track verification.** Currently rejected due to Cloudflare-hostility and ToS. Revisit if a customer requires programmatic firm-bio verification and is willing to accept the risk.
- **Vault / Chambers ranking integration.** Editorial; manual brief-authoring reference rather than programmatic data source. Revisit only if customers ask.

## 17. Decisions captured here

- 2026-04-29 — Legal is a LinkedIn module configuration plus bar lookup side effect, not a separate module.
- 2026-04-29 — Bar lookup ships in v1 for 5 highest-volume states; expansion is customer-driven.
- 2026-04-29 — CourtListener is optional enrichment for litigation briefs; not in the v1 default.
- 2026-04-29 — V1 build target is 2-3 calendar weeks at opportunistic pace.
- 2026-04-29 — Don't lead with legal in commercial positioning; offer as a quality-of-life addition for legal-recruiting-firm customers.
