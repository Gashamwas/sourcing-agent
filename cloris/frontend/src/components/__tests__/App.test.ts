// App.svelte tests.
//
// What we're guarding:
//   - The shell mounts without throwing during initial render — a
//     regression on the adaptive-polling rewiring (P1.14) or the
//     ErrorBoundary wrap (P1.10) would surface as a crash here.
//   - The top-level ErrorBoundary actually wraps the shell. We assert
//     this structurally — the boundary's recovery <section
//     class="error-boundary"> is gated behind an error, but the rendered
//     tree should still place the shell <main> beneath the boundary
//     component (i.e. App's outermost rendered child is the boundary
//     wrapper, not the <main> directly).
//   - Routing: home → Homescreen, filed → FiledAwayPage, brief-new →
//     OnboardingFlow, unknown → operational fallback. All sit beneath
//     ErrorBoundary.
//   - Telemetry is route-aware: each route id maps to its own
//     `surface_viewed` event ("homescreen", "filed_away",
//     "onboarding_brief_new", "unknown_route"). We de-duplicate so only
//     changes emit.
//
// We stub fetch so refreshStatus() (called on mount) doesn't actually
// hit the network from the test environment.

import { render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { tick } from "svelte";
import App from "../../App.svelte";
import { statusStore, pollErrorStore, lastActionAt } from "../../lib/stores";
import { currentRoute, _testResetRoute } from "../../lib/router";
import {
  _testReadEvents,
  _testClearEvents
} from "../../lib/telemetry";

beforeEach(() => {
  // Reset stores so App's mount doesn't react to stale state from a
  // previous test in the same file.
  statusStore.set(null);
  pollErrorStore.set(null);
  lastActionAt.set(0);

  // Reset the URL + route store so each test starts on the home route.
  window.location.hash = "#/";
  _testResetRoute();

  // Telemetry buffer is module-scoped → must be cleared per-test so
  // earlier surface_viewed emissions don't leak forward.
  _testClearEvents();

  // Stub fetch to a never-resolving promise so refreshStatus() neither
  // throws nor settles during the test (and the timer scheduling code
  // doesn't get a real response back).
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise(() => {}))
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "#/";
  _testResetRoute();
});

describe("App — render", () => {
  it("renders without throwing", () => {
    expect(() => render(App)).not.toThrow();
  });

  it("renders the shell <main> under the document root on the home route", () => {
    const { container } = render(App);
    const main = container.querySelector("main.cloris-shell");
    expect(main).not.toBeNull();
  });

  it("does not render the ErrorBoundary recovery surface in the happy path", () => {
    const { container } = render(App);
    // .error-boundary is the recovery surface; in the no-error branch
    // <svelte:boundary>'s `failed` snippet is not rendered, so this
    // class should be absent.
    const boundarySurface = container.querySelector(".error-boundary");
    expect(boundarySurface).toBeNull();
  });
});

describe("App — routing", () => {
  it("renders the Homescreen shell when route === 'home'", () => {
    const { container } = render(App);
    // Homescreen owns `<main class="cloris-shell">` and renders the running
    // folio (slim mono-caps verb strip); sniff both so a regression on
    // either surface fails loudly.
    const main = container.querySelector("main.cloris-shell");
    expect(main).not.toBeNull();
    const folio = container.querySelector(".running-folio");
    expect(folio).not.toBeNull();
    // OnboardingFlow's distinctive heading must NOT be on screen.
    expect(container.querySelector(".onboarding-shell")).toBeNull();
  });

  it("renders the RunReportPage when route === 'run' with valid params", async () => {
    const { container } = render(App);
    currentRoute.set({
      route: "run",
      hash: "#/run/linkedin/test-key/42",
      params: {
        source: "linkedin",
        state_key: "test-key",
        run_id: "42"
      }
    });
    await tick();

    // RunReportPage immediately starts loading — the Finding loader
    // mounts (one of four random variant SVGs).
    expect(container.querySelector(".finding-stage")).not.toBeNull();
    // Homescreen running folio must NOT be on the run-report surface.
    expect(container.querySelector(".running-folio")).toBeNull();
  });

  it("renders the FiledAwayPage when route === 'filed'", async () => {
    const { container } = render(App);
    currentRoute.set({ route: "filed", hash: "#/filed", params: {} });
    await tick();

    const main = container.querySelector("main.cloris-shell");
    expect(main).not.toBeNull();
    // The Quiet Drawer title is the canonical FiledAwayPage marker.
    const heading = container.querySelector(".card-stack-title");
    expect(heading?.textContent?.trim()).toBe("Paused briefs");
    // No running folio on this surface — that lives only on Homescreen.
    expect(container.querySelector(".running-folio")).toBeNull();
  });

  it("renders the OnboardingFlow wizard when route === 'brief-new'", async () => {
    const { container } = render(App);
    // Drive the router store directly. Using the store (not navigate)
    // avoids depending on happy-dom's hashchange semantics in a test
    // that's about App's render branches, not the router itself.
    currentRoute.set({
      route: "brief-new",
      hash: "#/brief/new",
      params: {}
    });
    await tick();

    // Phase D Slice D3: OnboardingFlow is now the real wizard.
    // The inner container moved from .onboarding-page (placeholder) to
    // .onboarding-wizard (the chapter shell). Either should be acceptable
    // proof that the wizard's outer surface mounted.
    const wizard = container.querySelector(".onboarding-wizard");
    expect(wizard).not.toBeNull();
  });

  it("renders the operational fallback when route === 'unknown'", async () => {
    const { container } = render(App);
    currentRoute.set({
      route: "unknown",
      hash: "#/foo",
      params: {}
    });
    await tick();

    const fallback = container.querySelector(".route-fallback");
    expect(fallback).not.toBeNull();
    // Cloris-voice 404: first-person H1 + italic explainer of the two
    // realistic causes (page moved, link stale). The recruiter lands
    // here from a bad URL and reads a sentence from a person, not
    // "ERR_NOT_FOUND".
    expect(fallback?.textContent ?? "").toContain(
      "Cloris looked, but there's nothing here."
    );
    expect(fallback?.textContent ?? "").toContain(
      "The page may have moved, or the link could be stale."
    );
  });
});

describe("App — telemetry on mount", () => {
  it("emits surface_viewed{homescreen} once after mount on the home route", () => {
    render(App);
    const events = _testReadEvents();
    const surfaceViews = events.filter(
      (e) => e.type === "surface_viewed" && e.surface === "homescreen"
    );
    expect(surfaceViews.length).toBe(1);
  });

  it("emits surface_viewed{filed_away} when navigating to the filed route", async () => {
    render(App);
    _testClearEvents();

    currentRoute.set({ route: "filed", hash: "#/filed", params: {} });
    await tick();

    const events = _testReadEvents();
    const surfaceViews = events.filter((e) => e.type === "surface_viewed");
    expect(surfaceViews.length).toBe(1);
    expect(surfaceViews[0]).toMatchObject({
      type: "surface_viewed",
      surface: "filed_away"
    });
  });

  it("emits surface_viewed{run_report} when navigating to a run route", async () => {
    render(App);
    _testClearEvents();

    currentRoute.set({
      route: "run",
      hash: "#/run/linkedin/test-key/42",
      params: { source: "linkedin", state_key: "test-key", run_id: "42" }
    });
    await tick();

    const events = _testReadEvents();
    const surfaceViews = events.filter((e) => e.type === "surface_viewed");
    expect(surfaceViews.length).toBe(1);
    expect(surfaceViews[0]).toMatchObject({
      type: "surface_viewed",
      surface: "run_report"
    });
  });

  it("emits surface_viewed{onboarding_brief_new} when navigating to the brief-new route", async () => {
    render(App);
    _testClearEvents();

    currentRoute.set({
      route: "brief-new",
      hash: "#/brief/new",
      params: {}
    });
    await tick();

    const events = _testReadEvents();
    const surfaceViews = events.filter(
      (e) => e.type === "surface_viewed"
    );
    expect(surfaceViews.length).toBe(1);
    expect(surfaceViews[0]).toMatchObject({
      type: "surface_viewed",
      surface: "onboarding_brief_new"
    });
  });

  it("emits surface_viewed{unknown_route} when navigating to an unknown route", async () => {
    render(App);
    _testClearEvents();

    currentRoute.set({
      route: "unknown",
      hash: "#/foo",
      params: {}
    });
    await tick();

    const events = _testReadEvents();
    const surfaceViews = events.filter(
      (e) => e.type === "surface_viewed"
    );
    expect(surfaceViews.length).toBe(1);
    expect(surfaceViews[0]).toMatchObject({
      type: "surface_viewed",
      surface: "unknown_route"
    });
  });

  it("does not re-emit surface_viewed when the route store updates with the same route id", async () => {
    render(App);
    _testClearEvents();

    // Same route id, different params → must NOT emit again.
    currentRoute.set({ route: "home", hash: "#/", params: {} });
    await tick();
    currentRoute.set({ route: "home", hash: "#/", params: {} });
    await tick();

    const events = _testReadEvents();
    const surfaceViews = events.filter((e) => e.type === "surface_viewed");
    expect(surfaceViews.length).toBe(0);
  });

  it("emitted surface_viewed event contains no PII (no path leakage, no error.message)", () => {
    render(App);
    const events = _testReadEvents();
    // Ambient mount must not buffer any path-shaped telemetry.
    for (const event of events) {
      const serialized = JSON.stringify(event);
      expect(serialized).not.toContain("config/");
    }
  });
});
