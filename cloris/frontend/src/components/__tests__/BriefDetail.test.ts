// BriefDetail "Where Cloris saves" section — Phase F Slice F2.
//
// Pins the F2 surface contract on BriefDetail.svelte:
// - Renders one row per `target_modules` (defaults to ["linkedin"]
//   when target_modules is absent).
// - LinkedIn row reads source_config.linkedin.project_id when present;
//   falls back to flat linkedin_project_id; renders missing italic
//   prose cue when neither is set.
// - GitHub row renders the "no destination needed" prose cue.
// - The deprecated/unknown drawer doesn't double-list source_config.

import { vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect } from "vitest";

import BriefDetail from "../BriefDetail.svelte";
import type {
  BriefDetailResponse,
  BriefVersionsResponse
} from "../../lib/types";

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    getBrief: vi.fn(),
    getBriefVersions: vi.fn(),
    putBrief: vi.fn()
  };
});

import { getBrief, getBriefVersions, putBrief } from "../../lib/api";

const briefMock = getBrief as unknown as ReturnType<typeof vi.fn>;
const versionsMock = getBriefVersions as unknown as ReturnType<typeof vi.fn>;
const putBriefMock = putBrief as unknown as ReturnType<typeof vi.fn>;

function makeBrief(
  v2_data: Record<string, unknown> = {}
): BriefDetailResponse {
  return {
    slice: "v0-brief-detail-1",
    brief_id: "test_brief_id",
    path: "config/Test/brief.json",
    role_title: "Test Role",
    v2_data: {
      capability_areas: [
        { name: "Eng", description: "ships systems" }
      ],
      depth_distinction: {
        builder_definition: "owns",
        user_definition: "uses",
        edge_case_guidance: "borderline"
      },
      ...v2_data
    },
    preserved_legacy: {},
    deprecated_keys: [],
    unknown_keys: [],
    last_modified: "2026-05-01T00:00:00Z",
    version_count: 0,
    was_flat: false
  };
}

beforeEach(() => {
  briefMock.mockReset();
  versionsMock.mockReset();
  putBriefMock.mockReset();
  versionsMock.mockResolvedValue({
    slice: "v0-brief-versions-1",
    brief_id: "test_brief_id",
    versions: []
  } satisfies BriefVersionsResponse);
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function flushMicrotasks(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

describe("BriefDetail — Where Cloris saves section (F2)", () => {
  it("renders the section heading", async () => {
    briefMock.mockResolvedValue(makeBrief());
    render(BriefDetail, { props: { briefId: "test_brief_id" } });
    await flushMicrotasks();

    expect(
      screen.getByRole("heading", { name: /where cloris saves/i })
    ).toBeInTheDocument();
  });

  it("reads source_config.linkedin.project_id when present", async () => {
    briefMock.mockResolvedValue(
      makeBrief({
        target_modules: ["linkedin"],
        source_config: {
          linkedin: { project_id: "1990251114", project_name: "FDE NYC" }
        }
      })
    );
    const { container } = render(BriefDetail, {
      props: { briefId: "test_brief_id" }
    });
    await flushMicrotasks();

    expect(container.textContent).toContain("Project 1990251114");
    expect(container.textContent).toContain("FDE NYC");
  });

  it("falls back to flat linkedin_project_id when source_config absent", async () => {
    briefMock.mockResolvedValue(
      makeBrief({
        target_modules: ["linkedin"],
        linkedin_project_id: "2009570906"
      })
    );
    const { container } = render(BriefDetail, {
      props: { briefId: "test_brief_id" }
    });
    await flushMicrotasks();

    expect(container.textContent).toContain("Project 2009570906");
  });

  it("renders the project URL editor when no destination is set", async () => {
    // Path 3 trial slice. The legacy missing-prose cue at
    // .brief-detail-destination-missing was replaced by the inline
    // editor; pasting a Recruiter project URL writes
    // source_config.linkedin via PUT and immediately rerenders the
    // section with the configured display.
    briefMock.mockResolvedValue(makeBrief({ target_modules: ["linkedin"] }));
    const { container } = render(BriefDetail, {
      props: { briefId: "test_brief_id" }
    });
    await flushMicrotasks();

    const editor = container.querySelector(".linkedin-project-editor");
    expect(editor).not.toBeNull();
    const input = container.querySelector(".linkedin-project-editor-input");
    expect(input).not.toBeNull();
    // The legacy missing-prose-cue element is gone — the editor itself
    // is the recruiter's affordance.
    expect(
      container.querySelector(".brief-detail-destination-missing")
    ).toBeNull();
  });

  it("renders the GitHub no-destination-needed prose cue", async () => {
    briefMock.mockResolvedValue(
      makeBrief({ target_modules: ["linkedin", "github"] })
    );
    const { container } = render(BriefDetail, {
      props: { briefId: "test_brief_id" }
    });
    await flushMicrotasks();

    expect(container.textContent).toContain("writes to the run folder");
  });

  it("defaults to linkedin row for legacy briefs without target_modules", async () => {
    briefMock.mockResolvedValue(
      makeBrief({ linkedin_project_id: "1957683706" })
    );
    const { container } = render(BriefDetail, {
      props: { briefId: "test_brief_id" }
    });
    await flushMicrotasks();

    // Section still renders despite missing target_modules; legacy
    // brief defaults to a linkedin row.
    expect(
      screen.getByRole("heading", { name: /where cloris saves/i })
    ).toBeInTheDocument();
    expect(container.textContent).toContain("Project 1957683706");
  });

  it("save flow writes source_config.linkedin via putBrief and rerenders the display", async () => {
    // Path 3 trial slice. The recruiter pastes a Recruiter project URL
    // into the inline editor; the helper merges into source_config and
    // calls PUT, then BriefDetail swaps its local state for the
    // returned detail and renders the configured display.
    briefMock.mockResolvedValue(makeBrief({ target_modules: ["linkedin"] }));
    putBriefMock.mockResolvedValue(
      makeBrief({
        target_modules: ["linkedin"],
        source_config: { linkedin: { project_id: "1990251114" } }
      })
    );

    const { container } = render(BriefDetail, {
      props: { briefId: "test_brief_id" }
    });
    await flushMicrotasks();

    const input = container.querySelector(
      ".linkedin-project-editor-input"
    ) as HTMLInputElement;
    expect(input).not.toBeNull();
    await fireEvent.input(input, {
      target: {
        value: "https://www.linkedin.com/talent/hire/1990251114/discover/recruiterSearch"
      }
    });
    const save = container.querySelector(
      ".linkedin-project-editor-save"
    ) as HTMLButtonElement;
    await fireEvent.click(save);
    await flushMicrotasks();
    await flushMicrotasks();

    expect(putBriefMock).toHaveBeenCalledTimes(1);
    const [, body] = putBriefMock.mock.calls[0] as [string, { v2_data: Record<string, unknown> }];
    const sc = body.v2_data["source_config"] as Record<string, unknown>;
    const linkedin = sc.linkedin as Record<string, unknown>;
    expect(linkedin.project_id).toBe("1990251114");

    expect(container.textContent).toContain("Project 1990251114");
  });
});
