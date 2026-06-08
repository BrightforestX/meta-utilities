"""scenario-research CLI (P0 layout).

Provides a thin entry that can delegate to the co-located camel-oasis-scaffold
or expose mcp-aware commands. For layout we ensure `scenario-research --help` works
and basic smoke (version) passes without requiring full scaffold wiring (see p0-wire-scaffold-extension).
"""
from __future__ import annotations

import typer
from rich import print

import asyncio
from pathlib import Path

from . import __version__
from .router import resolve_endpoint
from .scaffold_adapter import execute_scenario, get_scaffold_root

app = typer.Typer(help="ODRS scenario-research (extends camel-oasis-scaffold)")


@app.command()
def version() -> None:
    """Print package version."""
    print(f"scenario-research {__version__}")


@app.command()
def health() -> None:
    """Local health check (no MCP host required)."""
    print({"ok": True, "version": __version__, "router_smoke": resolve_endpoint("oasis_agent")})


@app.command()
def run(
    scenario: str = typer.Argument(..., help="info_spread | opinion_dynamics | marketing_ab | oteemo_billable (self-contained, no scaffold dep)"),
    agents: int = 50,
    steps: int = 5,
    seed: int | None = 42,
) -> None:
    """Run governed scenario. oteemo_billable is fully local (extends adapter without camel-oasis)."""
    r = asyncio.run(
        execute_scenario(scenario, n_steps=steps, seed=seed)
    )
    print(r.model_dump())


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
    from src.camel_sim.results.collector import write_results  # type: ignore
    from src.camel_sim.simulation.runner import run_scenarios  # type: ignore

    configs = load_scenario_configs(scenario_file)
    results = run_scenarios(configs, execution_mode=execution_mode, parallel=parallel)
    artifacts = write_results(
        results,
        output_dir,
        output_format=output_format,  # type: ignore[arg-type]
    )
    print(
        {
            "scenarios": len(results),
            "execution_mode": execution_mode,
            "artifacts": artifacts,
        }
    )


@app.command()
def ask(question: str, seed: int | None = 42):
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


def main() -> None:
    """Console script entry point for `scenario-research` (Typer app)."""
    app()


if __name__ == "__main__":
    main()
