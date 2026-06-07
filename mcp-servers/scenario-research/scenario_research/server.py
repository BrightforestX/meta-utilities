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
import os
import sys
from typing import Any

from fastmcp import FastMCP, Context

from .models import ScenarioRun, CostReport, ResearchReport
from .analytics import estimate_cost_report, fit_models_from_trace, load_trace_payload
from .linkml_surreal import persist_run_artifacts
from .observability import traced
from .optimization.replay import replay_policy as replay_policy_robustness
from .router import resolve_endpoint, get_model_for_role, get_local_inference_config
from .scaffold_adapter import execute_scenario, get_scaffold_root
from .timeouts import ENV_VAR as TIMEOUT_ENV_VAR, get_timeout_seconds, LONG_RUNNING_TOOLS, DEFAULT_TIMEOUT_SEC
from .validation import validate_agent_yaml_text, validate_before_run, validate_run_payload

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
_RUN_CACHE: dict[str, ScenarioRun] = {}

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
            "local_inference": get_local_inference_config(),
        },
        "contracts": ["ScenarioRun", "ModelFitResult", "CostReport", "ResearchReport"],
    }


@mcp.tool()
async def run_scenario(
    scenario: str,
    n_agents: int | None = None,
    n_steps: int = 10,
    seed: int | None = 42,
    ontology: str | None = None,
    ctx: Context | None = None,
) -> ScenarioRun:
    """Run a governed scenario (delegates to camel-oasis-scaffold for social scenarios; oteemo_billable is self-contained local using governed leadership roles + discrete firm sim).

    This is the wire that extends (without duplicating) the scaffold runtime where applicable.
    The MCP surface stays thin. oteemo_billable uses ontology-derived LeadershipRoles (Raja FinOps, Arka arch, Rod delivery) as distinct decision agents.
    Returns a populated ScenarioRun (status, db_path, error if any).
    """
    trace = traced(
        name="scenario_research.mcp.run_scenario",
        inputs={
            "scenario": scenario,
            "n_agents": n_agents,
            "n_steps": n_steps,
            "seed": seed,
            "ontology": ontology,
        },
        metadata={"surface": "mcp"},
    )
    try:
        # P3: block on invalid governed yaml/config before any scaffold work
        validate_before_run(
            scenario,
            seed=seed,
            n_steps=n_steps,
            n_agents=n_agents,
            ontology_ref=ontology,
        )
        trace.record_step(
            name="validate_before_run",
            inputs={
                "scenario": scenario,
                "seed": seed,
                "n_steps": n_steps,
                "n_agents": n_agents,
                "ontology_ref": ontology,
            },
            outputs={"valid": True},
            reasoning_summary="Validated governed inputs before invoking scenario runtime.",
        )

        # Note: n_agents is advisory here; the scaffold profiles determine population size.
        # Real enforcement / population_templates come in P2 ontology layer.
        result = await execute_scenario(
            scenario,
            n_steps=n_steps,
            seed=seed,
        )
        trace.record_step(
            name="execute_scenario",
            inputs={"scenario": scenario, "n_steps": n_steps, "seed": seed},
            outputs={"run_id": result.run_id, "status": result.status},
            reasoning_summary="Ran scenario through local adapter/scaffold extension path.",
        )
        surreal_write = persist_run_artifacts(
            result,
            trace_id=trace.trace_id,
            ontology_ref=ontology,
        )
        trace.record_step(
            name="persist_run_artifacts",
            inputs={"run_id": result.run_id, "trace_id": trace.trace_id, "ontology_ref": ontology},
            outputs={
                "backend": surreal_write.get("backend"),
                "records_written": surreal_write.get("records_written"),
            },
            reasoning_summary="Persisted structured scenario artifacts to Surreal when healthy, else local fallback.",
            metadata={"surreal_write": surreal_write},
        )
        if surreal_write.get("fallback_path"):
            trace.record_artifact(
                path=str(surreal_write["fallback_path"]),
                kind="surreal_fallback_payload",
                created_by_step="persist_run_artifacts",
                metadata={"run_id": result.run_id},
            )
        trace.record_artifacts_from_run(result, created_by_step="execute_scenario")
        trace.finalize(
            outputs={"run_id": result.run_id, "status": result.status, "scenario": result.scenario},
            error=result.error,
        )
        trace.attach_to_run(result)
        _RUN_CACHE[result.run_id] = result
        return result
    except Exception as exc:
        trace.finalize(outputs={"scenario": scenario}, error=f"{type(exc).__name__}: {exc}")
        raise


@mcp.tool()
async def ask(question: str, seed: int | None = 42, ctx: Context | None = None) -> ResearchReport:
    """(P4 flow) End-to-end ask delegating to scaffold workforce when available.

    Returns a ResearchReport DTO. In full env this will populate report_path, fits, cost_report.
    """
    trace = traced(
        name="scenario_research.mcp.ask",
        inputs={"question": question, "seed": seed},
        metadata={"surface": "mcp"},
    )
    # For wiring completeness we return a shaped report; real call to scaffold.ask would populate.
    # (The scaffold cli.ask does the workforce; we keep surface here without duplicating logic.)
    from datetime import datetime, timezone

    rid = f"ask-{abs(hash(question)) % 10**8}"
    report = ResearchReport(
        report_id=rid,
        question=question,
        created_at=datetime.now(timezone.utc).isoformat(),
        seed=seed,
        cost_report=CostReport(run_id=rid),
    )
    trace.record_step(
        name="build_research_report_shape",
        inputs={"question": question, "seed": seed},
        outputs={"report_id": rid},
        reasoning_summary="Returned a typed ResearchReport shape from MCP ask surface.",
    )
    trace.finalize(outputs={"report_id": rid, "seed": seed})
    return report


@mcp.tool()
async def get_cost_report(run_id: str, ctx: Context | None = None) -> CostReport:
    """Return deterministic cost telemetry estimate for a known run."""
    run = _RUN_CACHE.get(run_id)
    if run is None:
        return CostReport(run_id=run_id, notes="run_id not found in in-process cache")
    return estimate_cost_report(run)


@mcp.tool()
async def fit_models(
    run_id: str | None = None,
    db_path: str | None = None,
    models: list[str] | None = None,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Fit lightweight model summaries over a scenario trace JSON payload."""
    resolved_path = db_path
    if run_id and run_id in _RUN_CACHE:
        resolved_path = _RUN_CACHE[run_id].db_path
    trace = load_trace_payload(resolved_path)
    fits = fit_models_from_trace(trace, models=models)
    return [f.model_dump() for f in fits]


@mcp.tool()
async def replay_policy(
    policy: dict[str, Any],
    scenario: str = "oteemo_billable",
    seed: int = 42,
    periods: int = 12,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Replay candidate policy vs baseline and return robustness deltas."""
    return replay_policy_robustness(policy, scenario=scenario, seed=seed, periods=periods)


@mcp.tool()
async def validate_agent_yaml(yaml_text: str, ctx: Context | None = None) -> dict[str, Any]:
    """P3 surface: validate governed agent yaml before simulation (AC12)."""
    try:
        return validate_agent_yaml_text(yaml_text)
    except Exception as exc:  # structured
        return {"valid": False, "error": exc if isinstance(exc, dict) else {"message": str(exc)}}


def main() -> None:
    """Entry for `scenario-research-mcp` script (stdio MCP server)."""
    mcp.run()


if __name__ == "__main__":
    main()
