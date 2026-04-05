"""LLM client wrappers. Two functions: cheap_llm() for extraction, opus_llm() for judgment."""

from __future__ import annotations
import json
import random
import time
import shared.config as config


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

_RETRYABLE_STATUS_CODES = {429, 502, 503, 529}
_MAX_RETRIES = 5


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is a transient API error worth retrying."""
    err_str = str(exc)
    # Anthropic SDK raises APIStatusError with status_code attribute
    if hasattr(exc, 'status_code') and exc.status_code in _RETRYABLE_STATUS_CODES:
        return True
    # OpenAI SDK raises similar structured errors
    if hasattr(exc, 'status_code') and exc.status_code in _RETRYABLE_STATUS_CODES:
        return True
    # Fallback: check error message for known transient patterns
    for pattern in ['overloaded', '529', '503', '502', 'rate_limit', '429', 'capacity']:
        if pattern in err_str.lower():
            return True
    return False


def _retry_with_backoff(fn, label: str = "LLM"):
    """Call fn() with exponential backoff retry on transient errors."""
    for attempt in range(_MAX_RETRIES):
        try:
            return fn()
        except Exception as e:
            if attempt < _MAX_RETRIES - 1 and _is_retryable(e):
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"    [RETRY] {label} error ({e}), attempt {attempt + 1}/{_MAX_RETRIES}, waiting {wait:.1f}s")
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def cheap_llm(system_prompt: str, user_prompt: str, expect_json: bool = True) -> str | dict | list:
    """Call the cheap model (GPT-4o-mini or Gemini Flash) for DOM extraction.

    If expect_json=True, parses the response as JSON and returns dict/list.
    Otherwise returns raw string.
    """
    if config.CHEAP_MODEL_PROVIDER == "openai":
        return _call_openai(system_prompt, user_prompt, expect_json)
    elif config.CHEAP_MODEL_PROVIDER == "anthropic":
        return _call_anthropic_cheap(system_prompt, user_prompt, expect_json)
    elif config.CHEAP_MODEL_PROVIDER == "google":
        return _call_google(system_prompt, user_prompt, expect_json)
    else:
        raise RuntimeError(f"Unknown CHEAP_MODEL_PROVIDER: {config.CHEAP_MODEL_PROVIDER}")


def opus_llm(system_prompt: str, user_prompt: str, expect_json: bool = True, max_tokens: int = 8192) -> str | dict:
    """Call Opus for candidate judgment. Returns parsed JSON or raw string."""
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=300.0)

    def _call():
        message = client.messages.create(
            model=config.OPUS_MODEL_NAME,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        if message.stop_reason != "end_turn":
            raise RuntimeError(f"Opus response truncated: stop_reason={message.stop_reason}. Increase max_tokens or reduce prompt size.")
        return message.content[0].text.strip()

    text = _retry_with_backoff(_call, label="Opus")

    if expect_json:
        return _parse_json_response(text)
    return text


def opus_llm_cached(system_prompt: str, user_prompt: str, expect_json: bool = True, max_tokens: int = 8192) -> str | dict:
    """Call Opus with prompt caching on the system prompt.

    System prompt is sent as a content block with cache_control: {"type": "ephemeral"}.
    Cache write costs 1.25x, cache read costs 0.1x, TTL is 5 minutes (refreshed on hit).
    """
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=300.0)

    def _call():
        message = client.messages.create(
            model=config.OPUS_MODEL_NAME,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )
        if message.stop_reason != "end_turn":
            raise RuntimeError(f"Opus response truncated: stop_reason={message.stop_reason}. Increase max_tokens or reduce prompt size.")
        return message.content[0].text.strip()

    text = _retry_with_backoff(_call, label="Opus-cached")

    if expect_json:
        return _parse_json_response(text)
    return text


def facial_llm(system_prompt: str, user_prompt: str, expect_json: bool = True, max_tokens: int = 2048) -> str | dict:
    """Call the facial triage model with prompt caching.

    Defaults to Opus (same as opus_llm_cached) but can be overridden to Sonnet
    via FACIAL_MODEL_NAME in .env for 5x cost reduction on facial calls.
    Lower default max_tokens since facial responses are short.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=300.0)

    def _call():
        message = client.messages.create(
            model=config.FACIAL_MODEL_NAME,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )
        if message.stop_reason != "end_turn":
            raise RuntimeError(f"Facial model response truncated: stop_reason={message.stop_reason}.")
        return message.content[0].text.strip()

    text = _retry_with_backoff(_call, label="Facial")

    if expect_json:
        return _parse_json_response(text)
    return text


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _call_anthropic_cheap(system_prompt: str, user_prompt: str, expect_json: bool) -> str | dict | list:
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=120.0)

    def _call():
        message = client.messages.create(
            model=config.CHEAP_MODEL_NAME,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text.strip()

    text = _retry_with_backoff(_call, label="Anthropic-cheap")

    if expect_json:
        return _parse_json_response(text)
    return text


def _call_openai(system_prompt: str, user_prompt: str, expect_json: bool) -> str | dict | list:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=60.0)
    kwargs = {}
    if expect_json:
        kwargs["response_format"] = {"type": "json_object"}

    def _call():
        response = client.chat.completions.create(
            model=config.CHEAP_MODEL_NAME,
            max_tokens=8192,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            timeout=120.0,
            **kwargs,
        )
        return response.choices[0].message.content.strip()

    text = _retry_with_backoff(_call, label="OpenAI")

    if expect_json:
        return _parse_json_response(text)
    return text


def _call_google(system_prompt: str, user_prompt: str, expect_json: bool) -> str | dict | list:
    from google import genai

    client = genai.Client(api_key=config.GOOGLE_API_KEY)

    def _call():
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"{system_prompt}\n\n{user_prompt}",
            config={
                "temperature": 0.1,
                "response_mime_type": "application/json" if expect_json else "text/plain",
            },
        )
        return response.text.strip()

    text = _retry_with_backoff(_call, label="Google")

    if expect_json:
        return _parse_json_response(text)
    return text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict | list:
    """Parse JSON from LLM response, handling markdown code fences."""
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try to find JSON object or array in the text
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue
        # Last resort: try to close truncated JSON by finding the last complete key-value
        # and closing any open braces/brackets
        if text.strip().startswith("{"):
            # Truncate to last complete string value (ends with ")
            last_quote = text.rfind('"')
            if last_quote > 0:
                truncated = text[:last_quote + 1]
                # Count open/close braces to close properly
                open_braces = truncated.count("{") - truncated.count("}")
                open_brackets = truncated.count("[") - truncated.count("]")
                truncated += "}" * open_braces + "]" * open_brackets
                try:
                    return json.loads(truncated)
                except json.JSONDecodeError:
                    pass
        raise RuntimeError(f"Could not parse JSON from LLM response: {text[:500]}") from e
