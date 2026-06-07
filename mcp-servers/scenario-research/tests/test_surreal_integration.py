from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from scenario_research.linkml_surreal import (
    ScenarioSurrealWriter,
    fetch_run_artifacts,
    query_run_attributions,
)
from scenario_research.models import ScenarioRun


def _surreal_env_ready() -> bool:
    return bool(os.environ.get("SURREAL_URL"))


@pytest.mark.integration
def test_surreal_roundtrip_write_and_query(tmp_path):
    if not _surreal_env_ready():
        pytest.skip("SURREAL_URL not set; skipping live Surreal integration test")

    trace_json = tmp_path / "trace.json"
    trace_json.write_text(
        json.dumps(
            {
                "trace": {
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "pdr_attributions": [
                        {"period": 1, "delta_util": 0.02, "invest_cost": 3.5, "attribution_level": "policy"},
                        {"period": 2, "delta_util": -0.01, "invest_cost": 2.0, "attribution_level": "ops"},
                    ],
                }
            }
        )
    )
    run_id = f"it-surreal-{int(time.time() * 1000)}"
    run = ScenarioRun(
        run_id=run_id,
        scenario="oteemo_billable",
        n_agents=4,
        n_steps=2,
        seed=42,
        db_path=str(trace_json),
        status="succeeded",
        config_snapshot={"policy": {"raja": {"axiom_invest_frac": 0.22}}},
    )
    writer = ScenarioSurrealWriter()
    if writer.surreal is None or not writer.surreal.is_healthy():
        pytest.skip("Surreal not healthy in test environment")

    res = writer.store_scenario_run(run, trace_id="it-trace", ontology_ref="agents")
    assert res["backend"] == "surreal"
    assert res["records_written"] >= 4

    rows = fetch_run_artifacts(run_id, prefer_surreal=True)
    assert rows["found"] is True
    assert rows["backend"] == "surreal"
    assert rows["scenario_trace"]["run_id"] == run_id
    assert len(rows["attributions"]) == 2

    attrs = query_run_attributions(
        run_id,
        period_min=1,
        period_max=2,
        aggregate="sum_cost_by_level",
        prefer_surreal=True,
    )
    assert attrs["found"] is True
    assert attrs["count"] == 2
    assert attrs["aggregate"]["kind"] == "sum_cost_by_level"
