<!--
  VisualHunkCard — one principle's slice of a designer's vision-judgment
  rendered as an EditorialReviewCard.

  Designer Slice 6. Sibling of HunkCard.svelte (text-shaped reflection
  hunks). Both compose with the same EditorialReviewCard structural
  shell — kind eyebrow + section label + approve/skip toggle +
  rationale block + --terracotta left rule on approved.

  Per-principle shape:
    - Eyebrow: "VISUAL REVIEW" (mono-caps, R7-compliant)
    - Section: principle name (sentence-case)
    - Body: VisualReviewBeforeAfter renders the score chip + thumbnail
      strip + reasoning
    - Rationale: omitted (the per-principle reasoning IS the rationale;
      the EditorialReviewCard rationale block stays empty for visual
      cards)
    - Approve/skip toggle: per-principle accept/reject feedback that
      Slice 7's recruiter annotation flow consumes
-->
<script lang="ts">
  import EditorialReviewCard from "./EditorialReviewCard.svelte";
  import VisualReviewBeforeAfter from "./VisualReviewBeforeAfter.svelte";

  let {
    principleName,
    score,
    anchor,
    reasoning,
    images = [],
    anchorConsistencyPass = true,
    crossCheck = null,
    approved = true,
    onToggle,
    disabled = false,
  }: {
    principleName: string;
    score: number;
    anchor: string;
    reasoning: string;
    images?: Array<{
      id: number;
      url: string;
      thumbnailUrl?: string;
      source: string;
      projectTitle: string;
    }>;
    anchorConsistencyPass?: boolean;
    crossCheck?: {
      otherModel: string;
      otherScore: number;
      otherAnchor: string;
      otherReasoning: string;
    } | null;
    approved?: boolean;
    onToggle: (next: boolean) => void;
    disabled?: boolean;
  } = $props();
</script>

<EditorialReviewCard
  kindLabel="visual review"
  sectionLabel={principleName}
  kindClass="hunk-card-kind--visual-review"
  {approved}
  {onToggle}
  {disabled}
  rationale={null}
  ariaLabel={`${approved ? "Approved" : "Skipped"}: ${principleName} visual review`}
>
  <VisualReviewBeforeAfter
    {principleName}
    {score}
    {anchor}
    {reasoning}
    {images}
    {anchorConsistencyPass}
    {crossCheck}
  />
</EditorialReviewCard>
