"""LangSmith-backed tracing + local lineage ledger for scenario-research.

Tracks explicit reasoning summaries, tool/function step boundaries, and artifacts
created during each run. LangSmith is used when configured; local JSON ledgers
are always written for replayability and testability.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ScenarioRun


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    # scenario_research/ -> scenario-research/
    return Path(__file__).resolve().parents[1]


def _trace_dir() -> Path:
    configured = os.environ.get("SCENARIO_RESEARCH_TRACE_DIR")
    if configured:
        p = Path(configured)
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = _repo_root() / ".context" / "scenario-research-traces"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _langsmith_enabled() -> bool:
    val = os.environ.get("LANGSMITH_TRACING", "true").strip().lower()
    return val not in {"0", "false", "off", "no"}


def _create_langsmith_client() -> Any | None:
    if not _langsmith_enabled():
        return None
    try:
        from langsmith import Client  # type: ignore

        return Client()
    except Exception:
        return None


class TraceSession:
    """Track one end-to-end request/run with optional LangSmith publishing."""

    def __init__(
        self,
        *,
        name: str,
        inputs: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        project_name: str | None = None,
        run_type: str = "chain",
    ) -> None:
        self.name = name
        self.inputs = inputs
        self.metadata = metadata or {}
        self.project_name = project_name or os.environ.get(
            "LANGSMITH_PROJECT", "scenario-research"
        )
        self.run_type = run_type

        self.trace_id = str(uuid.uuid4())
        self.root_run_id = str(uuid.uuid4())
        self.created_at = _utc_now_iso()
        self.finished_at: str | None = None
        self.trace_url: str | None = None

        self.steps: list[dict[str, Any]] = []
        self.artifacts: list[dict[str, Any]] = []
        self.outputs: dict[str, Any] | None = None
        self.error: str | None = None

        self._client = _create_langsmith_client()
        if self._client is not None:
            try:
                self._client.create_run(
                    id=self.root_run_id,
                    name=self.name,
                    run_type=self.run_type,
                    project_name=self.project_name,
                    inputs=self.inputs,
                    extra={"metadata": {"trace_id": self.trace_id, **self.metadata}},
                )
            except Exception:
                self._client = None

    def record_step(
        self,
        *,
        name: str,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        reasoning_summary: str | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = "succeeded",
    ) -> None:
        step = {
            "name": name,
            "status": status,
            "inputs": inputs or {},
            "outputs": outputs or {},
            "reasoning_summary": reasoning_summary or "",
            "metadata": metadata or {},
            "started_at": _utc_now_iso(),
            "finished_at": _utc_now_iso(),
        }
        self.steps.append(step)

        if self._client is None:
            return

        child_id = str(uuid.uuid4())
        try:
            self._client.create_run(
                id=child_id,
                name=name,
                parent_run_id=self.root_run_id,
                run_type="tool",
                project_name=self.project_name,
                inputs=step["inputs"],
                extra={
                    "metadata": {
                        "trace_id": self.trace_id,
                        "reasoning_summary": step["reasoning_summary"],
                        **step["metadata"],
                    }
                },
            )
            self._client.update_run(
                run_id=child_id,
                outputs=step["outputs"],
                end_time=datetime.now(timezone.utc),
            )
        except Exception:
            # Keep local ledger as source of truth when remote tracing fails.
            pass

    def record_artifact(
        self,
        *,
        path: str,
        kind: str,
        created_by_step: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        p = Path(path)
        item = {
            "path": str(p),
            "kind": kind,
            "created_by_step": created_by_step,
            "exists": p.exists(),
            "size_bytes": p.stat().st_size if p.exists() else None,
            "metadata": metadata or {},
        }
        self.artifacts.append(item)

    def record_artifacts_from_run(self, run: ScenarioRun, *, created_by_step: str) -> None:
        if run.db_path:
            self.record_artifact(
                path=run.db_path,
                kind="scenario_db_or_trace",
                created_by_step=created_by_step,
                metadata={"scenario": run.scenario, "run_id": run.run_id},
            )

    def attach_to_run(self, run: ScenarioRun) -> None:
        snap = dict(run.config_snapshot or {})
        snap["observability"] = {
            "trace_id": self.trace_id,
            "trace_url": self.trace_url,
            "artifacts": self.artifacts,
        }
        run.config_snapshot = snap

    def finalize(self, *, outputs: dict[str, Any] | None = None, error: str | None = None) -> None:
        self.finished_at = _utc_now_iso()
        self.outputs = outputs or {}
        self.error = error

        if self._client is not None:
            try:
                self._client.update_run(
                    run_id=self.root_run_id,
                    outputs=self.outputs,
                    error=self.error,
                    end_time=datetime.now(timezone.utc),
                )
                # get_run_url is not available in all versions/environments; best-effort.
                try:
                    self.trace_url = str(
                        self._client.get_run_url(  # type: ignore[attr-defined]
                            run_id=self.root_run_id,
                            project_name=self.project_name,
                        )
                    )
                except Exception:
                    self.trace_url = None
            except Exception:
                pass

        payload = {
            "trace_id": self.trace_id,
            "root_run_id": self.root_run_id,
            "name": self.name,
            "project_name": self.project_name,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "inputs": self.inputs,
            "metadata": self.metadata,
            "steps": self.steps,
            "artifacts": self.artifacts,
            "outputs": self.outputs,
            "error": self.error,
            "trace_url": self.trace_url,
        }
        out = _trace_dir() / f"{self.trace_id}.json"
        out.write_text(json.dumps(payload, indent=2))


def traced(
    *,
    name: str,
    inputs: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    project_name: str | None = None,
) -> TraceSession:
    """Factory helper for call sites."""
    return TraceSession(
        name=name,
        inputs=inputs,
        metadata=metadata,
        project_name=project_name,
    )
