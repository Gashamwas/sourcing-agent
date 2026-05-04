// Cloris frontend router — minimal hand-rolled hash-based router (Slice 1
// of the onboarding flow plan, governing decision G3).
//
// Why hash-based:
//   - Works under pywebview without server-side rewrite rules. pywebview
//     loads `index.html` directly via file:// or a local handler; pushState
//     paths would 404 on reload.
//   - Degrades gracefully — pre-mount HTML still renders even if JS errors
//     during route resolution.
//   - Hash changes do not trigger a network fetch, so transitions are
//     instant and free of the SPA boilerplate (history guards, scroll
//     restoration, etc.) that we don't need yet.
//
// Why hand-rolled:
//   - Two routes (home + brief-new). A library would be net cost.
//   - Fewer moving parts → easier to reason about during a slice.
//
// Wire shape: a single `currentRoute` writable. Components read it
// reactively; `navigate(hash)` mutates `window.location.hash`, the
// hashchange listener parses, and the store updates. This means
// programmatic and user-driven (URL bar, back/forward) navigation funnel
// through the same code path — there's only one source of truth.
//
// SSR / test guard: every `window`/`document` access is gated by
// `typeof window !== "undefined"` so importing this module under jsdom or
// happy-dom with no globals (or under a hypothetical SSR pass) does not
// throw. The test environment in Vitest does have `window`, but parseHash
// + the initial store value still need to handle the no-window branch
// for safety.

import { writable } from "svelte/store";

// Six real routes plus two legacy synonyms (for redirect-on-mount) plus a
// sentinel for unknown hashes. Phase C-bis 0.1 pivoted workspace +
// candidate-detail to brief-first URLs; the legacy synonyms catch old
// bookmarks and redirect transparently via App.svelte.
//   home              → the verb-tile homescreen + in-motion mini-list
//   filed             → The Quiet Drawer (full filed-away browse + find input)
//   briefs            → brief library (Phase D Slice D1)
//   brief-detail      → per-brief detail/edit (Phase D Slice D2; param: brief_id)
//   brief-new         → onboarding flow for composing a new brief
//   run               → per-run report (params: source, state_key, run_id)
//   workspace         → per-brief workspace (params: brief_id)
//   candidate         → per-candidate detail (params: brief_id, candidate_id)
//   workspace-legacy  → legacy 2-segment workspace URL; redirects to brief-first
//   candidate-legacy  → legacy 3-segment candidate URL; redirects to brief-first
export type Route =
  | "home"
  | "filed"
  | "briefs"
  | "brief-detail"
  | "brief-new"
  | "drafts"
  | "run"
  | "workspace"
  | "candidate"
  | "workspace-legacy"
  | "candidate-legacy"
  // Phase E Slice E1: market viewer + per-market detail.
  | "market"
  | "market-detail"
  // Phase E Slice E2: refresh-brief flow against a market.
  | "refresh-brief"
  // Phase G Slice G2: identity reconciliation surface (sub-route of
  // workspace because pending merge decisions are brief-scoped).
  | "workspace-identity"
  // Phase G Slice G3: Live Monitor — operational view of active runs.
  | "monitor"
  | "monitor-run"
  // Phase G Slice G4: Tools index.
  | "tools"
  // Phase G Slice G5: Settings transparency surface.
  | "settings"
  // The Reflection — HITL market intelligence at
  // #/workspace/<brief_id>/reflect (optional ?session=<id>,
  // ?from_run=<run_id>, ?run_dir=<path> query params).
  | "reflect"
  | "unknown";

export interface RouteState {
  // Logical route id, used for switch/case in App.svelte.
  route: Route;
  // Raw hash string ("" or "#/..."). Stored so future code can recover the
  // exact navigation target, e.g. for deep-linking back into the URL bar.
  hash: string;
  // Reserved for future route params (e.g., a brief id in `#/brief/abc123`).
  // Empty for the v1 routes; kept on the type so adding params later is a
  // pure additive change at call sites.
  params: Record<string, string>;
}

function getCurrentHash(): string {
  return typeof window !== "undefined" ? window.location.hash : "";
}

// Parse a raw hash into the structured route state. Pure — no DOM or store
// reads — so it's trivially testable and safe to call during module init.
function parseHash(hash: string): RouteState {
  // Empty hash (initial page load with no fragment) and the bare "#/" both
  // mean "the home/ledger surface". We normalize them to the same route id
  // but preserve the original hash so the URL bar isn't rewritten.
  if (hash === "" || hash === "#" || hash === "#/") {
    return { route: "home", hash, params: {} };
  }
  if (hash === "#/filed") {
    return { route: "filed", hash, params: {} };
  }
  // Phase D Slice D1: brief library at `#/briefs`. Lives next to
  // brief-new so the recruiter can flip between "browse what I've
  // authored" and "author a new one" with predictable URLs.
  if (hash === "#/briefs") {
    return { route: "briefs", hash, params: {} };
  }
  // Phase D Slice D3 + D4: brief-new accepts an optional `?draft=<id>`
  // query suffix so the drafts list can deep-link a specific
  // in-flight session. We split on `?` so both `#/brief/new` and
  // `#/brief/new?draft=42` route to brief-new; the wizard reads the
  // draft param off route state.
  if (hash === "#/brief/new" || hash.startsWith("#/brief/new?")) {
    const queryIdx = hash.indexOf("?");
    const params: Record<string, string> = {};
    if (queryIdx !== -1) {
      const raw = hash.slice(queryIdx + 1);
      for (const pair of raw.split("&")) {
        if (!pair) continue;
        const eq = pair.indexOf("=");
        if (eq === -1) continue;
        const key = decodeURIComponent(pair.slice(0, eq));
        const val = decodeURIComponent(pair.slice(eq + 1));
        if (key) params[key] = val;
      }
    }
    return { route: "brief-new", hash, params };
  }
  // Phase D Slice D4: drafts list. Recruiter can resume an
  // unfinished intake or delete one. Lives at the plural `#/drafts`
  // because each session is a draft brief; the singular `#/brief/new`
  // is the wizard entry point itself.
  if (hash === "#/drafts") {
    return { route: "drafts", hash, params: {} };
  }
  // Phase D Slice D2: per-brief detail at `#/brief/<brief_id>`. The
  // brief_id is opaque (linkedin_state_key hash); we decode but don't
  // structurally validate. "new" is reserved for the intake flow above.
  if (hash.startsWith("#/brief/")) {
    const tail = hash.slice("#/brief/".length);
    const parts = tail.split("/");
    if (parts.length === 1 && parts[0] && parts[0] !== "new") {
      return {
        route: "brief-detail",
        hash,
        params: { brief_id: decodeURIComponent(parts[0]) }
      };
    }
  }
  // Per-run report: #/run/<source>/<state_key>/<run_id>. State_key is
  // an arbitrary directory slug that may legitimately contain hyphens
  // and underscores; we decode it but otherwise leave it opaque. The
  // run_id stays a string here — the page parses to int.
  if (hash.startsWith("#/run/")) {
    const tail = hash.slice("#/run/".length);
    const parts = tail.split("/");
    if (parts.length === 3 && parts[0] && parts[1] && parts[2]) {
      return {
        route: "run",
        hash,
        params: {
          source: decodeURIComponent(parts[0]),
          state_key: decodeURIComponent(parts[1]),
          run_id: decodeURIComponent(parts[2])
        }
      };
    }
  }
  // Per-brief workspace (Phase C-bis 0.1, brief-first):
  //   #/workspace/<brief_id>            → 1 segment, current
  //   #/workspace/<brief_id>/identity   → 2 segments, G2 reconciliation
  //   #/workspace/<brief_id>/reflect    → 2 segments, Reflection HITL
  //                                       (optional ?session=<id>,
  //                                       ?from_run=<run_id>,
  //                                       ?run_dir=<path>)
  //   #/workspace/<source>/<state_key>  → 2 segments, legacy (redirect)
  // Order: identity / reflect checks before legacy because all three
  // are 2-segment.
  if (hash.startsWith("#/workspace/")) {
    // Strip query string before splitting segments, but preserve it
    // for query-param parsing on the reflect route.
    const queryIdx = hash.indexOf("?");
    const beforeQuery = queryIdx === -1 ? hash : hash.slice(0, queryIdx);
    const queryStr = queryIdx === -1 ? "" : hash.slice(queryIdx + 1);
    const queryParams: Record<string, string> = {};
    if (queryStr) {
      for (const pair of queryStr.split("&")) {
        if (!pair) continue;
        const eq = pair.indexOf("=");
        if (eq === -1) continue;
        const key = decodeURIComponent(pair.slice(0, eq));
        const val = decodeURIComponent(pair.slice(eq + 1));
        if (key) queryParams[key] = val;
      }
    }
    const tail = beforeQuery.slice("#/workspace/".length);
    const parts = tail.split("/");
    if (parts.length === 1 && parts[0]) {
      return {
        route: "workspace",
        hash,
        params: {
          brief_id: decodeURIComponent(parts[0])
        }
      };
    }
    if (parts.length === 2 && parts[0] && parts[1] === "identity") {
      return {
        route: "workspace-identity",
        hash,
        params: {
          brief_id: decodeURIComponent(parts[0])
        }
      };
    }
    if (parts.length === 2 && parts[0] && parts[1] === "reflect") {
      return {
        route: "reflect",
        hash,
        params: {
          brief_id: decodeURIComponent(parts[0]),
          ...queryParams,
        }
      };
    }
    if (parts.length === 2 && parts[0] && parts[1]) {
      return {
        route: "workspace-legacy",
        hash,
        params: {
          source: decodeURIComponent(parts[0]),
          state_key: decodeURIComponent(parts[1])
        }
      };
    }
  }
  // Phase G Slice G4: Tools index.
  if (hash === "#/tools") {
    return { route: "tools", hash, params: {} };
  }
  // Phase G Slice G5: Settings transparency surface.
  if (hash === "#/settings") {
    return { route: "settings", hash, params: {} };
  }
  // Phase G Slice G3: Live Monitor.
  //   #/monitor                                          → index
  //   #/monitor/<source>/<state_key>/<run_id>            → per-run detail
  if (hash === "#/monitor") {
    return { route: "monitor", hash, params: {} };
  }
  if (hash.startsWith("#/monitor/")) {
    const tail = hash.slice("#/monitor/".length);
    const parts = tail.split("/");
    if (parts.length === 3 && parts[0] && parts[1] && parts[2]) {
      return {
        route: "monitor-run",
        hash,
        params: {
          source: decodeURIComponent(parts[0]),
          state_key: decodeURIComponent(parts[1]),
          run_id: decodeURIComponent(parts[2]),
        },
      };
    }
  }
  // Phase E Slice E1: market catalog + per-market detail.
  //   #/market                  → catalog list
  //   #/market/<market_key>     → per-market detail
  if (hash === "#/market") {
    return { route: "market", hash, params: {} };
  }
  if (hash.startsWith("#/market/")) {
    const tail = hash.slice("#/market/".length);
    const parts = tail.split("/");
    if (parts.length === 1 && parts[0]) {
      return {
        route: "market-detail",
        hash,
        params: { market_key: decodeURIComponent(parts[0]) }
      };
    }
  }
  // Phase E Slice E2: refresh-brief flow. Optional `?market=<key>`
  // pre-filters the picker; bare `#/refresh-brief` lets the recruiter
  // pick any brief.
  if (hash === "#/refresh-brief" || hash.startsWith("#/refresh-brief?")) {
    const queryIdx = hash.indexOf("?");
    const params: Record<string, string> = {};
    if (queryIdx !== -1) {
      const raw = hash.slice(queryIdx + 1);
      for (const pair of raw.split("&")) {
        if (!pair) continue;
        const eq = pair.indexOf("=");
        if (eq === -1) continue;
        const key = decodeURIComponent(pair.slice(0, eq));
        const val = decodeURIComponent(pair.slice(eq + 1));
        if (key) params[key] = val;
      }
    }
    return { route: "refresh-brief", hash, params };
  }
  // Per-candidate detail (Phase C-bis 0.1, brief-first):
  //   #/candidate/<brief_id>/<candidate_id>            → 2 segments, current
  //   #/candidate/<source>/<state_key>/<candidate_id>  → 3 segments, legacy (redirect)
  if (hash.startsWith("#/candidate/")) {
    const tail = hash.slice("#/candidate/".length);
    const parts = tail.split("/");
    if (parts.length === 2 && parts[0] && parts[1]) {
      return {
        route: "candidate",
        hash,
        params: {
          brief_id: decodeURIComponent(parts[0]),
          candidate_id: decodeURIComponent(parts[1])
        }
      };
    }
    if (parts.length === 3 && parts[0] && parts[1] && parts[2]) {
      return {
        route: "candidate-legacy",
        hash,
        params: {
          source: decodeURIComponent(parts[0]),
          state_key: decodeURIComponent(parts[1]),
          candidate_id: decodeURIComponent(parts[2])
        }
      };
    }
  }
  return { route: "unknown", hash, params: {} };
}

// Module-scoped store. Initialized synchronously from the current hash so
// the first render of App.svelte already knows which route to mount,
// avoiding a one-frame "home then brief-new" flash on direct navigation.
export const currentRoute = writable<RouteState>(parseHash(getCurrentHash()));

// Programmatic navigation. Mutating `window.location.hash` triggers the
// hashchange listener registered by `startRouter`, which is what actually
// updates the store — so this function is intentionally minimal. Callers
// can use plain `<a href="#/...">` for declarative links; `navigate` is
// here for cases where the router needs to be driven from JS (e.g., after
// a form submit completes).
export function navigate(hash: string): void {
  if (typeof window === "undefined") return;
  // Setting the hash to its current value is a no-op in browsers and does
  // not fire hashchange. We accept that — callers who really want to force
  // a re-emit should write to the store directly.
  window.location.hash = hash;
}

// Attach the hashchange listener and return an unsubscriber. Designed to
// be invoked from App.svelte's `onMount` and the unsubscriber called from
// `onDestroy`. We don't auto-attach at import time because that would tie
// the listener's lifetime to the module (i.e. the whole tab) rather than
// the App component, which is harder to reason about in tests.
export function startRouter(): () => void {
  if (typeof window === "undefined") {
    // No-op unsubscriber. Keeps the API symmetric in SSR / non-browser
    // tests so callers don't need a `typeof window` guard at the call site.
    return () => {};
  }

  const onHashChange = (): void => {
    currentRoute.set(parseHash(window.location.hash));
  };

  window.addEventListener("hashchange", onHashChange);

  // Synchronize once on attach: if the hash changed between module init
  // and `startRouter()` being called (e.g. a deep link arrived during
  // mount), this brings the store back into agreement with the URL.
  currentRoute.set(parseHash(window.location.hash));

  return () => {
    window.removeEventListener("hashchange", onHashChange);
  };
}

// Test-only helpers. Underscore prefix marks them as non-production API.
// `_testParseHash` exposes the parser for unit tests; `_testResetRoute`
// resets the store between tests so module-scoped state doesn't leak.
export function _testParseHash(hash: string): RouteState {
  return parseHash(hash);
}

export function _testResetRoute(): void {
  currentRoute.set(parseHash(getCurrentHash()));
}
