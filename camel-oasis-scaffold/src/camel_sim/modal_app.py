"""Modal entrypoint for the CAMEL multi-scenario service.

Run with:
    modal run src.camel_sim.modal_app --scenario-file examples/multi_scenarios.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config.models import MODEL_REGISTRY, default_server_urls
from .config.scenarios import load_scenario_configs
from .inference.sglang_server import make_sglang_server
from .results.collector import write_results
from .simulation.runner import run_scenario

try:
    import modal
except Exception:  # pragma: no cover - optional deployment dependency
    modal = None


if modal is not None:
    app = modal.App("camel-sim")
    _SERVER_CLASSES = [make_sglang_server(app, spec) for spec in MODEL_REGISTRY]
    _results_vol = modal.Volume.from_name("sim-results", create_if_missing=True)

    @app.function(
        cpu=2,
        memory=4096,
        timeout=900,
        retries=modal.Retries(max_retries=2, backoff_coefficient=2.0),
    )
    def run_scenario_remote(
        config: dict[str, Any],
        server_urls: dict[str, str],
        execution_mode: str = "local",
    ) -> dict[str, Any]:
        """Run one scenario inside Modal CPU workers."""
        return run_scenario(config, server_urls=server_urls, execution_mode=execution_mode)

    @app.function(volumes={"/results": _results_vol})
    def write_results_remote(
        results: list[dict[str, Any]],
        run_id: str = "",
        output_format: str = "parquet",
    ) -> dict[str, str]:
        """Write Modal results to the mounted persistent volume."""
        paths = write_results(
            results,
            Path("/results"),
            run_id=run_id or None,
            output_format=output_format,  # type: ignore[arg-type]
        )
        _results_vol.commit()
        return paths

    @app.local_entrypoint()
    def main(
        scenario_file: str = "examples/multi_scenarios.json",
        output_format: str = "parquet",
        execution_mode: str = "local",
        server_urls_json: str = "",
    ) -> None:
        scenario_configs = [cfg.model_dump() for cfg in load_scenario_configs(Path(scenario_file))]
        if execution_mode == "camel" and not server_urls_json:
            raise ValueError(
                "Modal CAMEL mode requires server_urls_json with reachable SGLang /v1 URLs. "
                "Do not use localhost URLs from separate CPU workers."
            )
        server_urls = json.loads(server_urls_json) if server_urls_json else default_server_urls()
        print(f"Dispatching {len(scenario_configs)} scenarios to Modal...")
        start = time.time()
        results = list(
            run_scenario_remote.map(
                scenario_configs,
                kwargs=[
                    {
                        "server_urls": server_urls,
                        "execution_mode": execution_mode,
                    }
                ]
                * len(scenario_configs),
            )
        )
        elapsed = time.time() - start
        print(f"Completed {len(results)} simulations in {elapsed:.1f}s")
        print(write_results_remote.remote(results, output_format=output_format))

else:
    app = None

    def main(*_: Any, **__: Any) -> None:
        raise RuntimeError(
            "Modal deployment requires installing the scaffold with the 'modal' extra."
        )
