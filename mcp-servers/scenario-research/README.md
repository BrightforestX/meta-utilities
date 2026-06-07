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
tool_timeouts = { scenario_research = 3600, run_scenario = 3600 }
```

## Timeouts (two-layer)

- Client: `SCENARIO_RESEARCH_TIMEOUT_SEC` (default 1800s for heavy sims).
- Host: `tool_timeouts` entry for the long tools.

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

## LinkML -> Surreal + run artifact writes

Step 1 (implemented): LinkML memory schema compilation to SurrealQL:
- `scenario_research/linkml_surreal.py::compile_linkml_to_surrealql`
- source schema: `ontology/memory/linkml_data_model.yaml`
- emits namespace/db/table/field/index DDL for `MemoryItem`, `ScenarioTrace`, `Attribution`, `LiveBusinessContext`

Step 2 (implemented): write-path adapter for scenario artifacts:
- `ScenarioSurrealWriter` + `persist_run_artifacts`
- CLI and MCP `run` paths call this after scenario execution
- if `SURREAL_URL` is healthy: applies schema and writes records
- fallback: writes local payload JSON to `.context/scenario-surreal-writes/` (or `SCENARIO_SURREAL_FALLBACK_DIR`)

Surreal envs:
- `SURREAL_URL`
- `SURREAL_NS` (default `odrs`)
- `SURREAL_DB` (default `memory`)
- optional auth: `SURREAL_USER`, `SURREAL_PASS`
- optional timeout: `SURREAL_TIMEOUT_SEC`

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

## Oteemo billable maximization (example real-org scenario)

A self-contained, governed scenario exercising the full ODRS stack for a federal SI leadership question:

- Distinct leadership decision agents (Raja/FinOps+strategy, Arka/arch, Rod/fed delivery) + Clifford (contractor, Axiom FinOps) derived from the real Oteemo ontology (LeadershipRole, DeliveryContext internal_platform vs client_delivery, EngagementType, FederalProgram, AIFinOps/PDR, ContractorContribution).
- Lightweight discrete firm model (compartmental util dynamics, pipeline wins, maturity investment trade-off, policy-attributed FinOps telemetry).
- Uses existing: agent_compiler + validation, ScenarioRun/ResearchReport/CostReport (repurposed), pulp + replay, batch replicates, timeouts, portable paths.
- Runnable via `scenario-research run oteemo_billable` (preferred; adapter handles local oteemo impl) or `python -m oteemo.demos.oteemo_billable_max --periods 12 --seed 42 --optimize` (when oteemo/ sibling on path) or the legacy direct.
- See `oteemo/docs/oteemo-billable.md` for how-to, recs format, reproducibility, data locations, and DB prereqs (Weaviate/Postgres/Surreal for governed memory/context).

This demonstrates "extend, don't duplicate" + dogfooding the platform on a concrete organizational decision problem without touching the source oteemo repo.
