# AGENTS.md — meta-utilities

This directory is the canonical source for my personal AI meta-tooling (deep research MCP, context optimization via Context Forge, memory unification, turbovec integration patterns, long-running tool discipline, and portable configuration templates).

## Core Identity

- **Purpose**: Make world-class agent capabilities (research depth + massive token efficiency + durable memory) trivially portable to every new project.
- **Audience**: Me (primary), and selectively other power users or teams who want the same stack.
- **Tone**: Practical, high-signal, zero hype. Every artifact must earn its tokens.

## When Working Inside This Repo

1. **Always think in portability terms**.
   - Never introduce absolute paths tied to oteemo, Brightforest, or any single machine.
   - Prefer relative references inside skills/MCPs.
   - Use `$META_UTILITIES_HOME` (or script-location detection) + clear env var fallbacks.
   - When in doubt, make it work with `uv run`, `uvx`, or a simple `python -m` invocation.

2. **Follow the established skill + MCP separation**.
   - Heavy logic lives in `mcp-servers/` (especially anything long-running or that needs real dependencies).
   - Thin, discoverable behavior lives in `skills/`.
   - Configuration/templates are first-class citizens in `templates/`.
   - Batch job manifests live in project-specific YAML; see `templates/batch/jobs.example.yaml` and `docs/batch-orchestration.md`.

3. **Respect the two-layer timeout model for anything long-running**.
   - Client level (inside the MCP/tool, controlled by env like `DEEP_RESEARCH_TIMEOUT_SEC`).
   - Host/MCP level (`.grok/config.toml` `tool_timeouts`, Cursor equivalents).
   - Document both layers everywhere relevant.

4. **Memory & Context Forge discipline**.
   - Treat Context Forge as the intelligence layer on top of durable storage (PARA via para-memory-files or `.context/`).
   - Prefer structural + semantic retrieval over dumping whole files.
   - Compress before injecting large outputs.
   - Use turbovec for semantic layers when the corpus justifies it.

5. **Self-dogfooding is mandatory**.
   - If you're adding a new pattern, demonstrate it inside this repo (use context-forge on the new code, run deep research via the local MCP, etc.).
   - The bootstrap script must be able to set up a working environment for meta-utilities itself.

6. **Distribution & Installation**.
   - The source of truth is here.
   - Provide clear, tested paths for:
     - Symlinking/copying into `~/.grok/skills/`, `~/.claude/skills/`, `~/.agents/skills/`.
     - Packaging individual MCPs (`uv tool`, Docker, etc.).
     - One-command bootstrap for a brand-new project.
   - The ink assistant (`cli/<name>/`) is an opt-in Node surface (assistant-ui/react-ink TUI); it does not affect the Python-only bootstrap happy path or MCP-first usage.

## File Organization Rules

- `mcp-servers/<name>/` — Self-contained, packageable MCP servers (pyproject.toml + entrypoint preferred).
- `skills/<name>/` — SKILL.md + references/ + examples/ (keep frontmatter high-quality for auto-invocation).
- `templates/` — Copy-paste ready fragments (never project-specific). Includes `templates/batch/` for job manifests.
- `scripts/` — Automation that works from anywhere (bootstrap, installers, wrappers).
- `cli/<name>/` — Interactive terminal assistants / TUIs (Node + Ink + @assistant-ui/react-ink for chat/assistant flows over the MCP/CLI surfaces). Own package.json + bin. Opt-in Node runtime; documented separately from Python MCPs. Use the same portability discipline ($META_UTILITIES_HOME or walk-up, env fallbacks, uv/uvx for backend services). Assistants may stdio-spawn sibling MCP servers located under a broader tools/ layout (e.g. tools/mcp/px-mcp/px-mcp-ts for gsd-mcp-server providing Composio + Arcade business context proxies); discovery must be relative/env-driven and never hard-code personal or absolute paths.
- `docs/` — Rationale, patterns, and "how to use in a new project" guides. Link back to the original deep research report for history.

## Anti-Patterns

- Hard-coding any old oteemo paths or Axiom-specific examples without clear `examples/axiom/` scoping.
- Making the bootstrap or installers require heavy dependencies.
- Letting skills or MCPs assume they are only ever used inside this repo.

## Success Metric

A fresh machine + fresh project can reach "I have my full deep-research + context-optimization + memory stack" in under 10 minutes of commands + one tool restart, with zero leakage of old project assumptions.

Current progress is tracked in `docs/gap-analysis.md` and `NEXT.md`.

This file is itself dogfoodable — use Context Forge on it when making changes.
