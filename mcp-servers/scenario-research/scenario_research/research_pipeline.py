"""End-to-end ask pipeline producing durable report artifacts."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analytics import estimate_cost_report, fit_models_from_trace, load_trace_payload
from .linkml_surreal import persist_run_artifacts
from .models import ResearchReport
from .optimization.replay import replay_policy as replay_policy_robustness
from .scaffold_adapter import execute_scenario


def _report_dir() -> Path:
    import os

    configured = os.environ.get("SCENARIO_RESEARCH_REPORT_DIR")
    if configured:
        p = Path(configured)
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = Path(__file__).resolve().parents[1] / ".context" / "scenario-research-reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _choose_scenario(question: str) -> str:
    q = (question or "").lower()
    # Expandable router; currently anchored to shipped local scenario.
    if any(k in q for k in ("oteemo", "billable", "utilization", "finops", "delivery")):
        return "oteemo_billable"
    return "oteemo_billable"


def _default_steps(scenario: str) -> int:
    try:
        from .agent_compiler import compile_scenario_spec

        spec = compile_scenario_spec(scenario)
        raw = ((spec.get("parameters", {}) or {}).get("n_steps", {}) or {}).get("default")
        if raw is not None:
            return int(raw)
    except Exception:
        pass
    return 8


def _report_id(question: str, scenario: str, seed: int | None) -> str:
    src = f"{scenario}|{seed}|{question}".encode("utf-8")
    digest = hashlib.sha1(src).hexdigest()[:12]
    return f"report-{digest}"


def _render_report_markdown(
    *,
    report_id: str,
    question: str,
    scenario: str,
    run: dict[str, Any],
    fits: list[dict[str, Any]],
    cost: dict[str, Any],
    replay: dict[str, Any],
    persistence: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append(f"# Scenario Research Report `{report_id}`")
    lines.append("")
    lines.append(f"- Question: {question}")
    lines.append(f"- Scenario: {scenario}")
    lines.append(f"- Run ID: {run.get('run_id')}")
    lines.append(f"- Status: {run.get('status')}")
    lines.append(f"- Seed: {run.get('seed')}")
    lines.append("")
    lines.append("## Cost telemetry")
    lines.append("")
    lines.append(f"- Local tokens: {cost.get('local_tokens')}")
    lines.append(f"- API tokens: {cost.get('api_tokens')}")
    lines.append(f"- Estimated USD: {cost.get('estimated_cost_usd')}")
    lines.append(f"- Local model: {cost.get('local_model')}")
    lines.append(f"- API model: {cost.get('api_model')}")
    lines.append("")
    lines.append("## Model fits")
    lines.append("")
    if not fits:
        lines.append("- No fit artifacts available.")
    for fit in fits:
        lines.append(f"- `{fit.get('model')}` metrics: `{fit.get('metrics')}`")
    lines.append("")
    lines.append("## Policy replay robustness")
    lines.append("")
    lines.append(f"- Status: {replay.get('status')}")
    lines.append(f"- Robustness delta: {replay.get('robustness_delta')}")
    lines.append(f"- Uncertainty: {replay.get('uncertainty')}")
    lines.append("")
    lines.append("## Persistence")
    lines.append("")
    lines.append(f"- Backend: {persistence.get('backend')}")
    lines.append(f"- Records written: {persistence.get('records_written')}")
    if persistence.get("fallback_path"):
        lines.append(f"- Fallback payload: `{persistence.get('fallback_path')}`")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


async def build_research_report(
    *,
    question: str,
    seed: int | None = 42,
    scenario: str | None = None,
    n_steps: int | None = None,
    ontology: str | None = None,
    trace_id: str | None = None,
) -> tuple[ResearchReport, dict[str, Any]]:
    """Run ask pipeline and return report + execution metadata."""
    chosen = scenario or _choose_scenario(question)
    steps = n_steps if n_steps is not None else _default_steps(chosen)
    run = await execute_scenario(chosen, n_steps=steps, seed=seed)
    persistence = persist_run_artifacts(run, trace_id=trace_id, ontology_ref=ontology)
    trace = load_trace_payload(run.db_path)
    fits = fit_models_from_trace(trace)
    cost = estimate_cost_report(run)
    replay = replay_policy_robustness(
        (run.config_snapshot or {}).get("policy", {}),
        scenario=chosen,
        seed=seed or 42,
        periods=min(max(int(steps), 1), 24),
    )

    rid = _report_id(question, chosen, seed)
    report_path = _report_dir() / f"{rid}.md"
    markdown = _render_report_markdown(
        report_id=rid,
        question=question,
        scenario=chosen,
        run=run.model_dump(),
        fits=[f.model_dump() for f in fits],
        cost=cost.model_dump(),
        replay=replay,
        persistence=persistence,
    )
    report_path.write_text(markdown)

    report = ResearchReport(
        report_id=rid,
        question=question,
        report_path=str(report_path),
        figures=[],
        fits=fits,
        cost_report=cost,
        scenario_runs=[run],
        created_at=datetime.now(timezone.utc).isoformat(),
        seed=seed,
    )
    meta = {
        "scenario": chosen,
        "steps": steps,
        "persistence": persistence,
        "replay": replay,
        "report_path": str(report_path),
    }
    return report, meta
