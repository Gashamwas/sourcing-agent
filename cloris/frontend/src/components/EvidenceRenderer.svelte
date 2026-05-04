<script lang="ts" module>
  // EvidenceRenderer (Phase F Slice F8 / Ledger L10).
  //
  // Integration point for Phase 2's multimodal modules (Designer,
  // Photographer, Motion). Add new `kind` cases here; do NOT add
  // per-kind rendering inline at call sites — that's the drift this
  // substrate exists to prevent.
  //
  // Narrow scope at first: text + link render real content; image +
  // video render explicit placeholder rows so a future module can
  // ship a richer renderer without each calling surface needing to
  // re-thread the props.
  import type { Source } from "../lib/types";

  export type Evidence =
    | { kind: "text"; payload: string; source: Source; cite?: string }
    | { kind: "link"; href: string; label: string; source: Source }
    | { kind: "image"; src: string; alt: string; source: Source }
    | { kind: "video"; src: string; alt: string; source: Source };
</script>

<script lang="ts">
  import { sourceMeta } from "../lib/sources";

  let {
    evidence,
    ariaLabel = "Evidence"
  }: {
    evidence: readonly Evidence[];
    ariaLabel?: string;
  } = $props();
</script>

<ul class="evidence-renderer" aria-label={ariaLabel}>
  {#each evidence as item, i (i)}
    <li class={`evidence-row evidence-row--${item.kind}`} data-evidence-kind={item.kind}>
      <p class="evidence-row-eyebrow">{sourceMeta(item.source).label}</p>
      {#if item.kind === "text"}
        <p class="evidence-row-text">{item.payload}</p>
        {#if item.cite}
          <p class="evidence-row-cite"><em>{item.cite}</em></p>
        {/if}
      {:else if item.kind === "link"}
        <p class="evidence-row-link">
          <a
            class="evidence-row-link-anchor"
            href={item.href}
            target="_blank"
            rel="noopener noreferrer"
          >
            {item.label || item.href}
          </a>
        </p>
      {:else if item.kind === "image"}
        <p class="evidence-row-placeholder"><em>Image evidence — renderer ships in Phase 2.</em></p>
      {:else if item.kind === "video"}
        <p class="evidence-row-placeholder"><em>Video evidence — renderer ships in Phase 2.</em></p>
      {/if}
    </li>
  {/each}
</ul>
