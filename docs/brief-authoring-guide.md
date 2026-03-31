# Brief Authoring Guide

This guide walks you through writing a brief for the autonomous sourcing agent. The brief carries ALL role-specific evaluation criteria — the pipeline's templates, adaptation logic, and bias controls read from it. A well-written brief is the single highest-leverage input to the system.

If you're trying to socialize brief-writing with recruiters and recruiting managers, or you need to translate unfamiliar roles into agent-ready criteria, start with `docs/team-brief-translation-playbook.md` and fill `docs/agent-brief-intake-template.md` before drafting the JSON.

The questions below map directly to fields in the brief schema. Answer each one. If you're using preflight (Opus generates a draft from the JD), use this guide to review what it produces — preflight fills gaps with generic criteria, and generic criteria compound into either false positives or false negatives over hundreds of evaluations.

---

## 1. Role Identity

**What is the exact title, level, and 2-3 sentence summary of what this person does day-to-day?**

Not a rephrased JD. A synthesized description of the work. The summary should answer: "If I watched this person work for a week, what would I see them building?"

*FDL example: "Translates research goals into concrete data specifications, RL environment designs, and evaluation frameworks that improve frontier model training. Owns the technical bridge between what researchers need and what the data/environment infrastructure produces."*

Bad example: "A technical leader who works on AI/ML projects and collaborates with cross-functional teams." This describes every ML role. The evaluation template injects this summary into every prompt — if it's generic, the evaluator has nothing to anchor against.

---

## 2. Capability Areas (3-7)

**What are the distinct domains that define this role's scope?**

Each capability area should be a type of work the role does — not a skill, not a keyword, not a team name. Think: "What are the 3-7 things this person might spend a quarter building?"

For each area:

- **Name**: Short, specific. "Post-Training Data & RLHF Pipelines" not "AI/ML."
- **Description**: What work in this area looks like at this level.
- **Builder signals**: Specific evidence that someone BUILDS in this area. Project types, methodologies, outputs. What would you see on a profile?
- **User signals**: Specific evidence that someone USES outputs from this area. This is the false positive boundary — profiles that list similar keywords but do different work.
- **Key terms** (optional): Terms that discriminate builders from users. Terms only builders would use.

The capability areas are the anchors for Step 1 of every evaluation. If you get these wrong, the evaluator either maps everything (too broad) or nothing (too narrow).

**How to test**: Take 5 candidates you've already evaluated correctly (3 saves, 2 rejects). Can you map each save to a specific capability area with evidence? Does each reject fail to map? If a reject maps to a capability area, the area is defined too broadly.

---

## 3. Depth Distinction

**What does "building" mean for this specific role? What does "using" mean?**

This is the single most important calibration point. The depth distinction is the boundary between "relevant to the role" and "works in the same general space."

- **Builder definition**: What specific artifacts, systems, or outputs does the role create? The answer should describe what the person's work FEEDS INTO. For FDL: "the output feeds into model training, not into a business application."
- **User definition**: What does the application-layer version of this work look like? The answer should describe what someone who USES the builder's outputs does. For FDL: "Fine-tunes or deploys pre-trained models for business use cases."
- **Edge case guidance**: How to handle borderline profiles. What tips the balance?

**How to test**: Take the candidate who was your hardest correct reject — someone who looked relevant but wasn't. Does the depth distinction explain why? If not, refine it.

---

## 4. Non-Fit Patterns (3-8)

**What are the most common profiles that will appear in search results, look adjacent, and aren't a fit?**

Each non-fit pattern describes WORK, not titles or keywords. The format:
- **Label**: Short identifier.
- **Description**: What this person actually builds every day.
- **Why not**: Why their work doesn't connect to the role despite surface similarity.
- **Examples**: Concrete examples — "fraud detection at Nubank" not "data science."

Non-fit patterns are checked AFTER capability mapping in the evaluation template. They're not "hard skips" (which triggers avoidance) — they're evidence that the candidate's actual work doesn't connect to the role.

**How to test**: Run your most common search strings mentally. What are the top 3 profile types that will flood results and waste evaluation tokens? Those are your non-fit patterns.

**The critical pitfall**: Don't make non-fit patterns too broad. "Data science" is not a non-fit pattern — it describes half the candidates. "Applied ML for business metrics (fraud, recommendations, ad targeting)" is a non-fit pattern — it describes specific work that isn't the role.

---

## 5. Employer Signal Rules

**How much does company name matter for this search?**

Define 3-4 tiers and for each one, specify what additional evidence is required beyond the employer name:

- **Frontier lab** (OpenAI, Anthropic, DeepMind, etc.): What's the minimum evidence needed beyond the employer name?
- **Strong AI company**: What specific evidence distinguishes a relevant role from an application-layer role at this company?
- **General tech** (strong companies with mostly-applied ML): This is typically the highest false-positive tier. What evidence separates the 2% doing relevant work from the 98% doing applied ML?
- **Neutral**: Same standard as any candidate — employer carries no weight.

**The key question for each tier**: Can you save on employer + relevant title alone, or do you always need project/publication/team evidence?

For almost every search, the answer is: employer alone is never sufficient. The one exception might be a search where the employer IS the domain — e.g., if you're sourcing for a BFSI AI role, someone leading AI at a major bank has domain relevance built in.

---

## 6. Minimum Bar

**What do the minimum years of experience actually mean in practice?**

Not just a number — a description of what those years should contain. "4-5+ years hands-on building deep learning systems where data quality or model behavior was the primary output" is meaningful. "3+ years of experience" is not — it passes everyone with a 3-year-old LinkedIn account.

---

## 7. Facial Triage Calibration

**What are the obvious non-fits that can be detected from a snippet?**

Remember what the facial stage actually sees: name, headline, current title/company, location, education line, and a **career history** (title + company + dates for every visible position). It does NOT see job description bullets, project details, or skills. You cannot tell from this data what someone actually built at a given company.

### Fast Exit Patterns

These should be things where the ENTIRE career trajectory is clearly outside scope. Not "current title is X" — every position points away. Examples: entire career is IT support, entire career is sales/BD, entire career is analytics/BI with no ML engineering positions.

If you're unsure whether something is a fast exit, it isn't. The facial stage should be permissive.

### Trajectory Patterns (the most important facial calibration)

The career history is the highest-signal field at the facial stage. Three categories:

**YES patterns** — career trajectories that favor passing to full evaluation:
- What employer/title combinations strongly suggest relevance? (e.g., "any position at a frontier AI lab in a technical role")
- What career progressions suggest depth? (e.g., "research → industry ML transitions")
- What specific keywords in titles are near-certain signals? (e.g., "RL" or "post-training" anywhere in any title)

**AMBIGUOUS patterns** — trajectories that default to YES because you can't resolve them from a snippet:
- This is the critical category. "ML Engineer at Nubank" is ambiguous — could be fraud detection (reject) or training infra (save). The facial stage CANNOT make this call. These MUST default to YES.
- Any role where the title is generic enough to span multiple domains (ML Engineer, Data Scientist, Applied Scientist) at a company with both relevant and irrelevant ML work.

**NO patterns** — trajectories that favor rejection, but ONLY if the entire history matches:
- What careers, when viewed across all positions, have zero plausible connection? (e.g., "entire career is data analytics/BI with no ML engineering positions at any point")
- These should be strong enough that seeing even ONE exception in the trajectory would flip to ambiguous.

**How to test**: Take 5 candidates who were facial YES but ultimately rejected at full evaluation. Were they ambiguous (correct facial YES, full eval resolved correctly) or fast exits (should have been caught at facial)? If they were legitimately ambiguous, the facial stage is working. If they were obvious non-fits detectable from trajectory alone, add the pattern.

### Expected YES Rate

What percentage of search results do you expect to survive facial triage?
- Dense market, broad strings: 40-60%
- Moderate targeting: 25-45%
- Narrow/senior search: 15-30%

---

## 8. Market Density

**Is this a dense, moderate, or sparse talent market?**

This controls pagination depth in the adaptation layer.
- **Dense**: Many plausible candidates per string. Brazil ML engineers, Bay Area SWEs.
- **Moderate**: Normal distribution. Default.
- **Sparse**: Few plausible candidates per string. Embodied AI in Latin America, niche research domains.

---

## Final Checklist

Before running the pipeline:

- [ ] Can you map 3 known-good candidates to specific capability areas with evidence from the brief?
- [ ] Does the depth distinction correctly reject your hardest correct-reject candidate?
- [ ] Are non-fit patterns specific enough that they describe work, not job titles?
- [ ] Does the employer signal rule for the highest-risk tier (usually general_tech) require specific evidence?
- [ ] Is the minimum bar description meaningful, not just a year count?
- [ ] Have you reviewed preflight's confidence notes (if using preflight)?
- [ ] Is the employer blacklist set (you probably don't want to source people from your own company)?
