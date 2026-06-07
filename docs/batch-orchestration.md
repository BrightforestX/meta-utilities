# Batch Orchestration

YAML-driven batch queue for deep research, normal inference, and multi-stage research pipelines.

## Overview

The **batch-orchestrator** package (`mcp-servers/batch-orchestrator/`) implements the queue + hybrid execution model described in [PRD.md](../PRD.md):

| Capability | Implementation |
|------------|----------------|
| Job manifest (YAML) | Pydantic-validated schema with DAG dependencies |
| Realtime inference | OpenAI-compatible chat APIs (Perplexity, Grok, OpenAI) |
| Provider batch mode | OpenAI, xAI, Anthropic async Batch APIs (~50% off) |
| Multi-stage pipeline | Triage → fan-out → synthesis → reflection |
| Durability | SQLite checkpoint store + artifact files |
| Interfaces | `meta-batch` CLI + MCP tools |

## Architecture

```
jobs.yaml → models.py → engine.py → store.py (SQLite)
                ↓
         pipeline.py (deep_research_pipeline type)
                ↓
    realtime: providers.py          batch: batch_providers/
```

## Manifest Reference

### Top-level fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `version` | int | 1 | Schema version |
| `defaults` | object | see below | Default job settings |
| `output_dir` | string | `./batch-results` | Artifact output directory |
| `concurrency` | int | 4 | Max parallel realtime jobs |
| `budget.max_usd` | float | — | Optional spend cap (tracked, not enforced yet) |
| `jobs` | list | required | Job definitions |

### Defaults

```yaml
defaults:
  provider: perplexity      # perplexity | grok | openai | anthropic
  reasoning_effort: high    # low | medium | high
  mode: realtime            # realtime | batch
  model: null               # optional model override
  max_retries: 2
```

### Job fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Unique alphanumeric identifier |
| `type` | yes | `deep_research`, `inference`, `deep_research_pipeline` |
| `mode` | no | Override defaults.mode |
| `provider` | no | Override defaults.provider |
| `query` | for research types | Research question |
| `prompt` | for inference | Inference prompt |
| `depends_on` | no | List of job ids that must complete first |
| `depth` | pipeline only | `simple` (1 agent), `comparative` (3), `deep` (5) |
| `max_subagents` | pipeline only | Cap on fan-out (hard max 20) |

### Prompt expansion

Use `{{file:./relative/path}}` in `prompt` or `query` to inline file contents relative to the manifest directory.

## Execution modes

### Realtime (`mode: realtime`)

- Executes immediately via chat completions API
- Required for Perplexity (no batch API)
- Best for deep research needing live web data
- Typical latency: seconds to 20+ minutes for deep research

### Batch (`mode: batch`)

- Submits to provider async Batch API
- ~50% cost discount, up to 24h SLA
- Supported: OpenAI, xAI (Grok), Anthropic
- Run exits with `waiting_batch` status; collect later:

```bash
meta-batch collect <run_id>
```

## Multi-stage pipeline

Job type `deep_research_pipeline` runs the following layers (Phase 2 enhancements: critic/ratchet + program + bounded reflection):

1. **Triage** — cheap model classifies query and builds research brief (program.md injected if present)
2. **Fan-out** — parallel deep research subagents (count capped by `depth`; each sub instructed re: downstream critic + "controller will dispatch reviewers")
3. **Critic/Verifier + Ratchet (post-fanout)** — heuristic citation verify + quality; only keep verified high-signal subs (Karpathy ratchet: monotonic improve only)
4. **Synthesis** — merge (program injected)
5. **Ratchet on draft (post-synth)** — split sections, apply_karpathy_ratchet (only verifiable improvements kept; low-signal/cite-less dropped); optional store to research_memory citation graph if available
6. **Reflection** — gap detection; re-roll loop max 2 (not 1); program injected; follow-up subs also use wrapped prompts
7. **Final ratchet** — ensure output after any replan is still ratcheted

Program support: job.metadata.program = "file:program.md" (or literal) for persistent instructions prefixed to stage prompts.

Depth tiers prevent overspawning (PRD failure mode):

Depth tiers prevent overspawning (PRD failure mode):

| Depth | Max subagents | Effort |
|-------|---------------|--------|
| simple | 1 | medium |
| comparative | 3 | high |
| deep | 5 | high |

## CLI reference

```bash
meta-batch validate jobs.yaml
meta-batch run jobs.yaml [--wait] [--output-dir DIR] [--run-id ID]
meta-batch status [run_id]
meta-batch collect <run_id>
meta-batch resume <run_id> [--wait]
```

State database: `~/.meta-utilities/batch-orchestrator.db` (override with `--db` or `BATCH_ORCHESTRATOR_HOME`).

## MCP tools

| Tool | Purpose |
|------|---------|
| `submit_batch` | Run a manifest |
| `get_batch_status` | Poll run status |
| `collect_batch_results` | Collect provider batch results |
| `run_research_pipeline` | Inline single-query pipeline |
| `list_batch_runs` | List recent runs |

## Installation

```bash
uv tool install -e /path/to/meta-utilities/mcp-servers/batch-orchestrator
ln -sfn /path/to/meta-utilities/skills/batch-research ~/.grok/skills/batch-research
```

Register MCP via `templates/grok/full-recommended.toml` or `templates/cursor/mcp.json`.

## Example manifest

See [templates/batch/jobs.example.yaml](../templates/batch/jobs.example.yaml).

## Related

- [PRD.md](../PRD.md) — multi-agent research architecture rationale
- [mcp-servers/deep-research/README.md](../mcp-servers/deep-research/README.md) — single-shot deep research
- [skills/batch-research/SKILL.md](../skills/batch-research/SKILL.md) — agent discovery skill

## Deep Research Multi-Stage Pipeline (2026-06-04 enhancement)
See templates/batch/jobs.research-deep-pipeline.yaml for planner → parallel-deep (or firecrawl) → critic-ratchet (Karpathy monotonic + citation verify in pipeline.py) → synth-with-rag (context-forge compress + research-memory recall) → persist-memory.

Supports program.md , use_memory, firecrawl_enabled.

Run: meta-batch validate ... ; meta-batch submit ... --topic "..."

Advances orchestration (goal 4), quality via ratchet (1), memory (2), tokens via RAG (3).

See docs/superpowers/plans/2026-06-04-deep-research-enhancement.md and docs/deep-research-architecture.md .

## Phase 3 Polish + Dogfood (Full Integration)

Ratchet wired in engine + pipeline (after fanout and final synth). Memory/firecrawl flags from manifest.defaults passed through to deep calls and RAG stages. measure_research_metrics used post-pipeline for citation/recall/token %.

Dogfood (see plan): meta-batch on research-deep-pipeline with topic "completion of ... plan" observes ratcheted sections only, prior artifacts recalled (Weaviate etc), tokens reduced, citations verified.
