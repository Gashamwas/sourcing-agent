"""LLM client wrappers. Two functions: cheap_llm() for extraction, opus_llm() for judgment."""

from __future__ import annotations
import json
import config


def cheap_llm(system_prompt: str, user_prompt: str, expect_json: bool = True) -> str | dict | list:
    """Call the cheap model (GPT-4o-mini or Gemini Flash) for DOM extraction.
    
    If expect_json=True, parses the response as JSON and returns dict/list.
    Otherwise returns raw string.
    """
    if config.CHEAP_MODEL_PROVIDER == "openai":
        return _call_openai(system_prompt, user_prompt, expect_json)
    elif config.CHEAP_MODEL_PROVIDER == "google":
        return _call_google(system_prompt, user_prompt, expect_json)
    else:
        raise RuntimeError(f"Unknown CHEAP_MODEL_PROVIDER: {config.CHEAP_MODEL_PROVIDER}")


def opus_llm(system_prompt: str, user_prompt: str, expect_json: bool = True, max_tokens: int = 8192) -> str | dict:
    """Call Opus for candidate judgment. Returns parsed JSON or raw string."""
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=config.OPUS_MODEL_NAME,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    if message.stop_reason != "end_turn":
        raise RuntimeError(f"Opus response truncated: stop_reason={message.stop_reason}. Increase max_tokens or reduce prompt size.")
    text = message.content[0].text.strip()

    if expect_json:
        return _parse_json_response(text)
    return text


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _call_openai(system_prompt: str, user_prompt: str, expect_json: bool) -> str | dict | list:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    kwargs = {}
    if expect_json:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(
        model=config.CHEAP_MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        **kwargs,
    )
    text = response.choices[0].message.content.strip()

    if expect_json:
        return _parse_json_response(text)
    return text


def _call_google(system_prompt: str, user_prompt: str, expect_json: bool) -> str | dict | list:
    from google import genai

    client = genai.Client(api_key=config.GOOGLE_API_KEY)
    
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"{system_prompt}\n\n{user_prompt}",
        config={
            "temperature": 0.1,
            "response_mime_type": "application/json" if expect_json else "text/plain",
        },
    )
    text = response.text.strip()

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
