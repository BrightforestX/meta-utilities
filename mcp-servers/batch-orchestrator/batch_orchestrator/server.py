"""FastMCP server for batch orchestration."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from fastmcp import Context, FastMCP

from batch_orchestrator.engine import BatchEngine
from batch_orchestrator.models import load_manifest
from batch_orchestrator.store import BatchStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] batch-orchestrator: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="batch-orchestrator",
    instructions=(
        "YAML-driven batch queue for deep research and inference. "
        "Submit job manifests, track status, collect provider batch results, "
        "or run multi-stage deep research pipelines."
    ),
)

_store = BatchStore()


def _engine(ctx: Context | None = None) -> BatchEngine:
    async def on_progress(run_id: str, event: str, data: dict[str, Any]) -> None:
        if ctx:
            await ctx.info(f"[{run_id}] {event}: {data.get('job_id', '')}")

    return BatchEngine(store=_store, on_progress=on_progress if ctx else None)


@mcp.tool()
async def submit_batch(
    manifest_path: str,
    output_dir: str | None = None,
    wait_for_batch: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """
    Submit and run a batch job manifest (YAML file).

    Args:
        manifest_path: Path to jobs.yaml manifest on disk.
        output_dir: Optional override for artifact output directory.
        wait_for_batch: If true, block until provider batch API jobs complete.

    Returns:
        Run status including run_id, job statuses, and output paths.
    """
    path = Path(manifest_path).resolve()
    if not path.exists():
        return {"error": f"manifest not found: {path}"}

    if ctx:
        await ctx.info(f"Loading manifest: {path}")

    try:
        manifest = load_manifest(path)
    except Exception as e:
        return {"error": f"invalid manifest: {e}"}

    engine = _engine(ctx)
    out = output_dir or manifest.output_dir
    run_id = engine.start_run(manifest, str(path), out)

    if ctx:
        await ctx.report_progress(0, 100, f"Started run {run_id}")

    status = await engine.run(
        run_id,
        wait_for_batch=wait_for_batch,
        manifest_dir=path.parent,
    )

    if ctx:
        await ctx.report_progress(100, 100, f"Run {status['status']}")

    return status


@mcp.tool()
async def get_batch_status(run_id: str) -> dict[str, Any]:
    """
    Get status of a batch run and all its jobs.

    Args:
        run_id: The run id returned by submit_batch.

    Returns:
        Run metadata and per-job status records.
    """
    engine = _engine()
    try:
        return engine.get_status(run_id)
    except KeyError:
        return {"error": f"run not found: {run_id}"}


@mcp.tool()
async def collect_batch_results(run_id: str, ctx: Context | None = None) -> dict[str, Any]:
    """
    Poll provider batch APIs and collect completed results for a run.

    Use when submit_batch returned status 'waiting_batch'.

    Args:
        run_id: The run id to collect results for.

    Returns:
        Updated run status after collection.
    """
    if ctx:
        await ctx.info(f"Collecting batch results for run {run_id}")

    engine = _engine(ctx)
    try:
        return await engine.collect_batches(run_id)
    except KeyError:
        return {"error": f"run not found: {run_id}"}


@mcp.tool()
async def run_research_pipeline(
    query: str,
    depth: str = "comparative",
    provider: str = "perplexity",
    max_subagents: int = 5,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """
    Run a multi-stage deep research pipeline for a single query.

    Stages: triage -> fan-out subagents -> synthesis -> reflection/replan.

    Args:
        query: Research question or topic.
        depth: simple | comparative | deep
        provider: perplexity | grok | openai
        max_subagents: Max parallel research subagents (capped by depth tier).

    Returns:
        Synthesized research report with citations.
    """
    from batch_orchestrator.models import DefaultsConfig, Job, Manifest

    if ctx:
        await ctx.info(f"Starting research pipeline (depth={depth})")

    manifest = Manifest(
        output_dir="./batch-results",
        defaults=DefaultsConfig(provider=provider),  # type: ignore[arg-type]
        jobs=[
            Job(
                id="pipeline",
                type="deep_research_pipeline",
                query=query,
                depth=depth,  # type: ignore[arg-type]
                max_subagents=max_subagents,
                provider=provider,  # type: ignore[arg-type]
            )
        ],
    )

    engine = _engine(ctx)
    run_id = engine.start_run(manifest, "<inline-pipeline>", manifest.output_dir)
    status = await engine.run(run_id, wait_for_batch=True)

    if status["jobs"] and status["jobs"][0].get("result_path"):
        import json

        result_path = Path(status["jobs"][0]["result_path"])
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            return {
                "run_id": run_id,
                "status": status["status"],
                "report": result.get("report", ""),
                "citations": result.get("citations", []),
                "sub_queries": result.get("sub_queries", []),
                "pipeline_depth": depth,
            }

    return {"run_id": run_id, "status": status["status"], "jobs": status["jobs"]}


@mcp.tool()
def list_batch_runs(limit: int = 10) -> dict[str, Any]:
    """List recent batch runs."""
    runs = _store.list_runs(limit=limit)
    return {
        "runs": [
            {
                "run_id": r.id,
                "status": r.status,
                "manifest_path": r.manifest_path,
                "output_dir": r.output_dir,
                "created_at": r.created_at,
            }
            for r in runs
        ]
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Batch Orchestrator MCP Server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        logger.info("Starting batch-orchestrator MCP server (stdio)")
        mcp.run()


if __name__ == "__main__":
    main()
