// Monitor index tests — Phase G Slice G3.
//
// Pins:
//   - Empty state when no active runs.
//   - One row per active run with operational mono-caps headers.
//   - Row link points at #/monitor/<source>/<state_key>/<run_id>.

import { render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";

import Monitor from "../Monitor.svelte";
import type { MonitorIndexResponse } from "../../lib/types";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>(
    "../../lib/api"
  );
  return {
    ...actual,
    getMonitorIndex: vi.fn(),
  };
});

import { getMonitorIndex } from "../../lib/api";

const mocked = {
  list: getMonitorIndex as unknown as ReturnType<typeof vi.fn>,
};

beforeEach(() => {
  mocked.list.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function flushMicrotasks(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

function makeIndex(
  overrides: Partial<MonitorIndexResponse> = {}
): MonitorIndexResponse {
  return {
    slice: "v0-monitor-index-1",
    active_runs: [],
    ...overrides,
  };
}

describe("Monitor — index render", () => {
  it("renders empty state when no active runs", async () => {
    mocked.list.mockResolvedValue(makeIndex());
    const { container } = render(Monitor);
    await flushMicrotasks();
    expect(container.textContent).toContain("Nothing is running");
    expect(container.querySelector(".monitor-table")).toBeNull();
  });

  it("renders one table row per active run", async () => {
    mocked.list.mockResolvedValue(
      makeIndex({
        active_runs: [
          {
            source: "linkedin",
            state_key: "li-1",
            run_id: 5,
            run_status: "running",
            stop_reason: null,
            started_at: "2026-05-01T00:00:00Z",
            ended_at: null,
            brief_id: "brief-li",
            brief_role_title: "FDE",
            worker_pid: 12345,
          },
          {
            source: "github",
            state_key: "gh-1",
            run_id: 9,
            run_status: "running",
            stop_reason: null,
            started_at: "2026-05-01T00:01:00Z",
            ended_at: null,
            brief_id: "brief-gh",
            brief_role_title: "PM",
            worker_pid: 12346,
          },
        ],
      })
    );
    const { container } = render(Monitor);
    await flushMicrotasks();
    expect(container.querySelectorAll(".monitor-table tbody tr").length).toBe(2);
    expect(container.textContent).toContain("12345");
    expect(container.textContent).toContain("12346");
  });

  it("row link points at the per-run monitor URL", async () => {
    mocked.list.mockResolvedValue(
      makeIndex({
        active_runs: [
          {
            source: "linkedin",
            state_key: "li-link",
            run_id: 7,
            run_status: "running",
            stop_reason: null,
            started_at: "2026-05-01T00:00:00Z",
            ended_at: null,
            brief_id: "brief-link",
            brief_role_title: "Eng",
            worker_pid: 99,
          },
        ],
      })
    );
    const { container } = render(Monitor);
    await flushMicrotasks();
    const link = container.querySelector(".monitor-row-link") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("#/monitor/linkedin/li-link/7");
  });
});
