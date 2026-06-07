"""OpenAI Batch API adapter."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

from openai import OpenAI

from batch_orchestrator.batch_providers.base import (
    BatchAdapter,
    BatchJobRequest,
    BatchPollResult,
    BatchResultItem,
)


class OpenAIBatchAdapter(BatchAdapter):
    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY required for OpenAI batch mode")
        self.client = OpenAI(api_key=api_key)

    async def submit(self, requests: list[BatchJobRequest]) -> str:
        lines = []
        for req in requests:
            lines.append(
                json.dumps(
                    {
                        "custom_id": req.custom_id,
                        "method": "POST",
                        "url": "/v1/chat/completions",
                        "body": {
                            "model": req.model,
                            "messages": [{"role": "user", "content": req.prompt}],
                            "max_tokens": req.max_tokens,
                        },
                    }
                )
            )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write("\n".join(lines))
            tmp_path = f.name

        try:
            with open(tmp_path, "rb") as f:
                file_obj = await asyncio.to_thread(
                    self.client.files.create, file=f, purpose="batch"
                )
            batch = await asyncio.to_thread(
                self.client.batches.create,
                input_file_id=file_obj.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
            )
            return batch.id
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def poll(self, batch_id: str) -> BatchPollResult:
        batch = await asyncio.to_thread(self.client.batches.retrieve, batch_id)
        status_map = {
            "validating": "pending",
            "in_progress": "running",
            "finalizing": "running",
            "completed": "completed",
            "failed": "failed",
            "expired": "expired",
            "cancelled": "failed",
        }
        return BatchPollResult(
            batch_id=batch_id,
            status=status_map.get(batch.status, "pending"),
            completed=batch.request_counts.completed if batch.request_counts else 0,
            total=batch.request_counts.total if batch.request_counts else 0,
            error=getattr(batch, "errors", None),
        )

    async def collect(self, batch_id: str) -> list[BatchResultItem]:
        batch = await asyncio.to_thread(self.client.batches.retrieve, batch_id)
        if not batch.output_file_id:
            return []

        content = await asyncio.to_thread(
            self.client.files.content, batch.output_file_id
        )
        text = content.text
        items: list[BatchResultItem] = []
        for line in text.strip().split("\n"):
            if not line.strip():
                continue
            row = json.loads(line)
            custom_id = row.get("custom_id", "")
            if row.get("error"):
                items.append(
                    BatchResultItem(
                        custom_id=custom_id,
                        text="",
                        error=json.dumps(row["error"]),
                    )
                )
                continue
            body = row.get("response", {}).get("body", {})
            choices = body.get("choices", [])
            msg_text = ""
            if choices:
                msg_text = choices[0].get("message", {}).get("content", "") or ""
            usage = body.get("usage", {})
            items.append(
                BatchResultItem(
                    custom_id=custom_id,
                    text=msg_text,
                    usage=usage,
                )
            )
        return items
