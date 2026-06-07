---
name: batch-research
description: >
  Run YAML-driven batch queues of deep research and inference jobs with hybrid
  realtime/batch provider routing and multi-stage research pipelines.
  Trigger phrases: batch research, meta-batch, job manifest, research queue,
  batch inference, deep research pipeline, submit batch jobs.
  Slash command: /batch-research
---

# Batch Research Skill

Execute lists of research and inference jobs from a YAML manifest using the
**batch-orchestrator** MCP server or the `meta-batch` CLI.

## When to Use

- You have **multiple research or inference tasks** to run (not just one query)
- Jobs have **dependencies** (synthesize after research completes)
- You want **cost savings** via provider Batch APIs (`mode: batch`, ~50% off, 24h SLA)
- You need a **multi-stage deep research pipeline** (triage → fan-out → synthesis → reflection)

## Preferred Invocation (MCP)

```
submit_batch(manifest_path="/path/to/jobs.yaml")
get_batch_status(run_id="...")
collect_batch_results(run_id="...")   # when status is waiting_batch
run_research_pipeline(query="...", depth="deep", provider="perplexity")
```

## CLI (Scripting / CI)

```bash
meta-batch validate jobs.yaml
meta-batch run jobs.yaml
meta-batch status <run_id>
meta-batch collect <run_id>
meta-batch resume <run_id>
```

## Manifest Basics

See `templates/batch/jobs.example.yaml` in meta-utilities.

| Field | Values | Notes |
|-------|--------|-------|
| `type` | `deep_research`, `inference`, `deep_research_pipeline` | Job kind |
| `mode` | `realtime`, `batch` | Hybrid routing |
| `provider` | `perplexity`, `grok`, `openai`, `anthropic` | Per-job override |
| `depends_on` | list of job ids | DAG dependencies |
| `depth` | `simple`, `comparative`, `deep` | Pipeline fan-out tier |

## Realtime vs Batch

| Mode | When | Providers |
|------|------|-----------|
| `realtime` | Need results now; deep research with live web | Perplexity, Grok, OpenAI |
| `batch` | Bulk inference/synthesis; 24h OK; 50% cheaper | OpenAI, xAI, Anthropic |

Perplexity has **no batch API** — always use `mode: realtime`.

## Prompt Expansion

Use `{{file:./relative/path.md}}` in `prompt` or `query` fields to inline file contents.

## Output

Artifacts written to `output_dir` (default `./batch-results`):
- `{job_id}.json` — structured result
- `{job_id}.md` — report text (when applicable)

State persisted in `~/.meta-utilities/batch-orchestrator.db` for resume/collect.

## Integration

Canonical package: `meta-utilities/mcp-servers/batch-orchestrator/`

Register via templates in `templates/grok/` and `templates/cursor/`.

Full reference: `docs/batch-orchestration.md`
