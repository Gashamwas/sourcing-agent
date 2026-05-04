<script lang="ts">
  // Settings — read-only operational transparency surface (Phase G G5).
  //
  // Recruiters see what Cloris has access to and how it operates without
  // being able to break things. Three sections (R6 omits empty):
  //   - Cloris's hands     — credentials as ✓/✗
  //   - Where Cloris saves — per-brief V2 source_config summary
  //   - How fast Cloris runs — governor read-only display
  //
  // Editorial register: each row leads with the answer, italic explainer
  // beneath. Mono-caps for keys + ≥14px floor (R17). No knobs — governor
  // is hard-coded by deliberate engineering decision; the explainer says so.

  import { onMount } from "svelte";
  import { ApiError, getSettings } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import type { SettingsResponse } from "../lib/types";
  import AmbientBanner from "./AmbientBanner.svelte";
  import DisplayTitle from "./DisplayTitle.svelte";
  import Finding from "./Finding.svelte";
  import PageBackLink from "./PageBackLink.svelte";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";

  let settings = $state<SettingsResponse | null>(null);
  let loadError = $state<string | null>(null);

  async function load(): Promise<void> {
    try {
      settings = await getSettings();
      loadError = null;
    } catch (err) {
      loadError = describeApiError(err, "Loading settings");
    }
  }

  onMount(load);

  function briefHref(briefId: string): string {
    return `#/brief/${encodeURIComponent(briefId)}`;
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />

  <PageBackLink href="#/" label="Back to home" />

  <div class="settings-page">
    <figure class="specimen-frame">
      <span class="specimen-frame-label">SETTINGS</span>
      <div class="specimen-frame-stage">
        <DisplayTitle head="What Cloris" accent="knows" />
        <!-- Plan Finding 14: dropped the second sentence
             ("Nothing in this view is editable from the UI."). The
             absence of edit affordances is the message. -->
        <p class="section-deck">
          <em>Read-only. Every value here is set in your environment or
          baked into Cloris by design.</em>
        </p>
      </div>
    </figure>

    {#if loadError !== null && settings === null}
      <section class="settings-empty" role="alert" aria-live="polite">
        <h2>Couldn't load settings.</h2>
        <p>{loadError}</p>
      </section>
    {:else if settings === null}
      <div class="settings-loading" out:loaderFadeOut>
        <Finding size="medium" />
      </div>
    {:else}
      {@const s = settings}
      <div class="settings-content" in:surfaceFadeIn>

      {#if s.credentials.length > 0}
        <section class="settings-section">
          <h2 class="settings-section-title">Cloris's hands</h2>
          <p class="settings-section-deck">
            <em>What Cloris can talk to right now.</em>
          </p>
          <ul class="settings-list">
            {#each s.credentials as c (c.key)}
              <li class="settings-row" data-credential={c.key}>
                <span class={`settings-mark ${c.present ? "settings-mark--ok" : "settings-mark--missing"}`}>
                  {c.present ? "✓" : "✗"}
                </span>
                <div class="settings-row-body">
                  <h3 class="settings-row-label">{c.label}</h3>
                  <p class="settings-row-pitch">{c.pitch}</p>
                </div>
              </li>
            {/each}
          </ul>
          <p class="settings-cdp-url">
            CDP endpoint: <code>{s.cdp_url || "—"}</code>
          </p>
          <!-- Phase 0 disclosure slice: relational framing for the
               Chrome / LinkedIn surface area. The governor section
               below ("How fast Cloris runs") shows the cadence
               numbers; this paragraph names what that cadence
               applies to in plain English so the recipient can
               re-orient on the operational bargain on every visit. -->
          <p class="settings-relational-framing">
            <em>
              Cloris reads and writes through the Chrome window above.
              Saves go into your real Recruiter projects. Pace is
              governed by the limits below — Cloris won't open more
              than that in a single sitting, and won't operate at all
              unless you start a search.
            </em>
          </p>
        </section>
      {/if}

      {#if s.save_destinations.length > 0}
        <section class="settings-section">
          <h2 class="settings-section-title">Where Cloris saves</h2>
          <p class="settings-section-deck">
            <em>Per-brief save destinations from each brief's
            source_config.</em>
            Edit a brief to change its destination.
          </p>
          <ul class="settings-list">
            {#each s.save_destinations as b (b.brief_id)}
              <li class="settings-row" data-brief-id={b.brief_id}>
                <div class="settings-row-body">
                  <h3 class="settings-row-label">
                    <a href={briefHref(b.brief_id)}>{b.role_title || b.brief_id}</a>
                  </h3>
                  <p class="settings-row-pitch">
                    Modules: {b.target_modules.join(", ") || "—"}
                    {#if b.linkedin_project_id}
                      · LinkedIn project: <code>{b.linkedin_project_id}</code>
                    {/if}
                  </p>
                </div>
              </li>
            {/each}
          </ul>
        </section>
      {/if}

      {#if s.governor.length > 0}
        <section class="settings-section">
          <h2 class="settings-section-title">How fast Cloris runs</h2>
          <!-- Plan Finding 14: dropped the section deck
               ("Tuned for safe LinkedIn cadence. Cloris doesn't expose
               these as knobs by design."). The values + their per-row
               explainers do the work; meta-commentary on a surface a
               recruiter visits more than once doesn't earn its place. -->
          <ul class="settings-list">
            {#each s.governor as g (g.name)}
              <li class="settings-row" data-governor={g.name}>
                <div class="settings-row-body">
                  <h3 class="settings-row-label">
                    {g.label}: <span class="settings-row-value">{g.value}</span>
                  </h3>
                  <p class="settings-row-pitch">{g.explainer}</p>
                </div>
              </li>
            {/each}
          </ul>
        </section>
      {/if}
      </div>
    {/if}
  </div>
</main>
