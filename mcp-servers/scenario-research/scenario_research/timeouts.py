"""Two-layer timeout contract for ODRS long-running operations (P0 frozen).

Client env var (inside the process/MCP):
  SCENARIO_RESEARCH_TIMEOUT_SEC  (default 1800 = 30 min)

Host level (Grok/Cursor/Claude config):
  tool_timeouts.scenario_research  (or per-tool like run_scenario, ask)

All long tools must respect the min of the two layers.
This module is the single source for the names and defaults.
"""
from __future__ import annotations

import os

# Client-side default (tunable via env for different hosts/CI)
DEFAULT_TIMEOUT_SEC: float = 1800.0  # 30 minutes for population sims + workforce

ENV_VAR: str = "SCENARIO_RESEARCH_TIMEOUT_SEC"


def get_timeout_seconds() -> float:
    """Return the effective client timeout (env override or default)."""
    val = os.getenv(ENV_VAR)
    if val is not None:
        try:
            return float(val)
        except ValueError:
            pass
    return DEFAULT_TIMEOUT_SEC


# Commonly referenced tool names for host timeout config
LONG_RUNNING_TOOLS: list[str] = [
    "scenario_research_health",  # short
    "run_scenario",
    "ingest_ontology",
    "search_ontology",
    # future: "ask", "fit_models", "execute_replicate_batch" etc.
]
