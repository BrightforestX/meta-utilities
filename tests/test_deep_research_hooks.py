"""TDD for deep-research MCP param passthrough + hooks (Phase 1/3)."""

import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-servers" / "deep-research"))

from deep_research_mcp import deep_research as _deep_tool  # type: ignore

# Unwrap (matches pattern in test_deep_research_mcp.py and research-memory test fix)
deep_research = _deep_tool.fn if hasattr(_deep_tool, "fn") else _deep_tool


def test_params_default_and_passthrough_no_break():
    # Call with defaults (no keys -> error but param path exercised without crash)
    res = asyncio.run(deep_research("test query for hooks", provider="grok"))
    assert "error" in res or "report" in res  # either auth fail or success path
    # Call with hooks
    res2 = asyncio.run(
        deep_research(
            "test with memory",
            use_memory=True,
            firecrawl_enabled=True,
        )
    )
    assert "rag_context" in res2
    assert "firecrawl" in res2
    rag = res2.get("rag_context", {})
    srcs = rag.get("sources", [])
    assert any("context-forge" in str(s).lower() for s in srcs) or "context_forge" in str(rag) or "context_forge_compressed" in rag, \
        f"should leverage context-forge per overlaps (even if via stub+real-compress); got {rag}"
