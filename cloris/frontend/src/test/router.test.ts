// Cloris frontend router tests (Slice 1 of the onboarding plan).
//
// What we're guarding:
//   - parseHash maps every documented input to the right Route id:
//       ""              → home
//       "#"             → home (defensive: bare "#" without trailing slash)
//       "#/"            → home
//       "#/brief/new"   → brief-new
//       "#/foo"         → unknown
//   - navigate(hash) writes through to window.location.hash, and the
//     hashchange listener wired by startRouter() updates currentRoute.
//   - startRouter()'s returned unsubscriber removes the listener so a
//     later hashchange does NOT update the store.
//   - The store value preserves the raw hash string (so future deep-link
//     code can recover it) and emits an empty params object.
//
// happy-dom provides window + history + location, but `window.location.hash =`
// in happy-dom does fire `hashchange` events synchronously, which is what we
// rely on. If happy-dom changes that behavior we'll fall back to manual
// dispatchEvent in these tests.

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { get } from "svelte/store";
import {
  currentRoute,
  navigate,
  startRouter,
  _testParseHash,
  _testResetRoute,
} from "../lib/router";

beforeEach(() => {
  // Reset the URL to a known baseline so each test starts on the home
  // route. Setting hash to "" doesn't always clear the fragment in
  // happy-dom (the URL retains the "#"), so we set it to "#/" — equivalent
  // for our parser and reliably normalized by the DOM.
  window.location.hash = "#/";
  _testResetRoute();
});

afterEach(() => {
  // Clean up any straggling hash so a test that left things mid-way
  // doesn't bleed into the next file.
  window.location.hash = "#/";
  _testResetRoute();
});

describe("router — parseHash", () => {
  it("maps empty hash to home", () => {
    const state = _testParseHash("");
    expect(state.route).toBe("home");
    expect(state.hash).toBe("");
    expect(state.params).toEqual({});
  });

  it("maps '#' (bare) to home", () => {
    // Browsers will sometimes leave just "#" after a hash is cleared.
    // We treat that as equivalent to the home route to avoid a flicker
    // through the unknown branch.
    const state = _testParseHash("#");
    expect(state.route).toBe("home");
  });

  it("maps '#/' to home", () => {
    const state = _testParseHash("#/");
    expect(state.route).toBe("home");
    expect(state.hash).toBe("#/");
  });

  it("maps '#/brief/new' to brief-new", () => {
    const state = _testParseHash("#/brief/new");
    expect(state.route).toBe("brief-new");
    expect(state.hash).toBe("#/brief/new");
    expect(state.params).toEqual({});
  });

  it("maps an unknown hash to unknown", () => {
    const state = _testParseHash("#/foo");
    expect(state.route).toBe("unknown");
    expect(state.hash).toBe("#/foo");
  });

  it("maps '#/brief/new?draft=42' to brief-new with draft param", () => {
    const state = _testParseHash("#/brief/new?draft=42");
    expect(state.route).toBe("brief-new");
    expect(state.params).toEqual({ draft: "42" });
  });

  it("maps '#/drafts' to drafts", () => {
    const state = _testParseHash("#/drafts");
    expect(state.route).toBe("drafts");
    expect(state.hash).toBe("#/drafts");
    expect(state.params).toEqual({});
  });

  it("maps '#/filed' to filed", () => {
    const state = _testParseHash("#/filed");
    expect(state.route).toBe("filed");
    expect(state.hash).toBe("#/filed");
  });

  it("maps '#/run/<source>/<state_key>/<run_id>' to run with params", () => {
    const state = _testParseHash("#/run/linkedin/some-key/42");
    expect(state.route).toBe("run");
    expect(state.params).toEqual({
      source: "linkedin",
      state_key: "some-key",
      run_id: "42"
    });
  });

  it("decodes URL-encoded state_key segments in run params", () => {
    const state = _testParseHash(
      "#/run/linkedin/" + encodeURIComponent("brief with spaces") + "/7"
    );
    expect(state.route).toBe("run");
    expect(state.params.state_key).toBe("brief with spaces");
  });

  it("falls back to unknown for malformed run hashes", () => {
    const a = _testParseHash("#/run/linkedin/missing-id");
    expect(a.route).toBe("unknown");
    const b = _testParseHash("#/run//state/1");
    expect(b.route).toBe("unknown");
  });
});

describe("router — navigate + store wiring", () => {
  it("startRouter() updates currentRoute when the hash changes", () => {
    const unsubscribe = startRouter();
    try {
      navigate("#/brief/new");
      expect(get(currentRoute).route).toBe("brief-new");
      expect(get(currentRoute).hash).toBe("#/brief/new");

      navigate("#/");
      expect(get(currentRoute).route).toBe("home");
    } finally {
      unsubscribe();
    }
  });

  it("startRouter()'s unsubscriber stops further updates", () => {
    const unsubscribe = startRouter();
    navigate("#/brief/new");
    expect(get(currentRoute).route).toBe("brief-new");

    unsubscribe();

    // After unsubscribing, the store should not pick up later hash
    // changes. We mutate window.location.hash directly (bypassing
    // navigate, which would also be a no-op as a setter — but we want
    // to assert specifically that the hashchange listener is gone).
    window.location.hash = "#/";
    // The store still holds the last-set value; it MUST NOT have moved
    // back to "home" via the (now-detached) listener.
    expect(get(currentRoute).route).toBe("brief-new");
  });

  it("navigate() to an unknown hash routes to unknown", () => {
    const unsubscribe = startRouter();
    try {
      navigate("#/does-not-exist");
      expect(get(currentRoute).route).toBe("unknown");
    } finally {
      unsubscribe();
    }
  });

  it("startRouter() synchronizes the store with the current hash on attach", () => {
    // Set the hash BEFORE startRouter runs. The store's initial value was
    // captured at module load (likely "#/"), but startRouter should
    // re-sync so the first render after attach matches the URL.
    window.location.hash = "#/brief/new";
    const unsubscribe = startRouter();
    try {
      expect(get(currentRoute).route).toBe("brief-new");
    } finally {
      unsubscribe();
    }
  });
});
