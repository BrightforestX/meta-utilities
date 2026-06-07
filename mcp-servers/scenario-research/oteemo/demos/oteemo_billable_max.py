"""Runnable demo for Oteemo billable maximization scenario (end-to-end on ODRS platform).

Usage (portable, from anywhere with the package importable or in tree):
  # Preferred (adapter resolves the oteemo sibling):
  scenario-research run oteemo_billable --steps 12 --seed 42 --optimize
  # Direct (when oteemo/ on PYTHONPATH as sibling):
  python -m oteemo.demos.oteemo_billable_max --periods 12 --seed 42 --optimize
  # Legacy direct may still be referenced in older docs.

Produces:
- ScenarioRun (via local adapter path)
- optimized policy + replay robustness
- human-readable markdown report + CostReport-analog (FinOps decision attribution)
- artifacts under examples/oteemo/reports/ (relative to package or cwd fallback)

Follows meta-utilities conventions: relative paths, env fallbacks (SCENARIO_RESEARCH_DATA, OTEEMO_FIRM_INIT), no hard-coded external oteemo absolutes at runtime.
Governed agents compiled from ontology/agents/*.yaml (Raja, Arka, Rod, Clifford).
Pre-run validation exercised.
Small-horizon, deterministic, replicate-friendly (pass different seeds).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pathlib import Path
from scenario_research.agent_compiler import compile_agent_for_role, load_roles, OTEEMO_ONTOLOGY
from scenario_research.models import CostReport, ResearchReport, ScenarioRun
from ..optimization.oteemo import (
    load_firm_init,
    optimize_oteemo_policy,
    replay_oteemo_policy,
)
from ..scenarios.oteemo_billable import simulate, default_baseline_policy
from scenario_research.validation import validate_before_run


def _reports_dir() -> Path:
    # Prefer oteemo/reports (or examples/oteemo/reports relative to oteemo tree; portable), fall back to cwd
    here = Path(__file__).resolve().parents[1]  # oteemo/
    for cand in (here / "reports", here / "examples" / "oteemo" / "reports"):
        if cand.exists() or cand.parent.exists():
            cand.mkdir(parents=True, exist_ok=True)
            return cand
    out = Path.cwd() / "oteemo_billable_reports"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _make_recs(optimized: dict[str, Any], replay: dict[str, Any], init: dict[str, Any]) -> list[str]:
    pol = optimized.get("chosen", {}).get("policy", default_baseline_policy())
    raja = pol.get("raja", {})
    rod = pol.get("rod", {})
    base = replay.get("base", {})
    delta = replay.get("robustness_delta", {})

    recs = [
        f"Raja (CEO / AI FinOps owner): Target axiom_invest_frac={raja.get('axiom_invest_frac', 0.22)} across the horizon to meet the >= {init.get('constraints',{}).get('min_axiom_maturity_end',0.35)} maturity floor. Use finops_tier='{raja.get('finops_tier','balanced')}' for balanced productivity vs attribution cost. This yields option value on future federal wins while controlling FinOps drag.",
        f"Arka (VP Tech): Architecture and knowledge investments (efficiency_mult ~{pol.get('arka',{}).get('efficiency_mult',1.04)}) compound with Raja's Axiom allocation. Focus GraphRAG / A2A leverage in periods 4-8 to amplify Rod's delivery wins without direct billable allocation.",
        f"Roderick (Head of Federal Delivery): Set client_target_util={rod.get('client_target_util',0.66)} and bid_aggressiveness={rod.get('bid_aggressiveness',0.75)} in periods 1-6 and 9-12. This keeps avg_util ~{base.get('avg_util',0.6)} while respecting bench <= {init.get('constraints',{}).get('max_avg_bench_frac',0.18)}. Shift 3-5% capacity to Axiom support in mid-horizon when maturity delta is highest leverage.",
        f"Clifford (Contractor, Axiom/FinOps): Fixed internal_platform allocation provides reliable +{init.get('axiom',{}).get('clifford_boost',0.015)} maturity per period + FinOps telemetry (PDR attribution). Use visibility from Fed Town Hall / contributions to reinforce Raja's cost_attribution policy adoption.",
        f"Overall: Optimized policy improves cum_billable by ~{delta.get('vs_base',0)} vs neighborhood avg under the risk-adjusted objective. Replay range shows robustness within {delta.get('cum_billable_range', [0,0])}. Re-run with --replicates via batch-orchestrator manifest for seed sweeps.",
    ]
    return recs


def generate_report(
    baseline_tr: dict[str, Any],
    opt_res: dict[str, Any],
    replay: dict[str, Any],
    scenario_run: ScenarioRun,
    cost_analog: CostReport,
    init: dict[str, Any],
    periods: int,
    seed: int,
) -> str:
    """Return markdown + side effects (write files to reports dir)."""
    reports = _reports_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base_name = f"oteemo_billable_{seed}_{periods}p_{ts}"
    md_path = reports / f"{base_name}.md"
    json_path = reports / f"{base_name}.json"

    chosen = opt_res.get("chosen") or {}
    pol = chosen.get("policy", {})
    base = replay.get("base", {})
    recs = _make_recs(opt_res, replay, init)

    # Simple text "spark" for trajectory
    def spark(vals: list[float]) -> str:
        if not vals:
            return ""
        mn, mx = min(vals), max(vals)
        if mx == mn:
            return "·" * len(vals)
        bars = "▁▂▃▄▅▆▇█"
        return "".join(bars[int((v - mn) / (mx - mn) * (len(bars) - 1))] for v in vals)

    md = f"""# Oteemo Billable Maximization Scenario — ODRS Report

**Generated**: {datetime.now(timezone.utc).isoformat()}  
**Scenario**: oteemo_billable (self-contained discrete firm model)  
**Horizon**: {periods} periods | Seed: {seed}  
**Governed agents** (compiled from ontology/agents/roles.yaml):  
- raja_gudepu_ceo (FinOps + strategy owner)  
- arkaprava_chaudhuri_vp_tech (platform / efficiency)  
- roderick_kelly_fed_delivery (client billable owner)  
- clifford_dalson_axiom_finops (contractor, fixed internal_platform contributor)  

**Source ontology**: oteemo.linkml + instances (LeadershipRole, DeliveryContext internal_platform vs client_delivery, EngagementType, FederalProgram, AIFinOps/PDR, ContractorContribution). Snapshot in package data/oteemo/oteemo_firm_init.yaml (portable; refresh via OTEEMO_ONTOLOGY_SRC env + helper if needed).

## Simulation Setup (faithful to ontology)
- Capacity: {init.get('capacity',{}).get('total_fte_equiv')} fte-equiv (fte/contractor/sub mix; Clifford fixed contractor on Axiom).
- Axiom (internal_platform, sponsor Raja): initial_maturity={init.get('axiom',{}).get('initial_maturity')}, builds via invest + Clifford FinOps boost.
- Pipeline: PEO IWS-class + Platform One stubs (generic types, Seaport-NXG / GSA per ontology).
- Levers per head derived from primary_accountabilities.
- FinOps / attribution: every period emits PDR-style record (policy_id, delta_util, attributed_cost, maturity). Repurposed into CostReport analog.
- Constraints (from init): min_axiom_maturity_end={init.get('constraints',{}).get('min_axiom_maturity_end')}, max_avg_bench={init.get('constraints',{}).get('max_avg_bench_frac')}.

## Baseline vs Optimized
**Baseline policy** (hand-tuned starting point):
```json
{json.dumps(default_baseline_policy(), indent=2)}
```

**Baseline trace**:
- cum_billable_hours: {baseline_tr['cum_billable_hours']}
- avg_util: {baseline_tr['avg_util']}
- final_maturity: {baseline_tr['final_maturity']}
- avg_bench_frac: {baseline_tr['avg_bench_frac']}
- constraints_satisfied: {baseline_tr['constraints_satisfied']}

**Optimized selection** (grid search + PuLP or fallback argmax on risk-adjusted objective; admissible first):
- status: {opt_res.get('status')}
- solver: {opt_res.get('solver')}
- chosen objective: {opt_res.get('objective')}
- chosen policy:
```json
{json.dumps(pol, indent=2)}
```
- n_candidates: {opt_res.get('n_candidates')} (admissible: {opt_res.get('n_admissible')})

**Replay robustness** (chosen + neighborhood):
- base: {json.dumps(base, indent=2)}
- robustness_delta: {json.dumps(replay.get('robustness_delta', {}), indent=2)}
- neighbors sample: {replay.get('neighbors', [])[:2]}

**Utilization trajectory (baseline spark for visual)**: {spark(baseline_tr.get('util_trajectory', []))}
**Maturity trajectory**: {spark(baseline_tr.get('maturity_trajectory', []))}

## Concrete Recommendations (phrased for the three heads)
{chr(10).join('- ' + r for r in recs)}

## FinOps / Decision Cost Attribution (CostReport analog)
PDR-style records emitted per period (policy-attributed, per ontology CostAttributionLevel=policy preference). Aggregated here.

```json
{cost_analog.model_dump_json(indent=2)}
```

Sample attributions (first 4 periods):
```json
{json.dumps(baseline_tr.get('pdr_attributions', [])[:4], indent=2)}
```

## Reproducibility & Scaling
- Deterministic seed + small grid for demo.
- Replicates: adapt templates/scenario-replicates.example.yaml (or batch-orchestrator manifest) with oteemo_billable + seed sweep.
- `scenario-research run oteemo_billable --steps {periods} --seed {seed}` (via local adapter; no camel required).
- Pre-run validation + agent compile exercised for oteemo roles.
- To refresh firm snapshot from source ontology (absolute path only at ingest time): set OTEEMO_ONTOLOGY_SRC and run a helper (future).

## ScenarioRun DTO (for MCP / orchestrator)
```json
{scenario_run.model_dump_json(indent=2)}
```

## ResearchReport (bundled deliverable shape)
```json
{ResearchReport(
    report_id=f"oteemo-{seed}",
    question="Maximize billable hours / utilization via leadership policy under Axiom investment vs client delivery trade-off (Oteemo ontology)",
    report_path=str(md_path),
    scenario_runs=[scenario_run],
    cost_report=cost_analog,
    created_at=datetime.now(timezone.utc).isoformat(),
    seed=seed,
).model_dump_json(indent=2)}
```

---
*All artifacts produced inside meta-utilities per AGENTS.md (portable, relative paths, governed YAML, two-layer timeouts respected via existing contract, no memory/orchestrator duplication, extends batch for replicates).*
"""

    md_path.write_text(md)
    bundle = {
        "baseline": baseline_tr,
        "optimized": opt_res,
        "replay": replay,
        "scenario_run": scenario_run.model_dump(),
        "cost_analog": cost_analog.model_dump(),
        "recommendations": recs,
        "report_path": str(md_path),
    }
    json_path.write_text(json.dumps(bundle, indent=2))
    return md


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Oteemo billable max demo (ODRS)")
    ap.add_argument("--periods", type=int, default=12)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--optimize", action="store_true", help="Run grid+pulp optimization + replay")
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args(argv)

    periods = args.periods
    seed = args.seed

    print("[oteemo] loading firm init (relative package data or env override)...")
    init = load_firm_init()
    print(f"[oteemo] capacity={init.get('capacity',{}).get('total_fte_equiv')}, axiom_init_mat={init.get('axiom',{}).get('initial_maturity')}")

    if not args.no_validate:
        print("[oteemo] pre-run validation + governed agent compile for leadership roles...")
        validate_before_run("oteemo_billable", seed=seed)
        # Explicit compile of the three heads + specialist (exercises compiler + roles.yaml)
        oteemo_base = OTEEMO_ONTOLOGY
        for rn in ("raja_gudepu_ceo", "arkaprava_chaudhuri_vp_tech", "roderick_kelly_fed_delivery", "clifford_dalson_axiom_finops"):
            spec = compile_agent_for_role(rn, ontology_base=oteemo_base)
            print(f"  compiled {rn}: kind={spec['kind']}, endpoint={spec['model_endpoint']}, source={spec.get('source')}")
        roles_doc = load_roles()
        print(f"[oteemo] roles schema_version={roles_doc.get('schema_version')}, total_roles={len(roles_doc.get('roles',[]))}")

    print("[oteemo] baseline run...")
    baseline_pol = default_baseline_policy()
    baseline_tr = simulate(baseline_pol, periods=periods, seed=seed, init=init)

    opt_res: dict[str, Any] = {"status": "skipped"}
    replay: dict[str, Any] = {"status": "skipped"}
    if args.optimize:
        print("[oteemo] building policy grid + evaluating candidates (light sims)...")
        opt_res = optimize_oteemo_policy(periods=periods, seed=seed, init=init)
        chosen_pol = (opt_res.get("chosen") or {}).get("policy") or baseline_pol
        print(f"[oteemo] optimized (status={opt_res.get('status')}, obj={opt_res.get('objective')})")
        print("[oteemo] replaying chosen policy for robustness...")
        replay = replay_oteemo_policy(chosen_pol, periods=periods, seed=seed, init=init)

    # ScenarioRun via the local path (exercises adapter for oteemo)
    from scenario_research.scaffold_adapter import execute_scenario
    print("[oteemo] producing ScenarioRun via adapter (local oteemo path)...")
    import asyncio
    scenario_run = asyncio.run(execute_scenario("oteemo_billable", n_steps=periods, seed=seed))

    # CostReport analog from baseline pdr (or chosen if optimized)
    pdr = baseline_tr.get("pdr_attributions", [])
    total_attrib_cost = sum(a.get("invest_cost", 0) for a in pdr)
    cost_analog = CostReport(
        run_id=scenario_run.run_id,
        local_tokens=len(pdr) * 120,  # proxy "decision tokens"
        api_tokens=0,
        estimated_cost_usd=round(total_attrib_cost / 800.0, 4),  # arbitrary scaling for demo
        local_model="oteemo-firm-sim",
        notes="Repurposed CostReport: decision FinOps attribution (invest+bench+policy deltas). PDR-level per ontology.",
    )

    print("[oteemo] generating report + artifacts...")
    generate_report(baseline_tr, opt_res, replay, scenario_run, cost_analog, init, periods, seed)
    print(f"[oteemo] report written. Key numbers: baseline_cum={baseline_tr['cum_billable_hours']}, opt_obj={opt_res.get('objective')}")
    print("Done. Repro: scenario-research run oteemo_billable --steps 12 --seed 42 --optimize (or python -m oteemo.demos.oteemo_billable_max when oteemo sibling on path)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
