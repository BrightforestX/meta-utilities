"""CLI entry point.

Usage:
    python -m src.cli run info_spread --agents 200 --steps 30
    python -m src.cli analyze info_spread
    python -m src.cli ask "your research question"
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich import print
from camel.tasks import Task

from src.analysis.metrics import cascade_report

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
    if db is None:
        db = DATA_DIR / f"{scenario}.db"
    if not db.exists():
        raise typer.BadParameter(f"{db} does not exist — run the scenario first.")
    rpt = cascade_report(db)
    print(rpt)


@app.command()
def ask(question: str):
    """End-to-end auto-research: planner → workers → report."""
    from src.auto_research.workforce import build_workforce
    wf = build_workforce()
    task = Task(content=question, id="user_question")
    result = wf.process_task(task)
    print(result.result)


if __name__ == "__main__":
    app()
