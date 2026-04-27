<script lang="ts">
  import { ApiError, launchLinkedIn, resumeLinkedIn } from "../lib/api";
  import { refreshStatus } from "../lib/stores";

  let briefPath = $state("");
  let inFlight = $state(false);
  let okMessage = $state<string | null>(null);
  let errorMessage = $state<string | null>(null);

  function describeError(err: unknown): string {
    if (err instanceof ApiError) {
      const d = err.detail;
      if (d && typeof d === "object" && "error" in d) {
        const detail = d as Record<string, unknown>;
        const code = String(detail.error ?? "");
        if (code === "brief_path_not_found") {
          return `brief path not found (${detail.brief_path ?? briefPath})`;
        }
        if (code === "worker_already_running") {
          return `worker already running (pid ${detail.pid ?? "?"})`;
        }
        return code || err.message;
      }
      if (typeof d === "string") return d;
      return err.message;
    }
    return String(err);
  }

  async function onLaunch(event: SubmitEvent) {
    event.preventDefault();
    if (inFlight || briefPath.trim() === "") return;
    inFlight = true;
    okMessage = null;
    errorMessage = null;
    try {
      const res = await launchLinkedIn(briefPath.trim());
      okMessage = `Launched. PID ${res.pid}. State directory ${res.state_dir}.`;
      refreshStatus();
    } catch (err) {
      errorMessage = `Launch failed: ${describeError(err)}.`;
    } finally {
      inFlight = false;
    }
  }

  async function onResume() {
    if (inFlight || briefPath.trim() === "") return;
    inFlight = true;
    okMessage = null;
    errorMessage = null;
    try {
      const res = await resumeLinkedIn(briefPath.trim());
      okMessage = `Resumed. PID ${res.pid}. State directory ${res.state_dir}.`;
      refreshStatus();
    } catch (err) {
      errorMessage = `Resume failed: ${describeError(err)}.`;
    } finally {
      inFlight = false;
    }
  }
</script>

<section class="section">
  <p class="section-number">02 — Launch</p>
  <hr class="hairline-rule" />
  <form onsubmit={onLaunch}>
    <label class="cloris-input-label" for="brief-path-input">brief path</label>
    <input
      id="brief-path-input"
      class="cloris-input"
      type="text"
      placeholder="config/brief-some-role-v1.json"
      bind:value={briefPath}
      disabled={inFlight}
      autocomplete="off"
      spellcheck="false"
    />
    <div class="launch-actions">
      <button
        class="cloris-btn"
        type="submit"
        disabled={inFlight || briefPath.trim() === ""}
      >
        Launch
      </button>
      <button
        class="cloris-btn"
        type="button"
        onclick={onResume}
        disabled={inFlight || briefPath.trim() === ""}
      >
        Resume
      </button>
    </div>
    <p class="italic-note" style="margin-top: 0.75rem;">
      Resume only takes effect when the brief's state directory has pending
      work to resume. Otherwise the backend reports no pending work and
      exits cleanly.
    </p>
  </form>

  <div class="launch-status">
    {#if okMessage !== null}
      <p class="ok">{okMessage}</p>
    {/if}
    {#if errorMessage !== null}
      <p class="error">{errorMessage}</p>
    {/if}
  </div>
</section>
