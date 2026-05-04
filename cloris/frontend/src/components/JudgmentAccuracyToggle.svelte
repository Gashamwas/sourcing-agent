<script lang="ts">
  // JudgmentAccuracyToggle — closed-loop calibration signal switcher.
  // Phase D Slice D6 (Ledger L1).
  //
  // Lives on the candidate-detail page below the StatusPillToggle. Asks
  // the recruiter to *calibrate Cloris's judgment* — distinct from
  // setting a pipeline action (which is what user_status is for). The
  // two signals are schema-distinct from C-bis Slice 0.5; the visual
  // register here keeps them perceptually distinct too.
  //
  // Allowed values mirror the API server's _ALLOWED_JUDGMENT_ACCURACIES
  // set; any other string would 422. The component is presentational —
  // the parent owns the data and the patch handler.

  import type { CandidateJudgmentAccuracy } from "../lib/types";
  import {
    judgmentToggleLabel,
    judgmentToggleClearLabel,
    judgmentToggleErrorLabel
  } from "../lib/copy";

  let {
    judgmentAccuracy = null,
    onChange,
    disabled = false,
    disabledReason = null
  }: {
    // Defensive default: legacy API responses (pre Phase C-bis 0.5)
    // omit the field entirely; we treat that as "no calibration set"
    // so the Clear button doesn't render against a phantom value.
    judgmentAccuracy?: string | null | undefined;
    onChange: (next: CandidateJudgmentAccuracy | null) => Promise<void>;
    disabled?: boolean;
    disabledReason?: string | null;
  } = $props();

  // Phase D D6: ship the three primary signals first. The schema accepts
  // five values (overstated_depth / understated_depth additionally) but
  // the UI surface starts narrow — the recruiter says "useful / wrong /
  // off-rubric" before refining "wrong" into a depth nuance. Phase G or
  // H may extend; for now the schema captures more than the UI.
  // Plan Finding 18: "Off rubric" was calibration vocabulary (the
  // marquee trial recruiter would have to guess what it meant);
  // "Doesn't fit the brief" reads as recruiter-language while the
  // schema value (off_rubric) stays untouched.
  const ACCURACIES: { value: CandidateJudgmentAccuracy; label: string }[] = [
    { value: "useful", label: "Useful" },
    { value: "wrong", label: "Wrong" },
    { value: "off_rubric", label: "Doesn't fit the brief" }
  ];

  let inFlight = $state<boolean>(false);
  let errorMessage = $state<string | null>(null);

  async function pick(next: CandidateJudgmentAccuracy | null): Promise<void> {
    if (inFlight || disabled) return;
    inFlight = true;
    errorMessage = null;
    try {
      await onChange(next);
    } catch {
      errorMessage = judgmentToggleErrorLabel;
    } finally {
      inFlight = false;
    }
  }

  function isActive(value: CandidateJudgmentAccuracy): boolean {
    return judgmentAccuracy === value;
  }
</script>

<section class="judgment-toggle" aria-label={judgmentToggleLabel}>
  <p class="judgment-toggle-label">{judgmentToggleLabel}</p>
  <!-- Plan Finding 18: dropped the help line
       ("Tell Cloris what to learn from on the next run.") — process-
       narration about Cloris's training loop the recruiter doesn't
       track. The buttons themselves are the action. -->
  <div class="judgment-toggle-row" role="radiogroup" aria-label={judgmentToggleLabel}>
    {#each ACCURACIES as accuracy (accuracy.value)}
      <button
        type="button"
        class={`judgment-toggle-button ${isActive(accuracy.value) ? "judgment-toggle-button--active" : ""}`}
        aria-pressed={isActive(accuracy.value)}
        disabled={inFlight || disabled}
        onclick={() => pick(isActive(accuracy.value) ? null : accuracy.value)}
      >
        {accuracy.label}
      </button>
    {/each}
  </div>
  {#if judgmentAccuracy !== null}
    <button
      type="button"
      class="judgment-toggle-clear"
      disabled={inFlight || disabled}
      onclick={() => pick(null)}
    >
      {judgmentToggleClearLabel}
    </button>
  {/if}
  {#if disabled && disabledReason !== null}
    <p class="judgment-toggle-disabled-note" aria-live="polite">{disabledReason}</p>
  {/if}
  {#if errorMessage !== null}
    <p class="judgment-toggle-error" role="alert" aria-live="polite">{errorMessage}</p>
  {/if}
</section>
