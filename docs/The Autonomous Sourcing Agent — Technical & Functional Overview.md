The Autonomous Sourcing Agent
From Prototype to Production

Sam Vangelos — Senior Recruiter, Applied AI & GTM Turing

March 2026

CONTENTS

1 What This Is Now
2 The Two-Model Architecture
3 How It Searches Autonomously
4 How It Evaluates
5 The Multi-Agent Orchestration Layer
6 How It Hides in Plain Sight
7 When Things Break
8 Colombia: The First Production Campaign
9 What Changed From the Prototype
10 What's Next


What This Is Now

Two weeks ago, I published a document describing what a prototype sourcing agent had produced: 69 pipeline candidates from 23 hours of sourcing, a save accuracy that improved from 18% to 100% across sessions, and an evaluation depth that hiring managers would recognize as expert-level. That prototype ran on a single expensive model — Claude Opus controlling everything through an open-source agent framework called OpenClaw — and I funded it personally.

The document ended with three constraints: one expensive model doing everything, a browser automation layer that crashed regularly, and no organizational funding. The system described here solves the first two.

Opus no longer reads DOM elements, clicks buttons, or parses HTML. A cheap model — GPT-4o-mini or Gemini Flash, running at roughly 1/50th the cost per call — handles every mechanical browser task. Opus receives only structured summaries and makes only the decisions that require sourcing judgment: facial triage, full candidate evaluation, search strategy, and real-time adaptation. The browser automation layer has been rebuilt from scratch without OpenClaw, with crash recovery, reconnection logic, and interaction patterns modeled on empirical data about how humans actually move a mouse and scroll a page.

The more consequential change is that the prototype ran search strings I wrote. The current system writes its own. Given a sourcing brief — the JD, intake notes, candidate archetypes, minimum bar, evaluation criteria — the agent formulates a search strategy, generates compound Boolean strings, executes them against LinkedIn Recruiter, and adapts in real time. It narrows noisy searches, abandons dead-end strings, broadens overfit queries, and generates supplementary strings to fill coverage gaps it identifies during execution. An existing Boolean search kit, if one exists for the role, serves as vocabulary that the agent can draw from — but the brief is the anchor, and the agent operates with or without a kit.

The system now runs as a multi-agent architecture: a session orchestrator manages sourcing within hard safety limits, a decoy agent generates passive LinkedIn browsing activity between and during sourcing bursts, and a governor enforces caps on profile opens, session duration, and operating hours with no override mechanism. The entire day cycle is autonomous. The agent sources for 1.5 to 3 hours, enters a dormant period with ambient browsing, resumes for another session, and cycles until its daily budget is spent or the operating window closes.


The Two-Model Architecture

The prototype's cost problem was structural: Claude Opus spent most of its tokens on work that requires no judgment. Reading a page of 25 candidate cards, extracting names and titles from DOM text, parsing a profile panel into structured fields — these are mechanical tasks that burned through the context window at full Opus pricing while the evaluation calls that actually justify that cost represented a small fraction of total token usage.

The current system separates extraction from judgment entirely. Two functions in the codebase — `cheap_llm()` and `opus_llm()` — route every model call, and there is no ambiguity about which model handles which task. The cheap model (configurable between GPT-4o-mini and Gemini Flash) handles all DOM extraction and text parsing: reading search results pages into structured candidate snippets, extracting full professional histories from profile panels, and any other task that transforms unstructured browser text into structured data. Opus handles every decision that requires sourcing judgment: facial triage from snippet text alone, full candidate evaluation against the brief's criteria, strategy formation from the JD and kit vocabulary, page-level adaptation after each set of results, and block-level adaptation after completing batches of search strings.

The cost structure has inverted. Opus no longer sees raw HTML; it sees pre-processed signal. The per-candidate evaluation cost is a fraction of what it was, and the agent can paginate through substantially more results before hitting the same budget ceiling. Every LLM call — both cheap and Opus — is wrapped in exponential backoff retry with up to 5 attempts and increasing waits, catching transient errors (429 rate limits, 502/503 server errors, 529 overloaded) and retrying automatically. If 5 consecutive calls fail even after retries, a circuit breaker pauses the pipeline for 60 seconds before continuing. If a facial judgment call fails entirely, the agent defaults to FACIAL_YES so the candidate proceeds to full evaluation rather than being permanently lost — the fallback is tagged in the decision rationale for visibility.


How It Searches Autonomously

The prototype's Session 7A pointed toward this capability: the agent ran 12 freestyle strings it had built from accumulated evidence, compared their results, identified the strongest performer and explained why, discovered talent nodes the kit had never targeted, and proposed three follow-on strings with exact Boolean syntax. The current system formalizes that into a deliberate pipeline — and it starts not from a search kit, but from the sourcing brief.

THE BRIEF AS ANCHOR

The agent's strategic input is the brief: the JD text, intake notes, role description, minimum bar, candidate archetypes (what good looks like), noise archetypes (what to avoid), known noise patterns from prior campaigns, search priorities, permanent filters like geography and location, and — for V2 briefs — structured evaluation criteria including capability areas, depth distinction definitions, non-fit patterns, employer signal rules, and facial calibration parameters.

If the brief carries a raw JD without structured evaluation criteria, the agent runs a preflight phase before strategy formation: Opus generates capability areas, depth distinctions, non-fit patterns, employer signal rules, and facial calibration from the JD text alone, producing a structured evaluation framework that the operator reviews and locks in before the agent begins searching. The agent can start from nothing more than a job description and generate its own evaluation architecture.

If a Boolean search kit exists for the role — a library of terms organized by competency domain — the agent fetches it and extracts structured vocabulary: every Boolean string organized by block, subblock, and type. These kit strings never appear in the execution queue. They are building blocks that Opus can draw from when synthesizing compound queries, cross-gating terms from multiple competency clusters into targeted searches that no individual kit string could produce. The kit accelerates strategy formation; it does not anchor it. The brief anchors it.

STRATEGY FORMATION

Opus receives the full brief context — JD, intake, archetypes, minimum bar, noise patterns, search priorities, instructions, permanent filters — along with kit vocabulary if present. In a single call, Opus synthesizes compound Boolean search strings: targeted queries that combine terms across competency domains, cross-cutting filters that surface candidates who span multiple archetype categories, and coverage gap strings that target areas the existing vocabulary doesn't reach. The output is an execution plan with ordered search strings organized into blocks of five for mid-run adaptation, each with a rationale explaining what population it targets and why.

For the Colombia FDL campaign, Opus synthesized 33 compound strings from the brief context and kit vocabulary — more strings than a human sourcer would typically write for a single role, each more precisely targeted than any individual kit string.

TWO-PHASE PAGINATION

Not all search strings deserve the same depth. A string returning 150 results can be paginated exhaustively; a string returning 6,000 needs triage. For strings above 3,000 results, the agent enters a scout phase: it evaluates only page 1, and Opus decides whether to commit to deeper pagination, narrow the search by adding AND clauses, or abandon the string entirely. Page 1 of LinkedIn's relevance ranking represents the best results the algorithm will surface for that query — if page 1 is noise, deeper pages will be worse.

Once committed to pagination, the agent works through results page by page, and after each page Opus reviews accumulated statistics — save rate, facial YES rate, duplicate rate, candidate quality trends — and decides the next action: continue, narrow, broaden, stop, or abandon. When Opus narrows a search, the current Boolean is pushed onto a refinement stack; when it broadens, the stack pops and the previous Boolean is restored. The agent maintains a full refinement history and can navigate the specificity gradient in either direction. Minimum pagination depth prevents premature stops: strings with 500+ results must review at least 3 pages before Opus can call stop or abandon.

BLOCK-LEVEL ADAPTATION

After completing each batch of approximately 5 strings, the agent runs a block adaptation. Opus reviews the batch's performance — total saves, save rate, top-performing strings, zero-save strings — and can generate supplementary strings to fill gaps, adjust the approach for the next batch, or skip remaining strings in an underperforming block. This is the Session 7A diagnosis capability — 24 Coding Precision strings producing zero saves, the agent identifying the structural problem and building a replacement — formalized into the execution cycle rather than requiring a human to notice the failure.


How It Evaluates

The evaluation pipeline has not changed in kind since the prototype. The depth and specificity that distinguished Session 7A's assessments — identifying that "rejection sampling" in a chip design context is a Monte Carlo technique for circuit simulation rather than the RLHF training method, or mapping a candidate's Isaac Sim infrastructure work across four separate roles spanning six years — operate with the same capability in the current system. What changed is the infrastructure around those evaluations: the separation of extraction from judgment, the bias monitoring, and the error resilience.

Every candidate on a search results page passes through a fixed sequence. The cheap model parses the raw DOM text into structured candidate snippets — name, title, company, location, summary text — and the agent cross-references each extracted name against the DOM's href attributes to establish reliable profile URLs for deduplication. The candidate's URL is checked against a session-level set of already-processed URLs; duplicates are skipped without an LLM call. If the brief specifies blocked employers, the candidate's current company is checked before any model is invoked — matches receive an instant FACIAL_NO with no API cost.

The first Opus call is the facial judgment: the snippet text alone, with no profile opened, evaluated against the brief. Opus returns FACIAL_YES or FACIAL_NO with rationale. This is the gate that prevents the expensive operation — opening a full profile, extracting its contents, running a full evaluation — from being wasted on candidates who are clearly not a fit based on their title, company, and summary text.

Candidates that pass facial triage proceed to full profile extraction. The agent opens the profile panel, the cheap model extracts the complete professional history into a structured summary, and Opus evaluates the full profile against the brief's criteria. The output is a decision — SAVE, REJECT, INFERENTIAL_SAVE for strong inference from limited data, or TRANSFERABLE_SAVE for adjacent experience that transfers to the role — with detailed rationale mapping the candidate's background against the brief's archetypes and minimum bar. Saves are executed via the LinkedIn Recruiter save button with ghost-cursor interaction and dialog confirmation.

For V2 briefs with bias control specifications, the agent tracks decision distributions across strings and flags anomalies: unusually high rejection rates on specific strings, concentration of saves in narrow candidate profiles, or statistical patterns that suggest the evaluation criteria are producing skewed outcomes. Alerts are categorized by severity and logged for human review.


The Multi-Agent Orchestration Layer

The prototype ran a single loop: start browser, enter search strings, evaluate candidates, stop when I interrupted it. The current system operates as a coordinated multi-agent architecture where three components — the session orchestrator, the session governor, and the decoy agent — manage sourcing within hard safety constraints across a full operating day.

The session orchestrator is the top-level process. It runs pre-session checks (time window, daily session cap, 24-hour profile budget), launches a sourcing session with a duration sampled from a log-normal distribution (median approximately 2 hours, clamped between 1.5 and 3 hours), transitions to a dormant period (also log-normal, median approximately 110 minutes, clamped between 75 and 180 minutes) with the decoy agent running passive browsing, and cycles until the daily budget is exhausted or the operating window closes. Session durations and dormant periods are sampled fresh each cycle; no two operating days have the same timing fingerprint.

The session governor enforces hard limits with no override mechanism: 3 hours maximum per session, 200 profile opens per session, 400 profile opens per rolling 24-hour window, 3 sessions per calendar day, and an operating window from 7:00 AM (jittered ±30 minutes per instance to avoid exact-hour patterns) to a rigid 1:00 AM ceiling. These are constants in the governor's source code, not configuration values. The governor monkeypatches the browser's profile-open methods to count every open at the source — before the open happens, not after — and raises an exception if any limit is reached. Session counting is work-based: only sessions that actually opened profiles count toward the daily cap, so aborted launches and test runs don't consume session slots.

The decoy agent operates on core LinkedIn surfaces — the feed, notifications, and jobs — and never touches Recruiter. It scrolls through the feed with human-like timing, checks notifications, browses job listings, all weighted by frequency (jobs 5:feed 3:notifications 1) and executed in randomized bursts. During sourcing sessions, the orchestrator periodically pauses the pipeline at a safe checkpoint, runs a decoy burst, then resumes sourcing — interleaving passive browsing with active sourcing so the account's activity pattern is indistinguishable from a recruiter who checks their feed between candidate evaluations.


How It Hides in Plain Sight

The prototype used raw Playwright automation: instant clicks, immediate page loads, no scrolling behavior, no reading time. Every interaction was machine-fast and machine-precise — exactly the behavioral signature that platform-side detection systems are built to identify.

The current system produces browser behavior that is, at the individual interaction level, indistinguishable from a human sourcer. Every click follows a Bézier curve trajectory generated by the python_ghost_cursor library, which models empirical human mouse movement data: the mouse moves from its current position to the target element along a randomized path with acceleration and deceleration, not a straight line teleport. Page scrolling uses the mouse wheel in 40–150 pixel increments with 15–60 millisecond inter-chunk delays, producing the visual rhythm of a human scrolling through content rather than programmatic scrollIntoView calls.

When the agent opens a candidate profile, it scrolls through the panel in 200–400 pixel chunks with 1.5–4 second dwell per section, producing 8–20 seconds of visible reading behavior before extracting the text. All inter-event delays follow log-normal distributions with temporal autocorrelation: each delay is blended with the previous delay using a correlation weight of 0.3, producing the clustered timing patterns that characterize human attention shifts — a long pause makes the next pause slightly longer, and vice versa. Uniform random delays, by contrast, are detectable by entropy-based classifiers with near-100% accuracy.

Every 25–35 minutes of continuous activity, the agent takes a 70–240 second idle break. When running under the session orchestrator, decoy interleave bursts replace these cadence pauses — the agent pauses sourcing, runs a burst of feed scrolling or job browsing, then resumes — so the activity pattern includes the ambient behaviors that characterize normal LinkedIn usage rather than sustained, unbroken Recruiter activity.

Taken together, these systems produce a behavioral fingerprint that is not merely randomized — it is modeled. Log-normal timing, Bézier mouse trajectories, correlated delays, chunked scrolling, profile reading simulation, cadence pauses, decoy interleaving, jittered operating windows, and log-normal session durations all operate simultaneously. The agent's browser behavior is not "random enough to avoid detection." It is structurally identical to the behavior it is imitating.


When Things Break

The prototype had no resilience. A single API error killed the session. A browser crash lost all in-flight work. The Colombia campaign's 102 consecutive Anthropic 529 "overloaded" errors — all concentrated in a 23-minute window during String 5 — would have silently lost every affected candidate. Every resilience system described here was built in direct response to a failure encountered in production.

Every LLM call is wrapped in exponential backoff retry: up to 5 attempts with increasing waits (2s, 4s, 8s, 16s, 32s plus jitter) for transient errors including rate limits, server errors, and overloaded responses. If 5 consecutive calls fail even after retries, a circuit breaker pauses the pipeline for 60 seconds before continuing — preventing the retry logic from hammering a degraded endpoint. If a facial judgment call fails entirely, the agent defaults to FACIAL_YES so the candidate proceeds to full evaluation rather than being permanently lost; the fallback is tagged in the rationale for downstream visibility.

If Chrome crashes mid-string, the agent enters a reconnection loop: 6 attempts at 10-second intervals, saving progress before the first attempt. If the browser comes back, the agent reconnects, marks the current string as partially complete, and continues to the next string. Progress is saved after every string completion, and the Ctrl+C handler saves immediately on interrupt. The `--resume` flag picks up from the last saved state, reprioritizing any interrupted string to the front of the queue. The `--restart-string N` flag resets a specific string to page 1, clearing all its output data and rebuilding the dedup set — built specifically for the Colombia scenario where String 5 needed to be re-run from scratch while preserving the work done on Strings 1 through 4.

Graceful shutdown follows a two-stage protocol: the first Ctrl+C sets a cooperative stop flag so the agent finishes its current candidate evaluation and saves progress cleanly; the second Ctrl+C raises an immediate interrupt for situations where the agent is stuck in a blocking API call.


Colombia: The First Production Campaign

The Colombia FDL campaign is the first full production run of the current architecture: same Frontier Data Lead role as the Brazil prototype campaign, different geography, entirely autonomous search strategy.

The agent received a sourcing brief — role description, minimum bar, seven capability areas with depth distinction definitions, seven non-fit patterns, four employer signal tiers, facial calibration parameters, and an employer blacklist — along with a Boolean search kit URL. From the brief context and kit vocabulary, Opus synthesized 33 compound Boolean search strings organized into execution blocks with adaptation checkpoints, targeting specific cross-sections of the Colombia talent pool across reinforcement learning, coding agents, agentic systems, data quality infrastructure, STEM reasoning, LLM fine-tuning, and embodied AI.

Five of 33 strings completed before the 529 error cascade, producing 9 qualified saves from approximately 143 successful facial judgments. String 5 — targeting a broad population that returned 6,000+ results — triggered 102 consecutive Anthropic 529 "overloaded" errors in a 23-minute window, and every affected candidate was permanently lost because the system had no retry logic. The entire retry, circuit breaker, and fallback architecture described in the previous section was built in direct response to this incident.

The facial judgments that succeeded before the cascade showed the same evaluation depth as the prototype's best sessions. The 529 cascade was an infrastructure failure, not an evaluation failure — and the incident exposed the resilience gap so completely that the remediation is now the most thoroughly tested subsystem in the codebase.

Twenty-eight strings remain to be executed. The campaign resumes with the remediated system.


What Changed From the Prototype

| Dimension | OpenClaw Prototype (S1–S7A) | Current System (V5) |
|-----------|---------------------------|---------------------|
| Model architecture | 1 model (Opus for everything) | 2 models (cheap extraction + Opus judgment) |
| Search strategy | Human-written Boolean kit | Brief/JD-driven autonomous compound generation (optional kit vocabulary) |
| Adaptation | Manual — human notices failure, agent proposes fix | Automatic — page-level and block-level adaptation in the execution loop |
| Browser behavior | Raw Playwright (instant clicks, no scroll) | Ghost-cursor Bézier trajectories, log-normal timing, chunked scrolling, profile reading simulation |
| Session management | Manual start/stop, single session | Governor-enforced limits, multi-session day cycling, log-normal durations |
| Anti-detection | None | Decoy agent, humanistic timing, cadence pauses, time-of-day patterns |
| Resilience | None — single error kills session | Retry with backoff, circuit breaker, crash recovery, fallback decisions, progress persistence |
| Agent framework | OpenClaw (third-party) | Purpose-built orchestration (no external dependencies) |
| Operating window | When human is watching | 7 AM – 1 AM autonomous, 3 sessions/day, 400 profiles/24h |

The evaluation quality — the depth, specificity, and accuracy of the agent's candidate assessments — has not changed. The Barbara Neves rejection, the Carlos Costa identification, the Caio Viturino simulation infrastructure analysis: these represent the same capability that Opus brings to the current system. What changed is everything surrounding those evaluations — how the agent finds candidates to evaluate, how it decides what to search, how it behaves in the browser, how it recovers from failures, and how it governs its own operating tempo.


What's Next

Every campaign produces structured byproducts: string-level save rates, keyword collision mappings, talent node identifications, noise archetype patterns, block adaptation decisions. The Colombia campaign will produce 33 strings' worth of performance data that feeds directly into the next campaign's strategy formation. The system already does this within a single run — block adaptation uses prior block performance to adjust the approach for the next batch — and the next step is making this work across campaigns, so a string that performed well sourcing FDL candidates in Brazil automatically informs the FDL search in Colombia.

A Greenhouse MCP server — already built, 73 tools, connected to Turing's ATS instance via OAuth2 — enables end-to-end pipeline management: the agent saves a candidate on LinkedIn, creates the corresponding Greenhouse record, attaches the evaluation rationale as a note, and moves the candidate to the appropriate pipeline stage. The sourcing workflow closes the loop from "found on LinkedIn" to "in the ATS ready for review" without human intermediation.

With trained models and a library of calibrated briefs, the system can source against anticipated openings — roles the team knows are coming based on client patterns, expansion plans, or recurring demand — before anyone submits a requisition. When the req opens, the team starts with a pipeline of evaluated candidates and a written record of the market landscape, not a blank project.

Each phase unlocks only when the previous one is reliable. Cross-campaign learning requires a track record of successful campaigns to learn from. Greenhouse integration requires the evaluation pipeline to be stable enough that automated ATS actions are trustworthy. Proactive sourcing requires both. The Colombia campaign, when it completes, provides the second data point. The infrastructure is built. The prototype proved the capability; the production system proves the architecture.
