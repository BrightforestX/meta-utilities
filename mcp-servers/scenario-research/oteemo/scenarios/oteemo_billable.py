"""Oteemo billable hours / utilization maximization scenario (self-contained, no camel-oasis dep).

Lightweight discrete-time firm model faithful to the Oteemo ontology:
- LeadershipRole as distinct governed decision agents (Raja/FinOps+strategy, Arka/arch+eff, Rod/fed delivery)
- DeliveryContext (internal_platform=Axiom R&D vs client_delivery=billable)
- EngagementType (fte/contractor/sub), with Clifford fixed as contractor on internal Axiom/FinOps
- FederalProgram + ContractVehicle for pipeline
- AIFinOps / PromptIntelligence / ModelTier / PolicyDecisionRecord-style cost attribution for decisions
- AxiomPlatform as sponsored internal initiative (Raja)

Dynamics:
- Time-stepped (periods): capacity allocation, opportunity pipeline, win events, accumulation of billable hours.
- Compartmental: total -> client(C), axiom(X), bench(B). util = C/total
- Maturity builds from X + Clifford contrib + FinOps policy quality; boosts future win_p and productivity.
- Heads influence via policy levers; reconciled each period (weighted by accountability).
- "FinOps" telemetry: per-decision attribution records (invest cost, bench opportunity, util delta) -> repurposed CostReport.
- Deterministic via seed (random.Random).

Math: simple production (effective_hours = C * (1 + 0.2*maturity) * finops_mult), win_p = base * f(maturity, util, policy).
No external libs beyond stdlib + pyyaml (for init load).

Optimization lives in optimization/oteemo.py (grid + pulp selection + replay).

Adapter/CLI surface supports "oteemo_billable" for `scenario-research run` (local path).
Demo: python -m scenario_research.demos.oteemo_billable_max --periods 12 --seed 42 --optimize

Portability: all paths relative to package or via env (OTEEMO_FIRM_INIT, SCENARIO_RESEARCH_DATA).
Never hard-codes absolute paths from oteemo/ or personal dirs at runtime.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from scenario_research.models import ScenarioRun

# Portable data location (package relative). Override with env for dev/regen.
# For initial creation we used absolute ontology paths (per task); runtime never does.
_DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data"
DATA_ROOT = Path(os.environ.get("SCENARIO_RESEARCH_DATA", str(_DEFAULT_DATA)))
OTEEMO_INIT = Path(os.environ.get("OTEEMO_FIRM_INIT", str(_DEFAULT_DATA / "oteemo_firm_init.yaml")))


def load_firm_init(path: Path | None = None) -> dict[str, Any]:
    p = path or OTEEMO_INIT
    if not p.exists():
        # Fallback to package if env pointed elsewhere
        p = _DEFAULT_DATA / "oteemo_firm_init.yaml"
    text = p.read_text()
    return yaml.safe_load(text) or {}


@dataclass
class FirmState:
    period: int = 0
    total_capacity: float = 25.0
    client: float = 15.0
    axiom: float = 6.25
    bench: float = 3.75
    axiom_maturity: float = 0.15
    cum_billable_hours: float = 0.0
    cum_invest_cost: float = 0.0  # opportunity + direct proxy
    util_history: list[float] = field(default_factory=list)
    maturity_history: list[float] = field(default_factory=list)
    bench_history: list[float] = field(default_factory=list)
    pdr_attributions: list[dict[str, Any]] = field(default_factory=list)  # FinOps / PDR analog
    active_contracts: list[dict[str, Any]] = field(default_factory=list)  # {end_period, billable_per_period}
    pipeline: list[dict[str, Any]] = field(default_factory=list)


def reconcile_allocation(policy: dict[str, Any], total: float, state: FirmState, init: dict[str, Any]) -> tuple[float, float, float]:
    """Reconcile distinct head levers into period allocation (C, X, B).

    Weights reflect primary_accountabilities (Rod delivery heavy for current util, Raja strategic Axiom, Arka efficiency).
    """
    p_raja = policy.get("raja", {})
    p_rod = policy.get("rod", {})

    rod_client = float(p_rod.get("client_target_util", 0.65))
    raja_axiom = float(p_raja.get("axiom_invest_frac", 0.20))
    # Arka influences via efficiency, not direct frac here (can shift effective later)

    # Compromise: 55% Rod pull, 35% Raja strategic, 10% floor for bench/ops
    client_target = 0.55 * rod_client + 0.35 * (1.0 - raja_axiom - 0.05) + 0.10 * 0.60
    client_target = max(0.40, min(0.80, client_target))

    axiom_target = max(0.10, min(0.35, raja_axiom))
    bench = max(0.0, total - client_target * total - axiom_target * total)

    # Apply min delivery signal constraint from init
    min_sig = init.get("constraints", {}).get("min_delivery_capacity_signal", 0.55)
    if client_target < min_sig:
        delta = (min_sig - client_target) * total
        client_target = min_sig
        # pull from axiom/bench proportionally
        if axiom_target * total > delta * 0.5:
            axiom_target -= delta * 0.5 / total
        else:
            bench = max(0.0, bench - (delta - axiom_target * total * 0.5))

    c = client_target * total
    x = axiom_target * total
    b = max(0.0, total - c - x)
    return c, x, b


def apply_finops_policy(policy: dict[str, Any], maturity: float) -> tuple[float, float]:
    """Return (productivity_mult, waste_reduction) from FinOps tier choice.

    Faithful to PromptIntelligenceRule / ModelTier / CostAttribution.
    """
    tier = policy.get("raja", {}).get("finops_tier", "balanced")
    if tier == "frontier":
        prod = 1.08 + 0.03 * maturity  # high cap, higher "cost" modeled in invest
        waste = 0.03
    elif tier == "efficient":
        prod = 1.02 + 0.01 * maturity
        waste = 0.01
    else:  # balanced
        prod = 1.05 + 0.02 * maturity
        waste = 0.02
    return prod, waste


def step(state: FirmState, policy: dict[str, Any], rng: random.Random, init: dict[str, Any]) -> None:
    """Advance one period. Mutates state."""
    state.period += 1
    total = state.total_capacity

    c, x, b = reconcile_allocation(policy, total, state, init)
    state.client = c
    state.axiom = x
    state.bench = b

    util = c / total if total > 0 else 0.0
    state.util_history.append(util)
    state.bench_history.append(b / total if total > 0 else 0.0)

    # FinOps / policy effects
    finops_prod, waste = apply_finops_policy(policy, state.axiom_maturity)
    clifford = init.get("axiom", {}).get("clifford_boost", 0.015)
    maturity_delta = (x / total) * init.get("axiom", {}).get("maturity_per_invest", 0.04) + clifford
    state.axiom_maturity = min(0.95, state.axiom_maturity + maturity_delta)
    state.maturity_history.append(state.axiom_maturity)

    # Effective billable this period (compartmental productivity)
    effective = c * (1.0 + 0.25 * state.axiom_maturity) * finops_prod * (1.0 - waste)
    state.cum_billable_hours += effective

    # Invest "cost" proxy (opportunity of X + B + policy choice)
    invest_cost_period = (x + b) * 0.8 + (0.1 if policy.get("raja", {}).get("finops_tier") == "frontier" else 0.0)
    state.cum_invest_cost += invest_cost_period

    # PDR-style attribution for this period's decision
    pdr = {
        "period": state.period,
        "policy": {
            "raja_axiom": policy.get("raja", {}).get("axiom_invest_frac"),
            "raja_finops": policy.get("raja", {}).get("finops_tier"),
            "rod_client": policy.get("rod", {}).get("client_target_util"),
        },
        "delta_util": round(util - (state.util_history[-2] if len(state.util_history) > 1 else 0.6), 4),
        "invest_cost": round(invest_cost_period, 2),
        "maturity": round(state.axiom_maturity, 4),
        "attribution_level": "policy",  # per ontology
    }
    state.pdr_attributions.append(pdr)

    # Pipeline + win events (simple arrival + duration contracts)
    # Seed arrivals from federal_programs in init
    programs = init.get("federal_programs", [])
    if state.period <= 3 or rng.random() < 0.35:
        prog = rng.choice(programs) if programs else {"base_win_prob": 0.3, "base_billable_potential_hours": 2000, "duration_periods": 4}
        win_p = prog.get("base_win_prob", 0.3) * (1.0 + 0.6 * state.axiom_maturity)
        bid_mult = policy.get("rod", {}).get("bid_aggressiveness", 0.8)
        win_p = min(0.92, win_p * (0.7 + 0.3 * bid_mult))
        if rng.random() < win_p:
            dur = prog.get("duration_periods", 4)
            per = prog.get("base_billable_potential_hours", 2000) / dur
            state.active_contracts.append({"end": state.period + dur, "per": per})

    # Age active contracts, accumulate billable already handled in effective above; here just prune
    state.active_contracts = [ac for ac in state.active_contracts if ac["end"] > state.period]

    # Simple "win" also adds direct to cum (already in effective); pipeline is for capacity signal only in this model.


def simulate(policy: dict[str, Any], periods: int = 12, seed: int = 42, init: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the full horizon. Return rich trace for optimizer / report."""
    init = init or load_firm_init()
    rng = random.Random(seed)
    st = FirmState(
        total_capacity=init.get("capacity", {}).get("total_fte_equiv", 25.0),
        client=init.get("capacity", {}).get("initial_client_delivery_frac", 0.6) * init.get("capacity", {}).get("total_fte_equiv", 25.0),
        axiom=init.get("capacity", {}).get("initial_axiom_internal_frac", 0.25) * init.get("capacity", {}).get("total_fte_equiv", 25.0),
        bench=init.get("capacity", {}).get("initial_bench_frac", 0.15) * init.get("capacity", {}).get("total_fte_equiv", 25.0),
        axiom_maturity=init.get("axiom", {}).get("initial_maturity", 0.15),
    )
    st.util_history = []
    st.maturity_history = []
    st.bench_history = []
    st.pdr_attributions = []
    st.active_contracts = []
    st.pipeline = []

    for _ in range(periods):
        step(st, policy, rng, init)

    avg_util = sum(st.util_history) / len(st.util_history) if st.util_history else 0.0
    final_mat = st.axiom_maturity
    constraints = init.get("constraints", {})
    ok_mat = final_mat >= constraints.get("min_axiom_maturity_end", 0.35)
    ok_bench = (sum(st.bench_history) / len(st.bench_history)) <= constraints.get("max_avg_bench_frac", 0.18)

    return {
        "policy": policy,
        "periods": periods,
        "seed": seed,
        "cum_billable_hours": round(st.cum_billable_hours, 1),
        "avg_util": round(avg_util, 4),
        "final_maturity": round(final_mat, 4),
        "avg_bench_frac": round(sum(st.bench_history) / len(st.bench_history) if st.bench_history else 0.0, 4),
        "cum_invest_cost": round(st.cum_invest_cost, 1),
        "util_trajectory": [round(u, 4) for u in st.util_history],
        "maturity_trajectory": [round(m, 4) for m in st.maturity_history],
        "bench_trajectory": [round(b, 4) for b in st.bench_history],
        "pdr_attributions": st.pdr_attributions,
        "constraints_satisfied": {"min_axiom_maturity": ok_mat, "max_bench": ok_bench},
        "init_version": init.get("version"),
    }


def default_baseline_policy() -> dict[str, Any]:
    return {
        "raja": {"axiom_invest_frac": 0.22, "finops_tier": "balanced", "bid_threshold": 0.5},
        "arka": {"arch_invest_frac": 0.08, "efficiency_mult": 1.04},
        "rod": {"client_target_util": 0.68, "bid_aggressiveness": 0.75, "engagement_mix": "balanced"},
    }


async def run(
    profile_path: Path | None = None,
    db_path: Path | None = None,
    n_steps: int = 12,
    seed: int | None = 42,
    policy: dict[str, Any] | None = None,
) -> ScenarioRun:
    """Adapter-compatible entry for oteemo_billable.

    Runs a baseline (or supplied policy) horizon. Populates ScenarioRun + writes a small json trace if db_path given.
    Does not require camel-oasis-scaffold.
    """
    seed = seed or 42
    pol = policy or default_baseline_policy()
    init = load_firm_init()
    trace = simulate(pol, periods=n_steps, seed=seed, init=init)

    rid = f"oteemo_billable-{seed}"
    run = ScenarioRun(
        run_id=rid,
        scenario="oteemo_billable",
        n_agents=int(init.get("capacity", {}).get("total_fte_equiv", 25)),
        n_steps=n_steps,
        seed=seed,
        db_path=str(db_path) if db_path else None,
        status="succeeded",
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
        config_snapshot={
            "policy": pol,
            "trace_summary": {k: trace[k] for k in ("cum_billable_hours", "avg_util", "final_maturity", "constraints_satisfied")},
            "wired_from": "oteemo_billable_local",
            "init_version": init.get("version"),
        },
        error=None,
    )

    if db_path:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_text(json.dumps({"trace": trace, "run": run.model_dump()}, indent=2))

    return run


if __name__ == "__main__":
    import asyncio
    tr = asyncio.run(run(n_steps=8, seed=42))
    print(tr.model_dump())
