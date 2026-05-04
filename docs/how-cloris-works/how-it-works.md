# How Cloris Works

*A walk through the system, written for my siblings. Six chapters; about half an hour to read.*

---

## Chapter 1 — The Brief

You can't find the right person without first knowing what "right" means. That sounds obvious. It's the thing recruiting software gets wrong, and it was the first thing I had to fix to build Cloris.

Working a real search, the part that's actually in your head is the work nobody types into a search bar. Which companies count as frontier this quarter. What "senior" means at this customer specifically — their L5 is somebody else's L7. The four patterns that look like a fit and aren't. The two candidates from last month who taught you what to watch for. None of that is in the job description. All of it is what you're using to evaluate. Most recruiting tools dump it the moment you hit search.

So the first thing I built for Cloris wasn't the search engine. It was the place that knowledge gets to live. The place is called the *brief* — a JSON file, structured rather than prose, with named sections like `capability_areas` (what the person needs to do), `depth_distinction` (how I tell a builder from a user — a first-class field at `shared/brief_iteration.py:261`), `non_fit_patterns` (the people who look like fits and aren't, with examples and *why not*), `employer_signal_rules` (when "they worked at X" is enough and when it isn't), and a small set of `calibration_examples`: real candidates from past searches, labeled by me as strong saves, wrong saves, or borderline. There's even a field called `facial_calibration` that captures what fraction of profiles I'd expect this brief to say yes to. That number sounds boring. It's how the system catches itself drifting.

Two structural choices make this more than "JSON instead of prose." First: the brief is versioned. Every revision the system proposes after a run is a new file — `brief-frontier-ml-v1`, `-v1.1`, `-v1.4` — and the system literally refuses to run if it can't pick a unique latest (`shared/recruiter_brief_resolution.py:88-92`). Two siblings tied at the top, or one without a parseable suffix? It stops and asks. That sounds paranoid until you imagine the alternative: the AI quietly running against last month's brief while I think it's running against this week's, and nobody can tell the difference until the results are bad.

Second: revisions are clamped. When the LLM proposes how the brief should change after a run, the calibration thresholds can't move by more than 0.10 in a single revision (`shared/brief_iteration.py:71`). One weird run can't radically retune the role. Recruiter judgment converges over weeks of feedback, not in a single AI hallucination.

Everything else in Cloris reads from this one object. The judging AI uses it to evaluate candidates. The search system uses it to know what to look for. The reconciliation step that matches GitHub identities to LinkedIn profiles uses it to know which Recruiter project we're working in. When feedback comes back from a run, the brief is what gets revised. Cloris gets sharper at your role specifically because *the brief is the thing that learns*.

That's chapter one. Everything else is downstream.

---

## Chapter 2 — The Search

The brief tells you what you're looking for. The world has a few hundred million candidates. You will not read all of them, or even most of them, and most recruiting software papers over this gap with keyword search: type "ML engineer NYC," get a few hundred matches, hope the right person is in there. That works for the easy roles. For the actual work — finding the few people who are the right level, in the right slice of the field, and who would actually take a call — keyword search is wrong twice. It pulls in profiles that match the words but not the role. And it misses the people who don't describe themselves in the language of the job description.

So Cloris doesn't search. It plans, executes, and stops on principled grounds.

Each platform has its own pipeline because each platform is a fundamentally different problem. LinkedIn (`linkedin/orchestrator.py`) drives a real browser and works the recruiter surface — Recruiter Search, Recruiter Projects, profile pages. There's a whole sub-system underneath for what to search next: drift assessment, page insights, search variants, an experiment-state object that tracks what's been tried (`linkedin/search_intelligence.py`). The bot mimics human behavior — humanized timing, decoy clicks, profile-read simulation — because if it didn't, LinkedIn would notice and the session would be over.

GitHub (`github/orchestrator.py`) is a totally different problem. No browser. Pure API — you ask for repos by language, by stars, by recent activity; you ask for users by their commits, their orgs, their contribution graphs; you walk the social network of who maintains what. The doc comment at the top of the file actually says: "Pure API-based. Mirrors orchestrator.py's Pipeline pattern." But the *what* the orchestrator does is completely different from LinkedIn, even where the *shape* is the same.

What's identical between the two is the rest of the lifecycle. Every candidate moves through a state machine — `discovered → snippet_extracted → facial_started → facial_terminal → full_started → full_terminal` (`shared/runtime_state/store.py:62-71`). The store enforces the transitions. You can't skip a step. Snippet first (light evidence — the card on the search page), then facial (a quick yes/no on whether to look closer), then full evaluation (the deep look at the profile or portfolio). Every one of those decisions is recorded in the same `runtime_state.sqlite3` database.

Here's the part that surprised me when I built it. A person who shows up on both LinkedIn and GitHub is *two rows in the database*, not one. The unique constraint is `UNIQUE(brief_id, source, identity_key)` (`shared/runtime_state/store.py:182`). At the storage layer, sources are not merged. Cross-source identity resolution — figuring out that GitHub user `eribarrett` is the same person as LinkedIn profile `eri-barrett-12345` — is its own layer (`shared/cross_module_identity/`). I designed it this way on purpose. Adding a third source (we're doing researcher search next, off OpenAlex/PubMed/arXiv) doesn't require redoing the storage. It requires writing one new orchestrator and one new identity-adapter function. The substrate absorbs new modules.

The other thing about the search: it's bounded. Both pipelines plan a finite list of queries, execute them, and stop with a recorded reason. The LinkedIn resolver carries `planned_queries` (the plan the system built) and `queries_tried` (what it actually issued), plus a `stop_reason` field that takes one of: `score_above_threshold`, `high_confidence_match`, `no_new_urls`, `single_surface_name_variant_stop`, `plan_exhausted` (`shared/recruiter_identity_schemas.py:170-178`). When a run finishes, you can see exactly why each search ended. Most search tools don't track this — they just stop when they stop, and you can't tell whether they stopped because they finished, gave up, or hit a wall.

That's chapter two. The search is bounded, planned, and recorded. Each platform is its own problem. Storage doesn't conflate sources. Now the system has to decide who's actually a fit.

---

## Chapter 3 — The Judgment

A candidate has surfaced. The hard question now is whether they're actually right for the role.

The naive version of this is a relevance score — the AI looks at a profile and gives it a number. That's what most "AI-powered" recruiting tools do, and it's why they're not very good. The number doesn't mean anything because it doesn't decompose. You can't ask: are they at the right level? Are they doing the kind of work that actually counts? Have they done it deeply enough? Could they transfer their experience into ours? Those are different questions. A senior recruiter answers them separately. The score-style AI just gives you a vibes-rating and hopes.

Cloris's evaluation is structural. Every candidate, on every platform, goes through the same four-step procedure: capability mapping (which of this role's capability areas does this person hit?), depth test (have they actually done this work, or just been adjacent to it?), transferability test (if they're in an adjacent space, would the experience translate?), decision (with named rationale and named confidence). The procedure lives in `shared/judger.py` and is instantiated by per-platform judgment templates (`linkedin/judgment_templates.py`, `github/judgment_templates.py`) that just frame the evidence — what a LinkedIn snippet looks like vs. what a GitHub profile looks like. The evaluation logic is shared.

The procedure is paradigm-neutral. It works for ML researchers, defense engineers, biotech computational scientists, designers — without structural change. The role-specific calibration comes from the brief: capability areas, depth distinction, calibration examples, employer signal rules. Code does not embed role-specific vocabulary. It composes brief-supplied vocabulary into the procedure.

There are two stages. *Facial* is a quick triage on the snippet — is this profile worth opening? Output is `FACIAL_YES`, `FACIAL_NO`, or `FACIAL_BORDERLINE` (`shared/judger.py:38`). A yes goes to *full*, where the system actually opens the profile, builds a structured summary, and runs the four-step procedure to a decision. Output is `SAVE`, `REJECT`, or one of three nuanced save modes — `INFERENTIAL_SAVE`, `TRANSFERABLE_SAVE`, `SIGNAL_SAVE` — that mark the rationale (`shared/bias_controls.py:53-58`). A `TRANSFERABLE_SAVE` is the system saying "this person is in an adjacent specialty, and I think the experience translates" — which is the kind of judgment most search tools refuse to make at all.

The really interesting part, the part I'm proudest of, is the bias monitor. Every decision the system makes is recorded; a watcher (`shared/bias_controls.py`) looks for compounding patterns: too many consecutive saves on one search string, too many consecutive rejects, save-rate spikes, parse-failure rates, facial-rate anomalies. When a pattern fires, the system raises an Alert. Alerts have severity. Some are `flag` (log it, keep going). The big ones are `pause` — *stop the current search, surface to the operator*. There's an alert called `CONSECUTIVE_SAVES` whose code comment names the failure mode it protects against: *"Volume-threshold inversion — the Session 5 failure mode where the agent saves everyone because the population 'looks' relevant as a group"* (`shared/bias_controls.py:175-180`). That's the kind of thing that actually happens with autonomous systems if you don't watch for it. The system has to be able to look at its own behavior and know when it's drifting.

This is the part that makes the autonomous loop trustable enough to leave running. Not just that it judges well — that it knows when it might be judging badly, and stops itself before the damage compounds.

---

## Chapter 4 — The Run

A real autonomous search runs for hours, sometimes overnight. It hits rate limits. The browser disconnects. The laptop sleeps. The recruiter wants to pause it, change the brief, resume tomorrow. If the system loses state at the wrong moment, you've burned a recruiter's afternoon and learned nothing.

This is the part I spent the most time on. It's not glamorous and it doesn't show up in any demo. It's also the architectural choice that makes everything else possible.

Every run writes to a SQLite database called `runtime_state.sqlite3`, one per state directory (`shared/runtime_state/store.py`). The schema is small but load-bearing: `runs` (the actual run, with start time, status, stop reason, brief snapshot), `work_units` (each search query or string the system is working through), `candidates` (each person it has discovered), `candidate_attempts` (each attempt to evaluate that person, with stage and status), `events` (an append-only log of everything that happened), `side_effects` (the irreversible actions the system took — the LinkedIn save click, the outreach email, with idempotency keys so they don't fire twice). Every state change goes through this database. Every transition between lifecycle states is enforced by an `ALLOWED_LIFECYCLE_TRANSITIONS` graph (`shared/runtime_state/store.py:62-71`); the store rejects an illegal transition rather than just letting it through.

The other files you see in a run output — `progress.json`, `snippets.jsonl`, `facial_judgments.jsonl`, `final_judgments.jsonl` — are not control state. They're *projections*: rebuilt from the canonical store. Code that needs to make a runtime decision is forbidden from reading them. This is a real rule, enforced by convention and architecture review. It exists because projections drift; canonical state doesn't.

There's exactly one writer per state directory: the detached worker process that's actually running the search (`cloris/worker.py`). The Cloris UI opens the same database in *read-only* mode (`cloris/control_plane.py:8-17`) — `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`. The UI cannot corrupt the run by accident; it can only watch. A `RuntimeStateLock` enforces the one-writer rule at the filesystem level.

That setup gives you stop and resume effectively for free. Stop a run? The canonical state is on disk. Resume tomorrow? Open the database, read the lifecycle column, pick up where the state machine left off. Crash? Reopen, read the events table, project the state forward, continue. The recruiter doesn't have to think about any of this. They just close the laptop and reopen it.

One other thing the runtime state pins: the brief itself. At run start, the orchestrator writes `brief_path_at_launch`, `brief_content_hash`, and `brief_snapshot_json` into the runs row (`shared/runtime_state/store.py:303-317`). So six weeks later, when you're looking at a candidate the system saved, you can answer the question "what did the brief look like when the system decided to save this person?" with the exact JSON. This is the precondition for the closed feedback loop in chapter 5. You can't revise a brief based on what the run did unless you know exactly which brief produced the run.

Schema migrations are gated and idempotent (`shared/runtime_state/store.py:_migrate`). When the schema evolves — and it has, eight times since I started — legacy data survives. The migration runs once per database, checks `meta.schema_version`, applies the diff. Old runs from three weeks ago still open and inspect cleanly today.

None of this is the part of the product that closes a sale. It's the part that makes the product not embarrass itself in week three of a customer's use.

---

## Chapter 5 — The Learning

Here's where it all comes together.

A single run is a one-shot. A team running searches for the same kind of role over months has accumulated something — what worked, what didn't, which companies actually produced the candidates that got hired, which signals turned out to be misleading. Most recruiting software doesn't capture any of that. The next search starts from zero. Cloris doesn't.

Two things compound across runs. The first is the brief itself. After every run, the system processes what happened — what was saved, what was rejected, the reasons attached to each decision, the recruiter's feedback — and proposes a brief revision (`shared/brief_iteration.py`). The proposal is bounded (calibration thresholds clamped at 0.10, from chapter 1) and its output is a new brief version with a tracked rationale. The recruiter approves or edits. Next run uses the new brief. Over weeks, the brief is no longer a generic "senior ML engineer" brief — it's *your team's* version of that role, calibrated against your taste, refined against your past mistakes. This is what "Cloris gets better with use" actually means at the data layer.

The second is the market intelligence layer. Every run writes structured evidence into a per-market artifact (`market_intelligence/engine.py`): `output/market_intelligence/<market_key>/market-intel.json`, where `market_key` is a hash of role title + geography + role level (`market_intelligence/engine.py:181-188`). Multiple briefs in the same market share the artifact. The artifact accumulates: market hypotheses, talent-pool patterns, employer signal evidence, research opportunities, sourcing implications. The synthesis is multi-stage — there's a planner, a critic, an internal-synthesis backend (`market_intelligence/agent_backends.py`) — so the artifact isn't just a dump of every run; it's an interpreted view of the market for that role.

The market layer is what powers "Learn about the market" — one of the five locked verbs on the Cloris home screen, sitting at the same level as "Start a search." It's not a settings panel. It's a primary action. Because asking *what's actually going on in this hiring market right now* is something every senior recruiter does informally, in their head, by reading a lot of profiles and forming an unstated thesis. Cloris does it explicitly, persists the thesis, and feeds it back into the next brief revision.

The closed loop, end to end:

1. The brief is authored (or iterated from a previous version).
2. The run executes against discovery modules; the runtime state captures what happened in detail.
3. Recruiter reviews saves and rejects, marks them, adds feedback.
4. Brief iteration proposes a revision based on the feedback and the run's outcome.
5. Market intelligence ingests the run's evidence into the per-market artifact.
6. Next brief revision sees both the recruiter's feedback *and* the market context.
7. Next run uses the revised brief, against an updated picture of the market.

This loop is the actual product. Everything else — the search, the judgment, the runtime state — is infrastructure for this. A version of Cloris that didn't close this loop would just be a one-shot search tool. The whole point is the compounding.

---

## Chapter 6 — The Surface

One last thing.

How the screen looks is part of the product, not an aesthetic decoration on top of it. Cloris doesn't look like SaaS chrome — no heavy headers, no metrics dashboards, no bright "AI-powered" branding, no tooltips that explain what every number means. It's editorial: the home shows recent runs in a calm horizontal layout, the launch is one input field and a button, the run review is built around the candidate, not the diagnostics. The design rules are enumerated as 18 binding editorial rules in `docs/cloris-surface-design-rules.md`; every UI surface ships against a checklist.

There's a voice running through the product. It's sparse. It doesn't appear inside focused work — when you're reviewing candidates, the voice gets out of the way. It appears at transitions: launching a run, finishing one, recovering from a stop. The voice has a specific shape — Cloris is a person who finds her glasses, not a brand mascot who reminds you to drink water — and it lives in the same git repo as the code.

I'm not pretending the surface is the moat. The substrate, the brief, the closed loop — those are the moat. But the surface is what makes a recruiter actually want to use this thing for two hours a day, week after week. Most recruiting software is unpleasant to look at, even when it works. Cloris is built on the assumption that the recruiter using it has taste, and that earning the recruiter's affection is part of the job.

That's the whole tour. Brief in. Search executes. Each candidate judged. Run state pinned to disk, resumable. Outcomes feed back into the brief and the market layer. The next run is sharper. The recruiter's day is calmer. Six chapters of how, one thesis underneath: *do the boring part of sourcing in the background so the recruiter can do the judgment part*. That sentence is the only one I haven't moved from where I first wrote it.
