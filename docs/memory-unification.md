# Memory Unification Strategy

**Goal**: Provide a clear path to evolve from `para-memory-files` into the richer Context Forge model (with turbovec) while preserving all existing investment.

## Core Philosophy

- **Never break what works.**
- `para-memory-files` is excellent prior art.
- Context Forge is a **powerful superset** — not a forced replacement.
- Adopt improvements gradually.

## The Four-Layer Memory Model

Context Forge recommends four layers:

1. **Working Memory** — Current session scratchpad (high churn)
2. **Episodic Memory** — Timestamped history (maps very well to daily notes in PARA)
3. **Semantic Memory** — Durable facts & knowledge (maps to PARA `life/` structure)
4. **Procedural Memory** — How we operate (skills, rules, preferences, configs)

`para-memory-files` already provides strong coverage of layers 2 and 3, plus some of layer 4.

## Recommended Approach: Evolve in Place

**Best path for most people**:

- Keep using your existing `para-memory-files` (or equivalent) as the primary storage for Episodic + Semantic memory.
- Use **Context Forge** as the intelligence + retrieval layer on top.
- Gradually introduce:
  - Better Working Memory handling
  - Stronger Procedural Memory via skills
  - turbovec vector indexing over your semantic layer

**Benefits**:
- Zero data migration risk
- Immediate wins from Smart Retrieval and compression
- You can start benefiting today

## Practical Steps

1. Run the Context Forge setup in your project (`scripts/setup-project.py` or via the bootstrap).
2. Point Context Forge at your existing PARA location in `.context/config.yaml`.
3. Start using `/context-forge` for retrieval instead of raw file reads.
4. Periodically run turbovec indexing over your `life/` or `knowledge/` directories.
5. Over time, let Context Forge become the primary way you interact with memory.

## Long-term Vision

Eventually you have one unified system where:
- PARA / file structure = durable storage
- Context Forge + turbovec = smart retrieval + compression + procedural guidance

This combination gives you the best of both worlds: human-readable durable memory + extremely efficient agent access.

See also:
- `skills/context-forge/references/memory-unification.md` (original detailed version)
- `para-memory-files` skill for the base layer

## Research-Memory Specialization (2026-06-04)
On top of unified PARA + Context Forge + turbovec, the thin `research-memory` MCP/skill provides research-artifact specific storage: store_artifact (or alias store_research_artifact) with citations/tags/metadata, citation graph resolve, search_prior_reports (vector/keyword) for RAG into deep-research or batch pipelines.

Uses same .context/research/ (or $META / CONTEXT_HOME), optional weaviate/turbovec (no logic dup from context-forge indexer).

See mcp-servers/research-memory/ , skills/research-memory/SKILL.md , and the deep research plan for integration (Phase 1+2 dogfood stores priors, ratchet/synth recall them).

Portable, two-layer timeouts (RESEARCH_MEMORY_TIMEOUT_SEC), uv packaged.

## Deep Research Full Integration (Phase 3)

research-memory is called from deep-research `_get_rag_context` (direct import hack for hooks, or via host MCP) and from batch ratchet/synth stages (store ratcheted artifacts + citation graphs). When use_memory, prior Weaviate/turbovec work is recalled and injected (see dogfood in plan: surfaces artifacts, ratchet keeps only verified).

See `docs/deep-research-architecture.md` (mermaid shows RM in flow) and `docs/gap-analysis.md` / NEXT for completion status.
