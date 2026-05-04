// Refining tests — the CREATING loader (R19 revised, four-kind contract).

import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";

import Refining from "../Refining.svelte";
import { loaderAnchorCreating } from "../../lib/copy";

describe("Refining", () => {
  it("renders the needles + yarn SVG with the size class", () => {
    const { container } = render(Refining, { props: { size: "small" } });
    expect(container.querySelector(".refining-stage--small")).not.toBeNull();
    expect(container.querySelector(".refining-yarn")).not.toBeNull();
    expect(container.querySelector(".refining-needle-1")).not.toBeNull();
    expect(container.querySelector(".refining-needle-2")).not.toBeNull();
  });

  it("defaults to the CREATING anchor when no caption is passed", () => {
    const { container } = render(Refining);
    expect(container.textContent).toContain(loaderAnchorCreating);
    expect(
      container.querySelector(".refining-stage")?.getAttribute("aria-label")
    ).toBe(loaderAnchorCreating);
  });

  it("renders a single-string caption and exposes it as aria-label", () => {
    const { container } = render(Refining, {
      props: { captions: "Refining the brief\u2026" },
    });
    expect(container.textContent).toContain("Refining the brief\u2026");
    expect(
      container.querySelector(".refining-stage")?.getAttribute("aria-label")
    ).toBe("Refining the brief\u2026");
  });

  it("decorative when captions is an empty array", () => {
    const { container } = render(Refining, { props: { captions: [] } });
    expect(
      container.querySelector(".refining-stage")?.getAttribute("aria-hidden")
    ).toBe("true");
  });
});
