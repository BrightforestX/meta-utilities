# Deep Research Architecture (2026-06-04 Enhancement)

**Status**: Production-grade, portable, self-dogfooded in meta-utilities. Balances all 4 goals from the design spec:
1. Quality/verifiability (critic + Karpathy ratchet: only monotonic verified improvements kept)
2. Persistent memory + recall (citation graphs, RAG over prior artifacts via research-memory + PARA)
3. Token/latency wins (real turbovec/Weaviate via context-forge hybrid RAG + compress-output with tiktoken)
4. Multi-stage orchestration (batch-orchestrator YAML DAGs: planner → parallel → critic/ratchet → synth)

All long-running steps use **two-layer timeouts** (client env e.g. DEEP_RESEARCH_TIMEOUT_SEC + host `tool_timeouts` in `.grok/config.toml` / Cursor). Self-dogfood first on this repo's docs/, plans/, skills/, mcp-servers/. Skill thin, MCP heavy. $META_UTILITIES_HOME + uv everywhere per AGENTS.md.

## High-Level Flow (Mermaid)

```mermaid
flowchart TD
    U[User / Agent<br/>or batch manifest<br/>topic + flags: use_memory, firecrawl_enabled] -->|query| D[deep-research skill<br/>or MCP<br/>(deep_research_mcp.py)]
    BM[Batch Manifest<br/>(templates/batch/jobs.research-deep-pipeline.yaml)] -->|meta-batch submit| BO[batch-orchestrator<br/>engine + pipeline]

    D -->|optional| CF[Context Forge<br/>smart_retrieve / semantic_search<br/>+ compress-output.py]
    D -->|optional RAG| RM[research-memory MCP<br/>search_prior_reports<br/>+ citation_graph<br/>(PARA + turbovec/Weaviate)]
    D -->|if firecrawl_enabled| FC[Firecrawl CLI/MCP<br/>search for initial grounding<br/>(before or parallel to perplexity)]

    CF --> RAG1[RAG context + token-compressed prior]
    RM --> RAG2[Prior artifacts + citation graph recall]
    FC --> GND[Grounding snippets injected to prompt]

    RAG1 & RAG2 & GND --> PL[Planner / Triage<br/>(decompose to sub-queries<br/>+ program.md)]

    PL --> PAR[Parallel Researchers<br/>(deep_research or Firecrawl sub-calls<br/>fan-out N sub-queries)]

    PAR --> CR[Critic / Verifier<br/>(CRITIC_PROMPT + verify_citations + compute_quality)]
    CR --> RT[Karpathy Ratchet<br/>(apply_karpathy_ratchet:<br/>keep ONLY if citation-verified<br/>AND quality > prior baseline;<br/>monotonic, no regression)]

    RT --> SY[Synth + RAG/Compress<br/>(merge, dedup, inject compressed memory,<br/>final ratchet pass)]

    SY --> REP[Structured Report<br/>+ citations + rag_context + metrics<br/>+ ratchet_decisions table]
    REP -->|store| RM2[research-memory<br/>store_research_artifact<br/>(+ optional vector index)]
    REP -->|update index| CF2[Context Forge index<br/>(turbovec / Weaviate)]

    subgraph "Two-Layer Timeouts (everywhere)"
    T1[Client: DEEP_RESEARCH_TIMEOUT_SEC=900<br/>FIRECRAWL_TIMEOUT_SEC=60<br/>RESEARCH_MEMORY_TIMEOUT_SEC=120]
    T2[Host: tool_timeouts in grok/config.toml<br/>or Cursor (e.g. 1800s for deep_research)]
    end
    T1 & T2 -.-> D & BO & RM & CF & FC

    style D fill:#e6f3ff
    style RT fill:#fff4e6,stroke:#f90
    style REP fill:#e6ffe6
```

## Component Responsibilities (No Duplication)

- **deep-research MCP** (`mcp-servers/deep-research/deep_research_mcp.py`): Core long-running provider calls (perplexity primary). First-class optional hooks (Phase 3): `use_memory=True` (default), `firecrawl_enabled`, `memory_mcp_url`. Computes `_get_rag_context` early (real context-forge compress via importlib portable, real research-memory recall via sibling import, real firecrawl `search` CLI for grounding). Injects to messages + prepends to returned report. Always surfaces `rag_context` + `firecrawl` in result (even error paths for audit). Two-layer docstring + env.

- **Context Forge** (`skills/context-forge/`): The intelligence layer. `compress-output.py` (tiktoken-aware, --stats, --max-tokens) for all token wins. `index-with-turbovec.py` (real sentence-transformers optional + Weaviate BYOV backend). mcp_server_example exposes semantic_search / compress_text for RAG in pipelines. Self-dogfood on meta-utilities corpus.

- **research-memory MCP** (`mcp-servers/research-memory/`): Thin PARA store for artifacts (json + .md sidecar) + citation graphs (inbound/outbound resolve of stored ids + urls). search_prior_reports (keyword + weaviate/turbovec vector if env). Leverages context-forge patterns for vector (no dup). CLI for dogfood (`research-memory search --query ...`). Pre-registered in templates.

- **batch-orchestrator** (`mcp-servers/batch-orchestrator/`): Durable multi-stage via YAML. `pipeline.py` has triage, fanout (deep or firecrawl), reflection + **critic/ratchet** (CRITIC_PROMPT, verify_citations, compute_quality, apply_karpathy_ratchet, split_report_to_sections, load_program). Engine wires ratchet stages + memory hooks from manifest defaults (use_memory, firecrawl_enabled). `meta-batch` CLI + MCP.

- **Firecrawl**: External (npm firecrawl-cli via `scripts/install-firecrawl.sh`; npx @mendable/firecrawl-mcp in host toml). Used for grounding/search/scrape/crawl. Two-layer timeouts pre-wired.

- **Skill layer** (thin): `skills/deep-research/SKILL.md` + `skills/research-memory/SKILL.md` + context-forge. Point to MCPs, document flags, examples. No heavy logic.

- **Templates / packaging**: `templates/grok/full-recommended.toml` pre-wires all (context-forge, research-memory, firecrawl, batch, deep with timeouts). `templates/cursor/mcp.json` + .example. `templates/batch/jobs.research-deep-pipeline.yaml` (planner → parallel+firecrawl → critic/ratchet → synth + persist). pyproject optional-deps for research/firecrawl extras. `scripts/measure_research_metrics.py` for citation pass / recall / token %.

## Key Invariants (AGENTS + Plan)

- **Portability**: $META_UTILITIES_HOME or __file__ sibling detection + uv --with / uvx / python -m. No oteemo paths. Hyphen scripts loaded via importlib.util.
- **Self-dogfood first**: All enhancements (RAG, ratchet, firecrawl grounding, metrics) demonstrated on meta-utilities/docs + plans + this architecture doc itself.
- **No fabrication**: Metrics from real compress / count / overlap. Ratchet drops unverifiable or non-improving.
- **Optional graceful**: sentence-transformers, weaviate, firecrawl key, etc. Fallbacks documented.
- **Two-layer everywhere**: Client env + host config + explicit in every long tool docstring / toml.
- **Skill/MCP separation**: Thin skill for invocation patterns + examples; heavy impl in mcp-servers/ (packaged, testable).
- **Metrics**: `scripts/measure_research_metrics.py` (TDD) + dogfood loops produce citation_pass_rate, recall_sim, token_reduction_pct, ratchet counts.

## Dogfood Loops (Observed in Phase 3)

- Pre-store artifact via `research-memory` CLI (or direct) containing "Weaviate + turbovec" notes.
- `python -m pytest tests/test_deep_research_mcp.py tests/test_deep_research_hooks.py tests/test_research_metrics.py -q` (all green).
- Enhanced deep-research call (with mocks or real keys) on "completion of 2026-06-04 deep research enhancement plan" surfaces prior turbovec/Weaviate RAG work in rag_context, uses firecrawl mock grounding, compress reduces tokens, ratchet (via batch) keeps only verified improved sections.
- `meta-batch validate templates/batch/jobs.research-deep-pipeline.yaml` passes.
- `scripts/measure_research_metrics.py --text "..." --prior docs/gap-analysis.md` shows pass_rate >0.5, recall >0, reduction %.

See `docs/superpowers/plans/2026-06-04-deep-research-enhancement.md` (completion note) + NEXT.md + gap-analysis.md for status (progress bumped to 80%+).

## Risks & Mitigations (from design spec)

- Optional bloat: graceful fallbacks + optionals in pyproject + external (npm for firecrawl).
- Timeout drift: explicit everywhere + templates.
- MCP reg friction: one-command uv tool + full-recommended toml + mcp.json.
- Weaviate conn: best-effort, keyword fallback always works.

This is the single source for how the enhanced deep research system works. Update on future phases.
