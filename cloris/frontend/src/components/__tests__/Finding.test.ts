// Finding tests — the SEARCHING loader (R19 revised, four-kind contract).
//
// Mirrors the Refining / Learning / Monitoring test shape so the four
// loader components stay parallel. Pre-revision Finding randomly
// dispatched among kettle / sewing / tv / glasses and ignored the
// captions prop; that behavior is gone — Finding is now glasses-only
// with the SEARCHING anchor as the captions default.

import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";

import Finding from "../Finding.svelte";
import { loaderAnchorSearching } from "../../lib/copy";

describe("Finding", () => {
  it("renders the glasses + magnifier SVG with the size class", () => {
    const { container } = render(Finding, { props: { size: "small" } });
    expect(container.querySelector(".finding-stage--small")).not.toBeNull();
    expect(container.querySelector(".finding-svg")).not.toBeNull();
    expect(container.querySelector(".finding-target")).not.toBeNull();
    expect(container.querySelector(".finding-magnifier")).not.toBeNull();
  });

  it("defaults to the SEARCHING anchor when no caption is passed", () => {
    const { container } = render(Finding);
    expect(container.textContent).toContain(loaderAnchorSearching);
    expect(
      container.querySelector(".finding-stage")?.getAttribute("aria-label")
    ).toBe(loaderAnchorSearching);
  });

  it("renders a single-string caption with aria-label", () => {
    const { container } = render(Finding, {
      props: { captions: "Hunting through the archive\u2026" },
    });
    expect(container.textContent).toContain("Hunting through the archive\u2026");
    expect(
      container.querySelector(".finding-stage")?.getAttribute("aria-label")
    ).toBe("Hunting through the archive\u2026");
  });

  it("renders a rotating caption set", () => {
    const { container } = render(Finding, {
      props: { captions: ["First line\u2026", "Second line\u2026", "Third line\u2026"] },
    });
    // The first caption renders initially (RotatingCaption holds it
    // before the first interval tick).
    expect(container.textContent).toContain("First line\u2026");
  });

  it("decorative when captions is an empty array", () => {
    const { container } = render(Finding, { props: { captions: [] } });
    expect(
      container.querySelector(".finding-stage")?.getAttribute("aria-hidden")
    ).toBe("true");
    expect(container.querySelector(".finding-caption")).toBeNull();
  });

  it("applies the finishing class when finishing=true", () => {
    const { container } = render(Finding, { props: { finishing: true } });
    expect(
      container.querySelector(".finding-stage--finishing")
    ).not.toBeNull();
  });
});
