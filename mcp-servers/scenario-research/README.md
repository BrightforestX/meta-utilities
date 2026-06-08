# scenario-research-mcp

Ontology-Governed Autonomous Business Scenario Research & Optimization Platform (ODRS) as an MCP server.

This package provides the MCP + CLI surface for running governed CAMEL-OASIS simulations, fitting math models (SIR/Hawkes/bounded confidence/bayesian AB), producing costed reports, and scaling via the existing batch-orchestrator.

It **extends** (does not duplicate) the co-located `camel-oasis-scaffold/` runtime.

## P0 Layout Status

- Package layout + entrypoints aligned with meta-utilities MCP conventions (fastmcp, hatch, uv).
- Core DTO contracts: `ScenarioRun`, `ModelFitResult`, `CostReport`, `ResearchReport`.
- Router contract stub (local for bulk OASIS, frontier for planner/writer).
- Contract tests exercising shapes + router decisions.
- CLI smoke (`scenario-research version`, `health`, stub `run`).
- MCP tool `scenario_research_health`.

See the root plan `scenario_research_platform_6d0fdfa6.plan.md` for full phased work, AC1-AC13, TDD/BDD gates, and artifact checklist.

## Install (dev)

From repo root or the mcp dir:

```bash
cd mcp-servers/scenario-research
uv pip install -e ".[dev]"
# Also install the scaffold (provides camel, scenarios, models, workforce)
uv pip install -e ../../camel-oasis-scaffold
```

## Run CLI smoke (P0)

```bash
scenario-research version
scenario-research health
scenario-research run info_spread --agents 20 --steps 3
scenario-research multi-run ../../camel-oasis-scaffold/examples/multi_scenarios.json

# Remote Modal (kick-off; recommended unified path, portable, no cd):
# After: uv pip install -e ".[modal]" and uv pip install -e "../../camel-oasis-scaffold[modal,parquet]"
uv run --project . scenario-research multi-run ../../camel-oasis-scaffold/examples/multi_scenarios.json --target modal
# (or from meta-utilities root: uv run --project mcp-servers/scenario-research scenario-research multi-run camel-oasis-scaffold/examples/... --target modal)
```

## Run MCP server

```bash
scenario-research-mcp
```

Register with host (example for Grok; see templates/):

```toml
[mcp_servers.scenario-research]
command = "uvx"
args = ["scenario-research-mcp"]
tool_timeouts = { scenario_research = 3600, run_scenario = 3600, run_multi_scenario = 3600, dispatch_multi_scenario_to_modal = 300 }
```

## Timeouts (two-layer)

- Client: `SCENARIO_RESEARCH_TIMEOUT_SEC` (default 1800s for heavy sims).
- Host: `tool_timeouts` entry for the long tools.

## Remote Modal multi-scenario dispatch (from this CLI/MCP)

The `scenario-research multi-run <file> --target modal` (or `--remote modal`) command (and the MCP `dispatch_multi_scenario_to_modal` tool) is the supported way to kick off a batch on the remote Modal workers defined in `camel-oasis-scaffold/src/camel_sim/modal_app.py`.

- Portable: uses the same `get_scaffold_root()` + sys.path injection as the local multi-run path. Works from the meta-utilities checkout root without `cd` into the scaffold.
- Kick-off (fire-and-forget): the CLI/MCP returns immediately after starting the documented `modal run .../modal_app.py` entrypoint in a detached child. The remote `run_scenario_remote.map(...)` + `write_results_remote` (to the `sim-results` Volume) continues independently.
- Flags forwarded: `--execution-mode` (local|camel), `--output-format` (parquet recommended), `--server-urls-json` (for camel mode with real endpoints).
- Install (into the scenario-research project/env):

  ```bash
  uv pip install -e "mcp-servers/scenario-research[modal]"
  uv pip install -e "camel-oasis-scaffold[modal,parquet]"
  ```

  Then (from meta root):

  ```bash
  uv run --project mcp-servers/scenario-research scenario-research multi-run \
    camel-oasis-scaffold/examples/multi_scenarios.json --target modal
  ```

- Two-layer timeout for this path: launch/submit bounded by `MODAL_LAUNCH_TIMEOUT_SEC` (or `SCENARIO_RESEARCH_TIMEOUT_SEC`); the long-running remote job uses the per-function `timeout=900` + `Retries` declared inside `modal_app.py`.
- Graceful errors: if `modal` CLI missing or scaffold undiscoverable, you get an actionable message with the exact `uv pip ...[modal,parquet]` command and no "cd" requirement.
- Results: land in the `sim-results` Modal Volume. (Full retrieval/polling into the meta layer is follow-up work; use `modal volume get` / dashboard in the interim.)
- MCP: hosts and agents call `dispatch_multi_scenario_to_modal(scenario_file=..., ...)`; register `dispatch_multi_scenario_to_modal` (or the `run_multi_scenario` bucket) in your host's `tool_timeouts`.
- The raw `modal run` inside the scaffold dir still works; the CLI/MCP path is the unified, documented, portable recommendation.

See also: `camel-oasis-scaffold/README.md` (updated to point here) and the dispatch implementation in `scenario_research/scaffold_adapter.py` + CLI/MCP surfaces.

## Local inference backends (cost reduction)

Router supports local backends for low-cost execution:

- `mlx` (default)
- `ollama`
- `lmstudio`
- `turnover` (local gateway/provider slot)

Configure with env vars:

- `SCENARIO_RESEARCH_LOCAL_PROVIDER=mlx|ollama|lmstudio|turnover`
- Provider model envs:
  - `SCENARIO_RESEARCH_MLX_MODEL` (default `mlx-qwen`)
  - `SCENARIO_RESEARCH_OLLAMA_MODEL` (default `qwen2.5:14b-instruct`)
  - `SCENARIO_RESEARCH_LMSTUDIO_MODEL` (default `local-model`)
  - `SCENARIO_RESEARCH_TURNOVER_MODEL` (default `turnover-local`)
- Optional provider base URLs:
  - `OLLAMA_BASE_URL` (default `http://localhost:11434`)
  - `LMSTUDIO_BASE_URL` (default `http://localhost:1234/v1`)
  - `TURNOVER_BASE_URL` (default `http://localhost:8080`)

If you want maximum cost savings for planning/writer roles too, enable:

- `SCENARIO_RESEARCH_COST_SAVER_MODE=true`

That forces frontier roles to local inference for the run.

Check provider reachability before runs:

```bash
scenario-research providers
scenario-research providers --active-only
scenario-research prov --active-only --timeout-sec 0.5
```

Note: `mlx` is typically an in-process local runtime, so probe output will mark it as a non-HTTP endpoint rather than pinging a network health URL.

**Headless / CI / scripting:** All commands accept inputs exclusively via flags/args (including the recent `--target modal` / `--remote` for fire-and-forget dispatch from any cwd via portable scaffold discovery). No interactive prompts in the Typer surfaces. Use `uv run --project mcp-servers/scenario-research scenario-research ...` (or installed entry) from scripts; pipe/redirect freely. See root `cli/README.md` for the full suite (incl. `meta-batch`, oteemo demos, and the oteemo-assistant `--headless` one-shot for the TUI surface). The oteemo-assistant TUI (chat or `--headless`) also supports the same remote dispatch via natural phrases such as "multi-run <file> --target modal" or "dispatch multi scenario to modal <file>" (thin .call to `dispatch_multi_scenario_to_modal`; see `cli/oteemo-assistant/README.md`). Outputs are structured (dicts/JSON) or explicit graceful messages when optional stores (Weaviate) or heavy extras (camel, modal) are absent.

## LinkML -> Surreal + run artifact writes

Step 1 (implemented): LinkML memory schema compilation to SurrealQL:
- `scenario_research/linkml_surreal.py::compile_linkml_to_surrealql`
- source schema: `ontology/memory/linkml_data_model.yaml`
- emits namespace/db/table/field/index DDL for `MemoryItem`, `ScenarioTrace`, `Attribution`, `LiveBusinessContext`

Step 2 (implemented): write-path adapter for scenario artifacts:
- `ScenarioSurrealWriter` + `persist_run_artifacts`
- CLI and MCP `run` paths call this after scenario execution
- if `SURREAL_URL` is healthy: runs additive schema reconcile and writes records
- fallback: writes local payload JSON to `.context/scenario-surreal-writes/` (or `SCENARIO_SURREAL_FALLBACK_DIR`)
- writes are deterministic/idempotent via explicit record IDs + `UPSERT`:
  - `ScenarioTrace` keyed by `run_id + period`
  - `Attribution` keyed by policy attribution key
  - `LiveBusinessContext` keyed by `trace_id + scenario`

Read path (implemented):
- `ScenarioSurrealReader` + `fetch_run_artifacts(run_id)`
- attempts Surreal query first (configurable), then falls back to local payload file
- CLI commands:
  - `scenario-research artifacts <run_id>`
  - `scenario-research arts <run_id>`
  - `scenario-research attributions <run_id> --period-min ... --period-max ... --aggregate ...`
  - `scenario-research attrs <run_id> ...`

Surreal envs:
- `SURREAL_URL`
- `SURREAL_NS` (default `odrs`)
- `SURREAL_DB` (default `memory`)
- optional auth: `SURREAL_USER`, `SURREAL_PASS`
- optional timeout: `SURREAL_TIMEOUT_SEC`
- optional schema reconcile toggle: `SCENARIO_SURREAL_SCHEMA_RECONCILE` (default `true`)

## Observability (LangSmith + local lineage ledger)

Scenario run/ask flows emit explicit, replayable reasoning + artifact lineage.

- LangSmith (optional, recommended):
  - `LANGSMITH_API_KEY`
  - `LANGSMITH_PROJECT` (default: `scenario-research`)
  - `LANGSMITH_TRACING=true` (set `false` to disable remote publish)
- Local ledger (always written):
  - `SCENARIO_RESEARCH_TRACE_DIR` (default: `mcp-servers/scenario-research/.context/scenario-research-traces`)

Each trace captures:
- `trace_id`
- step-level `reasoning_summary` (explicit reasoning notes, not hidden model CoT)
- step inputs/outputs
- artifact lineage (`path`, `kind`, `created_by_step`, existence/size)
- run outputs + status/error

`ScenarioRun.config_snapshot.observability` includes the active `trace_id` and artifact list so downstream tools (CLI/TUI/MCP consumers) can join on lineage.

## MCP analysis tools (implemented)

In addition to `run_scenario` and `ask`, the server now exposes:

- `get_cost_report(run_id)` -> deterministic local/api token estimate from run artifacts
- `fit_models(run_id|db_path, models)` -> lightweight fit summaries (`sir`, `hawkes`, `bounded_confidence`, `bayesian_ab`)
- `replay_policy(policy, scenario, seed, periods)` -> baseline-vs-treatment robustness deltas (implemented for `oteemo_billable`)
- `get_run_artifacts(run_id, prefer_surreal)` -> fetch persisted ScenarioTrace/Attribution/context by run id
- `query_attributions(run_id, period_min, period_max, level, aggregate, prefer_surreal)` -> filtered attribution rows + optional aggregates

## Ask pipeline (artifact-producing)

`ask` now runs a full local research pipeline (not shape-only fallback):

- selects a scenario (currently `oteemo_billable`)
- executes scenario run
- persists artifacts via Surreal write adapter (or fallback payload)
- computes model fit summaries + deterministic cost telemetry
- computes baseline-vs-treatment replay robustness
- writes a markdown report artifact to `SCENARIO_RESEARCH_REPORT_DIR` (default `.context/scenario-research-reports`)

CLI:

```bash
scenario-research ask "How do we improve billable utilization?" -s 42
scenario-research q "How do we improve billable utilization?" -s 42
```

## PostgreSQL

Optional everywhere. SQLite is the portable baseline for dev/CI. Full constraint enforcement is a prod nicety.

## Next (per plan)

- Wire real scaffold execution (p0-wire-scaffold-extension)
- Lock + test the DTOs and router (p0-lock-core-contracts, p0-model-routing-contract)
- Env/timeout contract + artifact bootstrap
- Governed YAML for CAMEL agents (roles/tools/policies/population_templates) with LinkML + validation gates (P2)
- etc.

## TDD/BDD

All changes follow Red (failing test/spec first) -> Green -> Refactor.
BDD features live under `tests/bdd/` (or root tests) and map to ACs.
PRs must include updated contract snapshots or new Given/When/Then when behavior changes.

## Ontology recall (new first-cut)
- `scenario-research ingest-ontology --target weaviate` (or `python -m scenario_research.ontology_ingest`)
- `scenario-research search-ontology "finops"`
- `scenario-research delete-ontology --name raja_gudepu_ceo` (or bare `delete-ontology MemoryItem`; `--source "oteemo/ontology/..."`; `--entity-type role` (advanced); `--all` (DANGEROUS broad))
- Walks shared ontology/ + oteemo/ontology/ (roles/policies/tools + LinkML classes/attrs).
- Maintains `meta_ontology` (configurable via RESEARCH_ONTOLOGY_COLLECTION) + ensures LinkML-derived collections (additive to Surreal).
- Chunks + embeds + inserts with stable IDs; idempotent clear-by-source for first-cut (now DRY via internal delete helper).
- Standalone deletes now first-class (MCP `delete_ontology`, CLI `delete-ontology`, TUI `delete ontology ...`); previously only implicit side-effect inside ingest.
- Graceful: clear messages if Weaviate or [research] extra absent; disk YAMLs are source of truth. Deletes affect recall layer only.
- MCP surface: `ingest_ontology`, `search_ontology`, `delete_ontology` (two-layer timeout wrapped; selectors name/entity_type/source/delete_all).
- TUI (oteemo-assistant): `ingest ontology`, `show ontology MemoryItem|raja_gudepu_ceo`, `ontology search ...`, `delete ontology raja... | --name X | --source Y | --all (careful)` (cyan delete cards with count + removed names list; status bar MODE "Ontology Delete").
See ontology_ingest.py + linkml_weaviate.py + oteemo-assistant README for usage + verification.

## Oteemo billable maximization (example real-org scenario)

A self-contained, governed scenario exercising the full ODRS stack for a federal SI leadership question:

- Distinct leadership decision agents (Raja/FinOps+strategy, Arka/arch, Rod/fed delivery) + Clifford (contractor, Axiom FinOps) derived from the real Oteemo ontology (LeadershipRole, DeliveryContext internal_platform vs client_delivery, EngagementType, FederalProgram, AIFinOps/PDR, ContractorContribution).
- Lightweight discrete firm model (compartmental util dynamics, pipeline wins, maturity investment trade-off, policy-attributed FinOps telemetry).
- Uses existing: agent_compiler + validation, ScenarioRun/ResearchReport/CostReport (repurposed), pulp + replay, batch replicates, timeouts, portable paths.
- Runnable via `scenario-research run oteemo_billable` (preferred; adapter handles local oteemo impl) or `python -m oteemo.demos.oteemo_billable_max --periods 12 --seed 42 --optimize` (when oteemo/ sibling on path) or the legacy direct.
- See `oteemo/docs/oteemo-billable.md` for how-to, recs format, reproducibility, data locations, and DB prereqs (Weaviate/Postgres/Surreal for governed memory/context).

This demonstrates "extend, don't duplicate" + dogfooding the platform on a concrete organizational decision problem without touching the source oteemo repo.
