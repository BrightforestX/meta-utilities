# Skill & MCP Installation Patterns for meta-utilities

## Recommended Ways to Use These Capabilities

### 1. Symlink (Best for Development / Personal Use)

```bash
# Grok Build
ln -sfn $META_UTILITIES_HOME/skills/context-forge ~/.grok/skills/context-forge
ln -sfn $META_UTILITIES_HOME/skills/deep-research ~/.grok/skills/deep-research

# Claude Code / Cursor (Claude)
ln -sfn $META_UTILITIES_HOME/skills/context-forge ~/.claude/skills/context-forge
ln -sfn $META_UTILITIES_HOME/skills/deep-research ~/.claude/skills/deep-research
```

### 2. Copy (For Portability Across Machines)

Copy the `skills/` subdirectories into your personal skill homes.

### 3. Dual .agents/ Layout (Following Paperclip Pattern)

For maximum compatibility, maintain a `.agents/skills/` mirror inside meta-utilities and point agents at it when possible.

### 4. MCP Servers

Preferred:
```bash
uv tool install -e $META_UTILITIES_HOME/mcp-servers/deep-research
```

Then register using the templates in `templates/`.

## Bootstrap Script

The recommended way for new projects:

```bash
bash $META_UTILITIES_HOME/scripts/bootstrap.sh /path/to/new-project
```

This sets up templates and prints the wiring instructions above.
