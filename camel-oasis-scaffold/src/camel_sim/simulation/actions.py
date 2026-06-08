"""Domain action toolkits for multi-scenario simulations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .state import SimulationState

try:  # CAMEL is installed in full scaffold environments, but tests may be light.
    from camel.toolkits import FunctionTool as _CamelFunctionTool
except Exception:  # pragma: no cover - exercised only when CAMEL is absent
    _CamelFunctionTool = None


@dataclass(frozen=True)
class LocalFunctionTool:
    """Small callable wrapper matching the subset we need from CAMEL FunctionTool."""

    func: Callable[..., dict[str, Any]]

    @property
    def name(self) -> str:
        return self.func.__name__

    def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.func(*args, **kwargs)


def _wrap_tool(func: Callable[..., dict[str, Any]]) -> Any:
    if _CamelFunctionTool is not None:
        return _CamelFunctionTool(func)
    return LocalFunctionTool(func)


def make_action_functions(
    state: SimulationState,
    domain: str,
) -> dict[str, Callable[..., dict[str, Any]]]:
    """Return raw action callables for local scripted execution."""

    def schedule_meeting(
        agent_id: str,
        time_slot: str,
        participants: list[str],
        agenda: str,
    ) -> dict[str, Any]:
        """Schedule a meeting and update shared calendar state."""
        if time_slot in state.calendar and state.calendar[time_slot].get("locked"):
            return {"status": "conflict", "slot": time_slot}
        state.calendar[time_slot] = {
            "host": agent_id,
            "attendees": participants,
            "agenda": agenda,
            "locked": True,
        }
        state.event_log.append(
            {
                "action": "SCHEDULE_MEETING",
                "agent": agent_id,
                "slot": time_slot,
                "tick": state.tick,
            }
        )
        return {"status": "confirmed", "slot": time_slot}

    def cancel_meeting(agent_id: str, time_slot: str) -> dict[str, Any]:
        """Cancel a previously scheduled meeting."""
        if time_slot not in state.calendar:
            return {"status": "not_found"}
        del state.calendar[time_slot]
        state.event_log.append(
            {
                "action": "CANCEL_MEETING",
                "agent": agent_id,
                "slot": time_slot,
                "tick": state.tick,
            }
        )
        return {"status": "cancelled"}

    def propose_contract(
        agent_id: str,
        counterparty: str,
        terms: dict[str, Any],
    ) -> dict[str, Any]:
        """Submit a contract proposal to the negotiation ledger."""
        proposal_id = f"prop_{len(state.ledger):04d}"
        state.ledger[proposal_id] = {
            "from": agent_id,
            "to": counterparty,
            "terms": terms,
            "status": "pending",
            "tick": state.tick,
        }
        state.event_log.append(
            {
                "action": "PROPOSE_CONTRACT",
                "agent": agent_id,
                "proposal_id": proposal_id,
                "tick": state.tick,
            }
        )
        return {"proposal_id": proposal_id, "status": "pending"}

    def counter_proposal(
        agent_id: str,
        proposal_id: str,
        revised_terms: dict[str, Any],
    ) -> dict[str, Any]:
        """Counter an existing proposal with revised terms."""
        if proposal_id not in state.ledger:
            return {"status": "not_found"}
        original = state.ledger[proposal_id]
        new_id = f"prop_{len(state.ledger):04d}"
        state.ledger[new_id] = {
            "from": agent_id,
            "to": original["from"],
            "terms": revised_terms,
            "counter_to": proposal_id,
            "status": "pending",
            "tick": state.tick,
        }
        state.ledger[proposal_id]["status"] = "countered"
        state.event_log.append(
            {
                "action": "COUNTER_PROPOSAL",
                "agent": agent_id,
                "original": proposal_id,
                "new": new_id,
                "tick": state.tick,
            }
        )
        return {"new_proposal_id": new_id}

    def accept_contract(agent_id: str, proposal_id: str) -> dict[str, Any]:
        """Accept a pending contract proposal."""
        if proposal_id not in state.ledger:
            return {"status": "not_found"}
        state.ledger[proposal_id]["status"] = "accepted"
        state.ledger[proposal_id]["accepted_by"] = agent_id
        state.ledger[proposal_id]["accepted_at"] = state.tick
        state.event_log.append(
            {
                "action": "ACCEPT_CONTRACT",
                "agent": agent_id,
                "proposal_id": proposal_id,
                "tick": state.tick,
            }
        )
        return {"status": "accepted", "proposal_id": proposal_id}

    def reject_contract(agent_id: str, proposal_id: str, reason: str) -> dict[str, Any]:
        """Reject a pending contract proposal."""
        if proposal_id not in state.ledger:
            return {"status": "not_found"}
        state.ledger[proposal_id]["status"] = "rejected"
        state.ledger[proposal_id]["rejection_reason"] = reason
        state.event_log.append(
            {
                "action": "REJECT_CONTRACT",
                "agent": agent_id,
                "proposal_id": proposal_id,
                "tick": state.tick,
            }
        )
        return {"status": "rejected"}

    def submit_finding(
        agent_id: str,
        claim: str,
        evidence: list[str],
        confidence: float,
    ) -> dict[str, Any]:
        """Add a research finding to the shared knowledge graph."""
        finding_id = f"find_{len(state.knowledge_graph):04d}"
        state.knowledge_graph[finding_id] = {
            "author": agent_id,
            "claim": claim,
            "evidence": evidence,
            "confidence": confidence,
            "citations": [],
            "tick": state.tick,
        }
        state.event_log.append(
            {
                "action": "SUBMIT_FINDING",
                "agent": agent_id,
                "finding_id": finding_id,
                "tick": state.tick,
            }
        )
        return {"finding_id": finding_id}

    def cite_finding(agent_id: str, finding_id: str, context: str) -> dict[str, Any]:
        """Cite an existing finding in a new research context."""
        if finding_id not in state.knowledge_graph:
            return {"status": "not_found"}
        citations = state.knowledge_graph[finding_id]["citations"]
        citations.append({"by": agent_id, "context": context, "tick": state.tick})
        state.event_log.append(
            {
                "action": "CITE_FINDING",
                "agent": agent_id,
                "finding_id": finding_id,
                "tick": state.tick,
            }
        )
        return {"status": "cited", "total_citations": len(citations)}

    def challenge_finding(
        agent_id: str,
        finding_id: str,
        counter_evidence: str,
    ) -> dict[str, Any]:
        """Challenge an existing finding with counter-evidence."""
        if finding_id not in state.knowledge_graph:
            return {"status": "not_found"}
        state.knowledge_graph[finding_id].setdefault("challenges", []).append(
            {"by": agent_id, "counter_evidence": counter_evidence, "tick": state.tick}
        )
        state.event_log.append(
            {
                "action": "CHALLENGE_FINDING",
                "agent": agent_id,
                "finding_id": finding_id,
                "tick": state.tick,
            }
        )
        return {"status": "challenge_logged"}

    def send_message(
        from_agent: str,
        to_agent: str,
        content: str,
        channel: str = "direct",
    ) -> dict[str, Any]:
        """Send a direct or channel message between agents."""
        msg_id = f"msg_{len(state.messages):04d}"
        state.messages[msg_id] = {
            "from": from_agent,
            "to": to_agent,
            "content": content,
            "channel": channel,
            "read": False,
            "tick": state.tick,
        }
        state.event_log.append(
            {
                "action": "SEND_MESSAGE",
                "agent": from_agent,
                "to": to_agent,
                "tick": state.tick,
            }
        )
        return {"msg_id": msg_id, "delivered": True}

    def form_coalition(
        initiator: str,
        members: list[str],
        purpose: str,
    ) -> dict[str, Any]:
        """Form a coalition group with a shared purpose."""
        coalition_id = f"coal_{len(state.coalitions):04d}"
        state.coalitions[coalition_id] = {
            "initiator": initiator,
            "members": members,
            "purpose": purpose,
            "active": True,
            "tick": state.tick,
        }
        state.event_log.append(
            {
                "action": "FORM_COALITION",
                "agent": initiator,
                "coalition_id": coalition_id,
                "tick": state.tick,
            }
        )
        return {"coalition_id": coalition_id}

    def observe(agent_id: str, target: str) -> dict[str, Any]:
        """Observe the current state of a target entity."""
        targets = {
            "calendar": state.calendar,
            "ledger": state.ledger,
            "knowledge_graph": state.knowledge_graph,
            "coalitions": state.coalitions,
            "messages": state.messages,
        }
        if target not in targets:
            return {"status": "unknown_target"}
        state.event_log.append(
            {
                "action": "OBSERVE",
                "agent": agent_id,
                "target": target,
                "tick": state.tick,
            }
        )
        return {"state": dict(targets[target])}

    action_sets = {
        "negotiation": {
            "propose_contract": propose_contract,
            "counter_proposal": counter_proposal,
            "accept_contract": accept_contract,
            "reject_contract": reject_contract,
            "observe": observe,
        },
        "scheduling": {
            "schedule_meeting": schedule_meeting,
            "cancel_meeting": cancel_meeting,
            "observe": observe,
        },
        "research": {
            "submit_finding": submit_finding,
            "cite_finding": cite_finding,
            "challenge_finding": challenge_finding,
            "observe": observe,
        },
        "social": {
            "send_message": send_message,
            "form_coalition": form_coalition,
            "observe": observe,
        },
    }
    return action_sets.get(domain, {"observe": observe})


def make_action_toolkit(state: SimulationState, domain: str) -> list[Any]:
    """Return the constrained FunctionTool-compatible action set for a domain."""
    return [_wrap_tool(func) for func in make_action_functions(state, domain).values()]
