"""Helpers for token/cost logging across LLM-backed workflows."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.storage import append_jsonl


_USAGE_LOG_PATH: ContextVar[Path | None] = ContextVar("llm_usage_log_path", default=None)
_USAGE_BASE_CONTEXT: ContextVar[dict[str, Any]] = ContextVar(
    "llm_usage_base_context",
    default={},
)


MODEL_RATE_TABLE_USD_PER_MTOKEN: dict[str, dict[str, float]] = {
    "claude-opus": {
        "input": 15.0,
        "output": 75.0,
        "cache_creation_input": 18.75,
        "cache_read_input": 1.5,
    },
    "openai/gpt-5.2": {
        "input": 1.75,
        "output": 14.0,
        "cache_read_input": 0.175,
    },
    "xai/grok-4-1-fast-non-reasoning": {
        "input": 0.2,
        "output": 0.5,
        "cache_read_input": 0.05,
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _lookup_model_rates(model: str) -> tuple[dict[str, float] | None, str]:
    normalized = _normalize_text(model)
    if not normalized:
        return None, "unknown"
    exact = MODEL_RATE_TABLE_USD_PER_MTOKEN.get(normalized)
    if exact:
        return exact, "exact"
    lowered = normalized.lower()
    for key, rates in MODEL_RATE_TABLE_USD_PER_MTOKEN.items():
        if lowered.startswith(key.lower()):
            return rates, f"prefix:{key}"
    return None, "unknown"


def estimate_usage_cost_usd(
    *,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> tuple[float | None, str]:
    rates, rate_source = _lookup_model_rates(model)
    if not rates:
        return None, rate_source
    cost = 0.0
    cost += (input_tokens / 1_000_000.0) * rates.get("input", 0.0)
    cost += (output_tokens / 1_000_000.0) * rates.get("output", 0.0)
    cost += (cache_read_input_tokens / 1_000_000.0) * rates.get(
        "cache_read_input",
        0.0,
    )
    cost += (cache_creation_input_tokens / 1_000_000.0) * rates.get(
        "cache_creation_input",
        0.0,
    )
    return round(cost, 6), rate_source


@contextmanager
def llm_usage_session(log_path: str | Path | None, **base_context: Any):
    path = Path(log_path) if log_path else None
    path_token = _USAGE_LOG_PATH.set(path)
    context_token = _USAGE_BASE_CONTEXT.set(dict(base_context))
    try:
        yield
    finally:
        _USAGE_LOG_PATH.reset(path_token)
        _USAGE_BASE_CONTEXT.reset(context_token)


def current_llm_usage_log_path() -> Path | None:
    return _USAGE_LOG_PATH.get()


def record_llm_usage(
    *,
    provider: str,
    model: str,
    usage: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
    usage_context: dict[str, Any] | None = None,
) -> None:
    log_path = _USAGE_LOG_PATH.get()
    if not log_path:
        return
    usage = dict(usage or {})
    request = dict(request or {})
    merged_context = dict(_USAGE_BASE_CONTEXT.get())
    merged_context.update(usage_context or {})

    input_tokens = _safe_int(usage.get("input_tokens"))
    output_tokens = _safe_int(usage.get("output_tokens"))
    cache_read_input_tokens = _safe_int(usage.get("cache_read_input_tokens"))
    cache_creation_input_tokens = _safe_int(usage.get("cache_creation_input_tokens"))
    estimated_cost_usd, rate_source = estimate_usage_cost_usd(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
    )

    record = {
        "timestamp": _utc_now(),
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_input_tokens": cache_read_input_tokens,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "estimated_cost_usd": estimated_cost_usd,
        "rate_source": rate_source,
        **merged_context,
        **request,
    }
    append_jsonl(log_path, record)


def anthropic_usage_dict(message: Any) -> dict[str, int]:
    usage = getattr(message, "usage", None)
    return {
        "input_tokens": _safe_int(getattr(usage, "input_tokens", 0)),
        "output_tokens": _safe_int(getattr(usage, "output_tokens", 0)),
        "cache_read_input_tokens": _safe_int(
            getattr(usage, "cache_read_input_tokens", 0)
        ),
        "cache_creation_input_tokens": _safe_int(
            getattr(usage, "cache_creation_input_tokens", 0)
        ),
    }


def openai_usage_dict(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    details = getattr(usage, "input_tokens_details", None)
    cached_tokens = 0
    if details is not None:
        cached_tokens = _safe_int(getattr(details, "cached_tokens", 0))
    if not cached_tokens and isinstance(details, dict):
        cached_tokens = _safe_int(details.get("cached_tokens", 0))
    return {
        "input_tokens": _safe_int(
            getattr(usage, "input_tokens", None)
            if usage is not None
            else 0,
            default=_safe_int(getattr(usage, "prompt_tokens", 0)),
        ),
        "output_tokens": _safe_int(
            getattr(usage, "output_tokens", None)
            if usage is not None
            else 0,
            default=_safe_int(getattr(usage, "completion_tokens", 0)),
        ),
        "cache_read_input_tokens": cached_tokens,
        "cache_creation_input_tokens": 0,
    }
