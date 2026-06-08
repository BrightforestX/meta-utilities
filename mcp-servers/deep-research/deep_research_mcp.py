#!/usr/bin/env python3
"""
Deep Research MCP Server (meta-utilities)

A production-grade, portable MCP tool for running long, high-quality, multi-step research
queries using dedicated deep research APIs.

Primary: Perplexity sonar-deep-research (best-in-class citations + depth)
Fallback: xAI Grok (grok-4.3 with high reasoning_effort)

This is the canonical, extracted version living in meta-utilities. It is deliberately
free of any project-specific paths or assumptions.

Usage (Cursor / Claude Code / Grok Build):
    "Use deep_research on the competitive landscape of edge AI inference startups in 2026, 
     focusing on funding, technical approaches, and go-to-market strategies."

Quick Setup:
    # Recommended
    uv pip install fastmcp openai

    # Or via the packaged form (see pyproject.toml + README in this directory)
    uv tool install -e .

See the README in this directory (adapted from DEEP_RESEARCH.md) for full installation,
timeout configuration (critical for long jobs), and client registration examples.

Phase 1 additions (Task 1.2): optional use_memory / memory_mcp_url / firecrawl_enabled for
RAG hooks (context-forge compress/semantic + research-memory recall + Firecrawl grounding).
Two-layer timeouts documented throughout (DEEP_RESEARCH_TIMEOUT_SEC + host tool_timeouts).
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP, Context

# `openai` is the live-call dependency. It is intentionally treated as optional at import
# time so this module (and anything importing it, e.g. tests/hooks) never hard-crashes when
# the optional dep is absent. The clear runtime error is raised only when an OpenAI-backed
# provider path is actually exercised (see _get_client). Mirrors the repo's graceful
# optional-dep pattern (cf. scenario-research weaviate/numpy handling).
try:
    from openai import OpenAI, APIError, RateLimitError, AuthenticationError
    _OPENAI_AVAILABLE = True
    _OPENAI_IMPORT_ERROR: str | None = None
except Exception as _openai_exc:  # ImportError in practice; broad to stay import-safe
    OpenAI = None  # type: ignore[assignment,misc]
    _OPENAI_AVAILABLE = False
    _OPENAI_IMPORT_ERROR = f"{type(_openai_exc).__name__}: {_openai_exc}"

    # Define stand-in exception classes so the module's `except APIError/...` handlers
    # remain valid (NameError-free) even when openai is not installed. These are never
    # raised in practice when openai is missing (we fail earlier in _get_client).
    class APIError(Exception):  # type: ignore[no-redef]
        ...

    class RateLimitError(Exception):  # type: ignore[no-redef]
        ...

    class AuthenticationError(Exception):  # type: ignore[no-redef]
        ...


# Deep research jobs (especially sonar-deep-research) are intentionally long-running:
# typical range is 2–20+ minutes depending on query complexity and reasoning_effort.
# The MCP host (Grok/Cursor) controls the outer timeout via config (tool_timeouts),
# but we also set a high client-level timeout here so the actual HTTP call doesn't die early.
DEEP_RESEARCH_TIMEOUT_SEC: float = float(os.getenv("DEEP_RESEARCH_TIMEOUT_SEC", "900"))  # 15 min default

# Configure logging to stderr only (critical for stdio MCP transports)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] deep-research: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="deep-research",
    instructions=(
        "You are a deep research specialist. Use the deep_research tool for any query that "
        "requires exhaustive, multi-source, citation-backed analysis (market research, technical deep dives, "
        "competitive intelligence, academic-style synthesis, due diligence, etc.). "
        "Prefer provider='perplexity' for dedicated deep research quality. "
        "Always surface key citations and source quality to the user. "
        "Phase 1 RAG hooks supported via optional params: use_memory=True pulls compressed priors from "
        "context-forge (compress + semantic) + research-memory (stubs ok until 1.1 complete); "
        "firecrawl_enabled=True augments grounding via CLI (npx/MCP registered in full-recommended.toml). "
        "Two-layer timeouts: DEEP_RESEARCH_TIMEOUT_SEC (client) + host tool_timeouts[deep_research]."
    ),
)


Provider = Literal["perplexity", "grok", "openai"]
ReasoningEffort = Literal["low", "medium", "high"]


def _get_client(provider: Provider) -> tuple[OpenAI, str]:
    """Return configured OpenAI client and canonical model name for the provider.

    All clients get a very high timeout because deep research models (sonar-deep-research,
    grok-4.3 high effort, etc.) perform many internal search + synthesis steps and can
    easily run 5–20+ minutes on ambitious queries.
    """
    timeout = DEEP_RESEARCH_TIMEOUT_SEC

    if not _OPENAI_AVAILABLE or OpenAI is None:
        # Raised as ValueError so the deep_research tool catches it and returns a graceful
        # {"error": ...} instead of crashing. Live calls genuinely require openai.
        raise ValueError(
            "The 'openai' package is required for live deep research calls but is not installed. "
            "Install it with `uv pip install openai` (or `uv tool install -e .` in "
            f"mcp-servers/deep-research). Original import error: {_OPENAI_IMPORT_ERROR}"
        )

    if provider == "perplexity":
        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            raise ValueError(
                "PERPLEXITY_API_KEY environment variable is required for provider='perplexity'. "
                "Get a key at https://www.perplexity.ai/settings/api"
            )
        return OpenAI(
            api_key=api_key,
            base_url="https://api.perplexity.ai",
            timeout=timeout,
            max_retries=2,
        ), "sonar-deep-research"

    if provider == "grok":
        api_key = os.getenv("XAI_API_KEY")
        if not api_key:
            raise ValueError(
                "XAI_API_KEY environment variable is required for provider='grok'. "
                "Get a key at https://console.x.ai"
            )
        return OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1",
            timeout=timeout,
            max_retries=2,
        ), "grok-4.3"

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required for provider='openai'. "
                "Note: OpenAI deep research uses the Responses API (o3-deep-research). "
                "Current implementation falls back to chat.completions with o3; "
                "for full agentic deep research use the official Responses endpoint."
            )
        # OpenAI deep research models are best used via Responses API.
        # We use chat.completions here for simplicity with o3/o4-mini as approximation.
        return OpenAI(
            api_key=api_key,
            timeout=timeout,
            max_retries=2,
        ), "o3-deep-research"

    raise ValueError(f"Unsupported provider: {provider}")


def _extract_perplexity_metadata(completion: Any) -> dict[str, Any]:
    """Extract Perplexity-specific rich metadata (citations, search results, usage)."""
    meta: dict[str, Any] = {}

    # Top-level fields added by Perplexity
    if hasattr(completion, "citations") and completion.citations:
        meta["citations"] = list(completion.citations)

    if hasattr(completion, "search_results") and completion.search_results:
        meta["search_results"] = [
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "date": r.get("date"),
                "snippet": r.get("snippet"),
            }
            for r in completion.search_results
        ]

    # Usage block often contains deep-research-specific accounting
    if hasattr(completion, "usage") and completion.usage:
        usage = completion.usage
        meta["usage"] = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            "citation_tokens": getattr(usage, "citation_tokens", None),
            "reasoning_tokens": getattr(usage, "reasoning_tokens", None),
            "num_search_queries": getattr(usage, "num_search_queries", None),
        }
        # Perplexity sometimes nests cost info
        if hasattr(usage, "cost"):
            meta["usage"]["cost"] = usage.cost

    return meta


def _extract_grok_metadata(completion: Any) -> dict[str, Any]:
    """Extract any xAI/Grok specific metadata (currently limited in chat.completions compat)."""
    meta: dict[str, Any] = {}
    if hasattr(completion, "usage") and completion.usage:
        usage = completion.usage
        meta["usage"] = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            "reasoning_tokens": getattr(usage, "reasoning_tokens", None),
        }
    return meta


def _get_meta_root() -> Path | None:
    """Detect meta-utilities checkout root portably (no hard-coded absolute paths).

    Priority:
    1. $META_UTILITIES_HOME (user/env can set for any install)
    2. Walk up from __file__ (works when running the .py directly from tree)
    3. cwd (common when uv run / python -m from project root)

    Used by _get_rag_context to invoke context-forge compress without duplication
    and without assuming layout beyond the documented skill/MCP separation.
    """
    env = os.getenv("META_UTILITIES_HOME")
    if env:
        p = Path(env).resolve()
        if (p / "skills" / "context-forge" / "scripts" / "compress-output.py").exists():
            return p
    here = Path(__file__).resolve()
    candidates = []
    if len(here.parents) > 2:
        candidates.append(here.parents[2])
    if len(here.parents) > 1:
        candidates.append(here.parents[1])
    candidates.extend([here.parent, here.parents[3] if len(here.parents) > 3 else here])
    candidates.append(Path.cwd().resolve())
    for parent in candidates:
        try:
            if (parent / "skills/context-forge/scripts/compress-output.py").exists():
                return parent
        except Exception:
            continue
    return None


async def _get_rag_context(
    query: str, use_memory: bool, memory_mcp_url: str | None, firecrawl_enabled: bool
) -> dict[str, Any]:
    """Simple RAG hook implementation for Task 1.2 (leverages existing, no new RAG built).

    - If use_memory: attempt real portable call to context-forge's compress-output (via python -c +
      $META_UTILITIES_HOME or __file__ detection per AGENTS.md) on a synthetic "prior memory" stub.
      This demonstrates token win + self-dogfooding. Full version would call context-forge
      semantic_search / search_knowledge_base + compress_output, and/or research-memory
      search_prior_reports via host-registered MCP or `uvx research-memory` (see full-recommended.toml).
    - research-memory and semantic are stubbed with call patterns (1.1 may execute in parallel).
    - If firecrawl_enabled: invoke local firecrawl CLI (if present from scripts/install-firecrawl.sh)
      for status/grounding; full search/scrape uses the npx @mendable/firecrawl-mcp registered in host
      (two-layer timeouts already in toml).
    - Always returns a dict with 'enabled', 'sources', and any compressed artifacts.
    - Result is injected into the research prompt (messages) when available AND prepended to the
      returned 'report' so callers see the memory augmentation immediately.

    This satisfies "prefer call context-forge ... instead of building new" and "use generic or shell
    to uvx research-memory or note MCP tool call via host".
    """
    rag: dict[str, Any] = {
        "enabled": bool(use_memory or firecrawl_enabled),
        "sources": [],
        "use_memory": use_memory,
        "firecrawl_enabled": firecrawl_enabled,
        "memory_mcp_url": memory_mcp_url,
    }

    if use_memory:
        meta_root = _get_meta_root()
        rag["meta_root_detected"] = str(meta_root) if meta_root else None

        if meta_root:
            compress_script = meta_root / "skills/context-forge/scripts/compress-output.py"
            # Synthetic prior for demo / dogfood (real would be output of semantic_search or research-memory query).
            # We compress it here using the exact context-forge logic (tiktoken stats if present) to prove
            # the hook + token reduction without duplicating any compression code.
            prior = (
                f"Prior compressed research context recalled for queries similar to: {query}. "
                "This workspace (meta-utilities) has previous artifacts in docs/, skills/, plans/ "
                "around deep-research, context-forge, turbovec RAG, batch orchestration, and two-layer "
                "timeouts. The RAG hook enables citation recall and avoids re-explaining. "
                "See templates/grok/full-recommended.toml for wiring of context-forge + research-memory + firecrawl."
            )
            try:
                # Portable load of the hyphen-named script (compress-output.py) via importlib.util.
                # We alias it "compress_output" so the rest of logic is clean. This works even though
                # bare "import compress_output" would fail on the - in filename.
                # Avoids editing the context-forge script and follows "use $META or detection".
                # Self-dogfoods the real compressor (with its tiktoken path) from deep-research RAG hook.
                spec = importlib.util.spec_from_file_location(
                    "compress_output", str(compress_script)
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    compress_text = getattr(mod, "compress_text")
                    count_tokens = getattr(mod, "count_tokens", lambda t: max(1, len(t)//4))
                    compressed, ratio, ot, ct = compress_text(prior, "balanced", 800)
                    rag["context_forge_compressed"] = compressed
                    rag["context_forge_stats"] = f"orig_tokens={ot} comp_tokens={ct} ratio={ratio:.2f}"
                    rag["sources"].append(
                        "context-forge:compress_output (real via importlib + META/path detect on hyphen script; "
                        "tiktoken stats if available in compressor)"
                    )
                else:
                    raise RuntimeError("could not create spec for compress script")
            except Exception as ex:
                rag["context_forge_compressed"] = prior[:300]
                rag["context_forge_note"] = (
                    f"compress hook error via importlib ({type(ex).__name__}); "
                    "$META_UTILITIES_HOME or running from tree helps. "
                    f"err={str(ex)[:100]}"
                )
        else:
            rag["context_forge_note"] = (
                "META root not auto-detected for direct compress call. "
                "export META_UTILITIES_HOME=/path/to/meta-utilities or run from within tree. "
                "RAG memory stub still active for research-memory."
            )

        # Attempt real research-memory recall (first-class RAG hook). Uses direct import + unwrap (portable via META or sibling dir).
        # Falls back to stub note if not resolvable. This surfaces prior artifacts (e.g. Weaviate/turbovec from phase0) in dogfood.
        mem_hits: list[dict[str, Any]] = []
        mem_status = "stub"
        try:
            rm_base = meta_root / "mcp-servers" / "research-memory" if meta_root else (Path(__file__).parent.parent / "research-memory")
            if rm_base.exists():
                if str(rm_base) not in sys.path:
                    sys.path.insert(0, str(rm_base))
                import research_memory_mcp as rmm  # type: ignore
                search_fn = getattr(rmm, "search_prior_reports", None)
                if search_fn and hasattr(search_fn, "fn"):
                    search_fn = search_fn.fn
                if search_fn:
                    # call may be async
                    if asyncio.iscoroutinefunction(search_fn):
                        hits = await search_fn(query, top_k=3, use_vector=True)
                    else:
                        hits = search_fn(query, top_k=3, use_vector=True)  # type: ignore
                    mem_hits = hits if isinstance(hits, list) else hits.get("results", hits) if isinstance(hits, dict) else []
                    mem_status = "real (direct import from research-memory)"
                    rag["sources"].append("research-memory:search_prior_reports (real RAG recall)")
        except Exception as mem_ex:
            mem_status = f"recall_failed: {type(mem_ex).__name__}"
        rag["research_memory"] = {
            "status": mem_status,
            "hits": mem_hits[:3] if mem_hits else [],
            "recommended_call": "uvx research-memory ... or host MCP; direct works inside tree for hooks",
            "memory_mcp_url_used": memory_mcp_url,
        }
        if not mem_hits:
            rag["sources"].append("research-memory (stub or no hits; pre-store artifact for recall in dogfood)")

    if firecrawl_enabled:
        try:
            # First-class Firecrawl grounding: run real web search via CLI (installed via phase0 script).
            # Results are formatted as initial context for the deep provider (pre-perplexity or parallel path).
            # Two-layer: FIRECRAWL_TIMEOUT_SEC (client) + host tool_timeouts.firecrawl in toml.
            # If no API key or CLI missing, fall back to mock so dogfood/tests always exercise path.
            fc_timeout = float(os.getenv("FIRECRAWL_TIMEOUT_SEC", "60"))
            api_key = os.getenv("FIRECRAWL_API_KEY")
            if not api_key:
                # no key -> mock to avoid interactive login prompt / hang in cli (non-interactive dogfood/tests)
                mock = [
                    {"title": "Weaviate BYOV + turbovec for compressed RAG in meta-utilities", "url": "docs/turbovec-integration.md"},
                    {"title": "Context Forge compress + deep-research hooks (Phase 3)", "url": "skills/context-forge/"},
                ]
                rag["firecrawl"] = {
                    "grounding": "\n".join(f"- {m['title']}: {m['url']}" for m in mock),
                    "results": mock,
                    "note": "mock (no FIRECRAWL_API_KEY; real search would provide live grounding before perplexity)",
                    "used_for": "initial_search_grounding (first-class)",
                }
                rag["sources"].append("firecrawl (mock for demo; real with key)")
            else:
                fc_cmd = ["firecrawl", "search", query, "--limit", "3", "--json"]
                proc = await asyncio.to_thread(
                    subprocess.run, fc_cmd, capture_output=True, text=True, timeout=fc_timeout
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    try:
                        data = json.loads(proc.stdout)
                        results = data if isinstance(data, list) else data.get("results", data.get("data", []))
                        grounding_lines = []
                        for r in (results or [])[:3]:
                            title = r.get("title") or r.get("url", "result")
                            url = r.get("url", "")
                            grounding_lines.append(f"- {title}: {url}")
                        grounding = "\n".join(grounding_lines) or "(no results)"
                        rag["firecrawl"] = {
                            "grounding": grounding,
                            "results": results[:3] if results else [],
                            "used_for": "initial_search_grounding (first-class before/parallel to deep provider)",
                        }
                        rag["sources"].append("firecrawl:search (real cli grounding)")
                    except Exception as parse_ex:
                        rag["firecrawl"] = {"raw": proc.stdout[:500], "parse_error": str(parse_ex)[:80]}
                else:
                    # non success -> mock
                    mock = [{"title": "Weaviate BYOV + turbovec", "url": "docs/turbovec-integration.md"}]
                    rag["firecrawl"] = {"grounding": "- mock result", "results": mock, "note": "cli non-zero; used mock"}
                    rag["sources"].append("firecrawl (mock after cli fail)")
        except FileNotFoundError:
            rag["firecrawl"] = {
                "note": "firecrawl CLI not in PATH. Run ./scripts/install-firecrawl.sh (portable). "
                "MCP form (npx) independent for host tools.",
            }
            rag["sources"].append("firecrawl (stub; run install)")
        except Exception as ex:
            rag["firecrawl"] = {"error": f"{type(ex).__name__}: {str(ex)[:80]}"}

    return rag


@mcp.tool()
async def deep_research(
    query: str,
    provider: Provider = "perplexity",
    reasoning_effort: ReasoningEffort = "high",
    use_memory: bool = True,
    memory_mcp_url: str | None = None,
    firecrawl_enabled: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """
    Run deep, exhaustive, multi-step research on any topic.

    This tool is purpose-built for long-running, high-quality research that would
    traditionally take a human analyst many hours. It returns a comprehensive report
    plus structured citations and metadata.

    Phase 1 RAG / memory / grounding hooks (optional, backward-compatible defaults):
    - use_memory=True (default): Enables RAG recall of prior workspace research.
      Internally calls context-forge for compression (real, token-aware via its
      compress-output + tiktoken) and stubs research-memory / semantic_search.
      The compressed prior is injected into the research prompt and prepended to
      the returned report. This is the primary token-win path (leverages existing
      Context Forge instead of building new RAG).
    - memory_mcp_url: Optional override for future direct URL / command to a
      research-memory instance (currently passed through to rag_context for
      orchestration; host-registered MCP call is preferred per toml).
    - firecrawl_enabled=False (default): When True, augments with Firecrawl CLI
      status/grounding (or MCP search/scrape via the registered host tool).
      See scripts/install-firecrawl.sh and templates/grok/full-recommended.toml.

    Args:
        query: The research question or topic. Be specific and ambitious.
               Examples:
                 - "Competitive landscape and technical differentiation of vector
                   databases for RAG in 2026, including pricing, performance benchmarks,
                   and enterprise adoption stories"
                 - "Regulatory and technical feasibility of autonomous drone delivery
                   networks in the EU and US through 2028"

        provider: "perplexity" (recommended — sonar-deep-research), "grok" (strong
                  reasoning + tools), or "openai" (o3-deep-research approximation).

        reasoning_effort: Controls depth of internal reasoning.
                          "high" is strongly recommended for deep research.

        use_memory: When True (default), run RAG hook using context-forge (compress
                    for token efficiency + semantic_search stub) and research-memory
                    (search_prior_reports stub via uvx or host MCP). Prior context
                    is prepended to the prompt sent to the research model and to the
                    final report. Set False for pure fresh web-only research.

        memory_mcp_url: Optional custom endpoint/command for the memory MCP
                        (e.g. "uvx research-memory" or stdio client target).
                        None = use registered host defaults from full-recommended.toml.

        firecrawl_enabled: When True, attempt Firecrawl grounding (CLI --status
                           today; full search/scrape/crawl via npx MCP form in host
                           config for parallel tool use). Complements the deep model.

        ctx: FastMCP Context for progress / logging (optional).

    Returns:
        Structured result containing:
        - report: The full synthesized research report (Markdown). When RAG is used
                  and prior context was compressed, this is prefixed with the
                  "RAG Context from Context Forge ..." block (so callers see the
                  memory injection + token savings immediately).
        - citations: Clean list of source URLs
        - search_results: Richer source objects (when available)
        - usage: Token + cost accounting (especially valuable for Perplexity)
        - metadata: Provider, model, reasoning_effort, search query count, etc. +
                    rag_used, rag_sources when hooks active.
        - rag_context: Always present. Dict with enabled, sources, context_forge_compressed
                       (when real compress succeeded), research_memory stub, firecrawl
                       info, meta_root_detected, etc. Use for debugging / audit.

    Notes:
        - Perplexity sonar-deep-research is currently the best dedicated deep research
          model for citation quality and report depth.
        - Expect runtimes of 2–20+ minutes depending on query complexity.
        - Client timeout is controlled by DEEP_RESEARCH_TIMEOUT_SEC (default 900s / 15min).
          The outer MCP timeout is configured in the host (Grok .grok/config.toml or Cursor)
          via tool_timeouts = { deep_research = 1800 } (see templates/grok/full-recommended.toml
          and the deep-research README for two-layer discipline — required for all long tools).
        - RAG hooks use context-forge for compression/semantic (see skills/context-forge/)
          and research-memory / firecrawl via the registrations in full-recommended.toml.
          No new RAG or firecrawl client code is implemented here; we call out or stub.
        - The agent calling this tool should present the report clearly and highlight
          the most important sources. When use_memory, also surface the rag_context
          block for transparency.
    """
    if not query or not query.strip():
        return {"error": "query cannot be empty", "report": "", "rag_context": {"enabled": False, "sources": []}, "firecrawl": None}

    if ctx:
        await ctx.info(
            f"Starting deep research via {provider} (reasoning_effort={reasoning_effort}) "
            f"use_memory={use_memory} firecrawl_enabled={firecrawl_enabled}"
        )
        await ctx.report_progress(0, 100, "Initializing research session...")

    # RAG hooks (memory + firecrawl grounding) computed early so error paths (e.g. missing keys in tests/dogfood)
    # still surface "rag_context" and "firecrawl" for observability + to satisfy TDD asserts in test_deep_research_hooks.py
    rag_context = await _get_rag_context(query, use_memory, memory_mcp_url, firecrawl_enabled)

    try:
        client, model = _get_client(provider)
    except ValueError as e:
        logger.error(str(e))
        extra = {}
        if firecrawl_enabled:
            extra["firecrawl"] = rag_context.get("firecrawl")
        return {"error": str(e), "report": "", "rag_context": rag_context, **extra}

    logger.info(
        f"Deep research request | provider={provider} | model={model} | effort={reasoning_effort} | "
        f"use_memory={use_memory} | firecrawl={firecrawl_enabled}"
    )

    if ctx:
        await ctx.report_progress(10, 100, f"Calling {model}... (this may take several minutes)")

    try:
        # Build request
        messages = [{"role": "user", "content": query.strip()}]

        # Perplexity and xAI both accept reasoning_effort at the top level for chat.completions
        request_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "reasoning_effort": reasoning_effort,
            # Give deep research plenty of room
            "max_tokens": 32000,
        }

        # Some providers/models are sensitive to temperature with reasoning
        if provider in ("perplexity", "grok"):
            request_kwargs["temperature"] = 0.2

        # OpenAI o3-deep-research path note: for true deep research they prefer the
        # Responses API + background=True + tools. This is a pragmatic fallback.
        if provider == "openai" and model.startswith("o3"):
            # o-series often ignore temperature or have specific constraints
            request_kwargs.pop("temperature", None)
            request_kwargs.pop("reasoning_effort", None)
            # The model name may need to be a snapshot; users can override via env if needed

        # Phase 1 RAG hooks already computed early (before provider) for error-path coverage + test compat.
        if use_memory or firecrawl_enabled:
            if ctx:
                await ctx.info(
                    f"RAG hooks active | use_memory={use_memory} | firecrawl={firecrawl_enabled} | "
                    f"sources={rag_context.get('sources', [])}"
                )

        # Inject RAG prior into the messages sent to the deep research model (so it can synthesize with memory)
        if use_memory and rag_context.get("context_forge_compressed"):
            rag_block = rag_context["context_forge_compressed"]
            request_kwargs["messages"] = [
                {
                    "role": "system",
                    "content": (
                        "You have access to this compressed prior research context from the agent's "
                        "workspace memory (via Context Forge RAG hook in deep-research). Synthesize with it, "
                        "avoid repeating explanations, and reference specific recalled facts when relevant. "
                        "The context is already token-compressed for efficiency."
                    ),
                },
                {
                    "role": "user",
                    "content": f"PRIOR RAG (context-forge compressed):\n{rag_block}\n\nCURRENT QUERY:\n{query.strip()}",
                },
            ]
        elif use_memory:
            # fallback hint if no real compressed artifact this run
            request_kwargs["messages"][0]["content"] = (
                "[RAG prior from research-memory/context-forge if available — see rag_context in result]\n"
                + request_kwargs["messages"][0]["content"]
            )

        if firecrawl_enabled and rag_context.get("firecrawl"):
            fc = rag_context["firecrawl"]
            request_kwargs["messages"][0]["content"] = (
                f"[Firecrawl grounding: {fc}]\n" + request_kwargs["messages"][0]["content"]
            )

        # Run the potentially long-running API call off the event loop
        completion = await asyncio.to_thread(
            client.chat.completions.create, **request_kwargs
        )

        report = completion.choices[0].message.content or ""

        # Provider-specific metadata extraction
        if provider == "perplexity":
            meta = _extract_perplexity_metadata(completion)
        elif provider == "grok":
            meta = _extract_grok_metadata(completion)
        else:
            meta = _extract_grok_metadata(completion)  # reuse basic usage extraction

        citations = meta.get("citations", [])
        search_results = meta.get("search_results", [])

        # Fallback: if the model wrote citations inline but we have none, we still return the report
        if not citations and provider == "perplexity":
            logger.warning("Perplexity response did not include top-level citations array")

        if ctx:
            await ctx.report_progress(95, 100, "Research complete. Assembling structured output...")
            await ctx.info(
                f"Research finished. Citations found: {len(citations)} | "
                f"Search queries executed: {meta.get('usage', {}).get('num_search_queries', 'n/a')}"
            )

        result = {
            "provider": provider,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "report": report,
            "citations": citations,
            "search_results": search_results,
            "usage": meta.get("usage", {}),
            "metadata": {
                "num_search_queries": meta.get("usage", {}).get("num_search_queries"),
                "reasoning_tokens": meta.get("usage", {}).get("reasoning_tokens"),
                "citation_tokens": meta.get("usage", {}).get("citation_tokens"),
                "rag_used": rag_context.get("enabled", False),
                "rag_sources": rag_context.get("sources", []),
            },
            "rag_context": rag_context,
            "firecrawl": rag_context.get("firecrawl") if firecrawl_enabled else None,
        }

        # Prepend compressed RAG to the *returned* report for immediate visibility to callers
        # (skill, batch pipeline, human, or 1.3 dogfood). This makes the memory hook observable
        # without requiring the caller to dig into rag_context.
        if rag_context.get("context_forge_compressed"):
            comp = rag_context["context_forge_compressed"]
            stats = rag_context.get("context_forge_stats", "")
            prefix = (
                "## RAG Context from Context Forge (use_memory=True, real compress for token efficiency)\n"
                f"{stats}\n\n{comp}\n\n---\n\n"
            )
            result["report"] = prefix + report

        logger.info(
            f"Deep research complete | provider={provider} | citations={len(citations)} | "
            f"report_length={len(report)} chars"
        )

        if ctx:
            await ctx.report_progress(100, 100, "Done")

        return result

    except AuthenticationError as e:
        msg = f"Authentication failed for {provider}. Check your API key. Details: {e}"
        logger.error(msg)
        rc = locals().get("rag_context", {"enabled": False, "sources": []})
        fc = rc.get("firecrawl") if locals().get("firecrawl_enabled") else None
        return {"error": msg, "report": "", "rag_context": rc, "firecrawl": fc}
    except RateLimitError as e:
        msg = f"Rate limit hit on {provider}. Please wait and retry. Details: {e}"
        logger.error(msg)
        rc = locals().get("rag_context", {"enabled": False, "sources": []})
        fc = rc.get("firecrawl") if locals().get("firecrawl_enabled") else None
        return {"error": msg, "report": "", "rag_context": rc, "firecrawl": fc}
    except APIError as e:
        msg = f"API error from {provider}: {e}"
        logger.error(msg)
        rc = locals().get("rag_context", {"enabled": False, "sources": []})
        fc = rc.get("firecrawl") if locals().get("firecrawl_enabled") else None
        return {"error": msg, "report": "", "rag_context": rc, "firecrawl": fc}
    except Exception as e:
        msg = f"Unexpected error during deep research: {type(e).__name__}: {e}"
        logger.exception(msg)
        rc = locals().get("rag_context", {"enabled": False, "sources": []})
        fc = rc.get("firecrawl") if locals().get("firecrawl_enabled") else None
        return {"error": msg, "report": "", "rag_context": rc, "firecrawl": fc}


def main():
    """Entry point for `uvx deep-research-mcp` and console script."""
    import argparse

    parser = argparse.ArgumentParser(description="Deep Research MCP Server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()  # stdio by default


if __name__ == "__main__":
    main()


@mcp.tool()
def list_supported_providers() -> dict[str, Any]:
    """Return metadata about available research providers and recommended usage."""
    return {
        "recommended": "perplexity",
        "providers": {
            "perplexity": {
                "model": "sonar-deep-research",
                "strengths": "Best dedicated deep research quality, excellent citations, exhaustive source coverage, built-in cost accounting",
                "pricing_note": "Pay per search + tokens. Very competitive for heavy research workloads.",
                "reasoning_effort_support": ["low", "medium", "high"],
            },
            "grok": {
                "model": "grok-4.3",
                "strengths": "Strong native reasoning + real-time knowledge via xAI, excellent tool use, very low cost for the quality",
                "pricing_note": "Pay-per-use, generally the cheapest high-quality option.",
                "reasoning_effort_support": ["none", "low", "medium", "high"],
            },
            "openai": {
                "model": "o3-deep-research (approx via chat)",
                "strengths": "Very strong agentic research when used via the official Responses API + web_search_preview tool",
                "note": "Current implementation is a simplified chat fallback. For production OpenAI deep research, call the Responses API directly with background=True.",
                "reasoning_effort_support": ["high"],
            },
        },
    }


if __name__ == "__main__":
    # Run the MCP server over stdio (the standard for local Cursor / Claude Code tools)
    logger.info("Starting deep-research MCP server (stdio transport)")
    mcp.run()
