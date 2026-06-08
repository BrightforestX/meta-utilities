"""Scenario configuration schemas for multi-scenario analysis."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .models import DOMAIN_TO_MODEL


TerminationCondition = Literal[
    "all_contracts_accepted",
    "any_contract_accepted",
    "finding_threshold",
    "coalition_formed",
]


class AgentDefinition(BaseModel):
    id: str
    role: str
    domain: str
    persona: str

    @field_validator("domain")
    @classmethod
    def known_domain(cls, value: str) -> str:
        if value not in DOMAIN_TO_MODEL:
            known = ", ".join(sorted(DOMAIN_TO_MODEL))
            raise ValueError(f"unknown domain {value!r}; expected one of: {known}")
        return value


class ScenarioConfig(BaseModel):
    id: str
    name: str
    description: str
    agents: list[AgentDefinition]
    max_ticks: int = Field(default=20, ge=1, le=10_000)
    termination_condition: TerminationCondition | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


EXAMPLE_SCENARIO = {
    "id": "contract_001",
    "name": "Two-party service contract negotiation",
    "description": "A buyer and seller negotiate a 12-month SaaS contract",
    "max_ticks": 4,
    "termination_condition": "any_contract_accepted",
    "parameters": {
        "contract_terms": {
            "price_usd": 50000,
            "term_months": 12,
            "payment": "annual prepay",
        }
    },
    "agents": [
        {
            "id": "buyer_1",
            "role": "buyer",
            "domain": "negotiation",
            "persona": (
                "You are a procurement manager seeking maximum cost efficiency. "
                "You have a hard budget cap of $50,000/year."
            ),
        },
        {
            "id": "seller_1",
            "role": "seller",
            "domain": "negotiation",
            "persona": (
                "You are a sales director aiming for a $65,000 contract. "
                "You can offer up to 15% discount for annual prepayment."
            ),
        },
    ],
}


def load_scenario_configs(path: Path) -> list[ScenarioConfig]:
    """Load one scenario config or a list of configs from JSON."""
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("scenario file must contain a JSON object or array")
    return [ScenarioConfig.model_validate(item) for item in payload]


def write_example_scenario(path: Path) -> Path:
    """Write an example scenario config for users to edit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([EXAMPLE_SCENARIO], indent=2) + "\n")
    return path
