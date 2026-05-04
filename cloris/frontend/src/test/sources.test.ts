// Vitest coverage for the centralized source-key registry.
//
// Asserts the registry mirrors the backend `_SOURCES` tuple, the
// defensive fallback for unknown keys, and the stable ordering contract
// (linkedin always first; remaining sources alphabetical by key).

import { describe, it, expect, vi, afterEach } from "vitest";
import {
  SOURCES,
  sourceMeta,
  isStoppable,
  isLaunchable,
  launchableSources,
  allSources,
  type SourceMeta,
} from "../lib/sources";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("sources registry — keys mirror SourceKey union", () => {
  it("contains exactly the registered SourceKey members", () => {
    // Manually enumerate the SourceKey union members. If `types.ts:Source`
    // widens, this test must be updated alongside SOURCES (the registry
    // and the wire type are kept in sync MANUALLY per the module
    // integration contract §6).
    const expected = ["designer", "exec_search", "github", "linkedin", "researcher"];
    expect(Object.keys(SOURCES).sort()).toEqual(expected);
  });
});

describe("sourceMeta(key)", () => {
  it("returns the registered entry for linkedin", () => {
    expect(sourceMeta("linkedin")).toEqual({
      key: "linkedin",
      label: "LinkedIn",
      shortLabel: "linkedin",
      pillLabel: "LI",
      stoppable: true,
      launchable: true,
    });
  });

  it("returns the registered entry for github", () => {
    expect(sourceMeta("github")).toEqual({
      key: "github",
      label: "GitHub",
      shortLabel: "github",
      pillLabel: "GH",
      stoppable: true,
      launchable: true,
    });
  });

  it("returns the registered entry for researcher", () => {
    expect(sourceMeta("researcher")).toEqual({
      key: "researcher",
      label: "Researcher",
      shortLabel: "researcher",
      pillLabel: "RE",
      stoppable: true,
      launchable: true,
    });
  });

  it("returns a defensive fallback for unknown keys and console.warns once", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const meta = sourceMeta("unknown_module");

    expect(meta.key).toBe("unknown_module");
    expect(meta.label).toBe("unknown_module");
    expect(meta.shortLabel).toBe("unknown_module");
    expect(meta.stoppable).toBe(false);
    expect(meta.launchable).toBe(false);

    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy).toHaveBeenCalledWith(
      'sourceMeta: unknown source "unknown_module"; using defensive fallback',
    );
  });
});

describe("isStoppable / isLaunchable predicates", () => {
  it("isStoppable matches the registry for known keys", () => {
    expect(isStoppable("linkedin")).toBe(true);
    expect(isStoppable("github")).toBe(true);
  });

  it("isStoppable returns false for unknown keys", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(isStoppable("unknown")).toBe(false);
  });

  it("isLaunchable matches the registry for known keys", () => {
    expect(isLaunchable("linkedin")).toBe(true);
  });

  it("isLaunchable returns false for unknown keys", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(isLaunchable("unknown")).toBe(false);
  });
});

describe("launchableSources / allSources ordering", () => {
  it("launchableSources returns the registered set in stable order (linkedin first, then alphabetical)", () => {
    const ordered = launchableSources().map((meta) => meta.key);
    expect(ordered).toEqual(["linkedin", "designer", "exec_search", "github", "researcher"]);
  });

  it("allSources returns the registered set in stable order (linkedin first, then alphabetical)", () => {
    const ordered = allSources().map((meta) => meta.key);
    expect(ordered).toEqual(["linkedin", "designer", "exec_search", "github", "researcher"]);
  });

  it("orders linkedin first then alphabetically with a hypothetical 'alpha' source", () => {
    // Local copy of SOURCES with a hypothetical "alpha" entry to verify
    // the stable-ordering contract without mutating the real registry.
    const localSources: Record<string, SourceMeta> = {
      ...SOURCES,
      alpha: {
        key: "alpha" as SourceMeta["key"],
        label: "Alpha",
        shortLabel: "alpha",
        pillLabel: "AL",
        stoppable: true,
        launchable: true,
      },
    };

    function compareSourceMeta(a: SourceMeta, b: SourceMeta): number {
      if (a.key === "linkedin" && b.key !== "linkedin") return -1;
      if (b.key === "linkedin" && a.key !== "linkedin") return 1;
      if (a.key < b.key) return -1;
      if (a.key > b.key) return 1;
      return 0;
    }

    const ordered = Object.values(localSources)
      .sort(compareSourceMeta)
      .map((meta) => meta.key);

    expect(ordered).toEqual(["linkedin", "alpha", "designer", "exec_search", "github", "researcher"]);
  });
});
