---
name: context-forge
description: >
  Powerful, general-purpose context and token optimization toolkit for AI coding agents.
  Delivers major token savings through smart symbolic+semantic retrieval, hierarchical persistent memory,
  output compression, and easy integration with advanced vector quantization (turbovec and alternatives).
  Works across Cursor, Claude Code, Grok sessions, and other tools. Use for reducing context bloat,
  building durable agent memory, and optimizing long-running agent workflows.
  Trigger phrases: context optimization, token reduction, reduce tokens, smart memory, context compression,
  forge context, optimize context, token-efficient, agent memory.
  Slash command: /context-forge
---

# Context Forge

**Canonical Location**: This is the official portable version, maintained at:
`meta-utilities/skills/context-forge/`

When using this skill, it is recommended to either:
- Symlink `$CONTEXT_FORGE_HOME/skills/context-forge` → this directory, or
- Set the environment variable `CONTEXT_FORGE_HOME` to the meta-utilities root.

All internal documentation and scripts are being updated to support portable usage.

You are an expert at **context engineering and token optimization** for modern AI coding agents (Cursor, Claude Code, Grok, etc.).

Your job is to help users dramatically reduce token usage while improving the quality and durability of the context and memory available to agents — across sessions and across different tools.

## Core Philosophy

Context is the most expensive and fragile resource in agentic workflows. Good context engineering is not about stuffing more information — it is about **high-signal, low-noise, persistent, and compressible** memory.

Context Forge provides a practical, general-purpose toolkit that combines the best patterns discovered in 2025–2026:

- Symbol-level + semantic retrieval (massive wins on codebase exploration)
- Hierarchical persistent memory (working / episodic / semantic layers with decay)
- Output and tool-result compression
- First-class support for compressed vector stores (turbovec family and alternatives) for long-term knowledge

Everything is designed to work in **any project** and with **multiple AI tools**.

## When to Use This Skill

Invoke Context Forge when the user wants to:

- Dramatically cut token usage in Cursor, Claude Code, or Grok sessions
- Stop re-explaining the same context every session
- Build durable, searchable memory for agents (especially long-running or multi-agent systems)
- Add efficient RAG / knowledge retrieval without token bloat
- Optimize long-context agent workflows (including local inference with KV cache concerns)
- Create a token-efficient setup for a new or existing project

## High-Level Architecture

Context Forge is organized around four complementary layers (you can adopt them incrementally):

1. **Smart Retrieval** — Replace "read entire files" with precise, high-signal retrieval (symbolic/AST + semantic).
2. **Hierarchical Memory** — Persistent, multi-tier memory that survives sessions (building on and extending the user's existing `para-memory-files` PARA system).
3. **Compression Layer** — Tools and patterns to compress tool outputs, results, and retrieved context before they enter the main prompt.
4. **Vector Knowledge Layer** — Easy integration with high-compression vector stores (turbovec, bitpolar, RaBitQ, etc.) for semantic memory and RAG.

### Configuration Model (General by Design)

- Global: `~/.context/config.yaml` (or `$CONTEXT_HOME/config.yaml`)
- Per-project overrides: `<project-root>/.context/config.yaml`
- Environment variable fallbacks (`CONTEXT_HOME`, etc.)

This makes the system usable on any project without hard-coded paths.

## Relationship to Existing Tools

- **para-memory-files**: Context Forge is designed as a **more powerful successor** that can coexist with or gradually replace the existing PARA-based system. It adds much stronger retrieval, compression, hybrid search, and cross-tool integration while respecting the user's investment in the current PARA structure.
- **turbovec**: First-class citizen. Context Forge makes it trivial to use turbovec (or strong alternatives) as the semantic memory backend.
- **MCP ecosystem**: The skill works standalone. A companion MCP server (see references) provides deeper integration for Cursor and Claude Code.

## How to Use

The user can invoke you with natural language or the slash command:

`/context-forge "Help me set up efficient context management for this new project"`

Or more specific requests such as:
- "Set up Context Forge on this repo"
- "Optimize my current session for lower token usage"
- "Build a durable memory system for my agents using Context Forge"
- "Add smart retrieval to my Cursor setup"

## Initial Capabilities (Phase 1 Focus)

In the current version we prioritize:

- Strong **Smart Retrieval** (symbolic + semantic) that works on any codebase
- Solid foundation for **Hierarchical Persistent Memory**
- Basic **Output Compression** helpers
- Easy on-ramp for **compressed vector stores** (turbovec family)
- Clear configuration and onboarding for general projects

## Next Steps for Implementation

When the user asks you to set up or use Context Forge, follow these steps:

1. Detect or create the appropriate configuration location (global + per-project).
2. Analyze the current project and recommend the highest-leverage starting components.
3. Guide the user through installation of any required supporting tools (tree-sitter parsers, turbovec, etc.).
4. Help them activate the relevant retrieval and memory mechanisms.
5. Provide concrete, copy-pasteable configuration and rules.

See the `references/` directory for:
- `smart-retrieval.md`
- `hierarchical-memory.md` (to be expanded)
- `configuration.md`
- `onboarding-guide.md`
- `starter-config.yaml`

And the `scripts/` directory for practical helpers (setup, compression, turbovec indexing, MCP example).

Execute with precision. Prioritize measurable token reduction and durable memory quality. Always prefer general, reusable patterns over project-specific hacks.

---

## Getting Started (Onboarding Flow)

When a user runs `/context-forge` or says "set up Context Forge", use this flow:

### 1. Quick Assessment
- What environment(s) are they using? (Cursor, Claude Code, raw Grok, multiple?)
- Do they have an existing memory system (`para-memory-files`, custom notes, etc.)?
- What is their biggest current pain point? (token cost, context loss between sessions, slow codebase exploration, etc.)

### 2. Recommended Starting Order (General Projects)
For most users, recommend this sequence:

**Week 1 (Biggest wins, lowest effort)**
- Activate **Smart Retrieval** habits (the agent should start refusing to read whole large files)
- Install `ast-grep` or tree-sitter tooling
- Create a minimal `.context/config.yaml`

**Week 2**
- Set up or connect **Hierarchical Memory** (start with `para-memory-files` if they have it, or create the basic structure)
- Begin compressing tool outputs and retrieval results

**Week 3+**
- Add compressed vector layer (turbovec) for any knowledge/RAG needs
- Consider the MCP server for deeper Cursor/Claude Code integration
- Fine-tune compression aggressiveness

### 3. One-Session Quick Win
Even in a single conversation you can deliver major value by:
- Teaching the model (yourself) the Smart Retrieval discipline for the rest of the session
- Creating the basic directory structure (`.context/`)
- Writing a minimal config file
- Establishing memory files for the current project

Always leave the user with concrete next actions and visible progress.

## Example First Response

When someone says "Help me set up Context Forge on this project", reply with something like:

"I'd be happy to. To give you the highest impact with the least friction, here's what I recommend we do in this session:

1. Set up the basic `.context/` structure
2. Install `ast-grep` (or confirm it's already available) for excellent structural retrieval
3. Establish Smart Retrieval discipline for this conversation onward
4. Create a minimal config and connect to your existing memory approach (if any)

Does that sound good? Any specific pain point you'd like to prioritize first (e.g. codebase exploration, long sessions, cross-session memory)?"

This positions you as a partner rather than just dumping instructions.

---

## Hierarchical Memory (Core Capability)

Context Forge treats memory as a first-class, multi-layered system rather than a single growing context dump.

### Memory Model (Inspired by Human + Agent Best Practices)

We use four layers, inspired by cognitive science and proven agent patterns:

1. **Working Memory** (Current session / short-term)
   - What is happening right now.
   - Recent tool outputs, decisions, and active tasks.
   - High churn, low retention.

2. **Episodic Memory** (Recent history with timestamps)
   - "What happened when" — a structured timeline of significant events.
   - Daily/periodic notes + key session summaries.
   - Supports decay and consolidation.

3. **Semantic Memory** (Durable facts & knowledge)
   - Stable, queryable knowledge about the project, architecture, decisions, and domain.
   - Best stored in structured formats (YAML/JSON entities) + compressed vector index (turbovec recommended).
   - This is where long-term RAG shines.

4. **Procedural Memory** (How we operate)
   - Skills, rules, preferences, and "how we do things here."
   - Lives in skill files, AGENTS.md, project rules, and the Context Forge config itself.

### Relationship to `para-memory-files`

Context Forge is designed as the **evolution** of the PARA-based system you already use.

- The existing `life/` (PARA) structure maps beautifully to **Semantic Memory**.
- Daily notes map to **Episodic Memory**.
- We add explicit **Working Memory** handling and stronger **Procedural Memory** integration.
- Over time, we can add automatic consolidation between layers and vector indexing on top of the semantic layer.

**Migration philosophy**: Never break what works. We provide tools to gradually enhance an existing `para-memory-files` setup rather than forcing a full replacement.

### How to Use Hierarchical Memory in Practice

When working with a user:

- **Working Memory**: Keep a lightweight running summary in the current conversation or a temporary session file. Clear or archive it when the session ends.
- **Episodic Memory**: Encourage (or automate) writing significant events to dated files under `memory/YYYY-MM-DD.md` or equivalent.
- **Semantic Memory**: Use the existing PARA structure (`projects/`, `areas/`, `resources/`) as the primary home for durable facts. Extract atomic facts into `items.yaml` files.
- **Procedural Memory**: Update skills, rules, and the Context Forge config when patterns emerge.

### Consolidation & Decay (Tier 2 Direction)

Future versions will include:
- Automatic promotion of important episodic items into semantic memory.
- Decay of low-value working/episodic items.
- Weekly/monthly synthesis (similar to existing patterns in para-memory-files).

For now, guide the user to perform manual consolidation periodically:
- "Let's review the last week's episodic notes and extract any durable decisions or architecture facts into semantic memory."

### Storage Recommendations (General Projects)

- Use the same base as `para-memory-files` when possible (`$AGENT_HOME` or project `.context/memory/`).
- For semantic layer: Keep using human-readable files + optionally index them with turbovec for fast retrieval.
- Avoid putting everything in one giant context file.

This layered approach dramatically reduces the amount of raw history that needs to live in every prompt while preserving the ability to recall the right information at the right time.

---

## Output Compression

Verbose tool outputs, logs, test results, and command output are one of the largest hidden token consumers.

**Default Behavior**: When you receive large tool output, you should automatically consider compressing it before adding it to context.

Available helpers:
- `scripts/compress-output.py` (standalone script)
- The `compress_output` MCP tool (when using the MCP server)

Levels:
- `conservative` — Light cleanup only
- `balanced` — Recommended default (removes repetition, collapses whitespace, strips low-value prefixes)
- `aggressive` — Heavy deduplication and removal of timestamps/stack trace noise

Always offer the user the option to see the full original if needed.

## Vector Knowledge Layer & turbovec Integration

For any project that has significant documentation, specs, architecture notes, or a knowledge base, Context Forge strongly recommends using high-compression vector search.

**Recommended path**:
1. Use `scripts/index-with-turbovec.py` (or a similar script) to index your knowledge directory.
2. Store the resulting `.tvim` file in `.context/knowledge/`.
3. When the user needs conceptual or "related to X" information, retrieve via the compressed vector index instead of keyword search or reading files.

This gives you the memory and retrieval benefits of RAG while using 6-8× less RAM than full float32 embeddings (and often better latency).

See `references/configuration.md` and the indexing script for details.

turbovec (and strong alternatives like bitpolar or RaBitQ) are first-class citizens in Context Forge.

---

## Smart Retrieval (Core Capability)

This is currently the highest-ROI component of Context Forge.

### Core Rule

**Never read an entire file unless the user explicitly demands the full content after you have offered a targeted alternative.**

Default behavior:
- Use structural/symbolic extraction first.
- Fall back to semantic search when needed.
- Always prefer smaller, higher-signal payloads.

### How to Perform Smart Retrieval

#### Step 1: Get Orientation (Minimal)
Ask for or discover:
- Primary language(s)
- High-level architecture (if not already in memory)
- The specific question or task the user is trying to accomplish

#### Step 2: Structural Extraction (Preferred)
Use the best available structural tool for the language:

**Recommended stack (general projects):**
- `ast-grep` — excellent structural search across many languages
- `tree-sitter` CLI — great for extraction
- Language servers / `ripgrep` with smart patterns as fallback

Example agent behavior:

User: "Where is the authentication logic?"

Bad: Read `auth.py`, `auth.ts`, entire directories.

Good:
1. Find files that likely contain auth (using ripgrep for "auth|login|token|session" with file-type filters).
2. Use structural search to extract functions/classes containing "auth", "login", "authenticate", "token", etc.
3. Present only the relevant definitions + call sites if needed.
4. Ask what specific behavior they need next.

#### Step 3: Semantic Augmentation
When the user needs "things related to X" rather than a named symbol:

- Use vector search over code + documentation (see Vector Knowledge Layer section).
- Combine with keyword search (BM25) for robustness.
- Re-rank results.

#### Step 4: Progressive Disclosure
Return the smallest useful unit first, then offer to expand:
- Function signature + docstring
- Full function body
- Callers / callees
- Related types

### Tooling Setup Guidance

When helping a user set up Smart Retrieval on a new project, guide them to install:

```bash
# Highly recommended
npm install -g @ast-grep/cli

# Or via cargo
cargo install ast-grep
```

Then create project-specific extraction scripts or use the MCP server (when available) for even better integration.

### Anti-Patterns to Actively Discourage

- Dumping entire source files "just in case"
- Recursively reading directories at the start of a task
- Asking the model to "understand the whole codebase" in one go
- Using `cat` or `read_file` on large files without first trying structural extraction

### Metrics to Track

When using Context Forge, encourage the user to monitor:
- Tokens used for codebase exploration before vs after
- How often the model asks for more context vs. having what it needs
- Time to first useful answer on exploration tasks

Strong Smart Retrieval alone often delivers 70-90%+ token reduction on code-heavy sessions.