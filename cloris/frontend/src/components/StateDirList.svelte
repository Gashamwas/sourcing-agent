<script lang="ts">
  import { statusStore } from "../lib/stores";
  import StateDirRow from "./StateDirRow.svelte";
</script>

<section class="section">
  <p class="section-number">03 — Runs</p>
  <hr class="hairline-rule" />

  {#if $statusStore === null}
    <p class="empty-state">Reading state.</p>
  {:else if $statusStore.entries.length === 0}
    <p class="empty-state">No state directories yet.</p>
  {:else}
    <div>
      {#each $statusStore.entries as entry (entry.source + "/" + entry.state_key)}
        <StateDirRow {entry} />
      {/each}
    </div>
  {/if}
</section>
