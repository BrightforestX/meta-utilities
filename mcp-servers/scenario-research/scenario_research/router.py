"""Model routing contract (locked at P0).

Source of truth (when available): camel-oasis-scaffold/configs/models.yaml `roles:` map.
This locks the local/frontier decision to the scaffold's governed config (no ad-hoc duplication).
Fallback to static map for environments where scaffold yaml is not yet present (P1 artifacts).
"""
from __future__ import annotations

import functools
from typing import Literal

import yaml

from .scaffold_adapter import get_scaffold_root

Role = str
Endpoint = Literal["local", "frontier"]


@functools.lru_cache(maxsize=1)
def _load_role_map() -> dict[str, str]:
    """Load roles: mapping from the scaffold's models.yaml if present.

    Returns e.g. {"oasis_agent": "local", "planner": "frontier", ...}
    """
    try:
        root = get_scaffold_root()
        cfg = root / "configs" / "models.yaml"
        if not cfg.exists():
            return {}
        data = yaml.safe_load(cfg.read_text()) or {}
        roles = data.get("roles", {}) or {}
        # Normalize values to our Endpoint literals
        return {str(k): str(v) for k, v in roles.items()}
    except Exception:
        return {}


def resolve_endpoint(role: Role) -> Endpoint:
    """Return 'local' for bulk OASIS roles, 'frontier' for planner/writer/high-leverage.

    Locked to scaffold yaml when available (P0 contract). Tests assert on both the
    yaml-driven path and the static fallback for key roles.
    """
    role_map = _load_role_map()
    if role in role_map:
        val = role_map[role]
        if val == "local":
            return "local"
        return "frontier"

    # Static fallback (matches the yaml in the scaffold at time of P0 freeze)
    local_roles = {"oasis_agent", "agent", "user", "poster", "liker", "commenter", "population"}
    if role in local_roles or role.startswith("oasis_") or role.startswith("population") or "population" in role:
        return "local"
    frontier_roles = {"planner", "coordinator", "writer", "analyst", "literature", "math_analyst"}
    if role in frontier_roles or "planner" in role or "writer" in role:
        return "frontier"
    return "frontier"


def get_model_for_role(role: Role) -> str:
    """Return a canonical model identifier for the role (string for now).

    Later this will return a resolved endpoint config object.
    """
    endpoint = resolve_endpoint(role)
    if endpoint == "local":
        return "local:mlx-qwen"
    return "frontier:claude-sonnet"
