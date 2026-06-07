# Context Forge Configuration

## Philosophy

Configuration should be minimal by default but powerful when needed. The system must work well with zero configuration on most projects.

## Locations (in priority order)

1. **Project-specific** (highest priority)
   - `<project-root>/.context/config.yaml`
   - This file should usually be committed (or at least tracked in some way for the team).

2. **Global / User**
   - `~/.context/config.yaml`
   - `~/.config/context-forge/config.yaml`
   - Controlled by `$CONTEXT_HOME` environment variable

3. **Environment variables** (override everything)

## Recommended Minimal Config

Most users should start with almost nothing:

```yaml
# .context/config.yaml in project root

retrieval:
  prefer_structural: true
  max_symbol_size: 4000    # tokens

memory:
  backend: "para"          # or "forge" once we have a native backend
  auto_decay: true

compression:
  enabled: true
  default_strategy: "balanced"
```

## Full Configuration Reference (Planned)

```yaml
# Global settings
home: ~/.context                    # Can be overridden by $CONTEXT_HOME

# Retrieval
retrieval:
  engines:
    - structural
    - semantic
  structural:
    tool: "ast-grep"                # or "tree-sitter", "ripgrep", etc.
    max_results: 20
  semantic:
    provider: "turbovec"            # or "simple", "openai", etc.
    dimension: 384
    top_k: 15

# Memory
memory:
  backend: "para"                   # Current recommendation: leverage para-memory-files
  layers:
    - working
    - episodic
    - semantic
  decay:
    enabled: true
    half_life_days: 30

# Compression
compression:
  enabled: true
  strategies:
    - output
    - retrieval
    - history
  aggressiveness: "balanced"        # conservative | balanced | aggressive

# Vector / Knowledge
vector:
  default_store: "turbovec"
  stores:
    turbovec:
      bit_width: 4
      auto_persist: true

# Integrations
integrations:
  cursor:
    use_mcp: true
  claude_code:
    use_mcp: true
  grok:
    skill_first: true
```

## Best Practices for General Projects

- Start with almost zero config.
- Add project-specific rules only when you have clear, repeatable patterns.
- Keep the global config very conservative.
- Use `.context/ignore` (similar to `.gitignore`) to exclude generated code, large data files, etc.

## Environment Variables

- `CONTEXT_HOME` — overrides the global context directory
- `CONTEXT_CONFIG` — path to a specific config file
- `CONTEXT_LOG_LEVEL`

This design ensures Context Forge works immediately on any project while still allowing sophisticated per-project tuning.