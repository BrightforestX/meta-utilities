# BDD scenarios for ODRS core (maps to AC1-AC13)
# These are the executable acceptance specs. In a full behave/pytest-bdd setup they would be bound to steps.

Feature: P0 Bootstrap and contracts
  Scenario: AC1 Bootstrap prints next command
    Given a clean environment
    When bootstrap.sh runs with BOOTSTRAP_DRY=1
    Then it prints "Bootstrap complete" and the happy path "scenario-research run" command

  Scenario: AC2 Hybrid routing
    Given the models.yaml mapping
    When resolve_endpoint for oasis_agent
    Then it is local and does not require frontier key

Feature: P2-P3 Governance and validation
  Scenario: AC11-13 Agent YAML governance + validation
    Given governed roles/tools/policies/population yamls
    When compiler produces runtime config
    Then output is deterministic for unchanged input (AC13)
    And pre-run validation blocks on invalid yaml with structured error (AC12)

Feature: P4 Simulation flow
  Scenario: AC3-6 Run + math + ask + cost
    Given a wired scenario
    When run info_spread via the mcp/cli
    Then a ScenarioRun with db is produced
    And db_loader bridge yields structures for math modules
    And ask produces ResearchReport with CostReport (local/api split)

Feature: P5-P6 Scale, memory, optimization
  Scenario: AC10 Risk alignment + optimizer replay
    Given existing memory/orchestrator in meta-utilities
    When ODRS integrates
    Then no duplicate memory, extends batch-orchestrator, and optimizer replay produces robustness deltas

Feature: Oteemo billable maximization (real organizational scenario on ODRS)
  # NOTE: oteemo-specific files consolidated under mcp-servers/scenario-research/oteemo/ (scenarios/, optimization/, demos/, data/, reports/, ontology/agents/, docs/).
  # Public scenario id 'oteemo_billable', CLI/MCP surface (scenario-research run, validate etc), and adapter behavior unchanged.
  # Shared ontology/ now contains only general oasis/workforce roles (no oteemo leadership duplication).
  Scenario: Oteemo-1 Governed distinct leadership agents + ontology fidelity
    Given the oteemo.linkml + instances (Raja CEO/FinOps owner, Arka VP Tech, Rod Head Fed Delivery, Clifford contractor on Axiom)
    When governed roles are compiled for raja_gudepu_ceo / arkaprava_chaudhuri_vp_tech / roderick_kelly_fed_delivery
    Then they are distinct (kind=leadership_decision or specialist_contributor), not identical population agents
    And primary_accountabilities + DeliveryContext (internal_platform vs client_delivery) + EngagementType + FederalProgram + AIFinOps/PDR are present in init snapshot and policy levers
    And pre-run validation passes for oteemo_billable

  Scenario: Oteemo-2 Baseline sim + optimize + replay + CostReport analog
    Given oteemo_billable scenario (self-contained, deterministic seed)
    When baseline run + optimize_oteemo_policy (grid + pulp/fallback) + replay
    Then ScenarioRun is produced (via local adapter, no camel required)
    And cum_billable_hours, avg_util, maturity, bench, pdr_attributions (FinOps decision attribution) are populated
    And optimized policy yields admissible candidate (min maturity, max bench) or surfaces constraint tension
    And replay produces robustness deltas; CostReport analog captures invest/bench/policy cost attribution (PDR-level)

  Scenario: Oteemo-3 Actionable recs for heads + batch replicate ready
    Given a completed oteemo run + report
    When recommendations are generated for Raja / Arka / Rod (Clifford as influencing contractor)
    Then they are concrete (fractions, periods, tiers) and traceable to levers/accountabilities
    And replicate mode is supported via batch-orchestrator manifest + seed sweeps (no new orchestrator)
    And all paths relative / env-fallback; no absolute oteemo or personal paths in runtime code
