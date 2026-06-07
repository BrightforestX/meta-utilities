#!/usr/bin/env python3
"""
Context Forge - MCP Server Reference Implementation

This is a significantly improved reference MCP server for Context Forge.

It exposes high-value tools that power the default optimization stack:
- Smart structural + semantic retrieval
- Hierarchical memory access
- Output compression
- (Future) Vector knowledge queries via turbovec indexes

Run it with:
    fastmcp dev $CONTEXT_FORGE_HOME/skills/context-forge/scripts/mcp_server_example.py

This is meant to be extended. The goal is to make Context Forge's capabilities
feel native inside Cursor and Claude Code.

TODOs for real implementation:
- Wire up actual tree-sitter / ast-grep for structural retrieval
- Add real turbovec loading and semantic search
- Connect to the user's actual memory backend (para-memory-files or native)
- Add persistence for working memory
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import sys
import os

# --- MCP SDK (assumes `mcp` package is installed) ---
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP SDK not found. This is a reference implementation.")
    print("Install with: pip install mcp")
    exit(1)


# =============================================================================
# Tool Implementations (Reference / Stub versions)
# =============================================================================

def smart_retrieve_symbol(file_path: str, symbol_name: str, context_lines: int = 2) -> str:
    """
    Extract a specific symbol (function, class, method, etc.) from a file.
    In a real implementation this would use tree-sitter or ast-grep.
    """
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"

    # Placeholder implementation
    return (
        f"[Smart Retrieval - Structural]\n"
        f"File: {file_path}\n"
        f"Symbol: {symbol_name}\n\n"
        f"(Real implementation would return only the definition of '{symbol_name}' "
        f"plus ~{context_lines} lines of surrounding context.)\n\n"
        f"Current stub: This tool dramatically reduces tokens compared to reading the whole file."
    )


def semantic_search(query: str, top_k: int = 8, scope: str = "project") -> str:
    """
    Semantic search over the project's knowledge base (ideally powered by turbovec).
    """
    return (
        f"[Smart Retrieval - Semantic]\n"
        f"Query: {query}\n"
        f"Scope: {scope}\n"
        f"top_k: {top_k}\n\n"
        f"(Real version would load the turbovec index from .context/knowledge.tvim "
        f"or similar and return the most relevant chunks with scores.)\n"
        f"This is one of the highest-leverage tools for large or long-lived projects."
    )


def get_memory_summary(layer: str = "semantic", max_tokens: int = 2000) -> str:
    """
    Return a compressed, high-signal view of a specific memory layer.
    """
    valid_layers = ["working", "episodic", "semantic", "procedural"]
    if layer not in valid_layers:
        layer = "semantic"

    return (
        f"[Hierarchical Memory]\n"
        f"Layer: {layer}\n"
        f"Max tokens: {max_tokens}\n\n"
        f"(Real implementation would read from the configured memory backend "
        f"— typically your para-memory-files location or Context Forge's native structures — "
        f"and return a concise, high-signal summary.)"
    )


def compress_text(text: str, level: str = "balanced", max_tokens: int | None = None) -> str:
    """
    Real token-aware compression via compress-output.py logic (tiktoken + heuristics).
    Use in deep-research reports, tool outputs, before RAG injection.
    """
    # Import and delegate to the enhanced compressor (portable path)
    sys.path.insert(0, str(Path(__file__).parent))
    from compress_output import compress_text as _compress, count_tokens
    compressed, _, orig_t, comp_t = _compress(text, level, max_tokens)
    return f"[Output Compression - {level}, {orig_t}->{comp_t} tokens]\n{compressed}"


def search_knowledge_base(query: str, top_k: int = 6) -> str:
    """
    High-level semantic search over the project's indexed knowledge (docs, specs, decisions, etc.).
    This is intended to be backed by turbovec.
    """
    return (
        f"[Vector Knowledge Layer]\n"
        f"Query: {query}\n\n"
        f"(This tool loads the turbovec index and performs compressed semantic search. "
        f"It is dramatically cheaper and often more relevant than raw file search for conceptual questions.)"
    )


# =============================================================================
# MCP Server
# =============================================================================

server = Server("context-forge")

@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="smart_retrieve_symbol",
            description=(
                "Extract only the definition of a specific function, class, method, or type from a file. "
                "Uses structural (AST) analysis. This is the preferred way to explore code instead of reading entire files."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the source file"},
                    "symbol_name": {"type": "string", "description": "Name of the function/class/method to extract"},
                    "context_lines": {"type": "integer", "description": "How many lines of context around the symbol (default 2)"}
                },
                "required": ["file_path", "symbol_name"]
            }
        ),
        Tool(
            name="semantic_search",
            description=(
                "Perform semantic search over the current project or knowledge base. "
                "Use this when the user is asking about concepts rather than specific symbols."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 8},
                    "scope": {"type": "string", "enum": ["project", "knowledge", "memory"], "default": "project"}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="search_knowledge_base",
            description=(
                "Semantic search over the project's documented knowledge (architecture, decisions, specs, research, etc.). "
                "This is intended to be powered by a turbovec index for excellent compression + recall."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 6}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_memory_summary",
            description=(
                "Get a high-signal, compressed summary from one layer of the hierarchical memory system "
                "(working, episodic, semantic, or procedural)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "layer": {
                        "type": "string",
                        "enum": ["working", "episodic", "semantic", "procedural"],
                        "default": "semantic"
                    },
                    "max_tokens": {"type": "integer", "default": 2000}
                }
            }
        ),
        Tool(
            name="compress_output",
            description=(
                "Compress large tool outputs, logs, command results, or retrieval results before they are added to context. "
                "One of the easiest high-ROI token savers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "level": {
                        "type": "string",
                        "enum": ["conservative", "balanced", "aggressive"],
                        "default": "balanced"
                    }
                },
                "required": ["text"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    if name == "smart_retrieve_symbol":
        result = smart_retrieve_symbol(
            arguments["file_path"],
            arguments["symbol_name"],
            arguments.get("context_lines", 2)
        )
        return [TextContent(type="text", text=result)]

    elif name == "semantic_search":
        result = semantic_search(
            arguments["query"],
            arguments.get("top_k", 8),
            arguments.get("scope", "project")
        )
        return [TextContent(type="text", text=result)]

    elif name == "search_knowledge_base":
        result = search_knowledge_base(
            arguments["query"],
            arguments.get("top_k", 6)
        )
        return [TextContent(type="text", text=result)]

    elif name == "get_memory_summary":
        result = get_memory_summary(
            arguments.get("layer", "semantic"),
            arguments.get("max_tokens", 2000)
        )
        return [TextContent(type="text", text=result)]

    elif name == "compress_output":
        result = compress_text(
            arguments["text"],
            arguments.get("level", "balanced")
        )
        return [TextContent(type="text", text=result)]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())