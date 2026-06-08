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
