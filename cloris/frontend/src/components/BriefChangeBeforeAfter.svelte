<!--
  BriefChangeBeforeAfter — shared diff display block.

  Renders the editorial before/after pair for a brief change. Used by:
    - HunkCard.svelte (Reflection Gate 2)
    - RefreshBrief.svelte (per-suggestion accept toggles)

  Lifted out of the two parallel render loops so the visual contract
  for "what does a brief change look like to the recruiter" lives in
  one place. Card-level chrome (kind badge, approve toggle, rationale,
  bulk controls) stays in the calling component — this primitive owns
  the diff block only.

  Two render modes:
    - Prose section (instructions, notes, depth_distinction prose):
      renders before/after as italic Instrument Serif paragraphs with
      <del>/<ins> wrappers for visual diff weight.
    - Tag section (additional_search_terms, employer_signal_rules,
      search_priorities, capability_areas adds): renders the after as
      a single tag-like value with cream background + wood-rule border.
      Before (when present) is rendered as a struck-through tag.

  When `before` is null or empty (an "add" case), only the after block
  renders. The two before/after labels can be overridden by the caller
  for context-specific framing ("Currently:" vs "Before:" vs etc.).
-->
<script lang="ts">
  import type { BriefChangeKind } from "../lib/briefChanges";

  let {
    before = null,
    after,
    kind = "modify",
    isProseSection = false,
    beforeLabel = "Currently:",
    afterLabel = "",
  }: {
    before?: string | null;
    after: string;
    kind?: BriefChangeKind;
    isProseSection?: boolean;
    beforeLabel?: string;
    afterLabel?: string;
  } = $props();

  // Default afterLabel reflects the kind so callers don't have to
  // re-derive it. Modify -> "Cloris suggests:"; add -> "Cloris would add:".
  // Caller can override for surface-specific framing.
  let resolvedAfterLabel = $derived(
    afterLabel.length > 0
      ? afterLabel
      : kind === "modify"
        ? "Cloris suggests:"
        : "Cloris would add:"
  );

  let hasBefore = $derived(
    before !== null && before !== undefined && before.length > 0
  );
</script>

{#if hasBefore && kind === "modify"}
  <section class="brief-change-before">
    <p class="brief-change-block-label">{beforeLabel}</p>
    {#if isProseSection}
      <p class="brief-change-prose brief-change-prose--before">
        <del>{before}</del>
      </p>
    {:else}
      <p class="brief-change-tag brief-change-tag--before">
        <del>{before}</del>
      </p>
    {/if}
  </section>
{/if}

<section class="brief-change-after">
  <p class="brief-change-block-label">{resolvedAfterLabel}</p>
  {#if isProseSection}
    <p class="brief-change-prose brief-change-prose--after">
      <ins>{after}</ins>
    </p>
  {:else}
    <p class="brief-change-tag brief-change-tag--after">
      <ins>{after}</ins>
    </p>
  {/if}
</section>
