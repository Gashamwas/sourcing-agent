<script lang="ts">
  // Brief library — Phase D Slice D1.
  //
  // Editorial card stack: every authored brief gets one row with
  // role title (Fraunces primary), source eyebrow (mono-caps), and a
  // small status pill carrying the latest run's state. Clicking a card
  // navigates to that brief's workspace (`#/workspace/<brief_id>`).
  //
  // Empty state when the recruiter has no briefs in `config/`: a
  // Cloris-voice italic line + a route-link to `#/brief/new`.

  import { onMount } from "svelte";
  import { ApiError, getBriefs } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import { sourceMeta } from "../lib/sources";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";
  import type { BriefInfo, BriefsListResponse } from "../lib/types";
  import AmbientBanner from "./AmbientBanner.svelte";
  import Finding from "./Finding.svelte";
  import PageBackLink from "./PageBackLink.svelte";

  let briefs = $state<BriefInfo[]>([]);
  let loadError = $state<string | null>(null);
  let loaded = $state<boolean>(false);

  onMount(async () => {
    try {
      const res: BriefsListResponse = await getBriefs();
      briefs = res.briefs;
    } catch (err) {
      loadError = describeApiError(err, "Loading briefs");
    } finally {
      loaded = true;
    }
  });

  function lastRunLabel(b: BriefInfo): string | null {
    const status = b.last_run_status;
    if (!status) return null;
    // Match the cloris-state vocabulary lightly without re-importing
    // the full state.ts vocabulary helpers — the wire string is already
    // recruiter-readable in 90% of cases. Phase F's H1 inversion will
    // wrap this in clorisStateLabel for full consistency.
    return status;
  }

  function lastRunStateKind(b: BriefInfo): string {
    // Map run-status to the same kind tokens StateDirRow's pill uses,
    // so we can reuse `card-status card-status--<kind>` from
    // components.css without lifting any component state.
    const status = (b.last_run_status ?? "").toLowerCase();
    if (!status) return "no-runs";
    if (status === "running") return "working";
    if (status === "completed") return "completed";
    if (status === "interrupted") return "interrupted";
    if (status === "governor_limit_reached") return "limit-reached";
    return "unknown";
  }

  function lastRunStateLabel(b: BriefInfo): string {
    const status = (b.last_run_status ?? "").toLowerCase();
    if (!status) return "No runs yet";
    if (status === "running") return "Working";
    if (status === "completed") return "Completed";
    if (status === "interrupted") return "Stopped";
    if (status === "governor_limit_reached") return "Paused";
    return status;
  }

  function lastRunStamp(b: BriefInfo): string | null {
    if (!b.last_run_at) return null;
    const parsed = new Date(b.last_run_at);
    if (Number.isNaN(parsed.getTime())) return b.last_run_at;
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit"
    }).format(parsed);
  }

  function workspaceHref(b: BriefInfo): string {
    if (b.brief_id) {
      return `#/workspace/${encodeURIComponent(b.brief_id)}`;
    }
    // Brief without a brief_id (no runs yet) — route to a placeholder
    // workspace URL using the path stem. Phase D's library always
    // surfaces brief_id post-D1, so this path is defensive only.
    return "#/brief/new";
  }

  // Phase D Slice D3 / Ledger L24: humanize legacy briefs that lack
  // role_title so the card reads as an editorial name instead of
  // leaking a `config/.../brief.json` filesystem path (R2 violation
  // caught by the Phase D Block C ensemble sweep on briefs@1280).
  // Rules:
  //   - role_title present → use it verbatim.
  //   - else strip directory prefix + .json suffix from `b.path`,
  //     drop the `brief-` filename prefix if present, and tag
  //     `(Legacy)` so the recruiter sees this is a pre-V2 brief.
  function cardTitle(b: BriefInfo): string {
    if (typeof b.role_title === "string" && b.role_title.trim().length > 0) {
      return b.role_title;
    }
    let stem = b.path;
    const slash = stem.lastIndexOf("/");
    if (slash !== -1) stem = stem.slice(slash + 1);
    if (stem.endsWith(".json")) stem = stem.slice(0, -5);
    if (stem.startsWith("brief-")) stem = stem.slice("brief-".length);
    if (stem === "brief") {
      // Nested layout brief.json without a role_title — fall back to
      // the parent dir name from the original path.
      const parts = b.path.split("/");
      stem = parts[parts.length - 2] ?? stem;
    }
    return `${stem} (Legacy)`;
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />
  <PageBackLink href="#/" label="Back to home" />

  <div class="shell-page">
    <section class="briefs-page">
      <header class="briefs-page-header">
        <p class="surface-eyebrow">your briefs</p>
        <h1 class="briefs-page-title">What you've authored</h1>
        <p class="section-deck">
          <em>Each one a search you've started, or could start.</em>
        </p>
        <hr class="section-rule" />
      </header>

      {#if !loaded}
        <div class="briefs-page-loading" out:loaderFadeOut>
          <Finding size="medium" />
        </div>
      {:else if loadError !== null}
        <p class="briefs-page-error" role="alert">{loadError}</p>
      {:else if briefs.length === 0}
        <section class="briefs-empty" in:surfaceFadeIn>
          <p class="briefs-empty-line">
            <em>You haven't authored a brief yet.</em>
          </p>
          <p class="briefs-empty-cta">
            <a class="briefs-empty-link" href="#/brief/new"
              >Start one →</a
            >
          </p>
        </section>
      {:else}
        <ul class="briefs-stack" aria-label="Authored briefs" in:surfaceFadeIn>
          {#each briefs as b (b.path)}
            <li class="briefs-card-wrap">
              <a class="briefs-card" href={workspaceHref(b)}>
                <header class="briefs-card-header">
                  <div class="briefs-card-heading">
                    {#if b.last_run_source !== null && b.last_run_source !== undefined}
                      <span class="briefs-card-source-eyebrow">
                        {sourceMeta(b.last_run_source).label}
                      </span>
                    {/if}
                    <h3 class="briefs-card-title">
                      {cardTitle(b)}
                    </h3>
                    {#if b.linkedin_project}
                      <p class="briefs-card-subtitle">
                        {b.linkedin_project}
                      </p>
                    {/if}
                  </div>
                  <span
                    class={`card-status card-status--${lastRunStateKind(b)}`}
                  >
                    {lastRunStateLabel(b)}
                  </span>
                </header>

                <dl class="briefs-card-fields">
                  <div class="briefs-card-field">
                    <dt class="briefs-card-field-label">Saves</dt>
                    <dd class="briefs-card-field-value">{b.total_saves ?? 0}</dd>
                  </div>
                  <!-- Plan Finding 13: Runs cell removed. The recruiter
                       cares about brief OUTPUT (saves) and whether to
                       revisit (last touched). The run count is operational
                       metadata about Cloris's execution loop. -->
                  {#if lastRunStamp(b)}
                    <div class="briefs-card-field">
                      <dt class="briefs-card-field-label">Last touched</dt>
                      <dd class="briefs-card-field-value">{lastRunStamp(b)}</dd>
                    </div>
                  {/if}
                </dl>
              </a>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </div>
</main>
