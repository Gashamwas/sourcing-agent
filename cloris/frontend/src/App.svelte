<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import {
    refreshStatus,
    statusStore,
    pollErrorStore,
    lastActionAt,
    currentPollCadence,
    type PollCadence
  } from "./lib/stores";
  import {
    getOnboardingStatus,
    reconcileOrphans,
    type OnboardingStatusResponse
  } from "./lib/api";
  import AmbientBanner from "./components/AmbientBanner.svelte";
  import CandidateDetail from "./components/CandidateDetail.svelte";
  import ErrorBoundary from "./components/ErrorBoundary.svelte";
  import Homescreen from "./components/Homescreen.svelte";
  import LegacyRedirect from "./components/LegacyRedirect.svelte";
  import PageBackLink from "./components/PageBackLink.svelte";
  import FiledAwayPage from "./components/FiledAwayPage.svelte";
  import OnboardingFlow from "./components/OnboardingFlow.svelte";
  import Welcome from "./components/Welcome.svelte";
  import Briefs from "./components/Briefs.svelte";
  import BriefDetail from "./components/BriefDetail.svelte";
  import Drafts from "./components/Drafts.svelte";
  import IdentityReconciliation from "./components/IdentityReconciliation.svelte";
  import Market from "./components/Market.svelte";
  import MarketDetail from "./components/MarketDetail.svelte";
  import Monitor from "./components/Monitor.svelte";
  import MonitorRun from "./components/MonitorRun.svelte";
  import RefreshBrief from "./components/RefreshBrief.svelte";
  import ReflectionFlow from "./components/ReflectionFlow.svelte";
  import Settings from "./components/Settings.svelte";
  import Tools from "./components/Tools.svelte";
  import RunReportPage from "./components/RunReportPage.svelte";
  import Workspace from "./components/Workspace.svelte";
  import { emit } from "./lib/telemetry";
  import { currentRoute, startRouter, type Route } from "./lib/router";

  // Adaptive polling cadence (P1.14) with visibility-aware pause/resume.
  //
  // Cadence rules (computed by lib/stores.currentPollCadence):
  //   - 3s when something is running, the user just acted, or the API
  //     is unreachable (faster recovery / faster reflection).
  //   - 10s when idle (nothing running, no recent action, no poll error).
  //   - bounded to exactly those two values; no intermediate steps.
  //
  // Lifecycle:
  //   - mount: poll once, schedule the next tick at the current cadence,
  //     subscribe to all four cadence-input stores so we re-arm the timer
  //     when the cadence should change, and listen for visibilitychange.
  //   - tab hidden: clear the scheduled tick; polling is paused entirely
  //     while invisible (preserves prior behavior).
  //   - tab visible: refresh once immediately and resume the schedule.
  //   - destroy: clear timer, drop subscriptions, drop the visibility
  //     listener.
  //
  // We use setTimeout (one-shot, then re-arm) instead of setInterval so
  // changing cadence is just "reschedule the next tick at the new ms"
  // — no clear+restart race window where two timers exist briefly.
  //
  // Routing note (Slice 1): polling continues across both routes. The
  // `brief-new` surface is lightweight (no live data) but cheap polling
  // keeps the home route warm if the user toggles back. Per-route pause
  // is a Phase 2 polish item.
  let timer: ReturnType<typeof setTimeout> | null = null;
  let scheduledCadence: PollCadence | null = null;
  let isVisible = true;

  // Phase 0 ``apikey-ui`` slice: first-launch welcome gate.
  //
  // We fetch the welcome-status snapshot on mount BEFORE rendering
  // the route table. Three states:
  //
  //   - onboardingStatus === null      → still loading; render nothing
  //                                      (the brief flicker is preferable
  //                                      to a flash of the home route
  //                                      that immediately gets replaced
  //                                      by Welcome).
  //   - welcome_complete === false     → render Welcome.svelte, gating
  //                                      the rest of the app until the
  //                                      recipient enters their key +
  //                                      acknowledges.
  //   - welcome_complete === true      → fall through to the route table.
  //
  // We deliberately do NOT poll the welcome status: once the page is
  // unlocked, no need to re-check. If the recipient clears their
  // user-data dir mid-session (extremely unlikely), they'll see the
  // welcome again on the next launch.
  let onboardingStatus = $state<OnboardingStatusResponse | null>(null);
  let onboardingError = $state<string | null>(null);

  async function refreshOnboarding(): Promise<void> {
    try {
      onboardingStatus = await getOnboardingStatus();
      onboardingError = null;
    } catch (err) {
      // If the gate read itself fails, fall through to the route table
      // rather than trapping the recipient on a permanent loading
      // screen. The legacy product flow still works without the
      // welcome gate; this is a soft-degrade rather than a hard fail.
      onboardingError = String(err);
      onboardingStatus = {
        slice: "v0-onboarding-status-1",
        welcome_complete: true,
        anthropic_present: false,
        acknowledged: false,
        acknowledged_at: null,
        env_path: "",
        acknowledgment_path: ""
      };
    }
  }

  function handleWelcomeComplete(): void {
    // The welcome surface fired its mutations successfully. Refresh
    // the gate so the route table renders on the next tick.
    void refreshOnboarding();
  }

  function clearTimer(): void {
    if (timer === null) return;
    clearTimeout(timer);
    timer = null;
    scheduledCadence = null;
  }

  function scheduleNext(cadence: PollCadence): void {
    clearTimer();
    scheduledCadence = cadence;
    timer = setTimeout(() => {
      timer = null;
      scheduledCadence = null;
      if (!isVisible) return;
      refreshStatus().finally(() => {
        if (isVisible) scheduleNext(currentPollCadence());
      });
    }, cadence);
  }

  function reconcileCadence(): void {
    if (!isVisible) return;
    const next = currentPollCadence();
    if (next !== scheduledCadence) {
      scheduleNext(next);
    }
  }

  function onVisibilityChange(): void {
    if (document.visibilityState === "hidden") {
      isVisible = false;
      clearTimer();
    } else {
      isVisible = true;
      refreshStatus().finally(() => {
        if (isVisible) scheduleNext(currentPollCadence());
      });
    }
  }

  // Map a logical route id to the surface name we report to telemetry.
  // Centralized here so adding a new route only touches this table and the
  // router's parseHash — the subscription below stays untouched.
  function surfaceForRoute(route: Route): string {
    switch (route) {
      case "home":
        return "homescreen";
      case "filed":
        return "filed_away";
      case "briefs":
        return "briefs_library";
      case "brief-detail":
        return "brief_detail";
      case "brief-new":
        return "onboarding_brief_new";
      case "drafts":
        return "intake_drafts_list";
      case "run":
        return "run_report";
      case "candidate":
        return "candidate_detail";
      case "workspace":
        return "workspace";
      case "workspace-identity":
        return "workspace_identity_reconciliation";
      case "workspace-legacy":
        return "workspace_legacy_redirect";
      case "candidate-legacy":
        return "candidate_legacy_redirect";
      case "market":
        return "market_catalog";
      case "market-detail":
        return "market_detail";
      case "refresh-brief":
        return "refresh_brief";
      case "monitor":
        return "monitor_index";
      case "monitor-run":
        return "monitor_run";
      case "tools":
        return "tools_index";
      case "settings":
        return "settings";
      case "reflect":
        return "reflection";
      case "unknown":
        return "unknown_route";
    }
  }

  // We subscribe imperatively (rather than via $effect) so the listener
  // runs exactly once for the component's lifetime and we own the
  // unsubscribe call in onDestroy.
  let unsubscribers: Array<() => void> = [];

  // Phase 1A: opportunistic zombie reconciliation. Fires on app mount and
  // every RECONCILE_INTERVAL_MS thereafter so runs whose worker process
  // died (Mac sleep, OOM, kill -9) get their status='running' lie corrected
  // to status='abandoned'. The /api/status endpoint stays a pure read; this
  // is the explicit write trigger.
  const RECONCILE_INTERVAL_MS = 5 * 60 * 1000;
  let reconcileInterval: ReturnType<typeof setInterval> | null = null;

  function kickoffReconciliation(): void {
    void reconcileOrphans()
      .then((response) => {
        // Re-fetch status so the UI reflects post-reconciliation state.
        // We refresh regardless of `applied` count: even when no zombies
        // are reconciled the status payload may have moved on independently.
        return refreshStatus();
      })
      .catch(() => {
        // Reconciliation is best-effort. If the endpoint is unreachable,
        // the existing status poll handles error surfacing — we don't
        // double-surface here.
      });
  }

  onMount(() => {
    isVisible =
      typeof document === "undefined" ||
      document.visibilityState !== "hidden";

    // Phase 0 ``apikey-ui`` slice: fetch the welcome-gate snapshot
    // before anything else. Fire-and-forget; the reactive render
    // below picks up the result when it lands.
    void refreshOnboarding();

    // Phase 1A: kick off reconciliation alongside the first status fetch.
    // We don't await — fire-and-forget so a slow reconciliation doesn't
    // delay first paint.
    kickoffReconciliation();
    reconcileInterval = setInterval(kickoffReconciliation, RECONCILE_INTERVAL_MS);

    refreshStatus().finally(() => {
      if (isVisible) scheduleNext(currentPollCadence());
    });

    // Wire the hash router. `startRouter` returns an unsubscriber that
    // removes the hashchange listener; we capture it alongside the store
    // subscriptions so onDestroy tears everything down uniformly.
    unsubscribers.push(startRouter());

    // Surface-view telemetry (P1.12). Now route-aware: every route
    // transition emits exactly one `surface_viewed` event for the new
    // surface. We de-duplicate so the initial subscription firing
    // (Svelte's writable subscribers always fire once on attach with the
    // current value) doesn't double up with a later "real" change to the
    // same route.
    let lastEmittedRoute: Route | null = null;
    unsubscribers.push(
      currentRoute.subscribe((state) => {
        if (state.route === lastEmittedRoute) return;
        lastEmittedRoute = state.route;
        emit({ type: "surface_viewed", surface: surfaceForRoute(state.route) });
      })
    );

    // Re-arm when any cadence input changes. statusStore captures the
    // alive-workers branch, pollErrorStore captures the API-down branch,
    // and lastActionAt captures the recent-action branch.
    unsubscribers.push(statusStore.subscribe(reconcileCadence));
    unsubscribers.push(pollErrorStore.subscribe(reconcileCadence));
    unsubscribers.push(lastActionAt.subscribe(reconcileCadence));

    document.addEventListener("visibilitychange", onVisibilityChange);
  });

  onDestroy(() => {
    clearTimer();
    if (reconcileInterval !== null) {
      clearInterval(reconcileInterval);
      reconcileInterval = null;
    }
    for (const unsub of unsubscribers) unsub();
    unsubscribers = [];
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", onVisibilityChange);
    }
  });
</script>

<!--
  Inline styles (no <style> block) for the route fallback. Same reason as
  ErrorBoundary: the project's vitest setup can't preprocess scoped <style>
  blocks (preprocessCSS path incompatible with current vite-plugin-svelte).
  The fallback only renders on the unknown branch, so the styling weight is
  trivial and inline keeps the test environment happy.
-->
<ErrorBoundary>
  {#if onboardingStatus === null}
    <!-- Phase 0 apikey-ui: pre-fetch flicker. Empty cream while the
         welcome-gate snapshot loads — preferable to flashing a route
         that may immediately get replaced by Welcome. -->
  {:else if !onboardingStatus.welcome_complete}
    <Welcome
      initial={onboardingStatus}
      onComplete={handleWelcomeComplete}
    />
  {:else if $currentRoute.route === "home"}
    <Homescreen />
  {:else if $currentRoute.route === "filed"}
    <FiledAwayPage />
  {:else if $currentRoute.route === "briefs"}
    <Briefs />
  {:else if $currentRoute.route === "brief-detail"}
    <BriefDetail briefId={$currentRoute.params.brief_id ?? ""} />
  {:else if $currentRoute.route === "brief-new"}
    <OnboardingFlow />
  {:else if $currentRoute.route === "drafts"}
    <Drafts />
  {:else if $currentRoute.route === "run"}
    <RunReportPage
      source={$currentRoute.params.source ?? ""}
      stateKey={$currentRoute.params.state_key ?? ""}
      runId={$currentRoute.params.run_id ?? ""}
    />
  {:else if $currentRoute.route === "candidate"}
    <CandidateDetail
      briefId={$currentRoute.params.brief_id ?? ""}
      candidateId={$currentRoute.params.candidate_id ?? ""}
    />
  {:else if $currentRoute.route === "workspace"}
    <Workspace
      briefId={$currentRoute.params.brief_id ?? ""}
    />
  {:else if $currentRoute.route === "workspace-identity"}
    <IdentityReconciliation
      briefId={$currentRoute.params.brief_id ?? ""}
    />
  {:else if $currentRoute.route === "reflect"}
    <ReflectionFlow
      briefId={$currentRoute.params.brief_id ?? ""}
      sessionId={$currentRoute.params.session ? Number($currentRoute.params.session) : null}
      sourceRunId={$currentRoute.params.from_run ? Number($currentRoute.params.from_run) : null}
      runDir={$currentRoute.params.run_dir ?? null}
    />
  {:else if $currentRoute.route === "workspace-legacy"}
    <LegacyRedirect
      kind="workspace"
      source={$currentRoute.params.source ?? ""}
      stateKey={$currentRoute.params.state_key ?? ""}
    />
  {:else if $currentRoute.route === "candidate-legacy"}
    <LegacyRedirect
      kind="candidate"
      source={$currentRoute.params.source ?? ""}
      stateKey={$currentRoute.params.state_key ?? ""}
      candidateId={$currentRoute.params.candidate_id ?? ""}
    />
  {:else if $currentRoute.route === "market"}
    <Market />
  {:else if $currentRoute.route === "market-detail"}
    <MarketDetail />
  {:else if $currentRoute.route === "refresh-brief"}
    <RefreshBrief />
  {:else if $currentRoute.route === "monitor"}
    <Monitor />
  {:else if $currentRoute.route === "monitor-run"}
    <MonitorRun
      source={$currentRoute.params.source ?? ""}
      stateKey={$currentRoute.params.state_key ?? ""}
      runId={$currentRoute.params.run_id ?? ""}
    />
  {:else if $currentRoute.route === "tools"}
    <Tools />
  {:else if $currentRoute.route === "settings"}
    <Settings />
  {:else}
    <!-- Phase 3C: 404 was previously bare cream with no masthead, breaking
         the design-system invariant ("every surface inherits the chrome").
         Wrap in cloris-shell + AmbientBanner so the 404 reads as a Cloris
         page that happens to not exist, not a rogue browser fallback.

         Phase C-bis 0.6b: ribbon hidden (irrelevant on 404 — the recruiter
         is here to recover from a bad URL, not glance at brief inventory),
         and a subordinate italic line below the H1 carries the editorial
         voice without burying the operational H1. -->
    <main class="cloris-shell">
      <AmbientBanner />
      <PageBackLink href="#/" label="Back to home" />
      <div class="shell-page">
        <section
          class="route-fallback"
          role="alert"
          aria-live="polite"
          style="max-width: 720px; margin: 4rem auto; padding: 2rem;"
        >
          <h1 style="margin: 0 0 0.5rem;">Cloris looked, but there's nothing here.</h1>
          <p class="section-deck">
            <em>The page may have moved, or the link could be stale.</em>
          </p>
        </section>
      </div>
    </main>
  {/if}
</ErrorBoundary>
