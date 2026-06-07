# Memory & Orchestration (P5)

Per plan risk alignment (locked):
- Memory: reuse existing meta-utilities stack (research-memory MCP + context-forge + turbovec/PARA) as primary.
  - No duplicate Weaviate schema or memory subsystem for ODRS.
  - Optional adapters only for ODRS-specific deltas (e.g. run_id -> report artifact recall) if baseline retrieval is insufficient.
- Orchestration: extend existing batch-orchestrator (YAML manifests for replicate fan-out, seed sweeps, pooled synthesis).
  - No parallel orchestrator implemented.

Example manifest (templates/scenario-replicates.example.yaml) can be submitted via meta-batch for 100-1000 agent bounded scale with orchestrated seeds.

Scale validated in bounded runs; 100-1000 agents target per plan non-goals.
