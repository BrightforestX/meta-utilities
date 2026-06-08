"""Sparse frontier-model evaluation for simulation batches."""
from __future__ import annotations

import json
import random
from typing import Any


def evaluate_simulation_batch(
    results: list[dict[str, Any]],
    sample_rate: float = 0.05,
) -> list[dict[str, Any]]:
    """Evaluate a random sample of simulation results with a frontier model."""
    if not results:
        return []
    try:
        from camel.agents import ChatAgent
        from camel.messages import BaseMessage
        from camel.models import ModelFactory
        from camel.types import ModelPlatformType
    except Exception as exc:  # pragma: no cover - depends on optional CAMEL install
        raise RuntimeError("Frontier evaluation requires camel-ai to be installed") from exc

    sample_size = max(1, int(len(results) * sample_rate))
    sample = random.sample(results, min(len(results), sample_size))

    evaluator_model = ModelFactory.create(
        model_platform=ModelPlatformType.ANTHROPIC,
        model_type="claude-sonnet-4-5",
        model_config_dict={"temperature": 0.2, "max_tokens": 2048},
    )
    evaluator = ChatAgent(
        system_message=BaseMessage.make_assistant_message(
            role_name="Evaluator",
            content=(
                "You are evaluating multi-agent simulation quality. Assess: "
                "(1) persona consistency, (2) action coherence, "
                "(3) state mutation correctness, (4) scenario realism. "
                "Return JSON scores from 0-10 and brief reasoning."
            ),
        ),
        model=evaluator_model,
    )

    evaluations = []
    for result in sample:
        message = BaseMessage.make_user_message(
            role_name="System",
            content=f"Evaluate this simulation:\n{json.dumps(result, indent=2)[:4000]}",
        )
        response = evaluator.step(message)
        evaluations.append(
            {
                "scenario_id": result["scenario_id"],
                "evaluation": response.msg.content,
            }
        )
    return evaluations
