"""P1 gap: profile_gen.py

Template-first generator for OASIS-compatible agent profile JSON.
For P0/P1 the output is a small synthetic set or copy of the 36 sample.
Used by cli gen-profile and population_templates.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def generate_synthetic(n: int = 200, seed: int = 42, platform: str = "reddit") -> list[dict[str, Any]]:
    """Produce a list of minimal OASIS user profiles (dicts)."""
    random.seed(seed)
    profiles = []
    for i in range(n):
        opinion = max(0.0, min(1.0, random.gauss(0.5, 0.2)))
        profiles.append({
            "user_id": f"synthetic_{i}",
            "description": f"User {i} who {'strongly agrees' if opinion > 0.7 else 'is skeptical' if opinion < 0.3 else 'is neutral'} about the topic.",
            "platform": platform,
            "opinion": opinion,
        })
    return profiles


def main(n: int = 200, out: Path | None = None, seed: int = 42) -> Path:
    out = out or (DATA_DIR / "synthetic_profiles.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    profs = generate_synthetic(n=n, seed=seed)
    out.write_text(json.dumps(profs, indent=2))
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    p = main(n=args.n, out=args.out, seed=args.seed)
    print(p)
