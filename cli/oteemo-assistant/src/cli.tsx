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
import { OteemoChat } from "./oteemo-adapter.js";

render(<OteemoChat />);
