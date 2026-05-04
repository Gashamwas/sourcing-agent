<script lang="ts">
  // StatusPillToggle — recruiter-overridden status switcher (Phase C, slice C3).
  //
  // The toggle lives next to Cloris's terminal_decision on the candidate-
  // detail page. Setting an override flips the displayed primary status to
  // the override (sentence-case Fraunces); Cloris's call is preserved as a
  // secondary smaller line. Clearing the override falls back to Cloris's
  // judgment as the primary.
  //
  // Allowed values mirror the API server's _ALLOWED_USER_STATUSES set;
  // any other string would 422. The component is presentational — the
  // parent owns the data and the patch handler.

  import type { CandidateUserStatus } from "../lib/types";
  import {
    statusToggleLabel,
    statusToggleClorisLabel,
    statusToggleClearLabel,
    statusToggleErrorLabel
  } from "../lib/copy";
  import { decisionLabel, decisionLabelClass } from "../lib/copy";

  let {
    userStatus,
    clorisCall,
    onChange,
    disabled = false,
    disabledReason = null
  }: {
    userStatus: string | null;
    clorisCall: string | null;
    onChange: (next: CandidateUserStatus | null) => Promise<void>;
    disabled?: boolean;
    disabledReason?: string | null;
  } = $props();

  const STATUSES: { value: CandidateUserStatus; label: string }[] = [
    { value: "shortlist", label: "Shortlist" },
    { value: "contacted", label: "Contacted" },
    { value: "parked", label: "Parked" },
    { value: "hidden", label: "Hidden" }
  ];

  let inFlight = $state<boolean>(false);
  let errorMessage = $state<string | null>(null);

  async function pick(next: CandidateUserStatus | null): Promise<void> {
    if (inFlight || disabled) return;
    inFlight = true;
    errorMessage = null;
    try {
      await onChange(next);
    } catch {
      errorMessage = statusToggleErrorLabel;
    } finally {
      inFlight = false;
    }
  }

  function isActive(value: CandidateUserStatus): boolean {
    return userStatus === value;
  }
</script>

<section class="status-toggle" aria-label={statusToggleLabel}>
  <p class="status-toggle-label">{statusToggleLabel}</p>
  <div class="status-toggle-row" role="radiogroup" aria-label={statusToggleLabel}>
    {#each STATUSES as status (status.value)}
      <button
        type="button"
        class={`status-toggle-button ${isActive(status.value) ? "status-toggle-button--active" : ""}`}
        aria-pressed={isActive(status.value)}
        disabled={inFlight || disabled}
        onclick={() => pick(isActive(status.value) ? null : status.value)}
      >
        {status.label}
      </button>
    {/each}
  </div>
  {#if userStatus !== null}
    <button
      type="button"
      class="status-toggle-clear"
      disabled={inFlight || disabled}
      onclick={() => pick(null)}
    >
      {statusToggleClearLabel}
    </button>
  {/if}
  {#if disabled && disabledReason !== null}
    <p class="status-toggle-disabled-note" aria-live="polite">{disabledReason}</p>
  {/if}
  {#if clorisCall !== null && userStatus !== null && !disabled}
    <p class={`status-toggle-cloris-call ${decisionLabelClass(clorisCall)}`}>
      {statusToggleClorisLabel}: {decisionLabel(clorisCall)}
    </p>
  {/if}
  {#if errorMessage !== null}
    <p class="status-toggle-error" role="alert" aria-live="polite">{errorMessage}</p>
  {/if}
</section>
