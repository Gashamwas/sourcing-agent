# Forward Deployed Engineer (IC) Sourcing Demo

## Executive Readout for Recruiting Lead

### Headline

Across two sourcing runs for the IC Forward Deployed Engineer brief, the agent evaluated **801 candidates**, escalated **126** to deeper review, and surfaced **50 named saves** across the two run summaries in what was explicitly treated as a **tapped market**. The strongest results came from Boolean patterns that targeted **backend infrastructure builders who pivoted into GenAI**, **document-understanding / production GenAI engineers**, **founding engineers**, and **consulting / field engineers shipping GenAI into enterprise environments**.

### Side-by-Side Run Snapshot

| Metric | Run A | Run B |
|---|---:|---:|
| Strings executed | 20 of 37 | 17 of 34 |
| Strings skipped by adaptation | 17 | 17 |
| Total search results available | 44,732 | 39,693 |
| Pages reviewed | 65 | 45 |
| Candidates evaluated | 367 | 434 |
| Facial YES | 59 | 67 |
| Facial YES rate | 16.8% | 17.1% |
| Saves logged in run summary | 34 | 16 unique saves |
| Rejected after deeper review | 24 | 50 |
| Reported full-review save rate | 47.8% | 43.7% |

### What These Runs Demonstrate

The sourcing system was able to stay selective in a difficult market. In both runs, only about **17%** of evaluated candidates were escalated from the initial screen to deeper review, and once escalated, the system converted at a strong rate. That is the clearest signal that the facial screen was not merely broad keyword matching; it was functioning as a meaningful quality gate.

The highest-yield search patterns were not title-first searches. The best strings consistently targeted engineers with **production systems depth** and then layered in GenAI signals. The two most reliable examples were:

| High-Signal Pattern | Why It Worked |
|---|---|
| Backend frameworks × GenAI | Surfaced engineers with real distributed-systems and architecture depth who had layered agentic / LLM systems on top |
| Document understanding × production GenAI | Surfaced engineers who had actually shipped enterprise RAG, extraction, and knowledge workflows rather than merely experimenting with GenAI |

### Most Productive Candidate Pools

Across the two runs, the strongest candidate pools were:

| Candidate Pool | Evidence Across Runs |
|---|---|
| Consulting / field engineers shipping GenAI for clients | One of the richest veins in both runs; repeatedly surfaced high-fit profiles from MongoDB Field, BCG X, Slalom, Deloitte, KPMG, and adjacent teams |
| Backend engineers who pivoted into GenAI | The single most productive Boolean family, especially when paired with Temporal, Kafka, gRPC, FastAPI, and other production-system signals |
| Founding engineers / 0-to-1 builders | Repeatedly produced highly relevant candidates who owned end-to-end GenAI delivery in ambiguous environments |
| Big-tech or hyperscaler engineers with customer-facing or platform delivery experience | Surfaced strong profiles from Meta, Google, AWS, OpenAI, Apple, and Snowflake-adjacent environments |
| Financial-services and fintech builders | Consistently yielded candidates with the right mix of enterprise constraints, architectural depth, and recent GenAI work |

### Strongest Candidate Signals Repeatedly Observed

The highest-confidence saves consistently showed some combination of:

- Production **RAG / retrieval-augmented generation**
- **Agentic / multi-agent** workflows
- Strong **backend / distributed systems** grounding
- Evidence of **enterprise delivery** or building for customers
- Ownership language such as **built from scratch**, **shipped**, **deployed**, or **architected**

Representative high-confidence profiles surfaced across the runs included:

- **Paul-Emile Brotons (0.92)**: MongoDB field / consulting engineer shipping RAG and agentic systems across enterprise verticals
- **Raj Pathak (0.88)**: OpenAI and founding-team Amazon Bedrock Agents / Knowledge Bases pedigree
- **Sherif Attia (0.88)**: FactSet agent orchestration and evaluation-framework depth
- **Chris Ruppelt (0.88)**: Goldman Sachs pedigree with consecutive founding / production GenAI builds
- **Jason Shi (0.88)**: Snowflake customer-facing LLM delivery plus Slalom consulting background

### What the Agent Learned Mid-Run

The adaptation engine behaved in a way that was useful for recruiting rather than merely exhaustive:

- It **skipped canonical / tapped pools** such as exact-title FDE searches and direct competitor poaches where marginal value was expected to be low.
- It correctly **de-prioritized high-noise areas** such as prompt engineering, HITL workflows, and broad executive-title searches.
- It generated productive adaptive strings from early signal, especially around:
  - consulting × GenAI delivery
  - fintech × founding / staff × LLM builders
  - 0-to-1 builder language
  - backend-engineer-turned-agentic-builder archetypes

One especially important finding was that **consulting / professional-services engineers with real GenAI delivery evidence** were a richer pool than expected. That pattern contributed a large share of the most compelling saves in both runs.

### Key Failure Modes and Limits

The main failure mode was not poor sourcing logic; it was **mechanical truncation** on a handful of strings. Several strings with good underlying concepts were cut short by timeout or UI issues before they had a fair run, most notably:

- **String #16**: RAG × production evidence
- **String #12**: customer-facing engineers at AI companies
- **String #27**: broad CTO / VP startup search, which also appears structurally too broad
- **String #62**: overly narrow Google field-solutions sniper

### Recommended Next Step

The next run should lead with the strongest proven patterns rather than start broad:

1. Expand the **backend-framework × GenAI** family.
2. Re-run **RAG × production** strings that were truncated by infrastructure issues.
3. Double down on the **consulting / field-engineer** vein.
4. Expand **fintech / financial-services** and **healthcare / life sciences** vertical variants.
5. Add more strings around **delivery verbs** such as `shipped`, `deployed`, `built for`, and `delivered to`.

### Bottom Line

These two runs show that the agent is not simply generating generic AI profiles. It is learning which pockets of the market still produce credible IC Forward Deployed Engineer candidates, adapting away from tapped or noisy pools, and surfacing candidates whose backgrounds align with the actual role: **production systems builders who can deliver GenAI in complex enterprise settings**.
