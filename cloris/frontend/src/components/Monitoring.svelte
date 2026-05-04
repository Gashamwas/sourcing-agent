<script lang="ts">
  // Monitoring — the WAITING loader.
  //
  // One graphic (CRT TV with phosphor flicker, scanline, rabbit
  // ears), one anchor caption ("Waiting for Matlock…"). Use whenever
  // the recruiter is genuinely waiting for an opaque, leavable
  // backend operation: long market-research synthesis, slow LLM
  // calls the user can walk away from, anything where "come back
  // later" is the right mental model.
  //
  // Part of the four-kind loader contract (R19 revised). Sister
  // components — same shape, different kind:
  //
  //   Refining   → CREATING     → sewing needles + yarn
  //   Finding    → SEARCHING    → glasses + magnifier
  //   Monitoring → WAITING      → CRT TV (this file)
  //   Learning   → INITIALIZING → kettle + steam
  //
  // Cloris-pivot verb is **monitor**; scratched verb is **watch**
  // (per the strikethrough tagline canon). The CRT metaphor — tuning
  // in, settling in, waiting for the show — registers the WAITING
  // beat without making the user feel idle.
  //
  // Motion graphic lifted from gemini-v2.html (Zenith). Phosphor
  // warmth over a flat gradient: 1960s wood-cabinet illustration
  // with rabbit ears, screen flicker, stepped-noise overlay for
  // cathode glow, scanline sweeping top-to-bottom.

  import RotatingCaption from "./RotatingCaption.svelte";
  import { loaderAnchorWaiting } from "../lib/copy";
  import { useDelayedShow } from "../lib/minDisplay.svelte";

  type StageSize = "small" | "medium" | "large";

  let {
    size = "medium",
    captions = null,
    delayMs = 200
  }: {
    size?: StageSize;
    captions?: string | readonly string[] | null;
    // Anti-flashbang gate — see Finding.svelte for rationale.
    delayMs?: number;
  } = $props();

  // Anchor default: when no caption is passed, render the WAITING
  // anchor. Pass an explicit rotating set (loaderRotatingWaiting in
  // lib/copy.ts) for surfaces with provably long latency (reflection
  // market research) so the wait reads as a moment.
  const captionList: string[] = $derived(
    captions === null
      ? [loaderAnchorWaiting]
      : typeof captions === "string"
        ? [captions]
        : [...captions]
  );

  const decorative = $derived(captionList.length === 0);
  const ariaLabel = $derived(captionList[0] ?? null);
  const show = useDelayedShow(
    () => true,
    () => delayMs
  );
</script>

{#if show()}
<figure
  class={`monitoring-stage monitoring-stage--${size}`}
  aria-hidden={decorative ? "true" : undefined}
  aria-label={ariaLabel ?? undefined}
  role={decorative ? "presentation" : "figure"}
>
  <div class="monitoring-frame">
    <svg
      class="monitoring-svg"
      viewBox="0 0 100 80"
      xmlns="http://www.w3.org/2000/svg"
      role="presentation"
      focusable="false"
      overflow="visible"
    >
      <!-- Rabbit ears (the antennae). Two stems with peach-tipped balls
           — small mid-century touch. -->
      <path
        d="M 50,15 L 25,5 M 50,15 L 85,0"
        fill="none"
        stroke="var(--wood)"
        stroke-width="1.5"
        stroke-linecap="round"
      />
      <circle cx="25" cy="5" r="2" fill="var(--peach-deep)" />
      <circle cx="85" cy="0" r="2" fill="var(--peach-deep)" />

      <!-- Wood-cabinet body — offset shadow underlay, then primary fill
           with darker frame. -->
      <rect
        x="15"
        y="15"
        width="70"
        height="50"
        rx="4"
        fill="var(--wood-deep)"
        transform="translate(3, 3)"
        opacity="0.2"
      />
      <rect
        x="15"
        y="15"
        width="70"
        height="50"
        rx="4"
        fill="var(--wood)"
        stroke="var(--wood-deep)"
        stroke-width="2"
      />

      <!-- Tuning dial column on the right (dotted for analog feel +
           a mustard knob). -->
      <path
        d="M 75,25 L 75,55"
        stroke="var(--ink)"
        stroke-width="2"
        stroke-linecap="round"
        stroke-dasharray="2 4"
      />
      <circle cx="75" cy="25" r="3" fill="var(--mustard)" />

      <!-- Inner bezel + screen. Clipped so flicker + scanline + phosphor
           noise stay within the rounded screen rect. -->
      <rect x="22" y="22" width="42" height="36" rx="8" fill="var(--ink-soft)" />

      <defs>
        <clipPath id="monitoring-screen-clip">
          <rect x="25" y="25" width="36" height="30" rx="6" />
        </clipPath>
      </defs>

      <g clip-path="url(#monitoring-screen-clip)">
        <rect
          class="monitoring-screen"
          x="25"
          y="25"
          width="36"
          height="30"
        />
        <rect
          class="monitoring-phosphor"
          x="25"
          y="25"
          width="36"
          height="30"
        />
        <rect
          class="monitoring-scanline"
          x="25"
          y="25"
          width="36"
          height="4"
          fill="rgba(255,255,255,0.2)"
        />
        <rect
          x="25"
          y="25"
          width="36"
          height="30"
          fill="none"
          stroke="var(--cream)"
          stroke-width="4"
          opacity="0.3"
        />
      </g>

      <!-- Stubby legs at the bottom. -->
      <path
        d="M 25,65 L 20,75 M 75,65 L 80,75"
        fill="none"
        stroke="var(--wood)"
        stroke-width="2.5"
        stroke-linecap="round"
      />
    </svg>
  </div>

  {#if !decorative}
    <figcaption class="monitoring-caption">
      <RotatingCaption captions={captionList} />
    </figcaption>
  {/if}
</figure>
{/if}
