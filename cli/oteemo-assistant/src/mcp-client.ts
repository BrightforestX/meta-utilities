/**
 * MCP stdio client layer for oteemo-assistant.
 *
 * - scenario-research-mcp (Python ODRS): uv/uvx driven from discovered meta root.
 * - (Next) gsd-mcp-server (px-mcp for composio/arcade business context).
 *
 * Two-layer timeouts: client (SCENARIO_RESEARCH_TIMEOUT_SEC etc) + host tool_timeouts.
 * Secrets for px live only in the px host process (never here).
 *
 * CRITICAL OUTPUT HYGIENE (interactive TUI):
 * StdioClientTransport MUST use stderr: 'pipe' (see connectScenarioResearch).
 * FastMCP (scenario-research-mcp) + gsd-mcp-server emit rich startup panels / lines to stderr
 * on spawn. If these reach the real terminal while Ink owns raw mode + virtual screen, they
 * interleave, corrupt cursor/terminal state, and break ComposerPrimitive.Input (no typing,
 * backspace, etc. work; visible "FastMCP UI flash" symptom). We pipe + silently drain so zero
 * child output leaks during normal interactive lifetime. (Headless also benefits: clean JSON.)
 * Diagnostics available via DEBUG/future forwarding or direct child runs; never by default.
 */

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { discoverRoots } from "./paths.js";
import { spawn } from "child_process";

export type McpHandle = {
  client: Client;
  close: () => Promise<void>;
};

const DEFAULT_SCENARIO_RESEARCH_TIMEOUT = Number(process.env.SCENARIO_RESEARCH_TIMEOUT_SEC || 1800);

function buildScenarioResearchCommand(metaRoot: string | null) {
  // Prefer explicit uv --project for dev; fall back to uvx (after `uv tool install` or pipx equiv).
  if (metaRoot) {
    return {
      command: "uv",
      args: ["--project", `${metaRoot}/mcp-servers/scenario-research`, "run", "scenario-research-mcp"],
    };
  }
  // Portable fallback (assumes scenario-research-mcp on PATH via uvx / pipx / uv tool).
  return { command: "uvx", args: ["scenario-research-mcp"] };
}

export async function connectScenarioResearch(): Promise<McpHandle> {
  const { metaUtilitiesRoot } = discoverRoots();
  const { command, args } = buildScenarioResearchCommand(metaUtilitiesRoot);

  const transport = new StdioClientTransport({
    command,
    args,
    // Inherit env so that SCENARIO_RESEARCH_* and host tool_timeouts (if any) propagate.
    env: process.env as Record<string, string>,
    // stderr: 'pipe' (NOT default/omit/'inherit') — REQUIRED to protect the parent Ink TUI.
    // See module JSDoc for full rationale. FastMCP rich banner + gsd startup line must never
    // reach the real controlling terminal while the assistant's ComposerPrimitive.Input is mounted.
    // 'pipe' routes child's stderr into transport.stderr (a stream we drain silently below).
    // This keeps Ink's raw-mode terminal control intact so backspace, text entry, Enter, etc.
    // all work in the text box. Child output is suppressed for the interactive lifetime.
    stderr: "pipe",
  });

  const client = new Client(
    { name: "oteemo-assistant", version: "0.1.0" },
    { capabilities: {} }
  );

  await client.connect(transport);

  // Silent drain of the piped child stderr stream.
  // Prevents any output from reaching process.stderr (the real terminal) during TUI use.
  // Also avoids stream backpressure. We intentionally do NOT forward or log here.
  // (The transport will be closed by client.close() in the handle's close path.)
  const childStderr = (transport as any).stderr;
  if (childStderr && typeof childStderr.on === "function") {
    childStderr.on("data", () => {
      /* silent: do not write to real console while Ink owns the screen */
    });
    childStderr.on("error", () => {
      /* best-effort; transport close will clean up */
    });
  }

  // Best-effort: we rely on host-side tool_timeouts + client env for the two-layer contract.
  // The transport does not expose per-call timeout here; long ops are protected by the MCP host config + our wrapper.

  const close = async () => {
    try { await client.close(); } catch { /* ignore */ }
  };

  return { client, close };
}

export async function listTools(handle: McpHandle) {
  return handle.client.listTools();
}

export async function callTool(handle: McpHandle, name: string, args: Record<string, unknown> = {}) {
  return handle.client.callTool({ name, arguments: args });
}

/**
 * Typed helper for the oteemo_billable happy path.
 * The payload shape is the ScenarioRun-ish dict expected by the MCP tool (run_scenario or the oteemo entry).
 */
export async function runOteemoBillable(
  handle: McpHandle,
  params: {
    steps?: number;
    seed?: number;
    optimize?: boolean;
    // future: liveContext?: any (from px enrichment)
  } = {}
) {
  const payload = {
    scenario: "oteemo_billable",
    n_steps: params.steps ?? 12,
    seed: params.seed ?? 42,
    // The ODRS server/adapter accepts extra hints; optimize is handled inside the demo path or via separate call.
    optimize: !!params.optimize,
  };
  // The MCP surface exposes "run_scenario" (generic) or scenario-specific; try the common one first.
  try {
    return await callTool(handle, "run_scenario", payload);
  } catch {
    // Fallback to explicit oteemo entry if the server surfaces it.
    return await callTool(handle, "oteemo_billable", payload);
  }
}

export async function health(handle: McpHandle) {
  // Many MCPs expose a health or the generic ping via tools list or a no-op call.
  // We surface the tools list as a liveness signal for the TUI.
  return listTools(handle);
}
