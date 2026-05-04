<script lang="ts">
  // Tools — index of standalone scripts (Phase G Slice G4).
  //
  // Catalog of Cloris's command-line tools, organized by tier:
  //   Tier A — recruiter-facing, runnable from the UI
  //   Tier B — operator-diagnostic, runnable from the UI when wrappable
  //   Tier C — CLI-only documentation entries
  //
  // Each tool card carries the editorial pitch + canonical CLI command.
  // Tier A/B tools with execution_model != "cli_only" expose a small
  // form panel + run button. Tier C tools render as documentation.

  import { onMount } from "svelte";
  import {
    ApiError,
    getToolJobStatus,
    getToolsIndex,
    runTool,
  } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import type {
    ToolEntry,
    ToolJobStatusWire,
    ToolRunAsyncWire,
    ToolRunSyncWire,
    ToolsIndexResponse,
  } from "../lib/types";
  import AmbientBanner from "./AmbientBanner.svelte";
  import DisplayTitle from "./DisplayTitle.svelte";
  import Finding from "./Finding.svelte";
  import PageBackLink from "./PageBackLink.svelte";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";

  let index = $state<ToolsIndexResponse | null>(null);
  let loadError = $state<string | null>(null);

  // Per-tool form state. The recruiter fills out values inline; running
  // a tool stashes the result in `lastResult` keyed by tool_id.
  let formValues = $state<Record<string, Record<string, string>>>({});
  let lastResult = $state<Record<string, ToolJobStatusWire | ToolRunSyncWire | string>>({});
  let inFlight = $state<string | null>(null);

  async function load(): Promise<void> {
    try {
      index = await getToolsIndex();
      loadError = null;
    } catch (err) {
      loadError = describeApiError(err, "Loading tools");
    }
  }

  onMount(load);

  function valueFor(toolId: string, fieldName: string): string {
    return formValues[toolId]?.[fieldName] ?? "";
  }

  function setValue(toolId: string, fieldName: string, value: string): void {
    if (!formValues[toolId]) formValues[toolId] = {};
    formValues[toolId][fieldName] = value;
  }

  function coerceArgs(tool: ToolEntry): Record<string, unknown> {
    const args: Record<string, unknown> = {};
    const raw = formValues[tool.tool_id] ?? {};
    for (const f of tool.schema_fields) {
      const v = raw[f.name];
      if (v === undefined || v === "") {
        if (f.required) {
          throw new Error(`Missing required field: ${f.name}`);
        }
        continue;
      }
      if (f.type === "integer") {
        args[f.name] = Number(v);
      } else if (f.type === "boolean") {
        args[f.name] = v === "true" || v === "1";
      } else {
        args[f.name] = v;
      }
    }
    return args;
  }

  async function pollJob(jobId: string, toolId: string): Promise<void> {
    const POLL_MS = 1500;
    const MAX_POLLS = 60; // ~90s max
    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      try {
        const status = await getToolJobStatus(jobId);
        lastResult[toolId] = status;
        if (
          status.status === "succeeded" ||
          status.status === "failed" ||
          status.status === "purged"
        ) {
          return;
        }
      } catch (err) {
        lastResult[toolId] = err instanceof ApiError ? err.message : String(err);
        return;
      }
    }
  }

  async function runOne(tool: ToolEntry): Promise<void> {
    if (inFlight !== null) return;
    inFlight = tool.tool_id;
    try {
      const args = coerceArgs(tool);
      const result = await runTool(tool.tool_id, args);
      lastResult[tool.tool_id] = result as ToolRunSyncWire | ToolRunAsyncWire as
        | ToolRunSyncWire
        | ToolJobStatusWire;
      if (result.slice === "v0-tool-async-1") {
        await pollJob((result as ToolRunAsyncWire).job_id, tool.tool_id);
      }
    } catch (err) {
      lastResult[tool.tool_id] =
        err instanceof ApiError ? err.message : String(err);
    } finally {
      inFlight = null;
    }
  }

  function tierLabel(tier: string): string {
    if (tier === "A") return "RECRUITER";
    if (tier === "B") return "OPERATOR";
    return "DOCS";
  }

  function resultRender(toolId: string): string | null {
    const r = lastResult[toolId];
    if (r === undefined) return null;
    if (typeof r === "string") return r;
    if ("exit_code" in r && r.exit_code !== null && r.exit_code !== undefined) {
      const stdoutTail = (r.stdout_tail ?? "").trim();
      const stderrTail = (r.stderr_tail ?? "").trim();
      const lines = [
        `Exit code: ${r.exit_code}`,
        stdoutTail ? `--- stdout ---\n${stdoutTail}` : "",
        stderrTail ? `--- stderr ---\n${stderrTail}` : "",
      ].filter(Boolean);
      return lines.join("\n\n");
    }
    if ("status" in r) {
      return `Job ${r.job_id} · ${r.status}${
        r.exit_code !== null ? ` · exit ${r.exit_code}` : ""
      }`;
    }
    return JSON.stringify(r);
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />

  <PageBackLink href="#/" label="Back to home" />

  <div class="tools-page">
    <figure class="specimen-frame">
      <span class="specimen-frame-label">TOOLS</span>
      <div class="specimen-frame-stage">
        <DisplayTitle head="Cloris's" accent="toolbox" />
        <!-- Plan Finding 14: dropped the second sentence about ordering.
             The visual order on the surface already shows recruiter-tier
             first, then operator, then CLI. -->
        <p class="section-deck">
          <em>Standalone scripts you can run from the UI or the CLI.</em>
        </p>
      </div>
    </figure>

    {#if loadError !== null && index === null}
      <section class="tools-empty" role="alert" aria-live="polite">
        <h2>Couldn't load tools.</h2>
        <p>{loadError}</p>
      </section>
    {:else if index === null}
      <div class="tools-loading" out:loaderFadeOut>
        <Finding size="medium" />
      </div>
    {:else}
      <ul class="tools-list" in:surfaceFadeIn>
        {#each index.tools as tool (tool.tool_id)}
          <li class="tools-card" data-tool-id={tool.tool_id}>
            <p class="tools-tier">{tierLabel(tool.tier)} · {tool.execution_model.replace("_", " ").toUpperCase()}</p>
            <h2 class="tools-label">{tool.label}</h2>
            <p class="tools-pitch">{tool.pitch}</p>
            <p class="tools-cli">
              <code>{tool.cli_command}</code>
            </p>

            {#if tool.execution_model !== "cli_only" && tool.schema_fields.length > 0}
              <form
                class="tools-form"
                onsubmit={(e) => {
                  e.preventDefault();
                  void runOne(tool);
                }}
              >
                {#each tool.schema_fields as field (field.name)}
                  <label class="tools-form-field">
                    <span class="tools-form-label">
                      {field.name}{field.required ? " *" : ""}
                    </span>
                    <input
                      class="tools-form-input"
                      type={field.type === "integer" ? "number" : "text"}
                      value={valueFor(tool.tool_id, field.name)}
                      oninput={(e) =>
                        setValue(
                          tool.tool_id,
                          field.name,
                          (e.target as HTMLInputElement).value
                        )}
                    />
                  </label>
                {/each}
                <button
                  type="submit"
                  class="tools-run-button"
                  disabled={inFlight !== null}
                >
                  {inFlight === tool.tool_id ? "Running…" : "Run"}
                </button>
              </form>
            {/if}
            {#if resultRender(tool.tool_id) !== null}
              <pre class="tools-result">{resultRender(tool.tool_id)}</pre>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</main>
