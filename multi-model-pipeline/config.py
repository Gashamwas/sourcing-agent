"""Configuration loader. Reads .env and provides typed access to all settings."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val or val.startswith("REPLACE_ME"):
        raise RuntimeError(f"Missing or placeholder value for {key}. Edit .env first.")
    return val


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# --- API Keys ---
ANTHROPIC_API_KEY: str = _require("ANTHROPIC_API_KEY")
CHEAP_MODEL_PROVIDER: str = _optional("CHEAP_MODEL_PROVIDER", "openai")

if CHEAP_MODEL_PROVIDER == "openai":
    OPENAI_API_KEY: str = _require("OPENAI_API_KEY")
    GOOGLE_API_KEY: str = ""
elif CHEAP_MODEL_PROVIDER == "google":
    GOOGLE_API_KEY: str = _require("GOOGLE_API_KEY")
    OPENAI_API_KEY: str = ""
else:
    raise RuntimeError(f"CHEAP_MODEL_PROVIDER must be 'openai' or 'google', got '{CHEAP_MODEL_PROVIDER}'")

# --- Model Names ---
CHEAP_MODEL_NAME: str = _optional("CHEAP_MODEL_NAME", "gpt-4o-mini")
OPUS_MODEL_NAME: str = _optional("OPUS_MODEL_NAME", "claude-opus-4-6")

# --- Browser ---
CDP_URL: str = _optional("CDP_URL", "http://127.0.0.1:18800")

# --- Behavior ---
MAX_PAGES_PER_STRING: int = int(_optional("MAX_PAGES_PER_STRING", "0"))
PAGE_DELAY_SECONDS: float = float(_optional("PAGE_DELAY_SECONDS", "3"))
PROFILE_DELAY_SECONDS: float = float(_optional("PROFILE_DELAY_SECONDS", "2"))

# --- Paths ---
PROJECT_ROOT: Path = Path(__file__).parent
OUTPUT_DIR: Path = PROJECT_ROOT / "output"
BRIEFS_DIR: Path = PROJECT_ROOT / "briefs"
OUTPUT_DIR.mkdir(exist_ok=True)
