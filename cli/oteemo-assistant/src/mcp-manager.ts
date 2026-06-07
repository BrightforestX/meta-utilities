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
  });
  const client = new Client({ name: "oteemo-assistant-px", version: "0.1.0" }, { capabilities: {} });
  await client.connect(transport);
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
