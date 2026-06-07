"""xAI Grok Batch API adapter."""

from __future__ import annotations

import asyncio
import json
import os

import httpx

from batch_orchestrator.batch_providers.base import (
    BatchAdapter,
    BatchJobRequest,
    BatchPollResult,
    BatchResultItem,
)

XAI_BASE = "https://api.x.ai/v1"


class XAIBatchAdapter(BatchAdapter):
    def __init__(self) -> None:
        self.api_key = os.getenv("XAI_API_KEY")
        if not self.api_key:
            raise ValueError("XAI_API_KEY required for xAI batch mode")
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    async def submit(self, requests: list[BatchJobRequest]) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{XAI_BASE}/batches",
                headers=self.headers,
                json={"name": "meta-batch-orchestrator"},
            )
            resp.raise_for_status()
            batch_id = resp.json()["batch_id"]

            batch_requests = []
            for req in requests:
                batch_requests.append(
                    {
                        "batch_request_id": req.custom_id,
                        "batch_request": {
                            "responses": {
                                "model": req.model,
                                "input": [{"role": "user", "content": req.prompt}],
                            }
                        },
                    }
                )

            add_resp = await client.post(
                f"{XAI_BASE}/batches/{batch_id}/requests",
                headers=self.headers,
                json={"batch_requests": batch_requests},
            )
            add_resp.raise_for_status()
            return batch_id

    async def poll(self, batch_id: str) -> BatchPollResult:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{XAI_BASE}/batches/{batch_id}",
                headers=self.headers,
            )
            resp.raise_for_status()
            data = resp.json()
            state = data.get("state", {})
            pending = state.get("num_pending", 0)
            total = state.get("num_total", 0)
            completed = total - pending if total else 0
            status = "completed" if pending == 0 and total > 0 else "running"
            if total == 0:
                status = "pending"
            return BatchPollResult(
                batch_id=batch_id,
                status=status,
                completed=completed,
                total=total,
            )

    async def collect(self, batch_id: str) -> list[BatchResultItem]:
        items: list[BatchResultItem] = []
        cursor: str | None = None

        async with httpx.AsyncClient(timeout=120.0) as client:
            while True:
                url = f"{XAI_BASE}/batches/{batch_id}/results?limit=100"
                if cursor:
                    url += f"&cursor={cursor}"
                resp = await client.get(url, headers=self.headers)
                resp.raise_for_status()
                data = resp.json()
                for row in data.get("results", []):
                    custom_id = row.get("batch_request_id", "")
                    if row.get("error"):
                        items.append(
                            BatchResultItem(
                                custom_id=custom_id,
                                text="",
                                error=json.dumps(row["error"]),
                            )
                        )
                        continue
                    output = row.get("response", row.get("result", {}))
                    text = ""
                    if isinstance(output, dict):
                        if "output" in output:
                            for block in output.get("output", []):
                                if block.get("type") == "message":
                                    for c in block.get("content", []):
                                        if c.get("type") == "output_text":
                                            text += c.get("text", "")
                        elif "choices" in output:
                            text = (
                                output["choices"][0]
                                .get("message", {})
                                .get("content", "")
                            )
                    items.append(BatchResultItem(custom_id=custom_id, text=text or ""))

                cursor = data.get("next_cursor")
                if not cursor:
                    break
        return items
