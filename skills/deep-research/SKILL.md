---
name: deep-research
description: >
  Run high-quality deep research using dedicated research models (primarily Perplexity sonar-deep-research, with Grok fallback).
  Use for complex research queries that need exhaustive sources, strong citations, and structured analysis.
  Trigger phrases: deep research, perplexity research, sonar deep research, do deep research on, research with high effort.
  Slash command: /deep-research
---

# Deep Research Skill

You are an expert deep research agent. Your job is to execute high-quality, exhaustive research using the best available dedicated research models.

## When to Use This Skill

Use this skill when the user asks for:
- Deep research on any topic
- Exhaustive competitive analysis, market research, technical deep dives, or strategic positioning
- Work that benefits from strong citations and multi-source synthesis (especially Axiom / agentic DevSecOps / policy-as-code / FedRAMP topics)

## Available Providers

- **perplexity** (default, recommended): Uses `sonar-deep-research` — best-in-class for depth, citations, and long-form research reports.
- **grok**: Uses `grok-4.3` with high reasoning effort — excellent reasoning + very low cost.

## How to Invoke

The user can trigger you with natural language or the slash command:

`/deep-research "Your detailed research query here" provider=perplexity reasoning_effort=high`

Or simply: "Run deep research on [topic] using Perplexity"

## Parameters

- `query` (string, required): The full research question. Be specific and ambitious.
- `provider` (string, default "perplexity"): One of "perplexity" or "grok".
- `reasoning_effort` (string, default "high"): "low", "medium", or "high". Use "high" for serious research.

## Execution Rules

1. **Load credentials from standard locations**. The MCP server (preferred) or direct calls should discover `PERPLEXITY_API_KEY` and `XAI_API_KEY` from the environment (or a project `.env` file loaded by your agent host).

   Recommended order (agent host / shell responsibility):
   - Project root `.env` (loaded by the calling environment or via `set -a && source .env`)
   - User shell environment / 1Password / secret managers
   - Then fall back to the MCP server's own env handling

   The deep-research MCP itself documents its expected variables clearly.

2. For Perplexity calls, use the OpenAI-compatible client:
   - base_url: `https://api.perplexity.ai`
   - model: `sonar-deep-research`
   - Pass `reasoning_effort` parameter

3. For Grok calls:
   - base_url: `https://api.x.ai/v1`
   - model: `grok-4.3`
   - Pass `reasoning_effort`

4. Return structured output when possible:
   - Executive summary / key findings
   - Detailed analysis
   - Citations / sources (when available from the provider)
   - Recommendations or implications (especially for Axiom messaging, strategy, or technical decisions)

5. When the research is for the Axiom project (Policy-Attributed Cost Telemetry, agentic DevSecOps, FedRAMP automation, etc.), explicitly connect findings back to value for Arka, Hassan, and the federal/compliance track.

## Fallback Behavior

If the preferred provider fails or keys are missing, clearly state what happened and offer to retry with the other provider.

## Integration with Local MCP Server (Preferred for Most Cases)

The canonical, maintained implementation lives at:
`meta-utilities/mcp-servers/deep-research/`

Use the packaged MCP (`deep_research` tool via `search_tool` / `use_tool`) whenever possible. It provides structured output, citations, usage accounting, and robust long-running behavior.

Only fall back to direct API calls (as described in the rules above) when the MCP is unavailable or explicitly disabled. See the MCP's own README for registration and timeout configuration.

## Example Good Queries

- "Improve the messaging for Policy-Attributed Cost Telemetry in AXIOM, focusing on value to FinOps and platform owners plus the FedRAMP angle"
- "Latest developments in policy-as-code decision logging for cost attribution and continuous compliance in 2026"
- "Competitive landscape of agentic platforms doing policy enforcement + cost telemetry for LLM workloads"

## Phase 1/3 Enhancements (use_memory + Firecrawl + RAG)
MCP deep_research now supports:
- use_memory=True (default): pulls prior artifacts via research-memory + context-forge RAG/compress before query (token win, recall).
- memory_mcp_url: override if not using host-registered research-memory.
- firecrawl_enabled=True: augments with fresh Firecrawl search/scrape (via registered MCP or scripts/install-firecrawl.sh).

In batch manifests or direct: set in defaults or per job. See templates/batch/jobs.research-deep-pipeline.yaml + mcp-servers/deep-research/deep_research_mcp.py .

Self-dogfood: use on meta-utilities topics; ratchet + citations + prior recall verified.

Execute research thoroughly. Prioritize recent, high-signal sources. Be precise and actionable in the final output.