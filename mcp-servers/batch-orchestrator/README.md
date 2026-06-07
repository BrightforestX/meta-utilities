# Batch Orchestrator MCP

YAML-driven batch queue for **deep research**, **normal inference**, and **multi-stage research pipelines** with hybrid realtime / provider-batch execution.

## Features

- **YAML job manifests** — declare a list of jobs with dependencies, providers, and execution modes
- **Hybrid execution** — `mode: realtime` (immediate API) or `mode: batch` (OpenAI/xAI/Anthropic async Batch APIs, ~50% cheaper)
- **Multi-stage pipeline** — `deep_research_pipeline` type runs triage → fan-out → synthesis → reflection
- **Durable SQLite store** — checkpoint runs, resume after crashes, collect batch results later
- **CLI + MCP** — `meta-batch` for scripting/CI; MCP tools for Grok/Cursor/Claude agents

## Quick Start

```bash
cd mcp-servers/batch-orchestrator
uv pip install -e ".[dev]"

# Validate a manifest
meta-batch validate ../../templates/batch/jobs.example.yaml

# Run all jobs (realtime jobs execute immediately; batch jobs submit and exit)
meta-batch run ../../templates/batch/jobs.example.yaml

# Collect provider batch results later
meta-batch collect <run_id>

# Check status
meta-batch status <run_id>
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PERPLEXITY_API_KEY` | Perplexity API (realtime deep research) |
| `XAI_API_KEY` | xAI Grok (realtime + batch) |
| `OPENAI_API_KEY` | OpenAI (realtime + batch) |
| `ANTHROPIC_API_KEY` | Anthropic (batch; optional) |
| `BATCH_ORCHESTRATOR_HOME` | State DB directory (default `~/.meta-utilities`) |
| `BATCH_ORCHESTRATOR_TIMEOUT_SEC` | Realtime API timeout (default 900s) |

## MCP Registration

**Grok** (`.grok/config.toml`):

```toml
[mcp_servers.batch-orchestrator]
command = "uvx"
args = ["batch-orchestrator-mcp"]
env = { OPENAI_API_KEY = "${OPENAI_API_KEY}", XAI_API_KEY = "${XAI_API_KEY}", PERPLEXITY_API_KEY = "${PERPLEXITY_API_KEY}" }
tool_timeouts = { submit_batch = 3600, run_research_pipeline = 3600 }
```

**Cursor** (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "batch-orchestrator": {
      "command": "uvx",
      "args": ["batch-orchestrator-mcp"]
    }
  }
}
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `submit_batch` | Run a YAML manifest |
| `get_batch_status` | Poll run/job status |
| `collect_batch_results` | Collect provider batch API results |
| `run_research_pipeline` | Single-query multi-stage pipeline |
| `list_batch_runs` | List recent runs |

## Manifest Schema

See `templates/batch/jobs.example.yaml` and `docs/batch-orchestration.md`.

## Related

- `mcp-servers/deep-research/` — single-shot deep research MCP
- `skills/batch-research/` — thin discovery skill
- `PRD.md` — multi-agent research architecture rationale
