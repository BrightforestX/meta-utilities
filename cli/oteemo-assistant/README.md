# oteemo-assistant

Interactive terminal assistant (Ink + **@assistant-ui/react-ink** ^0.0.23 + **react-ink-markdown**) for the Oteemo governed billable-max scenario on the ODRS platform, with optional live business context via sibling px-mcp (gsd-mcp-server → Composio + Arcade).

This is the **opt-in Node TUI surface**. The Python MCP + direct CLI paths remain 100% functional and are the happy path for most users. The assistant is **thin** — heavy logic, governance, simulation, and optimization live in `mcp-servers/scenario-research/oteemo`.

## Quickstart

```bash
cd cli/oteemo-assistant
npm install --legacy-peer-deps   # (for the assistant-ui pins coexisting with React 18 + ink 5)
npm run dev
# or after build: npm run build && npm start
```

On first run you see a clean header, the **initial context banner** (ThreadPrimitive.Empty), a composer line, and — most importantly — the **rich persistent bottom status bar** that is always visible and explains exactly what mode + backend + context you are in.

### What the beautiful TUI looks like (text mock)

```
Oteemo Assistant — @assistant-ui/react-ink (full primitives) + rich status bar
 meta:/path/to/meta-utilities | px:detected (live capable)

╭────────────────────────────────────────────────────────────────────────────╮
│ Oteemo context: Raja (CEO/FinOps), Arka (VP Tech/platform), Rod (Fed ...   │
│ Governed by oteemo/ontology/agents/*.yaml ...                              │
│ Quick actions: 'run oteemo 12 --optimize live', 'pull gmail PEO', ...      │
╰────────────────────────────────────────────────────────────────────────────╯

╭────────────────────────────────────────────────────────────────────────────╮
│ > run oteemo 6 --optimize | pull gmail PEO | enrich with live | show ...   │
╰────────────────────────────────────────────────────────────────────────────╯

MODE: Pure Simulation | MODEL: deterministic-sim (oteemo_billable) | STATUS:IDLE | PX:pure-sim | 6p/opt seed=42 | 5 0t | 87ms | meta:ok | Ctrl-C exit | /help | Tab
```

After a rich `run oteemo ...` the thread renders cyan `LeaderCard`s, cyan `Sparkline`s, and yellow `LiveBusinessContext` (px) blocks. Reports use terminal Markdown via `MarkdownText`. The bar updates to `Live-Seeded (px)` or `Report Review` etc. automatically.

Commands in the TUI (exact same surface as before):
- `run oteemo 6` or `run oteemo 12 --optimize [live]`
- `re-run 8 --optimize`
- `enrich with live` / `live context` / `pull gmail PEO` (px signals if available)
- `show report`, `validate <yaml>`, `health`, `help`
- **Ontology recall (new)**: `ingest ontology` / `reindex ontology`, `show ontology MemoryItem`, `show ontology raja_gudepu_ceo`, `ontology search finops` (surfaces as cyan cards + Markdown chunks via MCP; graceful if Weaviate absent)

## The Bottom Status Bar (the star of the 2026-06 upgrade)

The bar is implemented with `StatusBarPrimitive.Root / .Status / .ModelName / .MessageCount / .TokenCount / .Latency` (plus custom extensions for mode, px, params, roots, quick keys, and running indicator). It is anchored at the true bottom using `useWindowSize` (resize-aware polyfill + `useStdout`) + flex column + explicit `height=rows` layout (ViewportFooter pattern).

**Fields (left → right, example):**

- **MODE**: `Pure Simulation` (default, always works) | `Live-Seeded (px)` (after `enrich` or `... live`) | `Report Review` (`show report` / full view) | `Validation` | `Help` | `Command` (catch-all) | `Ontology Reindex` / `Ontology Search` (new; during ingest/show/search). Updates automatically on intent; makes the operating context instantly visible. Bottom bar briefly shows e.g. "MODE: Ontology Reindex".
- **MODEL / backend**: `deterministic-sim (oteemo_billable)` today. Prepared for future `local-mlx:...`, `frontier:claude-...`, `px-proxy`, `hybrid`. Shown via `StatusBarPrimitive.ModelName`.
- **STATUS**: `IDLE` / `RUNNING` / `ERROR` / `CANCELLED` (from `StatusBarPrimitive.Status` + our `isRunning` + last assistant status).
- **PX**: `live-ok` (px tree detected + built) or `pure-sim` (graceful; pure path is 100% functional and the happy path).
- **Last run params**: `12p/opt seed=42` (or without `/opt`) — surfaces exactly what you last asked for.
- **Message / token counts**: `StatusBarPrimitive.MessageCount` + our approx tokens (content length / 4) + `StatusBarPrimitive.TokenCount` (internal; 0 for non-LLM today).
- **Latency**: last command execution time (ms) — useful for two-layer timeout tuning.
- **Roots**: abbreviated discovery status (`meta:ok px:detected`).
- **Quick keys**: `Ctrl-C exit | /help | Tab` (Tab for future suggestion focus).
- **Running indicator**: `⏳ 2-layer-timeout` appears during long MCP calls (pairs with the `LoadingPrimitive` descriptive text that mentions `SCENARIO_RESEARCH_TIMEOUT_SEC` + host `tool_timeouts`).

The bar is **never hidden**, always explains the current world, and changes with your actions (run with live → Live-Seeded, show report → Report Review, etc.). Future model switches will light up here immediately.

See `UI_UX_RECOMMENDATIONS.md` for the full prioritized backlog (model picker, policy YAML sidecar, FinOps PDR panel, deep-research + context-forge unification inside the same chat, batch orchestration streaming, themes, full-screen report viewer, etc.). Every idea has effort, value, and explicit guardrails matching the root `AGENTS.md`.

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

## Ontology recall (Weaviate meta_ontology + LinkML target) — first-cut
The TUI now controls ontology as a first-class recall layer (additive; disk YAMLs under mcp-servers/scenario-research/ontology/ + oteemo/ontology/ are always the source of truth and git).
- `ingest ontology` / `reindex ontology`: walks the trees, chunks (role/policy/tool per agents yamls; class/attribute for linkml_data_model), ensures `meta_ontology` (and LinkML-derived odrs_* collections), embeds via shared vector glue, inserts (idempotent clear-by-source first-cut).
- `show ontology <name>` / `ontology search <q>`: calls search_ontology over the collection; renders as cyan-bordered cards (entity_type + name + source/tags) + MarkdownText snippets.
- Status bar lights up `MODE: Ontology Reindex` / `Ontology Search` during; graceful "Weaviate not available — ontology sources remain fully functional on disk ... pure-sim unaffected" if no client / [research] extra / store down.
- CLI surface (Python happy path): `uv --project mcp-servers/scenario-research run scenario-research ingest-ontology --target weaviate` or `python -m scenario_research.ontology_ingest`; `search-ontology "finops"`.
- LinkML extension: linkml_weaviate.ensure_weaviate_collections_from_linkml (maps attrs -> TEXT / TEXT_ARRAY; additive to Surreal; invoked on LinkML during ingest).
- All via existing MCP manager.call + two-layer timeout (SCENARIO_RESEARCH_TIMEOUT_SEC). Pure sim / prior flows 100% unaffected.

See updated scenario-research README + oteemo-billable.md for details. Follow-ups (better chunking, instance data in odrs_* colls) tracked in UI recs.

## Architecture notes

- Heavy logic stays in mcp-servers/.
- The assistant is a thin opt-in Node TUI surface.
- Discovery + stdio spawning of sibling MCPs (scenario-research-mcp + gsd) obeys the monorepo layout under tools/.
- See the moved `oteemo/docs/oteemo-billable.md` (Live business context via px-mcp section) and the root docs for deeper patterns.

Adding more scenarios later: register in the MCP server + extend the tiny intent parser + renders in the adapter.

## Recommendations & Future Ideas

See `UI_UX_RECOMMENDATIONS.md` (comprehensive + completed) for:
- The delivered state (framework primitives + the rich anchored bottom status bar).
- P0/P1/P2 backlog with descriptions, why, effort, and guardrails (portability, thin-TUI, secrets only on px host, two-layer timeouts, self-dogfood, pure-sim sacred).
- Architecture constraints and follow-ups (including small MCP-side health enhancements for authoritative model strings in the bar).

This fulfills the explicit request to produce and "complete" the Recommendations document.
