<script lang="ts">
  import { statusStore, pollErrorStore } from "../lib/stores";

  function summary(): string {
    if ($statusStore === null) return "Reading state.";
    const n = $statusStore.entries.length;
    if (n === 0) return "No state directories yet.";
    if (n === 1) return "1 state directory tracked.";
    return `${n} state directories tracked.`;
  }

  function errorDetail(): string {
    if ($pollErrorStore === null) return "";
    const d = $pollErrorStore.detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object") {
      try {
        return JSON.stringify(d);
      } catch {
        return $pollErrorStore.message;
      }
    }
    return $pollErrorStore.message;
  }
</script>

<section class="section">
  <p class="section-number">01 — Cloris</p>
  <hr class="hairline-rule" />
  <p class="prose">{summary()}</p>
  {#if $pollErrorStore !== null}
    <p class="poll-error">
      Cloris cannot reach the local server. Last error: {errorDetail()}.
    </p>
  {/if}
</section>
