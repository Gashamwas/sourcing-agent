<script lang="ts">
  // Finding — the SEARCHING loader.
  //
  // One graphic (glasses + magnifier hunting through the frame), one
  // anchor caption ("Looking for my glasses…"). Use whenever Cloris is
  // fetching something that already exists: a brief, a run report, a
  // candidate, a workspace, a settings index, a reconciliation list.
  //
  // Part of the four-kind loader contract (R19 revised). Sister
  // components — same shape, different kind:
  //
  //   Refining   → CREATING     → sewing needles + yarn
  //   Finding    → SEARCHING    → glasses + magnifier (this file)
  //   Monitoring → WAITING      → CRT TV
  //   Learning   → INITIALIZING → kettle + steam
  //
  // The captions default to the SEARCHING anchor when the caller
  // passes nothing; pass an explicit caption (string or array) only
  // when a long-running surface earns motion in the copy. Random
  // graphic dispatch is GONE — every mount renders the same glasses
  // SVG so the recruiter learns the kind from both the graphic and
  // the caption working together.

  import RotatingCaption from "./RotatingCaption.svelte";
  import { loaderAnchorSearching } from "../lib/copy";
  import { useDelayedShow } from "../lib/minDisplay.svelte";

  type StageSize = "small" | "medium" | "large";

  let {
    size = "medium",
    captions = null,
    finishing = false,
    delayMs = 200
  }: {
    size?: StageSize;
    captions?: string | readonly string[] | null;
    finishing?: boolean;
    // Anti-flashbang gate: don't render at all unless this loader has
    // been mounted (i.e., the caller's gating predicate has been true)
    // for at least delayMs. Default 200ms catches fast localhost
    // fetches without ever showing a loader; genuinely-slow operations
    // (>200ms) cross the threshold and the loader appears cleanly.
    // See lib/minDisplay.svelte.ts for the rationale on 200 vs other
    // values. Callers can override per-surface (e.g., 0 for tests).
    delayMs?: number;
  } = $props();

  // Anchor default: when no caption is passed, render the SEARCHING
  // anchor so the loader is never decorative for an in-flight fetch.
  // Callers that want a true decorative state pass an empty array
  // explicitly (matches Refining / Learning / Monitoring semantics).
  const captionList: string[] = $derived(
    captions === null
      ? [loaderAnchorSearching]
      : typeof captions === "string"
        ? [captions]
        : [...captions]
  );

  const decorative = $derived(captionList.length === 0);
  const ariaLabel = $derived(captionList[0] ?? null);
  // useDelayedShow(() => true) is "wait delayMs after mount, then
  // show — as long as we're still mounted." If the caller unmounts
  // this Finding (because the operation completed) before delayMs,
  // the timer cancels and nothing ever rendered.
  // delayMs passed as a getter so the prop reads reactively without
  // Svelte 5's initial-value-capture warning.
  const show = useDelayedShow(
    () => true,
    () => delayMs
  );
</script>

{#if show()}
<figure
  class={`finding-stage finding-stage--${size} ${finishing ? "finding-stage--finishing" : ""}`}
  aria-hidden={decorative ? "true" : undefined}
  aria-label={ariaLabel ?? undefined}
  role={decorative ? "presentation" : "figure"}
>
  <div class="finding-frame">
    <svg
      class="finding-svg"
      viewBox="0 0 200 120"
      xmlns="http://www.w3.org/2000/svg"
      role="presentation"
      focusable="false"
      overflow="visible"
    >
      <path d="M 10,90 Q 100,92 190,88" fill="none" stroke="var(--wood)" stroke-width="1.5" stroke-dasharray="2 6" stroke-linecap="round" opacity="0.5"/>

      <g class="finding-target">
        <path d="M 90,60 C 90,75 110,75 110,60 C 105,50 95,50 90,60 M 118,60 C 118,75 138,75 138,60 C 133,50 123,50 118,60" fill="var(--peach-deep)" transform="translate(2, 2)" opacity="0.6"/>
        <g fill="none" stroke="var(--wood)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M 90,60 C 90,75 110,75 110,60 C 105,48 95,48 90,60 Z"/>
          <path d="M 118,60 C 118,75 138,75 138,60 C 133,48 123,48 118,60 Z"/>
          <path d="M 110,55 C 113,53 115,53 118,55"/>
          <path d="M 90,55 C 80,50 75,55 75,65"/>
          <path d="M 138,55 C 145,52 150,55 155,65"/>
        </g>
      </g>

      <g class="finding-magnifier">
        <circle cx="30" cy="30" r="24" fill="var(--cream)" fill-opacity="0.5" stroke="var(--cream-deep)" stroke-width="4"/>
        <path d="M 30,6 C 45,6 54,15 54,30" fill="none" stroke="var(--cream)" stroke-width="3" opacity="0.8" stroke-linecap="round"/>
        <circle cx="30" cy="30" r="24" fill="none" stroke="var(--wood)" stroke-width="2.5"/>
        <path d="M 47,47 L 75,75" stroke="var(--wood)" stroke-width="6" stroke-linecap="round"/>
        <path d="M 47,47 L 75,75" stroke="var(--peach-deep)" stroke-width="2" stroke-linecap="round" transform="translate(-1, -1)"/>
      </g>
    </svg>
  </div>

  {#if !decorative}
    <figcaption class="finding-caption">
      <RotatingCaption captions={captionList} />
    </figcaption>
  {/if}
</figure>
{/if}
