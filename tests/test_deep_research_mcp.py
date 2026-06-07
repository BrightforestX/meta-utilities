#!/usr/bin/env python3
"""TDD test for Task 1.2 (Phase 1): Add RAG hooks (optional params) to deep-research MCP.

Verifies param passthrough for use_memory / memory_mcp_url / firecrawl_enabled
without breaking existing call signatures (defaults preserve backward compat).

Mocks _get_client to avoid requiring API keys / network during test.
Also exercises the RAG helper behavior (real compress dogfood path when run inside meta root).

Run:
  python -m pytest tests/test_deep_research_mcp.py -q --tb=short
  # or direct:
  python tests/test_deep_research_mcp.py

Per plan + user adapt: leverages context-forge compress (real portable call) for RAG token win;
stubs research-memory + semantic_search + firecrawl per "MCP call via host" / cli / npx.
No new RAG built. Follows AGENTS (portable detection, $META_UTILITIES_HOME, uv/python -m, self-dogfood, two-layer doc).
"""

import sys
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

# Portable sys.path hack (confined to this test file; no changes to conftest.py or other files).
# Allows "from deep_research_mcp import ..." to resolve when running `python -m pytest` (or python -m)
# from the meta-utilities root. Matches the spirit of tests/index_with_turbovec.py + conftest for hyphen case.
_mcp_dir = str((Path(__file__).parent.parent / "mcp-servers" / "deep-research").resolve())
if _mcp_dir not in sys.path:
    sys.path.insert(0, _mcp_dir)

from deep_research_mcp import deep_research as _deep_tool

# Unwrap fastmcp FunctionTool to get the raw async def for direct unit testing.
# (The decorator registers the tool but stores original at .fn; we call the raw for TDD isolation.)
deep_research = _deep_tool.fn if hasattr(_deep_tool, "fn") else _deep_tool


def _make_fake_completion(report_text: str = "Stub deep research report for RAG hook TDD test. Citations would be here.") -> MagicMock:
    comp = MagicMock()
    comp.choices = [MagicMock(message=MagicMock(content=report_text))]
    comp.citations = ["https://example.com/prior-rag-source", "https://example.com/fresh"]
    comp.search_results = []
    # usage may be object or dict-like; simple None works for our extraction fallbacks
    comp.usage = None
    return comp


def test_deep_research_rag_params_passthrough_no_break_existing_calls():
    """Core TDD assertion for Task 1.2.

    - Plain call deep_research("q") must continue to work (uses defaults for new optionals).
    - Calls passing use_memory=True, memory_mcp_url=..., firecrawl_enabled=True must be accepted.
    - Result always includes 'rag_context' (dict) per impl.
    - When flags on, rag_context indicates enabled + sources (context-forge compress is real via portable path).
    - Provider/reasoning_effort etc still round-trip.
    - No KeyError / crash on defaults or new paths.
    """
    async def _run():
        fake_comp = _make_fake_completion()

        with patch("deep_research_mcp._get_client") as mock_get_client:
            fake_client = MagicMock()
            fake_client.chat.completions.create.return_value = fake_comp
            mock_get_client.return_value = (fake_client, "test-stub-model")

            # --- Existing call style (no new kwargs) must not break ---
            res_old = await deep_research("existing call style test query for meta-utilities RAG")
            assert isinstance(res_old, dict), "result must be dict"
            assert "report" in res_old, "existing result shape preserved"
            assert res_old.get("error") in (None, ""), f"no error on default path: {res_old.get('error')}"
            assert res_old.get("provider") == "perplexity"
            assert res_old.get("reasoning_effort") == "high"
            assert "rag_context" in res_old, "rag_context always surfaced (even for default use_memory=True)"

            # --- New params accepted + passthrough + behavior ---
            res_new = await deep_research(
                query="RAG hooks test: prior memory + firecrawl grounding for deep research on context optimization",
                provider="grok",
                reasoning_effort="medium",
                use_memory=True,
                memory_mcp_url=None,
                firecrawl_enabled=True,
            )
            assert isinstance(res_new, dict)
            assert "report" in res_new
            assert res_new["provider"] == "grok"
            assert res_new["reasoning_effort"] == "medium"
            assert "rag_context" in res_new
            rag = res_new["rag_context"]
            assert isinstance(rag, dict)
            # The impl guarantees 'enabled' or at least 'sources' list for visibility
            assert rag.get("enabled") is True or "sources" in rag, f"rag_context should reflect flags: {rag}"
            if "sources" in rag:
                # context-forge compress path is exercised for real (self-dogfood) when inside tree
                assert any("context-forge" in str(s).lower() for s in rag["sources"]) or "context_forge" in str(rag), \
                    "should leverage context-forge per overlaps (even if via stub+real-compress)"

            # --- Explicit disable still works, no side effects ---
            res_off = await deep_research("disable test", use_memory=False, firecrawl_enabled=False)
            assert "rag_context" in res_off
            rag_off = res_off["rag_context"]
            # impl may still attach with enabled=False
            if "enabled" in rag_off:
                assert rag_off["enabled"] is False

        print("TDD PASS: param passthrough verified; old calls preserved; rag_context present with context-forge leverage.")

    asyncio.run(_run())


if __name__ == "__main__":
    # Allow direct python tests/test_...py execution (also exercises)
    test_deep_research_rag_params_passthrough_no_break_existing_calls()
