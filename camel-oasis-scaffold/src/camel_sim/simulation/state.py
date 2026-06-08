"""Shared simulation state for multi-scenario runs."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SimulationState(BaseModel):
    tick: int = 0
    scenario_id: str = ""

    calendar: dict[str, Any] = Field(default_factory=dict)
    ledger: dict[str, Any] = Field(default_factory=dict)
    knowledge_graph: dict[str, Any] = Field(default_factory=dict)
    messages: dict[str, Any] = Field(default_factory=dict)
    coalitions: dict[str, Any] = Field(default_factory=dict)

    event_log: list[dict[str, Any]] = Field(default_factory=list)

    def advance_tick(self) -> None:
        self.tick += 1

    def snapshot(self) -> dict[str, Any]:
        """Return a compact serializable state snapshot for agent context."""
        return {
            "tick": self.tick,
            "calendar_summary": {
                slot: item.get("agenda", "") for slot, item in self.calendar.items()
            },
            "open_proposals": {
                proposal_id: item
                for proposal_id, item in self.ledger.items()
                if item.get("status") == "pending"
            },
            "finding_count": len(self.knowledge_graph),
            "active_coalitions": [
                item for item in self.coalitions.values() if item.get("active")
            ],
            "recent_events": self.event_log[-10:],
        }
