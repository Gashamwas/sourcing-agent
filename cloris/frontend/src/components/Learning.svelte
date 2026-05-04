<script lang="ts">
  // Learning — the INITIALIZING loader.
  //
  // One graphic (kettle + three steam puffs rising on staggered
  // curves), one anchor caption ("Firing up the kettle…"). Use
  // whenever Cloris is starting / booting / setting up: app launch
  // splash, intake boot, reflection-session boot, any "she's just
  // getting going" moment.
  //
  // Part of the four-kind loader contract (R19 revised). Sister
  // components — same shape, different kind:
  //
  //   Refining   → CREATING     → sewing needles + yarn
  //   Finding    → SEARCHING    → glasses + magnifier
  //   Monitoring → WAITING      → CRT TV
  //   Learning   → INITIALIZING → kettle + steam (this file)
  //
  // Cloris-pivot verb is **learn**; scratched verb is **brew** (per
  // the strikethrough tagline canon). The kettle metaphor — heating,
  // steaming, preparing — registers as the start-of-something beat.
  //
  // Motion graphic lifted from gemini-v2.html. Volumetric steam puffs
  // rise on staggered easing curves, each puff scaling and rotating
  // gently as it fades. Offset print registration — fills sit slightly
  // detached from the hand-drawn linework so the kettle reads as a
  // mid-century illustration, not a modern flat icon.

  import RotatingCaption from "./RotatingCaption.svelte";
  import { loaderAnchorInitializing } from "../lib/copy";
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

  // Anchor default: when no caption is passed, render the
  // INITIALIZING anchor. Pass an explicit rotating set
  // (loaderRotatingInitializing in lib/copy.ts) for surfaces with
  // provably long latency (App splash 5s) so the wait reads as a
  // moment, not a frozen string.
  const captionList: string[] = $derived(
    captions === null
      ? [loaderAnchorInitializing]
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
  class={`learning-stage learning-stage--${size}`}
  aria-hidden={decorative ? "true" : undefined}
  aria-label={ariaLabel ?? undefined}
  role={decorative ? "presentation" : "figure"}
>
  <div class="learning-frame">
    <svg
      class="learning-svg"
      viewBox="0 0 160 140"
      xmlns="http://www.w3.org/2000/svg"
      role="presentation"
      focusable="false"
      overflow="visible"
    >
      <!-- Three steam puffs, staggered. Each scales and rotates on
           rise; the second + third have animation-delay so the cloud
           billows continuously. -->
      <g class="learning-steam">
        <g class="learning-steam-puff">
          <path
            class="learning-steam-fill"
            d="M 72,55 C 65,45 78,40 80,45 C 80,30 98,35 94,48 C 105,45 105,60 95,58 C 95,70 75,65 72,55 Z"
          />
          <path
            class="learning-steam-line"
            d="M 72,55 C 65,45 78,40 80,45 C 80,30 98,35 94,48 C 105,45 105,60 95,58 C 95,70 75,65 72,55 Z"
          />
        </g>
        <g class="learning-steam-puff learning-steam-puff--2">
          <path
            class="learning-steam-fill"
            d="M 78,58 C 72,52 75,40 82,45 C 80,32 98,32 95,42 C 105,40 108,55 98,58 C 95,68 80,68 78,58 Z"
          />
          <path
            class="learning-steam-line"
            d="M 78,58 C 72,52 75,40 82,45 C 80,32 98,32 95,42 C 105,40 108,55 98,58 C 95,68 80,68 78,58 Z"
          />
        </g>
        <g class="learning-steam-puff learning-steam-puff--3">
          <path
            class="learning-steam-fill"
            d="M 74,52 C 68,42 80,32 86,38 C 88,25 102,35 94,48 C 106,50 100,62 92,60 C 85,68 70,62 74,52 Z"
          />
          <path
            class="learning-steam-line"
            d="M 74,52 C 68,42 80,32 86,38 C 88,25 102,35 94,48 C 106,50 100,62 92,60 C 85,68 70,62 74,52 Z"
          />
        </g>
      </g>

      <!-- Kettle body — mustard fill with offset print registration
           (fill nudged 3px,2px from the linework). -->
      <path
        d="M 45,120 C 42,90 55,80 70,80 L 105,80 C 120,80 133,90 130,120 C 128,135 47,135 45,120 Z"
        fill="var(--mustard)"
        transform="translate(3, 2)"
        opacity="0.8"
      />
      <g
        fill="none"
        stroke="var(--wood)"
        stroke-width="2.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path
          d="M 45,120 C 42,90 55,80 70,80 L 105,80 C 120,80 133,90 130,120 C 128,135 47,135 45,120 Z"
        />
        <!-- Spout -->
        <path d="M 48,105 C 30,105 20,90 20,80 C 25,78 30,82 30,85 C 30,95 40,100 46,100" />
        <!-- Lid base + handle bar + knob -->
        <path d="M 72,80 C 72,75 103,75 103,80" />
        <circle cx="87.5" cy="72" r="4" fill="var(--wood)" />
        <path d="M 60,80 C 60,50 115,50 115,80" />
        <!-- Faint heat lines on the kettle's right -->
        <path d="M 115,125 C 120,115 122,100 120,90" stroke-width="1.5" opacity="0.5" />
        <path d="M 122,120 C 125,110 126,102 125,95" stroke-width="1.5" opacity="0.3" />
      </g>
    </svg>
  </div>

  {#if !decorative}
    <figcaption class="learning-caption">
      <RotatingCaption captions={captionList} />
    </figcaption>
  {/if}
</figure>
{/if}
