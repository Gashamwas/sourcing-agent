<!--
  EditorialReviewCard — shared structural shell for recruiter-facing
  review cards.

  Designer Slice 6 extracts this from HunkCard.svelte (which previously
  carried the shell directly) so both:
    - HunkCard.svelte (text-shaped reflection hunks; brief-iteration
      Gate 2)
    - VisualHunkCard.svelte (multimodal visual-judgment cards;
      Designer module HITL surface)
  share one structural primitive. The CONTENT primitive differs per
  surface (BriefChangeBeforeAfter vs VisualReviewBeforeAfter); the
  CHROME (kind eyebrow, section label, approve/skip toggle, rationale
  block, --terracotta left rule on approved) is identical.

  Visual rules (preserved from the HunkCard shell):
    - Approved cards have a left rule in --terracotta (the affirmative
      accent across the system).
    - Skipped cards gray to --ink-muted with reduced opacity.
    - R7 mono-caps discipline: only the kind badge is mono-caps;
      section label is sentence-case Fraunces.
    - Hover state is a subtle paper-card shift; no shadow-card chrome.

  Body content is rendered via the default slot. Rationale is optional
  and renders below the body when the `rationale` prop is non-empty
  (or the named `rationale` snippet is provided for richer formatting).
-->
<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    kindLabel,
    sectionLabel,
    kindClass = "",
    approved = true,
    onToggle,
    disabled = false,
    rationale = null,
    ariaLabel = "",
    children,
  }: {
    /** Mono-caps eyebrow text — "new" / "refine" / "remove" /
     *  "visual review" / etc. The caller derives this from the
     *  underlying kind enum (KIND_LABELS lookup, etc.) so this
     *  shell stays generic over surfaces. */
    kindLabel: string;
    /** Sentence-case section label — "capability area" /
     *  "visual hierarchy" / etc. */
    sectionLabel: string;
    /** Optional CSS class hook on the kind badge for surface-specific
     *  color/style. Convention: the caller's KIND_LABELS map provides
     *  the semantic class string (e.g., "hunk-card-kind--add"). */
    kindClass?: string;
    /** Whether the card is in the "approve" state (left rule) vs
     *  "skip" state (gray + reduced opacity). */
    approved?: boolean;
    /** Toggle callback fired when the recruiter clicks Approve/Skip. */
    onToggle: (next: boolean) => void;
    /** Disable the toggle (during a server round-trip, etc.). */
    disabled?: boolean;
    /** Plain-text rationale string — rendered as italic prose in the
     *  rationale block. For richer rationale shapes (multi-paragraph,
     *  inline marks, etc.) callers compose their own slot inside
     *  the body and pass `rationale={null}`. */
    rationale?: string | null;
    /** ARIA label for the article element. Caller provides the
     *  surface-specific framing so screen readers get clean copy. */
    ariaLabel?: string;
    children: Snippet;
  } = $props();

  function handleToggle(): void {
    onToggle(!approved);
  }

  let computedAriaLabel = $derived(
    ariaLabel || `${approved ? "Approved" : "Skipped"}: ${sectionLabel}`
  );
</script>

<article
  class={`hunk-card ${approved ? "hunk-card--approved" : "hunk-card--skipped"}`}
  aria-label={computedAriaLabel}
>
  <header class="hunk-card-header">
    <!-- R7: only ONE mono-caps element per region. The kind badge
         carries the operational signal ("NEW" / "REFINE" / "REMOVE" /
         "VISUAL REVIEW" / etc.) and stays mono-caps. The section label
         is demoted to sentence-case Fraunces so we don't stack two
         uppercase registers in the same header row. -->
    <span class={`hunk-card-kind ${kindClass}`}>{kindLabel}</span>
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

  {@render children()}

  {#if rationale}
    <section class="hunk-card-rationale">
      <p class="hunk-card-block-label">Why:</p>
      <p class="hunk-card-rationale-prose">
        <em>{rationale}</em>
      </p>
    </section>
  {/if}
</article>
