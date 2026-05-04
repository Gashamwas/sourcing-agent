<script lang="ts">
  import {
    ApiError,
    getLaunchReadiness,
    launchForSource,
    resumeLinkedIn
  } from "../lib/api";
  import { saveLinkedInProject } from "../lib/linkedinProject";
  import { refreshStatus, markAction, launchModeStore, statusStore } from "../lib/stores";
  import { describeApiError } from "../lib/errors";
  import { emit, hashBriefPath } from "../lib/telemetry";
  import { anyResumable, resumableBriefIds } from "../lib/cardfile";
  import BriefPicker from "./BriefPicker.svelte";
  import LinkedInProjectEditor from "./LinkedInProjectEditor.svelte";
  import type { BriefInfo, LaunchReadinessResponse, Source } from "../lib/types";
  import {
    launchPanelEyebrow,
    launchFileCardButton,
    launchPullResumeButton,
    launchFiledStatus,
    launchPulledStatus,
    launchReadinessLabel,
    launchReadinessReadyLabel,
    launchReadinessForceLabel,
    launchReadinessForceHelp,
    launchModulesLabel,
    launchModulesHelp,
    launchModulesEmpty,
    launchModuleLinkedInLabel,
    launchModuleGitHubLabel,
    launchModuleResearcherLabel,
    launchModuleResearcherDisabledHelp
  } from "../lib/copy";

  // Phase F Slice F5. The active modules a brief can target. LinkedIn
  // and GitHub are wired end-to-end (F1 launch endpoint, D9 readiness);
  // Researcher is in the catalog but renders disabled until its module
  // ships. Adding a new module post-F: append to ACTIVE_MODULES, add a
  // catalog entry, ship the per-module readiness + launch backends.
  type ModuleId = Source | "researcher";
  const MODULE_CATALOG: ReadonlyArray<{
    id: ModuleId;
    label: string;
    enabled: boolean;
    disabledHelp?: string;
  }> = [
    { id: "linkedin", label: launchModuleLinkedInLabel, enabled: true },
    { id: "github", label: launchModuleGitHubLabel, enabled: true },
    {
      id: "researcher",
      label: launchModuleResearcherLabel,
      enabled: false,
      disabledHelp: launchModuleResearcherDisabledHelp
    }
  ];

  let briefPath = $state("");
  let selectedBrief = $state<BriefInfo | null>(null);
  let inFlight = $state(false);
  let okMessage = $state<string | null>(null);
  let errorMessage = $state<string | null>(null);
  let panelEl: HTMLElement | null = $state(null);

  // Per-module readiness state. Replaces D9's single-source pattern.
  // The pre-flight stanza renders one block per selected ENABLED
  // module; aggregated `allReady` is AND across selected modules.
  let selectedModules = $state<Source[]>([]);
  let readinessByModule = $state<Partial<Record<Source, LaunchReadinessResponse>>>(
    {}
  );
  let readinessProbingByModule = $state<Partial<Record<Source, boolean>>>({});
  let readinessErrorByModule = $state<Partial<Record<Source, string>>>({});
  let forceBypass = $state(false);

  function detectForceBypass(): boolean {
    if (typeof window === "undefined") return false;
    const search = window.location.search ?? "";
    return new URLSearchParams(search).has("force");
  }

  $effect(() => {
    forceBypass = detectForceBypass();
  });

  // When a brief is picked, seed the selected modules from the brief's
  // target_modules (default ["linkedin"] for legacy briefs without the
  // key). Filter out modules not in the active catalog so a future
  // brief mentioning a not-yet-shipped module doesn't pre-select it.
  function activeModulesFor(brief: BriefInfo | null): Source[] {
    if (brief === null) return [];
    const fromBrief = brief.target_modules ?? ["linkedin"];
    const enabled = new Set(
      MODULE_CATALOG.filter((m) => m.enabled).map((m) => m.id)
    );
    return fromBrief.filter((m): m is Source => enabled.has(m as ModuleId)) as Source[];
  }

  $effect(() => {
    selectedModules = activeModulesFor(selectedBrief);
  });

  // Probe readiness per selected module. Re-runs whenever the brief OR
  // the selected modules change so toggling a chip refreshes the
  // pre-flight without a full reload.
  $effect(() => {
    const brief = selectedBrief;
    const modules = selectedModules;
    if (brief === null || modules.length === 0) {
      readinessByModule = {};
      readinessErrorByModule = {};
      readinessProbingByModule = {};
      return;
    }
    const next: Partial<Record<Source, boolean>> = {};
    for (const m of modules) {
      next[m] = true;
    }
    readinessProbingByModule = next;
    readinessErrorByModule = {};

    for (const m of modules) {
      getLaunchReadiness(m, brief.path)
        .then((res) => {
          readinessByModule = { ...readinessByModule, [m]: res };
        })
        .catch((err) => {
          readinessErrorByModule = {
            ...readinessErrorByModule,
            [m]: describeApiError(err, "Pre-flight check")
          };
          readinessByModule = { ...readinessByModule, [m]: undefined };
        })
        .finally(() => {
          readinessProbingByModule = { ...readinessProbingByModule, [m]: false };
        });
    }
  });

  function toggleModule(id: ModuleId, enabled: boolean): void {
    if (!enabled) return;
    const source = id as Source;
    if (selectedModules.includes(source)) {
      selectedModules = selectedModules.filter((m) => m !== source);
    } else {
      selectedModules = [...selectedModules, source];
    }
  }

  function isModuleSelected(id: ModuleId): boolean {
    return selectedModules.includes(id as Source);
  }

  // Re-probe readiness for one module after an inline blocker fix
  // (e.g. the recruiter just pasted a Recruiter project URL via
  // <LinkedInProjectEditor>). Uses the same endpoint as the initial
  // probe so the launch CTA unlocks without a page reload.
  async function reprobeReadinessFor(source: Source): Promise<void> {
    const brief = selectedBrief;
    if (brief === null) return;
    readinessProbingByModule = { ...readinessProbingByModule, [source]: true };
    try {
      const res = await getLaunchReadiness(source, brief.path);
      readinessByModule = { ...readinessByModule, [source]: res };
      readinessErrorByModule = { ...readinessErrorByModule, [source]: undefined };
    } catch (err) {
      readinessErrorByModule = {
        ...readinessErrorByModule,
        [source]: describeApiError(err, "Pre-flight check")
      };
      readinessByModule = { ...readinessByModule, [source]: undefined };
    } finally {
      readinessProbingByModule = { ...readinessProbingByModule, [source]: false };
    }
  }

  // D9 graceful-fallback semantics: only `observed-not-ready` blocks.
  // `probing` and `errored` do NOT block — the backend re-validates
  // on launch. Mirrors the single-source behavior; reduced AND-style
  // across modules.
  function anyModuleObservedNotReady(): boolean {
    for (const m of selectedModules) {
      const r = readinessByModule[m];
      if (r !== undefined && !r.ready) return true;
    }
    return false;
  }

  // True when EVERY selected module has reported ready=true. Used by
  // the force-label heuristic so we don't show "Start anyway" when all
  // modules are happy.
  function allModulesReady(): boolean {
    if (selectedModules.length === 0) return false;
    for (const m of selectedModules) {
      const r = readinessByModule[m];
      if (r === undefined || !r.ready) return false;
    }
    return true;
  }

  function launchDisabled(): boolean {
    if (inFlight) return true;
    if (briefPath.trim() === "") return true;
    if (selectedModules.length === 0) return true;
    if (anyModuleObservedNotReady() && !forceBypass) return true;
    return false;
  }

  function handleSelect(brief: BriefInfo): void {
    selectedBrief = brief;
    briefPath = brief.path;
    okMessage = null;
    errorMessage = null;
  }

  let pulseAttention = $state(false);
  let resumeMode = $state(false);

  $effect(() => {
    const mode = $launchModeStore;
    if (mode === null) return;
    resumeMode = mode === "resume";
    panelEl?.scrollIntoView({ behavior: "smooth", block: "start" });
    pulseAttention = true;
    setTimeout(() => {
      pulseAttention = false;
    }, 900);
    launchModeStore.set(null);
  });

  function errorCodeOf(err: unknown): string {
    if (err instanceof ApiError && err.detail && typeof err.detail === "object" && "error" in err.detail) {
      const code = (err.detail as Record<string, unknown>).error;
      return typeof code === "string" ? code : "unknown";
    }
    return "unknown";
  }

  // F5: fan out to /api/launch/{source} once per selected module.
  // Each module is its own worker; failures surface per-module without
  // aborting the rest. F6 + F7 will deduplicate the resulting cards
  // into a single per-brief view.
  async function onFileCard(event: SubmitEvent) {
    event.preventDefault();
    if (inFlight || briefPath.trim() === "" || selectedModules.length === 0) return;
    inFlight = true;
    okMessage = null;
    errorMessage = null;
    const trimmed = briefPath.trim();
    const briefId = selectedBrief?.brief_id ?? trimmed;
    const briefPathHash = hashBriefPath(trimmed);

    const failures: string[] = [];
    let succeeded = 0;

    await Promise.all(
      selectedModules.map(async (source) => {
        emit({
          type: "launch_attempted",
          source,
          brief_path_hash: briefPathHash
        });
        try {
          const res = await launchForSource(source, briefId, "fresh", forceBypass);
          succeeded += 1;
          emit({
            type: "launch_succeeded",
            source,
            brief_path_hash: briefPathHash,
            pid: res.pid
          });
        } catch (err) {
          const message = describeApiError(err, `Start search (${source})`);
          failures.push(message);
          emit({
            type: "launch_failed",
            source,
            brief_path_hash: briefPathHash,
            error_code: errorCodeOf(err)
          });
        }
      })
    );

    if (succeeded > 0) {
      okMessage = launchFiledStatus;
      resumeMode = false;
      markAction();
      refreshStatus();
    }
    if (failures.length > 0) {
      errorMessage = failures.join(" — ");
    }
    inFlight = false;
  }

  // Resume only fires for LinkedIn at first cut — the GitHub
  // resume path lives behind the legacy /api/resume/linkedin synonym
  // until F6 generalizes. Keeping the existing helper avoids changing
  // resume semantics in the same slice that introduces the picker.
  async function onPullAndResume() {
    if (inFlight || briefPath.trim() === "") return;
    inFlight = true;
    okMessage = null;
    errorMessage = null;
    const trimmed = briefPath.trim();
    const briefPathHash = hashBriefPath(trimmed);
    emit({
      type: "resume_attempted",
      source: "linkedin",
      brief_path_hash: briefPathHash
    });
    try {
      const res = await resumeLinkedIn(trimmed);
      okMessage = launchPulledStatus;
      resumeMode = false;
      emit({
        type: "resume_succeeded",
        source: "linkedin",
        brief_path_hash: briefPathHash,
        pid: res.pid
      });
      markAction();
      refreshStatus();
    } catch (err) {
      errorMessage = describeApiError(err, "Pull & Resume");
      emit({
        type: "resume_failed",
        source: "linkedin",
        brief_path_hash: briefPathHash,
        error_code: errorCodeOf(err)
      });
    } finally {
      inFlight = false;
    }
  }
</script>

<aside
  class={`file-panel ${pulseAttention ? "file-panel--pulse" : ""}`}
  aria-label="File a new card"
  bind:this={panelEl}
>
  <p class="panel-eyebrow">{resumeMode ? "Resume a search" : launchPanelEyebrow}</p>

  <form onsubmit={onFileCard}>
    <BriefPicker
      selectedPath={selectedBrief?.path ?? null}
      onSelect={handleSelect}
      resumeOnly={resumeMode}
      resumableIds={resumableBriefIds($statusStore?.entries ?? [])}
    />

    {#if selectedBrief !== null}
      <p class="brief-picker-selected" aria-live="polite">
        Ready: <strong>{selectedBrief.role_title ?? selectedBrief.path}</strong>
      </p>

      <!-- Phase F Slice F5: module picker. Honors the brief's
           target_modules (default ["linkedin"] for legacy briefs);
           recruiter can deselect a module for this launch only. -->
      <section class="launch-modules" aria-label={launchModulesLabel}>
        <p class="launch-modules-label">{launchModulesLabel}</p>
        <p class="launch-modules-help"><em>{launchModulesHelp}</em></p>
        <div class="launch-modules-chips" role="group" aria-label={launchModulesLabel}>
          {#each MODULE_CATALOG as mod (mod.id)}
            <button
              type="button"
              class={`launch-module-chip ${isModuleSelected(mod.id) ? "is-selected" : ""} ${mod.enabled ? "" : "is-disabled"}`}
              aria-pressed={isModuleSelected(mod.id)}
              aria-disabled={!mod.enabled}
              onclick={() => toggleModule(mod.id, mod.enabled)}
              title={mod.enabled ? "" : (mod.disabledHelp ?? "")}
            >
              {mod.label}
            </button>
          {/each}
        </div>
        {#if selectedModules.length === 0}
          <p class="launch-modules-empty"><em>{launchModulesEmpty}</em></p>
        {/if}
      </section>

      <!-- Per-module readiness pre-flight. One block per selected,
           ENABLED module; aggregated AND-style for the launch button. -->
      {#if selectedModules.length > 0}
        <section class="launch-readiness" aria-live="polite" aria-label={launchReadinessLabel}>
          <p class="launch-readiness-label">{launchReadinessLabel}</p>
          {#each selectedModules as moduleId (moduleId)}
            {@const probing = readinessProbingByModule[moduleId] ?? false}
            {@const readiness = readinessByModule[moduleId]}
            {@const errored = readinessErrorByModule[moduleId]}
            <div class="launch-readiness-module" data-module={moduleId}>
              <p class="launch-readiness-module-eyebrow">{moduleId}</p>
              {#if probing}
                <!-- Plan Finding 4: dropped "Cloris is checking…". The
                     per-module probing block is the visual signal — the
                     module eyebrow renders alone for the brief probing
                     window, then the ready / blockers branch fills in. -->
              {:else if errored !== undefined}
                <p class="launch-readiness-error">{errored}</p>
              {:else if readiness !== undefined}
                {#if readiness.ready}
                  <p class="launch-readiness-ready">{launchReadinessReadyLabel}</p>
                {:else}
                  <ul class="launch-readiness-blockers">
                    {#each readiness.blockers as blocker (blocker.message)}
                      <li class={`launch-readiness-blocker launch-readiness-blocker--${blocker.kind}`}>
                        <p class="launch-readiness-blocker-message">{blocker.message}</p>
                        <p class="launch-readiness-blocker-remediation">{blocker.remediation}</p>
                        {#if blocker.kind === "config" && moduleId === "linkedin" && selectedBrief !== null && selectedBrief.brief_id}
                          <!-- Path 3 trial slice: inline editor at the F2
                               readiness blocker. PUT, then re-probe so
                               the launch CTA unlocks without reload.
                               Guard on brief_id explicitly — the BriefInfo
                               type allows null when linkedin_state_key
                               fails, in which case the editor can't save
                               and we fall back to the remediation prose
                               directing the recruiter at the brief
                               library. -->
                          {@const targetBriefId = selectedBrief.brief_id}
                          <LinkedInProjectEditor
                            currentProjectId={null}
                            currentProjectName={null}
                            compact={true}
                            onSave={async ({ projectId, projectName }) => {
                              await saveLinkedInProject(targetBriefId, {
                                projectId,
                                projectName
                              });
                              await reprobeReadinessFor("linkedin");
                            }}
                          />
                        {/if}
                      </li>
                    {/each}
                  </ul>
                {/if}
              {/if}
            </div>
          {/each}
          {#if forceBypass && anyModuleObservedNotReady()}
            <p class="launch-readiness-force-active">
              <em>{launchReadinessForceHelp}</em>
            </p>
          {/if}
        </section>
      {/if}
    {/if}

    <div class="button-row">
      <button
        class="btn-file-card"
        type="submit"
        disabled={launchDisabled()}
      >
        {forceBypass && anyModuleObservedNotReady()
          ? launchReadinessForceLabel
          : launchFileCardButton}
      </button>
      {#if anyResumable($statusStore?.entries ?? [])}
        <button
          class="btn-pull-resume"
          type="button"
          onclick={onPullAndResume}
          disabled={launchDisabled()}
        >
          {launchPullResumeButton}
        </button>
      {/if}
    </div>
  </form>

  <div class="file-panel-status" aria-live="polite">
    {#if okMessage !== null}
      <p class="ok">{okMessage}</p>
    {/if}
    {#if errorMessage !== null}
      <p class="error">{errorMessage}</p>
    {/if}
  </div>
</aside>
