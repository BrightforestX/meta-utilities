"""SQLite durable store for batch runs and jobs."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from batch_orchestrator.models import JobStatus, Manifest, RunStatus


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunRecord:
    id: str
    manifest_path: str
    output_dir: str
    status: RunStatus
    created_at: str
    updated_at: str
    budget_spent_usd: float = 0.0
    error: str | None = None


@dataclass
class JobRecord:
    id: str
    run_id: str
    job_id: str
    status: JobStatus
    mode: str
    provider: str
    job_type: str
    attempts: int = 0
    provider_batch_id: str | None = None
    result_path: str | None = None
    error: str | None = None
    metadata_json: str = "{}"


class BatchStore:
    """Persistent SQLite store for runs and job state."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            base = Path(os.getenv("BATCH_ORCHESTRATOR_HOME", "~/.meta-utilities")).expanduser()
            base.mkdir(parents=True, exist_ok=True)
            db_path = base / "batch-orchestrator.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    manifest_path TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    budget_spent_usd REAL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    mode TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    provider_batch_id TEXT,
                    result_path TEXT,
                    error TEXT,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, job_id),
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_run ON jobs(run_id);
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                """
            )

    def create_run(
        self,
        manifest: Manifest,
        manifest_path: str,
        output_dir: str,
        run_id: str | None = None,
    ) -> RunRecord:
        run_id = run_id or str(uuid.uuid4())
        now = _utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO runs (id, manifest_path, manifest_json, output_dir, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    run_id,
                    manifest_path,
                    manifest.model_dump_json(),
                    output_dir,
                    now,
                    now,
                ),
            )
            for job in manifest.jobs:
                job_pk = f"{run_id}:{job.id}"
                conn.execute(
                    """
                    INSERT INTO jobs (
                        id, run_id, job_id, status, mode, provider, job_type,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                    """,
                    (
                        job_pk,
                        run_id,
                        job.id,
                        job.resolved_mode(manifest.defaults),
                        job.resolved_provider(manifest.defaults),
                        job.type,
                        now,
                        now,
                    ),
                )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> RunRecord:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise KeyError(f"run not found: {run_id}")
        return RunRecord(
            id=row["id"],
            manifest_path=row["manifest_path"],
            output_dir=row["output_dir"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            budget_spent_usd=row["budget_spent_usd"] or 0.0,
            error=row["error"],
        )

    def get_manifest(self, run_id: str) -> Manifest:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT manifest_json FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        if not row:
            raise KeyError(f"run not found: {run_id}")
        return Manifest.model_validate_json(row["manifest_json"])

    def update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        error: str | None = None,
        budget_spent_usd: float | None = None,
    ) -> None:
        now = _utcnow()
        with self._conn() as conn:
            if budget_spent_usd is not None:
                conn.execute(
                    """
                    UPDATE runs SET status = ?, error = ?, budget_spent_usd = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, error, budget_spent_usd, now, run_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE runs SET status = ?, error = ?, updated_at = ? WHERE id = ?
                    """,
                    (status, error, now, run_id),
                )

    def list_jobs(self, run_id: str) -> list[JobRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE run_id = ? ORDER BY job_id", (run_id,)
            ).fetchall()
        return [
            JobRecord(
                id=r["id"],
                run_id=r["run_id"],
                job_id=r["job_id"],
                status=r["status"],
                mode=r["mode"],
                provider=r["provider"],
                job_type=r["job_type"],
                attempts=r["attempts"] or 0,
                provider_batch_id=r["provider_batch_id"],
                result_path=r["result_path"],
                error=r["error"],
                metadata_json=r["metadata_json"] or "{}",
            )
            for r in rows
        ]

    def get_job(self, run_id: str, job_id: str) -> JobRecord:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE run_id = ? AND job_id = ?",
                (run_id, job_id),
            ).fetchone()
        if not row:
            raise KeyError(f"job not found: {run_id}/{job_id}")
        return JobRecord(
            id=row["id"],
            run_id=row["run_id"],
            job_id=row["job_id"],
            status=row["status"],
            mode=row["mode"],
            provider=row["provider"],
            job_type=row["job_type"],
            attempts=row["attempts"] or 0,
            provider_batch_id=row["provider_batch_id"],
            result_path=row["result_path"],
            error=row["error"],
            metadata_json=row["metadata_json"] or "{}",
        )

    def update_job(
        self,
        run_id: str,
        job_id: str,
        *,
        status: JobStatus | None = None,
        attempts: int | None = None,
        provider_batch_id: str | None = None,
        result_path: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = _utcnow()
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [now]

        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if attempts is not None:
            fields.append("attempts = ?")
            values.append(attempts)
        if provider_batch_id is not None:
            fields.append("provider_batch_id = ?")
            values.append(provider_batch_id)
        if result_path is not None:
            fields.append("result_path = ?")
            values.append(result_path)
        if error is not None:
            fields.append("error = ?")
            values.append(error)
        if metadata is not None:
            fields.append("metadata_json = ?")
            values.append(json.dumps(metadata))

        values.extend([run_id, job_id])
        sql = f"UPDATE jobs SET {', '.join(fields)} WHERE run_id = ? AND job_id = ?"
        with self._conn() as conn:
            conn.execute(sql, values)

    def list_runs(self, limit: int = 20) -> list[RunRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            RunRecord(
                id=r["id"],
                manifest_path=r["manifest_path"],
                output_dir=r["output_dir"],
                status=r["status"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                budget_spent_usd=r["budget_spent_usd"] or 0.0,
                error=r["error"],
            )
            for r in rows
        ]
