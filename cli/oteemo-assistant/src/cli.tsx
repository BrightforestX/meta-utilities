#!/usr/bin/env node
/**
 * oteemo-assistant — Interactive terminal assistant (Ink + @assistant-ui/react-ink ^0.0.23 + react-ink-markdown)
 * over scenario-research-mcp (ODRS/oteemo) + optional gsd-mcp-server (px-mcp for business context).
 *
 * Full primitives adoption: AssistantRuntimeProvider + custom useLocalRuntime bridge, ThreadPrimitive.*,
 * ComposerPrimitive.Input, LoadingPrimitive.*, ThreadPrimitive.Empty, StatusBarPrimitive.* (the star: rich persistent
 * bottom bar with MODE/MODEL/STATUS/PX/params/latency/tokens/keys), MarkdownText for reports.
 *
 * This is the opt-in Node surface. Python MCP + CLI paths remain fully functional.
 * All secrets (COMPOSIO/ARCADE) live only in the px-mcp host process env.
 * Pure simulation is 100% functional with zero px tree / keys / DBs.
 */

import React from "react";
import { render } from "ink";

// Local dupe of parseIntent (pure, top-level, no React side effects) so headless
// can run without fully parsing/ loading the (currently brace-unstable) adapter module body.
function parseIntentLocal(text: string): { kind: string; payload?: any } {
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
    // Case-preserving extraction (dupe of adapter parseIntent): ensures --headless `delete ontology MemoryItem` etc. forward original case
    // to delete_ontology (exact name match in Weaviate) instead of lowercased values.
    const m = original.match(/^(?:show ontology|ontology show)\s+(.+)$/i);
    const name = m ? m[1].trim() : "";
    return { kind: "show_ontology", payload: { name } };
  }
  if (t.startsWith("ontology search ") || t.startsWith("search ontology ")) {
    const q = original.replace(/^ontology search |^search ontology /i, "").trim();
    return { kind: "search_ontology", payload: { query: q || original } };
  }
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
      payload.name = rest;
    }
    return { kind: "delete_ontology", payload };
  }
  // Remote multi-scenario dispatch to Modal (headless dupe of adapter parse; keep in sync)
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
    return { kind: "multi_run_modal", payload };
  }
  return { kind: "chat", payload: { text } };
}

async function runHeadless() {
  // One-shot headless path for scripts/CI/pipes. Bypasses Ink UI entirely.
  // Uses McpManager + parseIntent (from adapter) + direct scenario/px calls (same contracts as TUI).
  // Supports: --command '...' or piping input when --headless (no TTY).
  // Exits 0 on success (even for graceful "px not available"), 1 on fatal.
  const { createMcpManager } = await import("./mcp-manager.js");
  const args = process.argv.slice(2);
  let cmd = "";
  const cmdIdx = args.findIndex(a => a === "--command" || a === "-c");
  if (cmdIdx >= 0 && args[cmdIdx + 1]) {
    cmd = args[cmdIdx + 1];
  } else if (!process.stdin.isTTY) {
    const chunks: Uint8Array[] = [];
    for await (const chunk of process.stdin) {
      chunks.push(chunk as Uint8Array);
    }
    cmd = Buffer.concat(chunks as any).toString("utf8").trim();
  } else {
    // last non-flag arg as command
    cmd = args.filter(a => !a.startsWith("--")).pop() || "health";
  }
  if (!cmd) cmd = "health";

  const manager = await createMcpManager();
  const intent = parseIntentLocal(cmd);
  let out: any = null;
  try {
    if (intent.kind === "health" || intent.kind === "status") {
      out = { status: "ok", scenario: !!(manager && manager.scenario), px: !!(manager && manager.px) };
    } else if (intent.kind === "run_oteemo") {
      const p = intent.payload || { steps: 4, optimize: false, useLive: false };
      // 'live' dropped to match runOteemoBillable({steps?, seed?, optimize?}) interface (TS2353); useLive was for intent classification only
      out = await manager.scenario.runOteemoBillable({ steps: p.steps || 4, seed: 42, optimize: !!p.optimize });
    } else if (intent.kind === "ingest_ontology") {
      out = await manager.scenario.call("ingest_ontology", { target: "weaviate" });
    } else if (intent.kind === "search_ontology") {
      const q = (intent.payload && intent.payload.query) || cmd.replace(/.*search ontology |.*ontology search /i, "").trim() || "finops";
      out = await manager.scenario.call("search_ontology", { query: q, top_k: 5 });
    } else if (intent.kind === "show_ontology") {
      const q = (intent.payload && intent.payload.name) || cmd.replace(/.*show ontology |.*ontology show /i, "").trim() || "MemoryItem";
      out = await manager.scenario.call("search_ontology", { query: q, top_k: 5 });
    } else if (intent.kind === "delete_ontology") {
      const pl = intent.payload || {};
      const args: any = {};
      if (pl.delete_all) args.delete_all = true;
      if (pl.name) args.name = pl.name;
      if (pl.source) args.source = pl.source;
      if (pl.entity_type) args.entity_type = pl.entity_type;
      out = await manager.scenario.call("delete_ontology", args);
    } else if (intent.kind === "multi_run_modal") {
      const p = intent.payload || {};
      const args: any = { scenario_file: p.scenario_file };
      if (p.execution_mode) args.execution_mode = p.execution_mode;
      if (p.output_format) args.output_format = p.output_format;
      if (p.server_urls_json) args.server_urls_json = p.server_urls_json;
      out = await manager.scenario.call("dispatch_multi_scenario_to_modal", args);
    } else if (intent.kind === "enrich_px" || intent.kind === "pull_context") {
      if (manager && manager.px) {
        out = await manager.px.onboardingComposioHint();
      } else {
        out = { note: "px not available (pure sim ok)", pureSim: true };
      }
    } else if (intent.kind === "help") {
      out = "headless oteemo-assistant: health | run oteemo N [--optimize] | ingest|show|search|delete ontology ... | multi-run <file> --target modal (dispatch) | (px pulls graceful). Generic: any tool via manager.scenario.call after parse.";
    } else {
      // fallback: try direct call if looks like tool, else echo intent
      if (manager && manager.scenario) {
        out = { note: `unhandled headless intent ${intent.kind}; raw cmd kept for scripting (power users: 'dispatch_multi_scenario_to_modal scenario_file=...' works via direct call path)`, cmd, intent };
      } else {
        out = `headless: ${intent.kind} (no manager)`;
      }
    }
    if (typeof out === "string") {
      console.log(out);
    } else {
      console.log(JSON.stringify(out, null, 2));
    }
  } catch (e: any) {
    console.error("headless error (graceful path):", String(e));
    process.exitCode = 1;
  } finally {
    try {
      if (manager && manager.closeAll) await manager.closeAll();
    } catch {}
  }
}

const isHeadless = process.argv.includes("--headless") || process.argv.includes("--command") || process.argv.includes("-c");
if (isHeadless) {
  runHeadless().then(() => {
    if (process.exitCode == null) process.exit(0);
  }).catch((e) => {
    console.error(e);
    process.exit(1);
  });
} else {
  (async () => {
    const { OteemoChat, closeActiveManager } = await import("./oteemo-adapter.js");

    // Clean MCP client shutdown (scenario + optional px) on Ctrl-C / SIGINT.
    // This replaces the previous root-level useInput handler (which broke ComposerPrimitive.Input
    // backspace/editing for commands in the assistant-ui text box).
    const onSigInt = () => {
      // Fire-and-forget the closes (closeAll awaits transport shutdown); then exit.
      closeActiveManager()
        .catch(() => {})
        .finally(() => process.exit(0));
    };
    process.once("SIGINT", onSigInt);

    render(<OteemoChat />);
  })();
}
