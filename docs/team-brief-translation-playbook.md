# Team Brief Translation Playbook

This document is for the moment when the agents stop being "Sam's search tool" and start becoming a team capability.

The important shift is this: recruiters and recruiting managers should not be asked to hand you a perfect brief. They should be asked to give you the raw hiring truth you can translate into a brief.

The brief is not a notes doc. It is a machine-executable policy. The job of the operator is to turn fuzzy human input into:

- capability areas
- a builder vs user boundary
- non-fit patterns
- employer signal rules
- channel-specific evidence expectations for LinkedIn and GitHub
- calibration examples that let the agent learn what "good" and "bad" actually look like

If you personally have zero context for a role, that is not a blocker. It just changes your job. You are no longer the domain expert. You are the translation layer between domain experts and the schema.

## The Operating Model

Think of the process as three different people contributing three different kinds of truth:

- Recruiting Manager: what the hiring team would actually interview, reject, and debate
- Recruiter: what the market actually looks like, what titles collide, what noise floods search, what companies matter in practice
- Agent operator: translates those truths into brief fields the system can evaluate against consistently

If any one of those is missing, the brief gets distorted:

- Manager-only briefs become aspirational and overfit to the JD
- Recruiter-only briefs become keyword-heavy and under-specified on technical depth
- Operator-only briefs become elegant but detached from real hiring decisions

The goal is not "capture everything." The goal is to capture the smallest set of truths that let the agents make the same directional decisions the humans would make.

## The Core Reframe

Do not ask:

- "Can you describe the ideal profile?"
- "What keywords should I search?"
- "Can you write the brief for me?"

Ask:

- "What would this person actually be building in their first six months?"
- "What kind of profile looks relevant on paper but you would not take a screen with?"
- "What evidence makes you believe someone is a builder instead of just adjacent?"
- "What would make you interview someone even if their background is non-obvious?"

This keeps the conversation grounded in decisions and evidence instead of abstractions.

## The Translation Pipeline

### 1. Capture Raw Hiring Truth

In the intake, collect raw statements without trying to formalize them too early.

Useful raw inputs:

- the hiring manager's description of day-to-day work
- recruiter observations about prior search noise
- 3-5 resumes, LinkedIn profiles, or GitHub profiles the team already considers strong, weak, or borderline
- 3-5 real or hypothetical saves
- 3-5 real or hypothetical rejects
- 1-3 borderline cases that would need discussion

You are trying to hear:

- what outputs matter
- what kinds of work transfer
- what adjacent profiles are tempting but wrong
- what level and trajectory actually count

### 2. Translate That Truth Into Brief Fields

After the meeting, convert the conversation into the schema.

- "What the person builds each quarter" becomes `capability_areas`
- "What counts as real depth vs surface adjacency" becomes `depth_distinction`
- "What floods search but is usually wrong" becomes `non_fit_patterns`
- "Which employers matter, and how much" becomes `employer_signal_rules`
- "What snippet-level trajectories should pass or fail quickly" becomes `facial_calibration`
- "What the floor means in practice" becomes `minimum_bar_description`
- "What we should save despite incomplete evidence" becomes `inferential_save_rules`
- "What examples anchor good judgment" becomes `calibration_examples`

The translation step is where most of the leverage lives. The manager does not need to know the field names. They need to provide the judgments that populate them.

### 3. Split the Evidence by Channel

The same role needs two different evidence surfaces.

For LinkedIn, ask:

- What titles, trajectories, or employer/title combinations should make us open the profile?
- What trajectories are ambiguous and must default to YES?
- What whole-career patterns are fast exits?
- What profile bullets would prove real depth?

For GitHub, ask:

- What kinds of repos, toolchains, libraries, or contribution patterns would prove depth?
- What would distinguish original work from tutorial usage or API consumption?
- What public artifacts might substitute for missing LinkedIn clarity: papers, talks, profile README, contribution graph, frontier repo PRs?
- What tool names are genuinely discriminating versus merely fashionable?

The underlying brief is shared, but the observable evidence is not.

### 4. Build a Calibration Pack

Do not stop at prose. Every unfamiliar role needs examples. If the recruiter or recruiting manager has a few resumes handy, use them.

Real resumes are especially valuable because they let you separate:

- what the team says it wants
- what the team actually responds to
- what evidence is visible on a resume but invisible on a LinkedIn snippet
- what should become a LinkedIn rule versus what should stay a full-eval rule

Treat those resumes as few-shot calibration material for the human workflow, even if they are not injected verbatim into prompts. They help you author better `calibration_examples`, sharper capability areas, and more realistic edge-case guidance.

Minimum viable calibration pack:

- 3 strong saves
- 3 clear rejects
- 2 borderlines

For each example, capture:

- why it is in that bucket
- what evidence mattered
- what almost fooled you
- whether the signal is visible on LinkedIn, GitHub, or only after cross-checking both

This is especially important when you lack context. You may not know the domain, but you can still capture comparative judgment: "this is more like the people we want; this is the adjacent population we do not."

If the team has actual resumes or profiles:

- ask them to mark each one as save, reject, or borderline
- ask what exact lines or projects drove that judgment
- ask what looked promising but turned out not to matter
- convert those notes into brief fields, not just an example pile

### 5. Run a Small Pilot Before Socializing Broadly

Before asking the whole team to trust the agents on a new family of roles, do a short calibration loop:

1. Draft the brief from one intake.
2. Run a small LinkedIn and GitHub pilot.
3. Review saves and rejects with recruiter and manager.
4. Tighten the brief.
5. Only then turn it into a reusable team pattern.

This avoids socializing the system around a brittle first draft.

## How To Work When You Have Zero Context

When you do not know the role, do not pretend to. Switch from expert mode to elicitation mode.

Your job is to extract discriminators.

The most effective moves are:

- Ask for contrasts, not definitions.
- Ask what the role produces, not what it "touches."
- Ask what the wrong but tempting profile looks like.
- Ask what evidence changes a no into a maybe, or a maybe into a yes.
- Ask what they would trade off and what they would not.

Good questions for unfamiliar roles:

- "If I watched this person work for a week, what would I actually see them building?"
- "Who is the most common false positive for this role?"
- "What kind of person could sound strong in a search review but fail in a hiring-manager screen?"
- "If two candidates have the same title, what evidence tells you one is real and the other is just adjacent?"
- "What would make you interview someone whose background looks off-template?"
- "What experience sounds relevant but does not actually transfer?"

The point is to get from nouns to judgments.

## A Better Division Of Labor In Intake Meetings

### Ask the Recruiting Manager for:

- the real work, not the JD language
- builder vs user distinctions
- transferable adjacent backgrounds
- must-have and nice-to-have tradeoffs
- borderline examples

### Ask the Recruiter for:

- noisy titles and market collisions
- companies that over-signal or under-signal
- geography-specific traps
- what good candidates tend to call themselves
- what search terms flood the funnel with the wrong population

### Ask Yourself, as operator:

- can I map this to 3-7 capability areas?
- do I understand the depth boundary well enough to reject attractive false positives?
- do I have enough channel-specific evidence to write both LinkedIn and GitHub evaluation criteria?
- do I have examples, or only prose?

If the answer to the last question is "only prose," you are not done.

## Ask For Artifacts, Not Just Opinions

When possible, leave the intake with concrete examples:

- resume PDFs
- LinkedIn URLs
- GitHub profiles or repos
- past candidates who reached onsite
- past candidates who looked good in search but failed calibration

These artifacts make unfamiliar roles much easier to translate. They also let you pressure-test whether the role's true bar is visible on LinkedIn, GitHub, both, or only after cross-referencing.

## Converting Human Statements Into Brief Fields

Below are common intake statements and what they usually mean in the schema.

- "We need someone strategic but still hands-on."
  Usually means the `minimum_bar_description` and `depth_distinction` both need to say that leadership without personal technical authorship is insufficient.

- "A lot of people in this space just use the tools."
  Usually means the brief needs sharper `user_signals`, GitHub-specific code signals, and stronger non-fit patterns around adoption or integration work.

- "Titles are useless here."
  Usually means `facial_calibration.trajectory_ambiguous_patterns` should be broad, and the bar should move to full evaluation evidence rather than snippet gating.

- "Anyone from Company X is probably good."
  Usually means "Company X belongs in `employer_signal_rules` with low additional evidence required," not "save on employer alone."

- "We care more about trajectory than exact domain."
  Usually means the brief needs explicit transferability guidance and maybe inferential save logic.

- "We can train domain specifics, but not systems judgment."
  Usually means the capability areas should be written around methodology and depth, not industry vocabulary.

## LinkedIn And GitHub Need Different Questions

The easiest mistake is asking one set of questions and trying to force the answers onto both agents.

For LinkedIn, your questions should pull out:

- title patterns
- employer/title trajectories
- bullet-level builder evidence
- whole-career fast exits
- recruiter-review-worthy ambiguity

For GitHub, your questions should pull out:

- code artifacts
- framework and toolchain evidence
- repo shapes
- frontier contribution signals
- signals that indicate original work instead of wrapper work

If the role is one where public GitHub will often be sparse, say that explicitly in the brief and rely more on profile README, contribution graph, papers, and inferential save logic.

## Definition Of Done For A New Role Family

You are ready to socialize the agents with the rest of the team when all of the following are true:

- the role can be summarized in 2-3 sentences without quoting the JD
- the brief has 3-7 capability areas written as work domains, not keywords
- the builder vs user boundary is sharp enough to explain your hardest reject
- you can name the top 3 noise patterns likely to flood LinkedIn
- you can name the top 3 GitHub signals that would actually prove depth
- you have at least 3 saves, 3 rejects, and 2 borderline examples
- the recruiter and recruiting manager both agree the draft reflects reality
- a pilot run produces outputs they recognize as directionally right

Until then, you are still in calibration, not rollout.

## Recommended Rollout Sequence

If you want to socialize this across the team, do it in this order:

1. Start with one recruiter and one recruiting manager on a single unfamiliar role.
2. Use the intake template in `docs/agent-brief-intake-template.md`.
3. Translate the meeting into a draft brief.
4. Run a limited pilot on both LinkedIn and GitHub.
5. Review outputs together and tighten the brief.
6. Turn the lessons into a reusable "role family" pattern.
7. Only then introduce the workflow to the broader recruiting org.

This keeps the socialization grounded in real examples instead of abstract enthusiasm.

## The Mental Model To Share With The Team

The agents do not replace recruiter judgment.

They formalize it.

The team's job is not to become prompt writers. The team's job is to provide:

- what good looks like
- what adjacent-but-wrong looks like
- what evidence matters
- where ambiguity should be preserved instead of prematurely collapsed

Your job is to transmute that into a brief the agents can execute consistently at scale.
