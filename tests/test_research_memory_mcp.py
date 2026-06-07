"""Basic smoke + TDD tests for research-memory MCP (Phase 1 Task 1.1).

Uses direct calls to the pure impl functions (store_artifact, search_..., etc) with
monkeypatched CONTEXT_HOME for isolation. Does not require a running MCP host or
full stdio transport.

Covers:
- file-only store + keyword search fallback (always works)
- list_artifacts
- citation graph resolve (internal ids)
- vector path is best-effort (skipped or graceful if no weaviate/turbovec in env)

Run: pytest tests/test_research_memory_mcp.py -q --tb=line
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest


# Ensure we can import the mcp module directly (similar to turbovec test shim pattern)
TESTS_DIR = Path(__file__).parent.resolve()
MCP_DIR = TESTS_DIR.parent / "mcp-servers" / "research-memory"
if str(MCP_DIR) not in os.sys.path:
    os.sys.path.insert(0, str(MCP_DIR))

from research_memory_mcp import (  # type: ignore
    _store_artifact_impl as store_artifact,
    _search_prior_reports_impl as search_prior_reports,
    _retrieve_by_citation_graph_impl as retrieve_by_citation_graph,
    _list_artifacts_impl as list_artifacts,
    get_research_home,
    _ensure_dirs,
)

def _unwrap_tool(t):
    """Unwrap fastmcp FunctionTool to raw fn for direct/test calls (the @mcp.tool replaces name with tool obj)."""
    return getattr(t, "fn", t)

store_artifact = _unwrap_tool(store_artifact)
search_prior_reports = _unwrap_tool(search_prior_reports)
retrieve_by_citation_graph = _unwrap_tool(retrieve_by_citation_graph)
list_artifacts = _unwrap_tool(list_artifacts)
# get_research_home and _ensure_dirs are plain functions, no unwrap needed


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _tmp_context_home(monkeypatch, tmp_path):
    """Isolate all file ops to a temp CONTEXT_HOME for every test."""
    monkeypatch.setenv("CONTEXT_HOME", str(tmp_path / "ctx"))
    # reset any cached home
    import research_memory_mcp as m

    # force re-resolve
    # (get_research_home reads env fresh each time)
    yield
    # cleanup not strictly needed; tmp_path auto


def test_get_research_home_uses_context_home(tmp_path):
    os.environ["CONTEXT_HOME"] = str(tmp_path / "myctx")
    home = get_research_home()
    assert "research" in str(home)
    assert home.name == "research"
    assert str(tmp_path) in str(home)


def test_store_artifact_writes_para_files_and_returns_id():
    res = _run(
        store_artifact(
            "This is a test research report about turbovec compression for dogfood. "
            "It references prior work.",
            tags=["test", "dogfood", "phase1"],
            citations=["https://example.com/prior", "abc123def456"],  # second is fake internal id
            metadata={"source": "test"},
        )
    )
    assert res["stored"] is True
    assert "id" in res and len(res["id"]) == 12
    assert res["indexed_backend"] in ("none", "weaviate", "turbovec")
    jpath = Path(res["path"])
    mpath = Path(res["md_path"])
    assert jpath.exists()
    assert mpath.exists()
    data = json.loads(jpath.read_text(encoding="utf-8"))
    assert data["id"] == res["id"]
    assert "test" in data["tags"]
    assert "compression" in data["content"].lower()


def test_search_prior_reports_keyword_finds_stored():
    _run(store_artifact("Alpha report on Weaviate BYOV integration and real embedder.", tags=["weaviate"]))
    _run(store_artifact("Beta report on token compression with tiktoken in context-forge.", tags=["compression"]))
    hits = _run(search_prior_reports("weaviate embedder", top_k=5, use_vector=False))
    assert len(hits) >= 1
    assert any("weaviate" in (h.get("snippet", "") + " ".join(h.get("tags", []))).lower() for h in hits)


def test_list_artifacts_returns_recent():
    _run(store_artifact("One", tags=["a"]))
    _run(store_artifact("Two", tags=["b"]))
    lst = _run(list_artifacts(limit=10))
    assert lst["count"] >= 2
    assert all("id" in a and "tags" in a for a in lst["artifacts"])


def test_retrieve_by_citation_graph_resolves_internal_and_external():
    # First store a target that will be cited
    target = _run(store_artifact("Target prior artifact for graph test.", tags=["target"]))
    tid = target["id"]
    # Now store one that cites it (by id) + an external url
    citer = _run(
        store_artifact(
            "This cites the target and an external source.",
            citations=[tid, "https://external.example.com/paper"],
        )
    )
    graph_res = _run(retrieve_by_citation_graph(citer["id"]))
    assert "artifact" in graph_res
    g = graph_res["graph"]
    assert any(n["id"] == tid for n in g["nodes"])
    assert any(e["to"] == tid for e in g["edges"])
    assert any(e["to"] == "https://external.example.com/paper" for e in g["edges"])
    assert g["resolved"] >= 1


def test_search_prior_reports_use_vector_graceful_when_no_backend():
    # Even if no weaviate/turbovec in the test env, should not crash (falls to keyword)
    _run(store_artifact("Gamma vector test artifact about sentence transformers fallback.", tags=["vector"]))
    hits = _run(search_prior_reports("sentence transformers fallback", top_k=3, use_vector=True))
    # may be 0 or more depending on backend presence, but must be list not error
    assert isinstance(hits, list)
