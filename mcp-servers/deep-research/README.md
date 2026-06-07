# deep-research-mcp

**Production-grade, portable Deep Research MCP server.**

Primary model: Perplexity `sonar-deep-research` (best-in-class for citations and depth)
Strong fallback: xAI Grok (`grok-4.3` with high reasoning effort)

This is the canonical, extracted version maintained in **meta-utilities**.

## Features

- Excellent structured output with citations, search results, and usage accounting
- Built-in support for very long-running jobs (2–20+ minutes)
- Two-layer timeout model (client + host)
- Progress reporting via MCP Context
- Three providers supported: `perplexity`, `grok`, `openai`
- Clean packaging (`uv tool` + Docker)

## Quick Start

### 1. Install

**Recommended:**
```bash
uv tool install -e /path/to/meta-utilities/mcp-servers/deep-research
```

Then run with:
```bash
deep-research-mcp
```

**Development:**
```bash
cd mcp-servers/deep-research
uv run python deep_research_mcp.py
```

### 2. Register with your agent

See the templates in this directory (`templates/`) and the main `docs/skill-install-patterns.md`.

Example for Grok Build (add to `.grok/config.toml`):
```toml
[mcp_servers.deep-research]
command = "uvx"
args = ["deep-research-mcp"]
env = { PERPLEXITY_API_KEY = "${PERPLEXITY_API_KEY}", XAI_API_KEY = "${XAI_API_KEY}" }
tool_timeouts = { deep_research = 1800 }
```

### 3. Use it

In any supported agent:
```
/deep-research "Competitive landscape of vector databases for RAG in 2026..."
```

Or call the `deep_research` tool directly via MCP.

## Timeout Configuration (Important)

Deep research jobs are intentionally long-running.

**Client level** (inside this server):
```bash
export DEEP_RESEARCH_TIMEOUT_SEC=1800
```

**Host level** (Grok example):
See `templates/grok-config-snippet.toml` in this directory.

Full explanation: `docs/timeout-patterns.md` in the meta-utilities root.

## Project Structure

- `deep-research-mcp.py` — The server
- `pyproject.toml` — Packaging
- `Dockerfile` — Container support
- `templates/` — Ready-to-use registration examples
- `DEEP_RESEARCH.md` — Original rich documentation (also see the expanded content below)

## Roadmap

See the main `docs/abstraction-roadmap.md` and the Gap Closure Plan for current priorities.

This MCP is one of the highest-value pieces being extracted into meta-utilities.
