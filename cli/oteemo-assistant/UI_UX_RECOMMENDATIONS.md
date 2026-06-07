# oteemo-assistant UI/UX Recommendations (Completed)

**Status:** Core upgrade complete (2026-06-07). **Ontology ingest/search in TUI + Python MCP/CLI + LinkML Weaviate extension delivered per follow-up request (2026-06-07).** This document captures the delivered state + a prioritized backlog of concrete, actionable future ideas. Every idea includes: short description, why it helps, rough effort (S/M/L), guardrails (portability, thin-TUI, secrets-only-on-px-host, two-layer timeouts, no heavy logic here).

**Ontology items now complete (see oteemo-assistant README "Ontology recall" section for commands + graceful notes):**
- First-cut `ingest ontology` / `reindex ontology` (walks shared + oteemo vertical, chunks to meta_ontology via Weaviate, idempotent, LinkML ensure side-effect).
- `show ontology <entity>`, `ontology search <q>` (nice cyan cards + Markdown chunks in thread; status bar MODE: Ontology Reindex/Search).
- Python: `scenario-research ingest-ontology`, `search-ontology`; MCP tools; LinkML->Weaviate additive (linkml_weaviate.py).
- All per AGENTS (portable discovery, shared vector_backends reuse + fallback, two-layer timeout, thin TUI, pure-sim sacred, disk YAMLs source of truth).
- Verified: uv pip -e '.[research]', ingest run, collection smoke, TS typecheck/build, pre-existing flows intact, graceful Weaviate-down path.

Self-dogfooding note: Adding the @assistant-ui/react-ink primitives + custom runtime bridge + anchored StatusBarPrimitive-based bar is itself a new pattern for thin ink assistants in this repo. Demonstrated here first; documented for reuse in sibling CLIs (e.g. future context-forge or deep-research TUIs).

## 1. Current Implemented State (This Release)

- Full adoption of `@assistant-ui/react-ink@^0.0.23` + `@assistant-ui/react-ink-markdown@^0.0.22` (via `npm install --legacy-peer-deps` to coexist with existing React 18 + ink 5).
- `AssistantRuntimeProvider` + stable `useLocalRuntime` with a custom `ChatModelAdapter` that **bridges** (does not replace) the existing `mcp-manager` / `mcp-client` / `px-launch` / `paths` surfaces + all `parseIntent` + `handle*` logic.
- `ThreadPrimitive.Root` + `Messages` (custom `OteemoMessage` render prop that re-uses/enhances `LeaderCard` (cyan), `Sparkline` (cyan), `LiveBusinessContext` yellow blocks) + `MarkdownText` for report content.
- `ComposerPrimitive.Input` (replaces manual `useInput` buffer + state while preserving exact command surface).
- `LoadingPrimitive.Root/Spinner/Text/ElapsedTime` for the "⏳ running (two-layer timeout protected)" experience with descriptive text.
- `ThreadPrimitive.Empty` for the initial Oteemo context banner + quick actions (no more hardcoded initial messages in a manual list).
- **The star: rich persistent bottom status bar** using `StatusBarPrimitive.Root / .Status / .ModelName / .MessageCount / .TokenCount / .Latency` + custom extensions (mode, px, last run params, roots summary, quick keys, running indicator). Anchored via `useWindowSize` polyfill (resize-aware + `useStdout`) + flex column + explicit `height=rows` layout (ViewportFooter-style pattern).
- All prior contracts 100% preserved: pure sim (no px tree / keys / DBs), portability (`META_UTILITIES_HOME` / `PX_MCP_ROOT` / walk-up), two-layer timeouts (client env + host), secrets never here, thin opt-in Node surface only, heavy logic stays in `mcp-servers/scenario-research/oteemo`.
- Polish touches: enhanced `LeaderCard` (▶ + cyan border), `Sparkline` (cyan), LiveBusinessContext box, latency tracking in adapter, mode auto-updates on intent (Pure Simulation ↔ Live-Seeded (px) ↔ Report Review ↔ Validation ↔ Help ↔ Command).
- Verification: `npm run typecheck` + `npm run build` clean; `npm run dev` starts without crash and renders header + empty banner + composer + anchored status bar.

Example bottom bar (text representation of what you see in different modes):

```
MODE: Pure Simulation | MODEL: deterministic-sim (oteemo_billable) | STATUS:IDLE | PX:pure-sim | 12p/opt seed=42 | 7 0t | 124ms | meta:ok | Ctrl-C exit | /help | Tab
```

```
MODE: Live-Seeded (px) | MODEL: deterministic-sim (oteemo_billable) | STATUS:RUNNING | PX:live-ok | 8p seed=42 | 4 0t | ⏳ 2-layer-timeout | meta:ok px:detected | Ctrl-C exit | /help | Tab
```

```
MODE: Report Review | MODEL: deterministic-sim (oteemo_billable) | STATUS:IDLE | PX:pure-sim | MSGS:19 ~312t | 87ms | meta:ok | Ctrl-C exit | /help | Tab
```

The bar is **always visible**, explains current mode + backend + operational context at a glance, and updates live with runs / px pulls / report views.

## 2. High-Priority Near-Term Ideas (P0 / P1)

**P0 — Model / Backend Picker Command (M effort, high user value)**
- Add `/model` or `model sim | local-mlx | frontier:claude-3-5 | px-proxy | hybrid` command (or interactive picker via suggestions).
- Updates the `currentModel` state (ref + set) surfaced in `StatusBarPrimitive.ModelName` and the adapter's run path (future: different MCP tool or local exec).
- Why: Makes the "model/backend in effect" claim real and switchable; prepares for local vs frontier vs px-augmented without changing contracts.
- Guardrails: Default remains `deterministic-sim (oteemo_billable)`. No secrets. Pure sim path always one command away. Document in status bar help text.
- Self-dogfood: Use the same command surface the TUI already parses; extend `parseIntent` + a tiny handler that only mutates the model ref/state.

**P0 — Visible Policy YAML Side-by-Side / Quick Edit (M-L, very high value for governed feel)**
- On `show policy Raja|Arka|Rod` or after a run, surface a split or modal-like view (ink `useFocus` + two `Box` panes) of the active `agent_compiler` YAML snippet + the "effective levers" used in the last sim.
- Allow `edit policy <name> <key>=<value>` (validated client-side + roundtrip to `validate_agent_yaml`).
- Persist the delta in a temp overlay (or write a short-lived patch under `~/.cache/meta-utilities/oteemo-policy-overlays/` with portable discovery) so follow-up `re-run` can consume it.
- Why: Makes the "governed" part of oteemo tangible inside the TUI; directly supports the ontology story and FinOps attribution.
- Guardrails: Never mutate the canonical YAML in `mcp-servers/.../data/`. Overlays are user-local + clearly labeled "ephemeral". Always offer "reset to canonical". Thin surface: the actual compile/validate stays in the MCP.
- Link to `oteemo-billable.md` governance section.

**P1 — Full-Screen Report Viewer Mode (S-M, high delight)**
- `view report` or after `show report` offers `view` subcommand that switches the main area to a scrollable `MarkdownText` of the latest (or chosen) report, with a floating "back" or `q` to return to chat.
- Use `useInput` for `j/k`, `PgUp/PgDn`, search within report, and "re-run from this report's seed/params" button (text affordance).
- Status bar updates to `MODE: Report Review (full)` and shows "q=chat | r=re-run | s=save snippet".
- Why: Long reports are the primary artifact; the current "first 40 lines + ... use show" is a placeholder. Full view turns the TUI into a report workstation without leaving the chat.
- Guardrails: Still thin; the report content comes from the same `loadLatestOteemoReport` + fs read. No new parsing logic here.

**P1 — Cost / FinOps Panel from PDRs (M, high strategic value)**
- After a run (especially `--optimize`), parse the `pdr_attributions[]` (or CostReport analog) from the latest JSON sidecar and render a small table or spark + "invest cost vs billable lift" summary under the leader cards.
- Add `finops` command that shows a 4-period rolling FinOps view (cum invest vs cum billable delta).
- Surface in status bar a tiny "FinOps: +$X lift / -$Y invest (net +Z)" when relevant.
- Why: Directly embodies the "AI FinOps owner" persona (Raja) and the whole point of the scenario. Turns the TUI into a decision-support surface, not just a launcher.
- Guardrails: Data comes from artifacts written by the MCP/server. Pure sim path always has the PDRs (even if 0-cost). No external billing APIs here.

**P1 — Better Suggestion Chips + History Recall (S-M)**
- Use (or polyfill) `ThreadPrimitive.Suggestions` + a small static + dynamic chip row under the composer (or in Empty when idle): "run 6", "run 12 --opt live", "pull gmail PEO", "enrich", "show last report", "re-run last".
- Clicking (or typing the number) submits.
- Add `/history` or up-arrow recall of prior commands from an in-memory ring (or research-memory MCP call when available).
- Why: Reduces typing friction; makes the "quick actions" from the original plan first-class and discoverable. History turns the session into a true REPL.
- Guardrails: Chips are declarative in the TUI only. History is ephemeral unless wired to durable memory (future).

## 3. Polish & Delight (P2, Nice-to-Have)

- **Themes / Color Profiles**: `theme cyan | yellow | mono` that remaps the leader cyan, live yellow, status accents, and sparkline color. Store in a tiny local config (portable `~/.config/meta-utilities/oteemo-assistant.json` or env). Low effort, high polish.
- **Better Sparklines / ASCII Art**: Upgrade `Sparkline` to support dual (util + maturity) side-by-side with labels, mini axes, or "trend arrows". Add a tiny "maturity floor reached" badge when the run crosses the policy threshold. Purely presentational.
- **Progress for px Pulls**: When `pull ...` or `enrich`, surface a `LoadingPrimitive` + "contacting gsd-mcp-server (stdio)..." + live "tools discovered: X" as the MCP responds. (Already partially covered by the global loading; make it intent-specific.)
- **History + Research-Memory Recall**: When the research-memory MCP is present, add a `recall <query>` that injects prior oteemo traces / context-forge notes as assistant messages (rich rendered). Status bar gains a "memory: on" indicator. Guardrail: graceful degrade if memory MCP absent.
- **Copy / Export Affordances**: In a rich oteemo message or report view, `c` copies the leader recs as markdown to clipboard (using a tiny `clipboardy` or `pbcopy` spawn — opt-in, document the dep). `e` writes the current report + json bundle to cwd with a timestamped name.
- **Resize Robustness + Focus Indicators**: Ensure the height=rows layout + status bar survive terminal resize (already wired). Add a subtle `>` caret or focus ring on the composer line when active.
- **First-Run Onboarding Overlay**: If no prior run and px not detected, show a one-time friendly "Pure sim is the happy path — try 'run oteemo 6'. For live signals later: build px-mcp-ts and set keys on *its* host." Dismissible with `dismiss`. (Thin: just a flag file in user cache.)

## 4. Architecture Guardrails (Non-Negotiable)

- **Stay thin**: All simulation, optimization (PuLP/grid), agent compilation, YAML governance, report generation, and long-running work live in `mcp-servers/scenario-research/oteemo` (and siblings). The TUI only discovers, stdio-spawns, parses intents, renders, and maintains tiny UI state (mode, last params, live ctx refs).
- **Portable discovery only**: Never hard-code personal paths. Always honor `META_UTILITIES_HOME` / `PX_MCP_ROOT` + the walk-up logic in `paths.ts`. New patterns (e.g. overlay policy dir) must use the same `$XDG_CACHE_HOME/meta-utilities/...` or env fallbacks.
- **Secrets only on px host**: `COMPOSIO_*`, `ARCADE_*`, `PX_WORKOS_*` are **never** read or stored by this package. The only interaction is "if the discovered px tree has a built `dist/cli.js`, stdio-spawn it (inheriting the *caller's* env at spawn time)". Onboarding hints and list-tools are always safe.
- **Two-layer timeouts**: Respect `SCENARIO_RESEARCH_TIMEOUT_SEC` (and future per-tool) in the client layer; surface the contract in Loading text and status bar. Never add client-side hard timeouts that would conflict with host `tool_timeouts`.
- **Pure sim is sacred**: Every new feature must have a no-px, no-DB, no-key code path that is the default and is tested on `npm run dev` from a fresh machine.
- **Self-dogfood**: If we introduce a new ink pattern (custom runtime bridge for command-driven not LLM, anchored StatusBar with mixed primitives + our state, data-part rich renders inside Messages), we document it here and ideally extract a tiny `cli/_shared/` helper later so other assistants (deep-research, context-forge) can reuse without duplication.
- **No scope creep into MCP**: Do not add new MCP tools, change tool contracts, or move oteemo logic here to "make the TUI nicer."

## 5. Future Scenarios & Integrations (P2 / Strategic)

- **More ODRS scenarios in the same TUI**: Register additional scenarios (e.g. `federal-pipeline`, `axiom-platform-invest`) in the MCP, extend the tiny intent parser + a scenario picker chip row, and add scenario-specific rich renderers (different cards, different sparklines). The bottom bar gains `SCENARIO:oteemo_billable` (or picker). Same adapter surface.
- **Multi-thread / Session Management**: Wire `ThreadListPrimitive` + `useRemoteThreadListRuntime` (or in-memory) so a user can have "oteemo-2026-q2", "what-if invest 35%", "PEO live seed sweep" as separate threads, switchable with `/threads`. Status bar shows "thread: oteemo-2026-q2 (3 msgs)".
- **Batch-Orchestrator Integration**: From the TUI, `batch replicate oteemo 5 seeds` spawns (or displays) a batch job manifest, then streams high-level progress ("seed 1 done — maturity 0.41", "seed 3 optimized") back into the chat as system messages. Uses the existing batch templates + orchestrator; TUI is just the control surface.
- **Deep-Research + Context-Forge Inside the Chat**: Commands like `deep "recent federal PEO IWS win themes"` or `forge context for oteemo firm_init` that invoke the sibling MCPs (deep-research, context-forge) and inject compressed, cited results as `LiveBusinessContext` or new "ResearchNote" rich blocks that can seed the next oteemo run. Status bar gains "research: 2 notes | forge: 1 context". Perfect unification of the meta-utilities stack.
- **REPL / Script Mode**: `oteemo-assistant --script - <<'EOF' ... EOF` that runs a sequence of commands non-interactively and emits a machine-readable transcript (or the final report bundle). Useful for CI or demos. The same adapter logic is reused; only the ink renderer is swapped for a plain emitter.
- **MCP Health / Observability Dashboard**: `health --watch` that polls the scenario + px health (tools list + simple ping) and renders a live updating mini dashboard in the status bar area or a dedicated split (uptime, last tool latency, "px tools: 47 discovered"). Ties into the two-layer timeout story.

## 6. Prioritization & Tracking

| Idea | Priority | Effort | Value | Guardrail Notes |
|------|----------|--------|-------|-----------------|
| Model picker | P0 | M | High (makes "model" real) | Default = deterministic-sim; pure sim always available |
| Policy YAML side-by-side + edit | P0 | M-L | Very high (governance visible) | Ephemeral overlays only; never touch canonical data/ |
| Full report viewer | P1 | S-M | High (delight + utility) | Same fs loader; q to return to chat |
| FinOps / PDR panel | P1 | M | High (strategic fit) | Data from server artifacts only |
| Suggestion chips + history | P1 | S-M | High (ergonomics) | Ephemeral history; chips are static + last-run derived |
| Themes | P2 | S | Medium (polish) | User-local config, portable path |
| Progress for px pulls | P2 | S | Medium | Reuse LoadingPrimitive |
| Research-memory recall | P2 | M | High (stack unification) | Graceful if memory MCP absent |
| More scenarios | Strategic | M+ | High | Extend parser + one renderer per; same bar |
| Batch + deep-research integration | Strategic | L | Very high | Thin surface; heavy work in the MCPs |

## 7. Open Questions / Follow-ups (for Next Agent or Human)

- The `assistant-cloud` package had to be explicitly installed to satisfy a transitive import in `@assistant-ui/core` (cloud history adapter). We don't use cloud features; consider whether a future aui release can tree-shake it or if we should pin a slimmer subset.
- React 18 + ink 5 vs the packages' stated React 19 / ink >=6 peers: works under `--legacy-peer-deps` and in practice here, but a future bump of the workspace to React 19 + ink 6 would be cleaner. Track in the root gap analysis.
- MCP-side enhancement request (small): surface `model` / `backend` / `sim_version` / `last_pdr_count` from the `scenario_research_health` or oteemo run result so the status bar can show authoritative "model: ..." instead of the client-side constant. (Purely additive; pure sim still works if absent.)
- Long-term: extract the stable adapter bridge + status bar layout + data-part rich message pattern into `cli/_shared/assistant-ui-ink-oteemo-bridge.ts` (or a small package) so other TUIs don't copy-paste the 120-line adapter.

---

**End of completed recommendations.** This document + the implemented bottom bar + primitives adoption + README updates fulfill the request to "explicitly produce and 'complete' a high-quality set of Recommendations / future ideas."

Next concrete step after this PR: pick the P0 model picker or policy sidecar and implement end-to-end (including a tiny server-side hook if needed for the model string). All ideas above are ready to hand off to a brightpath batch or human with the guardrails already written.