<script lang="ts">
  // RunningFolio — slim mono-caps verb strip, the homescreen's
  // chapter-header. Replaces the prior 2x3 verb-tile grid (the today's-plan
  // SpecimenFrame on the homescreen) with a single horizontal band:
  //
  //   WRITE · START · REPORT · MARKET
  //
  // The strip is editorial: it names the chapters of the product as
  // plain-English mono-caps verbs. The recruiter doesn't need to hover
  // to learn what each one does (R21); the verbs still become muscle
  // memory by the second visit.
  //
  // Soft-disabled verbs (REVIEW when no run exists, MARKET) keep the same
  // visual register but don't fire onVerb. Telemetry mirrors the prior
  // VerbTile primitive — verb_tile_clicked / verb_tile_disabled_clicked —
  // so the analytics surface is unchanged across the redesign.

  import type { VerbTileCopy } from "../lib/copy";
  import type { VerbId } from "../lib/telemetry";
  import { emit } from "../lib/telemetry";

  let {
    tiles,
    onVerb
  }: {
    tiles: readonly VerbTileCopy[];
    onVerb: (id: VerbId) => void;
  } = $props();

  function isDisabled(copy: VerbTileCopy): boolean {
    return copy.disabled !== null;
  }

  function handleClick(event: MouseEvent, copy: VerbTileCopy) {
    event.preventDefault();
    if (isDisabled(copy)) {
      emit({ type: "verb_tile_disabled_clicked", verb: copy.id });
      return;
    }
    emit({ type: "verb_tile_clicked", verb: copy.id });
    onVerb(copy.id);
  }

  function handleKey(event: KeyboardEvent, copy: VerbTileCopy) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    if (isDisabled(copy)) {
      emit({ type: "verb_tile_disabled_clicked", verb: copy.id });
      return;
    }
    emit({ type: "verb_tile_clicked", verb: copy.id });
    onVerb(copy.id);
  }
</script>

<nav class="running-folio" aria-label="What Cloris does">
  {#each tiles as copy (copy.id)}
    <button
      type="button"
      class={`folio-verb ${isDisabled(copy) ? "folio-verb--disabled" : ""}`}
      data-verb={copy.id}
      aria-disabled={isDisabled(copy)}
      title={copy.disabled ?? copy.eyebrow}
      onclick={(e) => handleClick(e, copy)}
      onkeydown={(e) => handleKey(e, copy)}
    >
      {copy.eyebrow}
    </button>
  {/each}
</nav>
