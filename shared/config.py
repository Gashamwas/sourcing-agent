"""Configuration loader. Reads .env and provides typed access to all settings.

Note: For Turing corporate proxy, you may need:
    export NODE_TLS_REJECT_UNAUTHORIZED=0

Frozen-app deployment (Phase 0 ``userdata`` slice): when Cloris runs
inside a signed .app bundle, the bundle is read-only — PROJECT_ROOT
resolves to a path inside ``Cloris.app/Contents/Resources/`` after
PyInstaller extraction and cannot be written to. ``shared.user_data_dir``
detects that case and we layer ``.env`` loads accordingly: the
recipient's writable ``~/Library/Application Support/Cloris/.env``
takes priority, with the project-root ``.env`` falling through for
dev. ``OUTPUT_DIR`` resolves the same way.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

from shared.user_data_dir import (
    cloris_user_data_dir,
    should_use_user_data_dir,
)

# .env layering. The user-data ``.env`` (written by the in-product API
# key entry on first launch) is loaded first so its values seed the
# environment. ``override=False`` on the second load means the
# project-root ``.env`` provides defaults for any keys the user-data
# ``.env`` did not set, without ever clobbering recipient-entered
# credentials. Dev workflow is unchanged: when the user-data path is
# disabled, we just load PROJECT_ROOT/.env directly the way we always
# have.
_PROJECT_ROOT_ENV: Path = Path(__file__).parent.parent / ".env"
if should_use_user_data_dir():
    _user_env_path = cloris_user_data_dir() / ".env"
    if _user_env_path.exists():
        load_dotenv(_user_env_path, override=False)
load_dotenv(_PROJECT_ROOT_ENV, override=False)


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# --- API Keys (lazy — validated at call time in llm_clients, not at import) ---
# Per-agent keys (LINKEDIN_ or GITHUB_ prefix) override shared keys.
# Prefix is set by each agent's entry point before config is imported.
_AGENT_PREFIX: str = os.getenv("AGENT_KEY_PREFIX", "")

def _agent_key(key: str) -> str:
    """Return agent-prefixed key if set, otherwise fall back to shared key."""
    if _AGENT_PREFIX:
        prefixed = os.getenv(f"{_AGENT_PREFIX}_{key}", "")
        if prefixed:
            return prefixed
    return _optional(key, "")

ANTHROPIC_API_KEY: str = _agent_key("ANTHROPIC_API_KEY")
OPENAI_API_KEY: str = _agent_key("OPENAI_API_KEY")
GOOGLE_API_KEY: str = _agent_key("GOOGLE_API_KEY")
PERPLEXITY_API_KEY: str = _agent_key("PERPLEXITY_API_KEY")
SUPABASE_ANON_KEY: str = _optional("SUPABASE_ANON_KEY", "")

CHEAP_MODEL_PROVIDER: str = _optional("CHEAP_MODEL_PROVIDER", "openai")

# --- Model Names ---
CHEAP_MODEL_NAME: str = _optional("CHEAP_MODEL_NAME", "gpt-4o-mini")
OPUS_MODEL_NAME: str = _optional("OPUS_MODEL_NAME", "claude-opus-4-6")
FACIAL_MODEL_NAME: str = _optional("FACIAL_MODEL_NAME", OPUS_MODEL_NAME)
MARKET_INTEL_EXTERNAL_RESEARCH_PROVIDER: str = _optional(
    "MARKET_INTEL_EXTERNAL_RESEARCH_PROVIDER",
    "auto",
)
MARKET_INTEL_EXTERNAL_RESEARCH_MODEL: str = _optional(
    "MARKET_INTEL_EXTERNAL_RESEARCH_MODEL",
    "",
)
MARKET_INTEL_PERPLEXITY_PRESET: str = _optional(
    "MARKET_INTEL_PERPLEXITY_PRESET",
    "deep-research",
)
MARKET_INTEL_EXTERNAL_RESEARCH_TIMEOUT_SECONDS: float = float(
    _optional("MARKET_INTEL_EXTERNAL_RESEARCH_TIMEOUT_SECONDS", "300")
)

# --- LinkedIn external evidence augmentation (Perplexity-backed) ---
# Slice 1 of the perplexity-evidence-augmentation feature. All defaults are
# safe / disabled: the feature is gated off until slice 2 wires it in.
LINKEDIN_EXTERNAL_EVIDENCE_ENABLED: bool = _optional(
    "LINKEDIN_EXTERNAL_EVIDENCE_ENABLED", "false"
).strip().lower() in {"1", "true", "yes", "on"}
LINKEDIN_EXTERNAL_EVIDENCE_MODEL: str = _optional("LINKEDIN_EXTERNAL_EVIDENCE_MODEL", "")
LINKEDIN_EXTERNAL_EVIDENCE_TIMEOUT_SECONDS: float = float(
    _optional("LINKEDIN_EXTERNAL_EVIDENCE_TIMEOUT_SECONDS", "90")
)
LINKEDIN_EXTERNAL_EVIDENCE_MAX_OUTPUT_TOKENS: int = int(
    _optional("LINKEDIN_EXTERNAL_EVIDENCE_MAX_OUTPUT_TOKENS", "4096")
)
LINKEDIN_EXTERNAL_EVIDENCE_MIN_CITATIONS: int = int(
    _optional("LINKEDIN_EXTERNAL_EVIDENCE_MIN_CITATIONS", "2")
)
LINKEDIN_EXTERNAL_EVIDENCE_MIN_IDENTITY_CONFIDENCE: float = float(
    _optional("LINKEDIN_EXTERNAL_EVIDENCE_MIN_IDENTITY_CONFIDENCE", "0.5")
)
# Intentionally NOT defaulted to "deep-research" — market-intel has its own preset
# and the candidate-evidence path runs under a tighter time budget.
LINKEDIN_EXTERNAL_EVIDENCE_PERPLEXITY_PRESET: str = _optional(
    "LINKEDIN_EXTERNAL_EVIDENCE_PERPLEXITY_PRESET", ""
)

# Step B of the FACIAL_BORDERLINE promotion plan (slice 13). When True, the
# facial-triage prompt offers a three-class output (YES/BORDERLINE/NO),
# the parser recognizes BORDERLINE, and the orchestrator translates
# BORDERLINE -> FACIAL_YES at the parser-output boundary (alias-to-YES).
# Persistence and counters stay binary at Step B; canonical state never
# observes BORDERLINE. Step C is where BORDERLINE becomes a real third
# state. Default off; production behavior under flag-off is byte-identical
# to pre-Step-B.
LINKEDIN_FACIAL_BORDERLINE_ENABLED: bool = _optional(
    "LINKEDIN_FACIAL_BORDERLINE_ENABLED", "false"
).strip().lower() in {"1", "true", "yes", "on"}

# --- Browser ---
CDP_URL: str = _optional("CDP_URL", "http://127.0.0.1:9222")

# --- Behavior ---
MAX_PAGES_PER_STRING: int = int(_optional("MAX_PAGES_PER_STRING", "0"))
PAGE_DELAY_SECONDS: float = float(_optional("PAGE_DELAY_SECONDS", "3"))
PROFILE_DELAY_SECONDS: float = float(_optional("PROFILE_DELAY_SECONDS", "2"))

# --- Cadence pause (anti-detection) ---
# After this many minutes of continuous activity, pause for a human-like break.
# Both values are jittered ±20% at runtime to avoid metronomic patterns.
CADENCE_INTERVAL_MINUTES: float = float(_optional("CADENCE_INTERVAL_MINUTES", "30"))
CADENCE_PAUSE_SECONDS: float = float(_optional("CADENCE_PAUSE_SECONDS", "120"))

# --- Search-control tuning ---
# The first compound block is intentionally smaller so the run can exploit early.
OPENING_BLOCK_SIZE: int = int(_optional("OPENING_BLOCK_SIZE", "3"))
# Large/noisy strings get a bounded number of pre-commit rescue attempts before stop.
PRECOMMIT_MAX_RECOVERY_ATTEMPTS: int = int(_optional("PRECOMMIT_MAX_RECOVERY_ATTEMPTS", "2"))
# Once a variant is committed, stop after this many consecutive zero-signal pages.
COMMITTED_ZERO_SIGNAL_STOP_STREAK: int = int(_optional("COMMITTED_ZERO_SIGNAL_STOP_STREAK", "2"))
# After a failed drift rescue, allow only this many additional zero-signal committed pages.
POST_DRIFT_ZERO_SIGNAL_STOP_STREAK: int = int(_optional("POST_DRIFT_ZERO_SIGNAL_STOP_STREAK", "1"))

# --- Legacy pagination floors (deprecated) ---
# These remain for compatibility with prior runs / architecture metadata, but the
# orchestrator now prefers phase-aware recovery + signal-decay controls instead.
MIN_PAGES_BY_RESULT_COUNT: list[tuple[int, int]] = [
    (500, 3),
    (100, 2),
    (30, 1),
    (0, 1),
]

# --- Glance assessment (page-level pre-filter) ---
GLANCE_NOISE_TITLE_THRESHOLD = 0.7   # >70% sharing a non-fit title family
GLANCE_KEYWORD_MISS_THRESHOLD = 0    # 0 snippets have any relevant key_term
GLANCE_MIN_SNIPPETS = 8              # Skip glance if fewer than 8 snippets

# --- Mid-page early exit ---
EARLY_EXIT_MIN_CANDIDATES = 5        # Evaluate at least N before checking
EARLY_EXIT_FACIAL_NO_RATE = 0.95     # >=95% facial_no triggers exit (raised for strict triage)

# --- LinkedIn search experimentation ---
SEARCH_EXPERIMENT_MAX_PLANNED_VARIANTS: int = int(_optional("SEARCH_EXPERIMENT_MAX_PLANNED_VARIANTS", "3"))
SEARCH_EXPERIMENT_MAX_EXECUTED_SIBLINGS: int = int(_optional("SEARCH_EXPERIMENT_MAX_EXECUTED_SIBLINGS", "2"))
SEARCH_EXPERIMENT_MAX_CONSECUTIVE_REWRITES: int = int(_optional("SEARCH_EXPERIMENT_MAX_CONSECUTIVE_REWRITES", "2"))
SEARCH_EXPERIMENT_MUTATION_BUDGET: int = int(_optional("SEARCH_EXPERIMENT_MUTATION_BUDGET", "8"))
SEARCH_EXPERIMENT_MAX_DRIFT_ATTEMPTS_PER_VARIANT: int = int(
    _optional("SEARCH_EXPERIMENT_MAX_DRIFT_ATTEMPTS_PER_VARIANT", "1")
)
SEARCH_EXPERIMENT_DRIFT_BUDGET: int = int(_optional("SEARCH_EXPERIMENT_DRIFT_BUDGET", "1"))
SEARCH_INTELLIGENCE_EXPLOIT_PROMOTION_LIMIT: int = int(
    _optional("SEARCH_INTELLIGENCE_EXPLOIT_PROMOTION_LIMIT", "3")
)
SEARCH_INTELLIGENCE_EXPLOIT_DEMOTION_LIMIT: int = int(
    _optional("SEARCH_INTELLIGENCE_EXPLOIT_DEMOTION_LIMIT", "3")
)

# --- LinkedIn cadence trim knobs ---
LINKEDIN_SEARCH_TYPING_CHAR_MIN_SECONDS: float = float(
    _optional("LINKEDIN_SEARCH_TYPING_CHAR_MIN_SECONDS", "0.055")
)
LINKEDIN_SEARCH_TYPING_CHAR_MAX_SECONDS: float = float(
    _optional("LINKEDIN_SEARCH_TYPING_CHAR_MAX_SECONDS", "0.11")
)
LINKEDIN_SEARCH_TYPING_OPERATOR_PAUSE_MIN_SECONDS: float = float(
    _optional("LINKEDIN_SEARCH_TYPING_OPERATOR_PAUSE_MIN_SECONDS", "0.18")
)
LINKEDIN_SEARCH_TYPING_OPERATOR_PAUSE_MAX_SECONDS: float = float(
    _optional("LINKEDIN_SEARCH_TYPING_OPERATOR_PAUSE_MAX_SECONDS", "0.45")
)
LINKEDIN_SEARCH_TYPING_THOUGHT_PAUSE_MIN_SECONDS: float = float(
    _optional("LINKEDIN_SEARCH_TYPING_THOUGHT_PAUSE_MIN_SECONDS", "0.30")
)
LINKEDIN_SEARCH_TYPING_THOUGHT_PAUSE_MAX_SECONDS: float = float(
    _optional("LINKEDIN_SEARCH_TYPING_THOUGHT_PAUSE_MAX_SECONDS", "0.90")
)
LINKEDIN_SEARCH_TYPING_PRE_SUBMIT_MIN_SECONDS: float = float(
    _optional("LINKEDIN_SEARCH_TYPING_PRE_SUBMIT_MIN_SECONDS", "0.40")
)
LINKEDIN_SEARCH_TYPING_PRE_SUBMIT_MAX_SECONDS: float = float(
    _optional("LINKEDIN_SEARCH_TYPING_PRE_SUBMIT_MAX_SECONDS", "1.20")
)
LINKEDIN_SEARCH_TYPING_MEDIUM_TYPO_PROBABILITY: float = float(
    _optional("LINKEDIN_SEARCH_TYPING_MEDIUM_TYPO_PROBABILITY", "0.15")
)
LINKEDIN_SEARCH_TYPING_LONG_TYPO_PROBABILITY: float = float(
    _optional("LINKEDIN_SEARCH_TYPING_LONG_TYPO_PROBABILITY", "0.30")
)
LINKEDIN_SEARCH_TYPING_SECOND_TYPO_PROBABILITY: float = float(
    _optional("LINKEDIN_SEARCH_TYPING_SECOND_TYPO_PROBABILITY", "0.10")
)
LINKEDIN_SEARCH_TYPING_MAX_TYPOS: int = int(
    _optional("LINKEDIN_SEARCH_TYPING_MAX_TYPOS", "2")
)
LINKEDIN_PROFILE_EXPAND_CLICK_DWELL_SECONDS: float = float(
    _optional("LINKEDIN_PROFILE_EXPAND_CLICK_DWELL_SECONDS", "0.25")
)
LINKEDIN_PROFILE_EXPAND_SETTLE_SECONDS: float = float(
    _optional("LINKEDIN_PROFILE_EXPAND_SETTLE_SECONDS", "0.5")
)
LINKEDIN_SAVE_LINGER_BASE_SECONDS: float = float(_optional("LINKEDIN_SAVE_LINGER_BASE_SECONDS", "3.6"))
LINKEDIN_SAVE_LINGER_MIN_SECONDS: float = float(_optional("LINKEDIN_SAVE_LINGER_MIN_SECONDS", "2.0"))
LINKEDIN_SAVE_LINGER_MAX_SECONDS: float = float(_optional("LINKEDIN_SAVE_LINGER_MAX_SECONDS", "6.0"))
LINKEDIN_SAVE_LINGER_MIN_CHUNKS_BACK: int = int(_optional("LINKEDIN_SAVE_LINGER_MIN_CHUNKS_BACK", "1"))
LINKEDIN_SAVE_LINGER_MAX_CHUNKS_BACK: int = int(_optional("LINKEDIN_SAVE_LINGER_MAX_CHUNKS_BACK", "2"))
LINKEDIN_REJECT_CLOSE_BASE_SECONDS: float = float(_optional("LINKEDIN_REJECT_CLOSE_BASE_SECONDS", "0.35"))
LINKEDIN_REJECT_CLOSE_MIN_SECONDS: float = float(_optional("LINKEDIN_REJECT_CLOSE_MIN_SECONDS", "0.2"))
LINKEDIN_REJECT_CLOSE_MAX_SECONDS: float = float(_optional("LINKEDIN_REJECT_CLOSE_MAX_SECONDS", "1.2"))
LINKEDIN_PANEL_CLOSE_SETTLE_SECONDS: float = float(_optional("LINKEDIN_PANEL_CLOSE_SETTLE_SECONDS", "0.5"))

# --- Architecture-specific overrides ---
# Per-architecture behavioral parameters. Looked up at runtime via
# ExecutionPlan.architecture; falls through to global defaults when empty.
ARCHITECTURE_OVERRIDES: dict[str, dict] = {
    "sniper": {
        "min_pages_by_result_count": [(500, 2), (100, 2), (30, 1), (0, 1)],
        "early_exit_facial_no_rate": 0.90,
    },
    "dragnet": {
        "min_pages_by_result_count": [(500, 4), (100, 3), (30, 2), (0, 1)],
        "early_exit_facial_no_rate": 0.97,
    },
    "titration": {
        "min_pages_by_result_count": [(500, 2), (100, 2), (30, 1), (0, 1)],
        "early_exit_facial_no_rate": 0.95,
    },
    "negative_space": {
        "min_pages_by_result_count": [(500, 3), (100, 2), (30, 1), (0, 1)],
        "early_exit_facial_no_rate": 0.93,
    },
    "company_first": {
        "min_pages_by_result_count": [(500, 3), (100, 2), (30, 1), (0, 1)],
        "early_exit_facial_no_rate": 0.93,
    },
    "title_first": {
        "min_pages_by_result_count": [(500, 2), (100, 1), (30, 1), (0, 1)],
        "early_exit_facial_no_rate": 0.90,
    },
}

# --- Paths ---
PROJECT_ROOT: Path = Path(__file__).parent.parent
# OUTPUT_DIR is the writable root for all per-state runtime data
# (state dirs, runtime_state.sqlite3, projection JSONLs). When Cloris
# runs as a frozen .app, this relocates under
# ``~/Library/Application Support/Cloris/output/`` because the bundle
# is read-only. Dev (running from the repo) preserves the historical
# ``PROJECT_ROOT/output`` layout — see ``shared/user_data_dir.py`` for
# the resolution rules and the ``CLORIS_USER_DATA_DIR`` opt-in for
# tests / power users.
from shared.user_data_dir import output_dir as _resolve_output_dir
OUTPUT_DIR: Path = _resolve_output_dir()
