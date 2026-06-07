"""Anthropic Message Batches API adapter."""

from __future__ import annotations

import asyncio
import os

from batch_orchestrator.batch_providers.base import (
    BatchAdapter,
    BatchJobRequest,
    BatchPollResult,
    BatchResultItem,
)


class AnthropicBatchAdapter(BatchAdapter):
    def __init__(self) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY required for Anthropic batch mode")
        try:
            import anthropic
        except ImportError as e:
            raise ImportError(
                "anthropic package required for Anthropic batch mode. "
                "Install with: pip install anthropic"
            ) from e
        self.client = anthropic.Anthropic(api_key=api_key)

    async def submit(self, requests: list[BatchJobRequest]) -> str:
        batch_requests = []
        for req in requests:
            batch_requests.append(
                {
                    "custom_id": req.custom_id,
                    "params": {
                        "model": req.model,
                        "max_tokens": req.max_tokens,
                        "messages": [{"role": "user", "content": req.prompt}],
                    },
                }
            )
        batch = await asyncio.to_thread(
            self.client.messages.batches.create,
            requests=batch_requests,
        )
        return batch.id

    async def poll(self, batch_id: str) -> BatchPollResult:
        result = await asyncio.to_thread(
            self.client.messages.batches.retrieve,
            batch_id,
        )
        status_map = {
            "in_progress": "running",
            "canceling": "running",
            "ended": "completed",
        }
        counts = result.request_counts
        return BatchPollResult(
            batch_id=batch_id,
            status=status_map.get(result.processing_status, "pending"),
            completed=counts.succeeded if counts else 0,
            total=(
                (counts.succeeded or 0)
                + (counts.errored or 0)
                + (counts.canceled or 0)
                + (counts.expired or 0)
                if counts
                else 0
            ),
        )

    async def collect(self, batch_id: str) -> list[BatchResultItem]:
        items: list[BatchResultItem] = []

        def _iter_results():
            return self.client.messages.batches.results(batch_id)

        results = await asyncio.to_thread(lambda: list(_iter_results()))
        for entry in results:
            custom_id = entry.custom_id
            if entry.result.type == "succeeded":
                text_blocks = [
                    b.text for b in entry.result.message.content if hasattr(b, "text")
                ]
                text = "\n".join(text_blocks)
                usage = {}
                if entry.result.message.usage:
                    u = entry.result.message.usage
                    usage = {
                        "input_tokens": u.input_tokens,
                        "output_tokens": u.output_tokens,
                    }
                items.append(
                    BatchResultItem(custom_id=custom_id, text=text, usage=usage)
                )
            else:
                items.append(
                    BatchResultItem(
                        custom_id=custom_id,
                        text="",
                        error=str(entry.result.type),
                    )
                )
        return items
