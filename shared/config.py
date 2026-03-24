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
ANTHROPIC_API_KEY: str = _optional("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY: str = _optional("OPENAI_API_KEY", "")
GOOGLE_API_KEY: str = _optional("GOOGLE_API_KEY", "")
SUPABASE_ANON_KEY: str = _optional("SUPABASE_ANON_KEY", "")

CHEAP_MODEL_PROVIDER: str = _optional("CHEAP_MODEL_PROVIDER", "openai")

# --- Model Names ---
CHEAP_MODEL_NAME: str = _optional("CHEAP_MODEL_NAME", "gpt-4o-mini")
OPUS_MODEL_NAME: str = _optional("OPUS_MODEL_NAME", "claude-opus-4-6")

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

# --- Paths ---
PROJECT_ROOT: Path = Path(__file__).parent.parent
OUTPUT_DIR: Path = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
