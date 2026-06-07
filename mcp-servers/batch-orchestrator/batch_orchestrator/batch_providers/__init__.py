"""Provider async Batch API adapters."""

from batch_orchestrator.batch_providers.anthropic_batch import AnthropicBatchAdapter
from batch_orchestrator.batch_providers.base import BatchAdapter, BatchJobRequest, BatchPollResult
from batch_orchestrator.batch_providers.openai_batch import OpenAIBatchAdapter
from batch_orchestrator.batch_providers.xai_batch import XAIBatchAdapter

__all__ = [
    "AnthropicBatchAdapter",
    "BatchAdapter",
    "BatchJobRequest",
    "BatchPollResult",
    "OpenAIBatchAdapter",
    "XAIBatchAdapter",
    "get_batch_adapter",
]


def get_batch_adapter(provider: str) -> BatchAdapter:
    """Return a batch adapter for the provider (lazy init — only the requested adapter is constructed)."""
    factories: dict[str, type[BatchAdapter]] = {
        "openai": OpenAIBatchAdapter,
        "grok": XAIBatchAdapter,
        "xai": XAIBatchAdapter,
        "anthropic": AnthropicBatchAdapter,
    }
    if provider not in factories:
        raise ValueError(
            f"batch mode not supported for provider '{provider}'. "
            f"Supported: {list(factories.keys())}"
        )
    return factories[provider]()
