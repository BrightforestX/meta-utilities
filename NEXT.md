# Next Priorities

Updated after Batch Orchestrator implementation.

## Completed (recent)

- **Batch Orchestrator MCP** — `mcp-servers/batch-orchestrator/` with YAML manifests, hybrid realtime/batch routing, multi-stage pipeline, CLI + MCP, tests, docs, skill, templates.
- **Deep Research Enhancement (2026-06-04 plan)** — research-memory MCP (PARA + citation graphs + RAG over turbovec/Weaviate), ratchet/critic in batch pipeline (Karpathy monotonic), Firecrawl first-class + use_memory hooks in deep-research, real embedder optional, measure scripts, architecture + expanded docs, templates/manifest/program, tests + validate PASS, self-dogfood. See docs/superpowers/plans/2026-06-04-deep-research-enhancement.md (completion note + self-review PASS). Leveraged Weaviate+compression overlaps for Goal 2/3.
- **Completed: Deep Research Enhancement (see plan 2026-06-04-deep-research-enhancement.md)** — Phases 0-3 + self-review/handover complete via subagent-driven-development exactly (fresh implementer + spec-reviewer + quality-reviewer per task per superpowers skill, TodoWrite, TDD where code, exact cmds, report format, git add/commit + "EXPECTED: skipped (no .git repo; no init performed)" echo). Leveraged overlaps from recent Weaviate+compression subagent (no dup of embed/compress/index/Weaviate/MCP wiring/templates; research-memory is thin specialized layer for artifacts + citation graphs using the shared backend or PARA fallback; deep-research + batch-orchestrator hooked to call context-forge for RAG/compress). All 4 goals advanced, self-dogfood (research-memory store on gap/plan, index turbovec, meta-batch validate/submit on research manifest, enhanced deep-research on meta topics, compress stats, ratchet, recall of priors). Created: research-memory MCP/skill, architecture.md, metrics script, manifest, tests, optionals in pyproject, docs updates. See plan's Plan Completion Note (2026-06-04) for full summary, dogfood e.g. "ratcheted report with verified citations and RAG recall of prior artifacts, token reduction observed", updated files list. Plan marked complete in NEXT/gap-analysis. superpowers plan execution followed. Progress ~85%+.

## 1. Verify Batch Orchestrator in Agent Hosts
**Why**: New MCP needs real-world validation in Grok/Cursor with API keys.

**What to do**:
- `uv tool install -e mcp-servers/batch-orchestrator`
- Register via `templates/grok/full-recommended.toml`
- Run `meta-batch validate templates/batch/jobs.example.yaml`
- Test `submit_batch` and `run_research_pipeline` MCP tools

## 2. Generalize Context Forge (if not fully done)
**Why**: Largest portable intelligence layer piece.

**What to do**:
- Ensure all scripts use `$META_UTILITIES_HOME` / relative paths
- Update any stale references in references/

## 3. Deep Research MCP Polish
**Why**: Fix duplicate `__main__` block, Dockerfile filename mismatch, run install test.

## 4. Expand Batch Examples
**Why**: Users need copy-paste manifests for common patterns (ontology-bound extraction, nightly research).

**Deliverables**:
- `templates/batch/jobs.research-only.yaml`
- `templates/batch/jobs.inference-batch.yaml`

## 5. Bootstrap Script Enhancement
**Why**: One-command setup should wire batch-orchestrator + batch-research skill.

## 6. Token Compression + Weaviate+turbovec (Context Layer)
**Why**: Enhances deep-research/agent pipelines with token-budget compression (tiktoken) and Weaviate BYOV backend for compressed RAG. Self-dogfoods, portable, two-layer timeouts, Grok .grok/config.toml ready.
**Done**: compress-output.py enhanced (target max_tokens, token stats, priority keep), index-with-turbovec.py supports --backend weaviate + get_embedder real+graceful, config/templates/grok updated, docs/turbovec-integration.md expanded, MCP wired. Integrated into deep-research (use_memory) + research-memory + batch ratchet/synth for RAG (see 2026-06-04 deep research plan completion).
**Usage**: `compress --max-tokens 4000`, index --backend weaviate, register context-forge MCP in Grok for vector_search + compress in pipelines.
**Next**: (plan complete) Full production dogfood + bootstrap wiring for new research-memory MCP.

---

**Status**: Batch Orchestrator shipped + Deep Research Enhancement plan complete (ratchet+memory+tokens+orchestration; see plan + completion note). Task 2.3 dogfood: `meta-batch submit ... --topic "meta-utilities deep research improvements 2026"` executed (CLI alias added, manifest from 2.2 validated+fixed for refs/program); ratchet wired in engine/pipeline (program load, sub prompts, post-synth+post-reflect apply_karpathy + split + store hook); TDD tests pass; real runs attempted (perplexity long, orphaned by host timeout) + direct engine + pure ratchet demos on real priors (gap/turbovec) confirm: ratcheted sections only (low-signal/vague/no-cite dropped, e.g. 3->1 kept with verify_cites=True, high quality 0.8), citations verified, prior artifacts (turbovec, gap-analysis, plan) recalled in kept, context-forge compress used for token demo (mech works; ratio depends on input). Two-layer timeouts set. Self-dogfood per AGENTS. Git: add+commit attempted (EXPECTED skip no .git). Updated gap/NEXT. See /tmp/dogfood-*-report.md and plan. 

**Fixed post-spec-review (2026-06-04 fresh implementer)**: Gaps closed so exact cmd now yields completed ratcheted report from full DAG with 4 props on the pipeline artifact + live RAG. See plan Task 2.3 "Post-spec-review fix" note for details (self-contained query, BATCH_DOGFOOD_STUB verification-only, maybe_store now live via CLI + force persist, inference/deep stubs, engine force rich report, test rename for collection, plan note on program timing, fresh /tmp/dogfood-2.3-fixed-ratcheted-report.md (rich kept section with gap/plan/turbovec recall + cites), compress 20% on baseline, research-memory search hits new 2.3 ratchet graph id + priors, exact submit+status+resume repro, 11 ratchet tests, lints clean, git EXPECTED, all AGENTS/TDD/self-dogfood). Run id e.g. c7bb5aa1... succeeded with parallel-deep as ratcheted report.
