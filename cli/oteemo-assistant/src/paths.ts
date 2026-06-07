/**
 * Portable root discovery for the oteemo-assistant (and sibling MCPs).
 *
 * - Honors META_UTILITIES_HOME / PX_MCP_ROOT if set (explicit override).
 * - Otherwise walks upward from import.meta.url (or __dirname fallback) until it finds
 *   a directory containing AGENTS.md *and* mcp-servers/scenario-research (for meta-utilities root).
 * - For px-mcp: walks until tools/mcp/px-mcp/px-mcp-ts (or the package with src/cli.ts + package.json naming gsd).
 *
 * Never hard-codes personal, absolute, or machine-specific paths.
 * Expected layout (from any cwd):
 *   tools/
 *     meta-utilities/   (this repo; contains AGENTS.md + mcp-servers/scenario-research + cli/oteemo-assistant)
 *     mcp/
 *       px-mcp/
 *         px-mcp-ts/    (the gsd-mcp-server package; src/cli.ts with shebang, builds to dist/cli.js)
 *
 * The assistant stdio-spawns:
 *   - scenario-research-mcp via `uv --project <meta>/mcp-servers/scenario-research run ...` (or uvx after install)
 *   - gsd-mcp-server via `node <px>/px-mcp-ts/dist/cli.js` (after its own `npm --prefix <px>/px-mcp-ts run build`)
 */

import { fileURLToPath } from "url";
import { dirname, resolve } from "path";
import { existsSync } from "fs";

export type DiscoveredRoots = {
  metaUtilitiesRoot: string | null;
  pxMcpRoot: string | null;
};

function fileExists(p: string): boolean {
  try { return existsSync(p); } catch { return false; }
}

function hasMetaMarker(dir: string): boolean {
  const agents = resolve(dir, "AGENTS.md");
  const mcpScenario = resolve(dir, "mcp-servers", "scenario-research");
  return fileExists(agents) && fileExists(mcpScenario);
}

function hasPxMarker(dir: string): boolean {
  // px-mcp-ts package root contains src/cli.ts (shebang entry) and package.json
  const cliTs = resolve(dir, "src", "cli.ts");
  const pkg = resolve(dir, "package.json");
  return fileExists(cliTs) && fileExists(pkg);
}

function walkUpForMarker(start: string, predicate: (d: string) => boolean, maxHops = 12): string | null {
  let cur = start;
  for (let i = 0; i < maxHops; i++) {
    if (predicate(cur)) return cur;
    const parent = resolve(cur, "..");
    if (parent === cur) break;
    cur = parent;
  }
  return null;
}

/**
 * Find the meta-utilities root (dir with AGENTS.md + mcp-servers/scenario-research).
 */
export function findMetaUtilitiesRoot(): string | null {
  const env = process.env.META_UTILITIES_HOME;
  if (env && fileExists(resolve(env, "AGENTS.md"))) {
    return env;
  }
  // ESM: import.meta.url -> file path
  const here = typeof import.meta.url === "string"
    ? dirname(fileURLToPath(import.meta.url))
    : dirname(__dirname); // tsx / cjs fallback
  return walkUpForMarker(here, hasMetaMarker);
}

/**
 * Find the px-mcp (gsd) package root (the px-mcp-ts dir).
 */
export function findPxMcpRoot(): string | null {
  const env = process.env.PX_MCP_ROOT;
  if (env && hasPxMarker(env)) {
    return env;
  }
  const meta = findMetaUtilitiesRoot();
  if (meta) {
    const candidate = resolve(meta, "..", "mcp", "px-mcp", "px-mcp-ts");
    if (hasPxMarker(candidate)) return candidate;
    // also try sibling under tools/
    const siblingTools = resolve(meta, "..", "..", "mcp", "px-mcp", "px-mcp-ts");
    if (hasPxMarker(siblingTools)) return siblingTools;
  }
  const here = typeof import.meta.url === "string"
    ? dirname(fileURLToPath(import.meta.url))
    : dirname(__dirname);
  // walk broadly from assistant location
  return walkUpForMarker(here, (d) => hasPxMarker(resolve(d, "tools", "mcp", "px-mcp", "px-mcp-ts")) || hasPxMarker(d));
}

/**
 * Convenience: return both (nulls are allowed; callers must degrade gracefully).
 */
export function discoverRoots(): DiscoveredRoots {
  return {
    metaUtilitiesRoot: findMetaUtilitiesRoot(),
    pxMcpRoot: findPxMcpRoot(),
  };
}
