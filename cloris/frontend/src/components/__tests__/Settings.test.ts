// Settings tests — Phase G Slice G5.
//
// Pins:
//   - Renders ✓ for present credentials, ✗ for missing.
//   - Governor section renders read-only with explainers.
//   - Save destinations section renders one row per brief.
//   - NEVER renders raw credential values (only ✓/✗ marks).

import { render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";

import Settings from "../Settings.svelte";
import type { SettingsResponse } from "../../lib/types";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>(
    "../../lib/api"
  );
  return {
    ...actual,
    getSettings: vi.fn(),
  };
});

import { getSettings } from "../../lib/api";

const mocked = {
  get: getSettings as unknown as ReturnType<typeof vi.fn>,
};

beforeEach(() => {
  mocked.get.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function flushMicrotasks(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

function makeSettings(
  overrides: Partial<SettingsResponse> = {}
): SettingsResponse {
  return {
    slice: "v0-settings-1",
    credentials: [],
    save_destinations: [],
    governor: [],
    cdp_url: "http://127.0.0.1:9222",
    ...overrides,
  };
}

describe("Settings — credentials section", () => {
  it("renders ✓ for present credentials and ✗ for missing", async () => {
    mocked.get.mockResolvedValue(
      makeSettings({
        credentials: [
          { key: "anthropic_api_key", label: "Anthropic", present: true, pitch: "Cloris uses Claude." },
          { key: "openai_api_key", label: "OpenAI", present: false, pitch: "OpenAI fallback." },
        ],
      })
    );
    const { container } = render(Settings);
    await flushMicrotasks();

    const ok = container.querySelector(".settings-mark--ok");
    const missing = container.querySelector(".settings-mark--missing");
    expect(ok?.textContent?.trim()).toBe("✓");
    expect(missing?.textContent?.trim()).toBe("✗");
  });

  it("never renders raw credential values to the DOM", async () => {
    // The wire shape is boolean-only by design; this test pins that the
    // component doesn't accidentally try to render a value field.
    mocked.get.mockResolvedValue(
      makeSettings({
        credentials: [
          { key: "anthropic_api_key", label: "Anthropic", present: true, pitch: "Cloris uses Claude." },
        ],
      })
    );
    const { container } = render(Settings);
    await flushMicrotasks();
    expect(container.textContent).not.toMatch(/sk-/);
    expect(container.textContent).not.toMatch(/AKIA/);
  });
});

describe("Settings — governor section", () => {
  it("renders one row per governor limit with explainer", async () => {
    mocked.get.mockResolvedValue(
      makeSettings({
        governor: [
          {
            name: "MAX_PROFILE_OPENS_PER_SESSION",
            label: "Profiles per session",
            value: 200,
            explainer: "Tuned for safe LinkedIn cadence.",
          },
          {
            name: "MAX_SESSIONS_PER_DAY",
            label: "Sessions per day",
            value: 3,
            explainer: "Hard cap.",
          },
        ],
      })
    );
    const { container } = render(Settings);
    await flushMicrotasks();
    expect(
      container.querySelectorAll(".settings-row[data-governor]").length
    ).toBe(2);
    expect(container.textContent).toContain("Tuned for safe LinkedIn cadence");
  });
});

describe("Settings — save destinations section", () => {
  it("renders one row per brief with target modules + linkedin project", async () => {
    mocked.get.mockResolvedValue(
      makeSettings({
        save_destinations: [
          {
            brief_id: "brief-fde",
            role_title: "FDE",
            target_modules: ["linkedin", "github"],
            linkedin_project_id: "proj-1",
          },
        ],
      })
    );
    const { container } = render(Settings);
    await flushMicrotasks();
    expect(
      container.querySelectorAll(".settings-row[data-brief-id]").length
    ).toBe(1);
    expect(container.textContent).toContain("linkedin, github");
    expect(container.textContent).toContain("proj-1");
  });
});
