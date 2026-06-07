---
name: research-memory
description: >
  Thin skill/MCP wrapper for storing and recalling deep research artifacts with full citation graphs and RAG.
  Uses PARA files + Weaviate/turbovec (via context-forge integration) for persistent cross-session memory of reports.
  Prefer after /deep-research or batch research pipelines. Complements context-forge for general compression/RAG.
  Trigger: store research, recall prior report, citation graph, research memory.
---

# Research Memory

Thin discoverable layer over the `research-memory` MCP.

**Canonical**: `meta-utilities/skills/research-memory/` + `mcp-servers/research-memory/`

## When to use
- Persist a deep research report or section with sources/citations for future recall.
- Build citation graph for a report (what it cites + who cites it).
- RAG over prior research artifacts in same project/domain (e.g. "what did we conclude about turbovec last time?").
- In multi-stage pipelines or after long /deep-research.

## Usage
After research:
"Use research-memory to store this report with tags meta-utilities,deep-research 2026"

Recall:
"search_prior_reports for turbovec Weaviate in meta-utilities artifacts"

See mcp-servers/research-memory/README.md for tools + CLI.

Portable, AGENTS compliant, leverages context-forge Weaviate/compress (no dup).
Two-layer timeouts documented in templates/grok/full-recommended.toml .
Self-dogfood in meta-utilities first.
