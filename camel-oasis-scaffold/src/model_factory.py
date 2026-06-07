"""Build CAMEL `BaseModelBackend` instances from configs/models.yaml.

The hybrid pattern: OASIS agents use a local OpenAI-compatible endpoint
(MLX or Ollama); Workforce planner/coordinator/analyst use a frontier API.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from camel.models import ModelFactory
from camel.types import ModelPlatformType


_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "models.yaml"


def _load_config() -> dict[str, Any]:
    with _CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


_PLATFORM_MAP = {
    "openai_compatible": ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
    "anthropic": ModelPlatformType.ANTHROPIC,
    "openai": ModelPlatformType.OPENAI,
    "ollama": ModelPlatformType.OLLAMA,
}


def make_model(role: str = "oasis_agent"):
    """Return a CAMEL model backend appropriate for the given role."""
    cfg = _load_config()
    target = cfg["roles"].get(role, "local")
    spec = cfg[target]

    platform = _PLATFORM_MAP[spec["platform"]]
    kwargs: dict[str, Any] = {
        "model_platform": platform,
        "model_type": spec["model"],
        "model_config_dict": spec.get("model_config", {}),
    }

    if spec["platform"] == "openai_compatible":
        kwargs["url"] = spec["base_url"]
        kwargs["api_key"] = spec.get("api_key", "EMPTY")
    elif "api_key_env" in spec:
        api_key = os.environ.get(spec["api_key_env"])
        if not api_key:
            raise RuntimeError(
                f"Role '{role}' needs env var {spec['api_key_env']} set."
            )
        kwargs["api_key"] = api_key

    return ModelFactory.create(**kwargs)
