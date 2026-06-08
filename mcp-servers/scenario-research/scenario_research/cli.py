"""scenario-research CLI (P0 layout).

Provides a thin entry that can delegate to the co-located camel-oasis-scaffold
or expose mcp-aware commands. For layout we ensure `scenario-research --help` works
and basic smoke (version) passes without requiring full scaffold wiring (see p0-wire-scaffold-extension).
"""
from __future__ import annotations

from typing import Any

import typer
from rich import print

import asyncio
from pathlib import Path

from . import __version__
from .models import ScenarioRun
from .router import resolve_endpoint, get_local_inference_config, probe_local_providers
from .scaffold_adapter import execute_multi_scenario_configs, execute_scenario, get_scaffold_root
from .ontology_ingest import (
    ingest_ontology as _ingest_impl,
    search_ontology as _search_impl,
    delete_ontology as _delete_impl,
    COLLECTION as _ONTOLOGY_COLLECTION,
)
# PR1 additions for full research pipeline + Surreal + local providers + observability
from .agent_compiler import compile_scenario_spec, list_ontology_refs, resolve_ontology_base
from .linkml_surreal import persist_run_artifacts, fetch_run_artifacts, query_run_attributions
from .observability import traced
from .research_pipeline import build_research_report
from .validation import validate_before_run

app = typer.Typer(help="ODRS scenario-research (extends camel-oasis-scaffold)")


def _version_impl() -> None:
    """Print package version."""
    print(f"scenario-research {__version__}")


def _health_impl() -> None:
    """Local health check (no MCP host required)."""
    print(
        {
            "ok": True,
            "version": __version__,
            "router_smoke": resolve_endpoint("oasis_agent"),
            "local_inference": get_local_inference_config(),
        }
    )


def _coerce_int(v: Any, fallback: int) -> int:
    try:
        return int(v)
    except Exception:
        return fallback


def _get_default_from_scenario(
    scenario: str,
    param: str,
    fallback: int,
    ontology_ref: str | None,
) -> int:
    ontology_base = resolve_ontology_base(ontology_ref) if ontology_ref else None
    spec = compile_scenario_spec(scenario, ontology_base=ontology_base)
    raw = ((spec.get("parameters", {}) or {}).get(param, {}) or {}).get("default")
    return _coerce_int(raw, fallback)


def _run_impl(
    scenario: str,
    agents: int | None,
    steps: int | None,
    seed: int | None,
    ontology: str | None,
) -> None:
    trace = traced(
        name="scenario_research.cli.run",
        inputs={
            "scenario": scenario,
            "agents": agents,
            "steps": steps,
            "seed": seed,
            "ontology": ontology,
        },
        metadata={"surface": "cli"},
    )
    try:
        resolved_agents = agents if agents is not None else _get_default_from_scenario(
            scenario,
            "n_agents",
            fallback=50,
            ontology_ref=ontology,
        )
        resolved_steps = steps if steps is not None else _get_default_from_scenario(
            scenario,
            "n_steps",
            fallback=5,
            ontology_ref=ontology,
        )
        trace.record_step(
            name="resolve_defaults",
            inputs={"scenario": scenario, "ontology": ontology},
            outputs={"resolved_agents": resolved_agents, "resolved_steps": resolved_steps},
            reasoning_summary="Resolved omitted CLI flags from governed ontology defaults for reproducible runs.",
        )
        validate_before_run(
            scenario,
            seed=seed,
            n_steps=resolved_steps,
            n_agents=resolved_agents,
            ontology_ref=ontology,
        )
        trace.record_step(
            name="validate_before_run",
            inputs={
                "scenario": scenario,
                "seed": seed,
                "n_steps": resolved_steps,
                "n_agents": resolved_agents,
                "ontology_ref": ontology,
            },
            outputs={"valid": True},
            reasoning_summary="Validated scenario parameters and ontology constraints before any execution.",
        )
        r = asyncio.run(
            execute_scenario(scenario, n_steps=resolved_steps, seed=seed)
        )
        trace.record_step(
            name="execute_scenario",
            inputs={"scenario": scenario, "n_steps": resolved_steps, "seed": seed},
            outputs={"run_id": r.run_id, "status": r.status},
            reasoning_summary="Executed scenario after passing validation gates.",
        )
        surreal_write = persist_run_artifacts(
            r,
            trace_id=trace.trace_id,
            ontology_ref=ontology,
        )
        trace.record_step(
            name="persist_run_artifacts",
            inputs={"run_id": r.run_id, "trace_id": trace.trace_id, "ontology_ref": ontology},
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
                metadata={"run_id": r.run_id},
            )
        trace.record_artifacts_from_run(r, created_by_step="execute_scenario")
        trace.finalize(
            outputs={"run_id": r.run_id, "status": r.status, "scenario": r.scenario},
            error=r.error,
        )
        trace.attach_to_run(r)
        print(r.model_dump())
    except Exception as exc:
        trace.finalize(outputs={"scenario": scenario}, error=f"{type(exc).__name__}: {exc}")
        raise


def _ask_impl(question: str, seed: int | None = 42) -> None:
    """Run full ask pipeline and emit a report artifact summary."""
    trace = traced(
        name="scenario_research.cli.ask",
        inputs={"question": question, "seed": seed},
        metadata={"surface": "cli"},
    )
    report, meta = asyncio.run(build_research_report(question=question, seed=seed, trace_id=trace.trace_id))
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
    trace.finalize(outputs={"report_id": report.report_id, "seed": seed})
    print(report.model_dump())


def _artifacts_impl(run_id: str, prefer_surreal: bool = True) -> None:
    """Fetch persisted run artifacts from Surreal or fallback payload files."""
    out = fetch_run_artifacts(run_id, prefer_surreal=prefer_surreal)
    print(out)


def _attributions_impl(
    run_id: str,
    *,
    period_min: int | None = None,
    period_max: int | None = None,
    level: str | None = None,
    aggregate: str | None = None,
    prefer_surreal: bool = True,
) -> None:
    out = query_run_attributions(
        run_id,
        period_min=period_min,
        period_max=period_max,
        level=level,
        aggregate=aggregate,
        prefer_surreal=prefer_surreal,
    )
    print(out)


@app.command()
def version() -> None:
    """Print package version."""
    _version_impl()


@app.command("v")
def version_short() -> None:
    """Short alias for version."""
    _version_impl()


@app.command()
def health() -> None:
    """Local health check (no MCP host required)."""
    _health_impl()


@app.command("h")
def health_short() -> None:
    """Short alias for health."""
    _health_impl()


@app.command()
def ontologies() -> None:
    """List ontology references available to CLI/MCP.

    You can reference ontologies by either:
    - folder name (e.g. agents)
    - LinkML `name` in the ontology schema (e.g. odrs_agents)
    """
    refs = list_ontology_refs()
    print({"ontologies": refs})


@app.command("onts")
def ontologies_short() -> None:
    """Short alias for ontologies."""
    ontologies()


@app.command()
def providers(
    active_only: bool = typer.Option(
        False,
        "--active-only",
        help="Probe only the currently active provider.",
    ),
    timeout_sec: float = typer.Option(
        1.5,
        "--timeout-sec",
        help="Per-provider HTTP probe timeout in seconds.",
    ),
) -> None:
    """Probe local provider reachability (Ollama, LM Studio, turnover)."""
    local = get_local_inference_config()
    rows = probe_local_providers(active_only=active_only, timeout_sec=timeout_sec)
    print(
        {
            "active_provider": local["provider"],
            "active_model": local["model"],
            "active_base_url": local["base_url"],
            "providers": rows,
        }
    )


@app.command("prov")
def providers_short(
    active_only: bool = typer.Option(False, "--active-only"),
    timeout_sec: float = typer.Option(1.5, "--timeout-sec"),
) -> None:
    """Short alias for providers."""
    providers(active_only=active_only, timeout_sec=timeout_sec)


@app.command()
def artifacts(
    run_id: str = typer.Argument(..., help="Scenario run_id to fetch persisted artifacts for."),
    prefer_surreal: bool = typer.Option(
        True,
        "--prefer-surreal/--prefer-fallback",
        help="Try Surreal first (default) or go straight to local fallback payload.",
    ),
) -> None:
    """Fetch persisted run artifacts (ScenarioTrace/Attribution/context)."""
    _artifacts_impl(run_id=run_id, prefer_surreal=prefer_surreal)


@app.command("arts")
def artifacts_short(
    run_id: str = typer.Argument(...),
    prefer_surreal: bool = typer.Option(True, "--prefer-surreal/--prefer-fallback"),
) -> None:
    """Short alias for artifacts."""
    _artifacts_impl(run_id=run_id, prefer_surreal=prefer_surreal)


@app.command()
def attributions(
    run_id: str = typer.Argument(..., help="Scenario run_id to query attribution rows for."),
    period_min: int | None = typer.Option(None, "--period-min", help="Filter for period >= value."),
    period_max: int | None = typer.Option(None, "--period-max", help="Filter for period <= value."),
    level: str | None = typer.Option(None, "--level", help="Filter by attribution level."),
    aggregate: str | None = typer.Option(
        None,
        "--aggregate",
        help="Aggregate helper: sum_cost_by_level | sum_delta_by_period",
    ),
    prefer_surreal: bool = typer.Option(
        True,
        "--prefer-surreal/--prefer-fallback",
        help="Try Surreal first (default) or go straight to local fallback payload.",
    ),
) -> None:
    """Query run attributions with filters and aggregate helpers."""
    _attributions_impl(
        run_id,
        period_min=period_min,
        period_max=period_max,
        level=level,
        aggregate=aggregate,
        prefer_surreal=prefer_surreal,
    )


@app.command("attrs")
def attributions_short(
    run_id: str = typer.Argument(...),
    period_min: int | None = typer.Option(None, "--period-min"),
    period_max: int | None = typer.Option(None, "--period-max"),
    level: str | None = typer.Option(None, "--level"),
    aggregate: str | None = typer.Option(None, "--aggregate"),
    prefer_surreal: bool = typer.Option(True, "--prefer-surreal/--prefer-fallback"),
) -> None:
    """Short alias for attributions."""
    _attributions_impl(
        run_id,
        period_min=period_min,
        period_max=period_max,
        level=level,
        aggregate=aggregate,
        prefer_surreal=prefer_surreal,
    )


@app.command()
def run(
    scenario: str = typer.Argument(..., help="info_spread | opinion_dynamics | marketing_ab | oteemo_billable (self-contained, no scaffold dep)"),
    agents: int | None = typer.Option(None, "--agents", "-a", help="Agent count; defaults from ontology scenario parameters."),
    steps: int | None = typer.Option(None, "--steps", "-n", help="Step count; defaults from ontology scenario parameters."),
    seed: int | None = typer.Option(42, "--seed", "-s", help="Deterministic seed for reproducibility."),
    ontology: str | None = typer.Option(None, "--ontology", "-o", help="Ontology folder name or LinkML schema name."),
) -> None:
    """Run governed scenario. Defaults are loaded from ontology when omitted."""
    _run_impl(scenario=scenario, agents=agents, steps=steps, seed=seed, ontology=ontology)


@app.command("r")
def run_short(
    scenario: str = typer.Argument(..., help="Scenario name"),
    agents: int | None = typer.Option(None, "--agents", "-a"),
    steps: int | None = typer.Option(None, "--steps", "-n"),
    seed: int | None = typer.Option(42, "--seed", "-s"),
    ontology: str | None = typer.Option(None, "--ontology", "-o"),
) -> None:
    """Short alias for run."""
    _run_impl(scenario=scenario, agents=agents, steps=steps, seed=seed, ontology=ontology)


@app.command("multi-run")
def multi_run(
    scenario_file: Path = typer.Argument(..., help="JSON object or array of CAMEL ScenarioConfig objects."),
    output_dir: Path | None = typer.Option(
        None,
        help="Output directory for event and summary artifacts.",
    ),
    execution_mode: str = typer.Option(
        "local",
        help="local for deterministic CLI runs, camel for configured CAMEL model backends.",
    ),
    output_format: str = typer.Option("jsonl", help="jsonl | json | parquet"),
    parallel: bool = typer.Option(False, help="Run scenarios concurrently in local mode."),
) -> None:
    """Run the CAMEL multi-scenario service via the co-located scaffold."""
    root = get_scaffold_root()
    if output_dir is None:
        output_dir = root / "data" / "camel_sim_results"

    from src.camel_sim.config.scenarios import load_scenario_configs  # type: ignore

    configs = load_scenario_configs(scenario_file)
    payload = execute_multi_scenario_configs(
        [cfg.model_dump() for cfg in configs],
        execution_mode=execution_mode,
        parallel=parallel,
        output_dir=output_dir,
        output_format=output_format,  # type: ignore[arg-type]
    )
    print(
        {
            "scenarios": payload["scenarios"],
            "execution_mode": payload["execution_mode"],
            "artifacts": payload["artifacts"],
        }
    )


@app.command()
def ask(
    question: str,
    seed: int | None = typer.Option(42, "--seed", "-s"),
) -> None:
    """Ask research question with optional seed."""
    _ask_impl(question=question, seed=seed)


@app.command("q")
def ask_short(
    question: str,
    seed: int | None = typer.Option(42, "--seed", "-s"),
) -> None:
    """Short alias for ask."""
    _ask_impl(question=question, seed=seed)


@app.command("ingest-ontology")
def ingest_ontology(
    target: str = typer.Option("weaviate", help="Target backend (first-cut: weaviate)"),
    paths: list[str] = typer.Option(None, "--paths", help="Explicit ontology roots (default: auto shared + oteemo)"),
) -> None:
    """Ingest ontology trees (shared + oteemo vertical) into Weaviate meta_ontology (or RESEARCH_ONTOLOGY_COLLECTION).
    Disk YAMLs remain source of truth. Idempotent clear+insert first-cut.
    Graceful if Weaviate or [research] extra absent.
    """
    res = asyncio.run(_ingest_impl(target=target, paths=paths or None))
    print(res)


@app.command("search-ontology")
def search_ontology(
    query: str = typer.Argument(..., help="Semantic query over meta_ontology chunks (roles/policies/tools/LinkML)"),
    top_k: int = typer.Option(5, help="Max results"),
) -> None:
    """Semantic search (Weaviate near_vector) over the governed ontology recall layer.
    Falls back to graceful message if Weaviate unavailable (sources on disk are canonical).
    """
    res = asyncio.run(_search_impl(query=query, top_k=top_k))
    print(res)


@app.command("delete-ontology")
def delete_ontology(
    target: str | None = typer.Argument(None, help="If no --flags: treated as --name value (convenience, e.g. scenario-research delete-ontology raja_gudepu_ceo)"),
    name: str | None = typer.Option(None, "--name", help="Exact name match (e.g. raja_gudepu_ceo or MemoryItem)"),
    entity_type: str | None = typer.Option(None, "--entity-type", help="e.g. role | policy | tool | class | attribute (advanced; use with care)"),
    source: str | None = typer.Option(None, "--source", help="Source prefix match (e.g. oteemo/ontology/agents or ontology/)"),
    all_for_source: bool = typer.Option(False, "--all-for-source", help="Convenience for source-based broad clear (same effect as --source with prefix)"),
    delete_all: bool = typer.Option(False, "--all", help="BROAD DELETE ALL objects in meta_ontology (DANGEROUS — no filter; disk YAMLs untouched but recall layer reset)"),
) -> None:
    """Delete from Weaviate meta_ontology recall layer (explicit, first-class; was previously only implicit reindex side-effect inside ingest).
    Selectors are AND-combined. source is prefix (like *src*). Idempotent (deleted=0 if no match).
    Graceful if Weaviate or [research] extra absent (sources on disk remain canonical; pure-sim unaffected).
    Two-layer timeout protected.
    """
    n = name or target
    eff_source = source
    eff_delete_all = delete_all or all_for_source
    res = asyncio.run(
        _delete_impl(name=n, entity_type=entity_type, source=eff_source, delete_all=eff_delete_all)
    )
    print(res)


def main() -> None:
    """Console script entry point for `scenario-research` (Typer app)."""
    app()


if __name__ == "__main__":
    main()
