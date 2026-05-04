<script lang="ts">
  // StrikethroughTagline — Cloris's master tagline pattern (V4-A canon).
  //
  // "Just like Grandma used to ~~make~~ source." A grandmotherly verb is
  // struck through with a hand-drawn ink line and replaced by a Cloris-
  // pivot verb in Instrument Serif italic terracotta. Lifted from the V4
  // tagline mockup at /Users/sam.vangelos/Downloads/tagline-v4.html;
  // V4-A is the canon (single ink pass; reads as "Cloris drew one
  // confident line through it"). V4-B + V4-C live in the mockup if we
  // ever want a heavier pass.
  //
  // Composition rule (per the motion+tagline synthesis): this is the
  // SYSTEM-LEVEL tagline, not a per-loader caption. It belongs on the
  // homescreen empty state, the splash, and any other low-frequency
  // brand moment. The four loaders (Finding / Refining / Learning /
  // Monitoring) carry their own functional captions, NOT this tagline.
  //
  // Three sizes: small (footer-style; rare), medium (homescreen empty
  // state default), large (splash / first-run hero).

  type TaglineSize = "small" | "medium" | "large";

  let {
    head = "Just like Grandma used to",
    scratched = "make",
    pivot = "source",
    tail = "",
    size = "medium"
  }: {
    head?: string;
    scratched?: string;
    pivot?: string;
    tail?: string;
    size?: TaglineSize;
  } = $props();
</script>

<p
  class={`strikethrough-tagline strikethrough-tagline--${size}`}
  aria-label={`${head} ${pivot}${tail}`}
>
  <span class="strikethrough-tagline-head">{head}</span>
  <span class="strikethrough-tagline-strike" aria-hidden="true">
    {scratched}
    <svg class="strike-x" viewBox="0 0 100 100" preserveAspectRatio="none" focusable="false">
      <!-- Two hand-drawn diagonal strokes forming an analog X -->
      <path
        d="M 8 12 Q 25 30, 48 52 T 92 90"
        stroke="var(--peach-deep)"
        stroke-width="8"
        fill="none"
        stroke-linecap="round"
        opacity="0.85"
      />
      <path
        d="M 88 8 Q 70 28, 50 50 T 10 94"
        stroke="var(--peach-deep)"
        stroke-width="7"
        fill="none"
        stroke-linecap="round"
        opacity="0.75"
      />
    </svg>
  </span>
  <span class="strikethrough-tagline-pivot">{pivot}</span>
  <span class="strikethrough-tagline-tail" aria-hidden="true">{tail}</span>
</p>
