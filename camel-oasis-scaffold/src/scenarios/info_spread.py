"""Information-spread scenario: seed a post, watch the cascade.

Pipeline:
1. Load (or synthesize) N agent profiles.
2. Build an OASIS Reddit (or Twitter) environment.
3. Seed step: one agent creates the target post.
4. Step the simulation for `n_steps`, letting all other agents act via `LLMAction()`.
5. Persist outputs to a SQLite DB for downstream math analysis.

Run:
    python -m src.scenarios.info_spread --agents 200 --steps 30
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


AVAILABLE_ACTIONS = [
    ActionType.LIKE_POST,
    ActionType.DISLIKE_POST,
    ActionType.CREATE_POST,
    ActionType.CREATE_COMMENT,
    ActionType.LIKE_COMMENT,
    ActionType.DISLIKE_COMMENT,
    ActionType.SEARCH_POSTS,
    ActionType.TREND,
    ActionType.REFRESH,
    ActionType.DO_NOTHING,
    ActionType.FOLLOW,
    ActionType.MUTE,
]


async def run(
    profile_path: Path = DEFAULT_PROFILES,
    db_path: Path = DATA_DIR / "info_spread.db",
    seed_post: str = "Breaking: new study claims X. Thoughts?",
    n_steps: int = 30,
):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()  # OASIS expects a fresh DB

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

    # Step 0 — seed: agent 0 creates the target post.
    seed_action = ManualAction(
        action_type=ActionType.CREATE_POST,
        action_args={"content": seed_post},
    )
    await env.step({env.agent_graph.get_agent(0): [seed_action]})

    # Subsequent steps — every agent acts autonomously via the LLM.
    for step_idx in range(1, n_steps):
        actions = {agent: LLMAction() for _, agent in env.agent_graph.get_agents()}
        await env.step(actions)
        print(f"[info_spread] step {step_idx}/{n_steps - 1} complete")

    await env.close()
    print(f"[info_spread] wrote {db_path}")
    return db_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    p.add_argument("--db", type=Path, default=DATA_DIR / "info_spread.db")
    p.add_argument("--seed-post", type=str, default="Breaking: new study claims X. Thoughts?")
    p.add_argument("--steps", type=int, default=30)
    args = p.parse_args()
    asyncio.run(run(args.profiles, args.db, args.seed_post, args.steps))


if __name__ == "__main__":
    main()
