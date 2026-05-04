<!--
  LinkedInProjectEditor — Path 3 trial slice.

  Single component, three consumers (OnboardingFlow, BriefDetail,
  LaunchForm). The recruiter pastes a Recruiter project URL; we parse
  the project_id client-side via the same regex linkedin/browser.py:198
  uses, then call the caller-supplied `onSave`. Each consumer wires its
  own write path:
    - OnboardingFlow → updateStateField (debounced PATCH on intake)
    - BriefDetail   → putBrief on the loaded BriefDetailResponse
    - LaunchForm    → putBrief by brief_id, then re-probe readiness

  Editorial register matches BriefDetail/OnboardingFlow surfaces:
  Fraunces inputs, Instrument Serif italic prompts, JetBrains Mono
  for project-id metadata. PUT never sees malformed input — parse-time
  validation closes the silent-acceptance failure mode.
-->
<script lang="ts">
  import { untrack } from "svelte";
  import { parseLinkedInProjectUrl, type ParsedLinkedInProject } from "../lib/linkedinProject";

  let {
    currentProjectId = null,
    currentProjectName = null,
    onSave,
    onClear = null,
    compact = false,
    placeholder = "https://www.linkedin.com/talent/hire/<digits>/discover/recruiterSearch",
    label = "Paste your Recruiter project URL.",
    saveLabel = "Save",
    changeLabel = "Change"
  }: {
    currentProjectId?: string | null;
    currentProjectName?: string | null;
    onSave: (parsed: ParsedLinkedInProject) => Promise<void>;
    onClear?: (() => Promise<void>) | null;
    compact?: boolean;
    placeholder?: string;
    label?: string;
    saveLabel?: string;
    changeLabel?: string;
  } = $props();

  // Initial editing mode is "open the form when there's no value yet,
  // show display when there is." After mount, the flag is purely
  // user-driven (Change / Cancel / save success). The template's
  // conditional render reacts to `currentProjectId` directly, so an
  // external clear or set doesn't need a $effect to flip the flag —
  // when there's no value the form renders regardless of `editing`.
  // `untrack` keeps Svelte 5's reactivity analyzer from treating the
  // initial-snapshot read as a dependency (we don't want it derived).
  let editing = $state<boolean>(
    untrack(
      () => currentProjectId === null || currentProjectId === ""
    )
  );
  let pasted = $state<string>("");
  let parseError = $state<string | null>(null);
  let saveError = $state<string | null>(null);
  let saving = $state<boolean>(false);

  async function attemptSave(): Promise<void> {
    parseError = null;
    saveError = null;
    const parsed = parseLinkedInProjectUrl(pasted);
    if (parsed === null) {
      parseError =
        "That doesn't look like a Recruiter project URL — paste from a project page (the URL has linkedin.com/talent/hire/<digits> in it).";
      return;
    }
    saving = true;
    try {
      await onSave(parsed);
      pasted = "";
      editing = false;
    } catch (err) {
      saveError =
        err instanceof Error ? err.message : `Couldn't save: ${String(err)}`;
    } finally {
      saving = false;
    }
  }

  function startEditing(): void {
    editing = true;
    pasted = "";
    parseError = null;
    saveError = null;
  }

  function cancelEditing(): void {
    editing = false;
    pasted = "";
    parseError = null;
    saveError = null;
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter") {
      event.preventDefault();
      void attemptSave();
    }
  }
</script>

<div class={`linkedin-project-editor ${compact ? "linkedin-project-editor--compact" : ""}`}>
  {#if !editing && currentProjectId !== null && currentProjectId !== ""}
    <p class="linkedin-project-editor-display">
      <span class="linkedin-project-editor-id"
        >Project {currentProjectId}</span
      >
      {#if currentProjectName !== null && currentProjectName !== ""}
        <span class="linkedin-project-editor-name"
          >· {currentProjectName}</span
        >
      {/if}
      <button
        type="button"
        class="linkedin-project-editor-change"
        onclick={startEditing}
      >
        {changeLabel}
      </button>
    </p>
  {:else}
    <div class="linkedin-project-editor-form">
      <label class="linkedin-project-editor-field">
        <span class="linkedin-project-editor-prompt">
          <em>{label}</em>
        </span>
        <input
          type="url"
          class="linkedin-project-editor-input"
          bind:value={pasted}
          onkeydown={handleKeydown}
          {placeholder}
          disabled={saving}
          autocomplete="off"
          spellcheck="false"
        />
      </label>
      {#if parseError !== null}
        <p class="linkedin-project-editor-error" role="alert">
          {parseError}
        </p>
      {/if}
      {#if saveError !== null}
        <p class="linkedin-project-editor-error" role="alert">
          {saveError}
        </p>
      {/if}
      <div class="linkedin-project-editor-actions">
        <button
          type="button"
          class="linkedin-project-editor-save"
          onclick={() => void attemptSave()}
          disabled={saving || pasted.trim() === ""}
        >
          {saving ? "Saving…" : saveLabel}
        </button>
        {#if currentProjectId !== null && currentProjectId !== ""}
          <button
            type="button"
            class="linkedin-project-editor-cancel"
            onclick={cancelEditing}
            disabled={saving}
          >
            Cancel
          </button>
        {/if}
        {#if onClear !== null && currentProjectId !== null && currentProjectId !== ""}
          <button
            type="button"
            class="linkedin-project-editor-clear"
            onclick={() => void onClear?.()}
            disabled={saving}
          >
            Clear
          </button>
        {/if}
      </div>
    </div>
  {/if}
</div>
