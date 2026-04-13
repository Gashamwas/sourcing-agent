from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from shared.llm_clients import opus_llm
from shared.llm_usage import llm_usage_session
from shared.storage import read_jsonl


class _FakeAnthropicMessage:
    def __init__(self, stop_reason: str) -> None:
        self.stop_reason = stop_reason
        self.usage = SimpleNamespace(
            input_tokens=111,
            output_tokens=22,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
        self.content = [SimpleNamespace(text='{"status":"partial"}')]


class _FakeAnthropicClient:
    def __init__(self, *, stop_reason: str) -> None:
        self.messages = SimpleNamespace(
            create=lambda **kwargs: _FakeAnthropicMessage(stop_reason)
        )


def test_opus_llm_logs_usage_even_when_response_truncates():
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "token-cost-log.jsonl"
        fake_module = SimpleNamespace(
            Anthropic=lambda api_key, timeout: _FakeAnthropicClient(stop_reason="max_tokens")
        )

        with patch.dict(sys.modules, {"anthropic": fake_module}):
            with llm_usage_session(log_path, pipeline="test_pipeline"):
                with pytest.raises(RuntimeError, match="stop_reason=max_tokens"):
                    opus_llm(
                        "system prompt",
                        "user prompt",
                        expect_json=False,
                        max_tokens=123,
                        usage_context={"stage": "test_stage"},
                    )

        records = read_jsonl(log_path)
        assert records
        assert records[0]["stage"] == "test_stage"
        assert records[0]["input_tokens"] == 111
        assert records[0]["output_tokens"] == 22
        assert records[0]["stop_reason"] == "max_tokens"
