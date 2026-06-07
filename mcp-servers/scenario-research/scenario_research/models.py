"""Core DTO contracts for ODRS (frozen at P0 per ACs).

These are the source-of-truth shapes for:
- ScenarioRun: a single scenario execution (maps to OASIS .db + metadata)
- ModelFitResult: output from one math model fit (SIR, Hawkes, etc.)
- CostReport: local vs frontier token/cost split for a run or ask
- ResearchReport: the final artifact bundle from a cli ask or orchestrated run

Contract tests pin these shapes + a CONTRACT_VERSION. Any drift is a breaking change
requiring plan update + AC re-review.

CONTRACT_VERSION: p0.1  (bump on additive-compatible changes only after review)
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CONTRACT_VERSION: str = "p0.1"


class ScenarioRun(BaseModel):
    """Represents one OASIS scenario execution (info_spread, opinion_dynamics, marketing_ab, ...)."""

    run_id: str = Field(..., description="Unique identifier for this run (uuid or timestamped)")
    scenario: str = Field(..., description="Scenario family name")
    n_agents: int = Field(..., ge=1)
    n_steps: int = Field(..., ge=1)
    seed: int | None = Field(None, description="Deterministic seed for reproducibility")
    db_path: str | None = Field(None, description="Path to the produced SQLite .db (if materialized)")
    status: Literal["pending", "running", "succeeded", "failed"] = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    config_snapshot: dict[str, Any] | None = Field(
        None, description="Canonicalized input config (agent yaml refs, model map, etc.) for reproducibility"
    )
    error: str | None = None


class ModelFitResult(BaseModel):
    """Typed result from fitting one mathematical model to OASIS trace data."""

    model: str = Field(..., description="e.g. sir, hawkes, bounded_confidence, bayesian_ab")
    parameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict, description="e.g. r0, branching_factor, polarization, uplift")
    uncertainty: dict[str, Any] | None = Field(None, description="95% CI / HDI or posterior summary")
    fit_summary: str | None = None
    artifacts: list[str] = Field(default_factory=list, description="Paths to generated figures/tables for this fit")


class CostReport(BaseModel):
    """Token and cost accounting split between local (bulk OASIS) and frontier (planner/writer)."""

    run_id: str
    local_tokens: int = 0
    api_tokens: int = 0
    estimated_cost_usd: float = 0.0
    local_model: str | None = None
    api_model: str | None = None
    notes: str | None = None


class ResearchReport(BaseModel):
    """Final deliverable from an end-to-end ask or orchestrated scenario batch."""

    report_id: str
    question: str
    report_path: str | None = None  # markdown
    figures: list[str] = Field(default_factory=list)
    fits: list[ModelFitResult] = Field(default_factory=list)
    cost_report: CostReport | None = None
    scenario_runs: list[ScenarioRun] = Field(default_factory=list)
    created_at: str | None = None
    seed: int | None = None
