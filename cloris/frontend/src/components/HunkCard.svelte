<!--
  HunkCard — one proposed brief change in the diff (Gate 2).

  Each hunk is rendered as an editorial card that mirrors the
  brief-detail section style (cf. BriefDetail.svelte:195-212). NOT a
  JSON diff, NOT a side-by-side text diff. The card carries:

    - Eyebrow with the hunk kind (NEW / REFINE) + section label
    - Cloris suggestion (the "after" value, formatted by section)
    - Optional "currently:" before-block when the hunk is a modify
    - Rationale paragraph (Cloris voice)
    - Per-hunk approve / skip toggle

  Per the trial-day phasing decision: inline edit modal is week-2.
  This card surfaces approve/skip only.

  Visual state:
    - Approved hunks have a left rule in --terracotta (the affirmative
      accent across the system).
    - Skipped hunks gray to --ink-muted with reduced opacity.
    - The hover state on the card is a subtle paper-card shift; no
      shadow-card chrome (frontend rule: editorial primitives only).

  Section-aware rendering:
    - additional_search_terms / employer_signal_rules / search_priorities:
      list-shaped sections; render the after as a single tag-like value.
    - instructions / notes: prose; render as italic Instrument Serif
      paragraph for the "Cloris suggests" block.
    - Other sections (legacy or unknown target_field): fall through
      to neutral prose rendering.
-->
<script lang="ts">
  import type { ReflectionHunk } from "../lib/reflection/types";
  import BriefChangeBeforeAfter from "./BriefChangeBeforeAfter.svelte";

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
  };

  let kindLabel = $derived(KIND_LABELS[hunk.kind] ?? hunk.kind);
  let sectionLabel = $derived(
    SECTION_LABELS[hunk.section] ?? hunk.section.replace(/_/g, " ")
  );

  // List-shaped sections render the suggestion as a tag-like single
  // value; prose sections render it as an italic paragraph block.
  const PROSE_SECTIONS = new Set(["instructions", "notes"]);
  let isProseSection = $derived(PROSE_SECTIONS.has(hunk.section));

  function handleToggle(): void {
    onToggle(!approved);
  }
</script>

<article
  class={`hunk-card ${approved ? "hunk-card--approved" : "hunk-card--skipped"}`}
  aria-label={`${approved ? "Approved" : "Skipped"}: ${hunk.label}`}
>
  <header class="hunk-card-header">
    <!-- R7: only ONE mono-caps element per region. The kind badge
         carries the operational signal ("NEW" / "REFINE" / "REMOVE")
         and stays mono-caps. The section label is demoted to
         sentence-case Fraunces so we don't stack two uppercase
         registers in the same header row. -->
    <span class={`hunk-card-kind hunk-card-kind--${hunk.kind}`}>
      {kindLabel}
    </span>
    <span class="hunk-card-section">{sectionLabel}</span>
    <button
      type="button"
      class="hunk-card-toggle"
      aria-pressed={approved}
      {disabled}
      onclick={handleToggle}
    >
      {approved ? "Skip" : "Approve"}
    </button>
  </header>

  <!-- Diff display block lifted to BriefChangeBeforeAfter so this card
       and the per-suggestion entries on RefreshBrief.svelte share one
       implementation of "what does a brief change look like". -->
  <BriefChangeBeforeAfter
    before={hunk.before}
    after={hunk.after}
    kind={hunk.kind}
    {isProseSection}
  />

  {#if hunk.rationale}
    <section class="hunk-card-rationale">
      <p class="hunk-card-block-label">Why:</p>
      <p class="hunk-card-rationale-prose">
        <em>{hunk.rationale}</em>
      </p>
    </section>
  {/if}
</article>
