"""P1 gap: cost.py

Computes local vs API token split and rough $ estimate for a run/ask.
For P0 this is a stub that the mcp can call; real accounting hooks into router + workforce traces.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostBreakdown:
    local_tokens: int
    api_tokens: int
    estimated_usd: float
    local_model: str | None = None
    api_model: str | None = None


def estimate_cost(local_tokens: int = 0, api_tokens: int = 0, local_model: str | None = None, api_model: str | None = None) -> CostBreakdown:
    # Very rough: $0.15 / 1M local-ish, $3/1M frontier for example
    usd = (local_tokens / 1_000_000 * 0.15) + (api_tokens / 1_000_000 * 3.0)
    return CostBreakdown(local_tokens, api_tokens, round(usd, 4), local_model, api_model)
