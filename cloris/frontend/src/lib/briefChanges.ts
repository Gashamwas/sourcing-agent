// Shared base type for brief-change diff entries.
//
// Both the RefreshBrief surface (lib/briefDiff.ts:BriefDiffEntry) and
// the Reflection surface (lib/reflection/types.ts:ReflectionHunk) carry
// proposed changes to a brief. Their wire shapes differ in card-level
// chrome (label, confidence, default_approved, target_field on the
// reflection side) but the diff core — field, kind, before, after,
// rationale — is identical.
//
// Lifting the core into BaseBriefChange means:
//   1. The shared <BriefChangeBeforeAfter /> render primitive can take
//      either an entry or a hunk and render the same diff block.
//   2. Future surfaces that propose brief edits inherit the contract
//      without re-establishing it.
//   3. Drift between RefreshBrief and Reflection becomes harder to
//      introduce silently — type-level coupling enforces shape parity.

export type BriefChangeKind = "add" | "remove" | "modify";

export interface BaseBriefChange {
  // Brief field being changed (e.g. "additional_search_terms",
  // "depth_distinction.builder_definition", "capability_areas[<key>]").
  field: string;
  kind: BriefChangeKind;
  // The pre-change value (string for prose fields; null for "add" cases
  // or list-section appends where there's nothing to show before).
  before: string | null;
  // The proposed value (always a string at the diff layer; consumers
  // that need structured data store it elsewhere on the entry).
  after: string;
  // Optional editorial cue Cloris uses to explain WHY she's suggesting
  // this change. Renders as italic prose under the field name.
  rationale?: string;
}
