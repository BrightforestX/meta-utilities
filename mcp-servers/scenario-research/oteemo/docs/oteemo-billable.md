# Oteemo Billable Maximization Scenario (ODRS / scenario-research)

Realistic simulation of Oteemo (federal systems integrator) leadership decision-making to maximize billable hours / utilization, built as a first-class governed scenario on the meta-utilities ODRS platform.

## Why this scenario
- Directly models the core trade-off in the ontology: **internal_platform** (Axiom R&D — long-term leverage, non-billable investment today) vs **client_delivery** (federal program billable hours / revenue now).
- Three heads as **distinct governed decision agents** (not identical population agents):
  - Raja Gudepu (Founder & CEO) — strategy + explicit AI FinOps / prompt intelligence owner.
  - Arkaprava Chaudhuri (VP, Technology) — platform architecture, A2A, GraphRAG, efficiency multipliers.
  - Roderick Kelly (Head of Delivery Operations, Federal) — PEO IWS-class program delivery, shaping, execution, current util.
- Clifford Dalson modeled as **Contractor - Axiom Platform & AI FinOps** (fixed to internal_platform per instances + ContractorContribution layer; provides maturity boost + FinOps telemetry).
- Faithful to ontology entities: LeadershipRole + primary_accountabilities, Person + EngagementType (fte/contractor/sub), DeliveryContext, FederalProgram + ContractVehicle, AxiomPlatform (sponsored initiative), AIFinOps / PromptIntelligenceRule / ModelTier / PolicyDecisionRecord (cost attribution at policy level), etc.
- Uses **existing platform machinery**: governed YAML (roles/tools/policies compiled by agent_compiler), pre-run validation, ScenarioRun / ResearchReport / CostReport (repurposed for decision FinOps), pulp optimizer + replay, batch-orchestrator replicate path, two-layer timeouts, portable relative paths + env fallbacks. No duplication of memory/orchestrator.

## Quick start (portable)
From the meta-utilities root or the mcp dir:

```bash
# Ensure the package is importable (editable recommended)
cd mcp-servers/scenario-research
uv pip install -e ".[opt]"   # opt pulls pulp for real solver; falls back gracefully

# Run the end-to-end demo (recommended entry)
python -m scenario_research.demos.oteemo_billable_max --periods 12 --seed 42 --optimize

# Or via the unified CLI (delegates to local oteemo implementation)
scenario-research run oteemo_billable --steps 12 --seed 42
```

The demo:
- Loads the packaged `data/oteemo/oteemo_firm_init.yaml` (relative; never hard-codes absolute paths from your oteemo checkout).
- Compiles the governed leadership roles (exercises agent_compiler + validation).
- Runs baseline + (with --optimize) grid search + PuLP (or argmax) selection + replay.
- Emits ScenarioRun, ResearchReport shape, CostReport analog (PDR-style decision attribution), and a human-readable markdown report with concrete recs for the three heads.
- Artifacts land in `examples/oteemo/reports/` (or cwd/oteemo_billable_reports fallback).

## Replicates / batch
Use the existing batch-orchestrator (no new orchestrator written).

Adapt `templates/scenario-replicates.example.yaml` (or submit directly):
- scenario: oteemo_billable
- seed sweeps, small horizon
- aggregate via research-memory or simple synthesis job

Example fragment (see templates/ for full):
```yaml
jobs:
  - id: oteemo-replicates
    type: scenario_research_replicates
    scenario: oteemo_billable
    seeds: [1, 2, 3, 42, 123]
    periods: 12
    # ... memory hooks, output to batch-results/
```

## Portability & environment
- All code/paths inside `mcp-servers/scenario-research/`.
- Data: `SCENARIO_RESEARCH_DATA` or `OTEEMO_FIRM_INIT` env to override (for local dev or alternate snapshots). Defaults to package-relative.
- Source ontology refresh (optional, one-time): set `OTEEMO_ONTOLOGY_SRC=/absolute/path/to/oteemo-instances.yaml` and run a future ingest helper. The absolute path is **never** present in committed runtime code or packaged data.
- No dependency on camel-oasis-scaffold for this scenario (self-contained discrete firm sim). Other scenarios continue to extend the scaffold.
- Two-layer timeouts: `SCENARIO_RESEARCH_TIMEOUT_SEC` (client) + host `tool_timeouts`.
- PostgreSQL optional (SQLite baseline; this sim is pure in-memory + json trace).

## Math / optimization notes
- Compartmental: Available → Client billable (C), Axiom internal (X), Bench (B). `util = C / total`.
- Production: effective billable hours modulated by maturity (from sustained X + Clifford) and FinOps policy (tier + waste reduction).
- Win probability: base (from federal program stubs) × (1 + maturity factor) × bid aggressiveness.
- Objective: cum_billable (risk-adjusted for invest cost + excess bench).
- Policy search: small discrete grid over Raja (invest_frac, finops_tier) + Rod (client_target, bid_aggr) → admissible filter (min maturity, max bench) → PuLP select or fallback.
- Replay: chosen + neighborhood deltas for robustness (no stochasticity beyond seed).

## Output artifacts (example)
- `examples/oteemo/reports/oteemo_billable_<seed>_<p>_<ts>.md` — executive summary, trajectories (sparklines), baseline vs opt, concrete recs for Raja/Arka/Rod/Clifford, full ScenarioRun + CostReport analog.
- `.json` bundle for downstream (orchestrator, context-forge).
- Traces include `pdr_attributions[]` (period, policy, delta_util, invest_cost, attribution_level=policy).

## Extending
- Add more federal_programs or duration models in the firm_init snapshot.
- Richer pipeline arrival (Hawkes-style via existing math modules if scaffold present).
- GraphRAG / knowledge effects on win_p (future: wire to research-memory or turbovec).
- Full engagement mix costing (fte vs contractor burn rates).
- Multi-objective (revenue + strategic Axiom maturity + bench risk) with ortools.

## Governance & quality
- All new code follows meta-utilities AGENTS.md (portability first, skill/MCP separation, two-layer timeouts, self-dogfood, no old oteemo path leakage).
- TDD/BDD: contract tests + feature scenarios added.
- Validation gate before any run.
- Governed YAML is the single source for the three heads' identities, levers, and policies.

## Live business context via px-mcp (Composio + Arcade)

The ink assistant (`cli/oteemo-assistant`) makes **live operating signals** first-class for the real-org Oteemo scenario:

- Explicit commands or natural language in the TUI: `pull gmail PEO IWS`, `pull slack recent delivery`, `get this week's calendar load for Raja/Arka/Rod`, `pull salesforce opportunities federal`, `pull notion architecture`, `enrich with live`, etc.
- These are routed via the multi-MCP client to `gsd-mcp-server` (the built `px-mcp-ts` stdio entry under the sibling `tools/mcp/px-mcp/px-mcp-ts`).
- The px host (and only the px host) holds `COMPOSIO_API_KEY` / `ARCADE_API_KEY` (and optional `PX_WORKOS_USER_ID` for alignment). Secrets never enter meta-utilities, the oteemo tree, or the assistant package.
- Pulled context is rendered in-thread as a `LiveBusinessContext` block (citations + timestamps) and can be referenced by a follow-up `run oteemo ... live` (or "re-run with the PEO signals").
- In the rendered leader cards this can surface grounded suggestions (e.g. "increase Rod bid_aggressiveness given recent client thread volume on PEO IWS (px:gmail+slack @T)").
- When artifacts are written (or ResearchReport shapes emitted), the LiveBusinessContext is included/cited so downstream consumers (batch, context-forge, research-memory) see the provenance.
- Safe no-key discovery tools are always available (`px_onboarding_composio_hint`, `composio_list_apps`, `arcade_list_toolkits`).
- If the px tree is absent, not built, or the host env lacks keys/connections: the assistant prints a clear message and the pure simulation path (governed oteemo_billable with the four leadership roles) remains 100% functional with no change in behavior.
- DB prereqs (Weaviate | Postgres | Surreal) are required only for memory/context "hit" paths or governed trace persistence; pure sim + px context pulls work without them (see `scripts/ensure-local-dbs.sh` and `templates/local-dbs/docker-compose.yml`).

Relevant toolkits for an Oteemo-like federal SI: Gmail/Google Workspace (client program threads), Slack (delivery + internal Axiom platform), Google Calendar/Outlook (leader load for the three heads + contractor), Salesforce/HubSpot (federal pipeline, win/loss reasons, PEO IWS opportunities), Notion/Confluence (architecture, GraphRAG/A2A notes), LinkedIn-style enrichment, and any custom Arcade actions.

See the `cli/oteemo-assistant/README.md` for TUI quickstart, envs, and the exact one-time `cd .../px-mcp-ts && npm install && npm run build` step.

See also:
- `mcp-servers/scenario-research/README.md`
- `oteemo/ontology/agents/roles.yaml` (and tools/policies) for the compiled leadership specs (governed, distinct from shared oasis/workforce)
- `oteemo/demos/oteemo_billable_max.py` (the executable entry; or `python -m oteemo.demos.oteemo_billable_max` when oteemo parent on PYTHONPATH)
- `oteemo/scenarios/oteemo_billable.py` (sim core)
- `oteemo/optimization/oteemo.py` (policy search + replay)
- `oteemo/data/oteemo_firm_init.yaml` (portable snapshot)
- Root `templates/batch/` for replicate manifests
- `scripts/ensure-local-dbs.sh` and `templates/local-dbs/docker-compose.yml` for Weaviate/Postgres/SurrealDB prereqs (for memory/context hits)

The `scenario-research run oteemo_billable` and `python -m scenario_research.demos...` (pre-layout) or equivalent via adapter continue to work. Direct demo module invocation updated for sibling layout.

Questions or extensions? Update `docs/decisions.yaml` (or equivalent) and the scenario README.
