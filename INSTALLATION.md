# Installation & Wiring Guide for meta-utilities

This document explains the recommended ways to make the capabilities in meta-utilities available to your AI agents (Grok Build, Cursor, Claude Code, etc.).

## 1. Quick Start (Recommended for Most Users)

```bash
# 1. Install MCP servers
uv tool install -e /path/to/meta-utilities/mcp-servers/deep-research
uv tool install -e /path/to/meta-utilities/mcp-servers/batch-orchestrator

# 2. Wire the skills (Grok example)
ln -sfn /path/to/meta-utilities/skills/context-forge ~/.grok/skills/context-forge
ln -sfn /path/to/meta-utilities/skills/deep-research  ~/.grok/skills/deep-research
ln -sfn /path/to/meta-utilities/skills/batch-research ~/.grok/skills/batch-research

# 3. (Optional) Same for Claude Code / Cursor
ln -sfn /path/to/meta-utilities/skills/context-forge ~/.claude/skills/context-forge
```

Then run the bootstrap in any new project:
```bash
bash /path/to/meta-utilities/scripts/bootstrap.sh /path/to/new-project
```

## 2. Alternative: Use the Bootstrap Script

The bootstrap script sets up templates and prints the exact wiring commands for your environment.

## 3. For Maximum Portability (Multiple Machines)

- Keep meta-utilities in a synced location (e.g. via Git or a dotfiles repo).
- Use the symlinks above on each machine.
- Or copy the `skills/` directories into your personal `~/.grok/skills/` and `~/.claude/skills/` folders.

## 4. Dual Layout Support (.agents/skills/)

Some agents prefer the `.agents/skills/` layout (following patterns from Paperclip and others). You can maintain a mirror if desired:

```bash
mkdir -p /path/to/meta-utilities/.agents/skills
ln -sfn ../skills/context-forge /path/to/meta-utilities/.agents/skills/context-forge
```

## 5. Environment Variable

Set `META_UTILITIES_HOME` or `CONTEXT_FORGE_HOME` in your shell for scripts that support it.

## Verification

After wiring:
- Run `/context-forge` in an agent.
- Run `/deep-research "test query with provider=grok"`.
- Run `meta-batch validate /path/to/meta-utilities/templates/batch/jobs.example.yaml`.
- Use MCP tool `submit_batch` or `run_research_pipeline` after registering batch-orchestrator.

Everything should work without referencing any old project-specific paths.

See `docs/batch-orchestration.md` for the full batch queue reference.
