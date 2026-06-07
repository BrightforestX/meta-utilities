# Context Forge — Cross-Tool Integration Playbooks

This document explains how to make the full default optimization stack feel native in Cursor, Claude Code, and Grok sessions.

---

## Cursor Integration

### 1. Connect the MCP Server

Add the Context Forge MCP server to your Cursor MCP configuration.

Example (in your Cursor settings or MCP config file):

```json
{
  "mcpServers": {
    "context-forge": {
      "command": "python",
      "args": [
        "$CONTEXT_FORGE_HOME/skills/context-forge/scripts/mcp_server_example.py" (or use the packaged MCP server)
      ],
      "env": {}
    }
  }
}
```

Restart Cursor after adding.

### 2. Recommended Project Rules

Add these to your project's `.cursorrules` or Cursor rules:

```
- Always use Context Forge's Smart Retrieval tools instead of reading entire files when possible.
- Prefer symbol-level extraction and semantic search over dumping large code sections.
- Consult the hierarchical memory system before doing broad codebase searches.
- Compress large tool outputs using the available compression tools before adding them to context.
- When the user asks about project architecture, decisions, or concepts, check the turbovec-indexed knowledge base first.
```

### 3. Best Practices in Cursor

- Use the MCP tools directly in chat (`@context-forge` or via the tool palette).
- For very large projects, rely heavily on the structural retrieval tool.
- Keep your `.context/config.yaml` in the project root so the MCP can read project-specific settings.

---

## Claude Code Integration

### 1. Connect the MCP Server

Similar to Cursor, add the same MCP server configuration in your Claude Code MCP settings.

### 2. Project Rules / CLAUDE.md

Add strong guidance in your project's `CLAUDE.md` or equivalent:

```markdown
## Context Management (Context Forge)

- Default to using Context Forge Smart Retrieval for any code or knowledge exploration.
- Use the available MCP tools for memory lookup, compression, and precise retrieval.
- Maintain working memory in the current session but push important items to episodic/semantic memory.
- Never dump entire large files without first attempting structural or semantic retrieval.
```

### 3. Workflow Tips

- Start complex tasks by explicitly asking the model to use Context Forge tools.
- Periodically ask it to summarize the session into episodic memory.

---

## Grok Integration (This Skill)

### 1. Skill Activation

The `context-forge` skill is designed to be one of your most frequently auto-triggered or manually invoked skills.

Recommended triggers (already in the skill frontmatter):
- "context optimization"
- "token reduction"
- "smart memory"
- "optimize context"
- etc.

You can also just say: `/context-forge "help me set up the default stack on this project"`

### 2. Making It the Default Behavior

In your global or project `AGENTS.md` / rules, add:

```
When working on code or technical tasks, default to Context Forge patterns:
- Use Smart Retrieval instead of broad file reads.
- Maintain and consult hierarchical memory.
- Compress outputs before injecting into context.
- Leverage any turbovec indexes that exist in .context/knowledge/.
```

### 3. Session Starters

Good patterns:
- "Use Context Forge to help me explore this codebase efficiently."
- "Set up full default optimization using Context Forge for this session."

---

## Recommended Combined Workflow (Power User)

1. **Global**: Context Forge skill + MCP server always available.
2. **Per Project**: Run `enable-full-default.sh` (or the individual setup + indexing steps).
3. **Daily**:
   - In Cursor/Claude Code → Use MCP tools heavily.
   - In Grok → Let the skill guide behavior or invoke explicitly.
4. **Memory**: Treat the unified hierarchical memory (via Context Forge + para-memory-files backend) as the single source of truth.
5. **Knowledge**: Keep important docs indexed with turbovec and query them via the skill/MCP.

This combination gives you the highest practical token efficiency with the least context loss across all your AI coding tools.

---

**Next Evolution**

As we improve the MCP server and add more native tools (better turbovec support, memory consolidation commands, etc.), these playbooks will be updated.