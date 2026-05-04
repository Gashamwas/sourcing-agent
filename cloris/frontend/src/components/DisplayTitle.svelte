<script lang="ts">
  // DisplayTitle — section title typographic duo.
  //
  // Lifted from the brand-spec component lab at
  // /Users/sam.vangelos/Downloads/cloris-components.html. Every lab
  // section title is a duo: Fraunces serif head + Instrument Serif
  // italic peach-deep accent word ("The chrome you don't *see*",
  // "She's *at work*", "When she *says* something", "A little of her
  // *house*", "The kettle is *whistling*").
  //
  // Two typefaces, one color shift, baseline-aligned. The italic word
  // toggles to a different *typeface family* (Instrument Serif), not
  // just a different slant — that's what gives the lab its literary
  // register.
  //
  // Use this for section titles wherever the editorial register is the
  // posture (homescreen sections, future Workspace sections, future
  // Brief Library sections). For sentence-case titles without a duo,
  // keep using the existing .card-stack-title pattern.
  //
  // Props:
  //   head    — the head word(s), Fraunces sentence-case
  //   accent  — the italic accent word, Instrument Serif italic, peach-
  //             deep. Single word or short phrase.
  //   level   — heading level (1-3); defaults to 2 to match
  //             .card-stack-title and other section-h2 conventions.

  type HeadingLevel = 1 | 2 | 3;

  let {
    head,
    accent,
    level = 2
  }: {
    head: string;
    accent: string;
    level?: HeadingLevel;
  } = $props();
</script>

{#if level === 1}
  <h1 class="display-title">
    <span class="display-title-head">{head}</span>
    <em class="display-title-accent">{accent}</em>
  </h1>
{:else if level === 3}
  <h3 class="display-title">
    <span class="display-title-head">{head}</span>
    <em class="display-title-accent">{accent}</em>
  </h3>
{:else}
  <h2 class="display-title">
    <span class="display-title-head">{head}</span>
    <em class="display-title-accent">{accent}</em>
  </h2>
{/if}
