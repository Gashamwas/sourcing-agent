<!--
  VisualReviewBeforeAfter — content primitive for the HITL visual
  review surface. Sibling of BriefChangeBeforeAfter (text-shaped) for
  Designer Slice 6.

  Renders one principle's slice of a designer's vision-judgment:
    - Score chip (0/3, 1/3, 2/3, 3/3) with anchor name beneath
    - Thumbnail strip — the 1-3 images that informed this principle's
      score (click to expand to full-size in a modal — Slice 7 wires
      the modal; this slice ships the strip + URL provenance)
    - Reasoning prose (italic Instrument Serif, recruiter voice)
    - Anchor-drift caveat when Layer 3 of the hallucination guard
      cascade marked the principle as `anchor_consistency_pass=false`
    - Cross-check disagreement marker (Slice 8 populates;
      this slice renders the placeholder when present)

  Slice-6 scope: rendering only. The recruiter's "Misrepresentative"
  flag per-thumbnail (Slice 7) hooks into the same thumbnail strip
  via a per-thumbnail click handler the parent will inject.
-->
<script lang="ts">
  let {
    principleName,
    score,
    anchor,
    reasoning,
    images = [],
    anchorConsistencyPass = true,
    crossCheck = null,
  }: {
    principleName: string;
    /** 0-3 — score is mapped from the rubric's 4-tier anchor scale
     *  (bad / okay / good / excellent). The chip renders score/3. */
    score: number;
    /** Anchor name string — "bad" | "okay" | "good" | "excellent" —
     *  shown sentence-case beneath the chip. */
    anchor: string;
    /** Per-principle reasoning prose (italic Instrument Serif). */
    reasoning: string;
    /** Subset of input images that informed this principle's score.
     *  The orchestrator passes only the IDs the model cited, so the
     *  strip is naturally bounded (typically 1-3 thumbnails). */
    images?: Array<{
      id: number;
      url: string;
      thumbnailUrl?: string;
      source: string;
      projectTitle: string;
    }>;
    /** False when Layer 3 of the hallucination guard fired for this
     *  principle. Surfaces a small "model anchor drift" caveat. */
    anchorConsistencyPass?: boolean;
    /** Slice 8: cross-check disagreement payload. When non-null,
     *  renders the "MODELS DISAGREE" eyebrow with both verdicts
     *  side-by-side. */
    crossCheck?: {
      otherModel: string;
      otherScore: number;
      otherAnchor: string;
      otherReasoning: string;
    } | null;
  } = $props();

  let anchorDisplay = $derived(anchor.charAt(0).toUpperCase() + anchor.slice(1));
</script>

<section class="visual-review">
  <header class="visual-review-header">
    <span class="visual-review-principle">{principleName}</span>
    <span class="visual-review-score-chip">
      <span class="visual-review-score">{score}/3</span>
      <span class="visual-review-anchor">{anchorDisplay}</span>
    </span>
  </header>

  {#if crossCheck !== null}
    <p class="visual-review-cross-check-eyebrow">Models disagree</p>
    <div class="visual-review-cross-check">
      <span>
        gemini-2.5-pro: {score}/3 ({anchorDisplay})
      </span>
      <span>
        {crossCheck.otherModel}: {crossCheck.otherScore}/3 ({crossCheck.otherAnchor})
      </span>
    </div>
  {/if}

  {#if images.length > 0}
    <div class="visual-review-thumbnail-strip">
      {#each images as image (image.id)}
        <figure class="visual-review-thumbnail">
          <img
            src={image.thumbnailUrl ?? image.url}
            alt={image.projectTitle || `image_id ${image.id}`}
            loading="lazy"
            class="visual-review-thumbnail-img"
          />
          <figcaption class="visual-review-thumbnail-caption">
            <span class="visual-review-thumbnail-source">{image.source}</span>
            {#if image.projectTitle}
              <span class="visual-review-thumbnail-title">{image.projectTitle}</span>
            {/if}
          </figcaption>
        </figure>
      {/each}
    </div>
  {/if}

  <p class="visual-review-reasoning">
    <em>{reasoning}</em>
  </p>

  {#if !anchorConsistencyPass}
    <p class="visual-review-anchor-drift">
      <em>
        Cloris flagged this score as drifting from the anchor definition;
        recruiter judgment carries.
      </em>
    </p>
  {/if}
</section>
