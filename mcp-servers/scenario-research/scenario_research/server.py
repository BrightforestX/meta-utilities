#!/usr/bin/env python3
"""
scenario-research-mcp

MCP server entrypoint for the Ontology-Governed Scenario Research Platform (ODRS).
Thin MCP surface over the camel-oasis-scaffold with:
- governed YAML agent definitions (P2)
- pre-run validation (P3)
- hybrid local/frontier routing
- cost telemetry and math fits surfaced as tools
- integration points for batch-orchestrator replicates (P5)

Two-layer timeouts documented in package README and templates.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

from fastmcp import FastMCP, Context

from .models import ScenarioRun, CostReport, ResearchReport
from .router import resolve_endpoint, get_model_for_role
from .scaffold_adapter import execute_multi_scenario_configs, execute_scenario
from .timeouts import get_timeout_seconds
from .validation import validate_agent_yaml_text, validate_before_run

# Client timeout for long simulation/research loops (OASIS runs + workforce ask)
# Host (grok/cursor) also sets tool_timeouts[scenario_research_*] (see LONG_RUNNING_TOOLS)
# Single source in .timeouts
SCENARIO_RESEARCH_TIMEOUT_SEC: float = get_timeout_seconds()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] scenario-research: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="scenario-research",
    instructions=(
        "Ontology-governed autonomous business scenario research & optimization platform (ODRS). "
        "Use scenario_research tools for running governed CAMEL-OASIS simulations, fitting mathematical models, "
        "producing costed research reports, and (via batch-orchestrator) scaling replicate ensembles. "
        "All agent roles, tools, policies, and population templates are declared in governed YAML under the ontology layer. "
        "Two-layer timeouts: SCENARIO_RESEARCH_TIMEOUT_SEC (client) + host tool_timeouts entry. "
        "PostgreSQL is optional; SQLite is the portable default baseline."
    ),
)


@mcp.tool()
async def scenario_research_health(ctx: Context | None = None) -> dict[str, Any]:
    """Lightweight health + contract smoke for the MCP surface."""
    return {
        "ok": True,
        "version": "0.1.0",
        "timeout_default": SCENARIO_RESEARCH_TIMEOUT_SEC,
        "router_example": {
            "oasis_agent": resolve_endpoint("oasis_agent"),
            "planner": resolve_endpoint("planner"),
            "model_oasis": get_model_for_role("oasis_agent"),
        },
        "contracts": ["ScenarioRun", "ModelFitResult", "CostReport", "ResearchReport"],
    }


@mcp.tool()
async def run_scenario(
    scenario: str,
    n_agents: int = 50,
    n_steps: int = 10,
    seed: int | None = 42,
    ctx: Context | None = None,
) -> ScenarioRun:
    """Run a governed scenario (delegates to camel-oasis-scaffold for social scenarios; oteemo_billable is self-contained local using governed leadership roles + discrete firm sim).

    This is the wire that extends (without duplicating) the scaffold runtime where applicable.
    The MCP surface stays thin. oteemo_billable uses ontology-derived LeadershipRoles (Raja FinOps, Arka arch, Rod delivery) as distinct decision agents.
    Returns a populated ScenarioRun (status, db_path, error if any).
    """
    # P3: block on invalid governed yaml/config before any scaffold work
    validate_before_run(scenario, seed=seed)

    # Note: n_agents is advisory here; the scaffold profiles determine population size.
    # Real enforcement / population_templates come in P2 ontology layer.
    result = await execute_scenario(
        scenario,
        n_steps=n_steps,
        seed=seed,
    )
    return result


@mcp.tool()
async def run_multi_scenario(
    scenario_configs: list[dict[str, Any]],
    execution_mode: str = "local",
    parallel: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Run CAMEL multi-scenario configs through the co-located scaffold.

    Local mode is deterministic and does not require GPUs or API keys. CAMEL mode
    uses the scaffold's model routing and should be paired with configured model
    backends or Modal/SGLang endpoints.
    """
    payload = execute_multi_scenario_configs(
        scenario_configs,
        execution_mode=execution_mode,
        parallel=parallel,
    )
    return {
        "scenarios": payload["scenarios"],
        "execution_mode": payload["execution_mode"],
        "results": payload["results"],
    }


@mcp.tool()
async def ask(question: str, seed: int | None = 42, ctx: Context | None = None) -> ResearchReport:
    """(P4 flow) End-to-end ask delegating to scaffold workforce when available.

    Returns a ResearchReport DTO. In full env this will populate report_path, fits, cost_report.
    """
    # For wiring completeness we return a shaped report; real call to scaffold.ask would populate.
    # (The scaffold cli.ask does the workforce; we keep surface here without duplicating logic.)
    from datetime import datetime, timezone
    rid = f"ask-{abs(hash(question)) % 10**8}"
    return ResearchReport(
        report_id=rid,
        question=question,
        created_at=datetime.now(timezone.utc).isoformat(),
        seed=seed,
        cost_report=CostReport(run_id=rid),
    )


@mcp.tool()
async def validate_agent_yaml(yaml_text: str, ctx: Context | None = None) -> dict[str, Any]:
    """P3 surface: validate governed agent yaml before simulation (AC12)."""
    try:
        return validate_agent_yaml_text(yaml_text)
    except Exception as exc:  # structured
        return {"valid": False, "error": exc if isinstance(exc, dict) else {"message": str(exc)}}


# Future tools (stubs for contract surface):
# - ask(question) -> ResearchReport
# - get_cost_report(run_id) -> CostReport
# - fit_models(db_path, models) -> list[ModelFitResult]


def main() -> None:
    """Entry for `scenario-research-mcp` script (stdio MCP server)."""
    mcp.run()


if __name__ == "__main__":
    main()
