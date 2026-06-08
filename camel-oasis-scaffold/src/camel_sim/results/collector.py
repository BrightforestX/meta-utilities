"""Result aggregation and artifact writing for simulation batches."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Literal


OutputFormat = Literal["json", "jsonl", "parquet"]


def flatten_event_rows(
    results: list[dict[str, Any]],
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    """Flatten simulation event logs into row dictionaries."""
    rows: list[dict[str, Any]] = []
    for sim in results:
        for event in sim.get("event_log", []):
            rows.append(
                {
                    "run_id": run_id,
                    "scenario_id": sim.get("scenario_id"),
                    "tick": event.get("tick"),
                    "action": event.get("action"),
                    "agent": event.get("agent"),
                    **{
                        key: value
                        for key, value in event.items()
                        if key not in {"tick", "action", "agent"}
                    },
                }
            )
    return rows


def summary_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one summary row per simulation result."""
    return [
        {
            "scenario_id": result.get("scenario_id"),
            "scenario_name": result.get("scenario_name"),
            "ticks_run": result.get("ticks_run"),
            "execution_mode": result.get("execution_mode"),
            **result.get("action_counts", {}),
        }
        for result in results
    ]


def write_results(
    results: list[dict[str, Any]],
    output_dir: Path,
    *,
    run_id: str | None = None,
    output_format: OutputFormat = "jsonl",
) -> dict[str, str]:
    """Persist simulation results and return created artifact paths."""
    run_id = run_id or str(uuid.uuid4())[:8]
    output_dir.mkdir(parents=True, exist_ok=True)

    events = flatten_event_rows(results, run_id=run_id)
    summaries = summary_rows(results)

    if output_format == "json":
        result_path = output_dir / f"{run_id}_results.json"
        result_path.write_text(json.dumps(results, indent=2) + "\n")
        summary_path = output_dir / f"{run_id}_summary.json"
        summary_path.write_text(json.dumps(summaries, indent=2) + "\n")
        return {"results": str(result_path), "summary": str(summary_path)}

    if output_format == "jsonl":
        events_path = output_dir / f"{run_id}_events.jsonl"
        events_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in events)
        )
        summary_path = output_dir / f"{run_id}_summary.json"
        summary_path.write_text(json.dumps(summaries, indent=2) + "\n")
        return {"events": str(events_path), "summary": str(summary_path)}

    if output_format == "parquet":
        try:
            import pandas as pd
        except Exception as exc:  # pragma: no cover - optional local dependency path
            raise RuntimeError("Parquet output requires pandas and a parquet engine") from exc
        events_path = output_dir / f"{run_id}_events.parquet"
        summary_path = output_dir / f"{run_id}_summary.parquet"
        pd.DataFrame(events).to_parquet(events_path, index=False)
        pd.DataFrame(summaries).to_parquet(summary_path, index=False)
        return {"events": str(events_path), "summary": str(summary_path)}

    raise ValueError(f"unsupported output format {output_format!r}")
