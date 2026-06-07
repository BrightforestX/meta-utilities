"""scenario-research CLI (P0 layout).

Provides a thin entry that can delegate to the co-located camel-oasis-scaffold
or expose mcp-aware commands. For layout we ensure `scenario-research --help` works
and basic smoke (version) passes without requiring full scaffold wiring (see p0-wire-scaffold-extension).
"""
from __future__ import annotations

import sys

import typer
from rich import print

import asyncio

from . import __version__
from .models import ScenarioRun
from .router import resolve_endpoint
from .scaffold_adapter import execute_scenario, get_scaffold_root
from .ontology_ingest import ingest_ontology as _ingest_impl, search_ontology as _search_impl, COLLECTION as _ONTOLOGY_COLLECTION

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


def main() -> None:
    """Console script entry point for `scenario-research` (Typer app)."""
    app()


if __name__ == "__main__":
    main()
