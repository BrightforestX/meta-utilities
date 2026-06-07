# research-memory-mcp

Thin specialized MCP for research artifact memory (PARA files + citation graphs + RAG over Weaviate/turbovec via context-forge patterns).

Common vector glue (embedder, weaviate client/ensure, basic turbovec load/save) is in the shared canonical `skills/context-forge/scripts/vector_backends.py` (imported at runtime for in-repo runs; minimal fallback copy used only for pure standalone `uvx` per AGENTS self-contained mcp-servers rule — research/citation/PARA logic here is never duplicated).

## Install (portable)
```bash
uv tool install -e mcp-servers/research-memory
research-memory --help
# or uvx research-memory
```

## Tools (MCP)
- `store_artifact(artifact, tags=None, citations=None, metadata=None, ctx=None)` / `store_research_artifact(...)` (alias) — persist report (str or dict) to PARA files under research/artifacts/ + optional vector index (citations list[str] used for both external sources and internal prior artifact ids; no separate `sources` param).
- `retrieve_by_citation_graph(artifact_id)` — load artifact + build/expand citation graph (resolves prior stored 12-hex ids to nodes; external sources as "sources" edges).
- `search_prior_reports(query, top_k=5, use_vector=True, ctx=None)` — semantic (weaviate/turbovec if ready + flag) or keyword search over stored artifacts. High-signal RAG input (often piped to context-forge compress).
- `list_artifacts(limit=20, ctx=None)` — list most recent stored artifacts (ids, titles, tags, paths) for discovery / CLI.

## CLI (for dogfood / batch / smoke)
```bash
research-memory store --artifact docs/gap-analysis.md --tags meta-utilities,deep-research
research-memory search --query "turbovec weaviate integration"
research-memory graph --id a1b2c3d4e5f6
research-memory list --limit 5
```

## Integration
Register via `templates/grok/full-recommended.toml` (pre-registered; tool_timeouts include primaries + alias + list).
Call from deep-research (with use_memory=true) or batch pipeline stages.
Two-layer: RESEARCH_MEMORY_TIMEOUT_SEC (client, now enforced inside tool wrappers) + host tool_timeouts.

## Storage
- Human-readable: research/artifacts/*.json + *.md (PARA style). Root resolved via RESEARCH_MEMORY_HOME > CONTEXT_HOME > $META_UTILITIES_HOME/.context/research > ~/.context/research (portable, no hardcodes).
- Vector: Weaviate (if WEAVIATE_URL set; BYOV) or local turbovec research-memory.tvim + idmap (under indexes/).

See plan `docs/superpowers/plans/2026-06-04-deep-research-enhancement.md` for full architecture + dogfood.
AGENTS.md compliant (relative, uv, self-dogfood first, no leakage, two-layer documented).
