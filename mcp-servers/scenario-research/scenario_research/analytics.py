"""Lightweight analytics helpers for fitted summaries and cost telemetry."""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from .models import CostReport, ModelFitResult, ScenarioRun
from .router import get_model_for_role


def load_trace_payload(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists() or p.suffix.lower() != ".json":
        return {}
    try:
        doc = json.loads(p.read_text())
    except Exception:
        return {}
    if isinstance(doc, dict):
        return doc.get("trace", doc) or {}
    return {}


def _trajectory(trace: dict[str, Any], key: str) -> list[float]:
    vals = trace.get(key, []) or []
    out: list[float] = []
    for v in vals:
        try:
            out.append(float(v))
        except Exception:
            continue
    return out


def _fit_sir(trace: dict[str, Any]) -> ModelFitResult:
    util = _trajectory(trace, "util_trajectory")
    growth = [max(util[i + 1] - util[i], 0.0) for i in range(len(util) - 1)]
    decay = [max(util[i] - util[i + 1], 0.0) for i in range(len(util) - 1)]
    beta = mean(growth) if growth else 0.0
    gamma = mean(decay) if decay else 0.0
    r0 = (beta + 1e-9) / (gamma + 1e-9)
    return ModelFitResult(
        model="sir",
        parameters={"beta": round(beta, 6), "gamma": round(gamma, 6)},
        metrics={"r0": round(r0, 6)},
        fit_summary="Heuristic SIR-style fit over utilization trajectory.",
    )


def _fit_hawkes(trace: dict[str, Any]) -> ModelFitResult:
    util = _trajectory(trace, "util_trajectory")
    jumps = [abs(util[i + 1] - util[i]) for i in range(len(util) - 1)]
    avg_jump = mean(jumps) if jumps else 0.0
    branching_factor = min(0.99, avg_jump * 6.0)
    return ModelFitResult(
        model="hawkes",
        parameters={"avg_jump": round(avg_jump, 6)},
        metrics={
            "branching_factor": round(branching_factor, 6),
            "intensity": round(mean(util), 6) if util else 0.0,
        },
        fit_summary="Heuristic self-excitation estimate over period deltas.",
    )


def _fit_bounded_confidence(trace: dict[str, Any]) -> ModelFitResult:
    util = _trajectory(trace, "util_trajectory")
    polarization = pstdev(util) if len(util) > 1 else 0.0
    consensus = max(0.0, 1.0 - min(1.0, polarization * 4.0))
    return ModelFitResult(
        model="bounded_confidence",
        parameters={"epsilon_proxy": 0.25},
        metrics={"polarization": round(polarization, 6), "consensus": round(consensus, 6)},
        fit_summary="Bounded-confidence proxy from trajectory variance.",
    )


def _fit_bayesian_ab(trace: dict[str, Any]) -> ModelFitResult:
    util = _trajectory(trace, "util_trajectory")
    if len(util) < 2:
        uplift = 0.0
    else:
        mid = max(1, len(util) // 2)
        uplift = mean(util[mid:]) - mean(util[:mid])
    posterior_prob = 1.0 / (1.0 + math.exp(-20.0 * uplift))
    return ModelFitResult(
        model="bayesian_ab",
        parameters={"split": "first_half_vs_second_half"},
        metrics={"uplift": round(uplift, 6), "p_uplift_gt_0": round(posterior_prob, 6)},
        fit_summary="Bayesian-style uplift proxy from pre/post trajectory split.",
    )


def fit_models_from_trace(trace: dict[str, Any], models: list[str] | None = None) -> list[ModelFitResult]:
    requested = [m.lower() for m in (models or ["sir", "hawkes", "bounded_confidence", "bayesian_ab"])]
    out: list[ModelFitResult] = []
    for name in requested:
        if name == "sir":
            out.append(_fit_sir(trace))
        elif name == "hawkes":
            out.append(_fit_hawkes(trace))
        elif name in {"bounded_confidence", "bounded-confidence"}:
            out.append(_fit_bounded_confidence(trace))
        elif name in {"bayesian_ab", "bayesian-ab", "ab"}:
            out.append(_fit_bayesian_ab(trace))
    return out


def estimate_cost_report(run: ScenarioRun) -> CostReport:
    trace = load_trace_payload(run.db_path)
    pdr_count = len(trace.get("pdr_attributions", []) or [])
    util_points = len(trace.get("util_trajectory", []) or [])
    # Deterministic heuristic estimate to keep local telemetry stable in tests/dev.
    local_tokens = 1200 + pdr_count * 180 + util_points * 80
    api_tokens = 120 if "observability" in (run.config_snapshot or {}) else 0
    estimated_cost_usd = round((api_tokens / 1_000_000) * 3.0, 6)
    return CostReport(
        run_id=run.run_id,
        local_tokens=local_tokens,
        api_tokens=api_tokens,
        estimated_cost_usd=estimated_cost_usd,
        local_model=get_model_for_role("oasis_agent"),
        api_model=get_model_for_role("planner"),
        notes="Heuristic cost estimate from trace size and observability metadata.",
    )
