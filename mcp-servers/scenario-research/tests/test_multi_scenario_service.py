from __future__ import annotations

import json
from pathlib import Path

from scenario_research.scaffold_adapter import get_scaffold_root


def test_multi_scenario_example_runs_locally_and_writes_results(tmp_path):
    root = get_scaffold_root()
    scenario_file = root / "examples" / "multi_scenarios.json"

    from src.camel_sim.config.scenarios import load_scenario_configs
    from src.camel_sim.results.collector import write_results
    from src.camel_sim.simulation.runner import run_scenarios

    configs = load_scenario_configs(scenario_file)
    results = run_scenarios(configs, execution_mode="local")

    assert len(results) == 4
    assert results[0]["scenario_id"] == "contract_001"
    assert results[0]["action_counts"]["PROPOSE_CONTRACT"] >= 1
    assert results[0]["action_counts"]["ACCEPT_CONTRACT"] >= 1
    assert results[1]["action_counts"]["SUBMIT_FINDING"] >= 1
    assert results[2]["action_counts"]["SCHEDULE_MEETING"] >= 1
    assert results[3]["action_counts"]["SEND_MESSAGE"] >= 1
    assert results[3]["action_counts"]["FORM_COALITION"] >= 1

    artifacts = write_results(results, tmp_path, run_id="test-run", output_format="jsonl")
    assert set(artifacts) == {"events", "summary"}
    assert (tmp_path / "test-run_events.jsonl").exists()
    summary = json.loads((tmp_path / "test-run_summary.json").read_text())
    assert summary[0]["scenario_id"] == "contract_001"


def test_multi_scenario_parallel_local_path_isolated():
    root = get_scaffold_root()
    scenario_file = root / "examples" / "multi_scenarios.json"

    from src.camel_sim.config.scenarios import load_scenario_configs
    from src.camel_sim.simulation.runner import run_scenarios

    configs = load_scenario_configs(scenario_file)
    results = run_scenarios(configs, execution_mode="local", parallel=True, max_workers=2)

    assert [result["scenario_id"] for result in results] == [
        "contract_001",
        "research_001",
        "scheduling_001",
        "social_001",
    ]
    assert all(result["final_state"]["scenario_id"] == result["scenario_id"] for result in results)


def test_multi_scenario_cli_surfaces_write_artifacts(tmp_path):
    from typer.testing import CliRunner

    root = get_scaffold_root()
    scenario_file = root / "examples" / "multi_scenarios.json"
    runner = CliRunner()

    from scenario_research.cli import app as scenario_app
    from src.cli import app as scaffold_app

    scenario_out = tmp_path / "scenario-cli"
    result = runner.invoke(
        scenario_app,
        ["multi-run", str(scenario_file), "--output-dir", str(scenario_out)],
    )
    assert result.exit_code == 0, result.output
    assert list(scenario_out.glob("*_events.jsonl"))

    scaffold_out = tmp_path / "scaffold-cli"
    result = runner.invoke(
        scaffold_app,
        ["multi-scenario", str(scenario_file), "--output-dir", str(scaffold_out)],
    )
    assert result.exit_code == 0, result.output
    assert list(scaffold_out.glob("*_summary.json"))


def test_multi_scenario_domain_routing_contract():
    from src.camel_sim.config.models import default_server_urls, get_model_name_for_domain

    assert get_model_name_for_domain("negotiation") == "qwen3-72b"
    assert get_model_name_for_domain("research") == "llama-3.3-70b"
    assert get_model_name_for_domain("scheduling") == "qwen3-32b"
    assert get_model_name_for_domain("social") == "mistral-24b"
    assert default_server_urls()["qwen3-72b"].endswith(":30001/v1")


def test_multi_scenario_invalid_domain_fails_fast():
    from pydantic import ValidationError
    import pytest

    from src.camel_sim.config.scenarios import ScenarioConfig

    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(
            {
                "id": "bad",
                "name": "bad",
                "description": "bad",
                "agents": [
                    {
                        "id": "a1",
                        "role": "unknown",
                        "domain": "not-a-domain",
                        "persona": "bad",
                    }
                ],
            }
        )


def test_multi_run_modal_target_constructs_portable_cmd_and_kicks_off(monkeypatch):
    """CLI surface for --target modal must be recognized, use get_scaffold_root for discovery,
    resolve the scenario file, and invoke the dispatch without blocking for the remote job.
    The actual modal CLI is not called; we assert the constructed command contains the
    portable paths and forwarded flags.
    """
    from typer.testing import CliRunner

    root = get_scaffold_root()
    scenario_file = root / "examples" / "multi_scenarios.json"

    captured = {}

    def fake_dispatch(sf, *, output_format="parquet", execution_mode="local", server_urls_json=""):
        captured["scenario_file"] = str(Path(sf).resolve())
        captured["output_format"] = output_format
        captured["execution_mode"] = execution_mode
        captured["server_urls_json"] = server_urls_json
        captured["scaffold_root"] = str(get_scaffold_root())
        return {
            "status": "dispatched",
            "target": "modal",
            "pid": 123456,
            "volume": "sim-results",
            "note": "mocked kick-off",
        }

    monkeypatch.setattr(
        "scenario_research.cli.dispatch_multi_scenario_to_modal",
        fake_dispatch,
    )

    runner = CliRunner()
    from scenario_research.cli import app as scenario_app

    result = runner.invoke(
        scenario_app,
        [
            "multi-run",
            str(scenario_file),
            "--target",
            "modal",
            "--execution-mode",
            "local",
            "--output-format",
            "parquet",
        ],
    )
    assert result.exit_code == 0, f"CLI failed: {result.output}"
    assert "dispatched" in result.output or "modal" in result.output.lower()
    assert captured["scenario_file"].endswith("multi_scenarios.json")
    assert captured["execution_mode"] == "local"
    assert captured["output_format"] == "parquet"
    # portable discovery was exercised (the fake calls get_scaffold_root)
    assert (Path(captured["scaffold_root"]) / "src").exists()


def test_multi_run_modal_target_graceful_when_modal_cli_missing(monkeypatch):
    """When 'modal' is not on PATH, the CLI must surface a clear actionable error
    containing the exact install hint (uv pip ...[modal,parquet]) and the
    no-cd / portable nature, without crashing or requiring the caller to cd.
    Mirrors the guard message style from modal_app.py.
    """
    from typer.testing import CliRunner

    root = get_scaffold_root()
    scenario_file = root / "examples" / "multi_scenarios.json"

    # Force the dispatch to raise the exact no-modal error the real impl would
    def fake_dispatch_raises(*a, **k):
        raise RuntimeError(
            "The 'modal' CLI is not available in PATH. "
            "To kick off Modal multi-scenario analysis from the meta-utilities scenario-research CLI (or MCP), "
            "install the camel-oasis-scaffold with the modal extra into the *same* environment used by scenario-research "
            "(this brings the 'modal' console script + the scaffold's runtime imports for the app definition): "
            "uv pip install -e 'camel-oasis-scaffold[modal,parquet]' "
            "(or from the scenario-research dir: uv pip install -e '../../camel-oasis-scaffold[modal,parquet]'). "
            "Then authenticate if needed: modal token new. "
            "After that, `scenario-research multi-run <file> --target modal` (or the MCP dispatch tool) will work from any CWD. "
            "See camel-oasis-scaffold/README.md (Modal section) and the guard in src/camel_sim/modal_app.py."
        )

    monkeypatch.setattr(
        "scenario_research.cli.dispatch_multi_scenario_to_modal",
        fake_dispatch_raises,
    )

    runner = CliRunner()
    from scenario_research.cli import app as scenario_app

    result = runner.invoke(
        scenario_app,
        ["multi-run", str(scenario_file), "--target", "modal"],
    )
    assert result.exit_code != 0
    out = result.output + str(result.exception or "")
    assert "modal" in out.lower() and "CLI" in out
    assert "uv pip install -e 'camel-oasis-scaffold[modal,parquet]'" in out
    assert "from any CWD" in out or "portable" in out.lower() or "no cd" in out.lower()
    assert "modal_app.py" in out or "guard" in out.lower()

# Headless / non-tty coverage (added for cli-headless task)
def test_cli_headless_smoke():
    from typer.testing import CliRunner
    runner = CliRunner()
    from scenario_research.cli import app as scenario_app
    # --help and a read-only command must never prompt and must exit cleanly in non-tty
    r1 = runner.invoke(scenario_app, ["--help"])
    assert r1.exit_code == 0
    assert "multi-run" in r1.output
    r2 = runner.invoke(scenario_app, ["search-ontology", "finops", "--top-k", "1"])
    # May be 0 or non-zero (graceful weaviate), but must not hang/prompt and must produce output
    assert r2.exit_code in (0, 1)
    assert "Weaviate" in (r2.output or "") or "finops" in (r2.output or "") or "error" in (r2.output or "").lower() or r2.exception is not None
    # multi-run --help exercises the recent --target modal flags path
    r3 = runner.invoke(scenario_app, ["multi-run", "--help"])
    assert r3.exit_code == 0
    assert "--target" in r3.output or "modal" in r3.output.lower()
