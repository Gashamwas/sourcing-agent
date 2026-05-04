<!--
  HunkCard — one proposed brief change in the diff (Gate 2).

  Refactored in Designer Slice 6: the structural shell (header,
  toggle, rationale block, --terracotta left rule) lives in
  EditorialReviewCard.svelte; the content primitive
  (BriefChangeBeforeAfter) ports unchanged. Behavior preserved —
  existing HunkCard tests assert this card renders byte-identically
  against the same `hunk` input.

  Per-hunk shape (unchanged):
    - Eyebrow with the hunk kind (NEW / REFINE / REMOVE) + section label
    - Cloris suggestion (the "after" value, formatted by section)
    - Optional "currently:" before-block when the hunk is a modify
    - Rationale paragraph (Cloris voice)
    - Per-hunk approve / skip toggle

  Section-aware rendering (preserved):
    - additional_search_terms / employer_signal_rules / search_priorities:
      list-shaped sections; render the after as a single tag-like value.
    - instructions / notes: prose; render as italic Instrument Serif
      paragraph for the "Cloris suggests" block.
-->
<script lang="ts">
  import type { ReflectionHunk } from "../lib/reflection/types";
  import BriefChangeBeforeAfter from "./BriefChangeBeforeAfter.svelte";
  import EditorialReviewCard from "./EditorialReviewCard.svelte";

  let { hunk, approved = true, onToggle, disabled = false }: {
    hunk: ReflectionHunk;
    approved?: boolean;
    onToggle: (next: boolean) => void;
    disabled?: boolean;
  } = $props();

  const KIND_LABELS: Record<string, string> = {
    add: "new",
    modify: "refine",
    remove: "remove",
    // Designer Slice 9: rubric refinement proposals from
    // design-market intelligence reflection polish. The hunk's
    // before/after carries a JSON fragment of the rubric weight or
    // exemplar change; the recruiter approves to apply.
    rubric_refine: "rubric",
  };

  const SECTION_LABELS: Record<string, string> = {
    additional_search_terms: "additional search terms",
    employer_signal_rules: "employer signal rule",
    search_priorities: "search priority",
    instructions: "search instructions",
    notes: "brief notes",
    capability_areas: "capability area",
    depth_distinction: "depth distinction",
    non_fit_patterns: "non-fit pattern",
    // Designer Slice 9: rubric-refinement section labels.
    "design_rubric.discipline_weight_overrides": "rubric weight",
    "design_rubric.calibration_exemplars": "rubric exemplar",
  };

  let kindLabel = $derived(KIND_LABELS[hunk.kind] ?? hunk.kind);
  let sectionLabel = $derived(
    SECTION_LABELS[hunk.section] ?? hunk.section.replace(/_/g, " ")
  );
  let kindClass = $derived(`hunk-card-kind--${hunk.kind}`);

  // List-shaped sections render the suggestion as a tag-like single
  // value; prose sections render it as an italic paragraph block.
  const PROSE_SECTIONS = new Set(["instructions", "notes"]);
  let isProseSection = $derived(PROSE_SECTIONS.has(hunk.section));
</script>

<EditorialReviewCard
  {kindLabel}
  {sectionLabel}
  {kindClass}
  {approved}
  {onToggle}
  {disabled}
  rationale={hunk.rationale ?? null}
  ariaLabel={`${approved ? "Approved" : "Skipped"}: ${hunk.label}`}
>
  <!-- Diff display block lifted to BriefChangeBeforeAfter so this card
       and the per-suggestion entries on RefreshBrief.svelte share one
       implementation of "what does a brief change look like". -->
  <BriefChangeBeforeAfter
    before={hunk.before}
    after={hunk.after}
    kind={hunk.kind}
    {isProseSection}
  />
</EditorialReviewCard>
