<script lang="ts">
  // Brief detail / edit — Phase D Slice D2.
  //
  // Editorial display first: the recruiter reads Cloris's understanding
  // of the brief back to them in Fraunces section heads + Instrument
  // Serif italic prose. Edit surface lands in a follow-up D2 iteration
  // (read-only here gates the Fork-B merge-with-deprecation contract
  // before exposing edit affordances). The deprecated-keys drawer with
  // count badge lets the recruiter SEE which legacy notes Cloris hasn't
  // promoted yet — a Phase D editorial commitment per the architectural-
  // fit critique.

  import { onMount } from "svelte";
  import { ApiError, getBrief, getBriefVersions } from "../lib/api";
  import { briefDetailByline } from "../lib/copy";
  import { describeApiError } from "../lib/errors";
  import { saveLinkedInProjectFromDetail } from "../lib/linkedinProject";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";
  import type {
    BriefDetailResponse,
    BriefVersionEntry
  } from "../lib/types";
  import AmbientBanner from "./AmbientBanner.svelte";
  import Finding from "./Finding.svelte";
  import LinkedInProjectEditor from "./LinkedInProjectEditor.svelte";
  import PageBackLink from "./PageBackLink.svelte";

  let { briefId }: { briefId: string } = $props();

  let detail = $state<BriefDetailResponse | null>(null);
  let loadError = $state<string | null>(null);
  let notFound = $state<boolean>(false);
  let loaded = $state<boolean>(false);
  let deprecatedOpen = $state<boolean>(false);
  // Phase D Slice D5: version history list (read-only).
  let versions = $state<BriefVersionEntry[]>([]);
  let versionsOpen = $state<boolean>(false);

  onMount(async () => {
    try {
      detail = await getBrief(briefId);
      // Lazy-fetch versions only after successful detail load — saves
      // a 404 cascade if the brief_id is bogus.
      try {
        const v = await getBriefVersions(briefId);
        versions = v.versions;
      } catch {
        // Versions are nice-to-have; suppress errors so detail still
        // renders. The history block just shows an empty list.
        versions = [];
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        notFound = true;
      } else {
        loadError = describeApiError(err, "Loading brief");
      }
    } finally {
      loaded = true;
    }
  });

  function formatVersionDate(s: string): string {
    const parsed = new Date(s);
    if (Number.isNaN(parsed.getTime())) return s;
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit"
    }).format(parsed);
  }

  function capabilityAreas(d: BriefDetailResponse): Array<Record<string, unknown>> {
    const cas = d.v2_data["capability_areas"];
    if (!Array.isArray(cas)) return [];
    return cas.filter((a): a is Record<string, unknown> => typeof a === "object" && a !== null);
  }

  function depthFields(
    d: BriefDetailResponse
  ): { builder?: string; user?: string; edge?: string } {
    const dd = d.v2_data["depth_distinction"];
    if (!dd || typeof dd !== "object") return {};
    const obj = dd as Record<string, unknown>;
    return {
      builder: typeof obj["builder_definition"] === "string" ? (obj["builder_definition"] as string) : undefined,
      user: typeof obj["user_definition"] === "string" ? (obj["user_definition"] as string) : undefined,
      edge: typeof obj["edge_case_guidance"] === "string" ? (obj["edge_case_guidance"] as string) : undefined
    };
  }

  function nonFitPatterns(d: BriefDetailResponse): Array<Record<string, unknown>> {
    const nfp = d.v2_data["non_fit_patterns"];
    if (!Array.isArray(nfp)) return [];
    return nfp.filter((p): p is Record<string, unknown> => typeof p === "object" && p !== null);
  }

  function targetModules(d: BriefDetailResponse): string[] {
    const tm = d.v2_data["target_modules"];
    if (Array.isArray(tm)) {
      return tm.filter((s): s is string => typeof s === "string");
    }
    return [];
  }

  // Phase F Slice F2 — save destination read-out helpers.
  //
  // Save destinations live under `source_config` in the V2 brief.
  // Per-source sub-shapes:
  //   linkedin: { project_id?: string, project_name?: string }
  //   github:   { } (no destination semantics in F2)
  //   researcher: { } (deferred past F2)
  //
  // Backward compat: a brief carrying only the legacy flat
  // `linkedin_project_id` field still reads its destination through
  // `linkedinProjectId()` so the section reads "configured" until the
  // recruiter migrates by editing.
  function sourceConfigFor(
    d: BriefDetailResponse,
    source: string
  ): Record<string, unknown> {
    const sc = d.v2_data["source_config"];
    if (sc === null || sc === undefined || typeof sc !== "object") return {};
    const sub = (sc as Record<string, unknown>)[source];
    if (sub === null || sub === undefined || typeof sub !== "object") return {};
    return sub as Record<string, unknown>;
  }

  function linkedinProjectId(d: BriefDetailResponse): string | null {
    const sub = sourceConfigFor(d, "linkedin");
    if (typeof sub["project_id"] === "string" && sub["project_id"]) {
      return sub["project_id"];
    }
    const flat = d.v2_data["linkedin_project_id"];
    if (typeof flat === "string" && flat) return flat;
    if (typeof flat === "number") return String(flat);
    return null;
  }

  function linkedinProjectName(d: BriefDetailResponse): string | null {
    const sub = sourceConfigFor(d, "linkedin");
    if (typeof sub["project_name"] === "string" && sub["project_name"]) {
      return sub["project_name"];
    }
    const flat = d.v2_data["linkedin_project"];
    if (typeof flat === "string" && flat) return flat;
    return null;
  }

  function destinationModules(d: BriefDetailResponse): string[] {
    // Render destinations only for modules in the brief's
    // `target_modules`. If a brief has none declared, default to
    // ["linkedin"] so the section still reads useful — most existing
    // briefs predate target_modules and assume LinkedIn.
    const tm = targetModules(d);
    return tm.length > 0 ? tm : ["linkedin"];
  }

  function workspaceHref(d: BriefDetailResponse): string {
    return `#/workspace/${encodeURIComponent(d.brief_id)}`;
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />
  <PageBackLink href="#/briefs" label="Back to briefs" />

  <div class="shell-page">
    {#if !loaded}
      <div class="brief-detail-loading" out:loaderFadeOut>
        <Finding size="medium" />
      </div>
    {:else if notFound}
      <section class="brief-detail-empty" in:surfaceFadeIn>
        <h1>Cloris couldn't find that brief.</h1>
        <p class="section-deck">
          <em>The link may be stale, or the brief may have been moved or deleted.</em>
        </p>
        <p>
          <a href="#/briefs">Back to briefs →</a>
        </p>
      </section>
    {:else if loadError !== null}
      <p class="brief-detail-error" role="alert">{loadError}</p>
    {:else if detail !== null}
      {@const d = detail}
      <article class="brief-detail-page" in:surfaceFadeIn>
        <header class="brief-detail-header">
          <p class="surface-eyebrow">brief</p>
          {#if briefDetailByline(d.last_modified) !== null}
            <p class="cloris-byline"><em>{briefDetailByline(d.last_modified)}</em></p>
          {/if}
          <h1 class="brief-detail-title">{d.role_title ?? d.path}</h1>
          {#if d.was_flat}
            <p class="brief-detail-was-flat-note">
              <em>This brief is in the legacy layout. The next edit will move it into a versioned folder.</em>
            </p>
          {/if}
          <hr class="section-rule" />
          <p class="section-deck">
            <em>What Cloris understands you're looking for.</em>
          </p>
          <div class="brief-detail-actions">
            <a class="brief-detail-action-link" href={workspaceHref(d)}>
              Open the workspace for this brief →
            </a>
          </div>
        </header>

        <section class="brief-detail-section">
          <h2 class="brief-detail-section-title">What we're looking for</h2>
          {#if capabilityAreas(d).length === 0}
            <p class="brief-detail-empty-line">
              <em>This brief has no capability areas yet.</em>
            </p>
          {:else}
            <ol class="brief-detail-capability-list">
              {#each capabilityAreas(d) as area}
                <li class="brief-detail-capability">
                  <h3 class="brief-detail-capability-name">
                    {typeof area["name"] === "string" ? area["name"] : "Unnamed area"}
                  </h3>
                  {#if typeof area["description"] === "string"}
                    <p class="brief-detail-capability-description">
                      {area["description"]}
                    </p>
                  {/if}
                </li>
              {/each}
            </ol>
          {/if}
        </section>

        {#if depthFields(d).builder || depthFields(d).user || depthFields(d).edge}
          <section class="brief-detail-section">
            <h2 class="brief-detail-section-title">Where the depth lives</h2>
            <dl class="brief-detail-depth">
              {#if depthFields(d).builder}
                <div class="brief-detail-depth-row">
                  <dt>Building</dt>
                  <dd>{depthFields(d).builder}</dd>
                </div>
              {/if}
              {#if depthFields(d).user}
                <div class="brief-detail-depth-row">
                  <dt>Using</dt>
                  <dd>{depthFields(d).user}</dd>
                </div>
              {/if}
              {#if depthFields(d).edge}
                <div class="brief-detail-depth-row">
                  <dt>Edge cases</dt>
                  <dd>{depthFields(d).edge}</dd>
                </div>
              {/if}
            </dl>
          </section>
        {/if}

        {#if nonFitPatterns(d).length > 0}
          <section class="brief-detail-section">
            <h2 class="brief-detail-section-title">Patterns we're not chasing</h2>
            <ul class="brief-detail-nfp-list">
              {#each nonFitPatterns(d) as p}
                <li class="brief-detail-nfp">
                  {#if typeof p["label"] === "string"}
                    <strong>{p["label"]}</strong>
                  {/if}
                  {#if typeof p["why_not"] === "string"}
                    <span class="brief-detail-nfp-why">— {p["why_not"]}</span>
                  {/if}
                </li>
              {/each}
            </ul>
          </section>
        {/if}

        {#if targetModules(d).length > 0}
          <section class="brief-detail-section">
            <h2 class="brief-detail-section-title">Where Cloris should look</h2>
            <p class="brief-detail-target-modules">
              {targetModules(d).join(" · ")}
            </p>
          </section>
        {/if}

        <!-- Phase F Slice F2: where Cloris saves per source.
             Read-only in F2's first cut; the recruiter edits via the
             same PUT path D2 ships, just with `source_config` set on
             the V2 payload. F5's module-picker readiness check + F1's
             launch path both consult the same blocker the section
             surfaces here passively. -->
        <section class="brief-detail-section brief-detail-destinations">
          <h2 class="brief-detail-section-title">Where Cloris saves</h2>
          <p class="section-deck">
            <em>Each module's destination, once.</em>
          </p>
          <dl class="brief-detail-destination-list">
            {#each destinationModules(d) as mod}
              <div class="brief-detail-destination-row">
                <dt class="brief-detail-destination-source">
                  {mod === "linkedin"
                    ? "LinkedIn"
                    : mod === "github"
                      ? "GitHub"
                      : mod === "researcher"
                        ? "Researcher"
                        : mod}
                </dt>
                <dd class="brief-detail-destination-value">
                  {#if mod === "linkedin"}
                    <LinkedInProjectEditor
                      currentProjectId={linkedinProjectId(d)}
                      currentProjectName={linkedinProjectName(d)}
                      onSave={async ({ projectId, projectName }) => {
                        const updated = await saveLinkedInProjectFromDetail(
                          d,
                          { projectId, projectName }
                        );
                        detail = updated;
                      }}
                    />
                  {:else if mod === "github"}
                    <em class="brief-detail-destination-note">
                      No destination needed — Cloris writes to the run folder.
                    </em>
                  {:else}
                    <em class="brief-detail-destination-note">
                      Cloris isn't saving anywhere for this module yet.
                    </em>
                  {/if}
                </dd>
              </div>
            {/each}
          </dl>
        </section>

        {#if versions.length > 0}
          <details class="brief-detail-versions" bind:open={versionsOpen}>
            <summary class="brief-detail-versions-summary">
              Edit history
              <span class="brief-detail-versions-count">({versions.length})</span>
            </summary>
            <ul class="brief-detail-versions-list">
              {#each versions as v (v.version_id)}
                <li class="brief-detail-version">
                  <span class="brief-detail-version-when">{formatVersionDate(v.created_at)}</span>
                  <span class="brief-detail-version-size">{(v.size_bytes / 1024).toFixed(1)}&nbsp;KB</span>
                </li>
              {/each}
            </ul>
          </details>
        {/if}

        {#if d.deprecated_keys.length > 0 || d.unknown_keys.length > 0}
          <!-- Plan Finding 19: summary collapsed to "Older brief fields"
               (plain product label) and the count badge dropped. The
               recruiter never makes a decision against the count —
               they either click in (because they care about legacy
               fields) or they don't. -->
          <details class="brief-detail-deprecated" bind:open={deprecatedOpen}>
            <summary class="brief-detail-deprecated-summary">
              Older brief fields
            </summary>
            <div class="brief-detail-deprecated-body">
              {#if d.deprecated_keys.length > 0}
                <p class="brief-detail-deprecated-line">
                  <em>These notes use the older brief shape. Each will need a home in the new structure or can be dropped.</em>
                </p>
                <ul class="brief-detail-deprecated-list">
                  {#each d.deprecated_keys as key}
                    <li class="brief-detail-deprecated-key">{key}</li>
                  {/each}
                </ul>
              {/if}
              {#if d.unknown_keys.length > 0}
                <p class="brief-detail-deprecated-line">
                  <em>Notes Cloris doesn't recognize. Decide whether to keep or drop on the next edit.</em>
                </p>
                <ul class="brief-detail-deprecated-list">
                  {#each d.unknown_keys as key}
                    <li class="brief-detail-deprecated-key">{key}</li>
                  {/each}
                </ul>
              {/if}
            </div>
          </details>
        {/if}
      </article>
    {/if}
  </div>
</main>
