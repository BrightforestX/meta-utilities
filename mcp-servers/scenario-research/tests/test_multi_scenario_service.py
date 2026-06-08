from __future__ import annotations

import json
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
