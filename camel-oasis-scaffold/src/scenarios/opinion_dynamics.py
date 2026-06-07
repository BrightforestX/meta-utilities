"""Opinion-dynamics scenario.

Each agent has a continuous-valued opinion in [0, 1] encoded in its profile
description ("strongly agrees that…", "is skeptical of…"). We seed two
counter-narratives, then run OASIS for `n_steps` and post-hoc fit a
bounded-confidence model (Deffuant or Hegselmann–Krause) to the agent
opinion trajectories — extracted by an LLM scoring each agent's posts.

This file produces the raw simulation; see src/models/bounded_confidence.py
for the fit.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import oasis
from oasis import ActionType, LLMAction, ManualAction

from src.model_factory import make_model

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_PROFILES = DATA_DIR / "reddit" / "user_data_36.json"

NARRATIVE_A = "Position A: aggressive regulation of AI is necessary to protect society."
NARRATIVE_B = "Position B: heavy-handed AI regulation will choke innovation and harm consumers."

AVAILABLE_ACTIONS = [
    ActionType.CREATE_POST,
    ActionType.CREATE_COMMENT,
    ActionType.LIKE_POST,
    ActionType.DISLIKE_POST,
    ActionType.FOLLOW,
    ActionType.REFRESH,
    ActionType.DO_NOTHING,
]


async def run(
    profile_path: Path = DEFAULT_PROFILES,
    db_path: Path = DATA_DIR / "opinion_dynamics.db",
    n_steps: int = 40,
):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    model = make_model(role="oasis_agent")
    agent_graph = await oasis.generate_reddit_agent_graph(
        profile_path=str(profile_path),
        model=model,
        available_actions=AVAILABLE_ACTIONS,
    )
    env = oasis.make(
        agent_graph=agent_graph,
        platform=oasis.DefaultPlatformType.REDDIT,
        database_path=str(db_path),
    )
    await env.reset()

    # Seed two opposing posts from two different agents.
    seed_actions = {
        env.agent_graph.get_agent(0): [
            ManualAction(action_type=ActionType.CREATE_POST, action_args={"content": NARRATIVE_A}),
        ],
        env.agent_graph.get_agent(1): [
            ManualAction(action_type=ActionType.CREATE_POST, action_args={"content": NARRATIVE_B}),
        ],
    }
    await env.step(seed_actions)

    for step_idx in range(1, n_steps):
        actions = {agent: LLMAction() for _, agent in env.agent_graph.get_agents()}
        await env.step(actions)
        print(f"[opinion_dynamics] step {step_idx}/{n_steps - 1}")

    await env.close()
    print(f"[opinion_dynamics] wrote {db_path}")
    return db_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    p.add_argument("--db", type=Path, default=DATA_DIR / "opinion_dynamics.db")
    p.add_argument("--steps", type=int, default=40)
    args = p.parse_args()
    asyncio.run(run(args.profiles, args.db, args.steps))


if __name__ == "__main__":
    main()
