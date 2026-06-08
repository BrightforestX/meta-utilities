# CLI Surface in meta-utilities

This directory contains **opt-in terminal interfaces** for the meta-utilities stack.

> **Important (per AGENTS.md)**: `cli/` entries are thin, opt-in Node (or other) surfaces. The reproducible, primary interfaces are the Python CLIs and MCP servers under `mcp-servers/`. Heavy logic (simulation, governance, optimization, research, memory) always stays in the MCP packages.

## What Lives Here Today

- `oteemo-assistant/` — The main interactive TUI (Node + React/Ink + `@assistant-ui/react-ink` primitives).

Everything else (deep research, batch orchestration, research memory, scenario research) is driven primarily via their Python CLIs / MCP tools or via skills in agent hosts (Grok, Cursor, Claude, etc.).

---

## oteemo-assistant (the Ink TUI)

Interactive terminal assistant for the **Oteemo governed billable-max scenario** (ODRS / `scenario-research`) with first-class support for:

- Running the discrete-firm simulation (Raja/Arka/Rod/Clifford governed leadership agents).
- Pulling live business context via sibling `px-mcp` (Composio + Arcade proxies for Gmail, Slack, Calendar, Salesforce, Notion, etc.).
- **Ontology recall** (new): ingest the full ontology trees (shared + oteemo vertical) into Weaviate `meta_ontology` and query them from the chat.

It uses the modern assistant-ui ink primitives (ThreadPrimitive, ComposerPrimitive, StatusBarPrimitive, LoadingPrimitive, MarkdownText, etc.) with a custom runtime bridge that re-uses the exact existing MCP manager + all prior command logic.

### Launch

**Recommended (portable shim from anywhere in the tree):**

```bash
./scripts/oteemo-assistant
# or from the package
cd cli/oteemo-assistant
npm install --legacy-peer-deps
npm run dev
# or built: npm run build && npm start
```

The shim walks upward until it finds a directory containing both `AGENTS.md` and `mcp-servers/scenario-research` (or honors `META_UTILITIES_HOME`).

Requires Node 18+. Pure Python paths remain fully functional if you don't have Node.

### The Bottom Status Bar (always visible)

The bar is anchored at the true bottom of the terminal and is the single best way to know what "world" you are in right now.

Example states:

```
MODE: Pure Simulation | MODEL: deterministic-sim (oteemo_billable) | STATUS:IDLE | PX:pure-sim | 12p/opt seed=42 | 7 0t | 124ms | meta:ok | Ctrl-C exit | /help | Tab
```

```
MODE: Live-Seeded (px) | MODEL: deterministic-sim (oteemo_billable) | STATUS:RUNNING | PX:live-ok | 8p seed=42 | ... | ⏳ 2-layer-timeout
```

```
MODE: Report Review | MODEL: deterministic-sim (oteemo_billable) | STATUS:IDLE | PX:pure-sim | MSGS:19 ~312t | ...
```

```
MODE: Ontology Reindex | ...   # or Ontology Search
```

**Key fields**:
- **MODE** — `Pure Simulation` (default), `Live-Seeded (px)`, `Report Review`, `Validation`, `Help`, `Command`, `Ontology Reindex`, `Ontology Search`, etc. Updates automatically based on what you type.
- **MODEL / backend** — Currently `deterministic-sim (oteemo_billable)`. Prepared for future local MLX, frontier models, px-proxy, or hybrid.
- **PX** — `live-ok` (px-mcp tree detected and built) or `pure-sim` (graceful; the pure path is the happy path and never requires px).
- Running indicator + two-layer timeout awareness (`⏳ 2-layer-timeout` + `LoadingPrimitive` descriptive text that references `SCENARIO_RESEARCH_TIMEOUT_SEC` + host `tool_timeouts`).
- Last run params, message/token counts, latency, discovery roots, quick keys.

### Core Commands (TUI)

**Oteemo simulation**
- `run oteemo 12 --optimize`
- `run oteemo 8 live` (or `... --optimize live`)
- `re-run 6 --optimize`

**Live business context (px-mcp)**
- `enrich with live` / `live context` / `px`
- `pull gmail PEO` / `pull slack recent delivery` / `pull calendar for heads` / `pull salesforce pipeline federal` / `pull notion arch` etc.

**Reports & utilities**
- `show report` / `report`
- `validate` (or paste YAML after the word)
- `health` / `status`
- `help` / `/help`

**Ontology recall (Weaviate `meta_ontology` + LinkML target) + first-class deletes**
- `ingest ontology` / `reindex ontology` — walks shared `ontology/` + `oteemo/ontology/`, chunks roles/policies/tools + LinkML classes/attributes, ensures collections, embeds, inserts (idempotent clear-by-source first-cut; now calls shared delete helper internally).
- `show ontology MemoryItem` / `show ontology raja_gudepu_ceo`
- `ontology search finops` / `search ontology "delivery util"`
- `delete ontology raja_gudepu_ceo` (bare name after) | `delete ontology --name MemoryItem` (or just the name) | `delete ontology --source "oteemo/ontology/agents"` | `delete ontology --entity-type role` (advanced, document) | `delete ontology --all` (strong warning in help; broad)
- Python: `scenario-research delete-ontology --name XXX` (positional name also works), `--source PREFIX`, `--entity-type T`, `--all`.
- MCP tool: `delete_ontology` (same selectors; returns deleted + removed names sample + graceful).
Deletes now explicitly first-class via oteemo-assistant (TUI intents + manager.scenario.call + "Ontology Delete" MODE + cyan result render with count/list), CLI, and MCP. Existing ingest internal clear behavior unchanged (DRY-refactored to helper). Disk YAMLs + pure-sim sacred.

**Remote multi-scenario analysis (Modal dispatch)**
- Chat or `--headless`: `multi-run camel-oasis-scaffold/examples/multi_scenarios.json --target modal` (or "dispatch multi scenario to modal <file>", "run multi scenarios remotely --target modal").
- Thin delegation to `dispatch_multi_scenario_to_modal` (fire-and-forget; returns dispatch payload with pid/volume/note immediately). Sets MODE "Remote Multi-Scenario (Modal)"; renders structured result card. Same portable scaffold discovery + two-layer timeout contract as the Python `scenario-research multi-run --target modal` CLI.
- Headless examples: `echo 'multi-run ... --target modal' | ./scripts/oteemo-assistant --headless` (or npx tsx in the package). Generic `manager.scenario.call("dispatch_multi_scenario_to_modal", {scenario_file, ...})` works for power users without the new parse.
- Prefer the direct Python CLI (`uv run --project mcp-servers/scenario-research scenario-research multi-run <file> --target modal`) for scripts/CI; use the assistant when you want the phrase in the same chat as oteemo runs + px + ontology. See `cli/oteemo-assistant/README.md` (new "Remote scenario analysis (Modal)" section) and `mcp-servers/scenario-research/README.md` for full details, install extras, `modal` monitoring, and limitations (result retrieval from sim-results volume still needs the modal CLI today).
- All prior surfaces unaffected.

Results (incl. deletes) render as cyan-bordered cards/summaries (entity + name + source + tags for search; for delete: count + removed names list + selectors). The status bar switches to `Ontology Reindex` / `Ontology Search` / `Ontology Delete` during the operation. (Remote Modal dispatch uses its own MODE + card style.)

**Graceful degradation**
- No px tree / keys → "pure sim path remains fully functional".
- No Weaviate / `[research]` extra / store down → clear message; disk YAMLs under `mcp-servers/scenario-research/ontology/` and `oteemo/ontology/` are always the source of truth and remain fully usable.

### Environment & Prereqs

**Discovery (portable, no hard-coded paths)**
- `META_UTILITIES_HOME` (or walk-up to a dir with `AGENTS.md` + `mcp-servers/scenario-research`).
- `PX_MCP_ROOT` (or sibling walk-up under `tools/mcp/px-mcp/px-mcp-ts`).

**Two-layer timeouts**
- Client: `SCENARIO_RESEARCH_TIMEOUT_SEC` (default 1800s for heavy work).
- Host: `tool_timeouts` entries when registering the MCP.

**DBs (Weaviate | Postgres | SurrealDB)**
- Required for research-memory RAG hits, governed ODRS traces/attributions/LiveBusinessContext, context-forge long-horizon, etc.
- Run `./scripts/ensure-local-dbs.sh` (or `--up` if Docker is available).
- Exports (localhost defaults):
  ```bash
  export WEAVIATE_URL=http://localhost:8080
  export SURREAL_URL=ws://localhost:8000
  export POSTGRES_DSN='postgresql://meta:meta@localhost:5432/meta'
  ```
- Pure simulation + px context pulls + ontology source files on disk are **never blocked**.

**px live context (Composio + Arcade)**
- One-time build on the px host: `cd <px-root>/px-mcp-ts && npm install && npm run build`.
- Secrets (`COMPOSIO_API_KEY`, `ARCADE_API_KEY`, optional `PX_WORKOS_USER_ID`) live **only** in the environment of the launched `gsd-mcp-server` process. The assistant discovers the built binary and spawns it via stdio, passing the current env.

### Python / Reproducible Paths (the happy path for most work)

The TUI is great for exploration. For scripts, CI, batch, or exact reproducibility use the Python surfaces:

```bash
cd mcp-servers/scenario-research
uv pip install -e '.[research,opt]'   # research = weaviate/turbovec/etc; opt = pulp

# Core simulation
scenario-research run oteemo_billable --steps 12 --seed 42 --optimize
# or the rich demo
python -m scenario_research.demos.oteemo_billable_max --periods 12 --seed 42 --optimize

# Ontology (new)
scenario-research ingest-ontology --target weaviate
scenario-research search-ontology "finops" --top-k 5

# MCP server (for agent hosts)
scenario-research-mcp
```

See `mcp-servers/scenario-research/README.md` and `oteemo/docs/oteemo-billable.md` for full details, DB prereqs for governed memory, and the batch-orchestrator integration.

### Headless / non-interactive / scripting / CI usage (new)

All Python CLIs (`scenario-research`, `oasis-research`, `meta-batch`, `research-memory`, `deep-research-mcp`, the oteemo demos, and scripts) are fully usable in non-TTY, piped, redirected, or container/CI environments. No `input()`, `typer.confirm` with default prompts, or hard TTY assumptions in the core paths. Safe non-destructive defaults apply when stdin is not a tty.

**Direct Python surfaces (recommended for scripts):**
```bash
# From meta-utilities root (portable; uses the project's uv layout)
uv run --project mcp-servers/scenario-research scenario-research --help
uv run --project mcp-servers/scenario-research scenario-research run oteemo_billable --steps 4 --seed 42
uv run --project mcp-servers/scenario-research scenario-research multi-run examples/multi_scenarios.json --target local --execution-mode local --output-dir /tmp/out
uv run --project mcp-servers/scenario-research scenario-research search-ontology "finops"
uv run --project mcp-servers/scenario-research scenario-research multi-run ... --target modal   # fire-and-forget kickoff; returns dispatch payload + pid immediately

uv run --project mcp-servers/batch-orchestrator meta-batch --help
uv run --project mcp-servers/batch-orchestrator meta-batch status
uv run --project mcp-servers/batch-orchestrator meta-batch validate path/to/jobs.yaml

# oteemo demo (argparse, already headless)
python -m oteemo.demos.oteemo_billable_max --periods 3 --seed 42
```

**oteemo-assistant (Ink TUI) headless one-shot path:**
```bash
# Preferred for fresh src (tsx)
cd cli/oteemo-assistant
echo 'health' | npx --yes tsx src/cli.tsx --headless
npx --yes tsx src/cli.tsx --headless --command 'run oteemo 4'
echo 'search ontology finops' | npx --yes tsx src/cli.tsx --headless
echo 'delete ontology --name MemoryItem' | npx --yes tsx src/cli.tsx --headless

# Via the portable shim (forwards args; prefers built dist; rebuild after src edits)
./scripts/oteemo-assistant --headless --command 'health'
echo 'run oteemo 3' | ./scripts/oteemo-assistant --headless
```

The `--headless` path bypasses the full ThreadPrimitive/Ink UI, creates the McpManager, runs parseIntent + direct scenario/px calls, prints JSON or text result, closes, and exits. Same power as the chat (run oteemo, ontology ops, px pulls, health) without interactivity. Pure sim always works; px graceful.

**Scripts (flag or status driven; set -euo pipefail):**
```bash
./scripts/ensure-local-dbs.sh            # status/check only (non-mutating)
./scripts/ensure-local-dbs.sh --up       # bring up if docker (guarded)
BOOTSTRAP_DRY=1 ./scripts/bootstrap.sh /tmp/target
./scripts/measure_research_metrics.py --help
bash skills/context-forge/scripts/enable-full-default.sh --yes   # headless full (indexes if --yes; non-tty defaults to safe/no-mutate)
```

All new flags/modes are optional; TTY interactive behavior for the TUI and the one prompt (now guarded) is unchanged. Use /tmp for outputs. Never reads the caller's real .env for the sweep/tests.

For Modal kickoff from CI/scripts: `scenario-research multi-run <file> --target modal ...` returns immediately with dispatch metadata; the remote work continues. Monitor via `modal` CLI. Requires the optional extras in the same env.

---

## Quick Reference — Where to Look

- `cli/oteemo-assistant/README.md` — Detailed TUI usage, status bar, ontology commands, px integration, recommendations.
- `cli/oteemo-assistant/UI_UX_RECOMMENDATIONS.md` — Delivered state + prioritized future ideas with guardrails.
- `scripts/oteemo-assistant` — The portable launcher.
- `mcp-servers/scenario-research/README.md` — Python CLI + MCP surface (including the new `ingest-ontology` / `search-ontology`).
- `mcp-servers/scenario-research/oteemo/docs/oteemo-billable.md` — Oteemo scenario specifics + live context + DB notes.
- Root `AGENTS.md` — Rules for the whole workspace (portability, thin surfaces, two-layer timeouts, etc.).

---

## Philosophy (Current State)

- **Disk YAMLs + LinkML are the source of truth** for ontology definitions and governance. Weaviate (`meta_ontology` + LinkML-derived collections) and SurrealDB are projections / recall / governed storage layers that you refresh with the ingest tools.
- The TUI is a **thin, delightful opt-in surface**. All the real work (simulation, optimization, validation, ontology walking, embedding, governed writes) happens in the Python MCPs.
- Pure simulation (no px keys, no local DBs, no research extra) is sacred and always works.
- Portability and self-dogfooding are non-negotiable — discovery, shims, and shared vector glue are designed so the same experience travels to any new project with minimal setup.

If you're adding a new CLI surface in `cli/`, follow the same thin + portable + heavy-logic-in-mcp-servers pattern.

---

*This document reflects the state after the 2026-06 assistant-ui ink primitives upgrade + rich status bar + ontology ingest / TUI commands / LinkML Weaviate target work.*