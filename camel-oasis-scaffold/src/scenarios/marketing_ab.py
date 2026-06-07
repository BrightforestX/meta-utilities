"""Marketing A/B scenario.

Run the same OASIS simulation twice (or N times) with two different seed
"campaign captions" — collect per-agent engagement outcomes, then feed
the two outcome arrays to src/models/bayesian_ab.py for a posterior on
the uplift.

For statistical power, run multiple seeds per variant (see --reps).
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
    ActionType.CREATE_COMMENT,
    ActionType.REFRESH,
    ActionType.DO_NOTHING,
    ActionType.FOLLOW,
]


async def run_variant(
    variant_name: str,
    seed_caption: str,
    profile_path: Path,
    db_path: Path,
    n_steps: int,
):
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

    seed_action = ManualAction(
        action_type=ActionType.CREATE_POST,
        action_args={"content": seed_caption},
    )
    await env.step({env.agent_graph.get_agent(0): [seed_action]})

    for step_idx in range(1, n_steps):
        actions = {agent: LLMAction() for _, agent in env.agent_graph.get_agents()}
        await env.step(actions)
        print(f"[{variant_name}] step {step_idx}/{n_steps - 1}")

    await env.close()
    return db_path


async def run(
    profile_path: Path,
    out_dir: Path,
    caption_a: str,
    caption_b: str,
    reps: int = 3,
    n_steps: int = 20,
):
    out_dir.mkdir(parents=True, exist_ok=True)
    db_paths: dict[str, list[Path]] = {"A": [], "B": []}
    for rep in range(reps):
        for variant, caption in (("A", caption_a), ("B", caption_b)):
            db_path = out_dir / f"marketing_{variant}_rep{rep}.db"
            await run_variant(f"{variant}/rep{rep}", caption, profile_path, db_path, n_steps)
            db_paths[variant].append(db_path)
    return db_paths


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    p.add_argument("--out-dir", type=Path, default=DATA_DIR / "marketing_ab")
    p.add_argument("--caption-a", default="Try our product — built by engineers, for engineers.")
    p.add_argument("--caption-b", default="Stop wasting time. Ship faster with [product].")
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--steps", type=int, default=20)
    args = p.parse_args()
    asyncio.run(
        run(args.profiles, args.out_dir, args.caption_a, args.caption_b, args.reps, args.steps)
    )


if __name__ == "__main__":
    main()
