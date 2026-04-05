"""Tests for token efficiency optimization (prompt caching, batch facial, model downgrade).

Run with: python -m pytest tests/test_token_efficiency.py -v
"""

from unittest.mock import MagicMock, patch, call
import json

from shared.schemas import CandidateSnippet, OpusDecision


def _make_snippet(**kwargs) -> CandidateSnippet:
    defaults = {
        "name": "Test Person",
        "headline": "ML Engineer",
        "current_title": "ML Engineer",
        "current_company": "Acme Corp",
        "location": "San Francisco",
        "education_snippet": "BS CS Stanford",
        "profile_url": "/talent/profile/test123",
        "source_string_id": 1,
        "source_string_name": "test",
        "page": 1,
        "result_rank": 1,
    }
    defaults.update(kwargs)
    return CandidateSnippet(**defaults)


# ---------------------------------------------------------------------------
# Phase 1: Prompt Caching — opus_llm_cached passes cache_control
# ---------------------------------------------------------------------------

def _mock_anthropic_client():
    """Create a mock Anthropic client with standard success response."""
    mock_msg = MagicMock()
    mock_msg.stop_reason = "end_turn"
    mock_msg.content = [MagicMock(text='{"answer": "yes"}')]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    mock_module = MagicMock()
    mock_module.Anthropic.return_value = mock_client
    return mock_module, mock_client


class TestOpusLlmCached:
    def test_passes_cache_control_annotation(self):
        """opus_llm_cached sends system as content blocks with cache_control."""
        mock_module, mock_client = _mock_anthropic_client()

        import shared.llm_clients as llm_mod
        orig_config = llm_mod.config
        try:
            llm_mod.config = MagicMock(ANTHROPIC_API_KEY="k", OPUS_MODEL_NAME="claude-opus-4-6")
            with patch.dict("sys.modules", {"anthropic": mock_module}):
                llm_mod.opus_llm_cached("system prompt", "user prompt")

            call_kwargs = mock_client.messages.create.call_args
            system_arg = call_kwargs.kwargs["system"]
            assert isinstance(system_arg, list)
            assert system_arg[0]["type"] == "text"
            assert system_arg[0]["text"] == "system prompt"
            assert system_arg[0]["cache_control"] == {"type": "ephemeral"}
        finally:
            llm_mod.config = orig_config

    def test_opus_llm_still_passes_string_system(self):
        """opus_llm (non-cached) still passes system as a plain string."""
        mock_module, mock_client = _mock_anthropic_client()

        import shared.llm_clients as llm_mod
        orig_config = llm_mod.config
        try:
            llm_mod.config = MagicMock(ANTHROPIC_API_KEY="k", OPUS_MODEL_NAME="claude-opus-4-6")
            with patch.dict("sys.modules", {"anthropic": mock_module}):
                llm_mod.opus_llm("system prompt", "user prompt")

            call_kwargs = mock_client.messages.create.call_args
            system_arg = call_kwargs.kwargs["system"]
            assert isinstance(system_arg, str)
            assert system_arg == "system prompt"
        finally:
            llm_mod.config = orig_config


# ---------------------------------------------------------------------------
# Phase 1: Split assembly functions produce correct static prefix
# ---------------------------------------------------------------------------

class TestSplitAssembly:
    def _make_brief(self):
        """Create a minimal mock brief for template testing."""
        brief = MagicMock()
        brief.role_title = "ML Engineer"
        brief.role_level = "IC4"
        brief.role_summary = "Build ML systems"
        brief.fast_exit_block.return_value = "- Wrong domain entirely"
        brief.trajectory_yes_block.return_value = "- ML research positions"
        brief.trajectory_ambiguous_block.return_value = "- Mixed ML/non-ML"
        brief.trajectory_no_block.return_value = "- Pure frontend"
        brief.non_fit_block.return_value = "- Management consulting"
        brief.capability_area_names.return_value = ["Data Curation", "RL"]
        brief.trajectory_yes_compact.return_value = "ML research"
        brief.trajectory_ambiguous_compact.return_value = "Mixed"
        brief.trajectory_no_compact.return_value = "Frontend"
        brief.non_fit_compact.return_value = "Consulting"
        brief.capability_area_names_inline.return_value = "Data Curation, RL"
        # Full eval fields
        brief.minimum_years_experience = 5
        brief.minimum_bar_description = "Hands-on ML"
        brief.capability_area_block.return_value = "1. Data Curation"
        brief.depth_block.return_value = "Builder vs User"
        brief.non_fit_override_rule_block.return_value = "Override rule"
        brief.employer_signal_block.return_value = "Employer rules"
        brief.inferential_save_block.return_value = "Inferential rules"
        brief.discriminating_skills_examples.return_value = "QLoRA, vLLM"
        brief.seniority_calibration_block.return_value = ""
        brief.executive_builder_block.return_value = ""
        brief.decision_matrix_block.return_value = "Decision matrix"
        brief.post_evaluation_safety_net.return_value = ""
        brief.post_save_modifiers_block.return_value = ""
        brief.calibration_block.return_value = ""
        brief.instructions_block.return_value = ""
        brief.capability_area_stack_rank_guidance.return_value = ""
        return brief

    def test_facial_system_contains_no_candidate_data(self):
        from linkedin.judgment_templates import assemble_facial_system
        brief = self._make_brief()
        system = assemble_facial_system(brief)

        assert "ML Engineer" in system
        assert "FACIAL_YES" in system
        assert "FACIAL_NO" in system
        # Should NOT contain actual candidate data — just a placeholder
        assert "[provided in user message]" in system

    def test_full_evaluation_system_contains_no_candidate_data(self):
        from linkedin.judgment_templates import assemble_full_evaluation_system
        brief = self._make_brief()
        system = assemble_full_evaluation_system(brief)

        assert "ML Engineer" in system
        assert "SAVE" in system
        assert "REJECT" in system
        assert "[provided in user message]" in system

    def test_facial_batch_system_contains_no_candidate_data(self):
        from linkedin.judgment_templates import assemble_facial_batch_system
        brief = self._make_brief()
        system = assemble_facial_batch_system(brief)

        assert "ML Engineer" in system
        assert "FACIAL_YES" in system
        assert "[provided in user message]" in system

    def test_github_facial_system_contains_no_candidate_data(self):
        from github.judgment_templates import assemble_github_facial_system
        brief = self._make_brief()
        system = assemble_github_facial_system(brief)

        assert "ML Engineer" in system
        assert "FACIAL_YES" in system
        assert "[provided in user message]" in system

    def test_github_facial_batch_system_contains_no_candidate_data(self):
        from github.judgment_templates import assemble_github_facial_batch_system
        brief = self._make_brief()
        system = assemble_github_facial_batch_system(brief)

        assert "ML Engineer" in system
        assert "FACIAL_YES" in system
        assert "[provided in user message]" in system

    def test_github_full_evaluation_system_contains_no_candidate_data(self):
        from github.judgment_templates import assemble_github_full_evaluation_system
        brief = self._make_brief()
        system = assemble_github_full_evaluation_system(brief)

        assert "ML Engineer" in system
        assert "SAVE" in system
        assert "[provided in user message]" in system


# ---------------------------------------------------------------------------
# Phase 2: Batch facial response parser
# ---------------------------------------------------------------------------

class TestParseFacialBatchResponse:
    def test_well_formed_response(self):
        from linkedin.judgment_templates import parse_facial_batch_response
        raw = (
            "[1] FACIAL_YES | Strong ML trajectory at DeepMind\n"
            "[2] FACIAL_NO | Pure frontend developer\n"
            "[3] FACIAL_YES | PhD in RL from Stanford\n"
        )
        results = parse_facial_batch_response(raw, 3)
        assert len(results) == 3
        assert results[0].decision == "FACIAL_YES"
        assert "DeepMind" in results[0].reason
        assert results[1].decision == "FACIAL_NO"
        assert results[2].decision == "FACIAL_YES"

    def test_missing_entry_returns_parse_failure(self):
        from linkedin.judgment_templates import parse_facial_batch_response
        raw = (
            "[1] FACIAL_YES | Good candidate\n"
            "[3] FACIAL_NO | Not a fit\n"
        )
        results = parse_facial_batch_response(raw, 3)
        assert len(results) == 3
        assert results[0].decision == "FACIAL_YES"
        assert results[1].decision == "PARSE_FAILURE"
        assert "missing" in results[1].reason
        assert results[2].decision == "FACIAL_NO"

    def test_malformed_line_ignored(self):
        from linkedin.judgment_templates import parse_facial_batch_response
        raw = (
            "[1] FACIAL_YES | Good\n"
            "This is not a valid line\n"
            "[2] FACIAL_NO | Bad\n"
        )
        results = parse_facial_batch_response(raw, 2)
        assert len(results) == 2
        assert results[0].decision == "FACIAL_YES"
        assert results[1].decision == "FACIAL_NO"

    def test_empty_response(self):
        from linkedin.judgment_templates import parse_facial_batch_response
        results = parse_facial_batch_response("", 3)
        assert len(results) == 3
        assert all(r.decision == "PARSE_FAILURE" for r in results)

    def test_case_insensitive(self):
        from linkedin.judgment_templates import parse_facial_batch_response
        raw = "[1] facial_yes | Good fit\n"
        results = parse_facial_batch_response(raw, 1)
        assert results[0].decision == "FACIAL_YES"


# ---------------------------------------------------------------------------
# Phase 2: facial_judge_batch returns correct decisions
# ---------------------------------------------------------------------------

class TestFacialJudgeBatch:
    def test_batch_returns_correct_count(self):
        """facial_judge_batch returns one OpusDecision per snippet."""
        snippets = [
            _make_snippet(name="Alice", profile_url="/alice"),
            _make_snippet(name="Bob", profile_url="/bob"),
            _make_snippet(name="Carol", profile_url="/carol"),
        ]

        mock_brief = MagicMock()
        mock_brief.has_v2_schema = True
        mock_brief._new_brief = MagicMock()

        batch_response = (
            "[1] FACIAL_YES | ML trajectory\n"
            "[2] FACIAL_NO | Wrong domain\n"
            "[3] FACIAL_YES | RL researcher\n"
        )

        with patch("shared.judger.facial_llm", return_value=batch_response), \
             patch("shared.judger.assemble_facial_batch_system", return_value="system"):
            from shared.judger import facial_judge_batch
            decisions = facial_judge_batch(snippets, mock_brief)

        assert len(decisions) == 3
        assert decisions[0].decision == "FACIAL_YES"
        assert decisions[0].candidate_name == "Alice"
        assert decisions[1].decision == "FACIAL_NO"
        assert decisions[1].candidate_name == "Bob"
        assert decisions[2].decision == "FACIAL_YES"
        assert decisions[2].candidate_name == "Carol"

    def test_batch_falls_back_to_sequential_on_failure(self):
        """If batch call fails, falls back to individual facial_judge calls."""
        snippets = [_make_snippet(name="Alice", profile_url="/alice")]

        mock_brief = MagicMock()
        mock_brief.has_v2_schema = True
        mock_brief._new_brief = MagicMock()

        with patch("shared.judger.facial_llm", side_effect=RuntimeError("API down")), \
             patch("shared.judger.assemble_facial_batch_system", return_value="system"), \
             patch("shared.judger.facial_judge") as mock_sequential:
            mock_sequential.return_value = OpusDecision(
                stage="facial", decision="FACIAL_YES", path="none",
                confidence=1.0, rationale="sequential fallback",
                candidate_name="Alice", profile_url="/alice",
            )

            from shared.judger import facial_judge_batch
            decisions = facial_judge_batch(snippets, mock_brief)

        assert len(decisions) == 1
        assert decisions[0].decision == "FACIAL_YES"
        mock_sequential.assert_called_once()

    def test_partial_batch_parse_failures_retry_only_failed_entries(self):
        """Malformed batch lines should be retried sequentially for affected snippets only."""
        snippets = [
            _make_snippet(name="Alice", profile_url="/alice"),
            _make_snippet(name="Bob", profile_url="/bob"),
        ]

        mock_brief = MagicMock()
        mock_brief.has_v2_schema = True
        mock_brief._new_brief = MagicMock()

        batch_response = "[1] FACIAL_YES | ML trajectory\n"

        with patch("shared.judger.facial_llm", return_value=batch_response), \
             patch("shared.judger.assemble_facial_batch_system", return_value="system"), \
             patch("shared.judger.facial_judge") as mock_sequential:
            mock_sequential.return_value = OpusDecision(
                stage="facial", decision="FACIAL_NO", path="none",
                confidence=1.0, rationale="sequential fallback",
                candidate_name="Bob", profile_url="/bob",
            )

            from shared.judger import facial_judge_batch
            decisions = facial_judge_batch(snippets, mock_brief)

        assert len(decisions) == 2
        assert decisions[0].decision == "FACIAL_YES"
        assert decisions[1].decision == "FACIAL_NO"
        mock_sequential.assert_called_once_with(snippets[1], mock_brief, prompt_prefix="")

    def test_old_brief_uses_sequential(self):
        """Old briefs (no V2 schema) fall back to sequential facial_judge."""
        snippets = [_make_snippet(name="Alice", profile_url="/alice")]

        mock_brief = MagicMock()
        mock_brief.has_v2_schema = False

        with patch("shared.judger.facial_judge") as mock_sequential:
            mock_sequential.return_value = OpusDecision(
                stage="facial", decision="FACIAL_NO", path="none",
                confidence=1.0, rationale="old brief path",
                candidate_name="Alice", profile_url="/alice",
            )

            from shared.judger import facial_judge_batch
            decisions = facial_judge_batch(snippets, mock_brief)

        assert len(decisions) == 1
        assert decisions[0].decision == "FACIAL_NO"


class TestGitHubFacialJudgeBatch:
    def test_github_batch_fallback_preserves_metadata(self):
        portfolio_texts = [
            ("Alice Example", "https://github.com/alice", "portfolio 1"),
        ]

        mock_brief = MagicMock()
        mock_brief.has_v2_schema = True
        mock_brief._new_brief = MagicMock()

        with patch("shared.judger.facial_llm", side_effect=RuntimeError("API down")), \
             patch("shared.judger.github_facial_judge") as mock_single:
            mock_single.return_value = OpusDecision(
                stage="facial", decision="FACIAL_YES", path="none",
                confidence=1.0, rationale="fallback", candidate_name="", profile_url="",
            )

            from shared.judger import github_facial_judge_batch
            decisions = github_facial_judge_batch(portfolio_texts, mock_brief)

        assert len(decisions) == 1
        assert decisions[0].candidate_name == "Alice Example"
        assert decisions[0].profile_url == "https://github.com/alice"
        assert decisions[0].decision == "FACIAL_YES"


# ---------------------------------------------------------------------------
# Phase 3: FACIAL_MODEL_NAME defaults to OPUS_MODEL_NAME
# ---------------------------------------------------------------------------

class TestFacialModelConfig:
    def test_default_matches_opus(self):
        from shared.config import FACIAL_MODEL_NAME, OPUS_MODEL_NAME
        assert FACIAL_MODEL_NAME == OPUS_MODEL_NAME

    def test_facial_llm_uses_facial_model_name(self):
        """facial_llm should use config.FACIAL_MODEL_NAME, not OPUS_MODEL_NAME."""
        mock_module, mock_client = _mock_anthropic_client()
        mock_client.messages.create.return_value.content[0].text = "DECISION: FACIAL_YES\nREASON: good"

        import shared.llm_clients as llm_mod
        orig_config = llm_mod.config
        try:
            llm_mod.config = MagicMock(
                ANTHROPIC_API_KEY="k",
                FACIAL_MODEL_NAME="claude-sonnet-4-6",
            )
            with patch.dict("sys.modules", {"anthropic": mock_module}):
                llm_mod.facial_llm("system", "user", expect_json=False)

            call_kwargs = mock_client.messages.create.call_args
            assert call_kwargs.kwargs["model"] == "claude-sonnet-4-6"
        finally:
            llm_mod.config = orig_config

    def test_facial_llm_lower_default_max_tokens(self):
        """facial_llm should default to max_tokens=2048."""
        mock_module, mock_client = _mock_anthropic_client()

        import shared.llm_clients as llm_mod
        orig_config = llm_mod.config
        try:
            llm_mod.config = MagicMock(
                ANTHROPIC_API_KEY="k",
                FACIAL_MODEL_NAME="claude-opus-4-6",
            )
            with patch.dict("sys.modules", {"anthropic": mock_module}):
                llm_mod.facial_llm("system", "user")

            call_kwargs = mock_client.messages.create.call_args
            assert call_kwargs.kwargs["max_tokens"] == 2048
        finally:
            llm_mod.config = orig_config
