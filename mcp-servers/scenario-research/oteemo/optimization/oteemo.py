"""Oteemo-specific policy optimization + replay on top of the lightweight firm sim.

Uses existing pulp_optimizer machinery where possible (grid -> candidates -> optimize_policy selection under constraints).
Falls back gracefully if pulp not installed (pure argmax).

Policy space (small for demo): discrete levers for raja (axiom_invest, finops_tier), rod (client_target, bid_aggr), arka (ignored for direct frac but efficiency noted).

Objective: maximize cum_billable_hours (or risk_adj = cum_billable - 0.3 * cum_invest - bench_penalty)
Constraints (from firm_init): min final maturity, max avg bench, etc.

Replay: re-run the chosen policy (and a couple neighbors) for robustness deltas.

All relative, deterministic, no abs paths.
"""

from __future__ import annotations

from typing import Any

from ..scenarios.oteemo_billable import (
    load_firm_init,
    simulate,
)

try:
    from scenario_research.optimization.pulp_optimizer import optimize_policy as base_optimize  # type: ignore
except Exception:
    base_optimize = None  # type: ignore


def make_policy_grid(init: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Small discrete grid over key levers (expandable)."""
    init = init or load_firm_init()
    grid: list[dict[str, Any]] = []
    for raja_axiom in (0.15, 0.18, 0.22, 0.26, 0.30):
        for finops in ("efficient", "balanced", "frontier"):
            for rod_client in (0.58, 0.62, 0.66, 0.70, 0.74):
                for bid_a in (0.65, 0.75, 0.85):
                    pol = {
                        "raja": {"axiom_invest_frac": raja_axiom, "finops_tier": finops},
                        "arka": {"arch_invest_frac": 0.08, "efficiency_mult": 1.04},
                        "rod": {"client_target_util": rod_client, "bid_aggressiveness": bid_a, "engagement_mix": "balanced"},
                    }
                    grid.append(pol)
    return grid


def evaluate_candidates(
    grid: list[dict[str, Any]],
    periods: int = 12,
    seed: int = 42,
    init: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run sim for each policy, attach metrics for optimizer."""
    init = init or load_firm_init()
    cands: list[dict[str, Any]] = []
    for i, pol in enumerate(grid):
        tr = simulate(pol, periods=periods, seed=seed, init=init)
        cand = {
            "id": f"p{i}",
            "policy": pol,
            "cum_billable_hours": tr["cum_billable_hours"],
            "avg_util": tr["avg_util"],
            "final_maturity": tr["final_maturity"],
            "avg_bench_frac": tr["avg_bench_frac"],
            "cum_invest_cost": tr["cum_invest_cost"],
            "constraints_satisfied": tr["constraints_satisfied"],
            # risk-adjusted objective (higher better)
            "objective": round(
                tr["cum_billable_hours"]
                - 0.35 * tr["cum_invest_cost"]
                - (max(0.0, tr["avg_bench_frac"] - 0.18) * 8000),
                1,
            ),
        }
        cands.append(cand)
    return cands


def optimize_oteemo_policy(
    periods: int = 12,
    seed: int = 42,
    init: dict[str, Any] | None = None,
    objective: str = "objective",
) -> dict[str, Any]:
    """Grid + select via base pulp (or fallback). Enforce constraints post-filter."""
    init = init or load_firm_init()
    grid = make_policy_grid(init)
    cands = evaluate_candidates(grid, periods=periods, seed=seed, init=init)

    # Pre-filter hard constraints for "admissible"
    admissible = [c for c in cands if c["constraints_satisfied"].get("min_axiom_maturity") and c["constraints_satisfied"].get("max_bench")]
    pool = admissible or cands  # if none satisfy, fall back (optimizer will surface)

    if base_optimize is not None:
        res = base_optimize(pool, objective=objective)
    else:
        # manual fallback
        best = max(pool, key=lambda c: c.get(objective, 0))
        res = {"chosen": best, "objective": best.get(objective, 0), "status": "fallback-argmax", "solver": "none"}

    chosen_cand = res.get("chosen") or (pool[0] if pool else None)
    return {
        "chosen": chosen_cand,
        "objective": res.get("objective"),
        "status": res.get("status"),
        "solver": res.get("solver", "grid+pulp-or-fallback"),
        "n_candidates": len(cands),
        "n_admissible": len(admissible),
        "periods": periods,
        "seed": seed,
    }


def replay_oteemo_policy(
    policy: dict[str, Any],
    periods: int = 12,
    seed: int = 42,
    init: dict[str, Any] | None = None,
    neighbors: int = 2,
) -> dict[str, Any]:
    """Replay chosen + small neighborhood for robustness (deltas on key metrics)."""
    init = init or load_firm_init()
    base_tr = simulate(policy, periods=periods, seed=seed, init=init)

    # Simple neighbors: tweak raja and rod a bit
    neigh_traces = []
    for da in (-0.03, 0.03):
        for dc in (-0.03, 0.03):
            p2 = {
                "raja": {**policy.get("raja", {}), "axiom_invest_frac": max(0.12, min(0.32, policy.get("raja", {}).get("axiom_invest_frac", 0.22) + da))},
                "arka": policy.get("arka", {}),
                "rod": {**policy.get("rod", {}), "client_target_util": max(0.55, min(0.78, policy.get("rod", {}).get("client_target_util", 0.66) + dc))},
            }
            tr = simulate(p2, periods=periods, seed=seed, init=init)
            neigh_traces.append({"delta_raja": round(da, 3), "delta_rod": round(dc, 3), "cum_billable": tr["cum_billable_hours"], "avg_util": tr["avg_util"]})

    return {
        "policy": policy,
        "base": {k: base_tr[k] for k in ("cum_billable_hours", "avg_util", "final_maturity", "avg_bench_frac", "constraints_satisfied")},
        "neighbors": neigh_traces,
        "robustness_delta": {
            "cum_billable_range": [
                min(n["cum_billable"] for n in neigh_traces),
                max(n["cum_billable"] for n in neigh_traces),
            ],
            "vs_base": round(base_tr["cum_billable_hours"] - sum(n["cum_billable"] for n in neigh_traces) / len(neigh_traces), 1),
        },
        "status": "replayed",
    }
