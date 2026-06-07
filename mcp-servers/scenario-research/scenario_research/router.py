"""Model routing contract (locked at P0).

Source of truth (when available): camel-oasis-scaffold/configs/models.yaml `roles:` map.
This locks the local/frontier decision to the scaffold's governed config (no ad-hoc duplication).
Fallback to static map for environments where scaffold yaml is not yet present (P1 artifacts).
"""
from __future__ import annotations

import functools
import os
from typing import Literal

import yaml

from .scaffold_adapter import get_scaffold_root

Role = str
Endpoint = Literal["local", "frontier"]

LOCAL_PROVIDERS = {"mlx", "ollama", "lmstudio", "turnover"}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_local_provider(value: str | None) -> str:
    provider = (value or "mlx").strip().lower()
    if provider in LOCAL_PROVIDERS:
        return provider
    return "mlx"


def get_local_inference_config() -> dict[str, str]:
    """Return active local inference provider/model config.

    Supports multiple local backends to reduce frontier/API cost:
    - mlx (default)
    - ollama
    - lmstudio
    - turnover (user-requested local gateway slot)
    """
    provider = _normalize_local_provider(os.environ.get("SCENARIO_RESEARCH_LOCAL_PROVIDER"))
    if provider == "ollama":
        return {
            "provider": "ollama",
            "model": os.environ.get("SCENARIO_RESEARCH_OLLAMA_MODEL", "qwen2.5:14b-instruct"),
            "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        }
    if provider == "lmstudio":
        return {
            "provider": "lmstudio",
            "model": os.environ.get("SCENARIO_RESEARCH_LMSTUDIO_MODEL", "local-model"),
            "base_url": os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1"),
        }
    if provider == "turnover":
        return {
            "provider": "turnover",
            "model": os.environ.get("SCENARIO_RESEARCH_TURNOVER_MODEL", "turnover-local"),
            "base_url": os.environ.get("TURNOVER_BASE_URL", "http://localhost:8080"),
        }
    return {
        "provider": "mlx",
        "model": os.environ.get("SCENARIO_RESEARCH_MLX_MODEL", "mlx-qwen"),
        "base_url": os.environ.get("SCENARIO_RESEARCH_MLX_BASE_URL", "local://mlx"),
    }


def _frontier_model_id() -> str:
    return os.environ.get("SCENARIO_RESEARCH_FRONTIER_MODEL", "claude-sonnet")


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
    # Optional "cost saver" mode: force all roles to local inference.
    # Useful when prioritizing cost reduction with local backends like Ollama/LM Studio.
    if _env_flag("SCENARIO_RESEARCH_COST_SAVER_MODE", default=False):
        return "local"

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
        local = get_local_inference_config()
        return f"local:{local['provider']}:{local['model']}"
    return f"frontier:{_frontier_model_id()}"
