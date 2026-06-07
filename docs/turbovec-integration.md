# turbovec Integration Guide

**turbovec** is the author's high-performance, high-compression vector library (Rust core + Python bindings using quantization — 2-bit / 4-bit, etc.).

It is a first-class citizen in this meta-utilities stack.

## Why turbovec?

Standard float32 embeddings are expensive in RAM and tokens. turbovec gives you 6-8x compression (or more) with excellent retrieval quality for many use cases.

## Recommended Integration Pattern

1. Store your durable semantic memory in human-readable form (PARA `life/`, `.context/knowledge/`, markdown files, etc.).
2. Periodically index the important parts with turbovec.
3. Use Context Forge + the turbovec index for fast semantic retrieval.
4. Fall back to full text / structural search when needed.

## How to Index

Use the helper in Context Forge:

```bash
python $META_UTILITIES_HOME/skills/context-forge/scripts/index-with-turbovec.py \
    ./life \
    --output .context/knowledge.tvim \
    --bit-width 4
```

See the script for more options.

## Using the Index

Once you have a `.tvim` file, Context Forge (and custom agents) can load it for fast vector search.

The deep-research system and general Context Forge workflows are designed to prefer the compressed index when available.

## Current Status in meta-utilities

- Integration scripts live in `skills/context-forge/scripts/`
- Documentation and best practices are being centralized here.
- The library itself remains in its primary development location.

## Weaviate Backend Support (BYOV + turbovec embed)

For distributed / cloud-scale semantic memory (beyond local .tvim), the indexer supports Weaviate as backend:

```bash
export WEAVIATE_URL=http://localhost:8080
export WEAVIATE_API_KEY=...
python $META_UTILITIES_HOME/skills/context-forge/scripts/index-with-turbovec.py \
    ./docs --backend weaviate --collection meta_knowledge --create-collection
```

- Uses `self_provided()` vectors (bring your own from sentence-transformers or hash fallback).
- Weaviate handles HNSW + optional PQ/BQ/RQ quantization server-side for further compression.
- Search via MCP `search_knowledge_base` (near_vector) or direct client.
- Config: templates/context/config.yaml + env fallbacks. Two-layer timeouts documented in templates/grok/*.toml.

## Grok Build CLI Pipeline Integration

Add to `~/.grok/config.toml` or project `.grok/config.toml` (from templates/grok/full-recommended.toml):

```toml
[mcp_servers.context-forge]
command = "python"
args = ["$META_UTILITIES_HOME/skills/context-forge/scripts/mcp_server_example.py"]
env = { WEAVIATE_URL = "${WEAVIATE_URL}", WEAVIATE_API_KEY = "${WEAVIATE_API_KEY}", COMPRESS_MAX_TOKENS = "4000" }
enabled = true
tool_timeouts = { semantic_search = 60, search_knowledge_base = 90, compress_text = 30 }
```

Then in Grok sessions: use `search_knowledge_base "topic"` for compressed RAG (avoids full context stuffing), pipe outputs through `compress --max-tokens 4000` in deep-research or batch pipelines. Self-dogfoods: index meta-utilities/docs/ for recall in research tasks.

## Tips

- Start with 4-bit for most knowledge bases.
- 2-bit can work surprisingly well for many retrieval tasks and saves even more memory.
- Keep the source files — the index is for speed, not the only copy of truth.
- For Weaviate dev: `docker run -p 8080:8080 -p 50051:50051 semitechnologies/weaviate:latest`

For the underlying library, see the turbovec crate and its Python bindings.

## Phase 0 Dogfood (Task 0.3)

Phase 0 dogfood: indexed docs/ + skills/ with real embedder (or hash fallback + WARN) → .turbovec/meta-utils.tvim ; see Task 0.3. (Local index; .gitignore'd or committed per size.)

Phase 0: real embedder ready (see Task 0.2 + 0.3 dogfood).

## Integration in Deep Research Enhancement (Phase 3)

Used by deep-research RAG hooks (`use_memory=True`): context-forge compress + index for token-efficient prior recall before calling perplexity. research-memory uses for vector backend (BYOV). batch pipelines fan out with RAG context. Metrics script exercises compress for reduction %.

See `docs/deep-research-architecture.md` for full mermaid + two-layer notes. Self-dogfood: enhanced deep-research on gap-analysis surfaces turbovec/weaviate artifacts from memory.
