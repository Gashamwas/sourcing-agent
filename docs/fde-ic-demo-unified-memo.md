# Forward Deployed Engineer (IC) Sourcing Demo

## Unified Synthesis Memo for Recruiting Lead

### Headline

Across two sourcing runs for the IC Forward Deployed Engineer brief, the agent showed that it can still surface credible candidates in a market the source reports explicitly describe as **tapped**. The clearest lesson from the two runs is that the highest-yield searches were not obvious title-led pools; they were capability-led Booleans aimed at **backend engineers who pivoted into GenAI**, **document-understanding and production-GenAI builders**, **founding and 0-to-1 engineers**, and **consulting or field engineers shipping GenAI into enterprise environments**.

### Top-Line Snapshot

| Metric | Combined View |
|---|---:|
| Candidates evaluated | 801 |
| Facial YES / deeper reviews | 126 |
| Reported facial pass rate | ~17% across both source reports |
| Reported full-review save conversion | 43.7%–47.8% |
| Named saves across the two source reports | 50 |
| Pages reviewed | 110 |
| Total search results available | 84,425 |

**Metric note:** The two source reports are not perfectly apples-to-apples. Run B separately notes **16 unique saves** and **45 total string-level save events**, so this memo stays with the more defensible phrasing: **“50 named saves across the two source reports.”** Likewise, the source reports themselves describe the facial pass rate as roughly **17%** in each run, so that framing is preserved here rather than forcing a new precision claim.

## 1. What the Runs Proved

The two runs tell a consistent story. First, the system was able to remain selective in a difficult market. In both reports, only a small share of evaluated profiles made it through the initial screen, and once a profile was escalated to deeper review, conversion remained strong. That is the strongest evidence that the facial screen was doing real filtering rather than merely matching broad keywords.

Second, the agent’s adaptation behavior was disciplined rather than exhaustive. Across the two runs, it skipped **34 strings** that were judged to be canonical, redundant, or structurally high-noise. That is important in a tapped market: the value did not come from searching everything, but from deciding what **not** to spend review time on.

Third, the strongest results repeatedly came from searches that encoded **production systems depth first** and layered GenAI on top, rather than starting with senior titles or generic AI language and hoping build evidence would emerge later.

## 2. Highest-Yield Sourcing Patterns

| Pattern | Source Evidence | Why It Mattered |
|---|---|---|
| **Backend frameworks × GenAI** | String **#4** was the workhorse in both reports, with **17 saves from 6 pages** and the highest absolute yield | It operationalized the core FDE insight: the best candidates are often backend or systems engineers who have layered LLM and agentic delivery onto real distributed-systems depth |
| **Document understanding × production GenAI** | String **#2** produced **10 saves from 5 pages** in both reports and was described as one of the highest-precision strings | It captured a canonical enterprise GenAI deployment pattern: engineers who actually built extraction, document intelligence, and RAG workflows |
| **Founding / 0-to-1 builders** | String **#19** produced **5 saves from 46 results**, and String **#37** added **6 saves** via builder-language targeting | These strings surfaced engineers who had owned full-stack delivery in ambiguous environments, which maps directly to the role |
| **Consulting / field delivery builders** | String **#15** and its follow-ons were repeatedly called out as one of the richest veins; String **#63** added **7 saves**, and String **#65** sustained yield over 6 pages | This pool produced engineers who scope ambiguous problems, ship into client environments, and build reusable GenAI patterns across engagements |

Two patterns deserve special emphasis because they cut across both runs. The first is the **backend-framework signal**: terms like Temporal, Kafka, gRPC, FastAPI, and adjacent infrastructure markers were powerful proxies for architectural judgment. The second is the **document-understanding / enterprise RAG pattern**, which repeatedly surfaced engineers who had actually shipped GenAI into practical enterprise workflows rather than merely experimenting with models.

The strongest supporting strings reinforced the same picture. **#19** proved that a tiny pool of founding engineers could be extraordinarily efficient. **#37** showed that targeting language such as “built from scratch” and “0-to-1” can work as well as explicit technical terms. And the consulting spawn chain off **#15** validated that this is not a fringe pocket of the market; it is one of the most productive sources of FDE-shaped IC talent.

## 3. What Candidate Profile Emerged

The two runs converged on a very consistent candidate archetype. The best candidates were usually not pure ML researchers, prompt specialists, or senior managers. They were more often one of the following:

- **Backend engineer → GenAI pivot**: strong systems or distributed-systems grounding, then recent LLM / agentic delivery work
- **Consulting or field delivery IC**: engineers who personally built and shipped GenAI systems for enterprise clients
- **Founding or early AI startup engineer**: 0-to-1 builders who owned the full stack out of necessity
- **Big-tech or hyperscaler platform / customer-facing builder**: engineers at Meta, Google, AWS, Apple, OpenAI, Snowflake, and adjacent environments with recent production GenAI depth
- **Financial-services or fintech builder**: engineers operating under enterprise constraints who had made a credible GenAI pivot

The named examples that appear most convincingly across the source reports fit that pattern cleanly:

- **Paul-Emile Brotons (0.92)**: MongoDB consulting and field engineer shipping RAG and agentic systems across enterprise environments
- **Raj Pathak (0.88)**: OpenAI plus founding-team Bedrock Agents pedigree
- **Sherif Attia (0.88)**: FactSet agent orchestration and evaluation-framework depth
- **Chris Ruppelt (0.88)**: Goldman Sachs pedigree plus consecutive founding / production GenAI builds
- **Jason Shi (0.88)**: Snowflake customer-facing LLM delivery plus Slalom consulting

The recurring technical signals were equally consistent: **RAG**, **agentic or multi-agent workflows**, **backend / distributed-systems grounding**, **enterprise integrations**, and delivery-oriented verbs like **built**, **shipped**, **deployed**, and **architected**. The source reports also repeatedly note **evaluation frameworks and guardrails** as emerging positive signals, especially among the stronger enterprise-facing candidates.

## 4. What Did Not Work

The clearest underperformer was the **title-first executive search**. String **#27** — a CTO / VP search at small startups — produced a **22,000-result pool** and zero saves. Both reports interpret that correctly: title-led seniority searches without strong technical qualifiers are structurally wrong for an IC Forward Deployed Engineer brief.

The reports also consistently rejected the idea that canonical FDE pools were the right place to spend time. Exact-title or exact-company searches around obvious competitors were treated as **tapped** and often skipped outright. That was not conservative behavior; it was rational behavior in an already-worked market.

Other clear low-value patterns included:

- **Prompt-engineering-led strings**, which were repeatedly identified as skewing toward non-builder profiles
- **Overly narrow micro-pool snipers**, such as **#62**, where the addressable population was simply too small to survive repeated narrowing
- **Support-automation / HITL / loosely customer-success-oriented strings**, which were judged likely to attract adjacent but non-builder profiles

It is also important to separate conceptual failures from mechanical ones. A handful of strings were hurt by **timeouts or UI truncation** rather than weak underlying logic. The reports repeatedly point to:

- **#16**: RAG × production evidence
- **#12**: customer-facing engineers at AI companies
- **#11**: hands-on agent infrastructure

These should be treated as **infrastructure-truncated** strings, not as evidence that those concepts lack value.

## 5. What We Would Do Next

The next run should not restart broad. It should begin with the patterns the two reports already validated.

1. **Expand backend-framework × GenAI variants.**  
   Build follow-ons around adjacent infrastructure signals such as event-driven systems, APIs, vector-store operators, IaC-adjacent deployment ownership, and other markers of production systems judgment.

2. **Retry the truncated RAG and customer-facing strings.**  
   In particular, **#16** and **#12** deserve a clean rerun because the reports treat them as mechanically interrupted, not conceptually invalid.

3. **Deepen the consulting / field-engineer vein.**  
   Both reports identify this as one of the richest underexplored pools. The next run should lean harder into consulting firms, vendor field teams, and adjacent enterprise-delivery organizations.

4. **Expand fintech and healthcare / life sciences variants.**  
   Financial services and fintech already showed strong results. Healthcare and pharma were repeatedly cited as the next promising vertical where enterprise GenAI delivery signals should translate well.

5. **Use delivery verbs and customer qualifiers more aggressively.**  
   The source reports repeatedly suggest the value of phrases such as `built for`, `deployed for`, `delivered to`, `customer`, `client`, and `engagement` when they are combined with concrete technical signals rather than used alone.

### Bottom Line

Taken together, the two runs show that the agent is not simply finding generic AI talent. It is learning where **IC Forward Deployed Engineer** signal actually lives on LinkedIn: among production systems builders who have moved into GenAI delivery, especially when that work is done in consulting, field, startup, or enterprise environments that require ambiguity tolerance, architectural judgment, and customer-oriented execution. That is the central recruiting insight these runs validated.
