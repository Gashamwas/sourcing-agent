// JudgmentAccuracyToggle tests — Phase D Slice D6 (Ledger L1).
//
// Pins the contract of the closed-loop calibration toggle:
// - Renders three buttons (Useful / Wrong / Doesn't fit the brief).
// - Clicking an inactive button fires onChange with that value.
// - Clicking the active button fires onChange with null (clear).
// - Renders a "Clear feedback" affordance ONLY when judgmentAccuracy is set.
// - Disabled prop blocks all interactions; disabledReason renders italic.
// - Error during onChange surfaces an editorial error line.
//
// Plan Finding 18 retired the help line ("Tell Cloris what to learn
// from on the next run.") and renamed the question label
// ("How was Cloris's judgment?" → "Was this the right call?") so the
// toggle reads as a per-candidate question, not a performance review of
// Cloris. The "Off rubric" button label was renamed to
// "Doesn't fit the brief" — recruiter-readable rather than calibration
// vocabulary. The schema value (off_rubric) is unchanged.

import { render, fireEvent } from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import JudgmentAccuracyToggle from "../JudgmentAccuracyToggle.svelte";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("JudgmentAccuracyToggle — render", () => {
  it("renders the editorial question label and no help line", () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    const { container } = render(JudgmentAccuracyToggle, {
      judgmentAccuracy: null,
      onChange
    });
    // Plan Finding 18: per-candidate question, not "Cloris's judgment".
    expect(
      container.querySelector(".judgment-toggle-label")?.textContent
    ).toBe("Was this the right call?");
    // Plan Finding 18: help line dropped (process-narration about
    // Cloris's training loop). The buttons themselves are the action.
    expect(container.querySelector(".judgment-toggle-help")).toBeNull();
  });

  it("renders three buttons (Useful / Wrong / Doesn't fit the brief)", () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    const { container } = render(JudgmentAccuracyToggle, {
      judgmentAccuracy: null,
      onChange
    });
    const buttons = container.querySelectorAll(".judgment-toggle-button");
    expect(buttons).toHaveLength(3);
    const labels = Array.from(buttons).map((b) => b.textContent?.trim());
    // Plan Finding 18: "Off rubric" → "Doesn't fit the brief"
    // (recruiter-readable vs. calibration vocabulary). Schema value
    // (off_rubric) is unchanged.
    expect(labels).toEqual(["Useful", "Wrong", "Doesn't fit the brief"]);
  });

  it("marks the active button with --active when judgmentAccuracy matches", () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    const { container } = render(JudgmentAccuracyToggle, {
      judgmentAccuracy: "useful",
      onChange
    });
    const buttons = container.querySelectorAll(".judgment-toggle-button");
    expect(
      buttons[0].classList.contains("judgment-toggle-button--active")
    ).toBe(true);
    expect(buttons[0].getAttribute("aria-pressed")).toBe("true");
    expect(
      buttons[1].classList.contains("judgment-toggle-button--active")
    ).toBe(false);
  });

  it("does NOT render Clear when judgmentAccuracy is null", () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    const { container } = render(JudgmentAccuracyToggle, {
      judgmentAccuracy: null,
      onChange
    });
    expect(container.querySelector(".judgment-toggle-clear")).toBeNull();
  });

  it("renders Clear when judgmentAccuracy is set", () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    const { container } = render(JudgmentAccuracyToggle, {
      judgmentAccuracy: "wrong",
      onChange
    });
    expect(
      container.querySelector(".judgment-toggle-clear")?.textContent
    ).toBe("Clear feedback");
  });
});

describe("JudgmentAccuracyToggle — interaction", () => {
  it("clicking an inactive button fires onChange with that value", async () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    const { container } = render(JudgmentAccuracyToggle, {
      judgmentAccuracy: null,
      onChange
    });
    const buttons = container.querySelectorAll(".judgment-toggle-button");
    await fireEvent.click(buttons[1]); // Wrong
    expect(onChange).toHaveBeenCalledWith("wrong");
  });

  it("clicking the active button fires onChange with null (toggle off)", async () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    const { container } = render(JudgmentAccuracyToggle, {
      judgmentAccuracy: "useful",
      onChange
    });
    const buttons = container.querySelectorAll(".judgment-toggle-button");
    await fireEvent.click(buttons[0]); // Useful (currently active)
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("clicking Clear fires onChange with null", async () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    const { container } = render(JudgmentAccuracyToggle, {
      judgmentAccuracy: "off_rubric",
      onChange
    });
    const clear = container.querySelector(
      ".judgment-toggle-clear"
    ) as HTMLButtonElement;
    await fireEvent.click(clear);
    expect(onChange).toHaveBeenCalledWith(null);
  });
});

describe("JudgmentAccuracyToggle — disabled + error", () => {
  it("disabled buttons don't fire onChange", async () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    const { container } = render(JudgmentAccuracyToggle, {
      judgmentAccuracy: null,
      onChange,
      disabled: true,
      disabledReason: "Cloris failed to evaluate this candidate."
    });
    const buttons = container.querySelectorAll(".judgment-toggle-button");
    await fireEvent.click(buttons[0]);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("renders disabledReason as italic note when disabled", () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    const { container } = render(JudgmentAccuracyToggle, {
      judgmentAccuracy: null,
      onChange,
      disabled: true,
      disabledReason: "Cloris failed to evaluate this candidate."
    });
    expect(
      container.querySelector(".judgment-toggle-disabled-note")?.textContent
    ).toContain("Cloris failed to evaluate");
  });

  it("renders an error line when onChange rejects", async () => {
    const onChange = vi.fn().mockRejectedValue(new Error("boom"));
    const { container } = render(JudgmentAccuracyToggle, {
      judgmentAccuracy: null,
      onChange
    });
    const buttons = container.querySelectorAll(".judgment-toggle-button");
    await fireEvent.click(buttons[0]);
    // Two ticks for the rejected promise to resolve and re-render.
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(
      container.querySelector(".judgment-toggle-error")?.textContent
    ).toContain("Couldn't save");
  });
});
