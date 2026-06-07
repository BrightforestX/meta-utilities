"""Tests for batch orchestrator models."""

from pathlib import Path

import pytest

from batch_orchestrator.models import (
    Job,
    Manifest,
    DefaultsConfig,
    expand_file_refs,
    load_manifest,
    topological_order,
)


def test_manifest_validates_dag():
    manifest = Manifest(
        jobs=[
            Job(id="a", type="inference", prompt="hello"),
            Job(id="b", type="inference", prompt="world", depends_on=["a"]),
        ]
    )
    assert len(manifest.jobs) == 2


def test_manifest_rejects_unknown_dependency():
    with pytest.raises(ValueError, match="unknown job"):
        Manifest(
            jobs=[
                Job(id="a", type="inference", prompt="x", depends_on=["missing"]),
            ]
        )


def test_manifest_rejects_cycle():
    with pytest.raises(ValueError, match="cycle"):
        Manifest(
            jobs=[
                Job(id="a", type="inference", prompt="a", depends_on=["b"]),
                Job(id="b", type="inference", prompt="b", depends_on=["a"]),
            ]
        )


def test_deep_research_requires_query():
    with pytest.raises(ValueError, match="requires 'query'"):
        Job(id="bad", type="deep_research")


def test_inference_requires_prompt():
    with pytest.raises(ValueError, match="requires 'prompt'"):
        Job(id="bad", type="inference")


def test_topological_order():
    jobs = [
        Job(id="c", type="inference", prompt="c", depends_on=["b"]),
        Job(id="a", type="inference", prompt="a"),
        Job(id="b", type="inference", prompt="b", depends_on=["a"]),
    ]
    order = topological_order(jobs)
    assert order.index("a") < order.index("b") < order.index("c")


def test_expand_file_refs(tmp_path: Path):
    f = tmp_path / "note.md"
    f.write_text("hello from file", encoding="utf-8")
    result = expand_file_refs("Prefix: {{file:note.md}}", tmp_path)
    assert "hello from file" in result


def test_load_example_manifest():
    example = (
        Path(__file__).resolve().parents[3]
        / "templates"
        / "batch"
        / "jobs.example.yaml"
    )
    if not example.exists():
        pytest.skip("example manifest not found")
    manifest = load_manifest(example)
    assert len(manifest.jobs) >= 3
    assert manifest.defaults.provider == "perplexity"


def test_resolved_defaults():
    job = Job(id="j", type="inference", prompt="test", provider="grok", mode="batch")
    defaults = DefaultsConfig()
    assert job.resolved_provider(defaults) == "grok"
    assert job.resolved_mode(defaults) == "batch"
