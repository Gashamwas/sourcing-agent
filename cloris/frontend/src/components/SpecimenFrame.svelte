<script lang="ts">
  // SpecimenFrame — typeset-publication wrapper for any homescreen /
  // report section.
  //
  // Lifted from the brand-spec component lab at
  // /Users/sam.vangelos/Downloads/cloris-components.html (see .specimen
  // / .specimen-tag / .specimen-stage / .specimen-note at lines 107-131
  // and 114-120 of the lab HTML). The defining typesetter's move: the
  // mono-caps label sits ABOVE the top hairline by 9px and uses a cream
  // background patch to "cut" the border line behind it — exactly the
  // way a museum specimen card or a typography specimen sheet is
  // labeled.
  //
  // Use this anywhere a section needs to read as a typeset specimen
  // rather than a styled <section>. R15 in docs/cloris-surface-design-
  // rules.md tracks every primitive; SpecimenFrame is the v1 substrate
  // for the editorial-publication parity slice.
  //
  // Props:
  //   label    — mono-caps tag that protrudes through the top border
  //              (e.g. "needs attention — · today" or "verb grid")
  //   footnote — optional italic Cloris-voice footnote in the dotted
  //              footer ("She'll keep this casing in saved searches.")
  //   tag      — optional right-aligned mono-caps tag in the footer
  //              (e.g. "§ DAILY", "specimen 01")
  //   children — slot content (the actual section body)
  //
  // Footer is omitted entirely when both footnote and tag are null —
  // some specimens don't need a note.

  import type { Snippet } from "svelte";

  let {
    label,
    footnote = null,
    tag = null,
    children
  }: {
    label: string;
    footnote?: string | null;
    tag?: string | null;
    children: Snippet;
  } = $props();

  const hasFooter = $derived(footnote !== null || tag !== null);
</script>

<figure class="specimen-frame">
  <span class="specimen-frame-label">{label}</span>
  <div class="specimen-frame-stage">
    {@render children()}
  </div>
  {#if hasFooter}
    <figcaption class="specimen-frame-note">
      <span class="specimen-frame-footnote">{footnote ?? ""}</span>
      {#if tag !== null}
        <span class="specimen-frame-tag">{tag}</span>
      {/if}
    </figcaption>
  {/if}
</figure>
