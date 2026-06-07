"""P6: PuLP optimizer module (baseline; OR-Tools optional extra).

IO contract:
- input: list of candidate dicts (e.g. from simulation top results) with metrics like profit, success_rate, cost
- output: dict with chosen "policy" params + objective value + status

Non-blocking: this phase is subordinate; core ODRS (P0/P1) must be green without it.
"""
from __future__ import annotations

from typing import Any

try:
    import pulp  # type: ignore
except Exception:  # optional
    pulp = None  # type: ignore


def optimize_policy(candidates: list[dict[str, Any]], objective: str = "profit") -> dict[str, Any]:
    """Return a trivial or PuLP-solved selection.

    For P0 when PuLP not present or no candidates, returns a passthrough choice.
    """
    if not candidates:
        return {"chosen": None, "objective": 0.0, "status": "no-candidates"}
    if pulp is None:
        # Fallback: pick max by objective key
        best = max(candidates, key=lambda c: c.get(objective, 0))
        return {"chosen": best, "objective": best.get(objective, 0), "status": "fallback-argmax", "solver": "none"}
    # Real (small) LP: select one candidate to max objective s.t. cost <= budget example
    prob = pulp.LpProblem("odrs_policy", pulp.LpMaximize)
    vars_ = [pulp.LpVariable(f"c{i}", cat="Binary") for i in range(len(candidates))]
    # objective
    prob += pulp.lpSum(v * c.get(objective, 0) for v, c in zip(vars_, candidates))
    # one choice
    prob += pulp.lpSum(vars_) == 1
    # budget example constraint (soft in P0)
    budget = max((c.get("cost", 0) for c in candidates), default=1) or 1
    prob += pulp.lpSum(v * c.get("cost", 0) for v, c in zip(vars_, candidates)) <= budget
    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    chosen_idx = next((i for i, v in enumerate(vars_) if pulp.value(v) > 0.5), 0)
    chosen = candidates[chosen_idx]
    return {
        "chosen": chosen,
        "objective": pulp.value(prob.objective),
        "status": pulp.LpStatus[status],
        "solver": "pulp-cbc",
    }
