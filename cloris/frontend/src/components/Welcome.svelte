<!--
  Welcome — Phase 0 ``apikey-ui`` + ``disclosure`` slices.

  First-launch surface that gates entry into Cloris on two things:

    1. Anthropic API key (the operational dependency — Cloris uses
       Claude for the heavy reading and writing).
    2. The recipient's acknowledgment of what Cloris will do on
       their Mac with their LinkedIn Recruiter session (the
       relational disclosure — see plan §5).

  Once both are recorded, ``GET /api/onboarding/status`` reports
  ``welcome_complete=true`` and the gate in App.svelte falls through
  to the home route. The recipient never sees this screen again
  unless they explicitly return (or a major version bump invalidates
  the acknowledgment, which is a later policy hook).

  Editorial register matches the rest of Cloris (cream paper,
  Fraunces serif title, italic Instrument-Serif deck, mono labels for
  the file paths). Specifically NOT the dashboard register — this is
  a deliberate "first contact" page, leaning on the same primitives
  the OnboardingFlow uses but with no resume-state, no chapter
  count, no "Picking up where you left off" cue.
-->
<script lang="ts">
  import {
    ApiError,
    postOnboardingAcknowledge,
    postOnboardingCredential,
    type OnboardingStatusResponse
  } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import { surfaceFadeIn } from "../lib/transitions";

  let {
    initial,
    onComplete
  }: {
    // Server-side onboarding snapshot at mount time. Lets the welcome
    // surface render the right initial state (e.g. acknowledgment
    // already recorded but key missing — partial progress).
    initial: OnboardingStatusResponse;
    // Called when the recipient successfully completes the welcome
    // flow. The parent (App.svelte) responds by re-rendering the
    // route table.
    onComplete: () => void;
  } = $props();

  let anthropicKey = $state<string>("");
  // Local mutable state seeded from the server snapshot at mount.
  // Once the welcome surface is on screen, the parent does not change
  // ``initial`` until ``onComplete`` (at which point this component
  // unmounts), so capturing the initial value here is intentional.
  let acknowledged = $state<boolean>(false);
  $effect(() => {
    acknowledged = initial.acknowledged;
  });
  let submitting = $state<boolean>(false);
  let errorMessage = $state<string | null>(null);

  // The recipient may already have entered an Anthropic key on a
  // prior aborted attempt. We don't prefill the input (we can't read
  // the key back from the server — we only know presence), but we
  // DO surface it as a hint so the recipient understands the box is
  // optional this time.
  const anthropicAlreadyPresent = $derived(initial.anthropic_present);

  // Continue is enabled iff:
  //   - the recipient typed a key OR Anthropic was already present from
  //     a prior attempt, AND
  //   - the acknowledgment box is checked.
  const canContinue = $derived(
    (anthropicKey.trim() !== "" || anthropicAlreadyPresent) && acknowledged
  );

  async function handleContinue(): Promise<void> {
    if (!canContinue || submitting) return;
    submitting = true;
    errorMessage = null;
    try {
      // Step 1: write the credential if the recipient typed one. We
      // do this even when ``anthropicAlreadyPresent`` is true if the
      // recipient typed a fresh value, so they can correct a typo'd
      // key from a prior attempt.
      const trimmed = anthropicKey.trim();
      if (trimmed !== "") {
        await postOnboardingCredential("anthropic_api_key", trimmed);
      }
      // Step 2: record the acknowledgment if not already done.
      // Idempotent on the server — re-acknowledging just bumps the
      // timestamp.
      await postOnboardingAcknowledge();
      onComplete();
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        const detail = err.detail as
          | { error?: string; message?: string }
          | undefined;
        if (detail?.error === "empty_credential_value") {
          errorMessage = "Cloris needs a non-empty key.";
        } else if (detail?.error === "unknown_credential_key") {
          errorMessage = "Cloris doesn't recognize that credential key.";
        } else {
          errorMessage = detail?.message ?? "Something went wrong filing that.";
        }
      } else {
        errorMessage = describeApiError(err, "Setting up Cloris");
      }
    } finally {
      submitting = false;
    }
  }
</script>

<main class="cloris-shell welcome-shell">
  <article class="welcome-page" in:surfaceFadeIn>
    <header class="welcome-header">
      <p class="surface-eyebrow surface-eyebrow--muted">FIRST CONTACT</p>
      <h1 class="welcome-headline">
        Welcome to <em>Cloris</em>.
      </h1>
      <hr class="section-rule" />
      <p class="section-deck">
        <em>Two things before Cloris gets to work.</em>
      </p>
    </header>

    <section class="welcome-section">
      <h2 class="welcome-section-title">First, your Anthropic key.</h2>
      <p class="welcome-section-deck">
        <em>
          Cloris uses Claude for the heavy reading and writing — judging
          candidates, drafting briefs, reading the market. Without it she
          can't think.
        </em>
      </p>
      <label class="welcome-field">
        <span class="welcome-field-prompt">
          <em>Paste your Anthropic API key.</em>
        </span>
        <input
          type="password"
          autocomplete="off"
          spellcheck="false"
          class="welcome-input"
          bind:value={anthropicKey}
          placeholder={anthropicAlreadyPresent
            ? "Already on file — paste a new value to replace it"
            : "sk-ant-…"}
        />
      </label>
      <p class="welcome-microcopy">
        <em>
          Cloris stores this on your Mac at <code>{initial.env_path}</code>
          (owner-readable only) and never sends it anywhere except
          Anthropic's API.
        </em>
      </p>
      {#if anthropicAlreadyPresent}
        <p class="welcome-microcopy welcome-microcopy--success">
          <em>A key is already on file. Leave the box blank to keep using it.</em>
        </p>
      {/if}
    </section>

    <section class="welcome-section">
      <h2 class="welcome-section-title">Then, what Cloris does on your machine.</h2>
      <p class="welcome-disclosure">
        <em>
          Cloris uses your Chrome to read and save candidates from your
          LinkedIn Recruiter account, at human pace. Cloris attaches to a
          separate Chrome window — not your everyday Chrome — waits for
          you to sign into LinkedIn once, and operates only when you
          explicitly start a search. Cloris does not type messages, send
          InMails, or change project settings on your behalf. Saves go
          into your real Recruiter projects.
        </em>
      </p>
      <label class="welcome-checkbox">
        <input type="checkbox" bind:checked={acknowledged} />
        <span>
          I understand and want Cloris to operate on my Recruiter account.
        </span>
      </label>
    </section>

    <footer class="welcome-footer">
      {#if errorMessage !== null}
        <p class="welcome-error" role="alert">{errorMessage}</p>
      {/if}
      <button
        type="button"
        class="onboarding-cta welcome-cta"
        disabled={!canContinue || submitting}
        onclick={handleContinue}
      >
        {#if submitting}
          Setting up…
        {:else}
          Continue with Cloris
        {/if}
      </button>
      <p class="welcome-microcopy welcome-microcopy--meta">
        <em>
          You can change either of these later from Settings.
        </em>
      </p>
    </footer>
  </article>
</main>
