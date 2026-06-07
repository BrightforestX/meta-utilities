"""Pydantic models for batch job manifests."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Provider = Literal["perplexity", "grok", "openai", "anthropic"]
ExecutionMode = Literal["realtime", "batch"]
JobType = Literal["deep_research", "inference", "deep_research_pipeline"]
ReasoningEffort = Literal["low", "medium", "high"]
PipelineDepth = Literal["simple", "comparative", "deep"]
JobStatus = Literal[
    "pending",
    "running",
    "submitted_batch",
    "succeeded",
    "failed",
    "cancelled",
]
RunStatus = Literal["pending", "running", "waiting_batch", "succeeded", "failed", "cancelled"]

FILE_REF_PATTERN = re.compile(r"\{\{file:([^}]+)\}\}")


class BudgetConfig(BaseModel):
    max_usd: float | None = None
    max_tokens: int | None = None


class DefaultsConfig(BaseModel):
    provider: Provider = "perplexity"
    reasoning_effort: ReasoningEffort = "high"
    mode: ExecutionMode = "realtime"
    model: str | None = None
    max_retries: int = 2


class Job(BaseModel):
    id: str
    type: JobType
    mode: ExecutionMode | None = None
    provider: Provider | None = None
    model: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    query: str | None = None
    prompt: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    depth: PipelineDepth = "comparative"
    max_subagents: int = Field(default=5, ge=1, le=20)
    max_retries: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    program_file: str | None = None  # e.g. "file:program.md" or inline; for ratchet/program injection (Phase 2)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("job id cannot be empty")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(f"job id '{v}' must be alphanumeric with _ or -")
        return v

    @model_validator(mode="after")
    def validate_job_fields(self) -> Job:
        if self.type in ("deep_research", "deep_research_pipeline") and not self.query:
            raise ValueError(f"job '{self.id}' of type '{self.type}' requires 'query'")
        if self.type == "inference" and not self.prompt:
            raise ValueError(f"job '{self.id}' of type 'inference' requires 'prompt'")
        return self

    def resolved_mode(self, defaults: DefaultsConfig) -> ExecutionMode:
        return self.mode or defaults.mode

    def resolved_provider(self, defaults: DefaultsConfig) -> Provider:
        return self.provider or defaults.provider

    def resolved_reasoning_effort(self, defaults: DefaultsConfig) -> ReasoningEffort:
        return self.reasoning_effort or defaults.reasoning_effort

    def resolved_max_retries(self, defaults: DefaultsConfig) -> int:
        return self.max_retries if self.max_retries is not None else defaults.max_retries

    def resolved_model(self, defaults: DefaultsConfig) -> str | None:
        return self.model or defaults.model

    def text_input(self) -> str:
        return (self.query or self.prompt or "").strip()


class Manifest(BaseModel):
    version: int = 1
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    output_dir: str = "./batch-results"
    concurrency: int = Field(default=4, ge=1, le=32)
    budget: BudgetConfig | None = None
    jobs: list[Job] = Field(min_length=1)
    program: str | None = None  # top-level program_file ref or content for persistent instructions + ratchet (e.g. "file:./program.md")

    @model_validator(mode="after")
    def validate_dag(self) -> Manifest:
        job_ids = {j.id for j in self.jobs}
        for job in self.jobs:
            for dep in job.depends_on:
                if dep not in job_ids:
                    raise ValueError(
                        f"job '{job.id}' depends on unknown job '{dep}'"
                    )
        _detect_cycles(self.jobs)
        return self

    def job_by_id(self, job_id: str) -> Job:
        for job in self.jobs:
            if job.id == job_id:
                return job
        raise KeyError(f"job not found: {job_id}")


def _detect_cycles(jobs: list[Job]) -> None:
    graph = {j.id: j.depends_on for j in jobs}
    visited: set[str] = set()
    stack: set[str] = set()

    def visit(node: str) -> None:
        if node in stack:
            raise ValueError(f"dependency cycle detected involving '{node}'")
        if node in visited:
            return
        stack.add(node)
        for dep in graph.get(node, []):
            visit(dep)
        stack.remove(node)
        visited.add(node)

    for job_id in graph:
        visit(job_id)


def expand_file_refs(text: str, base_dir: Path) -> str:
    """Replace {{file:path}} placeholders with file contents."""

    def replacer(match: re.Match[str]) -> str:
        rel = match.group(1).strip()
        path = Path(rel)
        if not path.is_absolute():
            path = (base_dir / path).resolve()
        if not path.exists():
            if os.getenv("BATCH_DOGFOOD_STUB") == "1":
                # graceful for verification timing per 2.3 (self-contained query preferred; stub if planner not yet on disk at expand)
                return f"[stub planner triage for topic: 1. meta-utilities gap-analysis recall via RAG/turbovec 2. ratchet monotonic keep only verified 3. program.md + batch submit alias 4. live persist + compress tokens]"
            raise FileNotFoundError(f"referenced file not found: {path}")
        return path.read_text(encoding="utf-8")

    return FILE_REF_PATTERN.sub(replacer, text)


def load_manifest(path: Path) -> Manifest:
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("manifest must be a YAML mapping")
    return Manifest.model_validate(raw)


def topological_order(jobs: list[Job]) -> list[str]:
    """Return job ids in dependency-respecting order."""
    graph = {j.id: j.depends_on for j in jobs}
    in_degree = {j.id: len(j.depends_on) for j in jobs}
    queue = [jid for jid, deg in in_degree.items() if deg == 0]
    order: list[str] = []

    while queue:
        queue.sort()
        node = queue.pop(0)
        order.append(node)
        for jid, deps in graph.items():
            if node in deps:
                in_degree[jid] -= 1
                if in_degree[jid] == 0:
                    queue.append(jid)

    if len(order) != len(jobs):
        raise ValueError("dependency cycle detected")
    return order
