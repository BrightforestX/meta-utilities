/**
 * px-mcp (gsd-mcp-server) launch helpers.
 *
 * - Discovery is in ./paths (findPxMcpRoot, honors PX_MCP_ROOT + walk).
 * - The oteemo-assistant NEVER loads COMPOSIO_API_KEY / ARCADE_API_KEY / PX_WORKOS_USER_ID.
 *   Those live exclusively in the environment of the *launched* gsd-mcp-server process.
 * - Before first use the px tree must be built once:
 *     cd <px-root> && npm install && npm run build
 *   (or the one-time step documented in cli/oteemo-assistant/README and oteemo-billable.md).
 */

import { findPxMcpRoot } from "./paths.js";
import { resolve } from "path";
import { existsSync } from "fs";

export type PxSpawn = { command: string; args: string[]; cwd?: string };

export function getPxSpawn(): PxSpawn | null {
  const pxRoot = findPxMcpRoot();
  if (!pxRoot) return null;
  const distCli = resolve(pxRoot, "dist", "cli.js");
  if (!existsSync(distCli)) {
    // Not built yet. Caller should surface guidance (do not auto-build in TUI to avoid surprising host env changes).
    return null;
  }
  return {
    command: "node",
    args: [distCli],
    // cwd left undefined; the gsd entry is self-contained.
  };
}

export function pxBuildGuidance(pxRoot: string | null): string {
  const root = pxRoot || "<px-mcp-root>";
  return `px-mcp (gsd-mcp-server) not ready. Run once on the host:\n  cd ${root} && npm install && npm run build\nThen restart the oteemo-assistant. COMPOSIO_API_KEY and ARCADE_API_KEY must be present in that shell's env (never here).`;
}
