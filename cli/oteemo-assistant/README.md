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
- **Ontology recall (new)**: `ingest ontology` / `reindex ontology`, `show ontology MemoryItem`, `show ontology raja_gudepu_ceo`, `ontology search finops`
- **Ontology deletes (first-class, explicit)**: `delete ontology raja_gudepu_ceo` (or bare name), `delete ontology --name MemoryItem`, `delete ontology --source "oteemo/ontology/agents"`, `delete ontology --entity-type role` (advanced), `delete ontology --all` (DANGEROUS broad with warning in help text). Surfaces as cyan delete summary (count + removed names list + selectors) via MCP; status MODE "Ontology Delete"; graceful same as ingest/search. (Previously deletes were only internal side-effect of reindex in ingest.)
  - **Casing note (fixed 2026-06)**: ontology show/search/delete names are extracted preserving original case from your input (e.g. `MemoryItem`, not `memoryitem`). This ensures they match the exact `name` values stored in Weaviate chunks (ingested from YAML/LinkML sources that use mixed/camelCase). The prior footgun (full `.toLowerCase()` before extracting `name`/`source`/`entity_type`) caused `deleted: 0` even for real data. Both interactive text box and `--headless --command` paths now forward cased selectors. (Backend delete uses exact `Filter.by_property("name").equal(...)`; search is more tolerant.)

## The Bottom Status Bar (the star of the 2026-06 upgrade)

The bar is implemented with `StatusBarPrimitive.Root / .Status / .ModelName / .MessageCount / .TokenCount / .Latency` (plus custom extensions for mode, px, params, roots, quick keys, and running indicator). It is anchored at the true bottom using `useWindowSize` (resize-aware polyfill + `useStdout`) + flex column + explicit `height=rows` layout (ViewportFooter pattern).

**Fields (left → right, example):**

- **MODE**: `Pure Simulation` (default, always works) | `Live-Seeded (px)` (after `enrich` or `... live`) | `Report Review` (`show report` / full view) | `Validation` | `Help` | `Command` (catch-all) | `Ontology Reindex` / `Ontology Search` / `Ontology Delete` (new; during ingest/show/search/delete). Updates automatically on intent; makes the operating context instantly visible. Bottom bar briefly shows e.g. "MODE: Ontology Reindex" or "Ontology Delete". Deletes are now using the full oteemo-assistant surface.
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

## Ontology recall (Weaviate meta_ontology + LinkML target) — first-cut + explicit deletes
The TUI now controls ontology as a first-class recall layer (additive; disk YAMLs under mcp-servers/scenario-research/ontology/ + oteemo/ontology/ are always the source of truth and git).
- `ingest ontology` / `reindex ontology`: walks the trees, chunks (role/policy/tool per agents yamls; class/attribute for linkml_data_model), ensures `meta_ontology` (and LinkML-derived odrs_* collections), embeds via shared vector glue, inserts (idempotent clear-by-source first-cut; refactored to call shared delete helper internally for DRY).
- `show ontology <name>` / `ontology search <q>`: calls search_ontology over the collection; renders as cyan-bordered cards (entity_type + name + source/tags) + MarkdownText snippets.
- **Deletes now first-class and using the oteemo-assistant** (addresses prior observation that deletes were "only internal side-effect inside ingest"): `delete ontology raja_gudepu_ceo` (or just the name), `delete ontology --name MemoryItem`, `delete ontology --source "oteemo/ontology/agents"`, `delete ontology --entity-type role` (advanced), `delete ontology --all` (strong warning surfaced in help + parse). Calls manager.scenario.call("delete_ontology", {name?, entity_type?, source?, delete_all?}); sets MODE "Ontology Delete"; renders rich result (cyan summary + deleted count + list of removed names + selectors) using data-part + OteemoMessage pattern. Idempotent, graceful, two-layer timeout.
- Status bar lights up `MODE: Ontology Reindex` / `Ontology Search` / `Ontology Delete` during; graceful "Weaviate not available — ontology sources remain fully functional on disk ... pure-sim unaffected" if no client / [research] extra / store down. Same contract for delete.
- CLI surface (Python happy path): `uv --project mcp-servers/scenario-research run scenario-research ingest-ontology --target weaviate` ... ; `search-ontology "finops"`; `delete-ontology --name raja_gudepu_ceo` (positional name ok), `--source ...`, `--all`.
- LinkML extension: linkml_weaviate.ensure_weaviate_collections_from_linkml (maps attrs -> TEXT / TEXT_ARRAY; additive to Surreal; invoked on LinkML during ingest).
- All via existing MCP manager.call + two-layer timeout (SCENARIO_RESEARCH_TIMEOUT_SEC). Pure sim / prior flows 100% unaffected. Deletes affect Weaviate recall only.

See updated scenario-research README + oteemo-billable.md for details. Follow-ups (better chunking, instance data in odrs_* colls, TUI confirm for --all) tracked in UI recs.

## Remote scenario analysis (Modal) — multi-run dispatch

The assistant now supports kicking off **remote multi-scenario analysis** on Modal workers (the `--target modal` / `dispatch_multi_scenario_to_modal` path recently added to the Python `scenario-research` CLI + MCP).

This is **fire-and-forget kick-off** (thin delegation): the assistant/MCP returns immediately with dispatch metadata (status, pid, cmd, `sim-results` volume, monitor/retrieve notes). The actual `run_scenario_remote.map(...)` + volume write continues in a detached child on the Modal side. Use the `modal` CLI to monitor/retrieve (full polling back into meta layer is future work).

**Thin surface**: uses the existing generic `manager.scenario.call("dispatch_multi_scenario_to_modal", { scenario_file, execution_mode?, output_format?, server_urls_json? })`. No new typed method on ScenarioAPI (power users can always call arbitrary tools directly via the manager in headless/scripts or custom hosts).

**Natural language in the TUI chat (exact examples you can type):**
- `multi-run camel-oasis-scaffold/examples/multi_scenarios.json --target modal`
- `dispatch multi scenario to modal camel-oasis-scaffold/examples/multi_scenarios.json`
- `run multi scenarios remotely --target modal camel-oasis-scaffold/examples/multi_scenarios.json --execution-mode camel --output-format parquet`
- `remote analysis modal camel-oasis-scaffold/examples/multi_scenarios.json`

The parser extracts the first path-like token as `scenario_file` (supports relative paths from the meta root, as recommended in the scenario-research docs) + optional `--execution-mode`, `--output-format` / `--format`, `--server-urls-json`. Presence of "modal"/"remote"/"multi-run"/"dispatch multi" routes to the dispatch kind.

**Status bar**: lights up `MODE: Remote Multi-Scenario (Modal)` during the (short) launch phase.

**Render**: cyan-bordered dispatch card showing status/pid/volume/file/cmd + the full note (monitor hints + two-layer timeout reminder). Errors (e.g. `modal` CLI not installed in the scenario-research env) surface as clear actionable text (the same message the Python CLI/MCP would give, with the exact `uv pip install -e 'camel-oasis-scaffold[modal,parquet]'` guidance). No crash.

**Headless / scripting / CI (one-shot, no TTY):**
```bash
# From meta root (portable shim)
echo 'multi-run camel-oasis-scaffold/examples/multi_scenarios.json --target modal' | ./scripts/oteemo-assistant --headless

# Or direct (fresh src)
cd cli/oteemo-assistant
echo 'dispatch multi scenario to modal camel-oasis-scaffold/examples/multi_scenarios.json --output-format parquet' | npx --yes tsx src/cli.tsx --headless

# With --command
npx --yes tsx src/cli.tsx --headless --command 'multi-run camel-oasis-scaffold/examples/multi_scenarios.json --target modal --execution-mode local'
```

The headless path uses the exact same `parseIntentLocal` + `manager.scenario.call` as the TUI, prints the JSON dispatch payload (or graceful error), closes the MCPs, and exits 0/1 appropriately.

**Generic call path (power users / custom scripts, no new parseIntent required):**
After the manager is created, any host can do:
```ts
const res = await manager.scenario.call("dispatch_multi_scenario_to_modal", {
  scenario_file: "camel-oasis-scaffold/examples/multi_scenarios.json",
  execution_mode: "camel",
  output_format: "parquet",
  // server_urls_json: JSON.stringify({ ... }) optional
});
console.log(res); // { status: "dispatched", pid: ..., cmd: ..., volume: "sim-results", note: "..." }
```
Documented in the help output and status guidance. The natural phrases above are the ergonomic entry point for chat + headless `--command`.

**Cross-link**: See `mcp-servers/scenario-research/README.md` (the "Remote Modal multi-scenario dispatch" section + CLI `multi-run --target modal` docs) and `camel-oasis-scaffold/README.md` for the underlying `modal_app.py` entrypoint, install extras, `modal token new`, volume usage, and two-layer timeout details (client launch cap via `MODAL_LAUNCH_TIMEOUT_SEC` / `SCENARIO_RESEARCH_TIMEOUT_SEC`; long-running work governed inside Modal functions).

**When to prefer the direct `scenario-research` CLI vs the assistant**:
- Direct CLI (`uv run --project mcp-servers/scenario-research scenario-research multi-run <file> --target modal ...`): best for scripts, CI, exact flags, non-Node environments, or when you want the Typer/Rich output directly.
- Assistant (chat or `--headless`): best for interactive exploration alongside oteemo runs / px pulls / ontology recall in one TUI, or when piping a natural phrase from another process into the Node surface. Same contracts, same MCP, same graceful degradation.

**Current limitations**:
- Result retrieval from the `sim-results` Modal Volume still requires the `modal` CLI (`modal volume ls/get sim-results ...`). No built-in "pull results" tool yet in the assistant or scenario-research surface.
- The scenario_file path is resolved relative to the *MCP server's CWD* (the scenario-research uv project), not the assistant's CWD. Use paths relative to the meta-utilities root (as in the examples above) for portability.
- Requires the optional `[modal,parquet]` extras installed into the *same* environment that runs `scenario-research-mcp` (the assistant just spawns it; it does not install for you). If missing you get the actionable error immediately (good).

Pure sim + local `multi-run` (without --target modal) and all prior oteemo/ontology/px paths are completely unaffected.

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
