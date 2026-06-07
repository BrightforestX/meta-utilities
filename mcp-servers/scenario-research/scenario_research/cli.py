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

from . import __version__
from .agent_compiler import compile_scenario_spec, list_ontology_refs, resolve_ontology_base
from .router import resolve_endpoint
from .scaffold_adapter import execute_scenario
from .validation import validate_before_run

app = typer.Typer(help="ODRS scenario-research (extends camel-oasis-scaffold)")


def _version_impl() -> None:
    """Print package version."""
    print(f"scenario-research {__version__}")


def _health_impl() -> None:
    """Local health check (no MCP host required)."""
    print({"ok": True, "version": __version__, "router_smoke": resolve_endpoint("oasis_agent")})


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
    validate_before_run(
        scenario,
        seed=seed,
        n_steps=resolved_steps,
        n_agents=resolved_agents,
        ontology_ref=ontology,
    )
    r = asyncio.run(
        execute_scenario(scenario, n_steps=resolved_steps, seed=seed)
    )
    print(r.model_dump())


def _ask_impl(question: str, seed: int | None = 42) -> None:
    """P4 flow: ask delegates to scaffold workforce when importable, else surfaces ResearchReport shape."""
    try:
        from src.auto_research.workforce import build_workforce  # type: ignore
        from camel.tasks import Task  # type: ignore
        wf = build_workforce()
        task = Task(content=question, id="user_question")
        res = wf.process_task(task)
        print(res.result)
    except Exception:
        from .models import ResearchReport, CostReport
        from datetime import datetime, timezone
        rid = f"ask-{abs(hash(question)) % 10**8}"
        rpt = ResearchReport(
            report_id=rid,
            question=question,
            created_at=datetime.now(timezone.utc).isoformat(),
            seed=seed,
            cost_report=CostReport(run_id=rid),
        )
        print(rpt.model_dump())


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


def main() -> None:
    """Console script entry point for `scenario-research` (Typer app)."""
    app()


if __name__ == "__main__":
    main()
