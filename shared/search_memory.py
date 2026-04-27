"""Helpers for brief-scoped search family memory and lightweight metadata inference."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.brief_loader import Brief


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
}


def _slugify(value: str) -> str:
    text = _NON_ALNUM.sub("_", (value or "").lower()).strip("_")
    return re.sub(r"_+", "_", text) or "unlabeled_family"


def _canonicalize_lane_id(value: str) -> str:
    """Normalize a domain lane label into the canonical lane-id shape.

    Both the explicit-value path and the brief-hint fallback path in
    ``infer_domain_lane`` must return the same shape, so this helper is the
    single normalizer for lane labels (e.g. ``"Capital Markets"`` →
    ``"capital_markets"``).
    """
    return _slugify(value)


def _stringify_list(value: list[object]) -> list[str]:
    out: list[str] = []
    for item in value or []:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _domain_lane_hint_map(brief: "Brief | None") -> dict[str, tuple[str, ...]]:
    """Build a {lane: (pattern, ...)} map from a brief's domain_lane_hints, if any.

    Lane keys are canonicalized to match the explicit-value path in
    ``infer_domain_lane``; pattern values stay as raw lowercase strings so
    substring matching against the boolean/rationale text still works.
    """
    if brief is None:
        return {}
    hints = getattr(brief, "domain_lane_hints", None) or []
    out: dict[str, tuple[str, ...]] = {}
    for hint in hints:
        lane = str(getattr(hint, "lane", "") or "").strip()
        patterns = getattr(hint, "patterns", None) or []
        normalized = tuple(
            str(pattern).strip().lower()
            for pattern in patterns
            if str(pattern).strip()
        )
        if lane and normalized:
            out[_canonicalize_lane_id(lane)] = normalized
    return out


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
    *,
    brief: "Brief | None" = None,
) -> str:
    """Normalize an explicit novelty value to ``edge_case``/``canonical``.

    When no explicit value is supplied, fall back to ``"canonical"`` — the
    vertical-agnostic default. ``boolean`` and ``rationale`` are accepted for
    signature stability with prior callers and for future brief-aware
    classification, but are not consulted here.
    """
    if novelty_bucket:
        value = _slugify(novelty_bucket)
        if value in {"edge_case", "canonical"}:
            return value
    return "canonical"


def infer_domain_lane(
    domain_lane: str | None,
    boolean: str = "",
    rationale: str = "",
    *,
    brief: "Brief | None" = None,
) -> str:
    """Infer the primary domain lane for a string.

    When ``brief`` exposes non-empty ``domain_lane_hints``, those patterns are
    consulted as a fallback after the explicit ``domain_lane`` value. Otherwise
    we default to ``"general"`` — the vertical-agnostic baseline.
    """
    if domain_lane:
        return _canonicalize_lane_id(domain_lane)

    lane_hints = _domain_lane_hint_map(brief)
    if lane_hints:
        text = f"{boolean} {rationale}".lower()
        for lane, patterns in lane_hints.items():
            if any(pattern in text for pattern in patterns):
                return lane

    return "general"


def extract_dominant_anchors(text: str, limit: int = 5) -> list[str]:
    """Extract a compact list of likely anchor tokens from a Boolean string.

    Uses generic English tokenization and stopword filtering only; no
    vertical-coupled phrase pre-pass.
    """
    lowered = (text or "").lower()
    tokens = [
        token for token in _WHITESPACE.split(_NON_ALNUM.sub(" ", lowered))
        if token and token not in _STOPWORDS and len(token) > 2
    ]
    counts = Counter(tokens)
    anchors: list[str] = []
    seen: set[str] = set()
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
    layer_items = memory.get("layer_items", {})
    layer_item_summary = sorted(
        (
            {
                "layer_item_id": item.get("layer_item_id", ""),
                "layer_name": item.get("layer_name", ""),
                "label": item.get("label", ""),
                "family_keys": item.get("family_keys", [])[:3],
                "saves": item.get("saves", 0),
                "strings_seen": item.get("strings_seen", 0),
                "noise_rate": round(item.get("noise_rate", 0.0), 4),
                "duplicate_rate": round(item.get("duplicate_rate", 0.0), 4),
            }
            for item in layer_items.values()
            if isinstance(item, dict)
        ),
        key=lambda item: (item["saves"], item["strings_seen"]),
        reverse=True,
    )
    hypotheses = memory.get("hypotheses", {})
    hypothesis_summary = sorted(
        (
            {
                "hypothesis_id": item.get("hypothesis_id", ""),
                "status": item.get("status", "hypothesis"),
                "source": item.get("source", ""),
                "saves": item.get("saves", 0),
                "strings_seen": item.get("strings_seen", 0),
                "confidence": round(item.get("confidence", 0.0), 4),
            }
            for item in hypotheses.values()
            if isinstance(item, dict)
        ),
        key=lambda item: (item["saves"], item["strings_seen"]),
        reverse=True,
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
        "layer_items": layer_item_summary[:limit],
        "hypotheses": hypothesis_summary[:limit],
    }


def get_search_memory_families(memory: dict | None) -> list[dict]:
    """Return family records from either raw memory artifacts or summarized memory."""
    if not memory:
        return []

    families = memory.get("families", [])
    if isinstance(families, dict):
        iterable = families.values()
    elif isinstance(families, list):
        iterable = families
    else:
        return []

    return [family for family in iterable if isinstance(family, dict)]


def format_search_memory_summary(memory: dict | None, limit: int = 8) -> str:
    """Human-readable summary for prompt injection."""
    summary = memory or {}
    if not summary or not isinstance(summary.get("families"), list):
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
        if summary.get("layer_items"):
            lines.append("- Layer items observed:")
            for item in summary["layer_items"][:limit]:
                lines.append(
                    "  "
                    f"* {item['layer_name']}::{item['label']} saves={item['saves']} "
                    f"strings={item['strings_seen']} noise_rate={item['noise_rate']:.1%}"
                )
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
    if summary.get("layer_items"):
        lines.append("- High-signal retrieval layer items:")
        for item in summary["layer_items"][:5]:
            lines.append(
                "  "
                f"* {item['layer_name']}::{item['label']} saves={item['saves']} "
                f"strings={item['strings_seen']} duplicate_rate={item['duplicate_rate']:.1%}"
            )
    if summary.get("hypotheses"):
        lines.append("- Edge-case hypothesis status:")
        for item in summary["hypotheses"][:5]:
            lines.append(
                "  "
                f"* {item['hypothesis_id']} status={item['status']} "
                f"saves={item['saves']} strings={item['strings_seen']}"
            )

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
    layer_items = dict(memory.get("layer_items", {}))
    layer_combinations = dict(memory.get("layer_combinations", {}))
    hypotheses = dict(memory.get("hypotheses", {}))

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

        retrieval_recipe = getattr(string, "retrieval_recipe", {}) or {}
        used_layer_items = retrieval_recipe.get("used_layer_item_ids", {})
        if isinstance(used_layer_items, dict):
            for layer_name, item_ids in used_layer_items.items():
                for item_id in _stringify_list(item_ids):
                    layer_entry = dict(layer_items.get(item_id, {}))
                    layer_entry.setdefault("layer_item_id", item_id)
                    layer_entry.setdefault("layer_name", layer_name)
                    layer_entry.setdefault("label", item_id.replace("_", " "))
                    layer_entry.setdefault("family_keys", [])
                    layer_entry.setdefault("strings_seen", 0)
                    layer_entry.setdefault("saves", 0)
                    layer_entry.setdefault("duplicates", 0)
                    layer_entry.setdefault("candidates_seen", 0)
                    layer_entry["strings_seen"] += 1
                    layer_entry["saves"] += saves
                    layer_entry["duplicates"] += duplicates
                    layer_entry["candidates_seen"] += candidates_seen
                    if family_key not in layer_entry["family_keys"]:
                        layer_entry["family_keys"] = list(layer_entry["family_keys"]) + [family_key]
                    total_seen = layer_entry["candidates_seen"] + layer_entry["duplicates"]
                    layer_entry["duplicate_rate"] = round(
                        layer_entry["duplicates"] / max(total_seen, 1), 4
                    )
                    layer_entry["noise_rate"] = round(
                        max(layer_entry["candidates_seen"] - layer_entry["saves"], 0)
                        / max(layer_entry["candidates_seen"], 1),
                        4,
                    )
                    layer_items[item_id] = layer_entry

            combo_key = "|".join(
                sorted(
                    item_id
                    for values in used_layer_items.values()
                    for item_id in _stringify_list(values)
                )
            )
            if combo_key:
                combo_entry = dict(layer_combinations.get(combo_key, {}))
                combo_entry.setdefault("combo_key", combo_key)
                combo_entry.setdefault("strings_seen", 0)
                combo_entry.setdefault("saves", 0)
                combo_entry.setdefault("duplicates", 0)
                combo_entry.setdefault("candidate_count", 0)
                combo_entry["strings_seen"] += 1
                combo_entry["saves"] += saves
                combo_entry["duplicates"] += duplicates
                combo_entry["candidate_count"] += candidates_seen
                layer_combinations[combo_key] = combo_entry

        for hypothesis_id in _stringify_list(
            getattr(string, "retrieval_hypothesis_ids", [])
            or retrieval_recipe.get("applied_hypothesis_ids", [])
        ):
            hypothesis_entry = dict(hypotheses.get(hypothesis_id, {}))
            hypothesis_entry.setdefault("hypothesis_id", hypothesis_id)
            hypothesis_entry.setdefault("status", "hypothesis")
            hypothesis_entry.setdefault("source", "run")
            hypothesis_entry.setdefault("strings_seen", 0)
            hypothesis_entry.setdefault("saves", 0)
            hypothesis_entry.setdefault("duplicates", 0)
            hypothesis_entry.setdefault("candidate_count", 0)
            hypothesis_entry["strings_seen"] += 1
            hypothesis_entry["saves"] += saves
            hypothesis_entry["duplicates"] += duplicates
            hypothesis_entry["candidate_count"] += candidates_seen
            if hypothesis_entry["strings_seen"] >= 2 and hypothesis_entry["saves"] >= 2:
                hypothesis_entry["status"] = "validated"
                hypothesis_entry["confidence"] = 0.7
            else:
                hypothesis_entry["confidence"] = 0.35 if hypothesis_entry["saves"] else 0.15
            hypotheses[hypothesis_id] = hypothesis_entry

    memory["version"] = 1
    memory["project_id"] = project_id
    memory["updated_at"] = datetime.now(timezone.utc).isoformat()
    memory["overall"] = overall
    memory["families"] = families
    memory["layer_items"] = layer_items
    memory["layer_combinations"] = layer_combinations
    memory["hypotheses"] = hypotheses
    return memory
