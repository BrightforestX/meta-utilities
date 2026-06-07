"""CLI entry point for meta-batch."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from batch_orchestrator.engine import BatchEngine
from batch_orchestrator.models import load_manifest
from batch_orchestrator.store import BatchStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] meta-batch: %(message)s",
    stream=sys.stderr,
)


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.manifest)
    if not path.exists():
        print(f"Error: manifest not found: {path}", file=sys.stderr)
        return 1
    try:
        manifest = load_manifest(path)
        print(f"Valid manifest with {len(manifest.jobs)} job(s)")
        for job in manifest.jobs:
            deps = f" (depends_on: {job.depends_on})" if job.depends_on else ""
            print(f"  - {job.id}: type={job.type}, mode={job.resolved_mode(manifest.defaults)}{deps}")
        return 0
    except Exception as e:
        print(f"Validation failed: {e}", file=sys.stderr)
        return 1


async def cmd_run(args: argparse.Namespace) -> int:
    path = Path(args.manifest).resolve()
    if not path.exists():
        print(f"Error: manifest not found: {path}", file=sys.stderr)
        return 1

    try:
        manifest = load_manifest(path)
    except Exception as e:
        print(f"Failed to load manifest: {e}", file=sys.stderr)
        return 1

    topic = getattr(args, "topic", None)
    if topic:
        print(f"Topic from --topic: {topic}")
        for j in manifest.jobs:
            if j.type in ("deep_research", "deep_research_pipeline"):
                base = j.query or ""
                if topic not in base:
                    j.query = f"{base} (CLI topic: {topic})".strip()

    store = BatchStore(db_path=args.db) if args.db else BatchStore()
    engine = BatchEngine(store=store)

    output_dir = args.output_dir or manifest.output_dir
    run_id = engine.start_run(manifest, str(path), output_dir, run_id=args.run_id)
    print(f"Started run {run_id}")
    print(f"Output directory: {output_dir}")

    status = await engine.run(
        run_id,
        wait_for_batch=args.wait,
        manifest_dir=path.parent,
    )
    print(json.dumps(status, indent=2))

    if status["status"] == "waiting_batch":
        print("\nSome jobs submitted to provider batch APIs. Run:")
        print(f"  meta-batch collect {run_id}")
        return 0
    return 0 if status["status"] == "succeeded" else 1


async def cmd_collect(args: argparse.Namespace) -> int:
    store = BatchStore(db_path=args.db) if args.db else BatchStore()
    engine = BatchEngine(store=store)
    try:
        status = await engine.collect_batches(args.run_id)
    except KeyError:
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        return 1
    print(json.dumps(status, indent=2))
    return 0 if status["status"] in ("succeeded", "running") else 1


async def cmd_resume(args: argparse.Namespace) -> int:
    store = BatchStore(db_path=args.db) if args.db else BatchStore()
    engine = BatchEngine(store=store)
    try:
        run = store.get_run(args.run_id)
    except KeyError:
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        return 1

    manifest = store.get_manifest(args.run_id)
    status = await engine.run(
        args.run_id,
        wait_for_batch=args.wait,
        manifest_dir=Path(run.manifest_path).parent,
    )
    print(json.dumps(status, indent=2))
    return 0 if status["status"] == "succeeded" else 1


def cmd_status(args: argparse.Namespace) -> int:
    store = BatchStore(db_path=args.db) if args.db else BatchStore()
    engine = BatchEngine(store=store)

    if args.run_id:
        try:
            status = engine.get_status(args.run_id)
            print(json.dumps(status, indent=2))
            return 0
        except KeyError:
            print(f"Run not found: {args.run_id}", file=sys.stderr)
            return 1

    runs = store.list_runs(limit=args.limit)
    if not runs:
        print("No runs found.")
        return 0
    for r in runs:
        print(f"{r.id}  {r.status}  {r.manifest_path}  ({r.created_at})")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="meta-batch",
        description="YAML-driven batch queue for deep research and inference",
    )
    parser.add_argument(
        "--db",
        help="Path to SQLite state database (default: ~/.meta-utilities/batch-orchestrator.db)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Validate a job manifest YAML")
    p_validate.add_argument("manifest", help="Path to jobs.yaml manifest")
    p_validate.set_defaults(func=cmd_validate)

    p_run = sub.add_parser("run", help="Run jobs from a manifest")
    p_run.add_argument("manifest", help="Path to jobs.yaml manifest")
    p_run.add_argument("--output-dir", help="Override manifest output_dir")
    p_run.add_argument("--run-id", help="Optional run id (for resumable named runs)")
    p_run.add_argument(
        "--wait",
        action="store_true",
        help="Block until provider batch jobs complete (may take up to 24h)",
    )
    p_run.set_defaults(func=lambda a: asyncio.run(cmd_run(a)))

    p_submit = sub.add_parser("submit", help="Submit/run manifest (plan-compatible alias to 'run'; accepts --topic)")
    p_submit.add_argument("manifest", help="Path to jobs.yaml manifest")
    p_submit.add_argument("--output-dir", help="Override manifest output_dir")
    p_submit.add_argument("--run-id", help="Optional run id (for resumable named runs)")
    p_submit.add_argument(
        "--wait",
        action="store_true",
        help="Block until provider batch jobs complete (may take up to 24h)",
    )
    p_submit.add_argument("--topic", help="Research topic override (for exact dogfood cmds like Task 2.3)")
    p_submit.set_defaults(func=lambda a: asyncio.run(cmd_run(a)))

    p_status = sub.add_parser("status", help="Show run status or list recent runs")
    p_status.add_argument("run_id", nargs="?", help="Run id (omit to list recent runs)")
    p_status.add_argument("--limit", type=int, default=20)
    p_status.set_defaults(func=cmd_status)

    p_collect = sub.add_parser(
        "collect", help="Poll and collect completed provider batch jobs"
    )
    p_collect.add_argument("run_id", help="Run id")
    p_collect.set_defaults(func=lambda a: asyncio.run(cmd_collect(a)))

    p_resume = sub.add_parser("resume", help="Resume an incomplete run")
    p_resume.add_argument("run_id", help="Run id")
    p_resume.add_argument("--wait", action="store_true")
    p_resume.set_defaults(func=lambda a: asyncio.run(cmd_resume(a)))

    args = parser.parse_args()
    result = args.func(args)
    sys.exit(result if isinstance(result, int) else 0)


if __name__ == "__main__":
    main()
