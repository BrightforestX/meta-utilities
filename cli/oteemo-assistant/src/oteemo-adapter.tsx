/**
 * Oteemo-focused chat adapter + custom renders for the ink TUI.
 *
 * - Parses simple commands or natural language triggers.
 * - Calls the multi-server manager (scenario + px).
 * - Renders ScenarioRun summary, leader rec cards, sparklines, PDR notes, and full report markdown.
 * - Supports follow-ups: re-run with tweak, validate yaml, compare seeds, "enrich with live" (px).
 *
 * Graceful when px not available (pure sim path remains 100% functional).
 */

import React, { useEffect, useState } from "react";
import { Box, Text, useApp, useInput } from "ink";
import { promises as fs } from "fs";
import path from "path";
import { createMcpManager, type McpManager } from "./mcp-manager.js";
import { LeaderCard, type LeaderRec } from "./components/LeaderCard.js";
import { Sparkline } from "./components/Sparkline.js";
import { discoverRoots } from "./paths.js";

type Msg = { role: "user" | "assistant"; content: string; meta?: any };

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
    // Accept pasted yaml after the word, or a bare "validate" to validate a default snippet
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
  // Very light parser for the "Concrete Recommendations" section in the generated oteemo md
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
  // The report contains text lines like:
  // **Utilization trajectory (baseline spark for visual)**: ············
  // **Maturity trajectory**: ▁▂▃▄▄▅▆▆▇█
  const utilLine = report.match(/\*\*Utilization[^:]*\*\*:\s*([▁▂▃▄▅▆▇█·]+)/);
  const matLine = report.match(/\*\*Maturity[^:]*\*\*:\s*([▁▂▃▄▅▆▇█·]+)/);
  // Convert the unicode bars back to approximate numeric series for the Sparkline component (demo scale)
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

export function OteemoChat() {
  const [manager, setManager] = useState<McpManager | null>(null);
  const [messages, setMessages] = useState<Msg[]>([
    { role: "assistant", content: "Oteemo context: Raja (CEO/FinOps), Arka (VP Tech/platform), Rod (Fed Delivery), Clifford (Axiom FinOps contractor). Internal Axiom vs client billable governed by oteemo/ontology/agents/*.yaml (odrs-agents/1)." },
    { role: "assistant", content: "Quick actions: 'run oteemo 12 --optimize', 'run oteemo 6', 'show current Raja policy', 'list scenarios', 'enrich with live', 'help'. (Empty-state banner + quick actions per plan.)" },
    { role: "assistant", content: "Oteemo Terminal Assistant ready. 'run oteemo 12 --optimize' | 're-run 8' | 'show report' | 'enrich with live' | 'help'. Pure sim works without px/DBs." },
  ]);
  const [busy, setBusy] = useState(false);
  const [busyDots, setBusyDots] = useState(0);
  const [lastLiveContext, setLastLiveContext] = useState<any>(null); // LiveBusinessContext from px pulls; used to seed / cite in oteemo results
  const app = useApp();

  // Simple animated status for long-running calls (respects two-layer timeout on the MCP side).
  useEffect(() => {
    if (!busy) { setBusyDots(0); return; }
    const id = setInterval(() => setBusyDots(d => (d + 1) % 4), 400);
    return () => clearInterval(id);
  }, [busy]);

  useEffect(() => {
    let alive = true;
    createMcpManager().then((m) => { if (alive) setManager(m); });
    return () => { alive = false; /* close on unmount in real */ };
  }, []);

  const roots = discoverRoots();
  const pxReady = !!roots.pxMcpRoot;

  async function handleRunOteemo(payload: any) {
    if (!manager) return "Manager not ready.";
    setBusy(true);
    try {
      const useLive = !!payload.useLive || !!lastLiveContext;
      const res = await manager.scenario.runOteemoBillable({ steps: payload.steps, seed: 42, optimize: payload.optimize, live: useLive } as any);
      // The MCP tool returns ScenarioRun (or wrapped CallToolResult). Surface key fields.
      const run = (res && (res as any).content && Array.isArray((res as any).content)) ? (res as any).content[0]?.text : res;
      let runInfo = "";
      try {
        const parsed = typeof run === "string" ? JSON.parse(run) : run;
        if (parsed && typeof parsed === "object") {
          runInfo = `run_id=${parsed.run_id || parsed.id || "?"} status=${parsed.status || "ok"} steps=${parsed.n_steps || payload.steps} seed=${parsed.seed ?? 42}`;
          if (parsed.db_path) runInfo += ` db=${parsed.db_path}`;
        }
      } catch { /* not json, use raw */ }
      const liveNote = useLive && lastLiveContext ? " (live-seeded with px signals)" : "";
      const summary = `oteemo_billable ${payload.steps}p seed=42 ${payload.optimize ? "(optimized)" : ""}${liveNote} — ${runInfo || "artifacts in oteemo/reports/"}`;

      // Try to load the latest generated report for real leader recs + sparklines + full markdown
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
          {
            name: "Raja (CEO/FinOps)",
            role: "strategy + FinOps",
            rec: "Target axiom_invest_frac per optimized policy; finops_tier for maturity floor.",
            metric: "maturity >=0.35",
          },
          {
            name: "Arka (VP Tech)",
            role: "platform leverage",
            rec: "Focus GraphRAG/A2A leverage; efficiency_mult compounds.",
            metric: "efficiency",
          },
          {
            name: "Rod (Fed Delivery)",
            role: "billable owner",
            rec: "client_target_util + bid_aggressiveness per horizon windows." + (useLive && lastLiveContext ? "  [LIVE: +bid_aggr suggested from recent client thread volume]" : ""),
            metric: "util / bench",
          },
          {
            name: "Clifford (Contractor)",
            role: "Axiom FinOps fixed",
            rec: "Fixed internal_platform + PDR telemetry for cost attribution.",
            metric: "+maturity boost",
          },
        ];
      }
      const ranked = rankLowestRiskFirst(recs.map((r) => enrichRecommendation(r, useLive)));
      const topTwo = ranked.slice(0, 2);
      const note = latest
        ? `Report: ${latest.path}. Showing top 2 lowest execution-risk candidates. Follow up: 're-run 8 --optimize', 'show report', 'validate <yaml>', 'pull gmail PEO', 'enrich with live'.`
        : "Full report + json written under oteemo/reports/. Showing top 2 lowest execution-risk candidates.";

      const liveBusinessContext = useLive && lastLiveContext ? lastLiveContext : undefined;
      return { summary, recs: topTwo, note, reportMd, sparkUtil, sparkMat, raw: run, liveBusinessContext };
    } finally {
      setBusy(false);
    }
  }

  async function handleEnrich() {
    if (!manager || !manager.px) return "px not available (pure sim path remains fully functional). See px build guidance.";
    try {
      const hint = await manager.px.onboardingComposioHint();
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
  }

  async function handlePullBusinessContext(query: string) {
    if (!manager || !manager.px) return "px not available (pure sim path remains fully functional). Build px-mcp-ts and ensure COMPOSIO/ARCADE keys on its host env.";
    const q = query.toLowerCase();
    try {
      let toolCall: { name: string; args?: any } | null = null;
      if (q.includes("gmail") || q.includes("email") || q.includes("peo")) {
        // Safe read: list tools or a generic list; actual search would use composio_call_tool with user's connected gmail toolkit qualified name
        toolCall = { name: "composio_list_tools", args: { slug: "gmail" } };
      } else if (q.includes("slack")) {
        toolCall = { name: "composio_list_tools", args: { slug: "slack" } };
      } else if (q.includes("calendar") || q.includes("availability")) {
        toolCall = { name: "composio_list_tools", args: { slug: "google_calendar" } };
      } else if (q.includes("salesforce") || q.includes("hubspot") || q.includes("pipeline") || q.includes("opportunity")) {
        toolCall = { name: "composio_list_apps", args: {} }; // or list_tools for salesforce
      } else if (q.includes("notion") || q.includes("confluence") || q.includes("arch")) {
        toolCall = { name: "composio_list_tools", args: { slug: "notion" } };
      } else if (q.includes("linkedin") || q.includes("enrich")) {
        toolCall = { name: "arcade_list_toolkits", args: {} };
      } else {
        // Default safe discovery
        toolCall = { name: "px_onboarding_composio_hint", args: {} };
      }

      const result = await manager.px.call(toolCall.name, toolCall.args || {});
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
  }

  async function send(text: string) {
    setMessages((m) => [...m, { role: "user", content: text }]);
    const intent = parseIntent(text);
    let reply: any = "Command not recognized. Try 'run oteemo 6 --optimize' or 'help'.";

    if (intent.kind === "run_oteemo") {
      reply = await handleRunOteemo(intent.payload);
    } else if (intent.kind === "pull_context") {
      reply = await handlePullBusinessContext(intent.payload?.query || "");
    } else if (intent.kind === "enrich_px") {
      reply = await handleEnrich();
    } else if (intent.kind === "health") {
      reply = manager ? "scenario + px (if present) connected. Use 'run oteemo'." : "Manager initializing...";
    } else if (intent.kind === "help") {
      reply = "Commands: run oteemo N [--optimize] [live], re-run N, show report, pull gmail|slack|calendar|salesforce|notion, enrich/live/context/px, validate <yaml or paste>, health, help. Defaults to top 2 lowest-risk candidates with reasoning + composio/arcade execution path hints.";
    } else if (intent.kind === "validate_yaml") {
      if (manager) {
        try {
          const v = await manager.scenario.call("validate_agent_yaml", { yaml_text: intent.payload?.yaml || "" });
          reply = typeof v === "string" ? v : JSON.stringify(v, null, 2);
        } catch (e: any) {
          reply = `validate error: ${String(e)}`;
        }
      } else {
        reply = "Manager not ready for validate.";
      }
    } else if (intent.kind === "show_report") {
      const latest = await loadLatestOteemoReport(roots.metaUtilitiesRoot);
      if (latest) {
        reply = `=== ${latest.path} ===\n\n${latest.content}`;
      } else {
        reply = "No oteemo report found yet under oteemo/reports/. Run an oteemo scenario first (the rich demo with --optimize writes the full governed recs).";
      }
    }

    const assistantContent = typeof reply === "string"
      ? reply
      : ((reply as any)?.summary ? (reply as any).summary : JSON.stringify(reply, null, 2).slice(0, 300));
    setMessages((m) => [...m, { role: "assistant", content: assistantContent, meta: reply as any }]);
  }

  // Simple keyboard: Ctrl-C exits
  useInput((input, key) => {
    if (key.ctrl && input === "c") {
      if (manager) manager.closeAll().finally(() => app.exit());
      else app.exit();
    }
  });

  // Minimal plain-ink "composer" (no assistant-ui primitives in this build; the custom oteemo cards + logic + px integration are the substance).
  const [input, setInput] = useState("");
  useInput((char, key) => {
    if (key.return) {
      const val = input.trim();
      if (val) {
        setInput("");
        // fire and forget; send updates messages
        void send(val);
      }
    } else if (key.backspace || key.delete) {
      setInput((s) => s.slice(0, -1));
    } else if (char && !key.ctrl && !key.meta) {
      setInput((s) => s + char);
    }
  });

  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color="green">Oteemo Assistant — governed oteemo_billable + optional px live context (plain-ink smoke build)</Text>
      <Text dimColor>meta: {roots.metaUtilitiesRoot || "(walked)"} | px: {roots.pxMcpRoot ? "present" : "not detected (pure sim OK)"}</Text>

      {/* Manual viewport over messages (equivalent surface to ThreadPrimitive.Viewport for this TUI) */}
      <Box flexDirection="column" marginBottom={1} borderStyle="round" paddingX={1}>
        {messages.map((m, i) => (
          <Box key={i} flexDirection="column" marginBottom={1}>
            <Text bold color={m.role === "user" ? "blue" : "magenta"}>{m.role}:</Text>
            {typeof m.meta === "object" && m.meta?.recs ? (
              <>
                <Text>{m.meta.summary}</Text>
                {m.meta.recs.map((r: LeaderRec, idx: number) => <LeaderCard key={idx} rec={r} />)}
                {m.meta.sparkUtil ? <><Text dimColor>util:</Text><Sparkline values={m.meta.sparkUtil} /></> : null}
                {m.meta.sparkMat ? <><Text dimColor>maturity:</Text><Sparkline values={m.meta.sparkMat} /></> : null}
                {m.meta.note ? <Text dimColor>{m.meta.note}</Text> : null}
                {m.meta.liveBusinessContext ? (
                  <Box borderStyle="round" paddingX={1} marginTop={1} flexDirection="column">
                    <Text bold color="yellow">LiveBusinessContext (px signals @ {m.meta.liveBusinessContext.timestamp})</Text>
                    <Text dimColor>{JSON.stringify(m.meta.liveBusinessContext.citations || []).slice(0, 280)}...</Text>
                    <Text dimColor>Signals can seed firm_init (win_p, capacity) or suggest policy deltas for next run. Citations above for audit.</Text>
                  </Box>
                ) : null}
                {m.meta.reportMd ? <Box marginTop={1}><Text>{m.meta.reportMd}</Text></Box> : null}
              </>
            ) : (
              <Text>{m.content}</Text>
            )}
          </Box>
        ))}
        {busy ? <Text color="yellow">⏳ running (two-layer timeout protected){".".repeat(busyDots)}</Text> : null}
      </Box>

      {/* Simple composer line */}
      <Box>
        <Text dimColor>&gt; </Text>
        <Text>{input || "(type command + Enter; e.g. 'run oteemo 4', 'pull gmail PEO', 'enrich with live', 'show report', 'help')"}</Text>
      </Box>

      <Text dimColor>Ctrl-C to exit. Artifacts land under oteemo/reports/. Pure sim works without px or DBs. (This is the plain-ink smoke shell; assistant-ui primitives can be restored when their 0.1+ packages are published.)</Text>
    </Box>
  );
}
