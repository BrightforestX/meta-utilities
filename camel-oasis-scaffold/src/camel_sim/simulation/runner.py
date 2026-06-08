"""Scenario runner for local and CAMEL-backed multi-scenario execution."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable

from ..config.models import default_server_urls
from ..config.scenarios import AgentDefinition, ScenarioConfig
from ..inference.model_router import get_camel_model
from .actions import make_action_functions, make_action_toolkit
from .state import SimulationState


def run_scenario(
    config: ScenarioConfig | dict[str, Any],
    server_urls: dict[str, str] | None = None,
    *,
    execution_mode: str = "local",
) -> dict[str, Any]:
    """Run a single scenario simulation.

    `execution_mode="local"` drives tools with deterministic scripted policies,
    giving the existing CLI a runnable path without GPUs or API keys.
    `execution_mode="camel"` wires CAMEL ChatAgents to the same tools.
    """
    scenario = (
        config if isinstance(config, ScenarioConfig) else ScenarioConfig.model_validate(config)
    )
    state = SimulationState(scenario_id=scenario.id)

    if execution_mode not in {"local", "camel"}:
        raise ValueError("execution_mode must be 'local' or 'camel'")

    if execution_mode == "camel":
        _run_with_camel_agents(scenario, state, server_urls or default_server_urls())
    else:
        _run_with_scripted_agents(scenario, state)

    return {
        "scenario_id": scenario.id,
        "scenario_name": scenario.name,
        "ticks_run": state.tick,
        "final_state": state.model_dump(),
        "event_log": state.event_log,
        "action_counts": _count_actions(state.event_log),
        "execution_mode": execution_mode,
    }


def run_scenarios(
    configs: Iterable[ScenarioConfig | dict[str, Any]],
    *,
    execution_mode: str = "local",
    parallel: bool = False,
    max_workers: int | None = None,
    server_urls: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Run a batch of scenarios locally, optionally parallelized by thread."""
    normalized = [
        cfg if isinstance(cfg, ScenarioConfig) else ScenarioConfig.model_validate(cfg)
        for cfg in configs
    ]
    if not parallel:
        return [
            run_scenario(cfg, server_urls=server_urls, execution_mode=execution_mode)
            for cfg in normalized
        ]

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(
            pool.map(
                lambda cfg: run_scenario(
                    cfg,
                    server_urls=server_urls,
                    execution_mode=execution_mode,
                ),
                normalized,
            )
        )


def _run_with_scripted_agents(scenario: ScenarioConfig, state: SimulationState) -> None:
    for _ in range(scenario.max_ticks):
        state.advance_tick()
        for index, agent in enumerate(scenario.agents):
            _apply_scripted_action(agent, index, scenario, state)
        if _termination_reached(scenario, state):
            break


def _apply_scripted_action(
    agent: AgentDefinition,
    agent_index: int,
    scenario: ScenarioConfig,
    state: SimulationState,
) -> None:
    actions = make_action_functions(state, agent.domain)
    agent_ids = [item.id for item in scenario.agents]
    counterparty = _next_agent(agent.id, agent_ids)

    if agent.domain == "negotiation":
        pending_for_agent = [
            (proposal_id, item)
            for proposal_id, item in state.ledger.items()
            if item.get("status") == "pending" and item.get("to") == agent.id
        ]
        if pending_for_agent:
            proposal_id, _ = pending_for_agent[0]
            actions["accept_contract"](agent.id, proposal_id)
            return
        if not any(item.get("from") == agent.id for item in state.ledger.values()):
            terms = dict(scenario.parameters.get("contract_terms", {}))
            terms.setdefault("price_usd", 50_000 + (agent_index * 5_000))
            terms.setdefault("term_months", 12)
            actions["propose_contract"](agent.id, counterparty, terms)
            return
        actions["observe"](agent.id, "ledger")
        return

    if agent.domain == "scheduling":
        slot = scenario.parameters.get("time_slot", f"tick-{state.tick}-slot-{agent_index}")
        participants = scenario.parameters.get("participants") or agent_ids
        actions["schedule_meeting"](
            agent.id,
            slot,
            list(participants),
            scenario.parameters.get("agenda", scenario.description),
        )
        return

    if agent.domain == "research":
        if not state.knowledge_graph:
            actions["submit_finding"](
                agent.id,
                scenario.parameters.get("claim", scenario.description),
                list(scenario.parameters.get("evidence", ["scenario_config"])),
                float(scenario.parameters.get("confidence", 0.7)),
            )
            return
        first_finding = next(iter(state.knowledge_graph))
        if state.tick % 3 == 0:
            actions["challenge_finding"](
                agent.id,
                first_finding,
                scenario.parameters.get("counter_evidence", "alternative interpretation"),
            )
        else:
            actions["cite_finding"](
                agent.id,
                first_finding,
                scenario.parameters.get("citation_context", "scenario synthesis"),
            )
        return

    if agent.domain == "social":
        if state.tick == 1:
            actions["send_message"](
                agent.id,
                counterparty,
                scenario.parameters.get("message", scenario.description),
            )
            return
        if not state.coalitions:
            actions["form_coalition"](
                agent.id,
                agent_ids,
                scenario.parameters.get("coalition_purpose", scenario.name),
            )
            return
        actions["observe"](agent.id, "coalitions")
        return

    actions["observe"](agent.id, "ledger")


def _run_with_camel_agents(
    scenario: ScenarioConfig,
    state: SimulationState,
    server_urls: dict[str, str],
) -> None:
    try:
        from camel.agents import ChatAgent
        from camel.messages import BaseMessage
    except Exception as exc:  # pragma: no cover - depends on optional CAMEL install
        raise RuntimeError("CAMEL execution requires camel-ai to be installed") from exc

    agents: dict[str, Any] = {}
    for agent_def in scenario.agents:
        model = get_camel_model(agent_def.domain, server_urls)
        sys_msg = BaseMessage.make_assistant_message(
            role_name=agent_def.role,
            content=f"{agent_def.persona}\n\nCurrent state:\n{state.snapshot()}",
        )
        agents[agent_def.id] = ChatAgent(
            system_message=sys_msg,
            model=model,
            tools=make_action_toolkit(state, agent_def.domain),
        )

    for _ in range(scenario.max_ticks):
        state.advance_tick()
        for agent in agents.values():
            message = BaseMessage.make_user_message(
                role_name="Environment",
                content=(
                    f"Tick {state.tick}. Current state:\n{state.snapshot()}\n\n"
                    "Take your next action using the available tools."
                ),
            )
            agent.step(message)
        if _termination_reached(scenario, state):
            break


def _termination_reached(scenario: ScenarioConfig, state: SimulationState) -> bool:
    condition = scenario.termination_condition
    if condition == "any_contract_accepted":
        return any(item.get("status") == "accepted" for item in state.ledger.values())
    if condition == "all_contracts_accepted":
        return bool(state.ledger) and all(
            item.get("status") == "accepted" for item in state.ledger.values()
        )
    if condition == "finding_threshold":
        threshold = int(scenario.parameters.get("finding_threshold", 1))
        return len(state.knowledge_graph) >= threshold
    if condition == "coalition_formed":
        return any(item.get("active") for item in state.coalitions.values())
    return False


def _count_actions(event_log: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in event_log:
        action = event.get("action", "UNKNOWN")
        counts[action] = counts.get(action, 0) + 1
    return counts


def _next_agent(agent_id: str, agent_ids: list[str]) -> str:
    if len(agent_ids) < 2:
        return agent_id
    index = agent_ids.index(agent_id)
    return agent_ids[(index + 1) % len(agent_ids)]
