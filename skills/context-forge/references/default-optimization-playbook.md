# Context Forge — Default Optimization Stack Playbook

**Goal**: Make heavy, high-quality token and context optimization the *default* experience across your entire workflow (Cursor, Claude Code, Grok, and future tools) with minimal ongoing effort.

This playbook represents the synthesized "best default setup" based on 2025–2026 research into tools like turbovec, Context Forge components, memory systems, and MCP tooling.

---

## The Exact Default Optimization Stack (Recommended)

### Always-On Core (This is the "Default Experience")

| Component                        | How It's Activated                  | What It Delivers                              | Priority |
|----------------------------------|-------------------------------------|-----------------------------------------------|----------|
| **Context Forge Skill**          | Always loaded in Grok sessions      | Orchestration, Smart Retrieval discipline, memory awareness, compression reflex | Critical |
| **Context Forge MCP Server**     | Running persistently (Cursor + Claude Code) | Native tools for retrieval, memory access, and compression inside the IDE | Critical |
| **Hierarchical Memory**          | Via Context Forge (backed by para-memory-files initially) | Working / Episodic / Semantic / Procedural layers with good recall | Critical |
| **Smart Retrieval (Structural + Semantic)** | Default behavior enforced by skill + MCP | Replace "read whole file" with precise symbol + semantic lookup | Critical |
| **Output Compression**           | Automatic via MCP or skill          | Compress large tool outputs before they hit context | High |
| **Global + Per-Project Config**  | `~/.context/config.yaml` + `.context/config.yaml` | Sensible defaults + project-specific tuning | High |

### Strongly Recommended (Auto-Enable Where Feasible)

- **turbovec-powered Vector Knowledge Layer**: Auto-index important knowledge folders (`docs/`, `specs/`, architecture notes, etc.) using turbovec. This becomes the semantic retrieval backend for long-term project knowledge.
- **Light KV Cache Awareness**: When you do local/long-context inference, default to using kvpress / HF QuantizedCache or TurboQuant-style methods.

### Opt-In / Advanced (Not part of the basic default)

- Full aggressive KV cache quantization pipelines
- Custom graph + vector hybrid layers beyond basic turbovec
- Heavy automation (e.g., automatic weekly memory consolidation hooks)

---

## One-Time Global Setup (Do This Once)

1. Ensure Context Forge skill is installed:
   ```bash
   ls $CONTEXT_FORGE_HOME/skills/context-forge
   ```

2. Install supporting tools (highly recommended):
   ```bash
   # Structural code search (huge win)
   npm install -g @ast-grep/cli

   # Vector compression
   pip install turbovec numpy

   # Optional but excellent for memory
   # (ensure your para-memory-files setup is healthy)
   ```

3. Create your global config (if it doesn't exist):
   ```bash
   mkdir -p ~/.context
   # Copy the starter global config from the skill
   cp $CONTEXT_FORGE_HOME/skills/context-forge/references/starter-config.yaml ~/.context/config.yaml
   ```

4. (Recommended) Set up the Context Forge MCP server to run persistently with Cursor and Claude Code.
   - See the example in `scripts/mcp_server_example.py`
   - Add it to your Cursor MCP config and Claude Code MCP config.

---

## Per-Project Setup (Run in Every New or Existing Project)

Run this in the root of any project you want optimized:

```bash
python $CONTEXT_FORGE_HOME/skills/context-forge/scripts/setup-project.py
```

This creates:
- `.context/config.yaml` (project overrides)
- `.context/memory/`
- `.context/knowledge/`
- `.context/.contextignore`
- Basic README

**Next (Strongly Recommended):**

Index your project's knowledge base with turbovec:

```bash
python $CONTEXT_FORGE_HOME/skills/context-forge/scripts/index-with-turbovec.py ./docs --output .context/knowledge.tvim --bit-width 4
# Or point it at specs/, architecture/, research/ folders, etc.
```

Update your project `.context/config.yaml` to point at the new index when you're ready.

---

## Making It Feel Native

### In Grok Sessions
- The `context-forge` skill should be one of your most frequently used skills.
- Start most technical sessions with `/context-forge` or simply let it trigger naturally.

### In Cursor
- Have the Context Forge MCP server connected.
- Add project rules that reinforce Smart Retrieval and memory usage.

### In Claude Code
- Same MCP server.
- Use project rules + the skill when working in Claude Code.

---

## Verification (Measure Your Wins)

After setting this up on a project, track:

- Tokens used for "explore the codebase / find where X is" tasks (before vs after)
- How often you have to re-explain project context across sessions
- Average context length at the end of long tasks
- Subjective "how lost does the model feel" after 100+ messages

Most users see dramatic improvements in the first week.

---

## Trade-offs & When to Dial It Back

- **Aggressive compression** can occasionally remove important nuance → Keep an easy "show me the full original" escape hatch.
- **Smart Retrieval** requires the agent to be disciplined → The skill + MCP tools help enforce this.
- **Multiple moving parts** (skill + MCP + turbovec indexes + memory) → Context Forge is designed to be the orchestrator so it doesn't feel fragmented.
- **Initial setup cost** vs long-term savings → The setup is front-loaded; the benefits compound over time.

---

*This playbook is the living document for your default optimization stack. Update it as you refine what "default" means for you.*

---

**Next Actions (Recommended Order)**

1. Complete the One-Time Global Setup.
2. Run the per-project setup on 1–2 active projects.
3. Wire up the MCP server in Cursor and/or Claude Code.
4. Index at least one knowledge folder with turbovec.
5. Start a session using Context Forge and observe the difference.

Would you like me to continue building the next pieces (enhanced setup script, more polished global config template, or the memory unification strategy document)?