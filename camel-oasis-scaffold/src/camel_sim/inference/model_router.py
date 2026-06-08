"""CAMEL model routing for multi-scenario domains."""
from __future__ import annotations

from typing import Any

from ..config.models import get_model_name_for_domain


def get_camel_model(domain: str, server_urls: dict[str, str]) -> Any:
    """Create a CAMEL model backend for a scenario domain.

    Frontier roles use Anthropic. Domain worker roles use SGLang if CAMEL exposes
    that platform; otherwise they fall back to OpenAI-compatible routing.
    """
    try:
        from camel.models import ModelFactory
        from camel.types import ModelPlatformType
    except Exception as exc:  # pragma: no cover - depends on optional CAMEL install
        raise RuntimeError("CAMEL model routing requires camel-ai to be installed") from exc

    model_name = get_model_name_for_domain(domain)
    if model_name == "frontier":
        return ModelFactory.create(
            model_platform=ModelPlatformType.ANTHROPIC,
            model_type="claude-sonnet-4-5",
            model_config_dict={"temperature": 0.3, "max_tokens": 4096},
        )

    platform = getattr(
        ModelPlatformType,
        "SGLANG",
        ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
    )
    if model_name not in server_urls:
        raise KeyError(f"missing SGLang server URL for {model_name!r}")

    return ModelFactory.create(
        model_platform=platform,
        model_type=model_name,
        url=server_urls[model_name],
        api_key="EMPTY",
        model_config_dict={"temperature": 0.7, "max_tokens": 1024},
    )
