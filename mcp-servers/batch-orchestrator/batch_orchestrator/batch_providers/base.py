"""Base types for provider batch adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

BatchPollStatus = Literal["pending", "running", "completed", "failed", "expired"]


@dataclass
class BatchJobRequest:
    custom_id: str
    prompt: str
    model: str
    max_tokens: int = 8192
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchPollResult:
    batch_id: str
    status: BatchPollStatus
    completed: int = 0
    total: int = 0
    error: str | None = None


@dataclass
class BatchResultItem:
    custom_id: str
    text: str
    error: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


class BatchAdapter(ABC):
    """Submit, poll, and collect provider batch jobs."""

    @abstractmethod
    async def submit(self, requests: list[BatchJobRequest]) -> str:
        """Submit batch requests; return provider batch id."""

    @abstractmethod
    async def poll(self, batch_id: str) -> BatchPollResult:
        """Poll batch status."""

    @abstractmethod
    async def collect(self, batch_id: str) -> list[BatchResultItem]:
        """Collect completed batch results."""
