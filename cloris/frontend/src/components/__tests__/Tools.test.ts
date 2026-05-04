// Tools index tests — Phase G Slice G4.
//
// Pins:
//   - Catalog renders one card per registered tool.
//   - Tier C / cli_only tools render the CLI command but no form.
//   - Tier A/B tools with schema_fields render a form.
//   - "Run" button POSTs through runTool().

import { render, fireEvent } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";

import Tools from "../Tools.svelte";
import type { ToolsIndexResponse } from "../../lib/types";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>(
    "../../lib/api"
  );
  return {
    ...actual,
    getToolsIndex: vi.fn(),
    runTool: vi.fn(),
    getToolJobStatus: vi.fn(),
  };
});

import {
  getToolsIndex,
  runTool,
  getToolJobStatus,
} from "../../lib/api";

const mocked = {
  index: getToolsIndex as unknown as ReturnType<typeof vi.fn>,
  run: runTool as unknown as ReturnType<typeof vi.fn>,
  job: getToolJobStatus as unknown as ReturnType<typeof vi.fn>,
};

beforeEach(() => {
  mocked.index.mockReset();
  mocked.run.mockReset();
  mocked.job.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function flushMicrotasks(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

function makeIndex(
  overrides: Partial<ToolsIndexResponse> = {}
): ToolsIndexResponse {
  return {
    slice: "v0-tools-index-1",
    tools: [],
    ...overrides,
  };
}

describe("Tools — index render", () => {
  it("renders one card per registered tool", async () => {
    mocked.index.mockResolvedValue(
      makeIndex({
        tools: [
          {
            tool_id: "iterate_brief",
            tier: "A",
            label: "Iterate brief",
            pitch: "Cloris drafts the next version.",
            cli_command: "tools/iterate_brief.py --brief x",
            execution_model: "async",
            schema_fields: [
              {
                name: "brief_path",
                type: "string",
                required: true,
                default: null,
                description: "",
              },
            ],
          },
          {
            tool_id: "audit_surfaces",
            tier: "B",
            label: "Capture surfaces",
            pitch: "Walks every surface.",
            cli_command: "make audit-ui",
            execution_model: "cli_only",
            schema_fields: [],
          },
        ],
      })
    );
    const { container } = render(Tools);
    await flushMicrotasks();
    expect(container.querySelectorAll(".tools-card").length).toBe(2);
    expect(container.textContent).toContain("Iterate brief");
    expect(container.textContent).toContain("Capture surfaces");
  });

  it("renders the CLI command for cli_only tools but no form", async () => {
    mocked.index.mockResolvedValue(
      makeIndex({
        tools: [
          {
            tool_id: "audit_surfaces",
            tier: "B",
            label: "Capture surfaces",
            pitch: "Walks every surface.",
            cli_command: "make audit-ui",
            execution_model: "cli_only",
            schema_fields: [],
          },
        ],
      })
    );
    const { container } = render(Tools);
    await flushMicrotasks();
    expect(container.querySelector(".tools-card .tools-cli code")?.textContent).toBe(
      "make audit-ui"
    );
    expect(container.querySelector(".tools-card .tools-form")).toBeNull();
  });

  it("renders a form for runnable tools with schema_fields", async () => {
    mocked.index.mockResolvedValue(
      makeIndex({
        tools: [
          {
            tool_id: "iterate_brief",
            tier: "A",
            label: "Iterate brief",
            pitch: "Cloris drafts.",
            cli_command: "tools/iterate_brief.py --brief x",
            execution_model: "async",
            schema_fields: [
              {
                name: "brief_path",
                type: "string",
                required: true,
                default: null,
                description: "",
              },
              {
                name: "report_path",
                type: "string",
                required: true,
                default: null,
                description: "",
              },
            ],
          },
        ],
      })
    );
    const { container } = render(Tools);
    await flushMicrotasks();
    expect(container.querySelectorAll(".tools-form-field").length).toBe(2);
  });
});

describe("Tools — run", () => {
  it("clicking Run POSTs through runTool with the form values", async () => {
    mocked.index.mockResolvedValue(
      makeIndex({
        tools: [
          {
            tool_id: "iterate_brief",
            tier: "A",
            label: "Iterate brief",
            pitch: "Cloris drafts.",
            cli_command: "x",
            execution_model: "async",
            schema_fields: [
              {
                name: "brief_path",
                type: "string",
                required: true,
                default: null,
                description: "",
              },
              {
                name: "report_path",
                type: "string",
                required: true,
                default: null,
                description: "",
              },
            ],
          },
        ],
      })
    );
    mocked.run.mockResolvedValue({
      slice: "v0-tool-async-1",
      tool_id: "iterate_brief",
      job_id: "abc123",
    });
    mocked.job.mockResolvedValue({
      slice: "v0-tool-job-1",
      job_id: "abc123",
      tool_id: "iterate_brief",
      status: "succeeded",
      started_at: 1,
      finished_at: 2,
      exit_code: 0,
      stdout_tail: "ok",
      stderr_tail: "",
      error_message: null,
    });

    const { container } = render(Tools);
    await flushMicrotasks();

    const inputs = container.querySelectorAll(
      ".tools-form-input"
    ) as NodeListOf<HTMLInputElement>;
    await fireEvent.input(inputs[0], { target: { value: "config/x.json" } });
    await fireEvent.input(inputs[1], { target: { value: "output/run/" } });

    const runBtn = container.querySelector(
      ".tools-run-button"
    ) as HTMLButtonElement;
    await fireEvent.click(runBtn);
    await flushMicrotasks();

    expect(mocked.run).toHaveBeenCalledWith("iterate_brief", {
      brief_path: "config/x.json",
      report_path: "output/run/",
    });
  });
});
