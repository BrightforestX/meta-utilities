# Deep Research MCP Tool for Cursor

A first-class, one-command deep research capability inside Cursor powered by dedicated research models (primarily **Perplexity sonar-deep-research**).

## Why This Exists

Standard LLM calls are not enough for serious research. This MCP server gives you a dedicated `deep_research` tool that can:

- Run exhaustive, multi-hour-style research sessions (typically 2–20 minutes)
- Return **structured output** with clean citations, search result metadata, and usage/cost accounting
- Use the best purpose-built models:
  - **Perplexity `sonar-deep-research`** (primary recommendation)
  - **xAI `grok-4.3`** with high reasoning effort (excellent price/performance)
- Be invoked naturally from Cursor Composer:  
  `"Run deep research on the state of agentic DevSecOps platforms in 2026 using Perplexity"`

## Files

- `deep-research-mcp.py` — The MCP server (FastMCP + OpenAI SDK)
- `.cursor/mcp.json` — Workspace MCP configuration
- `DEEP_RESEARCH.md` — This guide

## Quick Start (Recommended — FastMCP CLI)

The modern, cleanest way to install MCP servers in Cursor (2026):

```bash
# 1. Install the tool (uv recommended)
uv pip install "fastmcp>=3" openai

# 2. (Optional but recommended) Create a .env file with your keys
cat > .env << 'EOF'
PERPLEXITY_API_KEY=your_perplexity_key_here
XAI_API_KEY=your_xai_key_here
OPENAI_API_KEY=your_openai_key_here   # optional
# Raise this for very long deep research jobs (default inside server is already 15 min)
DEEP_RESEARCH_TIMEOUT_SEC=1800
EOF

# 3. Install/register the server with Cursor for this workspace (strongly recommended)
fastmcp install cursor deep-research-mcp.py \
  --env-file .env \
  --with openai \
  --python 3.12 \
  --name "deep-research"

# 4. Completely restart Cursor (or reload window)
```

**For Grok Build** (instead of or in addition to Cursor):
- The repo already contains `.grok/config.toml` with the server registered and `tool_timeouts.deep_research = 1800`.
- Make sure your shell has `PERPLEXITY_API_KEY` and `XAI_API_KEY` exported (or use `set -a && source .env && set +a` before launching `grok`).
```

After restart, Cursor will automatically discover the `deep_research` tool.

## Manual Setup (matches the original brief)

1. Install dependencies:

```bash
pip install fastmcp openai
# or
uv pip install fastmcp openai
```

2. Get API keys:
   - Perplexity (strongly recommended): https://www.perplexity.ai/settings/api
   - xAI Grok: https://console.x.ai

3. Edit `.cursor/mcp.json` and fill in the keys (or leave empty and rely on shell environment variables):

```json
{
  "mcpServers": {
    "deep-research": {
      "command": "python",
      "args": ["deep-research-mcp.py"],
      "env": {
        "PERPLEXITY_API_KEY": "pplx-...",
        "XAI_API_KEY": "xai-...",
        "OPENAI_API_KEY": ""
      }
    }
  }
}
```

4. Restart Cursor completely.

5. In Composer (or Agent), just say:

> Use the deep_research tool on [your ambitious research topic] with provider="perplexity"

## Usage Examples

```text
Use deep_research on the competitive landscape of edge AI inference chips in 2026, 
including technical approaches, key players, funding, power efficiency benchmarks, 
and enterprise adoption barriers. Focus on inference at the edge vs cloud.

Use deep_research with provider="grok" and reasoning_effort="high" on 
"Feasibility of fully autonomous last-mile drone delivery networks in dense 
European cities by 2029 — regulatory, technical, and economic analysis".
```

You can also call the helper:

```text
Use list_supported_providers
```

## Tool Reference

### `deep_research`

| Parameter          | Type     | Default     | Description |
|--------------------|----------|-------------|-----------|
| `query`            | string   | (required)  | The research topic. Be specific and ambitious. |
| `provider`         | enum     | "perplexity"| `perplexity`, `grok`, or `openai` |
| `reasoning_effort` | enum     | "high"      | `low` / `medium` / `high` — higher = deeper + more citations + longer runtime |

**Return shape (structured):**

```json
{
  "provider": "perplexity",
  "model": "sonar-deep-research",
  "reasoning_effort": "high",
  "report": "# Full Markdown research report...",
  "citations": ["https://...", "..."],
  "search_results": [
    { "title": "...", "url": "...", "snippet": "..." }
  ],
  "usage": {
    "prompt_tokens": 123,
    "completion_tokens": 14500,
    "reasoning_tokens": 193000,
    "num_search_queries": 21,
    "cost": { ... }
  },
  "metadata": { ... }
}
```

The Cursor agent receives the full structured object and can intelligently present the report + sources.

## Provider Comparison (2026)

| Provider     | Model                    | Best For                          | Citation Quality | Relative Cost | Notes |
|--------------|--------------------------|-----------------------------------|------------------|---------------|-------|
| **Perplexity** | `sonar-deep-research`   | Exhaustive reports, due diligence | Excellent        | Medium        | Gold standard for this use case |
| **Grok**       | `grok-4.3`              | Reasoning + cost sensitive work   | Very good        | Very Low      | Outstanding price/performance |
| OpenAI         | `o3-deep-research`      | Agentic multi-tool workflows      | Excellent        | High          | Requires Responses API for full power (future enhancement) |

## Long-Running Behavior & Best Practices

Deep research queries are intentionally long-running (the models perform dozens of searches and heavy synthesis). Typical wall time is 2–20+ minutes.

### Timeout Controls (Important)

You now have two layers of timeout protection:

1. **Client level** (inside the MCP server)
   - Controlled by the `DEEP_RESEARCH_TIMEOUT_SEC` environment variable.
   - Default: **900 seconds (15 minutes)**.
   - Set higher if needed: `export DEEP_RESEARCH_TIMEOUT_SEC=1800` before starting the server.

2. **MCP host level** (the agent that calls the tool)
   - **Grok Build**: Configure in `.grok/config.toml` (project or user):
     ```toml
     [mcp_servers.deep-research]
     tool_timeout_sec = 300
     tool_timeouts = { deep_research = 1800 }   # 30 minutes for the heavy tool
     ```
   - **Cursor**: Cursor's stdio MCP client has more limited per-tool timeout control. Use the modern `fastmcp install` registration (recommended below) and set `DEEP_RESEARCH_TIMEOUT_SEC` high. For extreme jobs, consider moving the server to Streamable HTTP transport.

- The server uses `async` + `ctx.report_progress` so the caller sees live updates.
- **Tip**: Start with `reasoning_effort="medium"` on exploratory queries, then escalate to `"high"`.

## Troubleshooting

**"PERPLEXITY_API_KEY is required"**
- Make sure the key is in the `env` section of `.cursor/mcp.json` **or** exported in your shell before starting Cursor.
- Restart Cursor after changing the json.

**Tool doesn't appear in Cursor**
- Check Cursor's Output panel → "MCP" or "Developer Tools" logs.
- Use the command palette: "Developer: Reload Window" or fully quit/reopen Cursor.
- Verify the python path resolves correctly (use absolute path in `args` if needed).

**Very long runs timeout or hang**
- Set `DEEP_RESEARCH_TIMEOUT_SEC=1800` (or higher) in your environment before launching the MCP server.
- For **Grok Build**: Use the project `.grok/config.toml` with `tool_timeouts.deep_research = 1800` (see the file already created in this repo at `.grok/config.toml`).
- For **Cursor**: The `fastmcp install cursor ...` method (recommended in Quick Start) is currently the most reliable. Cursor stdio transport has known limitations on very long calls.
- Advanced: Switch the server to Streamable HTTP transport for better long-connection behavior in Cursor.

**Want even better OpenAI deep research?**
The official `o3-deep-research` model shines when used via OpenAI's **Responses API** (`client.responses.create(..., background=True, tools=[{"type": "web_search_preview"}])`). A future version of this server can add a dedicated `openai_deep_research` tool using that path.

## Future Enhancements (Roadmap)

- [ ] Full OpenAI Responses API + `background=True` + webhook support for o3-deep-research
- [ ] `task=True` + live progress updates using FastMCP Docket
- [ ] TypeScript implementation using `@modelcontextprotocol/sdk` (single-file, no Python required)
- [ ] Streaming of partial research results
- [ ] Per-query search domain filters and recency controls (Perplexity extras)
- [ ] Cost estimation / budget guardrails before launching heavy jobs
- [ ] Integration with local RAG / your own documents (MCP resources)

## TypeScript Version?

A TypeScript version is straightforward using the official MCP TypeScript SDK + the same OpenAI-compatible calls. It would be useful for people who want zero Python in their environment. Let the maintainer know if you want it added.

## Credits & Sources

- Perplexity Sonar Deep Research docs (2026)
- xAI Grok API (OpenAI compatibility + reasoning_effort)
- FastMCP (the excellent modern Python MCP framework)
- Original design brief for Cursor deep research MCP

---

**Ready to use**: After setup, just talk to Cursor normally. The agent will automatically reach for `deep_research` when the task requires serious depth.
