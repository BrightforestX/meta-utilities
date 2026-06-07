# Smart Retrieval in Context Forge

## Philosophy

The single biggest token waster in AI coding agents is "read the whole file" or "here's the entire codebase."

**Smart Retrieval** replaces this with precise, high-signal extraction:

- **Symbolic / Structural retrieval** (preferred when possible): Extract only functions, classes, types, etc. using AST.
- **Semantic retrieval**: Vector similarity over code chunks or documentation when structural methods aren't sufficient.
- **Hybrid**: Use structural first, then semantic for related concepts.

Goal: Give the model exactly what it needs, nothing more.

## Core Techniques

### 1. Symbol-Level Extraction (Highest Leverage)

Use tree-sitter to parse code and extract specific symbols.

Recommended tools:
- `tree-sitter` CLI (fast, language-agnostic)
- `ast-grep` (excellent for structural search)
- Language-specific parsers when needed (e.g., `pyright`, `tsc --noEmit`)

Example workflow the agent should follow:

1. Identify the language of the target file(s).
2. Use the appropriate tree-sitter query or ast-grep pattern to extract the requested symbol(s).
3. Return only the relevant definition(s) + minimal surrounding context.
4. If the user asks for "the whole file," push back and ask which symbols or behaviors they need.

### 2. Semantic Code Search

When the user needs "things related to X" rather than a specific symbol:

- Maintain a lightweight index (can use turbovec, simple embeddings, or even ripgrep + reranking).
- Prefer chunking at function/class boundaries rather than fixed token windows.
- Combine with keyword search (BM25) for best results.

### 3. Just-in-Time Loading

Never preload entire directories unless explicitly asked.

Instead:
- Start with high-level structure (file tree + key symbols).
- Let the model request specific symbols or concepts.
- Use previous retrievals + memory to infer what is likely needed next.

## Implementation Guidelines for Agents

When a user asks you to "explore the codebase" or "find where X is implemented":

1. **Never** start by reading entire files.
2. First, get a high-level map (directory structure + important entry points).
3. Use structural search to locate the relevant symbols.
4. Retrieve only those symbols.
5. If more context is needed, retrieve related symbols (callers, types, etc.) surgically.

## Tooling Recommendations (General Projects)

- **Best general tool**: `ast-grep` (supports many languages, great query language).
- **Tree-sitter CLI**: Excellent for extraction.
- **For very large codebases**: Maintain a Context Forge index (see memory layer docs).

## Integration with Other Context Forge Layers

Smart Retrieval works best when combined with:
- Hierarchical Memory (remember which symbols have been important in the past)
- Vector Knowledge Layer (semantic search over documentation and code comments)
- Output Compression (compress the results of retrieval before injecting them)

This combination routinely achieves 80-95%+ token reduction on codebase interaction compared to naive "read everything" approaches.