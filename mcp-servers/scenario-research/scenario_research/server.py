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
# Union of rich HEAD (analytics/Surreal/observability/pipeline/replay/local router/timeout full) + PR2 multi-scenario execute
from .analytics import estimate_cost_report, fit_models_from_trace, load_trace_payload
from .linkml_surreal import persist_run_artifacts, fetch_run_artifacts, query_run_attributions
from .observability import traced
from .optimization.replay import replay_policy as replay_policy_robustness
from .research_pipeline import build_research_report
from .router import resolve_endpoint, get_model_for_role, get_local_inference_config
from .scaffold_adapter import (
    dispatch_multi_scenario_to_modal as _dispatch_to_modal_impl,
    execute_multi_scenario_configs,
    execute_scenario,
    get_scaffold_root,
)
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
_RUN_CACHE: dict[str, ScenarioRun] = {}

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
            "local_inference": get_local_inference_config(),
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
async def dispatch_multi_scenario_to_modal(
    scenario_file: str,
    output_format: str = "parquet",
    execution_mode: str = "local",
    server_urls_json: str = "",
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Kick off CAMEL multi-scenario analysis on remote Modal workers.

    Thin delegation to the co-located scaffold's modal_app entrypoint (the same
    `modal run src.camel_sim.modal_app --scenario-file ...` documented in the scaffold).
    Uses the exact same portable discovery (get_scaffold_root + PYTHONPATH injection)
    so no cd into the scaffold is required and no hard-coded paths are introduced.

    The scenario_file string is interpreted relative to the MCP server's CWD (or
    absolute) and resolved before passing to the Modal CLI. Hosts/agents/TUI calling
    this tool must supply a path that is valid on the filesystem where the
    scenario-research MCP process runs.

    Kick-off semantics (fire-and-forget by design for long remote jobs): returns
    immediately with dispatch metadata (pid, constructed cmd, volume name, monitor
    and retrieval notes). The actual remote execution (run_scenario_remote.map over
    the batch + write_results_remote to the "sim-results" Modal Volume) continues
    in a detached child process.

    Forwarded options:
    - execution_mode: "local" (scripted) or "camel" (real CAMEL agents via the
      server_urls). Modal CAMEL mode requires reachable non-localhost SGLang
      endpoints (see modal_app.py guard).
    - output_format: parquet (default, recommended), jsonl, json.
    - server_urls_json: optional JSON map for custom model endpoints.

    Two-layer timeout contract (documented in timeouts.py + package README):
    - Client: SCENARIO_RESEARCH_TIMEOUT_SEC (default 1800s) caps the launch/submit
      phase (we also honor MODAL_LAUNCH_TIMEOUT_SEC if set for this path).
    - Host: tool_timeouts.dispatch_multi_scenario_to_modal (or the broader
      run_multi_scenario entry). The long-running remote job itself is timed
      and retried inside the Modal functions defined in modal_app.py (900s
      timeout + 2 retries with backoff).

    Graceful degradation:
    - If the scaffold is not discoverable: the standard helpful RuntimeError
      from get_scaffold_root (with CAMEL_OASIS_SCAFFOLD_ROOT guidance).
    - If the 'modal' CLI is not on PATH in the env running the MCP server:
      actionable message directing the user to `uv pip install -e
      'camel-oasis-scaffold[modal,parquet]'` (into the scenario-research env)
      + `modal token new`. Matches the style and content of the guard in
      modal_app.py. No requirement to cd.
    - Local and camel paths via run_multi_scenario are completely unaffected.

    This keeps the MCP surface thin and "extends, does not duplicate" the
    scaffold (all batch logic, remote mapping, volume writes, and config loading
    stay in camel-oasis-scaffold).
    """
    trace = traced(
        name="scenario_research.mcp.dispatch_multi_scenario_to_modal",
        inputs={
            "scenario_file": scenario_file,
            "output_format": output_format,
            "execution_mode": execution_mode,
            "server_urls_json_present": bool(server_urls_json),
        },
        metadata={"surface": "mcp"},
    )
    try:
        # Bound the *launch* action (two-layer). The remote job runs independently.
        launch_cap = min(SCENARIO_RESEARCH_TIMEOUT_SEC, float(os.getenv("MODAL_LAUNCH_TIMEOUT_SEC", "300")))
        try:
            async with asyncio.timeout(launch_cap):
                loop = asyncio.get_running_loop()
                payload = await loop.run_in_executor(
                    None,
                    lambda: _dispatch_to_modal_impl(
                        scenario_file,
                        output_format=output_format,
                        execution_mode=execution_mode,
                        server_urls_json=server_urls_json,
                    ),
                )
        except asyncio.TimeoutError:
            logger.warning("dispatch_multi_scenario_to_modal launch timed out after %ss", launch_cap)
            if ctx:
                try:
                    await ctx.error(f"modal dispatch launch timed out after {launch_cap}s")
                except Exception:
                    pass
            trace.finalize(outputs={"scenario_file": scenario_file}, error="launch_timeout")
            return {
                "status": "timeout",
                "error": "launch_timeout",
                "timeout_sec": launch_cap,
                "note": "The kick-off to Modal timed out. The remote job (if partially submitted) may still be running; check 'modal app list'.",
            }

        trace.record_step(
            name="dispatch_to_modal",
            inputs={"scenario_file": scenario_file},
            outputs={"status": payload.get("status"), "pid": payload.get("pid"), "volume": payload.get("volume")},
            reasoning_summary="Kicked off multi-scenario batch to remote Modal via scaffold modal_app entrypoint using portable discovery. Fire-and-forget; child continues remote execution.",
        )
        trace.finalize(outputs={"status": payload.get("status"), "pid": payload.get("pid")})
        return payload
    except Exception as exc:
        trace.finalize(outputs={"scenario_file": scenario_file}, error=f"{type(exc).__name__}: {exc}")
        # Re-raise so MCP hosts see the (actionable) error; graceful messages are inside the raised errors for missing modal/scaffold.
        raise


@mcp.tool()
async def ask(question: str, seed: int | None = 42, ctx: Context | None = None) -> ResearchReport:
    """End-to-end ask that produces report artifact, fits, costs, and scenario runs."""
    trace = traced(
        name="scenario_research.mcp.ask",
        inputs={"question": question, "seed": seed},
        metadata={"surface": "mcp"},
    )
    report, meta = await build_research_report(
        question=question,
        seed=seed,
        trace_id=trace.trace_id,
    )
    trace.record_step(
        name="build_research_report",
        inputs={"question": question, "seed": seed},
        outputs={
            "report_id": report.report_id,
            "report_path": report.report_path,
            "scenario_runs": [r.run_id for r in report.scenario_runs],
            "fits": [f.model for f in report.fits],
        },
        reasoning_summary="Built full research report pipeline with run, fits, cost telemetry, and persisted artifacts.",
        metadata={"pipeline_meta": meta},
    )
    if report.report_path:
        trace.record_artifact(
            path=report.report_path,
            kind="research_report_markdown",
            created_by_step="build_research_report",
            metadata={"report_id": report.report_id},
        )
    for run in report.scenario_runs:
        trace.record_artifacts_from_run(run, created_by_step="build_research_report")
        _RUN_CACHE[run.run_id] = run
    trace.finalize(outputs={"report_id": report.report_id, "seed": seed})
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
async def get_run_artifacts(
    run_id: str,
    prefer_surreal: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Fetch persisted scenario artifacts by run_id."""
    return fetch_run_artifacts(run_id, prefer_surreal=prefer_surreal)


@mcp.tool()
async def query_attributions(
    run_id: str,
    period_min: int | None = None,
    period_max: int | None = None,
    level: str | None = None,
    aggregate: str | None = None,
    prefer_surreal: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Query attribution rows by run with optional filters and aggregate helper."""
    return query_run_attributions(
        run_id,
        period_min=period_min,
        period_max=period_max,
        level=level,
        aggregate=aggregate,
        prefer_surreal=prefer_surreal,
    )


@mcp.tool()
async def validate_agent_yaml(yaml_text: str, ctx: Context | None = None) -> dict[str, Any]:
    """P3 surface: validate governed agent yaml before simulation (AC12)."""
    try:
        return validate_agent_yaml_text(yaml_text)
    except Exception as exc:  # structured
        return {"valid": False, "error": exc if isinstance(exc, dict) else {"message": str(exc)}}


# Ontology recall layer (Weaviate first-cut; thin surface, heavy in ontology_ingest)
# Includes explicit delete_ontology (first-class, not only implicit reindex side-effect).
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
