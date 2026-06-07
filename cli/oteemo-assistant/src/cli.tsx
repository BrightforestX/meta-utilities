#!/usr/bin/env node
/**
 * oteemo-assistant — Interactive terminal assistant (Ink + @assistant-ui/react-ink)
 * over scenario-research-mcp (ODRS/oteemo) + optional gsd-mcp-server (px-mcp for business context).
 *
 * This is the opt-in Node surface. Python MCP + CLI paths remain fully functional.
 * All secrets (COMPOSIO/ARCADE) live only in the px-mcp host process env.
 */

import React from "react";
import { render } from "ink";
import { OteemoChat } from "./oteemo-adapter.js";

render(<OteemoChat />);
