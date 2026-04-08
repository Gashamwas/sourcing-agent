"""Configuration loader. Reads .env and provides typed access to all settings.

Note: For Turing corporate proxy, you may need:
    export NODE_TLS_REJECT_UNAUTHORIZED=0
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (one level up from shared/)
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


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
SUPABASE_ANON_KEY: str = _optional("SUPABASE_ANON_KEY", "")

CHEAP_MODEL_PROVIDER: str = _optional("CHEAP_MODEL_PROVIDER", "openai")

# --- Model Names ---
CHEAP_MODEL_NAME: str = _optional("CHEAP_MODEL_NAME", "gpt-4o-mini")
OPUS_MODEL_NAME: str = _optional("OPUS_MODEL_NAME", "claude-opus-4-6")
FACIAL_MODEL_NAME: str = _optional("FACIAL_MODEL_NAME", OPUS_MODEL_NAME)

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

# --- Pagination minimum depth (prevents premature stop on productive strings) ---
# Opus can't stop/abandon a string until it has reviewed at least this many pages.
# Keyed by result count threshold: strings with >= N results must review >= M pages.
MIN_PAGES_BY_RESULT_COUNT: list[tuple[int, int]] = [
    # (min_results, min_pages)
    (500, 3),   # 500+ results → must review at least 3 pages before stop
    (100, 2),   # 100+ results → must review at least 2 pages before stop
    (30, 1),    # 30+ results  → can stop after 1 page (current behavior)
    (0, 1),     # <30 results  → can stop after 1 page
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
OUTPUT_DIR: Path = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
