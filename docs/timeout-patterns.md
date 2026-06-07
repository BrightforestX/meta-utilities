# Timeout Patterns for Long-Running Agent Tools (2026 Best Practice)

This document captures the proven **two-layer timeout model** developed while building the deep-research MCP.

## The Problem

Deep research (and similar agentic tasks) routinely take 2–20+ minutes. Default MCP and agent host timeouts are usually 60 seconds.

## The Solution: Two Layers

### Layer 1: Client / Tool Level (Inside the MCP or Tool)

Controlled by environment variables or code:

```python
DEEP_RESEARCH_TIMEOUT_SEC=1800   # 30 minutes
```

In the deep-research-mcp, this is passed to the OpenAI client:

```python
OpenAI(..., timeout=DEEP_RESEARCH_TIMEOUT_SEC, max_retries=2)
```

**Recommendation**: Always set generous client timeouts for research-grade tools.

### Layer 2: MCP Host Level (Grok, Cursor, Claude Code, etc.)

This is the outer timeout enforced by the agent host when calling the MCP tool.

#### Grok Build (recommended)

```toml
# .grok/config.toml or project .grok/config.toml
[mcp_servers.deep-research]
tool_timeout_sec = 300
tool_timeouts = { deep_research = 1800 }   # 30 minutes for the heavy tool
```

#### Cursor

Cursor has more limited per-tool timeout control in `.cursor/mcp.json`. The main mitigations are:
- High `DEEP_RESEARCH_TIMEOUT_SEC`
- Prefer Streamable HTTP transport for very long jobs when possible
- Use `fastmcp install` where available

## Usage in meta-utilities

- The deep-research MCP respects `DEEP_RESEARCH_TIMEOUT_SEC`
- Templates in `templates/` include the Grok host-level settings
- The bootstrap script prints the recommended configuration

## General Rule

For any tool that can take > 2 minutes:
1. Set a high client timeout inside the tool/MCP.
2. Configure a matching (or higher) `tool_timeouts` entry in the host.
3. Document both layers clearly.

This pattern has proven reliable for the deep research use case.
