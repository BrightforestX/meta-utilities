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

import asyncio
import logging
import os
import sys
from typing import Any

from fastmcp import FastMCP, Context

from .models import ScenarioRun, CostReport, ResearchReport
from .router import resolve_endpoint, get_model_for_role
from .scaffold_adapter import execute_scenario, get_scaffold_root
from .timeouts import ENV_VAR as TIMEOUT_ENV_VAR, get_timeout_seconds, LONG_RUNNING_TOOLS, DEFAULT_TIMEOUT_SEC
from .validation import validate_agent_yaml_text, validate_before_run, validate_run_payload

# Ontology recall (Weaviate first-cut; additive, disk YAMLs remain source of truth)
from .ontology_ingest import (
    ingest_ontology as _ingest_ontology_impl,
    search_ontology as _search_ontology_impl,
    delete_ontology as _delete_ontology_impl,
)
from . import ontology_ingest as _ontology_ingest_mod  # for health surface + direct CLI entrypoint discovery + COLLECTION + DELETE_TIMEOUT etc.

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
        "New: first-class ontology recall via Weaviate (meta_ontology collection) with ingest_ontology + search_ontology + delete_ontology. "
        "Disk YAMLs (ontology/ + oteemo/ontology/) remain the source of truth; Weaviate is semantic recall/RAG only. "
        "Deletes are explicit (no longer only implicit side-effect of ingest); selectors by name/entity_type/source prefix or broad (safety in UI/CLI). "
        "LinkML -> Weaviate collections (additive to Surreal path). "
        "Two-layer timeouts: SCENARIO_RESEARCH_TIMEOUT_SEC (client) + host tool_timeouts entry. "
        "PostgreSQL is optional; SQLite is the portable default baseline. "
        "Pure simulation and all prior flows unaffected if Weaviate/research extra absent."
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
        "contracts": ["ScenarioRun", "ModelFitResult", "CostReport", "ResearchReport", "OntologyChunk", "LinkMLClass"],
        "ontology": {
            "ingest_tool": "ingest_ontology",
            "search_tool": "search_ontology",
            "delete_tool": "delete_ontology",
            "default_collection": "meta_ontology",
            "env_override": "RESEARCH_ONTOLOGY_COLLECTION | WEAVIATE_ONTOLOGY_COLLECTION",
            "graceful": "if Weaviate/research extra absent: clear msg; disk YAMLs + pure-sim 100% functional. Deletes now first-class (TUI/CLI/MCP) and DRY-called from ingest.",
            "selectors": "name (exact), entity_type, source (prefix via like), delete_all (broad, use carefully)",
        },
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

# --- Ontology recall layer (Weaviate first-cut; thin surface, heavy in ontology_ingest) ---
@mcp.tool()
async def ingest_ontology(target: str = "weaviate", paths: list[str] | None = None, ctx: Context | None = None) -> dict[str, Any]:
    """
    Walk shared ontology/ + oteemo/ontology/ (or explicit paths), chunk governed roles/policies/tools + LinkML classes/attrs,
    ensure meta_ontology (and LinkML-derived) Weaviate collections, embed+insert with stable ids + source tags.
    Idempotent first-cut: clears prior objects for the walked sources before insert.
    Source of truth remains the YAMLs on disk (git). Weaviate is for semantic recall/RAG only.
    Graceful if Weaviate or [research] extra unavailable.
    Two-layer timeout protected (client SCENARIO_RESEARCH_TIMEOUT_SEC + host tool_timeouts.ingest_ontology).
    """
    try:
        async with asyncio.timeout(SCENARIO_RESEARCH_TIMEOUT_SEC):
            return await _ingest_ontology_impl(target=target, paths=paths, ctx=ctx)
    except asyncio.TimeoutError:
        logger.warning("ingest_ontology timed out after %ss", SCENARIO_RESEARCH_TIMEOUT_SEC)
        if ctx:
            try:
                await ctx.error(f"timeout after {SCENARIO_RESEARCH_TIMEOUT_SEC}s")
            except Exception:
                pass
        return {"ok": False, "error": "timeout", "collection": _ontology_ingest_mod.COLLECTION}

@mcp.tool()
async def search_ontology(query: str, top_k: int = 5, ctx: Context | None = None) -> list[dict[str, Any]]:
    """
    Semantic (near_vector) search over the meta_ontology Weaviate collection (ontology chunks).
    Returns ranked hits with source, entity_type (role/policy/tool/class/attribute), name, text snippet, tags.
    If Weaviate unavailable, returns a single graceful error item (disk sources remain canonical).
    """
    try:
        async with asyncio.timeout(min(SCENARIO_RESEARCH_TIMEOUT_SEC, 60.0)):
            return await _search_ontology_impl(query=query, top_k=top_k, ctx=ctx)
    except asyncio.TimeoutError:
        logger.warning("search_ontology timed out")
        if ctx:
            try:
                await ctx.error("search timed out")
            except Exception:
                pass
        return [{"error": "timeout"}]


@mcp.tool()
async def delete_ontology(
    name: str | None = None,
    entity_type: str | None = None,
    source: str | None = None,
    delete_all: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """
    Delete objects from the meta_ontology Weaviate collection (recall layer only; disk YAMLs under ontology/ + oteemo/ontology/ are untouched and remain canonical).
    Selectors (AND-combined when >1): name (exact match), entity_type (role|policy|tool|class|attribute), source (prefix match, e.g. "oteemo/ontology/agents").
    delete_all=True (no other selectors) performs broad delete of the collection (DANGEROUS — use only for reset; CLI/TUI surfaces strong warnings).
    Idempotent: returns deleted=0 if no matches. Returns deleted count + sample of removed 'name' values.
    Graceful if Weaviate / [research] extra absent (same contract as ingest/search).
    Two-layer timeout (client SCENARIO_RESEARCH_TIMEOUT_SEC capped short for delete + host tool_timeouts.delete_ontology).
    Makes deletes first-class / explicit (previously only implicit side-effect inside ingest_ontology for reindex idempotency).
    """
    try:
        async with asyncio.timeout(min(SCENARIO_RESEARCH_TIMEOUT_SEC, 60.0)):
            return await _delete_ontology_impl(
                name=name, entity_type=entity_type, source=source, delete_all=delete_all, ctx=ctx
            )
    except asyncio.TimeoutError:
        logger.warning("delete_ontology timed out")
        if ctx:
            try:
                await ctx.error("delete timed out")
            except Exception:
                pass
        return {"ok": False, "error": "timeout", "deleted": 0, "collection": _ontology_ingest_mod.COLLECTION}


def main() -> None:
    """Entry for `scenario-research-mcp` script (stdio MCP server)."""
    mcp.run()


if __name__ == "__main__":
    main()
