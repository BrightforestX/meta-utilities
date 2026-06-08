/**
 * Oteemo-focused chat adapter + custom renders for the ink TUI, now upgraded to
 * @assistant-ui/react-ink ^0.0.23 + @assistant-ui/react-ink-markdown ^0.0.22.
 *
 * - Uses AssistantRuntimeProvider + useLocalRuntime with a custom ChatModelAdapter
 *   that bridges our existing MCP manager + parseIntent + oteemo handlers (unchanged contracts).
 * - ThreadPrimitive.Root / Messages (custom Message render re-using + enhancing LeaderCard,
 *   Sparkline, LiveBusinessContext yellow blocks) + MarkdownText for full reports.
 * - ComposerPrimitive.Input replaces manual buffer.
 * - LoadingPrimitive.Root + Spinner + Text + ElapsedTime for the long-running "⏳ running (two-layer timeout protected)" experience.
 * - ThreadPrimitive.Empty for the initial Oteemo context banner + quick actions.
 * - StatusBarPrimitive.Root / .Status / .ModelName / .MessageCount / .TokenCount / .Latency (plus custom extensions)
 *   as the star: always-visible, explains MODE (Pure Simulation | Live-Seeded (px) | Report Review | Validation | Help | Command),
 *   current MODEL/backend (deterministic-sim (oteemo_billable) + future hooks), px status, last run params, approx tokens,
 *   latency, roots, quick keys, and running indicator.
 * - Layout uses window size (polyfill + ink stdout awareness) + flex column + explicit height to anchor status at true bottom.
 *
 * All prior oteemo behavior, rich cards, px graceful fallback, pure-sim 100% path, portability, two-layer timeouts,
 * and MCP surface reuse are preserved exactly. Thin opt-in surface only.
 */

import React, { useEffect, useState, useMemo, useRef, useCallback } from "react";
import { Box, Text, useStdout } from "ink";
import { promises as fs } from "fs";
import path from "path";
import {
  AssistantRuntimeProvider,
  useLocalRuntime,
  ThreadPrimitive,
  ComposerPrimitive,
  StatusBarPrimitive,
  LoadingPrimitive,
  useAuiState,
  type ChatModelAdapter,
} from "@assistant-ui/react-ink";
import { MarkdownText } from "@assistant-ui/react-ink-markdown";
import { createMcpManager, type McpManager } from "./mcp-manager.js";
import { LeaderCard, type LeaderRec } from "./components/LeaderCard.js";
import { Sparkline } from "./components/Sparkline.js";
import { discoverRoots, type DiscoveredRoots } from "./paths.js";

type Mode =
  | "Pure Simulation"
  | "Live-Seeded (px)"
  | "Memory-Augmented"
  | "Report Review"
  | "Validation"
  | "Command"
  | "Help"
  | "Ontology Reindex"
  | "Ontology Search"
  | "Ontology Delete"
  | "Remote Multi-Scenario (Modal)";

type LastRunParams = {
  steps: number;
  seed: number;
  optimize: boolean;
} | null;

export function parseIntent(text: string): { kind: string; payload?: any } {
  const original = text.trim();
  const t = original.toLowerCase();
  if (t.startsWith("run oteemo") || t.startsWith("oteemo")) {
    const m = t.match(/(\d+)/);
    const steps = m ? parseInt(m[1], 10) : 6;
    const optimize = t.includes("opt") || t.includes("optimize");
    const useLive = t.includes("live") || t.includes("context") || t.includes("seed") || t.includes("enrich");
    return { kind: "run_oteemo", payload: { steps, optimize, useLive } };
  }
  if (t.startsWith("re-run") || t.startsWith("rerun")) {
    const m = t.match(/(\d+)/);
    const steps = m ? parseInt(m[1], 10) : 6;
    const optimize = t.includes("opt") || t.includes("optimize");
    const useLive = t.includes("live") || t.includes("context");
    return { kind: "run_oteemo", payload: { steps, optimize, useLive, rerun: true } };
  }
  if (t.includes("pull ") || t.startsWith("get ") || t.includes(" recent ") || t.includes("pipeline") || t.includes("availability")) {
    return { kind: "pull_context", payload: { query: text } };
  }
  if (t.includes("validate")) {
    const yamlMatch = text.match(/---[\s\S]*$/);
    return { kind: "validate_yaml", payload: { yaml: yamlMatch ? yamlMatch[0] : text } };
  }
  if (t.includes("show report") || t.includes("latest report") || t === "report") {
    return { kind: "show_report" };
  }
  // Ontology commands are specific; check them *before* the broad enrich/live/context/px detector
  // so that search queries or other commands containing words like "context" are not misclassified as px pulls.
  if (t.startsWith("ingest ontology") || t.startsWith("reindex ontology") || t === "reindex" || t.includes("ontology ingest")) {
    return { kind: "ingest_ontology", payload: { target: "weaviate" } };
  }
  if (t.startsWith("show ontology") || t.startsWith("ontology show")) {
    // Case-preserving extraction: match on original (with /i) so "MemoryItem", "raja_gudepu_ceo" etc. retain their casing for exact backend match.
    const m = original.match(/^(?:show ontology|ontology show)\s+(.+)$/i);
    const name = m ? m[1].trim() : "";
    return { kind: "show_ontology", payload: { name } };
  }
  if (t.startsWith("ontology search ") || t.startsWith("search ontology ")) {
    // Preserve original casing for query (search may be tolerant but names like MemoryItem must not be forced lower).
    const q = original.replace(/^ontology search |^search ontology /i, "").trim();
    return { kind: "search_ontology", payload: { query: q || original } };
  }
  // Delete ontology (first-class; supports bare name after, or --name / --source / --entity-type / --all)
  if (t.includes("enrich") || t.includes("live") || t.includes("context") || t.includes("px")) {
    return { kind: "enrich_px" };
  }
  if (t === "health" || t === "status") return { kind: "health" };
  if (t === "help" || t === "/help") return { kind: "help" };
  // Root cause of prior "delete not working in text box": prior impl did `const t = ...toLowerCase(); const rest = t.replace...` then `payload.name = rest` (etc),
  // sending lowercased selectors (e.g. "memoryitem") to delete_ontology which does exact `Filter.by_property("name").equal(name)` (and .like for source) against chunks
  // ingested with original YAML/LinkML casing (e.g. "MemoryItem", role names, "raja_gudepu_ceo" etc.). Result: deleted=0 even when data present.
  // Fix: keep original, use case-insensitive tests/replaces for command detection, but assign cased values from original text.
  if (t.startsWith("delete ontology") || t.startsWith("ontology delete")) {
    const restMatch = original.match(/^(?:delete ontology|ontology delete)\s+(.*)$/i);
    const rest = restMatch ? restMatch[1].trim() : "";
    const payload: any = {};
    if (rest === "--all" || /--all/i.test(rest)) {
      payload.delete_all = true;
    } else if (/^--name /i.test(rest)) {
      payload.name = rest.replace(/^--name /i, "").trim();
    } else if (/^--source /i.test(rest)) {
      payload.source = rest.replace(/^--source /i, "").trim().replace(/^["']|["']$/g, "");
    } else if (/^--entity[-_]?type /i.test(rest)) {
      payload.entity_type = rest.replace(/^--entity[-_]?type /i, "").trim();
    } else if (rest) {
      // bare e.g. "delete ontology raja_gudepu_ceo" or "delete ontology MemoryItem" or "delete ontology --name foo" handled above
      payload.name = rest;
    }
    return { kind: "delete_ontology", payload };
  }
  // Remote multi-scenario dispatch to Modal (thin; heavy in scenario-research MCP + scaffold modal_app)
  // Supports: "multi-run <file> --target modal", "dispatch multi scenario ... modal <file>", "run multi scenarios remotely --target modal <file>", etc.
  // Parses scenario_file (first path-like token) + optional flags. Generic .call path also works for power users.
  if (
    t.includes("multi-run") || t.includes("multi run") || t.includes("run multi") ||
    t.includes("dispatch multi") || (t.includes("multi") && (t.includes("modal") || t.includes("remote"))) ||
    t.includes("remote scenario") || t.includes("remote analysis")
  ) {
    const words = text.trim().split(/\s+/);
    let scenario_file = "";
    for (const w of words) {
      if (w.includes("/") || w.toLowerCase().endsWith(".json") || /examples\//i.test(w) || w.includes("scenarios")) {
        scenario_file = w;
        break;
      }
    }
    if (!scenario_file && words.length > 1) {
      // last non-flag token fallback
      scenario_file = words.filter(w => !w.startsWith("-")).pop() || "";
    }
    const payload: any = { scenario_file };
    const tl = text.toLowerCase();
    const mExec = tl.match(/--execution-mode[=\s]+(\S+)/) || tl.match(/--mode[=\s]+(\S+)/);
    if (mExec) payload.execution_mode = mExec[1];
    const mFmt = tl.match(/--output-format[=\s]+(\S+)/) || tl.match(/--format[=\s]+(\S+)/);
    if (mFmt) payload.output_format = mFmt[1];
    const mUrls = tl.match(/--server-urls-json[=\s]+(.+?)(?:\s+--|$|\s*$)/);
    if (mUrls) payload.server_urls_json = mUrls[1].trim().replace(/^["']|["']$/g, "");
    // target flag is advisory (presence of modal/remote in phrase already selected the dispatch kind)
    return { kind: "multi_run_modal", payload };
  }
  return { kind: "chat", payload: { text } };
}

async function findOteemoReportsDir(metaRoot: string | null): Promise<string | null> {
  if (!metaRoot) return null;
  const cand = path.join(metaRoot, "mcp-servers", "scenario-research", "oteemo", "reports");
  try {
    await fs.access(cand);
    return cand;
  } catch {
    return null;
  }
}

async function loadLatestOteemoReport(metaRoot: string | null): Promise<{ path: string; content: string } | null> {
  const dir = await findOteemoReportsDir(metaRoot);
  if (!dir) return null;
  try {
    const files = await fs.readdir(dir);
    const mds = files.filter(f => f.endsWith(".md")).sort().reverse();
    if (mds.length === 0) return null;
    const latest = path.join(dir, mds[0]);
    const content = await fs.readFile(latest, "utf8");
    return { path: latest, content };
  } catch {
    return null;
  }
}

function extractLeaderRecsFromReport(report: string): LeaderRec[] {
  const recs: LeaderRec[] = [];
  const lines = report.split("\n");
  let inRecs = false;
  for (const line of lines) {
    if (/^## Concrete Recommendations/.test(line)) { inRecs = true; continue; }
    if (inRecs && /^## /.test(line)) break;
    const m = line.match(/^- (Raja|Arka|Roderick|Clifford)[^:]*:\s*(.*)$/i);
    if (m) {
      const nameMap: Record<string, string> = {
        Raja: "Raja (CEO / AI FinOps owner)",
        Arka: "Arka (VP Tech)",
        Roderick: "Roderick (Head of Federal Delivery)",
        Clifford: "Clifford (Contractor, Axiom/FinOps)",
      };
      recs.push({
        name: nameMap[m[1]] || m[1],
        role: m[1] === "Raja" ? "strategy + FinOps" : m[1] === "Arka" ? "platform leverage" : m[1] === "Roderick" ? "billable owner" : "Axiom FinOps fixed",
        rec: m[2].trim(),
      });
    }
  }
  return recs;
}

function extractSparklinesFromReport(report: string): { util?: number[]; maturity?: number[] } {
  const utilLine = report.match(/\*\*Utilization[^:]*\*\*:\s*([▁▂▃▄▅▆▇█·]+)/);
  const matLine = report.match(/\*\*Maturity[^:]*\*\*:\s*([▁▂▃▄▅▆▇█·]+)/);
  const barToVal = (s: string) => {
    const bars = "▁▂▃▄▅▆▇█";
    return Array.from(s).map(ch => {
      const i = bars.indexOf(ch);
      return i >= 0 ? (i + 1) / (bars.length + 1) : 0.5;
    });
  };
  return {
    util: utilLine ? barToVal(utilLine[1]) : undefined,
    maturity: matLine ? barToVal(matLine[1]) : undefined,
  };
}

// Small live context box (yellow per prior design, polished) — kept from delete/ontology work
function LiveBusinessContextBox({ ctx }: { ctx: any }) {
  if (!ctx) return null;
  return (
    <Box borderStyle="round" borderColor="yellow" paddingX={1} marginTop={1} flexDirection="column">
      <Text bold color="yellow">LiveBusinessContext (px signals @ {ctx.timestamp || "now"})</Text>
      <Text dimColor>{JSON.stringify(ctx.citations || ctx.signals || {}).slice(0, 320)}...</Text>
      <Text dimColor>Signals can seed firm_init (win_p, capacity) or suggest policy deltas. Citations for audit. Use in next 'run oteemo ... live'.</Text>
    </Box>
  );
}

// useWindowSize polyfill (works on ink 5 + any node)
function useWindowSize() {
  const [size, setSize] = useState(() => ({
    columns: process.stdout.columns || 100,
    rows: process.stdout.rows || 32,
  }));
  const { stdout } = useStdout();
  useEffect(() => {
    const update = () => {
      const cols = stdout?.columns || process.stdout.columns || 100;
      const rws = stdout?.rows || process.stdout.rows || 32;
      setSize({ columns: cols, rows: rws });
    };
    update();
    const onResize = () => update();
    process.stdout.on("resize", onResize);
    if (stdout && stdout !== process.stdout) {
      stdout.on("resize", onResize);
    }
    return () => {
      process.stdout.off("resize", onResize);
      if (stdout && stdout !== process.stdout) stdout.off("resize", onResize);
    };
  }, [stdout]);
  return size;
}

// PR1 low-risk execution ranking helpers (additive; used to surface lowest-risk recs first in TUI)
type ExecutionRisk = "low" | "medium" | "high";

function riskScore(risk: ExecutionRisk | undefined): number {
  if (risk === "low") return 0;
  if (risk === "medium") return 1;
  return 2;
}

function enrichRecommendation(rec: LeaderRec, useLive: boolean): LeaderRec {
  const roleBlob = `${rec.name} ${rec.role}`.toLowerCase();
  if (roleBlob.includes("arka")) {
    return {
      ...rec,
      executionRisk: "low",
      reasoning: "Arcade toolkit-driven changes are reversible and have narrow blast radius.",
      executionPath: "arcade_list_toolkits -> arcade_call_tool",
    };
  }
  if (roleBlob.includes("rod") || roleBlob.includes("roderick")) {
    return {
      ...rec,
      executionRisk: "low",
      reasoning: useLive
        ? "Composio-backed pull path is already grounded by live context signals."
        : "Composio path can start with read-only discovery before any write action.",
      executionPath: "composio_list_tools(slug:salesforce|gmail|slack) -> composio_call_tool",
    };
  }
  if (roleBlob.includes("raja")) {
    return {
      ...rec,
      executionRisk: "medium",
      reasoning: "Finance policy adjustments impact wider budget controls and should be staged.",
      executionPath: "composio_list_apps -> composio_call_tool (pipeline/forecast updates)",
    };
  }
  if (roleBlob.includes("clifford")) {
    return {
      ...rec,
      executionRisk: "medium",
      reasoning: "Contractor leverage changes are effective but usually require broader coordination.",
      executionPath: "scenario policy replay (local) -> optional arcade/composio follow-up",
    };
  }
  return {
    ...rec,
    executionRisk: "medium",
    reasoning: "Defaulted to medium risk due to missing role-specific execution profile.",
  };
}

function rankLowestRiskFirst(recs: LeaderRec[]): LeaderRec[] {
  return [...recs].sort((a, b) => {
    const riskCmp = riskScore(a.executionRisk) - riskScore(b.executionRisk);
    if (riskCmp !== 0) return riskCmp;
    return a.name.localeCompare(b.name);
  });
}

// Support clean shutdown of MCP stdio clients on Ctrl-C / SIGINT *without* using ink's useInput hook.
// useInput at this root level was stealing keystrokes from the inner ComposerPrimitive.Input (backspace,
// delete, arrows, and in some cases normal editing/submit), breaking the assistant-ui text box for all
// commands including "delete ontology ...". The framework's Input primitive now owns interactive input.
let _activeManager: McpManager | null = null;

export async function closeActiveManager(): Promise<void> {
  const m = _activeManager;
  _activeManager = null;
  if (m && typeof m.closeAll === "function") {
    try {
      await m.closeAll();
    } catch {
      // best effort; transports will be torn down on process exit anyway
    }
  }
}

export function OteemoChat() {
  const [manager, setManager] = useState<McpManager | null>(null);
  const managerRef = useRef<McpManager | null>(null);
  const [lastLiveContext, setLastLiveContext] = useState<any>(null);
  const lastLiveRef = useRef<any>(null);
  const [mode, setMode] = useState<Mode>("Pure Simulation");
  const modeRef = useRef<Mode>("Pure Simulation");
  const [lastRunParams, setLastRunParams] = useState<LastRunParams>(null);
  const lastRunRef = useRef<LastRunParams>(null);
  const [lastLatencyMs, setLastLatencyMs] = useState<number>(0);
  const [currentModel] = useState<string>("deterministic-sim (oteemo_billable)"); // future: local-mlx, frontier:claude, px-proxy, hybrid

  const windowSize = useWindowSize();
  const roots: DiscoveredRoots = discoverRoots();
  const pxReady = !!roots.pxMcpRoot;

  // Keep refs in sync for stable adapter (prevents thread reset churn)
  useEffect(() => { managerRef.current = manager; }, [manager]);
  useEffect(() => { lastLiveRef.current = lastLiveContext; }, [lastLiveContext]);
  useEffect(() => { modeRef.current = mode; }, [mode]);
  useEffect(() => { lastRunRef.current = lastRunParams; }, [lastRunParams]);

  useEffect(() => {
    let alive = true;
    createMcpManager().then((m) => {
      if (alive) {
        setManager(m);
        managerRef.current = m;
        _activeManager = m;
      }
    });
    return () => {
      alive = false;
      // best-effort clear if this instance is going away (single-instance TUI in practice)
      if (_activeManager === managerRef.current) {
        _activeManager = null;
      }
    };
  }, []);

  // Core handlers (reused exactly; MCP surface + portability + pure-sim contracts untouched)
  // Note: busy state removed (framework LoadingPrimitive + isRunning handle the UX now)
  const handleRunOteemo = useCallback(async (payload: any, liveCtxOverride?: any) => {
    const mgr = managerRef.current;
    if (!mgr) return "Manager not ready.";
    const useLive = !!payload.useLive || !!liveCtxOverride || !!lastLiveRef.current;
    const res = await mgr.scenario.runOteemoBillable({ steps: payload.steps, seed: 42, optimize: payload.optimize, live: useLive } as any);
    const run = (res && (res as any).content && Array.isArray((res as any).content)) ? (res as any).content[0]?.text : res;
    let runInfo = "";
    try {
      const parsed = typeof run === "string" ? JSON.parse(run) : run;
      if (parsed && typeof parsed === "object") {
        runInfo = `run_id=${parsed.run_id || parsed.id || "?"} status=${parsed.status || "ok"} steps=${parsed.n_steps || payload.steps} seed=${parsed.seed ?? 42}`;
        if (parsed.db_path) runInfo += ` db=${parsed.db_path}`;
      }
    } catch { /* not json */ }
    const liveNote = useLive && (liveCtxOverride || lastLiveRef.current) ? " (live-seeded with px signals)" : "";
    const summary = `oteemo_billable ${payload.steps}p seed=42 ${payload.optimize ? "(optimized)" : ""}${liveNote} — ${runInfo || "artifacts in oteemo/reports/"}`;
    return { summary, recs: [], note: "headless: rec extraction skipped (pure manager call)", raw: run };
  }, [roots.metaUtilitiesRoot]);

  const handleEnrich = useCallback(async () => {
    const mgr = managerRef.current;
    if (!mgr || !mgr.px) return "px not available (pure sim path remains fully functional). See px build guidance.";
    try {
      const hint = await mgr.px.onboardingComposioHint();
      const ctx = {
        kind: "LiveBusinessContext",
        timestamp: new Date().toISOString(),
        citations: [{ tool: "px_onboarding_composio_hint", result: hint }],
        signals: { note: "onboarding hint; connect accounts in composio/arcade dashboards for full pulls" },
      };
      setLastLiveContext(ctx);
      return { kind: "live_context", ctx, text: `px live signals available. ${JSON.stringify(hint).slice(0, 200)}... Use 'run oteemo live' or 'pull gmail PEO' (when keys+connections on px host).` };
    } catch (e: any) {
      return `px call error (graceful): ${String(e)}`;
    }
  }, []);

  const handlePullBusinessContext = useCallback(async (query: string) => {
    const mgr = managerRef.current;
    if (!mgr || !mgr.px) return "px not available (pure sim path remains fully functional). Build px-mcp-ts and ensure COMPOSIO/ARCADE keys on its host env.";
    const q = query.toLowerCase();
    try {
      let toolCall: { name: string; args?: any } | null = null;
      if (q.includes("gmail") || q.includes("email") || q.includes("peo")) {
        toolCall = { name: "composio_list_tools", args: { slug: "gmail" } };
      } else if (q.includes("slack")) {
        toolCall = { name: "composio_list_tools", args: { slug: "slack" } };
      } else if (q.includes("calendar") || q.includes("availability")) {
        toolCall = { name: "composio_list_tools", args: { slug: "google_calendar" } };
      } else if (q.includes("salesforce") || q.includes("hubspot") || q.includes("pipeline") || q.includes("opportunity")) {
        toolCall = { name: "composio_list_apps", args: {} };
      } else if (q.includes("notion") || q.includes("confluence") || q.includes("arch")) {
        toolCall = { name: "composio_list_tools", args: { slug: "notion" } };
      } else if (q.includes("linkedin") || q.includes("enrich")) {
        toolCall = { name: "arcade_list_toolkits", args: {} };
      } else {
        toolCall = { name: "px_onboarding_composio_hint", args: {} };
      }

      const result = await mgr.px.call(toolCall.name, toolCall.args || {});
      const ctx = {
        kind: "LiveBusinessContext",
        timestamp: new Date().toISOString(),
        citations: [{ tool: toolCall.name, args: toolCall.args, resultSummary: JSON.stringify(result).slice(0, 300) }],
        signals: { query, note: "pulled via px proxy (composio/arcade); usable for seeding firm_init or policy suggestions" },
      };
      setLastLiveContext(ctx);
      return { kind: "live_context", ctx, text: `Live signals (${toolCall.name}): ${JSON.stringify(result).slice(0, 400)}...` };
    } catch (e: any) {
      return `px pull error (graceful; pure sim still works): ${String(e)}`;
    }
  }, []);

  // --- Ontology handlers (thin: parse + manager.scenario.call + render; heavy in scenario-research MCP) ---
  // Kept + extended for delete support (first-class explicit deletes in TUI)
  const handleIngestOntology = useCallback(async () => {
    const mgr = managerRef.current;
    if (!mgr) return "Manager not ready.";
    setMode("Ontology Reindex");
    try {
      const res = await mgr.scenario.call("ingest_ontology", { target: "weaviate" });
      const parsed = (res && (res as any).content && Array.isArray((res as any).content)) ? (res as any).content[0]?.text : res;
      let summary = "Ontology reindex requested.";
      try {
        const j = typeof parsed === "string" ? JSON.parse(parsed) : parsed;
        if (j && j.ok) {
          summary = `Ingested ${j.inserted ?? "?"} chunks into ${j.collection || "meta_ontology"} (cleared ${j.cleared_prior ?? 0} prior). Sources: ${(j.roots || []).join(", ")}`;
        } else if (j) {
          summary = `Ingest result: ${j.msg || JSON.stringify(j).slice(0, 200)}`;
        }
      } catch { /* non-json ok */ }
      return { kind: "ontology", action: "ingest", text: summary };
    } catch (e: any) {
      return `Ontology ingest error (graceful): ${String(e)}`;
    }
  }, []);

  const handleSearchOntology = useCallback(async (query: string) => {
    const mgr = managerRef.current;
    if (!mgr) return "Manager not ready.";
    setMode("Ontology Search");
    try {
      const res = await mgr.scenario.call("search_ontology", { query, top_k: 5 });
      return { kind: "ontology", action: "search", query, results: res };
    } catch (e: any) {
      return `Ontology search error (graceful): ${String(e)}`;
    }
  }, []);

  // (removed duplicate handleDeleteOntology definition here; the complete version with result parsing lives later in the component to avoid redeclare TS2451)

  // NOTE: `async function send(text)` was removed (dead post @assistant-ui migration).
  // It was unreachable (no callers; runtime adapter.run + parseIntent dispatch the real paths).
  // It also lacked delete_ontology / multi_run_modal cases and referenced removed setMessages state.
  // Headless uses parseIntentLocal + runHeadless; interactive uses adapter.run + handlers. Hygiene only.

  const handleShowOntology = useCallback(async (name: string) => {
    const mgr = managerRef.current;
    if (!mgr) return "Manager not ready.";
    setMode("Ontology Search");
    const q = name || "MemoryItem";
    try {
      const res = await mgr.scenario.call("search_ontology", { query: q, top_k: 5 });
      const hits = (res && (res as any).content && Array.isArray((res as any).content)) ? (res as any).content.map((c: any) => c.text ? JSON.parse(c.text) : c) : res;
      return { kind: "ontology_result", summary: `show ontology ${q}`, hits: Array.isArray(hits) ? hits : [hits] };
    } catch (e: any) {
      return `search_ontology error (graceful): ${String(e)}`;
    }
  }, []);

  // --- Delete ontology handler (thin: setMode + manager.scenario.call("delete_ontology", ...) + rich result; heavy delete in scenario-research MCP) ---
  const handleDeleteOntology = useCallback(async (payload: any) => {
    const mgr = managerRef.current;
    if (!mgr) return "Manager not ready.";
    setMode("Ontology Delete");
    try {
      const args: any = {};
      if (payload?.name) args.name = payload.name;
      if (payload?.entity_type) args.entity_type = payload.entity_type;
      if (payload?.source) args.source = payload.source;
      if (payload?.delete_all) args.delete_all = true;
      const res = await mgr.scenario.call("delete_ontology", args);
      const parsed = (res && (res as any).content && Array.isArray((res as any).content)) ? (res as any).content[0]?.text : res;
      let summary = "Ontology delete requested.";
      let deleted = 0;
      let removed: string[] = [];
      try {
        const j = typeof parsed === "string" ? JSON.parse(parsed) : parsed;
        if (j && j.ok) {
          deleted = j.deleted ?? 0;
          removed = Array.isArray(j.removed) ? j.removed : [];
          const sel = j.selectors || {};
          const selStr = [sel.name && `name=${sel.name}`, sel.entity_type && `type=${sel.entity_type}`, sel.source && `source~${sel.source}`, sel.delete_all && "ALL"].filter(Boolean).join(" ");
          summary = `Deleted ${deleted} from ${j.collection || "meta_ontology"} ${selStr ? `(${selStr})` : ""}`;
        } else if (j) {
          summary = `Delete result: ${j.msg || JSON.stringify(j).slice(0, 220)}`;
          deleted = j.deleted ?? 0;
          removed = Array.isArray(j.removed) ? j.removed : [];
        }
      } catch { /* not json */ }
      return { kind: "ontology_delete_result", summary, deleted, removed, raw: parsed };
    } catch (e: any) {
      return `delete_ontology error (graceful; pure sim + disk YAMLs unaffected): ${String(e)}`;
    }
  }, []);

  // Stable adapter (deps empty; uses refs + setState for live reactivity without resetting Thread)
  const adapter: ChatModelAdapter = useMemo(() => ({
    async *run({ messages }: { messages: readonly any[] }) {
      const lastUser = [...messages].reverse().find((m: any) => m.role === "user");
      if (!lastUser) {
        yield { content: [{ type: "text", text: "Oteemo Assistant ready. Type a command (e.g. 'run oteemo 6 --optimize live'). New: 'delete ontology <name | --name X | --source Y | --all (careful)>' or 'multi-run camel-oasis-scaffold/examples/multi_scenarios.json --target modal' (remote dispatch)." }] };
        return;
      }
      const userText = lastUser.content?.find((p: any) => p.type === "text")?.text?.trim() || "";
      const intent = parseIntent(userText);

      let rich: any = null;
      let outText = "Command processed.";
      const t0 = Date.now();

      if (intent.kind === "run_oteemo") {
        const p = intent.payload || {};
        const liveCtx = (p.useLive || lastLiveRef.current) ? lastLiveRef.current : undefined;
        setMode(liveCtx ? "Live-Seeded (px)" : "Pure Simulation");
        setLastRunParams({ steps: p.steps ?? 6, seed: 42, optimize: !!p.optimize });
        rich = await handleRunOteemo(p, liveCtx);
        outText = (rich && typeof rich === "object" && rich.summary) ? rich.summary : (typeof rich === "string" ? rich : "oteemo run complete.");
      } else if (intent.kind === "pull_context") {
        setMode("Command");
        rich = await handlePullBusinessContext(intent.payload?.query || userText);
        outText = (rich && typeof rich === "object" && rich.text) ? rich.text : (typeof rich === "string" ? rich : JSON.stringify(rich).slice(0, 320));
      } else if (intent.kind === "enrich_px") {
        setMode("Live-Seeded (px)");
        rich = await handleEnrich();
        outText = (rich && typeof rich === "object" && rich.text) ? rich.text : (typeof rich === "string" ? rich : "");
      } else if (intent.kind === "show_report") {
        setMode("Report Review");
        const latest = await loadLatestOteemoReport(roots.metaUtilitiesRoot);
        if (latest) {
          const recs = extractLeaderRecsFromReport(latest.content);
          const sp = extractSparklinesFromReport(latest.content);
          rich = { summary: `=== ${latest.path} ===`, reportMd: latest.content, recs, sparkUtil: sp.util, sparkMat: sp.maturity };
          outText = rich.summary;
        } else {
          outText = "No oteemo report found yet under oteemo/reports/. Run an oteemo scenario first (the rich demo with --optimize writes the full governed recs).";
        }
      } else if (intent.kind === "validate_yaml") {
        setMode("Validation");
        const mgr = managerRef.current;
        if (mgr) {
          try {
            const v = await mgr.scenario.call("validate_agent_yaml", { yaml_text: intent.payload?.yaml || userText });
            outText = typeof v === "string" ? v : JSON.stringify(v, null, 2);
          } catch (e: any) {
            outText = `validate error: ${String(e)}`;
          }
        } else {
          outText = "Manager not ready for validate.";
        }
      } else if (intent.kind === "health") {
        setMode("Command");
        const mgr = managerRef.current;
        outText = mgr ? "scenario + px (if present) connected. Use 'run oteemo'. New: multi-run <file> --target modal (remote fire-and-forget)." : "Manager initializing...";
      } else if (intent.kind === "help") {
        setMode("Help");
        outText = "Commands: run oteemo N [--optimize] [live], re-run N, show report, pull gmail|slack|calendar|salesforce|notion, enrich/live/context/px, validate <yaml or paste>, health, help, ingest ontology | reindex ontology, show ontology <MemoryItem|raja_gudepu_ceo|...>, ontology search finops, delete ontology <name|raja_gudepu_ceo| --name X | --source \"oteemo/ontology/agents\" | --entity-type role | --all (careful)>, multi-run <file> --target modal (or 'dispatch multi scenario to modal <file>' / 'run multi scenarios remotely'). px pulls surface as LiveBusinessContext (yellow); seed oteemo recs. Ontology results (incl. delete: count + removed names) use cyan. Bottom bar shows MODE (incl. Ontology Reindex/Search/Delete + Remote Multi-Scenario (Modal)). Pure sim + disk YAMLs work without Weaviate. Generic power-user: manager.scenario.call('dispatch_multi_scenario_to_modal', {scenario_file, ...}) also available via headless or custom hosts.";
      } else if (intent.kind === "ingest_ontology") {
        setMode("Ontology Reindex");
        rich = await handleIngestOntology();
        outText = (rich && typeof rich === "object" && rich.summary) ? rich.summary : (typeof rich === "string" ? rich : "Ontology ingest complete.");
      } else if (intent.kind === "show_ontology" || intent.kind === "search_ontology") {
        setMode("Ontology Search");
        const q = intent.payload?.name || intent.payload?.query || userText;
        rich = await handleShowOntology(q);
        outText = (rich && typeof rich === "object" && rich.summary) ? rich.summary : (typeof rich === "string" ? rich : "Ontology search complete.");
      } else if (intent.kind === "delete_ontology") {
        setMode("Ontology Delete");
        rich = await handleDeleteOntology(intent.payload || {});
        outText = (rich && typeof rich === "object" && rich.summary) ? rich.summary : (typeof rich === "string" ? rich : "Ontology delete complete.");
      } else if (intent.kind === "multi_run_modal") {
        setMode("Remote Multi-Scenario (Modal)");
        const mgr = managerRef.current;
        if (mgr) {
          try {
            const p = intent.payload || {};
            const args: any = { scenario_file: p.scenario_file };
            if (p.execution_mode) args.execution_mode = p.execution_mode;
            if (p.output_format) args.output_format = p.output_format;
            if (p.server_urls_json) args.server_urls_json = p.server_urls_json;
            rich = await mgr.scenario.call("dispatch_multi_scenario_to_modal", args);
            outText = (rich && typeof rich === "object" && (rich as any).status)
              ? `Modal dispatch ${ (rich as any).status } (pid=${(rich as any).pid || "?"}, volume=${(rich as any).volume || "sim-results"})`
              : (typeof rich === "string" ? rich : "Multi-scenario dispatch to Modal complete.");
          } catch (e: any) {
            outText = `dispatch_multi_scenario_to_modal error (graceful; modal extra or scaffold may be absent): ${String(e)}`;
          }
        } else {
          outText = "Manager not ready for remote multi-scenario dispatch.";
        }
      } else {
        setMode("Command");
        outText = "Unrecognized command. Try 'run oteemo 6 --optimize live', 'pull gmail PEO', 'enrich with live', 'show report', 'help', 'ingest ontology', 'show ontology MemoryItem', 'ontology search finops', 'delete ontology raja_gudepu_ceo | --name MemoryItem | --source oteemo/... | --all (careful)', 'multi-run camel-oasis-scaffold/examples/multi_scenarios.json --target modal' (or 'dispatch multi scenario to modal <file>').";
      }

      const latency = Date.now() - t0;
      setLastLatencyMs(latency);

      const content: any[] = [{ type: "text", text: outText }];
      if (rich && typeof rich === "object" && (rich.recs || rich.reportMd || rich.liveBusinessContext || rich.ctx || rich.kind === "ontology_result" || rich.hits || rich.kind === "ontology_delete_result" || (rich.deleted != null) || (rich.status && (rich.target === "modal" || rich.volume || rich.pid)))) {
        content.push({ type: "data", data: { kind: rich.kind === "ontology_delete_result" ? "ontology_delete_result" : (rich.kind === "ontology_result" ? "ontology_result" : (rich.status === "dispatched" || rich.pid ? "multi_modal_dispatch" : "oteemo_structured")), ...rich, _execLatencyMs: latency } });
      }
      yield { content };
    },
  }), []); // stable identity; internal refs + setState keep behavior fresh

  const runtime = useLocalRuntime(adapter);

  // No useInput hook: the ComposerPrimitive.Input (assistant-ui) is responsible for all text box behavior
  // (typing, backspace/delete for editing commands like "delete ontology MemoryItem", enter to submit, etc.).
  // Global SIGINT/Ctrl-C for clean MCP close is wired in cli.tsx via closeActiveManager + process signal.
  // (Previous unconditional useInput here was the direct cause of "backspace is not working" and made
  // the entire interactive command surface, including ontology delete commands, unusable in the text box.)

  // Custom rich message renderer (re-uses/enhances existing cards + adds MarkdownText + data-part support)
  const OteemoMessage = () => {
    const message = useAuiState((s: any) => s.message);
    const textPart = message.content?.find((p: any) => p.type === "text");
    const dataPart = message.content?.find((p: any) => p.type === "data" && p.data && (p.data.kind === "oteemo_structured" || p.data.recs || p.data.kind === "ontology_result" || p.data.kind === "ontology_delete_result" || (p.data.deleted != null) || p.data.kind === "multi_modal_dispatch" || (p.data.status && (p.data.target === "modal" || p.data.pid || p.data.volume))));
    const rich = dataPart?.data || null;

    const isUser = message.role === "user";

    if (rich && (rich.recs || rich.reportMd || rich.liveBusinessContext)) {
      return (
        <Box key={message.id} flexDirection="column" marginBottom={1} paddingX={1}>
          <Text bold color={isUser ? "blue" : "magenta"}>{message.role}:</Text>
          {rich.summary ? <Text>{rich.summary}</Text> : null}
          {rich.recs && rich.recs.length > 0 ? (
            rich.recs.map((r: LeaderRec, idx: number) => <LeaderCard key={idx} rec={r} />)
          ) : null}
          {rich.sparkUtil ? <><Text dimColor>util:</Text><Sparkline values={rich.sparkUtil} /></> : null}
          {rich.sparkMat ? <><Text dimColor>maturity:</Text><Sparkline values={rich.sparkMat} /></> : null}
          {rich.liveBusinessContext ? <LiveBusinessContextBox ctx={rich.liveBusinessContext} /> : null}
          {rich.reportMd ? (
            <Box marginTop={1} flexDirection="column">
              <Text dimColor>--- report excerpt / full (markdown rendered) ---</Text>
              <MarkdownText text={rich.reportMd} />
            </Box>
          ) : null}
          {rich.note ? <Text dimColor>{rich.note}</Text> : null}
        </Box>
      );
    }

    // Ontology results (cards + markdown chunks, styled consistently with cyan/yellow cards; graceful msgs handled in text)
    if (rich && rich.kind === "ontology_result") {
      return (
        <Box key={message.id} flexDirection="column" marginBottom={1} paddingX={1}>
          <Text bold color={isUser ? "blue" : "magenta"}>{message.role}:</Text>
          {rich.summary ? <Text color="cyan">{rich.summary}</Text> : null}
          {rich.hits && rich.hits.length > 0 ? (
            rich.hits.map((h: any, idx: number) => (
              <Box key={idx} borderStyle="round" borderColor="cyan" paddingX={1} marginY={0} flexDirection="column">
                <Text bold color="cyan">▶ {h.entity_type || "chunk"}: {h.name}</Text>
                <Text dimColor>source: {h.source} | tags: {(h.tags || []).join(", ")}</Text>
                {h.text ? <MarkdownText text={String(h.text).slice(0, 800)} /> : null}
              </Box>
            ))
          ) : null}
          {rich.raw ? <Text dimColor>{typeof rich.raw === "string" ? rich.raw.slice(0, 200) : JSON.stringify(rich.raw).slice(0, 200)}</Text> : null}
        </Box>
      );
    }

    // Ontology delete results (cyan summary + count + removed names list; consistent style)
    if (rich && rich.kind === "ontology_delete_result") {
      return (
        <Box key={message.id} flexDirection="column" marginBottom={1} paddingX={1}>
          <Text bold color={isUser ? "blue" : "magenta"}>{message.role}:</Text>
          {rich.summary ? <Text color="cyan">{rich.summary}</Text> : null}
          {typeof rich.deleted === "number" ? (
            <Text color="green">🗑️ Deleted: {rich.deleted}</Text>
          ) : null}
          {rich.removed && rich.removed.length > 0 ? (
            <Text dimColor>Removed: {rich.removed.slice(0, 20).join(", ")}{rich.removed.length > 20 ? " ..." : ""}</Text>
          ) : null}
          {rich.raw ? <Text dimColor>{typeof rich.raw === "string" ? rich.raw.slice(0, 220) : JSON.stringify(rich.raw).slice(0, 220)}</Text> : null}
        </Box>
      );
    }

    // Remote multi-scenario (Modal) dispatch result (fire-and-forget; cyan like ontology, with pid/volume/cmd/note for monitoring)
    if (rich && (rich.kind === "multi_modal_dispatch" || (rich.status && (rich.target === "modal" || rich.pid || rich.volume)))) {
      return (
        <Box key={message.id} flexDirection="column" marginBottom={1} paddingX={1}>
          <Text bold color={isUser ? "blue" : "magenta"}>{message.role}:</Text>
          {rich.status ? <Text color="cyan">Modal dispatch: {rich.status} (target: {rich.target || "modal"})</Text> : null}
          {rich.pid ? <Text color="green">pid: {rich.pid}</Text> : null}
          {rich.volume ? <Text>volume: {rich.volume} (use `modal volume ls/get` to retrieve)</Text> : null}
          {rich.scenario_file ? <Text dimColor>file: {rich.scenario_file}</Text> : null}
          {rich.cmd ? <Text dimColor>cmd: {rich.cmd}</Text> : null}
          {rich.note ? (
            <Box marginTop={0} flexDirection="column">
              <Text dimColor>--- note ---</Text>
              <Text dimColor>{String(rich.note).slice(0, 600)}</Text>
            </Box>
          ) : null}
          {rich.error || rich.msg ? <Text color="red">{rich.error || rich.msg}</Text> : null}
          <Text dimColor>(fire-and-forget: remote work continues on Modal after this call returns. Monitor with `modal app list` / `modal logs`. Two-layer timeout on launch only.)</Text>
        </Box>
      );
    }

    // Fallback (help, health, errors, plain chat, validate output, etc.)
    return (
      <Box key={message.id} flexDirection="column" marginBottom={1} paddingX={1}>
        <Text bold color={isUser ? "blue" : "magenta"}>{message.role}:</Text>
        <Text>{textPart?.text || ""}</Text>
      </Box>
    );
  };

  // The rich persistent bottom status bar (the star of the upgrade)
  const OteemoStatusBar = () => {
    const auiMessageCount = useAuiState((s: any) => (s.thread?.messages?.length ?? 0));
    const isRunning = useAuiState((s: any) => !!s.thread?.isRunning);
    const auiTokenApprox = useAuiState((s: any) => {
      const last = s.thread?.messages?.at?.(-1);
      const txt = last?.content?.find((p: any) => p.type === "text")?.text || "";
      return Math.floor((txt.length || 0) / 4);
    });

    return (
      <StatusBarPrimitive.Root borderStyle="single" paddingX={1} marginTop={0}>
        <Text color="cyan" bold>MODE:</Text>
        <Text bold> {mode} </Text>
        <Text dimColor>|</Text>
        <Text color="green" bold>MODEL:</Text>
        <StatusBarPrimitive.ModelName name={currentModel} />
        <Text dimColor>|</Text>
        <StatusBarPrimitive.Status format={(s: string) => `STATUS:${(s || "idle").toUpperCase()}`} />
        <Text dimColor>|</Text>
        <Text> PX:{pxReady ? "live-ok" : "pure-sim"} </Text>
        {lastRunParams ? (
          <Text> | {lastRunParams.steps}p{lastRunParams.optimize ? "/opt" : ""} seed={lastRunParams.seed} </Text>
        ) : null}
        <Text dimColor>|</Text>
        <StatusBarPrimitive.MessageCount />
        <Text> </Text>
        <StatusBarPrimitive.TokenCount />
        <Text>~{auiTokenApprox}t </Text>
        {lastLatencyMs > 0 ? <Text>| {lastLatencyMs}ms </Text> : null}
        <Text dimColor>|</Text>
        <Text> {roots.metaUtilitiesRoot ? "meta:ok" : "meta:walk"} </Text>
        <Text dimColor>|</Text>
        <Text dimColor> Ctrl-C exit | /help | Tab </Text>
        {isRunning ? <Text color="yellow"> ⏳ 2-layer-timeout </Text> : null}
      </StatusBarPrimitive.Root>
    );
  };

  const headerHeight = 3; // title + meta line
  const effectiveRows = Math.max(20, windowSize.rows || 32);

  return (
    <Box flexDirection="column" height={effectiveRows}>
      <AssistantRuntimeProvider runtime={runtime}>
        <ThreadPrimitive.Root>
          {/* Header (outside strict viewport but inside provider for potential future aui hooks) */}
          <Box paddingX={1} paddingBottom={0} flexShrink={0}>
            <Text bold color="green">Oteemo Assistant — @assistant-ui/react-ink (full primitives) + rich status bar</Text>
            <Text dimColor> meta:{roots.metaUtilitiesRoot || "(walked)"} | px:{pxReady ? "detected (live capable)" : "not detected (pure sim 100% functional)"}</Text>
          </Box>

          {/* Main content column with explicit height to enable footer anchoring */}
          <Box flexDirection="column" flexGrow={1} height={effectiveRows - headerHeight - 4 /*composer+status approx*/} paddingX={1}>
            <ThreadPrimitive.Messages components={{ Message: OteemoMessage }} />
            <ThreadPrimitive.Empty>
              <Box flexDirection="column" borderStyle="round" borderColor="green" paddingX={1} paddingY={0} marginBottom={1}>
                <Text bold color="green">Oteemo context: Raja (CEO/FinOps), Arka (VP Tech/platform), Rod (Fed Delivery), Clifford (Axiom FinOps contractor).</Text>
                <Text dimColor>Governed by oteemo/ontology/agents/*.yaml (odrs-agents/1). Artifacts under oteemo/reports/.</Text>
                <Text dimColor>Quick actions: 'run oteemo 12 --optimize live', 'pull gmail PEO', 'enrich with live', 'show report', 'validate', 'health', 'help', 'ingest ontology', 'show ontology MemoryItem', 'ontology search finops', 'delete ontology raja_gudepu_ceo', 'delete ontology --source "oteemo/ontology/agents"', 'delete ontology --name MemoryItem', 'multi-run camel-oasis-scaffold/examples/multi_scenarios.json --target modal'.</Text>
                <Text dimColor>Ontology recall (Weaviate meta_ontology) + LinkML-&gt;Weaviate additive. Pure sim + disk YAMLs 100% (graceful if no Weaviate or research extra). Bottom bar always explains mode (incl. Ontology Reindex/Search) + model + px + keys.</Text>
              </Box>
            </ThreadPrimitive.Empty>

            {/* Loading experience (surfaces during adapter run / MCP calls) */}
            <LoadingPrimitive.Root>
              <LoadingPrimitive.Spinner />
              <Text> </Text>
              <LoadingPrimitive.Text>running (two-layer timeout protected: client SCENARIO_RESEARCH_TIMEOUT_SEC + host tool_timeouts)</LoadingPrimitive.Text>
              <LoadingPrimitive.ElapsedTime />
            </LoadingPrimitive.Root>
          </Box>

          {/* Composer (inside Thread.Root per framework) */}
          <Box borderStyle="round" paddingX={1} marginX={1} flexShrink={0}>
            <Text dimColor>&gt; </Text>
            {/*
              submitOnEnter is REQUIRED for Enter to dispatch. In @assistant-ui/react-ink ^0.0.23,
              ComposerInput defaults submitOnEnter={false}; with it false, key.return is swallowed
              (no submit, no newline in single-line mode) so aui.composer().send() — and therefore
              our ChatModelAdapter.run / parseIntent dispatch — is never invoked. The library's own
              README example uses `submitOnEnter`. This was the root cause of "cannot submit anything"
              in the interactive TUI. Single-line (multiLine omitted) so Enter submits the command.
            */}
            <ComposerPrimitive.Input
              submitOnEnter
              placeholder="run oteemo 6 --optimize | pull gmail PEO | ... | multi-run camel-oasis-scaffold/examples/multi_scenarios.json --target modal | dispatch multi scenario to modal <file> | help"
              autoFocus
            />
          </Box>

          {/* The star: persistent rich bottom status bar (anchored via layout + window height) */}
          <OteemoStatusBar />
        </ThreadPrimitive.Root>
      </AssistantRuntimeProvider>
    </Box>
  );
}
