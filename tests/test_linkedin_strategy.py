"""Tests for LinkedIn strategy prompt assembly and edge-case rebalancing."""

from pathlib import Path
from unittest.mock import patch

from shared.brief_loader import load_brief
from shared.brief_schema import (
    AbbreviationCollision,
    BlacklistCategory,
    DomainLaneHint,
    ExampleCompound,
)
from shared.schemas import BlockReport, SearchString
from linkedin.strategy import (
    _annotate_string_metadata,
    _build_strategy_system,
    _build_strategy_user,
    _opening_priority,
    adapt_after_block,
    form_strategy,
)


HEAD_AI_V2_BRIEF_PATH = str(
    Path(__file__).parent.parent / "config" / "brief-head-ai-lab-nyc-v2.json"
)
FDE_BRIEF_PATH = str(
    Path(__file__).parent.parent / "config" / "Forward-Deployed-Engineer-NYC" / "brief-forward-deployed-engineer-us-v1.4.json"
)


# Reference calibration vocabulary used to keep the historical strategy tests
# meaningful now that `_opening_priority` reads its patterns from the compat
# brief instead of module-level constants. These mirror what the legacy
# constants used to be so behavioral expectations carry over; new tests below
# vary them explicitly to assert that the classification is brief-driven.
_LEGACY_CANONICAL_FRAMEWORK_PATTERNS = (
    "langgraph", "pydanticai", "dspy", "crewai", "autogen", "semantic kernel",
    "model context protocol", "mcp", "browser-use", "browser use", "playwright",
    "litellm", "langsmith", "ragas", "deepeval",
)
_LEGACY_CANONICAL_COMPANY_PATTERNS = (
    "palantir", "scale ai", "snorkel", "anthropic", "openai", "cohere",
    "cognition", "cursor", "anduril", "dataiku", "datarobot", "c3 ai", "c3.ai",
)
_LEGACY_CANONICAL_TITLE_PATTERNS = (
    "forward deployed", "forward-deployed", "fde", "fdse",
    "customer engineer", "customer engineering",
    "solutions engineer", "solutions engineering", "implementation engineer",
    "implementation engineering", "delivery engineer", "delivery engineering",
    "field engineer", "field engineering",
)
_LEGACY_CANONICAL_BROAD_PATTERNS = (
    "agentic workflow", "agentic workflows", "agentic system", "agentic systems",
    "agent orchestration", "tool calling", "function calling",
)
_LEGACY_EDGE_CASE_PATTERNS = (
    "copilot", "co-pilot", "internal copilot", "analyst assistant", "treasury assistant",
    "research workflow", "research copilot", "investment memo", "investment research",
    "advisor copilot", "wealth platform", "portfolio analytics", "portfolio construction",
    "buy side", "buy-side", "sell side", "sell-side", "hedge fund workflow",
    "client reporting", "trade surveillance", "market surveillance",
    "collateral workflow", "collateral management", "post trade", "post-trade",
    "onboarding automation", "regulatory reporting", "regulatory filing",
    "filing automation", "transaction monitoring", "adverse media", "case management",
    "claims intake", "claims workflow", "underwriting workbench", "underwriting assistant",
    "policy review", "model risk", "model governance", "regulatory response",
    "payment orchestration", "transaction banking", "real-time payments", "fednow",
    "swift", "cash management", "treasury management", "issuer processing",
    "merchant risk", "market data workflow", "custody workflow", "portfolio operations",
    "knowledge management", "knowledge assistant", "intelligent search", "semantic search",
    "document processing", "document understanding", "document intelligence",
    "document extraction", "isda", "10-k", "prospectus", "term sheet", "covenant review",
    "contract analysis", "compliance workflow", "founder", "co-founder", "hands-on cto",
    "startup cto", "support automation", "developer productivity", "internal tools",
    "technical discovery", "solution design", "solutions delivery", "requirements gathering",
    "trusted advisor", "technical consulting", "reference architecture",
    "reference implementation", "deployment toolkit", "accelerator", "reusable module",
    "reusable modules", "delivery playbook", "workflow engine", "human in the loop",
    "human-in-the-loop", "semantic cache", "evaluation harness", "eval harness",
    "observability", "tracing", "prompt logging", "latency optimization",
    "cost optimization", "agent routing", "event-driven", "event driven", "temporal",
    "fastapi",
)
_LEGACY_EDGE_CASE_COMPANY_PATTERNS = (
    "exl", "deloitte", "accenture", "bcg", "bcg x", "mckinsey", "quantumblack",
    "slalom", "thoughtworks", "epam", "globant", "ci&t", "harvey", "casetext",
    "ironclad", "robin ai", "evenup", "notion", "glean", "moveworks", "writer",
    "hebbia", "vellum",
)
_LEGACY_EXAMPLE_COMPOUNDS = (
    ExampleCompound(
        boolean='("agentic" OR "LLM agent") AND ("financial services" OR "banking" OR "BFSI") AND ("production" OR "deployment" OR "enterprise")',
        purpose="Broad recall AND-gate combining agentic vocabulary, BFSI domain, and production proof",
        novelty_bucket="canonical",
    ),
    ExampleCompound(
        boolean='("Axolotl" OR "vLLM" OR "DeepSpeed")',
        purpose="Precision sniper anchored on builder-only framework names",
        novelty_bucket="canonical",
    ),
    ExampleCompound(
        boolean='("SWE-bench" OR "MMLU" OR "HumanEval")',
        purpose="Precision sniper anchored on builder-only benchmark names",
        novelty_bucket="canonical",
    ),
    ExampleCompound(
        boolean='("Constitutional AI" OR "GRPO")',
        purpose="Precision sniper anchored on method-specific terms",
        novelty_bucket="canonical",
    ),
    ExampleCompound(
        boolean='("TRL" OR "PEFT")',
        purpose="Precision sniper anchored on post-training infrastructure",
        novelty_bucket="canonical",
    ),
)
_LEGACY_TERM_BLACKLIST_CATEGORIES = (
    BlacklistCategory(
        label="Universal infrastructure",
        rationale="Generic infrastructure tools shared across all software roles",
        terms=[
            "PyTorch", "TensorFlow", "JAX", "Keras", "Docker", "Kubernetes",
            "AWS", "GCP", "Azure", "Spark", "Airflow", "Kafka", "Redis",
            "PostgreSQL", "MongoDB", "Git", "GitHub", "pandas", "NumPy",
            "SciPy", "scikit-learn",
        ],
    ),
    BlacklistCategory(
        label="Universal ML",
        rationale="ML vocabulary so common it is non-discriminating on LinkedIn",
        terms=[
            "machine learning", "deep learning", "neural network",
            "gradient descent", "backpropagation", "cross-validation",
            "hyperparameter", "training (alone)", "inference (alone)",
            "model (alone)", "transformer (alone)", "encoder", "decoder",
        ],
    ),
    BlacklistCategory(
        label="Generic software",
        rationale="Generic software-engineering vocabulary present on most engineer profiles",
        terms=[
            "CI/CD", "GitHub Actions", "Jenkins", "unit testing", "code review",
            "API integration", "microservices", "REST", "GraphQL",
        ],
    ),
    BlacklistCategory(
        label="User tools (not builder tools)",
        rationale="Names of consumer/user-facing AI products are not builder evidence",
        terms=[
            "GitHub Copilot", "Cursor", "ChatGPT", "Claude (product)", "Gemini",
            "LangChain", "LlamaIndex", "AutoGPT", "BabyAGI",
        ],
    ),
    BlacklistCategory(
        label="Buzzwords",
        rationale="Marketing buzzwords are non-discriminating on LinkedIn",
        terms=[
            "AI-powered", "intelligent automation", "cutting-edge",
            "generative AI (alone)", "autonomous (alone)", "automation (alone)",
            "data-driven", "next-generation",
        ],
    ),
)
_LEGACY_ABBREVIATION_COLLISIONS = (
    AbbreviationCollision(
        abbreviation="IPO",
        expansion="identity preference optimization",
        standalone_allowed=False,
        note="IPO collides with Initial Public Offering",
    ),
    AbbreviationCollision(
        abbreviation="ORM",
        expansion="outcome reward model",
        standalone_allowed=False,
        note="ORM collides with Object-Relational Mapping",
    ),
    AbbreviationCollision(
        abbreviation="CAI",
        expansion="constitutional AI",
        standalone_allowed=False,
        note="CAI has various non-ML meanings",
    ),
    AbbreviationCollision(
        abbreviation="PPO",
        expansion="proximal policy optimization",
        standalone_allowed=False,
        note="PPO collides with Preferred Provider Organization",
    ),
    AbbreviationCollision(
        abbreviation="RLHF",
        expansion="reinforcement learning from human feedback",
        standalone_allowed=True,
        note="No dominant non-ML meaning",
    ),
    AbbreviationCollision(
        abbreviation="DPO",
        expansion="direct preference optimization",
        standalone_allowed=False,
        note="DPO collides with Data Protection Officer in some markets",
    ),
)
_LEGACY_SEQUENCING_HEURISTICS = (
    "BACKLOAD RL/RLHF STRINGS — place strings anchored primarily to "
    "RL/RLHF/post-training vocabulary in the SECOND HALF of the execution "
    "sequence. Front-load strings targeting other capability areas first "
    "(agentic systems, data quality/evaluation, coding agents, STEM/multimodal, "
    "embodied AI, general fine-tuning). RL/RLHF strings surface the densest, "
    "most well-trodden talent pool — they will still run, but later. Thinner "
    "capability-area pools surface more net-new candidates per string. By the "
    "time RL strings execute, the adaptation loop will have learned from "
    "earlier strings' signal/noise patterns."
)
_LEGACY_DOMAIN_LANE_HINTS = (
    DomainLaneHint(lane="capital_markets", patterns=[
        "capital markets", "post trade", "post-trade", "collateral", "treasury",
        "market structure", "market data", "trade surveillance", "trading",
        "sell side", "buy side",
    ]),
    DomainLaneHint(lane="risk_compliance", patterns=[
        "risk", "compliance", "surveillance", "aml", "kyc", "sanctions",
        "regulatory", "model governance", "model risk", "fraud",
    ]),
    DomainLaneHint(lane="asset_management", patterns=[
        "asset management", "wealth", "portfolio", "investment memo",
        "investment research", "research copilot", "research workflow",
        "client reporting", "advisor",
    ]),
    DomainLaneHint(lane="insurance", patterns=[
        "insurance", "actuarial", "underwriting", "claims", "policy",
        "broker", "carrier",
    ]),
    DomainLaneHint(lane="payments", patterns=[
        "payment", "payments", "payment orchestration", "transaction banking",
        "real-time payments", "rtp", "fednow", "swift", "cash management",
        "merchant risk", "issuer processing",
    ]),
    DomainLaneHint(lane="document_intelligence", patterns=[
        "document intelligence", "document understanding", "document extraction",
        "document processing", "isda", "10-k", "prospectus", "term sheet",
        "covenant review", "filing automation",
    ]),
    DomainLaneHint(lane="bfsi_vendors", patterns=[
        "fintech", "regtech", "custody", "workflow vendor", "market data",
        "vendor", "platform",
    ]),
)


def _hydrate_legacy_calibration(brief):
    """Populate the compat brief's calibration mirror with the historical AI/BFSI
    vocabulary so existing strategy tests still exercise the bucket/score paths
    they were designed for. Production code never mutates these lists; only
    test fixtures do.

    Slice 2 Commit 2 extends this to also inject the legacy AI vocabulary for
    the planner-prompt fields (example_compounds, term_blacklist_categories,
    abbreviation_collisions, sequencing_heuristics). These mirror the strings
    that were hardcoded in `_build_strategy_system` before the planner-prompt
    refactor, so existing AI-brief strategy tests keep their behavioral pins.
    """
    brief.canonical_framework_patterns = list(_LEGACY_CANONICAL_FRAMEWORK_PATTERNS)
    brief.canonical_company_patterns = list(_LEGACY_CANONICAL_COMPANY_PATTERNS)
    brief.canonical_title_patterns = list(_LEGACY_CANONICAL_TITLE_PATTERNS)
    brief.canonical_broad_patterns = list(_LEGACY_CANONICAL_BROAD_PATTERNS)
    brief.edge_case_patterns = list(_LEGACY_EDGE_CASE_PATTERNS)
    brief.edge_case_company_patterns = list(_LEGACY_EDGE_CASE_COMPANY_PATTERNS)
    brief.domain_lane_hints = list(_LEGACY_DOMAIN_LANE_HINTS)
    brief.example_compounds = list(_LEGACY_EXAMPLE_COMPOUNDS)
    brief.term_blacklist_categories = list(_LEGACY_TERM_BLACKLIST_CATEGORIES)
    brief.abbreviation_collisions = list(_LEGACY_ABBREVIATION_COLLISIONS)
    brief.sequencing_heuristics = _LEGACY_SEQUENCING_HEURISTICS
    return brief


def test_build_strategy_user_includes_search_family_memory():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    prompt = _build_strategy_user(
        brief,
        [],
        prior_run_data={
            "search_memory_summary": {
                "overall": {
                    "families_tracked": 2,
                    "save_rate": 0.04,
                    "duplicate_rate": 0.47,
                    "novelty_mix": {
                        "edge_case_saves": 3,
                        "canonical_saves": 8,
                    },
                },
                "families": [
                    {
                        "family_key": "canonical_bank_company_first",
                        "novelty_bucket": "canonical",
                        "domain_lane": "capital_markets",
                        "status": "exhausted",
                        "status_reason": "Repeated family with high duplicate overlap.",
                        "save_rate": 0.01,
                        "duplicate_rate": 0.58,
                        "dominant_anchors": ["goldman", "jpmorgan", "capital markets"],
                    }
                ],
            }
        },
    )

    assert "Search Family Memory" in prompt
    assert "canonical_bank_company_first" in prompt
    assert "Repeated family with high duplicate overlap." in prompt
    assert "goldman, jpmorgan, capital markets" in prompt


def test_build_strategy_user_includes_market_intel_lanes_and_cleanup_rule():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    prompt = _build_strategy_user(brief, [], prior_run_data={})

    assert "regulatory reporting" in prompt.lower()
    assert "market infrastructure" in prompt.lower()
    assert "capital markets and institutional finance remain the strongest domain prior" in prompt.lower()
    assert "high-quality lead worth a conversation" in prompt.lower()


def test_build_strategy_user_legacy_brief_omits_layered_retrieval_design_section():
    brief = load_brief(FDE_BRIEF_PATH)
    prompt = _build_strategy_user(brief, [], prior_run_data={})
    system = _build_strategy_system(brief, has_kit=False, use_layered_retrieval=False)

    assert "## Layered Retrieval Design" not in prompt
    assert "Synthesize compound Boolean search strings" in prompt
    assert "Generate 15-30 search strings total." in system
    assert "Treat these priorities as semantic guidance" not in prompt
    assert "These terms are anchors and hints" not in prompt


def test_build_strategy_user_strict_seniority_legacy_brief_adds_semantic_guidance():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    prompt = _build_strategy_user(brief, [], prior_run_data={})

    assert "Treat these priorities as semantic guidance" in prompt
    assert "These terms are anchors and hints" in prompt
    assert "prefer technical-authority concepts" in prompt
    assert "Do not turn these hints into broad OR groups of generic titles" in prompt


def test_form_strategy_reorders_head_ai_opening_toward_edge_case():
    brief = _hydrate_legacy_calibration(load_brief(HEAD_AI_V2_BRIEF_PATH))
    mock_plan = {
        "architecture": "dragnet",
        "architecture_rationale": "mock",
        "architecture_success_criteria": [],
        "architecture_pivot_triggers": [],
        "strategy_rationale": "mock",
        "generated_strings": [
            {
                "boolean": "(\"Goldman Sachs\" OR \"JPMorgan\") AND (\"GenAI\" OR \"LLM\")",
                "rationale": "Canonical bank company-first cleanup string",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"banking\" OR \"financial services\" OR \"BFSI\") AND (\"GenAI\" OR \"RAG\")",
                "rationale": "Broad generic BFSI cleanup string",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"trade surveillance workflow\" OR \"market surveillance workflow\") AND (\"agentic\" OR \"retrieval pipeline\")",
                "rationale": "Trade surveillance edge-case population",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"collateral workflow\" OR \"post-trade workflow\") AND (\"document intelligence\" OR \"orchestration\")",
                "rationale": "Collateral and post-trade edge-case population",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"research copilot\" OR \"investment memo automation\") AND (\"production\" OR \"deployed\")",
                "rationale": "Asset management and research workflow builders",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"underwriting workbench\" OR \"claims intake\") AND (\"production\" OR \"deployed\")",
                "rationale": "Insurance workflow builders",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"model risk review\" OR \"regulatory response\") AND (\"applied AI\" OR \"evaluation framework\")",
                "rationale": "Risk and compliance workflow builders",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"custody workflow\" OR \"market data workflow\") AND (\"agentic\" OR \"document intelligence\")",
                "rationale": "BFSI vendor workflow builders",
                "vocabulary_sources": "mock",
            },
        ],
        "coverage_gaps": [],
        "noise_predictions": [],
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_plan):
        plan = form_strategy(brief, [], prior_run_data={})

    assert len(plan.generated_strings) == 8
    first_eight = plan.generated_strings[:8]
    edge_case_count = sum(
        1 for item in first_eight if item.get("novelty_bucket") == "edge_case"
    )
    assert edge_case_count >= 5
    assert first_eight[0]["domain_lane"] != "general"


def test_form_strategy_promotes_market_intel_gap_lanes_ahead_of_cleanup():
    brief = _hydrate_legacy_calibration(load_brief(HEAD_AI_V2_BRIEF_PATH))
    mock_plan = {
        "architecture": "dragnet",
        "architecture_rationale": "mock",
        "architecture_success_criteria": [],
        "architecture_pivot_triggers": [],
        "strategy_rationale": "mock",
        "generated_strings": [
            {
                "boolean": "(\"Head of Applied AI\" OR \"Executive Director AI\") AND (\"banking\" OR \"financial services\") AND (\"GenAI\" OR \"LLM\")",
                "rationale": "Archetype-first executive-builder cleanup string",
                "vocabulary_sources": "mock",
                "family_key": "executive_builder_cleanup",
            },
            {
                "boolean": "(\"regulatory reporting\" OR \"regulatory filing\" OR \"transaction monitoring\") AND (\"LLM\" OR \"agentic\" OR \"RAG\")",
                "rationale": "Regulatory reporting and compliance GenAI builders",
                "vocabulary_sources": "mock",
                "family_key": "reg_reporting_genai",
            },
            {
                "boolean": "(\"payment orchestration\" OR \"transaction banking\" OR \"FedNow\") AND (\"LLM\" OR \"agentic\" OR \"document intelligence\")",
                "rationale": "Payments and transaction-banking builders",
                "vocabulary_sources": "mock",
                "family_key": "payments_builder",
            },
            {
                "boolean": "(\"founder\" OR \"co-founder\" OR \"CTO\") AND (\"fintech\" OR \"insurtech\" OR \"regtech\") AND (\"GenAI\" OR \"agentic\")",
                "rationale": "Founder and CTO edge-case population",
                "vocabulary_sources": "mock",
                "family_key": "founder_cto_bfsi",
            },
        ],
        "coverage_gaps": [],
        "noise_predictions": [],
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_plan):
        plan = form_strategy(brief, [], prior_run_data={})

    family_order = [item.get("family_key") for item in plan.generated_strings]
    cleanup_index = family_order.index("executive_builder_cleanup")
    assert family_order.index("reg_reporting_genai") < cleanup_index
    assert plan.generated_strings[0]["family_key"] == "reg_reporting_genai"
    assert all(
        item.get("title_bucket_risk") != "high"
        for item in plan.generated_strings[:3]
    )


def test_form_strategy_demotes_exhausted_families_from_search_memory():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    mock_plan = {
        "architecture": "dragnet",
        "architecture_rationale": "mock",
        "architecture_success_criteria": [],
        "architecture_pivot_triggers": [],
        "strategy_rationale": "mock",
        "generated_strings": [
            {
                "boolean": "(\"Goldman Sachs\" OR \"JPMorgan\") AND (\"GenAI\" OR \"LLM\")",
                "rationale": "Canonical bank company-first cleanup string",
                "vocabulary_sources": "mock",
                "family_key": "canonical_bank_company_first",
                "novelty_bucket": "canonical",
                "domain_lane": "capital_markets",
            },
            {
                "boolean": "(\"trade surveillance workflow\" OR \"market surveillance workflow\") AND (\"agentic\" OR \"retrieval pipeline\")",
                "rationale": "Trade surveillance edge-case population",
                "vocabulary_sources": "mock",
                "family_key": "trade_surveillance_workflow",
                "novelty_bucket": "edge_case",
                "domain_lane": "risk_compliance",
            },
            {
                "boolean": "(\"research copilot\" OR \"investment memo automation\") AND (\"production\" OR \"deployed\")",
                "rationale": "Research copilot edge-case population",
                "vocabulary_sources": "mock",
                "family_key": "research_copilot_asset_mgmt",
                "novelty_bucket": "edge_case",
                "domain_lane": "asset_management",
            }
        ],
        "coverage_gaps": [],
        "noise_predictions": [],
    }

    prior_run_data = {
        "search_memory_summary": {
            "overall": {
                "families_tracked": 2,
                "save_rate": 0.02,
                "duplicate_rate": 0.51,
                "novelty_mix": {"edge_case_saves": 2, "canonical_saves": 10},
            },
            "families": [
                {
                    "family_key": "canonical_bank_company_first",
                    "novelty_bucket": "canonical",
                    "domain_lane": "capital_markets",
                    "status": "exhausted",
                    "status_reason": "Repeated family with high duplicate overlap.",
                    "save_rate": 0.01,
                    "duplicate_rate": 0.58,
                    "dominant_anchors": ["goldman", "jpmorgan"],
                }
            ],
        }
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_plan):
        plan = form_strategy(brief, [], prior_run_data=prior_run_data)

    assert plan.generated_strings[-1]["family_key"] == "canonical_bank_company_first"


def test_form_strategy_strict_seniority_lint_suppresses_broad_title_buckets():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    mock_plan = {
        "architecture": "dragnet",
        "architecture_rationale": "mock",
        "architecture_success_criteria": [],
        "architecture_pivot_triggers": [],
        "strategy_rationale": "mock",
        "generated_strings": [
            {
                "boolean": "(\"Head of\" OR \"Director\" OR \"VP\" OR \"CTO\" OR \"Principal\") AND (\"financial services\" OR \"banking\") AND (\"GenAI\" OR \"LLM\")",
                "rationale": "Too-broad title-bucket opener.",
                "vocabulary_sources": "mock",
                "family_key": "broad_titles",
                "novelty_bucket": "canonical",
                "domain_lane": "general",
            },
            {
                "boolean": "(\"Executive Director\" OR \"Head of AI Platforms\") AND (\"capital markets\" OR \"market data\") AND (\"production\" OR \"deployed\")",
                "rationale": "Safer ED-scoped opener.",
                "vocabulary_sources": "mock",
                "family_key": "ed_scope",
                "novelty_bucket": "canonical",
                "domain_lane": "capital_markets",
            },
            {
                "boolean": "(\"BlackRock\" OR \"Two Sigma\") AND (\"GenAI\" OR \"LLM\")",
                "rationale": "Buy-side lane without builder proof should not open.",
                "vocabulary_sources": "mock",
                "family_key": "buy_side_generic",
                "novelty_bucket": "edge_case",
                "domain_lane": "asset_management",
            },
            {
                "boolean": "(\"research workflow\" OR \"investment workflow\") AND (\"production\" OR \"deployed\")",
                "rationale": "Workflow-first capital markets lane.",
                "vocabulary_sources": "mock",
                "family_key": "workflow_cap_markets",
                "novelty_bucket": "edge_case",
                "domain_lane": "capital_markets",
            },
        ],
        "coverage_gaps": [],
        "noise_predictions": [],
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_plan):
        plan = form_strategy(brief, [], prior_run_data={})

    booleans = [item["boolean"] for item in plan.generated_strings]
    assert not any('("Head of" OR "Director" OR "VP" OR "CTO" OR "Principal")' in boolean for boolean in booleans)
    assert plan.generated_strings[0]["family_key"] in {"ed_scope", "workflow_cap_markets"}
    buy_side = next(item for item in plan.generated_strings if item["family_key"] == "buy_side_generic")
    assert buy_side["opening_eligible"] is False


def test_form_strategy_accepts_raw_search_memory_artifact():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    mock_plan = {
        "architecture": "dragnet",
        "architecture_rationale": "mock",
        "architecture_success_criteria": [],
        "architecture_pivot_triggers": [],
        "strategy_rationale": "mock",
        "generated_strings": [
            {
                "boolean": "(\"Goldman Sachs\" OR \"JPMorgan\") AND (\"GenAI\" OR \"LLM\")",
                "rationale": "Canonical bank company-first cleanup string",
                "vocabulary_sources": "mock",
                "family_key": "canonical_bank_company_first",
                "novelty_bucket": "canonical",
                "domain_lane": "capital_markets",
            },
            {
                "boolean": "(\"trade surveillance workflow\" OR \"market surveillance workflow\") AND (\"agentic\" OR \"retrieval pipeline\")",
                "rationale": "Trade surveillance edge-case population",
                "vocabulary_sources": "mock",
                "family_key": "trade_surveillance_workflow",
                "novelty_bucket": "edge_case",
                "domain_lane": "risk_compliance",
            },
        ],
        "coverage_gaps": [],
        "noise_predictions": [],
    }

    prior_run_data = {
        "search_memory_summary": {
            "project_id": "1957683706",
            "overall": {
                "strings_seen": 1,
                "candidates_seen": 7,
                "duplicates": 4,
                "saves": 1,
                "edge_case_saves": 1,
                "canonical_saves": 0,
            },
            "families": {
                "canonical_bank_company_first": {
                    "family_key": "canonical_bank_company_first",
                    "novelty_bucket": "canonical",
                    "domain_lane": "capital_markets",
                    "status": "exhausted",
                    "status_reason": "Repeated family with high duplicate overlap.",
                    "dominant_anchors": ["goldman", "jpmorgan"],
                }
            },
        }
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_plan):
        plan = form_strategy(brief, [], prior_run_data=prior_run_data)

    assert plan.generated_strings[-1]["family_key"] == "canonical_bank_company_first"


def test_adapt_after_block_accepts_raw_search_memory_artifact():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    report = BlockReport(
        block_name="Compound Batch 1",
        strings_run=1,
        strings_with_saves=1,
        total_results=99,
        total_saves=1,
        string_details=[
            {
                "string_id": 5,
                "name": "Insurance string",
                "boolean": "(\"underwriting automation\")",
                "original_boolean": "(\"underwriting\")",
                "result_count": 99,
                "pages_reviewed": 1,
                "candidates": 7,
                "duplicates": 0,
                "saves": 1,
                "save_names": ["Devasis Bassu"],
                "saved_profiles": [],
                "facial_yes": 2,
                "facial_no": 7,
                "family_key": "insurance_ai_builder",
                "novelty_bucket": "edge_case",
                "domain_lane": "insurance",
                "notes": "Abandoned after page 1.",
            }
        ],
    )
    remaining = [
        SearchString(
            id=6,
            name="Vendor cleanup string",
            boolean="(\"Broadridge\" OR \"FIS\") AND (\"GenAI\")",
            block="Compound Batch 2",
            family_key="canonical_bank_company_first",
            novelty_bucket="canonical",
            domain_lane="capital_markets",
        )
    ]
    raw_memory = {
        "project_id": "1957683706",
        "overall": {
            "strings_seen": 1,
            "candidates_seen": 7,
            "duplicates": 4,
            "saves": 1,
            "edge_case_saves": 1,
            "canonical_saves": 0,
        },
        "families": {
            "canonical_bank_company_first": {
                "family_key": "canonical_bank_company_first",
                "novelty_bucket": "canonical",
                "domain_lane": "capital_markets",
                "status": "exhausted",
                "status_reason": "Repeated family with high duplicate overlap.",
                "dominant_anchors": ["goldman", "jpmorgan"],
            }
        },
    }
    mock_adaptation = {
        "new_strings": [],
        "skip_remaining": [],
        "reorder": [
            {
                "string_id": 6,
                "move_to": "next",
                "reason": "Move this closer to the top.",
            }
        ],
        "noise_updates": [],
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_adaptation):
        adaptation = adapt_after_block(
            brief,
            report,
            remaining,
            search_memory_summary=raw_memory,
        )

    assert adaptation.reorder[0]["move_to"] == "last"


def test_form_strategy_materializes_retrieval_families_into_rendered_strings():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    mock_plan = {
        "architecture": "dragnet",
        "architecture_rationale": "mock",
        "architecture_success_criteria": [],
        "architecture_pivot_triggers": [],
        "strategy_rationale": "mock",
        "retrieval_families": [
            {
                "family_id": "fde_delivery_builders",
                "label": "FDE delivery builders",
                "objective": "Open with broad delivery cohorts, then constrain to real builders.",
                "priority": 90,
                "enabled": True,
                "variants_to_emit": 2,
                "entry_signals": [
                    {
                        "item_id": "entry_delivery",
                        "label": "Delivery engineers",
                        "terms": ["deployment engineer", "implementation engineer"],
                    }
                ],
                "capability_proxies": [
                    {
                        "item_id": "cap_orchestration",
                        "label": "Orchestration work",
                        "terms": ["workflow orchestration", "tool calling"],
                    }
                ],
                "reality_filters": [
                    {
                        "item_id": "real_production",
                        "label": "Production proof",
                        "terms": ["production", "deployed"],
                    }
                ],
                "context_constraints": [
                    {
                        "item_id": "ctx_customer",
                        "label": "Customer environment",
                        "terms": ["enterprise", "customer"],
                    }
                ],
                "anti_noise": [
                    {
                        "item_id": "anti_sales",
                        "label": "Sales-only noise",
                        "terms": ["sales engineer", "account executive"],
                    }
                ],
                "hypothesis_ids": ["post_sale_builders"],
            }
        ],
        "generated_strings": [],
        "coverage_gaps": [],
        "noise_predictions": [],
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_plan):
        plan = form_strategy(brief, [], prior_run_data={})

    assert plan.retrieval_families
    assert plan.generated_strings
    rendered = plan.generated_strings[0]
    assert "deployment engineer" in rendered["boolean"]
    assert "workflow orchestration" in rendered["boolean"]
    assert "production" in rendered["boolean"]
    assert rendered["retrieval_recipe"]["family_id"] == "fde_delivery_builders"
    assert rendered["retrieval_hypothesis_ids"] == ["post_sale_builders"]


def test_form_strategy_legacy_brief_keeps_generated_strings_primary_over_retrieval_families():
    brief = load_brief(FDE_BRIEF_PATH)
    mock_plan = {
        "architecture": "dragnet",
        "architecture_rationale": "mock",
        "architecture_success_criteria": [],
        "architecture_pivot_triggers": [],
        "strategy_rationale": "mock",
        "retrieval_families": [
            {
                "family_id": "delivery_builders",
                "label": "Delivery builders",
                "objective": "Structured compatibility family.",
                "priority": 90,
                "enabled": True,
                "variants_to_emit": 1,
                "entry_signals": [
                    {"item_id": "entry_delivery", "label": "Delivery", "terms": ["deployment engineer"]}
                ],
                "capability_proxies": [
                    {"item_id": "cap_prod", "label": "Prod", "terms": ["workflow orchestration"]}
                ],
                "reality_filters": [
                    {"item_id": "real_prod", "label": "Reality", "terms": ["production"]}
                ],
                "context_constraints": [],
                "anti_noise": [],
            }
        ],
        "generated_strings": [
            {
                "boolean": "(\"copilot\" OR \"assistant\") AND (\"workflow orchestration\" OR \"tool calling\") AND (\"production\" OR \"deployed\")",
                "rationale": "Legacy primary string.",
                "vocabulary_sources": "mock",
                "family_key": "legacy_primary",
                "novelty_bucket": "edge_case",
                "domain_lane": "general",
            }
        ],
        "coverage_gaps": [],
        "noise_predictions": [],
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_plan):
        plan = form_strategy(brief, [], prior_run_data={})

    assert plan.generated_strings[0]["family_key"] == "legacy_primary"
    assert "copilot" in plan.generated_strings[0]["boolean"]


def test_form_strategy_legacy_brief_can_fallback_to_retrieval_families_when_strings_missing():
    brief = load_brief(FDE_BRIEF_PATH)
    mock_plan = {
        "architecture": "dragnet",
        "architecture_rationale": "mock",
        "architecture_success_criteria": [],
        "architecture_pivot_triggers": [],
        "strategy_rationale": "mock",
        "retrieval_families": [
            {
                "family_id": "delivery_builders",
                "label": "Delivery builders",
                "objective": "Structured fallback family.",
                "priority": 90,
                "enabled": True,
                "variants_to_emit": 1,
                "entry_signals": [
                    {"item_id": "entry_delivery", "label": "Delivery", "terms": ["deployment engineer"]}
                ],
                "capability_proxies": [
                    {"item_id": "cap_prod", "label": "Prod", "terms": ["workflow orchestration"]}
                ],
                "reality_filters": [
                    {"item_id": "real_prod", "label": "Reality", "terms": ["production"]}
                ],
                "context_constraints": [],
                "anti_noise": [],
            }
        ],
        "generated_strings": [],
        "coverage_gaps": [],
        "noise_predictions": [],
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_plan):
        plan = form_strategy(brief, [], prior_run_data={})

    assert plan.generated_strings
    assert "deployment engineer" in plan.generated_strings[0]["boolean"]


# ---------------------------------------------------------------------------
# Brief-driven _opening_priority / _annotate_string_metadata coverage (Slice 2 Commit 1)
# ---------------------------------------------------------------------------


def test_opening_priority_returns_neutral_when_brief_has_no_calibration_patterns():
    """With an empty calibration mirror, no string should classify as canonical or
    edge-case — every input collapses to bucket=1 (neutral / mixed)."""
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)

    bucket_canonical_ai, _score = _opening_priority(
        brief,
        '("LangGraph" OR "DSPy") AND ("OpenAI" OR "Anthropic")',
        "Frontier framework + frontier company canonical opener.",
    )
    bucket_edge, _score = _opening_priority(
        brief,
        '("trade surveillance workflow") AND ("agentic")',
        "Edge-case capital markets workflow population.",
    )
    assert bucket_canonical_ai == 1
    assert bucket_edge == 1


def test_opening_priority_classifies_canonical_ai_when_brief_supplies_ai_calibration():
    """An AI-calibrated brief should mark frontier AI strings as canonical."""
    brief = _hydrate_legacy_calibration(load_brief(HEAD_AI_V2_BRIEF_PATH))

    bucket, score = _opening_priority(
        brief,
        '("LangGraph" OR "DSPy") AND ("OpenAI" OR "Anthropic" OR "Cohere")',
        "Frontier framework + frontier company canonical opener.",
    )
    assert bucket == 2
    assert score < 0


def test_opening_priority_is_brief_driven_for_alternative_vertical():
    """Construct an alternative vertical (clinical/healthtech). The same
    'LangGraph' string is no longer canonical because the brief does not list it
    as such; instead, a clinical edge-case string flips to bucket 0."""
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    brief.canonical_framework_patterns = []
    brief.canonical_company_patterns = ["epic", "cerner", "athenahealth"]
    brief.canonical_title_patterns = ["clinical informatics director"]
    brief.canonical_broad_patterns = []
    brief.edge_case_patterns = [
        "telehealth triage",
        "remote patient monitoring",
        "clinical decision support",
    ]
    brief.edge_case_company_patterns = ["abridge", "nabla", "suki"]

    canonical_bucket, _ = _opening_priority(
        brief,
        '("Epic" OR "Cerner") AND ("clinical informatics director")',
        "Frontier EHR vendor + canonical clinical title.",
    )
    edge_bucket, edge_score = _opening_priority(
        brief,
        '("telehealth triage" OR "remote patient monitoring") AND ("clinical decision support")',
        "Edge-case clinical AI population.",
    )
    ai_bucket, _ = _opening_priority(
        brief,
        '("LangGraph" OR "DSPy") AND ("OpenAI")',
        "Frontier AI vocabulary that is canonical for the AI brief, but irrelevant here.",
    )
    assert canonical_bucket == 2
    assert edge_bucket == 0
    assert edge_score > 0
    assert ai_bucket == 1


def test_annotate_string_metadata_reflects_brief_domain_lane_hints_and_canonical_patterns():
    """`_annotate_string_metadata` should thread the brief through into both
    novelty_bucket and domain_lane via brief-driven classification."""
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    brief.canonical_framework_patterns = []
    brief.canonical_company_patterns = []
    brief.canonical_title_patterns = []
    brief.canonical_broad_patterns = []
    brief.edge_case_patterns = ["telehealth triage", "remote patient monitoring"]
    brief.edge_case_company_patterns = []
    brief.domain_lane_hints = [
        DomainLaneHint(
            lane="clinical_workflows",
            patterns=["telehealth triage", "remote patient monitoring", "clinical decision support"],
        ),
    ]

    annotated = _annotate_string_metadata(
        brief,
        {
            "boolean": '("telehealth triage" OR "remote patient monitoring") AND ("clinical decision support")',
            "rationale": "Edge-case clinical AI population.",
        },
    )

    assert annotated["novelty_bucket"] == "edge_case"
    assert annotated["domain_lane"] == "clinical_workflows"


def test_annotate_string_metadata_uses_general_lane_when_brief_has_no_lane_hints():
    """When the brief carries no domain_lane_hints, the lane defaults to 'general'."""
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    brief.domain_lane_hints = []

    annotated = _annotate_string_metadata(
        brief,
        {
            "boolean": '("Goldman Sachs") AND ("financial services")',
            "rationale": "Vertical-agnostic baseline test.",
        },
    )

    assert annotated["domain_lane"] == "general"


def test_opening_priority_does_not_classify_fde_as_canonical_when_brief_is_empty():
    """An empty-calibration brief must NOT classify a string containing
    'FDE' / 'forward deployed engineer' as canonical. Classification is fully
    brief-driven; with no patterns, every input collapses to neutral (bucket 1,
    score 0)."""
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    brief.canonical_framework_patterns = []
    brief.canonical_company_patterns = []
    brief.canonical_title_patterns = []
    brief.canonical_broad_patterns = []
    brief.edge_case_patterns = []
    brief.edge_case_company_patterns = []

    bucket_fde, score_fde = _opening_priority(
        brief,
        '("FDE" OR "forward deployed engineer")',
        "Forward-deployed canonical title — should NOT classify on an empty brief.",
    )
    bucket_phrase, score_phrase = _opening_priority(
        brief,
        '("forward deployed") AND ("delivery engineer")',
        "Forward-deployed phrase — should NOT classify on an empty brief.",
    )

    assert (bucket_fde, score_fde) == (1, 0)
    assert (bucket_phrase, score_phrase) == (1, 0)


def test_opening_priority_does_not_classify_fde_as_canonical_for_non_ai_vertical():
    """A non-AI vertical brief (clinical/healthtech) that does NOT mention FDE in
    any canonical pattern set must NOT classify a string containing 'FDE' or
    'forward deployed engineer' as canonical."""
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    brief.canonical_framework_patterns = []
    brief.canonical_company_patterns = ["epic", "cerner", "athenahealth"]
    brief.canonical_title_patterns = ["clinical informatics director"]
    brief.canonical_broad_patterns = []
    brief.edge_case_patterns = ["telehealth triage", "remote patient monitoring"]
    brief.edge_case_company_patterns = ["abridge", "nabla", "suki"]

    bucket_fde, _score_fde = _opening_priority(
        brief,
        '("FDE" OR "forward deployed engineer")',
        "FDE has no clinical meaning — must not classify here.",
    )
    bucket_clinical, _score_clinical = _opening_priority(
        brief,
        '("Epic" OR "Cerner") AND ("clinical informatics director")',
        "Clinical canonical opener anchored in this brief's calibration.",
    )

    assert bucket_fde == 1
    assert bucket_clinical == 2


def test_opening_priority_classifies_fde_as_canonical_when_brief_lists_it():
    """Pin: brief-driven path. A brief whose canonical_title_patterns explicitly
    names 'forward deployed' / 'fde' DOES classify those strings as canonical."""
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    brief.canonical_framework_patterns = []
    brief.canonical_company_patterns = []
    brief.canonical_title_patterns = ["forward deployed", "fde"]
    brief.canonical_broad_patterns = []
    brief.edge_case_patterns = []
    brief.edge_case_company_patterns = []

    bucket_phrase, score_phrase = _opening_priority(
        brief,
        '("forward deployed engineer")',
        "Forward-deployed canonical title via brief calibration.",
    )
    bucket_acronym, score_acronym = _opening_priority(
        brief,
        '("FDE" OR "FDSE")',
        "FDE acronym via brief calibration.",
    )

    assert bucket_phrase == 2
    assert score_phrase < 0
    assert bucket_acronym == 2
    assert score_acronym < 0

