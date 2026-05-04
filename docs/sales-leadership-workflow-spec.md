# Sales Leadership Workflow Spec

Status: ready-to-implement
Owner: Sam
Last updated: 2026-04-29

The Sales Leadership workflow is a LinkedIn module configuration plus sales-leadership-specific Perplexity prompt variants and confidence calibration. It is not a separate source module — there is no source-of-truth database for sales performance because quota attainment data is not public. The workflow synthesizes the best-available public evidence (company stage during tenure, headcount growth, industry vertical, GTM motion type, occasional press coverage) into recruiter-actionable candidate evaluations.

This spec follows the shape in `docs/cloris-module-template.md`. For why this is a workflow not a module — and why the original audit's "skip" recommendation was reframed via founder pushback — see `Cloris-Module-Strategy.md` §2.6.

## 1. Target population

VPs of Sales, CROs (Chief Revenue Officers), and enterprise AE leaders with verifiable performance signals at companies in defined growth stages. Specifically:

- People who built outbound motions from scratch (SDR-to-AE pipeline architecture, comp design, territory model).
- People who scaled SDR teams through multiple hiring cycles.
- Enterprise sellers who closed multi-million-dollar deals in defined verticals (fintech, healthcare IT, cybersecurity, DevTools, AI infrastructure).
- VPs of Sales at companies that scaled headcount during their tenure (a public signal of GTM motion success).

Excluded: sales executives whose primary differentiation is sales-specific certifications without performance evidence; sales leaders at companies with no public funding/headcount signal; pure transactional/inside sales roles at high volume (different recruiting market).

The cohort is a subset of the LinkedIn module's general L7+ senior-role population (`shared/brief_schema.py:454`'s `is_senior_role()`). What changes is the evaluation approach — direct evidence from publication record or technical artifacts is unavailable; contextual inference from public signals does the work.

## 2. Buyer persona

- VC-backed companies scaling their first GTM team.
- PE portfolio companies doing operational turnarounds (PE firms placing CROs into portfolio companies).
- Executive search firms serving SaaS companies (Bowdoin Group, Glocap, BeRecruited).

Pricing: in line with the LinkedIn module ($1.5K-$4K/seat-month for in-house teams; $20K-$60K firm-level annual for boutique sales recruiting firms). The workflow is positioned as a LinkedIn-module value-add, not as a flagship offering; pricing premium is modest.

Why these buyers cannot solve the problem with existing tools: LinkedIn search alone surfaces the cohort but does not synthesize public evidence beyond LinkedIn into structured evaluation. Apollo and ZoomInfo provide contact data without GTM-context evaluation. The workflow's contribution is the Perplexity-augmented synthesis of company-stage and growth context, structured against the brief's GTM-architecture builder/user calibration.

## 3. Differentiation thesis

Honest framing, repeated from `Cloris-Module-Strategy.md` §2.6:

"Best available automated synthesis of public evidence for sales leadership profiles."

Not "evidence-grounded evaluation equivalent to Researcher" — that framing fails because quota attainment, deal history, and pipeline numbers are not public. The differentiation is:

- The synthesis quality (contextual inference from company stage + headcount growth + vertical + GTM motion type) is materially better than unassisted LinkedIn search.
- The confidence calibration is honest about lower confidence bands (0.40-0.70 vs. 0.60-0.95 for technical roles), surfaced to the recruiter.
- The workflow's `PostSaveModifier` patterns make evidence basis explicit ("strong company-growth signal during tenure", "press mention of award-recognition", etc.).

Position as a complement to LinkedIn-native sales recruiting workflow, not as a category-defining product. Don't lead with this on the platform homepage. Don't claim Researcher-level evidence quality.

## 4. Strategic priority and roadmap fit

Priority **#5** in `Cloris-Module-Strategy.md` §4. Build in Phase 4.

Roadmap fit: Phase 4 (November 2026 – February 2027), in parallel with Defense engineering. Prerequisites:

- `shared/external_evidence/provider.py` Perplexity infrastructure already in place.
- LinkedIn module's senior-role calibration shipped (already done).
- Phase 1 foundation work complete.

Customer development for sales recruiting firms: parallel workstream in Phase 3.

## 5. Data foundation

### 5.1 LinkedIn (existing module)

Primary data source. The LinkedIn module already covers VP-of-Sales-level discovery via boolean strings calibrated to the role. The workflow adds sales-specific brief calibration vocabulary, not new discovery surfaces.

### 5.2 Perplexity via `shared/external_evidence/provider.py`

Existing infrastructure. The workflow adds sales-leadership-specific prompt variants:

- **Company stage during tenure.** "What was [Company]'s stage (seed, Series A, B, C, D, public, post-IPO) during [Person]'s tenure as VP Sales [start year] – [end year]? What was the funding round at start of tenure? What was the funding round at end of tenure?"
- **Headcount growth during tenure.** "What was [Company]'s approximate headcount at the start of [Person]'s tenure? At the end of tenure? Sources?"
- **Industry vertical and GTM motion.** "What was [Company]'s primary industry vertical and GTM motion (PLG, enterprise, channel, hybrid) during [Person]'s tenure? What was their primary customer segment (SMB, mid-market, enterprise)?"
- **Press mentions and award recognition.** "Has [Person] been mentioned in industry press, named in deal announcements, won sales-leadership awards, or spoken at SaaStr/Pavilion/Sales Hacker conferences? What context?"
- **Public methodology content.** "Has [Person] published GTM methodology content on LinkedIn, Substack, or industry blogs? What positions have they taken publicly on sales architecture or comp design?"

Each prompt produces structured output that becomes part of the candidate's `ExternalCandidateEvidence` payload, consumed by `full_judge_with_external_evidence` in `shared/judger.py:649`.

### 5.3 Crunchbase (optional v2)

Useful for company-stage and funding-event verification. Commercial API ($10K+/year minimum). V1 uses Perplexity-augmented company context (already available, $0 marginal cost for calls already made). V2 integration is customer-driven if Perplexity coverage proves insufficient.

### 5.4 Apollo / ZoomInfo (out of scope)

These are contact-data products. The workflow does not pursue contact data; that is the recruiter's separate workflow once Cloris surfaces a candidate. Cloris's job is discovery + evaluation, not contact provisioning.

### 5.5 Sources considered and rejected

- **RepVue self-reported quota attainment.** Small, opt-in, biased sample. Doesn't generalize to the broader cohort.
- **Glassdoor compensation data.** Anonymized; cannot be tied to specific candidates.
- **ZoomInfo / Apollo bulk import.** Out of scope.

## 6. Source-specific brief calibration

The workflow does not introduce a new module-level calibration dataclass — it reuses the existing LinkedIn brief schema with sales-leadership-specific values in the existing fields:

**Capability areas** populated for sales leadership:

- "GTM Architecture" — builder = designed segmentation/territory/comp; user = managed a team executing someone else's playbook.
- "Pipeline Generation" — builder = built outbound motion from scratch, scaled SDR; user = managed inbound-only or pipeline-attribution.
- "Enterprise Closing" — builder = closed multi-million-dollar deals with multi-stakeholder negotiation; user = transactional closing or smaller-deal-size.
- "Team Scaling" — builder = hired and developed sales teams through multiple cycles; user = managed a stable team.
- "Vertical Expertise" — defined per brief.

**`employer_signal_rules`** calibrated for sales context:

- Tier 1 (frontier_gtm): named-fast-growth SaaS at Series B-D during tenure (Figma, Linear, Notion-class growth).
- Tier 2 (proven_gtm): late-stage public SaaS where a sales leader could have built or maintained but contextual evidence required.
- Tier 3 (general_tech): tech companies at large scale where GTM is mature and the leader's specific contribution is unclear without further evidence.
- Tier 4 (low_signal): companies without public stage/growth signal.

**`PostSaveModifier`** patterns for confidence calibration:

```python
PostSaveModifier(
    name="Company growth during tenure",
    trigger="When public sources confirm 3x+ headcount growth or 2+ funding rounds during tenure",
    if_present="Boost confidence by 0.10-0.15",
    if_absent="No adjustment",
    signals=[
        "Crunchbase or Perplexity-confirmed funding rounds during tenure",
        "LinkedIn company headcount data showing 3x+ growth",
    ],
)
```

```python
PostSaveModifier(
    name="Public methodology content",
    trigger="When candidate has published structured GTM methodology content publicly",
    if_present="Boost confidence by 0.05-0.10; surface content in workspace",
    if_absent="No adjustment",
    signals=[
        "Substack or LinkedIn long-form posts on sales architecture",
        "Conference talk at SaaStr / Pavilion / Sales Hacker",
        "Named contributor to industry methodology framework",
    ],
)
```

Confidence bands explicitly lower for the sales workflow (encoded in the brief's evaluation calibration):

- `SAVE`: 0.55-0.70 (vs. 0.80-0.95 for technical roles).
- `INFERENTIAL_SAVE`: 0.40-0.55 (vs. 0.45-0.50 for technical L7+).
- `TRANSFERABLE_SAVE`: 0.45-0.60.

Pre-built brief templates (`config/brief-templates/sales/`):

- `vp-sales-series-b-c-saas.json`
- `cro-pe-portfolio-company.json`
- `enterprise-ae-leader-cybersecurity.json`
- `head-of-revenue-ai-infrastructure.json`
- `vp-channel-sales-saas.json`

## 7. Evaluation pipeline mapping

Standard LinkedIn pipeline with the existing `shared/judger.full_judge_with_external_evidence` path used for SAVE-eligible candidates. The Perplexity augmentation is the key — for sales leadership candidates, the augmentation adds the company-stage/growth context that would otherwise be implicit.

The judgment template extends the existing senior-role calibration block with sales-specific instructions:

> For sales leadership roles, weight contextual inference from company stage and growth heavily. A VP Sales at a company that scaled from 80 to 400 employees during their tenure is providing strong builder evidence even without quota disclosure. Treat the absence of public quota data as expected, not as an evidence gap.

The instructions are in the brief's `instructions: list[str]` field, populated by the brief templates.

## 8. State machine fit

No changes. Standard LinkedIn lifecycle and work-unit kinds. The workflow is brief-template-driven and prompt-driven; it does not change the state machine.

## 9. Identity disambiguation

Standard LinkedIn identity disambiguation via existing `linkedin/recruiter_identity_resolver.py`. Sales leaders are typically distinct individuals on LinkedIn (less common-name collision than mid-tier roles).

## 10. Reconciliation strategy

Standard LinkedIn reconciliation. No cross-module identity bridge needed because the workflow runs entirely within the LinkedIn module's identity space.

If the recruiter is also running the Researcher module against a related brief (rare edge case), cross-module identity resolution applies the standard adapter logic; sales leaders rarely overlap with researchers, so practical merge cases are uncommon.

## 11. Save destination

Standard: `["linkedin_recruiter", "candidate_workspace"]`. Same as the LinkedIn module's default.

The workspace renders sales leadership candidates with the contextualization payload visible: company-stage timeline, headcount-growth indicator, vertical and GTM motion summary, public methodology references when discovered. The recruiter reviews these alongside standard LinkedIn evidence.

Outreach generation extends `linkedin/` outreach with sales-leadership-specific copy: references the candidate's company-stage tenure, frames the role's GTM stage, signals expectations for the GTM architecture work.

## 12. Build effort estimate

Total: **2 weeks** at split-attention pace.

Breakdown:

- Sales-leadership-specific Perplexity prompt variants in `shared/external_evidence/provider.py`: 3 days. Five prompt variants per §5.2; tested for output quality and structured-extraction reliability.
- `PostSaveModifier` patterns for company-growth and methodology-content signals: 1 day.
- Confidence calibration adjustments in evaluation templates: 1 day.
- Pre-built sales leadership brief templates (5 templates): 3 days.
- Workspace rendering for sales-specific contextualization payload: 2 days. The "company stage during tenure" timeline and headcount-growth indicator are new visual elements.
- Documentation for honest positioning ("best available public evidence") in customer-facing materials: 1 day.
- Tests: 2 days.

Total: ~13 person-days = ~2 calendar weeks at split-attention pace.

## 13. First-customer demonstration scope

Demo brief: "VP of Sales for a Series B/C cybersecurity SaaS. Built outbound motion from scratch at a prior Series-B SaaS that scaled 3x during tenure. 8-15 years total sales experience. US East Coast or remote-US."

What the workflow produces: LinkedIn-discovered candidates filtered by capability-area calibration; Perplexity-augmented evidence on company stage, headcount growth, and GTM motion for each high-confidence candidate; contextualization-aware confidence scoring (lower bands than technical roles, made explicit to the recruiter); workspace cards showing both the LinkedIn evidence and the Perplexity-derived company context.

Customer expectation setting: "This module surfaces sales leadership candidates with the best available synthesis of public context. Quota attainment and specific deal history are not public; the workflow does not infer them. The recruiter validates direct performance evidence in conversation."

## 14. Ship-quality scope

Beyond the demo: Crunchbase API integration for v2 verification of Perplexity-derived company stage; expanded brief templates (CMO, Chief Revenue Officer of public companies, GM of business unit); workflow-specific telemetry on confidence-band drift over time; integration with Cloris's brief-iteration feedback loop (recruiter feedback on saves' actual quota performance, when discovered post-conversation, refines the modifier patterns).

## 15. Failure modes and edge cases

- **Perplexity-derived company context is wrong.** Perplexity occasionally fabricates company-stage details. Strategy: cross-validate against multiple Perplexity calls; require the evidence to cite sources; surface low-confidence company context to the recruiter as "Perplexity-derived, not independently verified."
- **Company name collision.** "Lever" the recruiting platform vs. "Lever" the financial services firm. Strategy: disambiguate via tenure dates + industry vertical.
- **Stealth-mode period.** Some sales leaders had stealth-mode tenures (founder-stage) without public funding signal. Strategy: surface as `INFERENTIAL_SAVE` with thin-evidence flag; recruiter validates.
- **Overconfident scoring on weak evidence.** The lower-confidence bands are explicit but model can drift. Strategy: ongoing telemetry on save-to-confirmation rate; if confidence is materially miscalibrated, adjust band parameters in brief templates.
- **Buyer disappointment vs. positioning.** Customers may expect Researcher-grade evidence quality. Strategy: position honestly in customer onboarding; lead with "best available public evidence" framing; show the contextualization output explicitly so customers see what the workflow does and doesn't surface.

## 16. Open questions

- **Crunchbase integration timeline.** Useful but expensive. Customer-driven decision: if customers explicitly request more rigorous company-stage data than Perplexity provides, prioritize Crunchbase.
- **Sales-specific feedback loop.** Recruiter discovers the candidate's actual quota performance post-conversation (e.g., from reference calls). Should that data feed back into the workflow's calibration? V1: no, recruiter notes capture it but no automated calibration. V2: structured feedback path.
- **Self-reported quota attainment from public sources (LinkedIn posts, RepVue).** Sometimes candidates self-disclose. The workflow could include this as a modifier; v1 doesn't because the signal is biased and inconsistent. V2 if customer pull indicates value.

## 17. Decisions captured here

- 2026-04-29 — Sales Leadership ships as a LinkedIn workflow configuration, not a separate module.
- 2026-04-29 — Workflow uses the existing `shared/external_evidence/provider.py` Perplexity infrastructure with sales-specific prompt variants.
- 2026-04-29 — Confidence bands are explicitly lower for sales (0.55-0.70 SAVE vs. 0.80-0.95 for technical). Honesty about evidence sparsity is a feature.
- 2026-04-29 — V1 build target is 2 calendar weeks at split-attention pace.
- 2026-04-29 — Position as LinkedIn-module value-add, not as flagship offering. Don't lead with this on the platform homepage.
- 2026-04-29 — Crunchbase integration deferred to v2; Perplexity covers v1 needs.
