"""Replay policy against baseline and compute robustness deltas."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base)
    for k, v in updates.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_oteemo_module():
    oteemo_root = Path(__file__).resolve().parents[2] / "oteemo"
    mod_path = oteemo_root / "scenarios" / "oteemo_billable.py"
    if not mod_path.exists():
        raise RuntimeError(f"oteemo scenario module not found at {mod_path}")

    pkg_name = "oteemo_replay_local"
    pkg_scen = f"{pkg_name}.scenarios"
    mod_name = f"{pkg_scen}.oteemo_billable"

    if pkg_name not in sys.modules:
        pkg_spec = importlib.util.spec_from_loader(pkg_name, loader=None)
        pkg = importlib.util.module_from_spec(pkg_spec) if pkg_spec else type(sys)("name")
        pkg.__path__ = [str(oteemo_root)]  # type: ignore[attr-defined]
        sys.modules[pkg_name] = pkg
    if pkg_scen not in sys.modules:
        pkg_spec = importlib.util.spec_from_loader(pkg_scen, loader=None)
        pkg = importlib.util.module_from_spec(pkg_spec) if pkg_spec else type(sys)("name")
        pkg.__path__ = [str(oteemo_root / "scenarios")]  # type: ignore[attr-defined]
        sys.modules[pkg_scen] = pkg

    if mod_name in sys.modules:
        return sys.modules[mod_name]

    spec = importlib.util.spec_from_file_location(mod_name, str(mod_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to create module spec for oteemo replay module")
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = pkg_scen
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def replay_policy(
    policy: dict[str, Any],
    scenario: str = "oteemo_billable",
    *,
    seed: int = 42,
    periods: int = 12,
) -> dict[str, Any]:
    """Re-run baseline and treatment policy to estimate robustness deltas.

    Currently implemented for `oteemo_billable` (self-contained local sim).
    """
    if scenario != "oteemo_billable":
        return {
            "policy": policy,
            "scenario": scenario,
            "robustness_delta": {"profit": 0.0, "success_rate": 0.0},
            "uncertainty": {"profit": [0.0, 0.0]},
            "status": "unsupported_scenario",
            "error": "Replay currently implemented for oteemo_billable only.",
        }

    mod = _load_oteemo_module()
    default_baseline_policy = getattr(mod, "default_baseline_policy")
    load_firm_init = getattr(mod, "load_firm_init")
    simulate = getattr(mod, "simulate")

    init = load_firm_init()
    baseline_policy = default_baseline_policy()
    candidate_policy = _deep_merge(baseline_policy, policy)

    baseline = simulate(baseline_policy, periods=periods, seed=seed, init=init)
    treatment = simulate(candidate_policy, periods=periods, seed=seed, init=init)

    base_profit = float(baseline.get("cum_billable_hours", 0.0)) - float(baseline.get("cum_invest_cost", 0.0))
    trt_profit = float(treatment.get("cum_billable_hours", 0.0)) - float(treatment.get("cum_invest_cost", 0.0))
    delta_profit = trt_profit - base_profit

    base_success = 1.0 if all((baseline.get("constraints_satisfied") or {}).values()) else 0.0
    trt_success = 1.0 if all((treatment.get("constraints_satisfied") or {}).values()) else 0.0
    delta_success = trt_success - base_success

    # Deterministic uncertainty envelope from trajectory deltas (non-probabilistic, but data-grounded).
    util_base = baseline.get("util_trajectory", []) or []
    util_trt = treatment.get("util_trajectory", []) or []
    diffs = [float(t) - float(b) for b, t in zip(util_base, util_trt)] or [0.0]
    lo = min(diffs)
    hi = max(diffs)

    return {
        "policy": candidate_policy,
        "scenario": scenario,
        "seed": seed,
        "periods": periods,
        "baseline": {
            "cum_billable_hours": baseline.get("cum_billable_hours"),
            "cum_invest_cost": baseline.get("cum_invest_cost"),
            "constraints_satisfied": baseline.get("constraints_satisfied"),
        },
        "treatment": {
            "cum_billable_hours": treatment.get("cum_billable_hours"),
            "cum_invest_cost": treatment.get("cum_invest_cost"),
            "constraints_satisfied": treatment.get("constraints_satisfied"),
        },
        "robustness_delta": {"profit": round(delta_profit, 4), "success_rate": round(delta_success, 4)},
        "uncertainty": {"util_delta_range": [round(lo, 6), round(hi, 6)]},
        "status": "solved",
    }
