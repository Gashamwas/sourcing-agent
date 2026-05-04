<script lang="ts">
  // Refining — the CREATING loader.
  //
  // One graphic (sewing needles + yarn ticking through fabric), one
  // anchor caption ("Stitching something special…"). Use whenever
  // Cloris is producing something: a sourcing run in flight, a brief
  // iterating, a market artifact rebuilding, a brief diff being
  // synthesized.
  //
  // Part of the four-kind loader contract (R19 revised). Sister
  // components — same shape, different kind:
  //
  //   Refining   → CREATING     → sewing needles + yarn (this file)
  //   Finding    → SEARCHING    → glasses + magnifier
  //   Monitoring → WAITING      → CRT TV
  //   Learning   → INITIALIZING → kettle + steam
  //
  // Cloris-pivot verb is **refine**; scratched verb is **knit** (per
  // the strikethrough tagline canon). On-thesis with Chapter 5 of
  // How Cloris Works ("The Learning"): each pass refines the brief
  // and the system's understanding.
  //
  // Motion graphic lifted from gemini-v2.html. Physical rhythm: a
  // sharp two-step keyframe on the needles to mimic the click-clack
  // of knitting; the yarn pulls taut through the pull animation
  // rather than being "drawn in" with stroke-dashoffset.

  import RotatingCaption from "./RotatingCaption.svelte";
  import { loaderAnchorCreating } from "../lib/copy";
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
    // 200ms catches fast localhost ops without ever showing.
    delayMs?: number;
  } = $props();

  // Anchor default: when no caption is passed, render the CREATING
  // anchor so the loader is never decorative for an in-flight op.
  // Callers that want a true decorative state (empty-state usage)
  // pass an empty array explicitly.
  const captionList: string[] = $derived(
    captions === null
      ? [loaderAnchorCreating]
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
  class={`refining-stage refining-stage--${size}`}
  aria-hidden={decorative ? "true" : undefined}
  aria-label={ariaLabel ?? undefined}
  role={decorative ? "presentation" : "figure"}
>
  <div class="refining-frame">
    <svg
      class="refining-svg"
      viewBox="0 0 220 140"
      xmlns="http://www.w3.org/2000/svg"
      role="presentation"
      focusable="false"
      overflow="visible"
    >
      <!-- Yarn ball, lower-right. Mustard with offset shadow + soft
           stitched detailing. Sits at rest; the action is at the
           fabric end. -->
      <g transform="translate(160, 95)">
        <circle
          cx="0"
          cy="0"
          r="28"
          fill="var(--mustard)"
          opacity="0.8"
          transform="translate(2, 2)"
        />
        <circle cx="0" cy="0" r="28" fill="none" stroke="var(--wood)" stroke-width="2" />
        <path
          d="M -20,-10 C 0,-30 15,10 25,-5"
          fill="none"
          stroke="var(--wood)"
          stroke-width="1.5"
          opacity="0.5"
        />
        <path
          d="M -25,5 C -10,15 5,-10 20,15"
          fill="none"
          stroke="var(--wood)"
          stroke-width="1.5"
          opacity="0.5"
        />
      </g>

      <!-- Yarn thread pulling toward the needles. The dasharray + offset
           creates the "pull taut" beat each cycle. -->
      <path
        class="refining-yarn"
        d="M 140,80 Q 120,110 80,60"
        fill="none"
        stroke="var(--peach-deep)"
        stroke-width="2.5"
        stroke-linecap="round"
      />

      <!-- Fabric block — peach with offset shadow + horizontal stitch
           detail. The fabric stays still; what moves is the yarn + the
           needles. -->
      <g transform="translate(30, 60)">
        <path
          d="M 0,0 Q 10,-5 20,0 Q 30,-5 40,0 L 40,50 L 0,50 Z"
          fill="var(--peach-deep)"
          transform="translate(2, 2)"
          opacity="0.7"
        />
        <path
          d="M 0,0 Q 10,-5 20,0 Q 30,-5 40,0 L 40,50 L 0,50 Z"
          fill="none"
          stroke="var(--wood)"
          stroke-width="2"
          stroke-linejoin="round"
        />
        <path
          d="M 5,10 L 15,10 M 25,10 L 35,10 M 5,20 L 15,20 M 25,20 L 35,20 M 5,30 L 15,30 M 25,30 L 35,30"
          stroke="var(--wood)"
          stroke-width="1.5"
          stroke-linecap="round"
          opacity="0.4"
        />
      </g>

      <!-- Needle 2 (back). Sharp two-step bezier rhythm, slight
           translation on the click. -->
      <g class="refining-needle-2">
        <line
          x1="45"
          y1="95"
          x2="90"
          y2="35"
          stroke="var(--wood)"
          stroke-width="4"
          stroke-linecap="round"
        />
        <circle cx="45" cy="95" r="4" fill="var(--wood-deep)" />
        <line
          x1="45"
          y1="95"
          x2="90"
          y2="35"
          stroke="var(--cream)"
          stroke-width="1"
          stroke-linecap="round"
          opacity="0.5"
          transform="translate(-1, 0)"
        />
      </g>

      <!-- Needle 1 (front). Counter-rotating click for the click-clack
           effect. -->
      <g class="refining-needle-1">
        <line
          x1="85"
          y1="95"
          x2="40"
          y2="35"
          stroke="var(--wood)"
          stroke-width="4"
          stroke-linecap="round"
        />
        <circle cx="85" cy="95" r="4" fill="var(--wood-deep)" />
        <line
          x1="85"
          y1="95"
          x2="40"
          y2="35"
          stroke="var(--cream)"
          stroke-width="1"
          stroke-linecap="round"
          opacity="0.5"
          transform="translate(-1, 0)"
        />
      </g>
    </svg>
  </div>

  {#if !decorative}
    <figcaption class="refining-caption">
      <RotatingCaption captions={captionList} />
    </figcaption>
  {/if}
</figure>
{/if}
