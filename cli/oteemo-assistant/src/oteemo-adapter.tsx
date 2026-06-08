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
import { Box, Text, useApp, useInput, useStdout } from "ink";
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
  | "Ontology Delete";

type LastRunParams = {
  steps: number;
  seed: number;
  optimize: boolean;
} | null;

function parseIntent(text: string): { kind: string; payload?: any } {
  const t = text.trim().toLowerCase();
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
  if (t.includes("enrich") || t.includes("live") || t.includes("context") || t.includes("px")) {
    return { kind: "enrich_px" };
  }
  if (t === "health" || t === "status") return { kind: "health" };
  if (t === "help" || t === "/help") return { kind: "help" };
  // Ontology recall (first-cut; thin call through MCP manager + nice cards/markdown)
  if (t.startsWith("ingest ontology") || t.startsWith("reindex ontology") || t === "reindex" || t.includes("ontology ingest")) {
    return { kind: "ingest_ontology", payload: { target: "weaviate" } };
  }
  if (t.startsWith("show ontology") || t.startsWith("ontology show")) {
    const m = t.match(/show ontology\s+(.+)$/);
    const name = m ? m[1].trim() : "";
    return { kind: "show_ontology", payload: { name } };
  }
  if (t.startsWith("ontology search ") || t.startsWith("search ontology ")) {
    const q = t.replace(/^ontology search |^search ontology /, "").trim();
    return { kind: "search_ontology", payload: { query: q || t } };
  }
  // Delete ontology (first-class; supports bare name after, or --name / --source / --entity-type / --all)
  if (t.startsWith("delete ontology") || t.startsWith("ontology delete")) {
    const rest = t.replace(/^delete ontology |^ontology delete /, "").trim();
    const payload: any = {};
    if (rest === "--all" || rest.includes("--all")) {
      payload.delete_all = true;
    } else if (rest.startsWith("--name ")) {
      payload.name = rest.replace("--name ", "").trim();
    } else if (rest.startsWith("--source ")) {
      payload.source = rest.replace("--source ", "").trim().replace(/^["']|["']$/g, "");
    } else if (rest.startsWith("--entity-type ") || rest.startsWith("--entity_type ")) {
      payload.entity_type = rest.replace(/--entity-?type /, "").trim();
    } else if (rest) {
      // bare e.g. "delete ontology raja_gudepu_ceo" or "delete ontology MemoryItem" or "delete ontology --name foo" handled above
      payload.name = rest;
    }
    return { kind: "delete_ontology", payload };
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

// Small live context box (yellow per prior design, polished)
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

// useWindowSize polyfill (works on ink 5 + any node; query calls for "ink's useWindowSize() + layout (height=rows or ViewportFooter patterns)")
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

  const app = useApp();
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
      }
    });
    return () => { alive = false; };
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

    const latest = await loadLatestOteemoReport(roots.metaUtilitiesRoot);
    let recs: LeaderRec[] = [];
    let sparkUtil: number[] | undefined;
    let sparkMat: number[] | undefined;
    let reportMd = "";
    if (latest) {
      recs = extractLeaderRecsFromReport(latest.content);
      const sp = extractSparklinesFromReport(latest.content);
      sparkUtil = sp.util;
      sparkMat = sp.maturity;
      reportMd = latest.content.split("\n").slice(0, 40).join("\n") + "\n... (use 'show report' for full)";
    }
    if (recs.length === 0) {
      recs = [
        { name: "Raja (CEO/FinOps)", role: "strategy + FinOps", rec: "Target axiom_invest_frac per optimized policy; finops_tier for maturity floor.", metric: "maturity >=0.35" },
        { name: "Arka (VP Tech)", role: "platform leverage", rec: "Focus GraphRAG/A2A leverage; efficiency_mult compounds.", metric: "efficiency" },
        { name: "Rod (Fed Delivery)", role: "billable owner", rec: "client_target_util + bid_aggressiveness per horizon windows." + (useLive ? "  [LIVE: +bid_aggr suggested from recent client thread volume]" : ""), metric: "util / bench" },
        { name: "Clifford (Contractor)", role: "Axiom FinOps fixed", rec: "Fixed internal_platform + PDR telemetry for cost attribution.", metric: "+maturity boost" },
      ];
    }
    const note = latest
      ? `Report: ${latest.path}. Follow up: 're-run 8 --optimize', 'show report', 'validate <yaml>', 'pull gmail PEO', 'enrich with live'.`
      : "Full report + json written under oteemo/reports/. Follow up with 're-run ...' or 'show report'.";

    const liveBusinessContext = useLive && (liveCtxOverride || lastLiveRef.current) ? (liveCtxOverride || lastLiveRef.current) : undefined;
    return { summary, recs, note, reportMd, sparkUtil, sparkMat, raw: run, liveBusinessContext };
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
      } catch { /* not json */ }
      return { kind: "ontology_result", summary, raw: parsed };
    } catch (e: any) {
      return `ingest_ontology error (graceful; pure sim + disk YAMLs unaffected): ${String(e)}`;
    }
  }, []);

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
        yield { content: [{ type: "text", text: "Oteemo Assistant ready. Type a command (e.g. 'run oteemo 6 --optimize live'). New: 'delete ontology <name | --name X | --source Y | --all (careful)>'." }] };
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
        outText = mgr ? "scenario + px (if present) connected. Use 'run oteemo'." : "Manager initializing...";
      } else if (intent.kind === "help") {
        setMode("Help");
        outText = "Commands: run oteemo N [--optimize] [live], re-run N, show report, pull gmail|slack|calendar|salesforce|notion, enrich/live/context/px, validate <yaml or paste>, health, help, ingest ontology | reindex ontology, show ontology <MemoryItem|raja_gudepu_ceo|...>, ontology search finops, delete ontology <name|raja_gudepu_ceo| --name X | --source \"oteemo/ontology/agents\" | --entity-type role | --all (careful)>. px pulls surface as LiveBusinessContext (yellow); seed oteemo recs. Ontology results (incl. delete: count + removed names) use cyan. Bottom bar shows MODE (incl. Ontology Reindex/Search/Delete). Pure sim + disk YAMLs work without Weaviate.";
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
      } else {
        setMode("Command");
        outText = "Unrecognized command. Try 'run oteemo 6 --optimize live', 'pull gmail PEO', 'enrich with live', 'show report', 'help', 'ingest ontology', 'show ontology MemoryItem', 'ontology search finops', 'delete ontology raja_gudepu_ceo | --name MemoryItem | --source oteemo/... | --all (careful)'.";
      }

      const latency = Date.now() - t0;
      setLastLatencyMs(latency);

      const content: any[] = [{ type: "text", text: outText }];
      if (rich && typeof rich === "object" && (rich.recs || rich.reportMd || rich.liveBusinessContext || rich.ctx || rich.kind === "ontology_result" || rich.hits || rich.kind === "ontology_delete_result" || (rich.deleted != null))) {
        content.push({ type: "data", data: { kind: rich.kind === "ontology_delete_result" ? "ontology_delete_result" : (rich.kind === "ontology_result" ? "ontology_result" : "oteemo_structured"), ...rich, _execLatencyMs: latency } });
      }
      yield { content };
    },
  }), []); // stable identity; internal refs + setState keep behavior fresh

  const runtime = useLocalRuntime(adapter);

  // Global hotkeys (Ctrl-C clean shutdown of MCPs)
  useInput((input, key) => {
    if (key.ctrl && input === "c") {
      const mgr = managerRef.current;
      if (mgr) {
        mgr.closeAll().finally(() => app.exit());
      } else {
        app.exit();
      }
    }
    // Future: Tab for composer focus / suggestions (framework may provide; documented in status + recommendations)
  });

  // Custom rich message renderer (re-uses/enhances existing cards + adds MarkdownText + data-part support)
  const OteemoMessage = () => {
    const message = useAuiState((s: any) => s.message);
    const textPart = message.content?.find((p: any) => p.type === "text");
    const dataPart = message.content?.find((p: any) => p.type === "data" && p.data && (p.data.kind === "oteemo_structured" || p.data.recs || p.data.kind === "ontology_result" || p.data.kind === "ontology_delete_result" || (p.data.deleted != null)));
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
                <Text dimColor>Quick actions: 'run oteemo 12 --optimize live', 'pull gmail PEO', 'enrich with live', 'show report', 'validate', 'health', 'help', 'ingest ontology', 'show ontology MemoryItem', 'ontology search finops', 'delete ontology raja_gudepu_ceo', 'delete ontology --source "oteemo/ontology/agents"', 'delete ontology --name MemoryItem'.</Text>
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
            <ComposerPrimitive.Input
              placeholder="run oteemo 6 --optimize | pull gmail PEO | enrich | show report | ingest ontology | show ontology MemoryItem | ontology search finops | delete ontology raja... | --name X | --source Y | --all (careful) | help"
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
