"""
GitHub-native evaluation templates for the autonomous sourcing agent.

These templates mirror the structure and output format of judgment_templates.py
but evaluate GitHub-specific evidence (repos, READMEs, toolchain usage, frontier
contributions, papers/website) instead of LinkedIn evidence (career trajectory,
summary bullets).

CRITICAL DESIGN CONSTRAINT: The output format is IDENTICAL to the LinkedIn
templates so that parse_facial_response and parse_full_evaluation_response can
be reused without modification.

Evidence sources (GitHub):
  - Repository code: imports, configs, training scripts, eval harness extensions
  - README content: architecture explanations, training procedures, results tables
  - Frontier repo contributions: PRs to huggingface/trl, EleutherAI/lm-eval, etc.
  - Website + papers: personal sites, arxiv links
  - Repo metadata: topics, descriptions, stars, forks, language distribution
  - Profile: bio, profile README, follower count
"""

from shared.brief_schema import Brief

# Re-export parse functions so callers can import everything from one module.
from linkedin.judgment_templates import parse_facial_response, parse_full_evaluation_response


# ---------------------------------------------------------------------------
# GITHUB FACIAL TRIAGE TEMPLATE
# ---------------------------------------------------------------------------
# Purpose: Filter out GitHub profiles where no reasonable full evaluation
# could produce a save. This is a TRIAGE, not a judgment.
# Expected pass-through: 20-50% (GitHub profiles skew noisier than LinkedIn).
# Parse failure default: YES (cost of false positive = one cheap extraction;
# cost of false negative = a permanently missed candidate).
# ---------------------------------------------------------------------------

GITHUB_FACIAL_TRIAGE_TEMPLATE = """You are triaging candidate profiles from GitHub search results.

ROLE: {role_title} ({role_level}) — {role_summary}

YOUR TASK: Decide whether this candidate's GitHub portfolio warrants a full profile review. You are deciding whether to spend tokens on a full read, not whether to save.

WHAT YOU HAVE: A username, bio, profile README (if any), public repo list with names/descriptions/topics/stars/languages, and a toolchain summary listing detected frameworks and libraries across their repos. You do NOT have full repo contents, commit history, or code quality analysis yet.

═══════════════════════════════════════════════════════
STEP 1 — FAST EXITS
═══════════════════════════════════════════════════════

Reject immediately ONLY if the profile clearly indicates work outside scope:
{fast_exit_block}

A fast exit requires that NO repo, topic, or bio element has a plausible connection to the role. One relevant-looking repo or toolchain signal anywhere means this is NOT a fast exit.

═══════════════════════════════════════════════════════
STEP 2 — PORTFOLIO READ
═══════════════════════════════════════════════════════

The portfolio summary is your highest-signal field. Read ALL of: toolchain_detected, repo_summaries, frontier_contributions, website_papers, profile_summary. What you're looking for:

PORTFOLIO PATTERNS THAT FAVOR YES:
{portfolio_yes_patterns}

PORTFOLIO PATTERNS THAT ARE AMBIGUOUS (default YES — let the full evaluation resolve):
{portfolio_ambiguous_patterns}

PORTFOLIO PATTERNS THAT FAVOR NO (only if consistent across the ENTIRE portfolio):
{portfolio_no_patterns}

CAPABILITY AREAS for this role:
{capability_area_names}

═══════════════════════════════════════════════════════
DECISION
═══════════════════════════════════════════════════════

GitHub profiles can be misleading — a user with mostly forks may have significant private work, and repo names alone do not reveal depth. Do NOT try to make depth calls at this stage.

- FACIAL_YES: Any repo, toolchain signal, contribution, or bio element COULD connect to a capability area. Ambiguity favors YES.
- FACIAL_NO: The ENTIRE portfolio clearly indicates work outside all capability areas. Every repo, topic, and toolchain signal points away from relevance. No single element creates doubt.

CANDIDATE PORTFOLIO:
{candidate_portfolio}

Respond with EXACTLY this format:
DECISION: FACIAL_YES or FACIAL_NO
REASON: One sentence — what portfolio signal you see (if YES) or why the full portfolio is clearly outside scope (if NO)."""


# ---------------------------------------------------------------------------
# GITHUB FULL EVALUATION TEMPLATE
# ---------------------------------------------------------------------------
# Purpose: Determine whether a candidate should be saved to the pipeline.
# This is where the bar lives. Three-step claim-and-evidence procedure
# producing output IDENTICAL to the LinkedIn full evaluation template.
# Parse failure default: REJECT with PARSE_FAILURE flag (auditable, not silent).
# ---------------------------------------------------------------------------

GITHUB_FULL_EVALUATION_TEMPLATE = """You are evaluating a candidate for a specific technical role based on their GitHub presence. Follow the procedure below EXACTLY. Do not skip steps.

ROLE: {role_title} ({role_level})
{role_summary}

MINIMUM BAR: {minimum_years_experience}+ years hands-on. {minimum_bar_description}

WHAT YOU HAVE: An enriched GitHub profile — bio, profile README, public repos with full README content, detected toolchain/framework usage across repos, contributions to external repos, website content, papers, stars/forks counts, language distribution, and repo commit activity summaries.

EVIDENCE HIERARCHY (GitHub-specific — ranked by diagnostic value):
1. FRONTIER TOOLCHAIN USAGE — HIGHEST. Repos that import, configure, or extend frontier frameworks (axolotl, trl, lm-eval-harness, swe-bench, vllm, megatron, deepspeed, nemo, alignment-handbook). The brief's capability areas define what counts. A repo with `from trl import DPOTrainer` and custom config is stronger signal than any number of stars.
2. README CONTENT + REPO STRUCTURE — HIGHEST (tied). Architecture explanations, training procedure documentation, directory structures showing data pipelines, eval harness configs, and results tables. A well-documented training repo is equivalent to LinkedIn summary bullets describing the same work.
3. FRONTIER REPO CONTRIBUTIONS — HIGH. Merged PRs or substantive issues on huggingface/trl, EleutherAI/lm-evaluation-harness, vllm-project/vllm, etc. Drive-by typo fixes do not count.
4. WEBSITE + PAPERS — HIGH. Personal site with ML project writeups, arxiv papers with hands-on implementation sections.
5. REPO TOPICS + DESCRIPTIONS — MODERATE-HIGH. Topics like "reinforcement-learning-from-human-feedback", "llm-evaluation", "fine-tuning" indicate domain awareness. But topics are self-reported — verify against actual repo content.
6. STARS/FORKS — MODERATE. High stars on ML repos indicate community validation. But stars can reflect novelty, not depth. Forks of popular repos without modifications are noise.
7. BIO / PROFILE README — MODERATE. Self-reported claims. "ML researcher at X" is moderate signal. Verify against repo evidence.
8. LANGUAGE DISTRIBUTION — LOW. Python-heavy is expected but not diagnostic. Rust/C++ in ML contexts (kernels, inference engines) is a mild positive.

═══════════════════════════════════════════════════════
SPARSE PROFILE CHECK (run FIRST, before anything else)
═══════════════════════════════════════════════════════

A sparse GitHub profile is one with FEW OR NO substantive repos — mostly forks with no modifications, empty repos, or only a profile README. GitHub profiles can be sparse because significant work lives in private repos or employer orgs. If the profile is sparse, check:

{inferential_save_block}

ADDITIONAL SPARSE SIGNAL: If the profile is sparse BUT the detected toolchain includes highly specific practitioner frameworks ({discriminating_skills_examples}), treat this as supporting evidence. These frameworks are too specialized to appear without hands-on experience. A sparse profile with contributions to frontier repos + detected vllm/trl usage is a stronger inferential save than contributions alone.

GITHUB-SPECIFIC INFERENTIAL SAVE CONDITIONS:
- Contributed to frontier repos (huggingface/*, EleutherAI/*, vllm-project/*) even if own repos are sparse
- >200 followers with bio indicating ML research/engineering
- Any repo with >50 stars in a domain relevant to the capability areas
- Linked website/papers showing ML depth not reflected in public repos

If an inferential save condition is met, respond with DECISION: INFERENTIAL_SAVE, confidence 0.4-0.6. These go to the recruiter for manual review.

If no inferential save applies AND the profile is sparse, respond REJECT — not enough signal.

If the profile HAS meaningful detail, proceed to Step 1.

═══════════════════════════════════════════════════════
STEP 1 — CAPABILITY MAPPING (signal, NOT a gate)
═══════════════════════════════════════════════════════

Try to map the candidate's ACTUAL WORK (as evidenced by repo contents, toolchain usage, and contributions) to one of the following capability areas. Areas are stack-ranked — higher-ranked matches increase confidence.

{capability_area_block}

EMPLOYER SIGNAL RULES:
{employer_signal_block}

Note: On GitHub, "employer" signal comes from org memberships, bio mentions, and contribution graphs to employer repos. Weight accordingly — a bio saying "ML Engineer at DeepMind" with no public ML repos is weaker than someone with 10 ML repos and no employer mentioned.

RESULT — classify the match as one of:
- DIRECT: Repo contents, toolchain usage, or contributions demonstrate work that falls squarely within a capability area. Cite the area and the evidence.
- ADJACENT: The work touches a capability area but isn't core to it (e.g., built ML evaluation tools but for a non-LLM domain). Note what's adjacent and why.
- NONE: No capability area maps. This is NOT an automatic reject — proceed to Step 2.

═══════════════════════════════════════════════════════
STEP 2 — DEPTH TEST (runs REGARDLESS of Step 1 result)
═══════════════════════════════════════════════════════

This step evaluates the candidate's hands-on ML depth INDEPENDENT of whether their domain matches. Read the repo evidence across ALL repositories. Do they demonstrate hands-on ML work where data quality, model training, or evaluation methodology was a primary focus?

{depth_block}

Key distinction — look at CODE EVIDENCE and REPO PATTERNS:
- BUILDER evidence: Original repos with custom training loops, eval harness extensions, data pipeline code, fine-tuning configs with non-default hyperparameters, iterative commit history on ML systems, published papers with code, custom CUDA kernels, novel evaluation methods, training infrastructure code
- USER evidence: Only forks with minimal or no changes, API wrapper repos, tutorial/course notebook repos, default configs copied from docs, "using X model" READMEs without implementation, Gradio/Streamlit demos calling hosted APIs, awesome-list curation without original work

"Fine-tuned" in a README is ambiguous — check for actual training code. A repo claiming "fine-tuned LLaMA" with actual LoRA configs, training scripts, and loss curves is BUILDER. A repo with the same claim but only inference code calling a hosted model is USER.

A profile that lists ML topics but whose repos contain only application-layer code does not pass the depth test.

═══════════════════════════════════════════════════════
STEP 3 — TRANSFERABILITY (only if Step 1 was ADJACENT or NONE)
═══════════════════════════════════════════════════════

If Step 1 found no direct capability area match, ask: does this person's METHODOLOGY transfer to the role, even though their DOMAIN doesn't match?

The test: "If you took this person's skills and methodology and pointed them at LLM training data / RL environments / model evaluation instead of their current domain, would the skills apply?"

TRANSFERS (methodology is domain-portable):
- Evaluation framework design in any ML domain -> evaluation framework design for LLMs. The person knows how to measure model quality. The specific model changes; the methodology of rigorous evaluation is the same.
- Data quality systems for model training in any domain -> data quality for frontier model training. Someone who built data curation pipelines and quality metrics for computational biology models knows what training data quality means.
- Custom model training (architectures, training loops, hyperparameter optimization) in any domain -> can learn LLM training. Deep hands-on model training experience is the hardest skill to develop.
- Systems-level ML infrastructure (custom kernels, distributed training, inference optimization) -> transfers directly regardless of model type.

DOES NOT TRANSFER (domain gap is too wide AND methodology doesn't port):
- Web frontend repos with no ML component -> strong coding but no ML depth to port.
- DevOps/infrastructure repos (Terraform, Kubernetes) without ML workload focus -> operational skills but no model training methodology.
- Mobile app development -> different engineering discipline entirely.
- Data visualization / dashboarding without ML model building -> data-adjacent but no model training methodology.

RESULT: TRANSFERABLE (cite what methodology transfers) or NOT_TRANSFERABLE (explain why the gap is too wide).

═══════════════════════════════════════════════════════
STEP 4 — DECISION
═══════════════════════════════════════════════════════

State the strongest CASE FOR this candidate's relevance:
- What evidence supports their fit? (capability area match, depth evidence, transferable methodology)

State the strongest CASE AGAINST:
- What's missing, misaligned, or uncertain?

NON-FIT PATTERNS — work that is valuable but outside scope:
{non_fit_block}

CRITICAL — NON-FIT OVERRIDE RULE:
{non_fit_override_rule}

DECISION MATRIX — weigh the evidence from Steps 1-3 together:

DIRECT match + BUILDER depth = SAVE (high confidence, 0.75-0.95)
ADJACENT match + BUILDER depth = SAVE (moderate confidence, 0.55-0.75)
NONE match + BUILDER depth + TRANSFERABLE methodology = SAVE (moderate confidence, 0.45-0.65, flag as TRANSFERABLE_SAVE for recruiter awareness)
NONE match + BUILDER depth + NOT TRANSFERABLE = REJECT
Any match level + USER depth = REJECT (application-layer work regardless of domain)
Sparse profile meeting inferential conditions = INFERENTIAL_SAVE (0.4-0.6)

The decision standard: would the hiring manager agree this person has the hands-on ML depth and data quality instincts to learn the role? Not "already doing it at a frontier lab" — that's too high. Not "vaguely ML-adjacent" — that's too low. "Has done hands-on ML work with enough depth to grow into this role, even if their current domain is different."

The guard against permissiveness is the DEPTH TEST, not the capability mapping. A person must demonstrate hands-on ML builder depth to be saved — no exceptions. What the capability mapping determines is confidence level, not the binary decision. Strong domain match + depth = high confidence save. No domain match + depth + transferable methodology = moderate confidence save. No depth = reject regardless of domain.

CANDIDATE EVIDENCE:
{candidate_evidence}

═══════════════════════════════════════════════════════
RESPOND WITH EXACTLY THIS FORMAT:
═══════════════════════════════════════════════════════

STEP_1_MATCH: DIRECT or ADJACENT or NONE
STEP_1_AREA: [capability area name if DIRECT/ADJACENT, or "N/A"]
STEP_1_EVIDENCE: [cite specific repo contents, toolchain signals, or contributions, 2-3 sentences max]

STEP_2_DEPTH: BUILDER or USER
STEP_2_EVIDENCE: [what code evidence and repo patterns indicate, 1-2 sentences]

STEP_3_TRANSFERABILITY: TRANSFERABLE or NOT_TRANSFERABLE or N/A (if DIRECT match)
STEP_3_EVIDENCE: [what methodology transfers, or why the gap is too wide, 1-2 sentences. Write "N/A" if Step 1 was DIRECT]

CASE_FOR: [strongest argument for relevance, 1-2 sentences]
CASE_AGAINST: [strongest argument against, 1-2 sentences]

DECISION: SAVE or REJECT or INFERENTIAL_SAVE or TRANSFERABLE_SAVE
CONFIDENCE: [0.0 to 1.0 — use the decision matrix ranges above]
SUMMARY: [one-line evaluation a hiring manager could act on]"""


# ---------------------------------------------------------------------------
# DEFAULT GITHUB FACIAL PATTERNS
# ---------------------------------------------------------------------------
# Used when the brief does not supply GitHub-specific facial calibration.
# ---------------------------------------------------------------------------

_DEFAULT_GITHUB_FAST_EXITS = [
    "Profile is an organization account, not a person",
    "Profile has zero repos AND zero contributions AND no bio — completely empty",
    "ALL repos are forks of web frontend frameworks (React, Vue, Angular) with zero ML content anywhere",
    "Profile is clearly a bot or auto-generated account",
]

_DEFAULT_PORTFOLIO_YES_PATTERNS = [
    "Any repo importing or configuring frontier ML frameworks (transformers, trl, axolotl, vllm, deepspeed, megatron, lm-eval-harness)",
    "Contributions to frontier ML repos (huggingface/*, EleutherAI/*, vllm-project/*)",
    "Repos with topics like fine-tuning, rlhf, llm-evaluation, training-data, reward-model",
    "Papers linked in bio or repos (arxiv, conference proceedings)",
    "Personal website with ML project writeups or research descriptions",
    "Repos containing training scripts, eval configs, or data pipeline code",
    "Bio mentions ML research, model training, or AI safety work",
]

_DEFAULT_PORTFOLIO_AMBIGUOUS_PATTERNS = [
    "Mix of ML and non-ML repos — some relevant repos exist alongside unrelated work",
    "Sparse profile with ML-relevant bio but few public repos (private work is common)",
    "Repos with ML topics but unclear depth from descriptions alone",
    "Data science repos that could indicate model training or could be analytics-only",
    "PhD student profile with research topics adjacent to ML but unclear hands-on coding",
]

_DEFAULT_PORTFOLIO_NO_PATTERNS = [
    "ALL repos are web frontend (React, Next.js, Vue) with zero ML content",
    "ALL repos are DevOps/infrastructure (Terraform, Kubernetes, CI/CD) with no ML workloads",
    "ALL repos are mobile development (iOS, Android, Flutter)",
    "ALL repos are tutorial completions or bootcamp projects with no original ML work",
    "Profile is entirely game development, embedded systems, or blockchain with no ML intersection",
]


# ---------------------------------------------------------------------------
# ASSEMBLY FUNCTIONS
# ---------------------------------------------------------------------------
# These inject Brief content into template slots at runtime.
# The GitHub judger calls these — never constructs prompts directly.
# ---------------------------------------------------------------------------

def assemble_github_facial_prompt(brief: Brief, portfolio_text: str) -> str:
    """Assemble a GitHub facial triage prompt for a single candidate.

    Uses GitHub-specific facial patterns from the brief if available
    (via getattr on github_facial_calibration or similar fields),
    otherwise falls back to sensible defaults.
    """
    # GitHub-specific fast exits
    github_fast_exits = getattr(brief, "github_fast_exit_patterns", None)
    if github_fast_exits:
        fast_exit_block = "\n".join(f"- {p}" for p in github_fast_exits)
    else:
        fast_exit_block = "\n".join(f"- {p}" for p in _DEFAULT_GITHUB_FAST_EXITS)

    # Portfolio YES patterns
    portfolio_yes = getattr(brief, "github_portfolio_yes_patterns", None)
    if portfolio_yes:
        portfolio_yes_block = "\n".join(f"- {p}" for p in portfolio_yes)
    else:
        portfolio_yes_block = "\n".join(f"- {p}" for p in _DEFAULT_PORTFOLIO_YES_PATTERNS)

    # Portfolio AMBIGUOUS patterns
    portfolio_ambiguous = getattr(brief, "github_portfolio_ambiguous_patterns", None)
    if portfolio_ambiguous:
        portfolio_ambiguous_block = "\n".join(f"- {p}" for p in portfolio_ambiguous)
    else:
        portfolio_ambiguous_block = "\n".join(f"- {p}" for p in _DEFAULT_PORTFOLIO_AMBIGUOUS_PATTERNS)

    # Portfolio NO patterns
    portfolio_no = getattr(brief, "github_portfolio_no_patterns", None)
    if portfolio_no:
        portfolio_no_block = "\n".join(f"- {p}" for p in portfolio_no)
    else:
        portfolio_no_block = "\n".join(f"- {p}" for p in _DEFAULT_PORTFOLIO_NO_PATTERNS)

    return GITHUB_FACIAL_TRIAGE_TEMPLATE.format(
        role_title=brief.role_title,
        role_level=brief.role_level,
        role_summary=brief.role_summary,
        fast_exit_block=fast_exit_block,
        portfolio_yes_patterns=portfolio_yes_block,
        portfolio_ambiguous_patterns=portfolio_ambiguous_block,
        portfolio_no_patterns=portfolio_no_block,
        capability_area_names="\n".join(f"  - {name}" for name in brief.capability_area_names()),
        candidate_portfolio=portfolio_text,
    )


def assemble_github_full_evaluation_prompt(brief: Brief, evidence_text: str) -> str:
    """Assemble a GitHub full evaluation prompt for one candidate.

    Uses the same Brief formatting methods as the LinkedIn template
    (capability_area_block, depth_block, etc.) since the brief's
    capability areas and depth distinctions are role-level, not
    platform-level.
    """
    return GITHUB_FULL_EVALUATION_TEMPLATE.format(
        role_title=brief.role_title,
        role_level=brief.role_level,
        role_summary=brief.role_summary,
        minimum_years_experience=brief.minimum_years_experience,
        minimum_bar_description=brief.minimum_bar_description,
        capability_area_block=brief.capability_area_block(),
        depth_block=brief.depth_block(),
        non_fit_block=brief.non_fit_block(),
        non_fit_override_rule=brief.non_fit_override_rule_block(),
        employer_signal_block=brief.employer_signal_block(),
        inferential_save_block=brief.inferential_save_block(),
        discriminating_skills_examples=brief.discriminating_skills_examples(),
        candidate_evidence=evidence_text,
    )
