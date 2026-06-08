"""CAMEL multi-scenario simulation service scaffold.

The package keeps the attached Modal/SGLang design usable from local CLI runs:
local execution is deterministic and dependency-light, while CAMEL, Modal, and
SGLang are optional integration layers.
"""
from __future__ import annotations

from .config.scenarios import AgentDefinition, ScenarioConfig
from .simulation.runner import run_scenario, run_scenarios
from .simulation.state import SimulationState

__all__ = [
    "AgentDefinition",
    "ScenarioConfig",
    "SimulationState",
    "run_scenario",
    "run_scenarios",
]
