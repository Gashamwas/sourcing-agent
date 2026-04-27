<script lang="ts">
  import { ApiError, stopWorker } from "../lib/api";
  import {
    optimisticStoppingStore,
    markStopping,
    refreshStatus
  } from "../lib/stores";
  import type { StateDirEntry } from "../lib/types";

  let { entry }: { entry: StateDirEntry } = $props();

  let stopInFlight = $state(false);
  let stopError = $state<string | null>(null);

  function key(): string {
    return `${entry.source}/${entry.state_key}`;
  }

  function isOptimisticallyStopping(): boolean {
    return $optimisticStoppingStore.has(key());
  }

  function latestRunLine(): string {
    if (entry.latest_run === null && !entry.runtime_state_present) {
      return "Runtime DB missing.";
    }
    if (entry.latest_run === null) {
      return "No run recorded yet.";
    }
    const status = entry.latest_run.status ?? "unknown";
    let line = `Latest run: ${status}`;
    if (entry.latest_run.stop_reason) {
      line += `, stopped: ${entry.latest_run.stop_reason}`;
    }
    if (entry.latest_run.ended_at) {
      line += ` (ended ${entry.latest_run.ended_at})`;
    }
    return line + ".";
  }

  function workerLine(): string {
    if (isOptimisticallyStopping()) return "Stopping...";
    if (entry.worker_state === "alive") {
      return `Worker alive (pid ${entry.worker_pid}).`;
    }
    if (entry.worker_state === "stale") {
      if (entry.worker_pid !== null && entry.worker_pid !== undefined) {
        return `Worker stale (pid ${entry.worker_pid}).`;
      }
      return "Worker stale.";
    }
    return "Worker missing.";
  }

  function workerLineIsItalic(): boolean {
    return isOptimisticallyStopping();
  }

  function resumabilityLine(): string | null {
    if (entry.resumable === true) return "Pending work to resume.";
    if (entry.resumable === false) return "No pending work.";
    return null;
  }

  function describeStopError(err: unknown): string {
    if (err instanceof ApiError) {
      if (err.status === 404) return "state directory not found";
      const d = err.detail;
      if (typeof d === "string") return d;
      if (d && typeof d === "object" && "error" in d) {
        return String((d as Record<string, unknown>).error ?? err.message);
      }
      return err.message;
    }
    return String(err);
  }

  async function onStop() {
    if (stopInFlight) return;
    stopInFlight = true;
    stopError = null;
    try {
      const { status, body } = await stopWorker(entry.source, entry.state_key);
      if (status === 202 && body.worker_state === "stopping") {
        markStopping(entry.source, entry.state_key);
      }
      refreshStatus();
    } catch (err) {
      stopError = `Stop failed: ${describeStopError(err)}.`;
    } finally {
      stopInFlight = false;
    }
  }

  function canStop(): boolean {
    return (
      entry.source === "linkedin" &&
      entry.worker_state === "alive" &&
      !isOptimisticallyStopping() &&
      !stopInFlight
    );
  }
</script>

<div class="state-row">
  <div class="state-row-header">{entry.source} · {entry.state_key}</div>
  <p class="state-row-line">{latestRunLine()}</p>
  {#if workerLineIsItalic()}
    <p class="italic-note">{workerLine()}</p>
  {:else}
    <p class="state-row-line">{workerLine()}</p>
  {/if}
  {#if resumabilityLine() !== null}
    <p class="state-row-line">{resumabilityLine()}</p>
  {/if}

  {#if entry.source === "linkedin"}
    <div class="state-row-actions">
      <button class="cloris-btn" type="button" onclick={onStop} disabled={!canStop()}>
        Stop
      </button>
      {#if stopError !== null}
        <p class="state-row-line" style="margin-top: 0.5rem; color: var(--wood-deep);">
          {stopError}
        </p>
      {/if}
    </div>
  {/if}
</div>
