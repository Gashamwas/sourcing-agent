// Monitoring tests — the WAITING loader (R19 revised, four-kind contract).

import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";

import Monitoring from "../Monitoring.svelte";
import { loaderAnchorWaiting } from "../../lib/copy";

describe("Monitoring", () => {
  it("renders the CRT body + screen + scanline + phosphor", () => {
    const { container } = render(Monitoring, { props: { size: "small" } });
    expect(container.querySelector(".monitoring-stage--small")).not.toBeNull();
    expect(container.querySelector(".monitoring-screen")).not.toBeNull();
    expect(container.querySelector(".monitoring-scanline")).not.toBeNull();
    expect(container.querySelector(".monitoring-phosphor")).not.toBeNull();
  });

  it("defaults to the WAITING anchor when no caption is passed", () => {
    const { container } = render(Monitoring);
    expect(container.textContent).toContain(loaderAnchorWaiting);
    expect(
      container.querySelector(".monitoring-stage")?.getAttribute("aria-label")
    ).toBe(loaderAnchorWaiting);
  });

  it("renders a single-string caption with aria-label", () => {
    const { container } = render(Monitoring, {
      props: { captions: "Tuned in to the run\u2026" },
    });
    expect(container.textContent).toContain("Tuned in to the run\u2026");
    expect(
      container.querySelector(".monitoring-stage")?.getAttribute("aria-label")
    ).toBe("Tuned in to the run\u2026");
  });

  it("decorative when captions is an empty array", () => {
    const { container } = render(Monitoring, { props: { captions: [] } });
    expect(
      container.querySelector(".monitoring-stage")?.getAttribute("aria-hidden")
    ).toBe("true");
  });
});
