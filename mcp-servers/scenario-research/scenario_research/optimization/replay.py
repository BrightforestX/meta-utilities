"""P6 replay: run optimized policy back through OASIS+math path and capture robustness.

Stub for P0; real would re-execute scenario with policy params from optimizer and diff fits.
"""
from __future__ import annotations

from typing import Any


def replay_policy(policy: dict[str, Any], scenario: str = "info_spread") -> dict[str, Any]:
    """Return a robustness report stub.

    In full impl: execute_scenario with policy knobs, load db, refit, compute deltas vs baseline.
    """
    return {
        "policy": policy,
        "scenario": scenario,
        "robustness_delta": {"profit": 0.0, "success_rate": 0.0},
        "uncertainty": {"profit": [ -0.1, 0.1 ]},
        "status": "stub",
    }
