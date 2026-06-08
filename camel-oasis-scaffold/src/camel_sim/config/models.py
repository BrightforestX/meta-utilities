"""Model registry for the CAMEL multi-scenario service.

The registry mirrors the Modal/SGLang technical specification but remains pure
Python so local CLI commands can inspect routing without Modal installed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


GpuKind = Literal["H100", "A100", "L40S"]
QuantizationKind = Literal["fp8", "fp16", "awq"]


@dataclass(frozen=True)
class ModelSpec:
    name: str
    hf_repo: str
    gpu: GpuKind
    quantization: QuantizationKind
    port: int
    domains: list[str]


MODEL_REGISTRY: list[ModelSpec] = [
    ModelSpec(
        name="qwen3-72b",
        hf_repo="Qwen/Qwen3-72B-Instruct",
        gpu="H100",
        quantization="fp8",
        port=30001,
        domains=["negotiation", "complex_reasoning"],
    ),
    ModelSpec(
        name="llama-3.3-70b",
        hf_repo="meta-llama/Llama-3.3-70B-Instruct",
        gpu="A100",
        quantization="fp16",
        port=30002,
        domains=["research", "synthesis"],
    ),
    ModelSpec(
        name="qwen3-32b",
        hf_repo="Qwen/Qwen3-32B-Instruct",
        gpu="L40S",
        quantization="awq",
        port=30003,
        domains=["scheduling", "tool_dispatch"],
    ),
    ModelSpec(
        name="mistral-24b",
        hf_repo="mistralai/Mistral-Small-3.2-24B-Instruct",
        gpu="L40S",
        quantization="fp16",
        port=30004,
        domains=["social", "dialogue"],
    ),
]

DOMAIN_TO_MODEL: dict[str, str] = {
    domain: spec.name for spec in MODEL_REGISTRY for domain in spec.domains
}
DOMAIN_TO_MODEL.update(
    {
        "planner": "frontier",
        "evaluator": "frontier",
    }
)


def get_model_name_for_domain(domain: str) -> str:
    """Return the configured model name for a scenario domain."""
    return DOMAIN_TO_MODEL.get(domain, "qwen3-72b")


def get_model_spec(model_name: str) -> ModelSpec:
    """Return the model spec for a configured SGLang model."""
    for spec in MODEL_REGISTRY:
        if spec.name == model_name:
            return spec
    raise KeyError(f"unknown model {model_name!r}")


def default_server_urls(host: str = "localhost") -> dict[str, str]:
    """Build OpenAI-compatible `/v1` URLs for locally reachable SGLang servers."""
    return {spec.name: f"http://{host}:{spec.port}/v1" for spec in MODEL_REGISTRY}
