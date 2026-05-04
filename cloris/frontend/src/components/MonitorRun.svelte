<script lang="ts">
  // MonitorRun — per-run Live Monitor view (Phase G Slice G3).
  //
  // Operational depth for one run: full attempt-health table, recent
  // attempts (raw enums), recent events. Polled every 1s while the worker
  // is alive, 5s otherwise; pauses entirely while the tab is hidden.
  //
  // Register exception: this surface is operational, not editorial.
  // Mono-caps headers and raw enums are correct here. The editorial
  // counterpart is RunReportPage; recruiters who want depth come here.

  import { onMount, onDestroy } from "svelte";
  import {
    ApiError,
    getRunReport,
    getRunTelemetry,
  } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import { clorisStopReasonLabel } from "../lib/state";
  import type {
    RunReportResponse,
    RunTelemetryResponse,
  } from "../lib/types";
  import AmbientBanner from "./AmbientBanner.svelte";
  import Finding from "./Finding.svelte";
  import PageBackLink from "./PageBackLink.svelte";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";

  let {
    source,
    stateKey,
    runId,
  }: {
    source: string;
    stateKey: string;
    runId: string;
  } = $props();

  let report = $state<RunReportResponse | null>(null);
  let telemetry = $state<RunTelemetryResponse | null>(null);
  let loadError = $state<string | null>(null);

  const ACTIVE_POLL_MS = 1000;
  const IDLE_POLL_MS = 5000;
  let pollHandle: ReturnType<typeof setInterval> | null = null;

  function isActive(): boolean {
    return report?.run.status === "running";
  }

  function tabIsVisible(): boolean {
    if (typeof document === "undefined") return true;
    return document.visibilityState !== "hidden";
  }

  async function load(): Promise<void> {
    if (!tabIsVisible()) return;
    const runIdNum = Number(runId);
    if (!Number.isFinite(runIdNum)) {
      loadError = "Invalid run id.";
      return;
    }
    try {
      const [r, t] = await Promise.all([
        getRunReport(source, stateKey, runIdNum),
        getRunTelemetry(source, stateKey, runIdNum),
      ]);
      report = r;
      telemetry = t;
      loadError = null;
    } catch (err) {
      loadError = describeApiError(err, "Loading the run");
    }
  }

  function schedulePoll(): void {
    if (pollHandle !== null) clearInterval(pollHandle);
    const interval = isActive() ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    if (typeof window !== "undefined") {
      pollHandle = setInterval(() => void load().then(schedulePoll), interval);
    }
  }

  onMount(() => {
    void load().then(schedulePoll);
  });

  onDestroy(() => {
    if (pollHandle !== null) clearInterval(pollHandle);
  });

  function backHref(): string {
    return `#/monitor`;
  }

  function backToReportHref(): string {
    return `#/run/${encodeURIComponent(source)}/${encodeURIComponent(stateKey)}/${encodeURIComponent(runId)}`;
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />

  <PageBackLink href={backHref()} label="Back to monitor" />

  <div class="monitor-run-page">
    {#if loadError !== null && report === null}
      <section class="monitor-empty" role="alert" aria-live="polite">
        <h2>Couldn't load this run.</h2>
        <p>{loadError}</p>
      </section>
    {:else if report === null}
      <div class="monitor-loading" out:loaderFadeOut>
        <Finding size="medium" />
      </div>
    {:else}
      {@const r = report}
      <section class="monitor-run-header" in:surfaceFadeIn>
        <p class="surface-eyebrow">RUN #{r.run.id} · {r.source.toUpperCase()} · {r.state_key}</p>
        <h1 class="monitor-run-title">
          {r.run.brief_role_title ?? r.run.brief_id ?? "Untitled run"}
        </h1>
        <!-- Plan Finding 17: dropped the "STATUS · " prefix. The label
             added zero information; the value alone is the message. R7
             violation by the team's own rules — eyebrow + body data at
             the same register. -->
        <p class="monitor-run-status">
          {r.run.status?.toUpperCase() ?? "UNKNOWN"}
          {#if r.run.stop_reason !== null}
            <span class="monitor-run-stop">
              · {r.run.stop_reason} ({clorisStopReasonLabel(r.run.stop_reason)})
            </span>
          {/if}
        </p>
        <p class="monitor-run-link">
          <a href={backToReportHref()}>← Back to editorial run report</a>
        </p>
      </section>

      {#if r.attempt_health !== null}
        {@const h = r.attempt_health}
        <section class="monitor-section">
          <h2 class="monitor-section-title">ATTEMPT HEALTH</h2>
          <table class="monitor-attempt-health">
            <tbody>
              <tr><th scope="row">TOTAL</th><td>{h.total_attempts_in_window}</td></tr>
              <tr><th scope="row">SUCCEEDED</th><td>{h.succeeded_in_window}</td></tr>
              <tr><th scope="row">FAILED</th><td>{h.failed_in_window}</td></tr>
              <tr><th scope="row">DOMINANT FAILURE</th><td>{h.dominant_failure_kind ?? "—"}</td></tr>
              <tr><th scope="row">LAST SUCCESS AGE (s)</th><td>{h.last_success_age_s ?? "—"}</td></tr>
            </tbody>
          </table>
          {#if h.recent_failures.length > 0}
            <h3 class="monitor-subsection-title">RECENT FAILURE HISTOGRAM</h3>
            <table class="monitor-failure-histogram">
              <thead>
                <tr><th scope="col">KIND</th><th scope="col">COUNT</th></tr>
              </thead>
              <tbody>
                {#each h.recent_failures as f (f.kind)}
                  <tr><td>{f.kind}</td><td>{f.count}</td></tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </section>
      {/if}

      {#if telemetry !== null}
        <section class="monitor-section">
          <h2 class="monitor-section-title">
            ATTEMPTS · {telemetry.attempts.length} of {telemetry.attempts_total} most recent
          </h2>
          {#if telemetry.attempts.length === 0}
            <p class="monitor-empty-line">No attempts logged yet.</p>
          {:else}
            <table class="monitor-attempts-table">
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">STAGE</th>
                  <th scope="col">ATTEMPT</th>
                  <th scope="col">STATUS</th>
                  <th scope="col">FAILURE KIND</th>
                  <th scope="col">STARTED</th>
                  <th scope="col">ENDED</th>
                </tr>
              </thead>
              <tbody>
                {#each telemetry.attempts as a (a.id)}
                  <tr>
                    <td>{a.id}</td>
                    <td>{a.stage}</td>
                    <td>{a.attempt_number}</td>
                    <td>{a.status}</td>
                    <td>{a.failure_kind ?? "—"}</td>
                    <td>{a.started_at}</td>
                    <td>{a.ended_at ?? "—"}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </section>

        <section class="monitor-section">
          <h2 class="monitor-section-title">
            EVENTS · {telemetry.events.length} of {telemetry.events_total} most recent
          </h2>
          {#if telemetry.events.length === 0}
            <p class="monitor-empty-line">No events logged yet.</p>
          {:else}
            <table class="monitor-events-table">
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">TYPE</th>
                  <th scope="col">CREATED</th>
                  <th scope="col">PAYLOAD</th>
                </tr>
              </thead>
              <tbody>
                {#each telemetry.events as e (e.id)}
                  <tr>
                    <td>{e.id}</td>
                    <td>{e.event_type}</td>
                    <td>{e.created_at}</td>
                    <td class="monitor-events-payload">{e.payload_summary ?? "—"}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </section>
      {/if}
    {/if}
  </div>
</main>
