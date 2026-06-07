# oteemo-assistant

Interactive terminal assistant (Ink + @assistant-ui/react-ink) for the Oteemo governed billable-max scenario on the ODRS platform, with optional live business context via sibling px-mcp (gsd-mcp-server → Composio + Arcade).

## Quickstart

```bash
cd cli/oteemo-assistant
npm install
npm run dev
# or after build: npm run build && npm start
```

Commands in the TUI:
- `run oteemo 6` or `run oteemo 12 --optimize`
- `enrich with live` / `live context` (px signals if available)
- `health`, `help`

## Env & portability

- `META_UTILITIES_HOME` (or walk-up from the assistant package until AGENTS.md + mcp-servers/scenario-research is found).
- `PX_MCP_ROOT` (or walk-up to tools/mcp/px-mcp/px-mcp-ts).
- `SCENARIO_RESEARCH_TIMEOUT_SEC` (client layer of the two-layer timeout).
- px keys (COMPOSIO_API_KEY, ARCADE_API_KEY, optional PX_WORKOS_USER_ID) live **only** in the environment of the launched gsd-mcp-server process. The assistant never holds them.

One-time for px (on the host that will run gsd):
```
cd <px-root>/px-mcp-ts && npm install && npm run build
```

Pure simulation (no px, no DBs) remains fully functional.

## DB prereqs (Weaviate | Postgres | SurrealDB)

For research-memory hits, context-forge long-horizon, governed ODRS traces/persistence, and ink 'ask' + memory:
- Run `./scripts/ensure-local-dbs.sh` (or `... --up`).
- Exports: WEAVIATE_URL, SURREAL_URL, POSTGRES_DSN (defaults to localhost).
- The TUI surfaces status + guidance before long/memory paths.
- Pure sim is never blocked.

See `templates/local-dbs/docker-compose.yml` and the root AGENTS / docs for details.

## Live business context via px-mcp (Composio + Arcade)

The assistant can pull **real, up-to-date operating signals** without ever holding third-party secrets:

- `pull gmail PEO` / `pull slack recent` / `pull calendar for heads` / `pull salesforce pipeline federal` / `pull notion arch` etc.
- These route through the sibling `gsd-mcp-server` (from `tools/mcp/px-mcp/px-mcp-ts` after its `npm run build`).
- The px host process carries `COMPOSIO_API_KEY`, `ARCADE_API_KEY` (and optionally `PX_WORKOS_USER_ID` for user alignment on certain HITL/composio/arcade calls). The assistant only discovers the location and spawns it via stdio.
- Results surface as `LiveBusinessContext` blocks (with tool citations + timestamps) in the thread and can be referenced when you do a subsequent `run oteemo ... live`.
- In the oteemo result cards this can drive visible suggestions (e.g. "Rod bid_aggressiveness +5pp given recent PEO thread volume") and is included in the meta for any persisted report artifacts.
- Always-available safe tools (no keys needed on host): `px_onboarding_composio_hint`, `px_onboarding_arcade_hint`, `composio_list_apps`, `arcade_list_toolkits`.
- If px tree absent / not built / no keys or connections: graceful "pure sim path remains fully functional".

See also the "Live business context via px-mcp" section in the moved `oteemo/docs/oteemo-billable.md` and the root docs.

## Architecture notes

- Heavy logic stays in mcp-servers/.
- The assistant is a thin opt-in Node TUI surface.
- Discovery + stdio spawning of sibling MCPs (scenario-research-mcp + gsd) obeys the monorepo layout under tools/.
- See the moved `oteemo/docs/oteemo-billable.md` (Live business context via px-mcp section) and the root docs for deeper patterns.

Adding more scenarios later: register in the MCP server + extend the tiny intent parser + renders in the adapter.
