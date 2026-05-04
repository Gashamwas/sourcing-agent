<script lang="ts">
  // RotatingCaption — fades through a list of captions on a steady loop.
  //
  // Used by the loader components (CrochetStage, GlassesFinder) so a long
  // operation reads as a real moment with Cloris, not a frozen string.
  // The pattern is lifted from the brand-spec component lab's glasses-
  // finder loader (see /Users/sam.vangelos/Downloads/cloris-components.html
  // lines 1383-1401): three lines, ~1.6s cadence, soft cross-fade.
  //
  // Single-caption back-compat:
  //   - Pass `captions={['just one line']}` and the rotation halts; the
  //     caption renders flat. Equivalent to the old static caption prop.
  //
  // Reduced-motion: the first caption holds for the duration. The user
  // still sees a label; we don't strobe text into a vestibular trigger.
  //
  // Accessibility: the wrapper is a <span> with aria-live="polite" so the
  // currently-shown caption is announced when it changes, but only when
  // motion is allowed (reduced-motion users get a single announcement).

  import { onDestroy, onMount } from "svelte";

  let {
    captions,
    intervalMs = 1666,
    fadeMs = 380
  }: {
    captions: readonly string[];
    intervalMs?: number;
    fadeMs?: number;
  } = $props();

  let index = $state<number>(0);
  let visible = $state<boolean>(true);

  // Detect reduced-motion preference once on mount. We intentionally do
  // not subscribe to changes — if the user toggles preferences mid-session,
  // a refresh is fine; the rotation is decorative and we don't need to
  // hot-swap behavior. It's $state because the template reads it for
  // aria-live, and svelte-check would warn otherwise.
  let prefersReducedMotion = $state<boolean>(false);

  let timer: ReturnType<typeof setInterval> | null = null;

  onMount(() => {
    if (typeof window !== "undefined" && window.matchMedia) {
      prefersReducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
      ).matches;
    }

    if (prefersReducedMotion) return;
    if (captions.length <= 1) return;

    timer = setInterval(() => {
      visible = false;
      window.setTimeout(() => {
        index = (index + 1) % captions.length;
        visible = true;
      }, fadeMs);
    }, intervalMs);
  });

  onDestroy(() => {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  });
</script>

<span
  class="rotating-caption"
  class:rotating-caption--hidden={!visible}
  style:--rotating-caption-fade-ms={`${fadeMs}ms`}
  aria-live={prefersReducedMotion || captions.length <= 1 ? "off" : "polite"}
>
  {captions[index]}
</span>
