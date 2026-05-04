<script lang="ts">
  // Monitor — Live Monitor index (Phase G Slice G3).
  //
  // Operational depth surface. Lists every run currently in motion
  // (worker_alive=true). Click into a row to read per-run telemetry.
  //
  // Editorial register exception: Monitor is operational, not editorial.
  // Mono-caps headers, raw enums, dense tables are all OK here. Recruiters
  // come to Monitor when they want depth Run Report deliberately doesn't
  // show — the editorial register lives on RunReportPage; Monitor is its
  // operational counterpart.

  import { onMount, onDestroy } from "svelte";
  import { ApiError, getMonitorIndex } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import { sourceMeta } from "../lib/sources";
  import { resolveRecruiterTitleFromKey } from "../lib/state";
  import type { MonitorIndexResponse, ActiveRunSummary, Source } from "../lib/types";
  import AmbientBanner from "./AmbientBanner.svelte";
  import Monitoring from "./Monitoring.svelte";
  import DisplayTitle from "./DisplayTitle.svelte";
  import Finding from "./Finding.svelte";
  import PageBackLink from "./PageBackLink.svelte";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";

  let index = $state<MonitorIndexResponse | null>(null);
  let loadError = $state<string | null>(null);

  const POLL_MS = 5000;
  let pollHandle: ReturnType<typeof setInterval> | null = null;

  async function load(): Promise<void> {
    try {
      index = await getMonitorIndex();
      loadError = null;
    } catch (err) {
      loadError = describeApiError(err, "Loading Monitor");
    }
  }

  onMount(() => {
    void load();
    if (typeof window !== "undefined") {
      pollHandle = setInterval(() => void load(), POLL_MS);
    }
  });

  onDestroy(() => {
    if (pollHandle !== null) clearInterval(pollHandle);
  });

  function rowHref(r: ActiveRunSummary): string {
    if (r.run_id === null) return "#/monitor";
    return `#/monitor/${encodeURIComponent(r.source)}/${encodeURIComponent(r.state_key)}/${r.run_id}`;
  }

  function rowTitle(r: ActiveRunSummary): string {
    return resolveRecruiterTitleFromKey(
      r.source as Source,
      r.brief_id ?? r.state_key,
      r.brief_role_title
    ).primary;
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />

  <PageBackLink href="#/" label="Back to home" />

  <div class="monitor-page">
    <figure class="specimen-frame">
      <span class="specimen-frame-label">LIVE MONITOR</span>
      <div class="specimen-frame-stage">
        <DisplayTitle head="Live" accent="monitor" />
        <p class="monitor-deck">
          <em>Runs in motion right now.</em>
          {#if index !== null && index.active_runs.length === 0}
            Nothing is running.
          {:else if index !== null}
            {index.active_runs.length} active.
          {/if}
        </p>
      </div>
    </figure>

    {#if loadError !== null && index === null}
      <section class="monitor-empty" role="alert" aria-live="polite">
        <h2>Couldn't load Monitor.</h2>
        <p>{loadError}</p>
      </section>
    {:else if index === null}
      <div class="monitor-loading" out:loaderFadeOut>
        <Finding size="medium" />
      </div>
    {:else if index.active_runs.length === 0}
      <div in:surfaceFadeIn>
        <Monitoring size="small" />
      </div>
    {:else}
      <table class="monitor-table" aria-label="Active runs" in:surfaceFadeIn>
        <thead>
          <tr>
            <th scope="col">SOURCE</th>
            <th scope="col">BRIEF</th>
            <th scope="col">RUN</th>
            <th scope="col">STATUS</th>
            <th scope="col">STARTED</th>
            <th scope="col">PID</th>
          </tr>
        </thead>
        <tbody>
          {#each index.active_runs as r (`${r.source}/${r.state_key}/${r.run_id ?? "x"}`)}
            <tr>
              <td>
                <span class={`monitor-source-pill monitor-source-pill--${r.source}`}>
                  {sourceMeta(r.source).pillLabel}
                </span>
              </td>
              <td>
                <a href={rowHref(r)} class="monitor-row-link">{rowTitle(r)}</a>
              </td>
              <td>{r.run_id ?? "—"}</td>
              <td>{r.run_status ?? "—"}</td>
              <td>{r.started_at ?? "—"}</td>
              <td>{r.worker_pid ?? "—"}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
</main>
