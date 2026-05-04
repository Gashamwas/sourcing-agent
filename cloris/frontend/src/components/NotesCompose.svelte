<script lang="ts">
  // NotesCompose — recruiter-authored note log on the candidate-detail
  // surface (Phase C, slice C3).
  //
  // The compose field is plain operational copy (R21); the rendered note
  // body is whatever the recruiter typed. Notes are append-only and
  // rendered in reverse-chrono. The primitive is presentational — the
  // parent owns the data and the submit handler.

  import type { CandidateNoteEntry } from "../lib/types";
  import {
    notesComposeLabel,
    notesComposePlaceholder,
    notesComposeAddButton,
    notesComposeAddingButton,
    notesComposeError
  } from "../lib/copy";

  let {
    notes,
    onSubmit,
    disabled = false
  }: {
    notes: CandidateNoteEntry[];
    onSubmit: (body: string) => Promise<void>;
    disabled?: boolean;
  } = $props();

  let draft = $state<string>("");
  let inFlight = $state<boolean>(false);
  let errorMessage = $state<string | null>(null);

  // Reverse-chrono: oldest -> newest is how the canonical store appends,
  // but the recruiter cares about the most recent note first.
  function notesReverseChrono(): CandidateNoteEntry[] {
    return [...notes].reverse();
  }

  function formatTimestamp(iso: string): string {
    const parsed = new Date(iso);
    if (Number.isNaN(parsed.getTime())) return iso;
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit"
    }).format(parsed);
  }

  async function handleSubmit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const body = draft.trim();
    if (inFlight || disabled || body === "") return;
    inFlight = true;
    errorMessage = null;
    try {
      await onSubmit(body);
      draft = "";
    } catch {
      errorMessage = notesComposeError;
    } finally {
      inFlight = false;
    }
  }
</script>

<section class="notes-compose" aria-label={notesComposeLabel}>
  <p class="notes-compose-label">{notesComposeLabel}</p>
  <form class="notes-compose-form" onsubmit={handleSubmit}>
    <textarea
      class="notes-compose-textarea"
      placeholder={notesComposePlaceholder}
      bind:value={draft}
      disabled={inFlight || disabled}
      rows="3"
    ></textarea>
    <div class="notes-compose-actions">
      <button
        type="submit"
        class="notes-compose-submit"
        disabled={inFlight || disabled || draft.trim() === ""}
      >
        {inFlight ? notesComposeAddingButton : notesComposeAddButton}
      </button>
    </div>
  </form>
  {#if errorMessage !== null}
    <p class="notes-compose-error" role="alert" aria-live="polite">{errorMessage}</p>
  {/if}

  <!-- Phase C-bis 0.6a: empty-state paragraph removed. The textarea
       placeholder already carries the empty state ("Write a note about
       this candidate…"); the redundant message below the form was R23
       redundancy. Note list only renders when there are notes. -->
  {#if notes.length > 0}
    <ul class="notes-compose-list">
      {#each notesReverseChrono() as note (note.created_at)}
        <li class="notes-compose-entry">
          <p class="notes-compose-entry-body">{note.body}</p>
          <p class="notes-compose-entry-stamp">{formatTimestamp(note.created_at)}</p>
        </li>
      {/each}
    </ul>
  {/if}
</section>
