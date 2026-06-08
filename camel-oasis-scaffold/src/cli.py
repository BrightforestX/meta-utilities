"""CLI entry point.

Usage:
    python -m src.cli run info_spread --agents 200 --steps 30
    python -m src.cli analyze info_spread
    python -m src.cli ask "your research question"
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich import print

app = typer.Typer(help="OASIS deep-research scaffold CLI")

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@app.command()
def run(
    scenario: str = typer.Argument(..., help="info_spread | opinion_dynamics | marketing_ab"),
    steps: int = 30,
    reps: int = 3,
):
    """Run one of the built-in scenarios."""
    if scenario == "info_spread":
        from src.scenarios.info_spread import run as r
        asyncio.run(r(n_steps=steps))
    elif scenario == "opinion_dynamics":
        from src.scenarios.opinion_dynamics import run as r
        asyncio.run(r(n_steps=steps))
    elif scenario == "marketing_ab":
        from src.scenarios.marketing_ab import run as r, DEFAULT_PROFILES
        asyncio.run(r(DEFAULT_PROFILES, DATA_DIR / "marketing_ab",
                       "Caption A", "Caption B", reps=reps, n_steps=steps))
    else:
        raise typer.BadParameter(f"unknown scenario {scenario!r}")


@app.command()
def analyze(scenario: str, db: Path = typer.Option(None, help="Path to OASIS .db")):
    """Run the math-model fits against a scenario's DB."""
    from src.analysis.metrics import cascade_report

    if db is None:
        db = DATA_DIR / f"{scenario}.db"
    if not db.exists():
        raise typer.BadParameter(f"{db} does not exist — run the scenario first.")
    rpt = cascade_report(db)
    print(rpt)


@app.command()
def ask(question: str):
    """End-to-end auto-research: planner → workers → report."""
    from camel.tasks import Task
    from src.auto_research.workforce import build_workforce

    wf = build_workforce()
    task = Task(content=question, id="user_question")
    result = wf.process_task(task)
    print(result.result)


@app.command("multi-scenario-example")
def multi_scenario_example(
    output: Path = typer.Option(
        DATA_DIR / "multi_scenarios.example.json",
        help="Where to write the example scenario JSON.",
    ),
) -> None:
    """Write an editable CAMEL multi-scenario config file."""
    from src.camel_sim.config.scenarios import write_example_scenario

    path = write_example_scenario(output)
    print({"wrote": str(path)})


@app.command("multi-scenario")
def multi_scenario(
    scenario_file: Path = typer.Argument(..., help="JSON object or array of ScenarioConfig objects."),
    output_dir: Path = typer.Option(
        DATA_DIR / "camel_sim_results",
        help="Directory for event and summary artifacts.",
    ),
    execution_mode: str = typer.Option(
        "local",
        help="local for deterministic CLI runs, camel for configured CAMEL model backends.",
    ),
    output_format: str = typer.Option("jsonl", help="jsonl | json | parquet"),
    parallel: bool = typer.Option(False, help="Run scenarios concurrently in local mode."),
) -> None:
    """Run CAMEL multi-scenario simulations from a JSON config file."""
    from src.camel_sim.config.scenarios import load_scenario_configs
    from src.camel_sim.results.collector import write_results
    from src.camel_sim.simulation.runner import run_scenarios

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


if __name__ == "__main__":
    app()
