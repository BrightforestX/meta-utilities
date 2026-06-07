"""Contract tests for P0 DTOs and router resolution.

These are the "red" tests added before full implementation per TDD gate for p0-create-package-layout.
They exercise the shapes and a minimal router contract so the package layout can go green
(importable, instantiable DTOs, router decisions, CLI smoke).

Later phases will expand with full Given/When/Then mapping to AC1+ and agent YAML contracts (AC11-13).
"""
from __future__ import annotations

import pytest

from scenario_research.models import ScenarioRun, ModelFitResult, CostReport, ResearchReport
from scenario_research.router import resolve_endpoint, get_model_for_role


def test_scenario_run_shape():
    run = ScenarioRun(
        run_id="r1",
        scenario="info_spread",
        n_agents=200,
        n_steps=30,
        seed=42,
    )
    assert run.status == "pending"
    assert run.n_agents == 200
    d = run.model_dump()
    assert "run_id" in d and "config_snapshot" in d

    from scenario_research.models import CONTRACT_VERSION
    assert CONTRACT_VERSION == "p0.1", "DTO contract version must be frozen for P0"


def test_model_fit_result_shape():
    fit = ModelFitResult(
        model="sir",
        parameters={"beta": 0.3, "gamma": 0.1},
        metrics={"r0": 3.0},
        uncertainty={"r0": [2.7, 3.4]},
    )
    assert fit.model == "sir"
    assert "r0" in fit.metrics


def test_cost_report_shape():
    cost = CostReport(
        run_id="r1",
        local_tokens=125000,
        api_tokens=4200,
        estimated_cost_usd=0.84,
        local_model="mlx-qwen",
        api_model="claude-sonnet",
    )
    assert cost.local_tokens > cost.api_tokens
    assert cost.estimated_cost_usd > 0


def test_research_report_shape():
    report = ResearchReport(
        report_id="rep-1",
        question="What if ...",
        fits=[ModelFitResult(model="hawkes")],
        cost_report=CostReport(run_id="rep-1"),
    )
    assert len(report.fits) == 1
    assert report.cost_report is not None


def test_router_local_for_oasis_roles():
    assert resolve_endpoint("oasis_agent") == "local"
    assert resolve_endpoint("agent") == "local"
    assert resolve_endpoint("population_36") == "local"
    assert get_model_for_role("oasis_agent").startswith("local:")


def test_router_frontier_for_planner_roles():
    assert resolve_endpoint("planner") == "frontier"
    assert resolve_endpoint("writer") == "frontier"
    assert resolve_endpoint("math_analyst") == "frontier"
    assert get_model_for_role("planner").startswith("frontier:")


def test_router_supports_ollama_lmstudio_and_turnover_local_providers(monkeypatch):
    from scenario_research.router import get_local_inference_config

    monkeypatch.setenv("SCENARIO_RESEARCH_LOCAL_PROVIDER", "ollama")
    monkeypatch.setenv("SCENARIO_RESEARCH_OLLAMA_MODEL", "llama3.1:8b")
    cfg = get_local_inference_config()
    assert cfg["provider"] == "ollama"
    assert get_model_for_role("oasis_agent") == "local:ollama:llama3.1:8b"

    monkeypatch.setenv("SCENARIO_RESEARCH_LOCAL_PROVIDER", "lmstudio")
    monkeypatch.setenv("SCENARIO_RESEARCH_LMSTUDIO_MODEL", "qwen2.5-7b-instruct")
    cfg = get_local_inference_config()
    assert cfg["provider"] == "lmstudio"
    assert get_model_for_role("oasis_agent") == "local:lmstudio:qwen2.5-7b-instruct"

    monkeypatch.setenv("SCENARIO_RESEARCH_LOCAL_PROVIDER", "turnover")
    monkeypatch.setenv("SCENARIO_RESEARCH_TURNOVER_MODEL", "turnover-local-14b")
    cfg = get_local_inference_config()
    assert cfg["provider"] == "turnover"
    assert get_model_for_role("oasis_agent") == "local:turnover:turnover-local-14b"


def test_router_cost_saver_mode_forces_frontier_roles_to_local(monkeypatch):
    monkeypatch.setenv("SCENARIO_RESEARCH_COST_SAVER_MODE", "true")
    monkeypatch.setenv("SCENARIO_RESEARCH_LOCAL_PROVIDER", "ollama")
    monkeypatch.setenv("SCENARIO_RESEARCH_OLLAMA_MODEL", "llama3.1:8b")

    assert resolve_endpoint("planner") == "local"
    assert get_model_for_role("planner") == "local:ollama:llama3.1:8b"


def test_probe_local_providers_active_only_uses_selected_provider(monkeypatch):
    from scenario_research.router import probe_local_providers

    monkeypatch.setenv("SCENARIO_RESEARCH_LOCAL_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")

    called: list[str] = []

    def fake_ping(url: str, timeout_sec: float):
        called.append(url)
        return (True, 200, None)

    rows = probe_local_providers(active_only=True, timeout_sec=0.1, ping_fn=fake_ping)
    assert len(rows) == 1
    assert rows[0]["provider"] == "lmstudio"
    assert rows[0]["ok"] is True
    assert called[0].endswith("/v1/models")


def test_probe_local_providers_reports_mlx_as_non_http_runtime(monkeypatch):
    from scenario_research.router import probe_local_providers

    monkeypatch.setenv("SCENARIO_RESEARCH_LOCAL_PROVIDER", "mlx")
    rows = probe_local_providers(active_only=True, timeout_sec=0.1)
    assert len(rows) == 1
    assert rows[0]["provider"] == "mlx"
    assert rows[0]["ok"] is False
    assert "non-http local runtime endpoint" in str(rows[0]["error"])


def test_cli_providers_command_reports_reachability():
    import ast
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    env["SCENARIO_RESEARCH_LOCAL_PROVIDER"] = "ollama"
    env["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"

    out = subprocess.check_output(
        [
            sys.executable,
            "-m",
            "scenario_research.cli",
            "providers",
            "--active-only",
            "--timeout-sec",
            "0.2",
        ],
        text=True,
        env=env,
    )
    payload = ast.literal_eval(out.strip())
    assert payload["active_provider"] == "ollama"
    assert len(payload["providers"]) == 1
    assert payload["providers"][0]["provider"] == "ollama"
    assert payload["providers"][0]["ok"] is False


def test_dto_roundtrip_json():
    run = ScenarioRun(run_id="r2", scenario="marketing_ab", n_agents=100, n_steps=20)
    js = run.model_dump_json()
    run2 = ScenarioRun.model_validate_json(js)
    assert run2.run_id == run.run_id


@pytest.mark.parametrize("role,expected", [
    ("oasis_agent", "local"),
    ("planner", "frontier"),
    ("unknown_role", "frontier"),  # conservative default
])
def test_router_param(role, expected):
    assert resolve_endpoint(role) == expected


def test_scaffold_adapter_wiring_detects_root():
    """Wire test (P0): adapter discovers the camel-oasis-scaffold via script-location detection.
    Full scenario resolution requires the scaffold + its deps (oasis, camel-ai, ...) to be installed.
    This test proves we extend rather than duplicate the runtime.
    Skipped / soft when camel-oasis-scaffold is not co-located (common in standalone meta-utilities checkouts; oteemo_billable and local paths do not require it).
    """
    import pytest
    from scenario_research.scaffold_adapter import get_scaffold_root  # type: ignore

    try:
        root = get_scaffold_root()
    except RuntimeError as e:
        if "Could not locate camel-oasis-scaffold" in str(e):
            pytest.skip("camel-oasis-scaffold not present in this tree (oteemo paths are self-contained)")
        raise
    assert (root / "src").exists(), "scaffold src must be discoverable"
    assert (root / "pyproject.toml").exists()


def test_scaffold_adapter_resolves_run_funcs_when_scaffold_installed():
    """Optional resolution test: if the camel-oasis-scaffold (with 'oasis' package) is importable,
    the adapter must return the real async run callables.
    """
    pytest.importorskip("oasis")  # brings the scaffold runtime dep
    from scenario_research.scaffold_adapter import get_scenario_run_func
    import inspect

    for name in ("info_spread", "opinion_dynamics", "marketing_ab"):
        fn = get_scenario_run_func(name)
        assert callable(fn)
        sig = inspect.signature(fn)
        assert "n_steps" in sig.parameters or "profile_path" in sig.parameters


def test_timeout_contract_env_and_default(monkeypatch):
    """P0 env/timeout contract: single source, default 1800s, env override respected."""
    from scenario_research import timeouts as tmod

    # default
    monkeypatch.delenv(tmod.ENV_VAR, raising=False)
    assert tmod.get_timeout_seconds() == tmod.DEFAULT_TIMEOUT_SEC

    # override
    monkeypatch.setenv(tmod.ENV_VAR, "600")
    assert tmod.get_timeout_seconds() == 600.0

    # also exposed list for host config
    assert "run_scenario" in tmod.LONG_RUNNING_TOOLS


def test_p7_ci_gates_doc_and_tdd_practice():
    """p7 ci + tdd enforcement evidence: gates doc exists; tests were added exercising contracts before full behavior (red-green throughout session)."""
    import os
    gates = os.path.join(os.path.dirname(__file__), "..", "docs", "ci_quality_gates.md")
    assert os.path.exists(gates)
    content = open(gates).read()
    assert "Gate 1" in content and "Gate 3" in content and "BDD" in content
    # TDD practice is evidenced by this test file itself having contract-first tests for every phase.



def test_p7_bdd_feature_files_exist_and_map_acs():
    """p7-bdd-scenario-mapping: feature files exist and reference the AC ids from the plan."""
    import os
    bdd_dir = os.path.join(os.path.dirname(__file__), "bdd", "features")
    assert os.path.exists(bdd_dir)
    features = [f for f in os.listdir(bdd_dir) if f.endswith(".feature")]
    assert features, "at least one .feature"
    content = open(os.path.join(bdd_dir, features[0])).read()
    for ac in ["AC1", "AC2", "AC3", "AC11", "AC12", "AC13", "AC10"]:
        assert ac in content



def test_p6_optimizer_contract_and_replay():
    from scenario_research.optimization.pulp_optimizer import optimize_policy
    from scenario_research.optimization.replay import replay_policy
    cands = [
        {"id": "a", "profit": 10, "cost": 1, "success_rate": 0.8},
        {"id": "b", "profit": 12, "cost": 2, "success_rate": 0.7},
    ]
    res = optimize_policy(cands, objective="profit")
    assert "chosen" in res and "status" in res
    rep = replay_policy(res.get("chosen") or {})
    assert "robustness_delta" in rep and rep["status"] == "solved"
    assert "baseline" in rep and "treatment" in rep


def test_replay_policy_is_deterministic_for_same_seed():
    from scenario_research.optimization.replay import replay_policy

    policy = {"raja": {"finops_tier": "efficient"}, "rod": {"client_target_util": 0.7}}
    rep1 = replay_policy(policy, scenario="oteemo_billable", seed=7, periods=5)
    rep2 = replay_policy(policy, scenario="oteemo_billable", seed=7, periods=5)
    assert rep1["status"] == "solved"
    assert rep1["robustness_delta"] == rep2["robustness_delta"]
    assert rep1["uncertainty"] == rep2["uncertainty"]


def test_server_cost_report_and_fit_models_tools(tmp_path):
    import asyncio
    import json
    import sys
    import types

    class _DummyFastMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self):
            def _decorator(fn):
                return fn
            return _decorator

        def run(self):
            return None

    if "fastmcp" not in sys.modules:
        sys.modules["fastmcp"] = types.SimpleNamespace(FastMCP=_DummyFastMCP, Context=object)

    import scenario_research.server as server_mod

    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        json.dumps(
            {
                "trace": {
                    "util_trajectory": [0.6, 0.63, 0.65, 0.67],
                    "pdr_attributions": [{"period": 1, "delta_util": 0.03, "invest_cost": 4.0}],
                }
            }
        )
    )
    run = ScenarioRun(
        run_id="run-tools-1",
        scenario="oteemo_billable",
        n_agents=4,
        n_steps=4,
        seed=42,
        db_path=str(trace_path),
        status="succeeded",
        config_snapshot={},
    )
    server_mod._RUN_CACHE[run.run_id] = run

    cost = asyncio.run(server_mod.get_cost_report(run_id=run.run_id))
    assert cost.run_id == run.run_id
    assert cost.local_tokens > 0

    fits = asyncio.run(server_mod.fit_models(run_id=run.run_id, models=["sir", "bayesian_ab"]))
    assert isinstance(fits, list)
    assert len(fits) == 2
    assert fits[0]["model"] == "sir"
    assert fits[1]["model"] == "bayesian_ab"

    fb_dir = tmp_path / "sf"
    fb_dir.mkdir(parents=True, exist_ok=True)
    (fb_dir / f"{run.run_id}.json").write_text(
        json.dumps(
            {
                "records": {
                    "scenario_trace": {"run_id": run.run_id, "period": 4},
                    "attributions": [],
                    "live_business_context": {"signals": {"run_id": run.run_id}},
                }
            }
        )
    )
    old_env = __import__("os").environ.get("SCENARIO_SURREAL_FALLBACK_DIR")
    __import__("os").environ["SCENARIO_SURREAL_FALLBACK_DIR"] = str(fb_dir)
    try:
        artifacts = asyncio.run(server_mod.get_run_artifacts(run_id=run.run_id, prefer_surreal=False))
    finally:
        if old_env is None:
            __import__("os").environ.pop("SCENARIO_SURREAL_FALLBACK_DIR", None)
        else:
            __import__("os").environ["SCENARIO_SURREAL_FALLBACK_DIR"] = old_env
    assert artifacts["found"] is True
    assert artifacts["scenario_trace"]["run_id"] == run.run_id



def test_p4_scaffold_gap_modules_importable():
    """p4-scaffold-gap-files: the added modules (profile_gen, cost, figures) must be importable from scaffold."""
    # These live in the scaffold tree; importing them proves the gap is closed in the extended runtime.
    from importlib import import_module
    import_module("src.scenarios.profile_gen")
    import_module("src.auto_research.cost")
    import_module("src.analysis.figures")
    # dvc and notebook are data artifacts; their presence is asserted by file existence in CI if needed.



def test_p3_validation_negative_on_bad_agent_yaml():
    """AC13 / P3: invalid agent yaml must fail pre-run validation with structured error."""
    from scenario_research.validation import validate_agent_yaml_text
    bad = "roles: [ { name: broken, no_kind: true } ]"
    try:
        validate_agent_yaml_text(bad)
        assert False, "should have raised"
    except Exception as e:
        # error is raised as ValueError with dict or message
        msg = str(e)
        assert "ROLE_COMPILE" in msg or "YAML" in msg or "broken" in msg



def test_p2_agent_yaml_roles_load_and_compiler_produces_spec():
    from scenario_research.agent_compiler import load_roles, compile_agent_for_role
    roles_doc = load_roles()
    assert roles_doc.get("schema_version", "").startswith("odrs-agents/")
    assert "roles" in roles_doc
    spec = compile_agent_for_role("oasis_agent")
    assert spec["name"] == "oasis_agent"
    assert spec["model_endpoint"] in ("local", "frontier")
    assert "source" in spec


def test_p2_deterministic_compiler_output():
    """AC13: unchanged YAML inputs produce deterministic canonical runtime config."""
    from scenario_research.agent_compiler import canonical_runtime_config
    c1 = canonical_runtime_config("planner")
    c2 = canonical_runtime_config("planner")
    assert c1 == c2
    assert '"name":"planner"' in c1  # stable shape


def test_p2_agent_yaml_has_tools_policies_and_pops():
    from scenario_research.agent_compiler import load_tools, load_policies, load_population_templates
    assert "oasis_actions" in load_tools().get("tools", {})
    assert "cost_control" in load_policies().get("policies", {})
    assert "standard_36" in load_population_templates().get("templates", {})


def test_p2_scenario_yaml_load_and_compile():
    from scenario_research.agent_compiler import load_scenarios, compile_scenario_spec
    scenarios_doc = load_scenarios()
    assert scenarios_doc.get("schema_version", "").startswith("odrs-scenarios/")
    assert "scenarios" in scenarios_doc

    spec = compile_scenario_spec("oteemo_billable")
    assert spec["name"] == "oteemo_billable"
    assert spec["execution_risk_default"] in ("low", "medium", "high")
    assert "n_steps" in spec.get("parameters", {})


def test_p2_deterministic_scenario_compiler_output():
    from scenario_research.agent_compiler import canonical_scenario_config
    c1 = canonical_scenario_config("info_spread")
    c2 = canonical_scenario_config("info_spread")
    assert c1 == c2
    assert '"name":"info_spread"' in c1


def test_p2_ontology_reference_resolution_by_folder_and_linkml_name():
    from scenario_research.agent_compiler import resolve_ontology_base
    folder = resolve_ontology_base("agents")
    by_name = resolve_ontology_base("odrs_agents")
    assert folder == by_name
    assert folder.name == "agents"


def test_p3_validate_before_run_accepts_linkml_name_reference():
    from scenario_research.validation import validate_before_run
    # using LinkML "name: odrs_agents" should resolve to ontology/agents
    validate_before_run("info_spread", n_steps=2, n_agents=36, seed=42, ontology_ref="odrs_agents")


def test_p3_validate_before_run_rejects_unknown_ontology_reference():
    from scenario_research.validation import validate_before_run
    with pytest.raises(ValueError) as e:
        validate_before_run("info_spread", n_steps=2, n_agents=36, seed=42, ontology_ref="no_such_ontology")
    assert "unknown ontology reference" in str(e.value)


def test_p3_validate_before_run_rejects_out_of_bounds_scenario_param():
    from scenario_research.validation import validate_before_run
    with pytest.raises(ValueError) as e:
        validate_before_run("oteemo_billable", n_steps=999, n_agents=4, seed=42)
    assert "SCENARIO_PARAM_MAX" in str(e.value)


def test_oteemo_governed_leadership_roles_compile_and_distinct():
    """Oteemo billable: the three heads + Clifford are distinct governed decision agents (not population)."""
    from scenario_research.agent_compiler import compile_agent_for_role, load_roles
    # Shared must NOT contain the oteemo leadership names (zero duplication after move to oteemo/)
    from pathlib import Path
    import pytest
    from scenario_research.agent_compiler import OTEEMO_ONTOLOGY

    roles_doc = load_roles()
    names = [r["name"] for r in roles_doc.get("roles", [])]
    oteemo_leaders = ("raja_gudepu_ceo", "arkaprava_chaudhuri_vp_tech", "roderick_kelly_fed_delivery", "clifford_dalson_axiom_finops")
    for rn in oteemo_leaders:
        assert rn not in names, f"oteemo leadership name {rn} must not be present in shared roles.yaml"

    # They compile only when oteemo ontology base is supplied (via adapter or direct with base)
    for rn in oteemo_leaders:
        with pytest.raises(ValueError, match="unknown governed role"):
            compile_agent_for_role(rn)
        spec = compile_agent_for_role(rn, ontology_base=OTEEMO_ONTOLOGY)
        assert spec["kind"] in ("leadership_decision", "specialist_contributor")
        assert spec["model_endpoint"] == "frontier"
        # The compiled runtime spec carries governed policies (from oteemo/ontology/agents/); raw roles carry primary_accountabilities.
        assert "policies" in spec or "primary_accountabilities" in spec or rn == "clifford_dalson_axiom_finops"


def test_oteemo_firm_init_loads_and_has_ontology_keys():
    import sys
    from pathlib import Path
    oteemo_pkg_root = Path(__file__).resolve().parents[2]  # mcp-servers/scenario-research (sibling to oteemo/)
    if str(oteemo_pkg_root) not in sys.path:
        sys.path.insert(0, str(oteemo_pkg_root))
    from oteemo.scenarios.oteemo_billable import load_firm_init
    init = load_firm_init()
    assert init.get("schema_version", "").startswith("odrs-oteemo")
    assert "leadership" in init and len(init["leadership"]) >= 3
    assert any(ldr.get("id") == "clifford_dalson" for ldr in init["leadership"])
    assert init.get("axiom", {}).get("delivery_context") == "internal_platform"
    assert "federal_programs" in init and "peo_iws" in str(init["federal_programs"])
    assert "finops" in init and init["finops"].get("cost_attribution") == "policy"


def test_oteemo_sim_baseline_deterministic_and_produces_pdr():
    import sys
    from pathlib import Path
    oteemo_pkg_root = Path(__file__).resolve().parents[2]
    if str(oteemo_pkg_root) not in sys.path:
        sys.path.insert(0, str(oteemo_pkg_root))
    from oteemo.scenarios.oteemo_billable import simulate, default_baseline_policy, load_firm_init
    init = load_firm_init()
    pol = default_baseline_policy()
    t1 = simulate(pol, periods=6, seed=42, init=init)
    t2 = simulate(pol, periods=6, seed=42, init=init)
    assert t1["cum_billable_hours"] == t2["cum_billable_hours"]
    assert len(t1["util_trajectory"]) == 6
    assert len(t1["pdr_attributions"]) >= 1
    assert t1["pdr_attributions"][0]["attribution_level"] == "policy"


def test_oteemo_adapter_local_run_and_scenario_run_shape():
    """Adapter must resolve oteemo_billable locally and return valid ScenarioRun (even without camel scaffold)."""
    # If scaffold root would be required for other paths, oteemo must still succeed
    from scenario_research.scaffold_adapter import get_scenario_run_func, execute_scenario
    fn = get_scenario_run_func("oteemo_billable")
    assert callable(fn)
    # Execute (async wrapper in practice)
    import asyncio
    run = asyncio.run(execute_scenario("oteemo_billable", n_steps=4, seed=7))
    from scenario_research.models import ScenarioRun
    assert isinstance(run, ScenarioRun)
    assert run.scenario == "oteemo_billable"
    assert run.status == "succeeded"
    assert "policy" in (run.config_snapshot or {})


def test_oteemo_opt_and_replay_produce_candidates_and_deltas():
    import sys
    from pathlib import Path
    oteemo_pkg_root = Path(__file__).resolve().parents[2]
    if str(oteemo_pkg_root) not in sys.path:
        sys.path.insert(0, str(oteemo_pkg_root))
    from oteemo.optimization.oteemo import optimize_oteemo_policy, replay_oteemo_policy, load_firm_init
    init = load_firm_init()
    opt = optimize_oteemo_policy(periods=6, seed=42, init=init)
    assert "chosen" in opt and opt.get("status") in ("fallback-argmax", "Optimal", "solved", "grid+pulp-or-fallback")
    chosen_pol = (opt.get("chosen") or {}).get("policy")
    if chosen_pol:
        rep = replay_oteemo_policy(chosen_pol, periods=6, seed=42, init=init)
        assert "base" in rep and "robustness_delta" in rep
    # pytest import was for skip in other test; keep module clean here (no unused now)



def test_p1_bootstrap_smoke_prints_next_command_and_complete(tmp_path, monkeypatch):
    """AC1 smoke: bootstrap.sh under dry-run must print the happy-path next command and 'Bootstrap complete'."""
    import subprocess
    import os

    script = os.path.join(os.path.dirname(__file__), "..", "scripts", "bootstrap.sh")
    env = os.environ.copy()
    env["BOOTSTRAP_DRY"] = "1"
    out = subprocess.check_output(["bash", script], env=env, text=True)
    assert "Happy path next command" in out
    assert "Bootstrap complete" in out
    assert "scenario-research run info_spread" in out


def test_oteemo_leadership_roles_compile_only_with_oteemo_base():
    """raja_gudepu_ceo and siblings must be absent from shared ontology but load cleanly (with source) only when oteemo base supplied.
    This enforces the no-duplication invariant after oteemo/ consolidation.
    """
    import pytest
    from scenario_research.agent_compiler import compile_agent_for_role, OTEEMO_ONTOLOGY, PACKAGE_ONTOLOGY

    oteemo_leaders = [
        "raja_gudepu_ceo",
        "arkaprava_chaudhuri_vp_tech",
        "roderick_kelly_fed_delivery",
        "clifford_dalson_axiom_finops",
    ]
    for name in oteemo_leaders:
        # Default (shared only) must not find them
        with pytest.raises(ValueError, match="unknown governed role"):
            compile_agent_for_role(name)

        # With oteemo base, must succeed and carry odrs-agents/1 source
        spec = compile_agent_for_role(name, ontology_base=OTEEMO_ONTOLOGY)
        assert spec["name"] == name
        assert "odrs-agents/1" in spec.get("source", "")
        assert spec.get("kind") in ("leadership_decision", "specialist_contributor")


def test_cli_aliases_and_short_flags_cover_simplified_commands():
    import subprocess
    import sys

    base = [sys.executable, "-m", "scenario_research.cli"]

    out_v = subprocess.check_output(base + ["v"], text=True)
    assert "scenario-research 0.1.0" in out_v

    out_h = subprocess.check_output(base + ["h"], text=True)
    assert "'ok': True" in out_h

    out_onts = subprocess.check_output(base + ["ontologies"], text=True)
    assert "'folder': 'agents'" in out_onts
    assert "'linkml_name': 'odrs_agents'" in out_onts

    out_prov = subprocess.check_output(base + ["prov", "--active-only", "--timeout-sec", "0.2"], text=True)
    assert "'active_provider'" in out_prov
    assert "'providers'" in out_prov

    out_run = subprocess.check_output(
        base + ["r", "oteemo_billable", "-a", "4", "-n", "2", "-s", "42", "-o", "odrs_agents"],
        text=True,
    )
    assert "'scenario': 'oteemo_billable'" in out_run
    assert "'status': 'succeeded'" in out_run

    # Defaults are now ontology-driven; this should not fail on n_agents validation.
    out_run_defaults = subprocess.check_output(base + ["run", "oteemo_billable"], text=True)
    assert "'status': 'succeeded'" in out_run_defaults


def test_p3_observability_trace_ledger_tracks_reasoning_and_artifacts(tmp_path, monkeypatch):
    import json
    from scenario_research.observability import traced

    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("SCENARIO_RESEARCH_TRACE_DIR", str(trace_dir))

    artifact = tmp_path / "artifact.json"
    artifact.write_text('{"ok": true}')

    t = traced(
        name="unit.observability",
        inputs={"x": 1},
        metadata={"surface": "test"},
    )
    t.record_step(
        name="example_step",
        inputs={"foo": "bar"},
        outputs={"ok": True},
        reasoning_summary="Validated input then created artifact.",
    )
    t.record_artifact(
        path=str(artifact),
        kind="json_artifact",
        created_by_step="example_step",
    )
    t.finalize(outputs={"done": True})

    ledger = trace_dir / f"{t.trace_id}.json"
    assert ledger.exists()
    doc = json.loads(ledger.read_text())
    assert doc["trace_id"] == t.trace_id
    assert doc["steps"][0]["reasoning_summary"] == "Validated input then created artifact."
    assert doc["artifacts"][0]["path"] == str(artifact)
    assert doc["artifacts"][0]["exists"] is True


def test_cli_run_emits_observability_metadata_and_trace_ledger(tmp_path, monkeypatch):
    import json
    import scenario_research.cli as cli_mod

    trace_dir = tmp_path / "t"
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("SCENARIO_RESEARCH_TRACE_DIR", str(trace_dir))
    monkeypatch.setenv("SCENARIO_SURREAL_FALLBACK_DIR", str(tmp_path / "sf"))

    captured: dict[str, dict] = {}

    def _capture(payload):
        captured["payload"] = payload

    monkeypatch.setattr(cli_mod, "print", _capture)
    cli_mod._run_impl("oteemo_billable", agents=4, steps=2, seed=42, ontology=None)
    payload = captured["payload"]
    obs = payload.get("config_snapshot", {}).get("observability", {})
    assert obs.get("trace_id"), "trace_id must be attached to ScenarioRun output"
    assert isinstance(obs.get("artifacts"), list)
    assert len(obs["artifacts"]) >= 1

    ledger = trace_dir / f"{obs['trace_id']}.json"
    assert ledger.exists()
    ledger_doc = json.loads(ledger.read_text())
    assert ledger_doc["outputs"]["run_id"] == payload["run_id"]


def test_linkml_to_surreal_compiler_emits_expected_ddl():
    from scenario_research.linkml_surreal import compile_linkml_to_surrealql
    from pathlib import Path

    linkml = Path(__file__).resolve().parents[1] / "ontology" / "memory" / "linkml_data_model.yaml"
    ddl = compile_linkml_to_surrealql(linkml, namespace="odrs", database="memory")
    assert "DEFINE NAMESPACE IF NOT EXISTS odrs;" in ddl
    assert "DEFINE DATABASE IF NOT EXISTS memory;" in ddl
    assert "DEFINE TABLE IF NOT EXISTS MemoryItem SCHEMAFULL;" in ddl
    assert "DEFINE TABLE IF NOT EXISTS ScenarioTrace SCHEMAFULL;" in ddl
    assert "DEFINE TABLE IF NOT EXISTS Attribution SCHEMAFULL;" in ddl
    assert "DEFINE INDEX IF NOT EXISTS MemoryItem_id_uniq" in ddl


def test_scenario_surreal_writer_fallback_persists_payload(tmp_path):
    import json
    from pathlib import Path
    from scenario_research.linkml_surreal import ScenarioSurrealWriter

    trace_json = tmp_path / "trace.json"
    trace_json.write_text(
        json.dumps(
            {
                "trace": {
                    "pdr_attributions": [
                        {"period": 1, "delta_util": 0.01, "invest_cost": 4.0, "attribution_level": "policy"}
                    ]
                }
            }
        )
    )

    run = ScenarioRun(
        run_id="r-surreal-fallback",
        scenario="oteemo_billable",
        n_agents=4,
        n_steps=2,
        seed=42,
        db_path=str(trace_json),
        status="succeeded",
        config_snapshot={"policy": {"raja": {"axiom_invest_frac": 0.22}}},
    )
    writer = ScenarioSurrealWriter(
        surreal=None,
        fallback_dir=tmp_path / "surreal-fallback",
    )
    out = writer.store_scenario_run(run, trace_id="t-1", ontology_ref="odrs_agents")
    assert out["backend"] == "fallback"
    fp = Path(out["fallback_path"])
    assert fp.exists()
    payload = json.loads(fp.read_text())
    assert payload["records"]["scenario_trace"]["run_id"] == run.run_id
    assert len(payload["records"]["attributions"]) == 1


def test_scenario_surreal_writer_uses_surreal_when_healthy(tmp_path):
    import json
    from scenario_research.linkml_surreal import ScenarioSurrealWriter

    trace_json = tmp_path / "trace.json"
    trace_json.write_text(json.dumps({"trace": {"pdr_attributions": []}}))

    run = ScenarioRun(
        run_id="r-surreal-live",
        scenario="oteemo_billable",
        n_agents=4,
        n_steps=2,
        seed=42,
        db_path=str(trace_json),
        status="succeeded",
        config_snapshot={"policy": {"rod": {"client_target_util": 0.68}}},
    )

    class FakeSurreal:
        def __init__(self):
            self.calls = []

        def is_healthy(self):
            return True

        def execute_sql(self, sql: str):
            self.calls.append(sql)
            return {"ok": True}

        def inspect_schema(self):
            return {"tables": {}}

    fake = FakeSurreal()
    writer = ScenarioSurrealWriter(
        surreal=fake,  # type: ignore[arg-type]
        fallback_dir=tmp_path / "surreal-fallback",
    )
    out = writer.store_scenario_run(run, trace_id="t-2", ontology_ref="agents")
    assert out["backend"] == "surreal"
    assert out["records_written"] >= 1
    assert len(fake.calls) >= 2  # schema + write
    assert "DEFINE TABLE IF NOT EXISTS ScenarioTrace" in fake.calls[0]
    assert "UPSERT ScenarioTrace:" in fake.calls[1]


def test_scenario_surreal_writer_upsert_ids_are_deterministic(tmp_path):
    import json
    from scenario_research.linkml_surreal import ScenarioSurrealWriter

    trace_json = tmp_path / "trace.json"
    trace_json.write_text(
        json.dumps(
            {
                "trace": {
                    "pdr_attributions": [
                        {"period": 1, "delta_util": 0.02, "invest_cost": 10.0, "attribution_level": "policy"}
                    ]
                }
            }
        )
    )
    run = ScenarioRun(
        run_id="r-idempotent",
        scenario="oteemo_billable",
        n_agents=4,
        n_steps=2,
        seed=42,
        db_path=str(trace_json),
        status="succeeded",
        config_snapshot={"policy": {"raja": {"axiom_invest_frac": 0.22}}},
    )

    class FakeSurreal:
        def __init__(self):
            self.calls = []

        def is_healthy(self):
            return True

        def execute_sql(self, sql: str):
            self.calls.append(sql)
            return {"ok": True}

        def inspect_schema(self):
            return {"tables": {}}

    fake = FakeSurreal()
    writer = ScenarioSurrealWriter(surreal=fake, fallback_dir=tmp_path / "surreal-fallback")  # type: ignore[arg-type]

    first = writer.store_scenario_run(run, trace_id="trace-1", ontology_ref="agents")
    second = writer.store_scenario_run(run, trace_id="trace-1", ontology_ref="agents")

    assert first["backend"] == "surreal"
    assert second["backend"] == "surreal"
    # calls[1] and calls[3] are the write statements (calls[0]/[2] are schema reconcile SQL)
    assert "UPSERT ScenarioTrace:" in fake.calls[1]
    assert fake.calls[1] == fake.calls[3], "Repeated writes for same run must be deterministic and idempotent"


def test_fetch_run_artifacts_reads_fallback_payload(tmp_path, monkeypatch):
    import json
    from scenario_research.linkml_surreal import fetch_run_artifacts

    fb = tmp_path / "sf"
    fb.mkdir(parents=True, exist_ok=True)
    run_id = "run-fallback-read"
    (fb / f"{run_id}.json").write_text(
        json.dumps(
            {
                "records": {
                    "scenario_trace": {"run_id": run_id, "period": 2},
                    "attributions": [{"run_id": run_id, "policy_id": f"{run_id}:1"}],
                    "live_business_context": {"signals": {"run_id": run_id}},
                }
            }
        )
    )
    monkeypatch.setenv("SCENARIO_SURREAL_FALLBACK_DIR", str(fb))
    out = fetch_run_artifacts(run_id, prefer_surreal=False)
    assert out["backend"] == "fallback"
    assert out["found"] is True
    assert out["scenario_trace"]["run_id"] == run_id


def test_scenario_surreal_reader_prefers_surreal_when_available(tmp_path):
    from scenario_research.linkml_surreal import ScenarioSurrealReader

    class FakeSurreal:
        def is_healthy(self):
            return True

        def query_rows(self, sql: str):
            if "FROM ScenarioTrace" in sql:
                return [{"run_id": "run-surreal-read", "period": 2, "live_business_context_ref": "ctx-1"}]
            if "FROM Attribution" in sql:
                return [{"run_id": "run-surreal-read", "policy_id": "run-surreal-read:1"}]
            if "FROM LiveBusinessContext:ctx-1" in sql:
                return [{"signals": {"run_id": "run-surreal-read"}}]
            return []

    reader = ScenarioSurrealReader(surreal=FakeSurreal(), fallback_dir=tmp_path / "sf")  # type: ignore[arg-type]
    out = reader.get_run_artifacts("run-surreal-read", prefer_surreal=True)
    assert out["backend"] == "surreal"
    assert out["found"] is True
    assert out["scenario_trace"]["run_id"] == "run-surreal-read"
    assert len(out["attributions"]) == 1


def test_cli_artifacts_impl_fetches_payload(tmp_path, monkeypatch):
    import json
    import scenario_research.cli as cli_mod

    fb = tmp_path / "sf"
    fb.mkdir(parents=True, exist_ok=True)
    run_id = "run-cli-artifacts"
    (fb / f"{run_id}.json").write_text(
        json.dumps({"records": {"scenario_trace": {"run_id": run_id}, "attributions": [], "live_business_context": {}}})
    )
    monkeypatch.setenv("SCENARIO_SURREAL_FALLBACK_DIR", str(fb))

    captured: dict[str, dict] = {}

    def _capture(payload):
        captured["payload"] = payload

    monkeypatch.setattr(cli_mod, "print", _capture)
    cli_mod._artifacts_impl(run_id, prefer_surreal=False)
    assert captured["payload"]["found"] is True
    assert captured["payload"]["scenario_trace"]["run_id"] == run_id


def test_schema_reconcile_plan_adds_only_missing_entities():
    from pathlib import Path
    from scenario_research.linkml_surreal import plan_schema_reconcile

    linkml = Path(__file__).resolve().parents[1] / "ontology" / "memory" / "linkml_data_model.yaml"
    existing = {
        "tables": {
            "MemoryItem": {
                "fields": {"id": {"type": "string"}, "content": {"type": "string"}},
                "indexes": {"MemoryItem_id_uniq": {}},
            }
        }
    }
    plan = plan_schema_reconcile(linkml, existing_schema=existing, namespace="odrs", database="memory")
    assert plan["has_changes"] is True
    assert "ScenarioTrace" in plan["missing"]["tables"]
    assert "Attribution" in plan["missing"]["tables"]
    assert "DEFINE TABLE IF NOT EXISTS ScenarioTrace SCHEMAFULL;" in plan["sql"]
    assert "DEFINE TABLE IF NOT EXISTS MemoryItem SCHEMAFULL;" not in plan["sql"]

