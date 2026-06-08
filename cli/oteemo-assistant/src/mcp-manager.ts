/**
 * Multi-server MCP manager for oteemo-assistant.
 *
 * Owns two independent stdio sessions:
 *  - scenario-research-mcp (ODRS + oteemo_billable governed sim)
 *  - gsd-mcp-server (px-mcp proxies for composio + arcade business context)
 *
 * Namespaced surface:
 *   manager.scenario.runOteemoBillable(...)
 *   manager.px.listComposioApps(), manager.px.callComposioTool(...), manager.px.listArcadeToolkits()...
 *   manager.px.onboardingHint() etc (always available, no keys required)
 *
 * Two-layer timeouts documented in README + oteemo docs.
 * px keys live only in the gsd host process env.
 *
 * OUTPUT HYGIENE NOTE:
 * Both connectScenarioResearch (mcp-client) and connectPx use StdioClientTransport with
 * explicit stderr: 'pipe' + silent drain. This prevents FastMCP/gsd startup banners from
 * leaking to the real terminal while the interactive Ink TUI (ComposerPrimitive.Input etc.)
 * owns the screen via raw mode. See mcp-client.ts JSDoc for the full explanation and
 * why this is non-negotiable for usable text input in the assistant-ui box.
 */

import { connectScenarioResearch, callTool, listTools, runOteemoBillable, type McpHandle } from "./mcp-client.js";
import { getPxSpawn, pxBuildGuidance } from "./px-launch.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

export type ScenarioAPI = {
  runOteemoBillable: (p?: { steps?: number; seed?: number; optimize?: boolean }) => Promise<unknown>;
  health: () => Promise<unknown>;
  listTools: () => Promise<unknown>;
  call: (name: string, args?: Record<string, unknown>) => Promise<unknown>;
  close: () => Promise<void>;
};

export type PxAPI = {
  listComposioApps: () => Promise<unknown>;
  listComposioTools: (slug?: string) => Promise<unknown>;
  callComposioTool: (qualified: string, args?: Record<string, unknown>) => Promise<unknown>;
  listArcadeToolkits: () => Promise<unknown>;
  callArcadeTool: (qn: string, args?: Record<string, unknown>) => Promise<unknown>;
  onboardingComposioHint: () => Promise<unknown>;
  onboardingArcadeHint: () => Promise<unknown>;
  health: () => Promise<unknown>;
  listTools: () => Promise<unknown>;
  call: (name: string, args?: Record<string, unknown>) => Promise<unknown>;
  close: () => Promise<void>;
};

export type McpManager = {
  scenario: ScenarioAPI;
  px: PxAPI | null; // null when px tree not present or not built (graceful)
  closeAll: () => Promise<void>;
};

async function connectPx(): Promise<{ client: Client; close: () => Promise<void> } | null> {
  const spawnInfo = getPxSpawn();
  if (!spawnInfo) return null;

  const transport = new StdioClientTransport({
    command: spawnInfo.command,
    args: spawnInfo.args,
    env: process.env as Record<string, string>,
    // stderr: 'pipe' (NOT default/omit/'inherit') — REQUIRED to protect the parent Ink TUI.
    // See mcp-client.ts and module JSDoc. The gsd-mcp-server (px) prints a startup line
    // "[gsd-mcp-server] MCP server started on stdio" (and FastMCP does its rich banner for scenario).
    // These must be captured by the SDK (into transport.stderr) rather than forwarded to the
    // real terminal. While Ink controls the TTY (raw mode + its virtual screen), any leaked
    // child output corrupts cursor state and breaks key event delivery to ComposerPrimitive.Input
    // (typing/backspace/Enter stop working; banner "flash" is the observable symptom).
    // Silent drain below + close on client.close() keeps the interactive surface responsive.
    // (Graceful: if !getPxSpawn we never reach here; pxHandle remains null.)
    stderr: "pipe",
  });
  const client = new Client({ name: "oteemo-assistant-px", version: "0.1.0" }, { capabilities: {} });
  await client.connect(transport);

  // Silent drain of piped child stderr (same contract as scenario child).
  // Zero writes to real process.stderr / console during TUI lifetime.
  const childStderr = (transport as any).stderr;
  if (childStderr && typeof childStderr.on === "function") {
    childStderr.on("data", () => {
      /* silent: protect Ink TUI terminal ownership and ComposerPrimitive.Input */
    });
    childStderr.on("error", () => {
      /* best-effort; close path handles transport teardown */
    });
  }

  const close = async () => { try { await client.close(); } catch {} };
  return { client, close };
}

export async function createMcpManager(): Promise<McpManager> {
  const scenarioHandle = await connectScenarioResearch();

  const scenario: ScenarioAPI = {
    runOteemoBillable: (p) => runOteemoBillable(scenarioHandle, p),
    health: () => callTool(scenarioHandle, "scenario_research_health", {}),
    listTools: () => listTools(scenarioHandle),
    call: (name, args) => callTool(scenarioHandle, name, args || {}),
    close: () => scenarioHandle.close(),
  };

  let pxHandle: { client: Client; close: () => Promise<void> } | null = null;
  try {
    pxHandle = await connectPx();
  } catch {
    pxHandle = null;
  }

  const px: PxAPI | null = pxHandle
    ? {
        listComposioApps: () => callTool(pxHandle!, "composio_list_apps", {}),
        listComposioTools: (slug) => callTool(pxHandle!, "composio_list_tools", slug ? { slug } : {}),
        callComposioTool: (qualified, args) => callTool(pxHandle!, "composio_call_tool", { qualified_name: qualified, arguments: args || {} }),
        listArcadeToolkits: () => callTool(pxHandle!, "arcade_list_toolkits", {}),
        callArcadeTool: (qn, args) => callTool(pxHandle!, "arcade_call_tool", { qualified_name: qn, arguments: args || {} }),
        onboardingComposioHint: () => callTool(pxHandle!, "px_onboarding_composio_hint", {}),
        onboardingArcadeHint: () => callTool(pxHandle!, "px_onboarding_arcade_hint", {}),
        health: () => listTools(pxHandle!),
        listTools: () => listTools(pxHandle!),
        call: (name, args) => callTool(pxHandle!, name, args || {}),
        close: () => pxHandle!.close(),
      }
    : null;

  const closeAll = async () => {
    await Promise.allSettled([scenario.close(), px ? px.close() : Promise.resolve()]);
  };

  return { scenario, px, closeAll };
}
