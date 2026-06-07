# Context Forge - Onboarding & Project Setup Guide

## One-Time Global Setup (Recommended)

```bash
# 1. Make sure the skill points to the canonical location in meta-utilities
#    (recommended: symlink or set CONTEXT_FORGE_HOME)
ls $CONTEXT_FORGE_HOME/skills/context-forge

# 2. (Optional but powerful) Install supporting tools
npm install -g @ast-grep/cli     # Excellent for structural code search
pip install turbovec numpy       # For vector compression / semantic memory
```

## Per-Project Setup (Run in any project root)

```bash
python $CONTEXT_FORGE_HOME/skills/context-forge/scripts/setup-project.py
# or simply run it directly if you are inside the meta-utilities checkout
```

This creates:
- `.context/config.yaml`
- `.context/memory/`
- `.context/knowledge/`
- `.context/.contextignore`
- `.context/README.md`

## Recommended Adoption Path

### Phase 1 — Quick Wins (1–2 sessions)
1. Run the setup script.
2. Start using Smart Retrieval discipline in your AI sessions (the agent will guide you).
3. Install `ast-grep` if you do a lot of code exploration.

Expected impact: 60-85% reduction in codebase exploration tokens.

### Phase 2 — Memory Foundation (1 week)
1. Connect Context Forge to your existing `para-memory-files` setup (or start using the `.context/memory/` structure).
2. Begin writing episodic notes for important sessions.
3. Use the `get_memory_summary` tool (via skill or MCP) regularly.

### Phase 3 — Advanced (Ongoing)
1. Enable turbovec-backed semantic search for your project's knowledge base.
2. Set up the MCP server for deep Cursor / Claude Code integration.
3. Tune compression levels and retrieval preferences in `.context/config.yaml`.

## Using with Different Tools

**Grok sessions**:
- Just use `/context-forge` naturally. The skill will guide behavior.

**Cursor / Claude Code**:
- Use the MCP server example for best results.
- Or rely on the skill + good project rules.

**Multi-tool workflows**:
- Keep memory in `.context/` (or your central `para-memory-files` location).
- All tools can read from the same source.

## Measuring Success

Track these metrics before and after adopting Context Forge:

- Tokens used for "explore the codebase" style tasks
- How often you have to re-explain project context
- Average context length of your sessions
- How "lost" the model feels after 50+ messages

Most users see 3-10x effective context efficiency within the first week.

## Need Help?

Run:
```
/context-forge "Help me finish setting up Context Forge on this project"
```

The skill will walk you through the remaining steps tailored to your environment and pain points.