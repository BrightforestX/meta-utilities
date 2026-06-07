"""Tests for batch orchestration engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from batch_orchestrator.engine import BatchEngine
from batch_orchestrator.models import DefaultsConfig, Job, Manifest
from batch_orchestrator.store import BatchStore


@pytest.fixture
def store(tmp_path: Path) -> BatchStore:
    return BatchStore(db_path=tmp_path / "test.db")


@pytest.fixture
def engine(store: BatchStore) -> BatchEngine:
    return BatchEngine(store=store)


@pytest.fixture
def simple_manifest() -> Manifest:
    return Manifest(
        output_dir="./out",
        concurrency=2,
        defaults=DefaultsConfig(provider="openai", mode="realtime"),
        jobs=[
            Job(id="first", type="inference", prompt="Say hello"),
            Job(
                id="second",
                type="inference",
                prompt="Summarize: {{dependency}}",
                depends_on=["first"],
            ),
        ],
    )


@pytest.mark.asyncio
async def test_engine_runs_dependency_chain(
    engine: BatchEngine, store: BatchStore, simple_manifest: Manifest, tmp_path: Path
):
    output_dir = tmp_path / "results"
    manifest_path = tmp_path / "jobs.yaml"
    manifest_path.write_text("jobs: []", encoding="utf-8")

    run_id = engine.start_run(
        simple_manifest, str(manifest_path), str(output_dir)
    )

    mock_inference = AsyncMock(
        side_effect=[
            {"text": "Hello world", "report": "Hello world", "error": None, "usage": {}},
            {"text": "Summary done", "report": "Summary done", "error": None, "usage": {}},
        ]
    )

    with patch(
        "batch_orchestrator.engine.run_inference", mock_inference
    ):
        status = await engine.run(run_id, manifest_dir=tmp_path)

    assert status["status"] == "succeeded"
    jobs = {j["job_id"]: j for j in status["jobs"]}
    assert jobs["first"]["status"] == "succeeded"
    assert jobs["second"]["status"] == "succeeded"
    assert (output_dir / "first.json").exists()
    assert (output_dir / "second.json").exists()


@pytest.mark.asyncio
async def test_engine_submits_batch_without_wait(
    engine: BatchEngine, store: BatchStore, tmp_path: Path
):
    manifest = Manifest(
        output_dir=str(tmp_path / "out"),
        jobs=[
            Job(
                id="batch-job",
                type="inference",
                mode="batch",
                provider="openai",
                prompt="Batch prompt",
            )
        ],
    )
    manifest_path = tmp_path / "jobs.yaml"
    manifest_path.write_text("x", encoding="utf-8")
    run_id = engine.start_run(manifest, str(manifest_path), manifest.output_dir)

    mock_adapter = AsyncMock()
    mock_adapter.submit = AsyncMock(return_value="batch-123")
    mock_adapter.poll = AsyncMock(
        return_value=type("P", (), {"status": "running", "completed": 0, "total": 1})()
    )

    with patch(
        "batch_orchestrator.engine.get_batch_adapter", return_value=mock_adapter
    ):
        status = await engine.run(run_id, wait_for_batch=False, manifest_dir=tmp_path)

    assert status["status"] == "waiting_batch"
    job = status["jobs"][0]
    assert job["status"] == "submitted_batch"
    assert job["provider_batch_id"] == "batch-123"


@pytest.mark.asyncio
async def test_engine_resume_skips_succeeded(
    engine: BatchEngine, store: BatchStore, simple_manifest: Manifest, tmp_path: Path
):
    output_dir = tmp_path / "results"
    manifest_path = tmp_path / "jobs.yaml"
    manifest_path.write_text("x", encoding="utf-8")
    run_id = engine.start_run(
        simple_manifest, str(manifest_path), str(output_dir)
    )

    store.update_job(run_id, "first", status="succeeded", result_path=str(output_dir / "first.json"))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "first.json").write_text(
        '{"text": "cached", "report": "cached"}', encoding="utf-8"
    )

    mock_inference = AsyncMock(
        return_value={"text": "done", "report": "done", "error": None, "usage": {}}
    )

    with patch("batch_orchestrator.engine.run_inference", mock_inference):
        status = await engine.run(run_id, manifest_dir=tmp_path)

    assert mock_inference.call_count == 1
    assert status["status"] == "succeeded"


@pytest.mark.asyncio
async def test_pipeline_reflection_loops_max_2(
    engine: BatchEngine, store: BatchStore, tmp_path: Path
):
    """Verify reflection re-roll bounded to max 2 (per Task 2.1)."""
    from batch_orchestrator.models import DefaultsConfig, Job, Manifest

    manifest = Manifest(
        output_dir=str(tmp_path / "out"),
        defaults=DefaultsConfig(provider="openai", mode="realtime"),
        jobs=[
            Job(
                id="pipe-job",
                type="deep_research_pipeline",
                query="test ratchet reflection loop",
                depth="simple",
                max_subagents=1,
            )
        ],
    )
    manifest_path = tmp_path / "jobs.yaml"
    manifest_path.write_text("x", encoding="utf-8")
    run_id = engine.start_run(manifest, str(manifest_path), manifest.output_dir)

    # Simulate: triage, instruction, 1 fanout report, synth, then 2x reflection NOT complete + 1 final complete?
    # But to bound, count reflection calls.
    call_log: list[str] = []

    async def mock_run_inference(prompt: str, *a, **k):
        call_log.append("inference:" + (prompt[:40] if prompt else ""))
        if "triage" in prompt.lower() or "classification" in prompt.lower():
            return {"text": "## Classification\nsimple\n\n## Research Brief\nDo X", "report": "", "error": None, "usage": {}}
        if "numbered list" in prompt.lower() or "sub-queries" in prompt.lower():
            return {"text": "1. Subtask one", "report": "", "error": None, "usage": {}}
        if "merge the following sub-reports" in prompt.lower():
            return {"text": "## Synth\nData here.", "report": "", "error": None, "usage": {}}
        if "review this research draft" in prompt.lower() or "gaps" in prompt.lower():
            # first two reflections: incomplete; third would not be called due to max 2
            call_log.append("REFLECTION_CALL")
            if call_log.count("REFLECTION_CALL") >= 2:
                return {"text": "COMPLETE", "report": "", "error": None, "usage": {}}
            return {"text": "Gap: missing foo. - Follow up on bar", "report": "", "error": None, "usage": {}}
        return {"text": "ok", "report": "ok", "error": None, "usage": {}}

    async def mock_run_deep(subq: str, *a, **k):
        call_log.append("deep:" + subq[:30])
        return {"report": "sub report with https://cite [1]", "text": "", "error": None, "citations": [], "usage": {}}

    with patch("batch_orchestrator.engine.run_inference", mock_run_inference), \
         patch("batch_orchestrator.engine.run_deep_research", mock_run_deep):
        status = await engine.run(run_id, manifest_dir=tmp_path)

    refl_count = call_log.count("REFLECTION_CALL")
    assert refl_count <= 2, f"reflection should loop at most 2 times, got {refl_count}"
    assert status["status"] == "succeeded"
