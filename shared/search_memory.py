"""Helpers for brief-scoped search family memory and lightweight metadata inference."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re


_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_WHITESPACE = re.compile(r"\s+")

_STOPWORDS = {
    "and",
    "or",
    "not",
    "the",
    "a",
    "an",
    "of",
    "to",
    "for",
    "with",
    "in",
    "on",
    "at",
    "by",
    "from",
    "into",
    "workflow",
    "workflows",
    "system",
    "systems",
    "production",
    "enterprise",
    "built",
    "build",
    "deployed",
    "deploy",
    "shipped",
    "ship",
    "implemented",
    "implement",
    "engineering",
    "engineer",
    "genai",
    "generative",
    "ai",
    "llm",
    "rag",
    "banking",
    "financial",
    "services",
    "bfsi",
}

_ANCHOR_PHRASES = (
    "trade surveillance",
    "market surveillance",
    "collateral workflow",
    "collateral management",
    "model governance",
    "model risk",
    "regulatory response",
    "research copilot",
    "analyst assistant",
    "treasury assistant",
    "client reporting",
    "claims intake",
    "claims workflow",
    "underwriting workbench",
    "underwriting assistant",
    "portfolio operations",
    "investment memo",
    "onboarding automation",
    "document intelligence",
    "document understanding",
    "compliance workflow",
    "knowledge management",
    "intelligent search",
    "semantic search",
    "post trade",
    "post-trade",
    "capital markets",
    "market structure",
    "asset management",
    "wealth management",
    "policy review",
    "custody workflow",
    "risk workflow",
    "aml workflow",
    "kyc workflow",
    "sanctions screening",
)

_BIG_BANK_TERMS = (
    "goldman",
    "jpmorgan",
    "morgan stanley",
    "barclays",
    "citi",
    "citigroup",
    "bank of america",
    "bofa",
    "blackrock",
    "apollo",
    "vanguard",
    "tradeweb",
    "bloomberg",
)

_EDGE_CASE_TERMS = (
    "analyst assistant",
    "treasury assistant",
    "research copilot",
    "investment memo",
    "client reporting",
    "claims intake",
    "underwriting",
    "collateral",
    "surveillance",
    "onboarding",
    "regulatory",
    "policy review",
    "custody",
    "market data",
    "model governance",
    "model risk",
    "document intelligence",
    "document understanding",
    "compliance workflow",
    "knowledge management",
    "intelligent search",
    "semantic search",
)

_DOMAIN_LANE_HINTS: dict[str, tuple[str, ...]] = {
    "capital_markets": (
        "capital markets",
        "post trade",
        "post-trade",
        "collateral",
        "treasury",
        "market structure",
        "market data",
        "trade surveillance",
        "trading",
        "sell side",
        "buy side",
    ),
    "risk_compliance": (
        "risk",
        "compliance",
        "surveillance",
        "aml",
        "kyc",
        "sanctions",
        "regulatory",
        "model governance",
        "model risk",
        "fraud",
    ),
    "asset_management": (
        "asset management",
        "wealth",
        "portfolio",
        "investment memo",
        "research copilot",
        "research workflow",
        "client reporting",
        "advisor",
    ),
    "insurance": (
        "insurance",
        "actuarial",
        "underwriting",
        "claims",
        "policy",
        "broker",
        "carrier",
    ),
    "bfsi_vendors": (
        "fintech",
        "regtech",
        "custody",
        "workflow vendor",
        "market data",
        "vendor",
        "platform",
    ),
}


def _slugify(value: str) -> str:
    text = _NON_ALNUM.sub("_", (value or "").lower()).strip("_")
    return re.sub(r"_+", "_", text) or "unlabeled_family"


def normalize_family_key(
    family_key: str | None,
    boolean: str = "",
    rationale: str = "",
) -> str:
    """Return a stable-ish family identifier for a generated string."""
    if family_key:
        return _slugify(family_key)

    anchors = extract_dominant_anchors(boolean or rationale, limit=4)
    if anchors:
        return _slugify("_".join(anchors))
    return "unlabeled_family"


def normalize_novelty_bucket(
    novelty_bucket: str | None,
    boolean: str = "",
    rationale: str = "",
) -> str:
    """Normalize to edge_case/canonical, with a lightweight fallback heuristic."""
    if novelty_bucket:
        value = _slugify(novelty_bucket)
        if value in {"edge_case", "canonical"}:
            return value

    text = f"{boolean} {rationale}".lower()
    if any(term in text for term in _EDGE_CASE_TERMS):
        return "edge_case"
    if any(term in text for term in _BIG_BANK_TERMS):
        return "canonical"
    return "canonical"


def infer_domain_lane(
    domain_lane: str | None,
    boolean: str = "",
    rationale: str = "",
) -> str:
    """Infer the primary domain lane for a string."""
    if domain_lane:
        return _slugify(domain_lane)

    text = f"{boolean} {rationale}".lower()
    for lane, hints in _DOMAIN_LANE_HINTS.items():
        if any(hint in text for hint in hints):
            return lane
    return "general"


def extract_dominant_anchors(text: str, limit: int = 5) -> list[str]:
    """Extract a compact list of likely anchor phrases/terms from a Boolean string."""
    lowered = (text or "").lower()
    anchors: list[str] = []
    seen: set[str] = set()

    for phrase in _ANCHOR_PHRASES:
        if phrase in lowered and phrase not in seen:
            seen.add(phrase)
            anchors.append(phrase)
            if len(anchors) >= limit:
                return anchors

    tokens = [
        token for token in _WHITESPACE.split(_NON_ALNUM.sub(" ", lowered))
        if token and token not in _STOPWORDS and len(token) > 2
    ]
    counts = Counter(tokens)
    for token, _count in counts.most_common():
        if token in seen:
            continue
        anchors.append(token)
        seen.add(token)
        if len(anchors) >= limit:
            break
    return anchors


def build_search_memory_summary(memory: dict | None, limit: int = 8) -> dict:
    """Return a compact, LLM-facing summary of stored search family history."""
    memory = memory or {}
    overall = memory.get("overall", {})
    families = memory.get("families", {})

    summary_families = []
    for family in families.values():
        candidates = family.get("candidates_seen", 0)
        duplicates = family.get("duplicates", 0)
        saves = family.get("saves", 0)
        total_seen = candidates + duplicates
        summary_families.append(
            {
                "family_key": family.get("family_key", ""),
                "novelty_bucket": family.get("novelty_bucket", "canonical"),
                "domain_lane": family.get("domain_lane", "general"),
                "status": family.get("status", "active"),
                "status_reason": family.get("status_reason", ""),
                "save_rate": round(saves / max(candidates, 1), 4),
                "duplicate_rate": round(duplicates / max(total_seen, 1), 4),
                "saves": saves,
                "strings_seen": family.get("strings_seen", 0),
                "dominant_anchors": family.get("dominant_anchors", [])[:5],
            }
        )

    summary_families.sort(
        key=lambda family: (
            0 if family["status"] == "exhausted" else 1,
            0 if family["novelty_bucket"] == "edge_case" else 1,
            family["save_rate"],
        )
    )

    total_candidates = overall.get("candidates_seen", 0)
    total_duplicates = overall.get("duplicates", 0)
    total_seen = total_candidates + total_duplicates

    return {
        "project_id": memory.get("project_id", ""),
        "overall": {
            "families_tracked": len(summary_families),
            "strings_seen": overall.get("strings_seen", 0),
            "save_rate": round(overall.get("saves", 0) / max(total_candidates, 1), 4),
            "duplicate_rate": round(total_duplicates / max(total_seen, 1), 4),
            "novelty_mix": {
                "edge_case_saves": overall.get("edge_case_saves", 0),
                "canonical_saves": overall.get("canonical_saves", 0),
            },
        },
        "families": summary_families[:limit],
    }


def format_search_memory_summary(memory: dict | None, limit: int = 8) -> str:
    """Human-readable summary for prompt injection."""
    summary = build_search_memory_summary(memory, limit=limit)
    overall = summary["overall"]
    lines = [
        "Prior search-family memory:",
        (
            f"- {overall['families_tracked']} families tracked; "
            f"save_rate={overall['save_rate']:.1%}; "
            f"duplicate_rate={overall['duplicate_rate']:.1%}; "
            f"novelty_mix=edge_case:{overall['novelty_mix']['edge_case_saves']} / "
            f"canonical:{overall['novelty_mix']['canonical_saves']}"
        ),
    ]

    if not summary["families"]:
        lines.append("- No family history available yet.")
        return "\n".join(lines)

    lines.append("- Family status:")
    for family in summary["families"]:
        anchors = ", ".join(family["dominant_anchors"]) or "n/a"
        lines.append(
            "  "
            f"* {family['family_key']} [{family['novelty_bucket']} / {family['domain_lane']}] "
            f"status={family['status']} save_rate={family['save_rate']:.1%} "
            f"duplicate_rate={family['duplicate_rate']:.1%} anchors={anchors}"
        )
        if family["status_reason"]:
            lines.append(f"    reason: {family['status_reason']}")

    return "\n".join(lines)


def update_search_memory(
    memory: dict | None,
    project_id: str,
    strings: list,
) -> dict:
    """Merge completed search strings into the memory artifact."""
    memory = dict(memory or {})
    families = dict(memory.get("families", {}))
    overall = dict(memory.get("overall", {}))

    overall.setdefault("strings_seen", 0)
    overall.setdefault("pages_reviewed", 0)
    overall.setdefault("candidates_seen", 0)
    overall.setdefault("duplicates", 0)
    overall.setdefault("saves", 0)
    overall.setdefault("edge_case_saves", 0)
    overall.setdefault("canonical_saves", 0)

    for string in strings:
        family_key = normalize_family_key(
            getattr(string, "family_key", ""),
            getattr(string, "boolean", ""),
            getattr(string, "name", ""),
        )
        novelty_bucket = normalize_novelty_bucket(
            getattr(string, "novelty_bucket", ""),
            getattr(string, "boolean", ""),
            getattr(string, "name", ""),
        )
        domain_lane = infer_domain_lane(
            getattr(string, "domain_lane", ""),
            getattr(string, "boolean", ""),
            getattr(string, "name", ""),
        )

        entry = dict(families.get(family_key, {}))
        entry.setdefault("family_key", family_key)
        entry.setdefault("novelty_bucket", novelty_bucket)
        entry.setdefault("domain_lane", domain_lane)
        entry.setdefault("strings_seen", 0)
        entry.setdefault("pages_reviewed", 0)
        entry.setdefault("candidates_seen", 0)
        entry.setdefault("duplicates", 0)
        entry.setdefault("saves", 0)
        entry.setdefault("facial_yes", 0)
        entry.setdefault("facial_no", 0)
        entry.setdefault("anchor_counts", {})
        entry.setdefault("example_booleans", [])
        entry.setdefault("status", "active")
        entry.setdefault("status_reason", "")

        candidates_seen = int(getattr(string, "candidates_count", 0) or 0)
        duplicates = int(getattr(string, "duplicates_count", 0) or 0)
        saves = len(getattr(string, "saves", []) or [])
        facial_yes = int(getattr(string, "facial_yes_count", 0) or 0)
        facial_no = int(getattr(string, "facial_no_count", 0) or 0)

        entry["strings_seen"] += 1
        entry["pages_reviewed"] += int(getattr(string, "pages_reviewed", 0) or 0)
        entry["candidates_seen"] += candidates_seen
        entry["duplicates"] += duplicates
        entry["saves"] += saves
        entry["facial_yes"] += facial_yes
        entry["facial_no"] += facial_no
        entry["last_seen_at"] = datetime.now(timezone.utc).isoformat()

        anchors = extract_dominant_anchors(getattr(string, "boolean", ""))
        anchor_counts = Counter(entry.get("anchor_counts", {}))
        anchor_counts.update(anchors)
        entry["anchor_counts"] = dict(anchor_counts)
        entry["dominant_anchors"] = [
            anchor for anchor, _count in anchor_counts.most_common(5)
        ]

        example_booleans = list(entry.get("example_booleans", []))
        boolean = getattr(string, "boolean", "")
        if boolean and boolean not in example_booleans:
            example_booleans.append(boolean)
        entry["example_booleans"] = example_booleans[-3:]

        total_seen = entry["candidates_seen"] + entry["duplicates"]
        duplicate_rate = entry["duplicates"] / max(total_seen, 1)
        save_rate = entry["saves"] / max(entry["candidates_seen"], 1)
        low_novelty = entry["novelty_bucket"] == "canonical"
        repeated = entry["strings_seen"] >= 2

        if repeated and duplicate_rate >= 0.40:
            entry["status"] = "exhausted"
            entry["status_reason"] = "Repeated family with high duplicate overlap."
        elif repeated and low_novelty and save_rate <= 0.03:
            entry["status"] = "exhausted"
            entry["status_reason"] = "Repeated canonical family with low save yield."
        else:
            entry["status"] = "active"
            entry["status_reason"] = ""

        families[family_key] = entry

        overall["strings_seen"] += 1
        overall["pages_reviewed"] += int(getattr(string, "pages_reviewed", 0) or 0)
        overall["candidates_seen"] += candidates_seen
        overall["duplicates"] += duplicates
        overall["saves"] += saves
        if novelty_bucket == "edge_case":
            overall["edge_case_saves"] += saves
        else:
            overall["canonical_saves"] += saves

    memory["version"] = 1
    memory["project_id"] = project_id
    memory["updated_at"] = datetime.now(timezone.utc).isoformat()
    memory["overall"] = overall
    memory["families"] = families
    return memory
