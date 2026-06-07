# Deep Research Enhancement — Brief Design Spec (2026-06-04)

**Goals (equal priority):** 1. Report quality/verifiability (critique, Karpathy ratchet, citation verify, gap detect). 2. Persistent memory + agentic recall (citation graphs, replayable traces, cross-session RAG). 3. Token/latency wins (real turbovec embeddings, Context Forge hybrid RAG/compression). 4. Multi-stage orchestration (planner + parallel + critic + synth on existing batch-orchestrator YAML DAGs).

**Architecture Summary:** Layered, portable. Query → (Context Forge + research_memory RAG) → Planner → Parallel (deep-research or Firecrawl) → Critic/Verifier/Ratchet (only monotonic verified improvements kept) → Synthesizer (RAG+compress) → report + memory update. Two-layer timeouts everywhere. Skill thin, MCP heavy. $META_UTILITIES_HOME + uv everywhere. Self-dogfood on meta-utilities corpus first.

**2-3 Approaches + Tradeoffs + Rec:**
- Extend existing (batch pipeline + Context Forge + deep-research MCP): lowest risk, reuses durable YAML + turbovec hooks. Rec: yes.
- New heavy framework (e.g. LangGraph): YAGNI, violates portability/AGENTS.md. Reject.
- Pure in-memory ratchet without persistent memory MCP: loses goal 2. Reject.

**Key Proposals Integrated:** Real embedder (Phase 0), research_memory MCP (Phase 1), Karpathy ratchet + critic in pipeline (Phase 2), Firecrawl + full integration (Phase 3). Metrics: citation pass %, recall %, token reduction, ratchet improvement count, time-to-first-useful.

**Risks:** Optional deps bloat (mit: graceful), registration (mit: templates), timeout drift (mit: explicit doc in every long tool).

**Success:** After dogfood, enhanced deep-research on own gap-analysis surfaces prior artifacts, produces ratcheted higher-quality report with verified citations, using <50% tokens of baseline.

Approved for plan execution (this spec + writing-plans plan).