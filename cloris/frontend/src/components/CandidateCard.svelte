<script lang="ts">
  // CandidateCard — one tile in the Workspace grid (Phase C, slice C2).
  //
  // Renders the recipe-card view of a saved candidate: name, save reason
  // (italic prose, the Cloris-voice "why"), decision class + confidence,
  // and a stamp for when Cloris last touched the row. The whole card is
  // a link to the candidate-detail page; clicks anywhere route through.
  //
  // Visual register: cream-deeper card on cream body, peach-deep accent
  // for the decision pill. Designed to fit a 2-column grid at 1280px and
  // collapse to 1 column under 720px (scoped via CSS, not props).

  import type { CandidateCardSummary } from "../lib/types";
  import { sourceMeta } from "../lib/sources";
  import {
    candidateCardSaveReasonLabel,
    candidateCardLastSeenLabel,
    decisionLabel,
    decisionLabelClass
  } from "../lib/copy";

  let {
    card,
    briefId
  }: {
    card: CandidateCardSummary;
    briefId: string;
  } = $props();

  function href(): string {
    return `#/candidate/${encodeURIComponent(briefId)}/${card.candidate_id}`;
  }

  function lastSeenShort(): string | null {
    if (!card.last_seen_at) return null;
    const parsed = new Date(card.last_seen_at);
    if (Number.isNaN(parsed.getTime())) return card.last_seen_at;
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric"
    }).format(parsed);
  }
</script>

<a class="candidate-card" data-candidate-id={card.candidate_id} href={href()}>
  <div class="candidate-card-header">
    {#if card.user_status !== null}
      <span class="candidate-card-user-status">{card.user_status}</span>
    {:else}
      <span class={`candidate-card-decision ${decisionLabelClass(card.terminal_decision)}`}>{decisionLabel(card.terminal_decision)}</span>
    {/if}
    <!-- Plan Finding 11: confidence percentage removed from row-level
         rendering. LLM-derived confidence is the wrong instrument for
         row-level prioritization (false precision); the "She flagged
         this" badge on CandidateDetail carries the high-confidence
         signal that earns the recruiter's attention. -->
  </div>
  <h3 class="candidate-card-name">
    <!-- Phase F Slice F6: replaces D10's single-source pill with a
         multi-source list when this person aggregates 2+ sources via
         F3's identity resolver. The primary source's pill renders
         first; cross-source sources follow in the order returned by
         the read model. -->
    <span class="candidate-card-source-pills">
      <span class={`candidate-card-source-pill candidate-card-source-pill--${card.source}`} aria-label={sourceMeta(card.source).label}>
        {sourceMeta(card.source).pillLabel}
      </span>
      {#each card.cross_source_links ?? [] as link (`${link.source}/${link.state_key}/${link.candidate_id}`)}
        <span
          class={`candidate-card-source-pill candidate-card-source-pill--${link.source}`}
          aria-label={sourceMeta(link.source).label}
          title={link.describe}
        >
          {sourceMeta(link.source).pillLabel}
        </span>
      {/each}
    </span>
    {card.display_name || "Unknown"}
  </h3>
  {#if card.save_reason !== null}
    <p class="candidate-card-save-reason">
      <span class="candidate-card-save-reason-label">{candidateCardSaveReasonLabel}</span>
      <span class="candidate-card-save-reason-body">{card.save_reason}</span>
    </p>
  {/if}
  {#if lastSeenShort() !== null}
    <p class="candidate-card-footer">
      <span class="candidate-card-footer-label">{candidateCardLastSeenLabel}</span>
      <span class="candidate-card-footer-value">{lastSeenShort()}</span>
    </p>
  {/if}
</a>
