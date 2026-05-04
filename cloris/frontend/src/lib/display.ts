// Cloris frontend display helpers.
//
// Pure transforms over StateDirEntry. No backend changes; these run in the
// browser to give each card a human-facing name and a small catalog/reference
// number that reads like a card-file index.
//
// Source-of-truth fields (from cloris/models.py / lib/types.ts):
//   - source: "linkedin" | "github"
//   - state_key: opaque backend key
//   - brief_id_from_run: optional brief-derived id
//   - brief_path_from_worker: optional brief path on disk
//
// Display-name policy:
//   1. Prefer brief_id_from_run cleaned up.
//   2. Otherwise derive from brief_path_from_worker basename (without
//      extension).
//   3. Otherwise derive from state_key (cleaned).
//   4. If the cleaned candidate is numeric-only (no letters), do NOT show
//      a digit string as the visible card title — fall back to a generic
//      label keyed off source. The catalog number still carries the digits.
//
// Catalog-number policy:
//   - Always derived from source + state_key (never invented).
//   - LinkedIn → "LI-<state_key, uppercased and sanitized>"
//   - GitHub   → "GH-<state_key, uppercased and sanitized>"
//   - Sanitize: strip non-alphanumeric except hyphens; cap to a readable
//     length so it reads like a Dewey-decimal number, not a UUID.

import type { Source, StateDirEntry } from "./types";

const TRAILING_LONG_DIGITS = /[-_]?\d{6,}$/; // e.g. "..._2015831122" or "...-1957683706"
const TRAILING_VERSION_TAG = /[-_]v\d+$/i; // e.g. "...-v1", "..._v4"
const TRAILING_DATE_TAG = /[-_](?:\d{4}[-_]?\d{2}[-_]?\d{2})$/; // ...-2026-04-27 etc.

function stripTrailingRunIdish(value: string): string {
  let next = value;
  next = next.replace(TRAILING_DATE_TAG, "");
  next = next.replace(TRAILING_LONG_DIGITS, "");
  return next;
}

// Tiny, deliberate acronym map. Only obvious tokens we know we'll see in
// real state_keys / brief ids on this product. Keep this list short — we'd
// rather under-style than mis-style. Keys are lower-case for matching.
const ACRONYMS: Record<string, string> = {
  fde: "FDE",
  fdl: "FDL",
  pm: "PM",
  swe: "SWE",
  sre: "SRE",
  ic: "IC",
  // gh -> GitHub: only when it appears as a standalone word inside a
  // humanized name (not as part of "github" which already case-fixes).
  gh: "GitHub"
};

function applyAcronyms(word: string): string {
  const lower = word.toLowerCase();
  const mapped = ACRONYMS[lower];
  return mapped !== undefined ? mapped : word;
}

function humanize(value: string): string {
  const cleaned = stripTrailingRunIdish(value).replace(/[_-]+/g, " ").trim();
  if (cleaned === "") return value;
  // If the string already contains uppercase letters, the source likely
  // had intentional casing — leave it alone. We still walk the words so
  // standalone known acronyms get their canonical casing.
  if (/[A-Z]/.test(cleaned)) {
    return cleaned
      .split(/\s+/)
      .map((word) => applyAcronyms(word))
      .join(" ");
  }
  return cleaned
    .split(/\s+/)
    .map((word) => {
      if (word.length === 0) return word;
      const acronym = ACRONYMS[word.toLowerCase()];
      if (acronym !== undefined) return acronym;
      return word[0].toUpperCase() + word.slice(1);
    })
    .join(" ");
}

function basenameWithoutExt(path: string): string {
  const slash = path.replace(/\\/g, "/").lastIndexOf("/");
  const tail = slash === -1 ? path : path.slice(slash + 1);
  const dot = tail.lastIndexOf(".");
  return dot === -1 ? tail : tail.slice(0, dot);
}

// A candidate is "useful as a name" only when it contains at least one
// letter. Backends sometimes record a numeric LinkedIn search id (e.g.
// "2015831122") as brief_id_from_run; that's a reference number, not a
// human-facing name, so we fall through to the next source.
function hasLetter(value: string): boolean {
  return /[A-Za-z]/.test(value);
}

function isNumericOnly(value: string): boolean {
  return value.length > 0 && !hasLetter(value);
}

// Generic placeholder when no real human label exists. We deliberately
// don't invent a role/location — the catalog number on the card already
// carries the technical reference, and the Reference Slip exposes the
// underlying state_key for anyone who needs it.
function genericLabel(entry: StateDirEntry): string {
  return genericLabelForSource(entry.source);
}

function genericLabelForSource(source: Source): string {
  if (source === "linkedin") return "LinkedIn card";
  if (source === "github") return "GitHub card";
  return "Sourcing card";
}

// Humanize a state_key directly without manufacturing a synthetic
// StateDirEntry. Reuses the same humanize / numeric-fallback logic as
// `displayName`. Used by surfaces that have a state_key but not a full
// StateDirEntry (e.g. the run-report page, where the URL params carry
// `(source, state_key)` and the run id but not the entry).
//
// Title-fallback chain for non-card surfaces:
//   1. humanizeStateKey(state_key, source)
//   2. The caller's source-typed generic ("LinkedIn search", etc.) is
//      surfaced when this returns the generic label.
// TODO: The LLM prompt that generates market_thesis JSON should be
// updated to emit prose lane labels instead of snake_case keys, so
// humanizeStateKey is only a fallback rather than the primary display
// name in the market-detail lane list.
export function humanizeStateKey(stateKey: string, source: Source): string {
  const cleaned = humanize(stateKey);
  if (isNumericOnly(cleaned)) {
  return genericLabelForSource(source);
  }
  return cleaned;
}

export function displayName(entry: StateDirEntry): string {
  const briefId = entry.brief_id_from_run?.trim();
  if (briefId && hasLetter(briefId)) {
    return humanize(briefId);
  }
  const briefPath = entry.brief_path_from_worker?.trim();
  if (briefPath && briefPath.length > 0) {
    const base = basenameWithoutExt(briefPath);
    if (hasLetter(base)) {
      return humanize(base);
    }
  }
  // Cleaned state_key is the last derivation step. If after cleaning it's
  // numeric-only (or empty), do not show the number as the card title —
  // surface a source-typed generic label instead. The digits stay visible
  // in the catalog number on the card footer, which is the right place
  // for technical references.
  const stateCleaned = humanize(entry.state_key);
  if (isNumericOnly(stateCleaned)) {
    return genericLabel(entry);
  }
  return stateCleaned;
}

// Catalog/reference number. A short, all-caps, hyphenated tag derived from
// source + state_key. Reads like a library card reference, not the run's
// primary identity.
export function catalogNumber(entry: StateDirEntry): string {
  const prefix = entry.source === "linkedin" ? "LI" : "GH";
  const sanitized = entry.state_key
    .toUpperCase()
    .replace(/[^A-Z0-9-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  const capped = sanitized.length > 28 ? sanitized.slice(0, 28) : sanitized;
  return `${prefix}-${capped}`;
}
