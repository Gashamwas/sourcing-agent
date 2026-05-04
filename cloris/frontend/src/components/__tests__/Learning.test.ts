// Learning tests — the INITIALIZING loader (R19 revised, four-kind contract).

import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";

import Learning from "../Learning.svelte";
import { loaderAnchorInitializing } from "../../lib/copy";

describe("Learning", () => {
  it("renders the kettle + three steam puffs", () => {
    const { container } = render(Learning, { props: { size: "medium" } });
    expect(container.querySelector(".learning-stage--medium")).not.toBeNull();
    expect(container.querySelectorAll(".learning-steam-puff").length).toBe(3);
  });

  it("defaults to the INITIALIZING anchor when no caption is passed", () => {
    const { container } = render(Learning);
    expect(container.textContent).toContain(loaderAnchorInitializing);
    expect(
      container.querySelector(".learning-stage")?.getAttribute("aria-label")
    ).toBe(loaderAnchorInitializing);
  });

  it("renders a single-string caption with aria-label", () => {
    const { container } = render(Learning, {
      props: { captions: "Brewing market intelligence\u2026" },
    });
    expect(container.textContent).toContain("Brewing market intelligence\u2026");
    expect(
      container.querySelector(".learning-stage")?.getAttribute("aria-label")
    ).toBe("Brewing market intelligence\u2026");
  });

  it("decorative when captions is an empty array", () => {
    const { container } = render(Learning, { props: { captions: [] } });
    expect(
      container.querySelector(".learning-stage")?.getAttribute("aria-hidden")
    ).toBe("true");
  });
});
