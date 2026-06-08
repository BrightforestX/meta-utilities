"""Modal SGLang server factory.

This module is intentionally optional: importing it without `modal` installed is
safe, and the error is raised only when a Modal class is requested.
"""
from __future__ import annotations

import subprocess
import time
from typing import Any

from ..config.models import ModelSpec


def make_sglang_server(app: Any, spec: ModelSpec) -> type:
    """Create a Modal class serving one configured SGLang model."""
    try:
        import modal
        import requests
    except Exception as exc:  # pragma: no cover - requires optional modal extra
        raise RuntimeError("Modal SGLang servers require the optional modal extra") from exc

    weights_vol = modal.Volume.from_name(f"weights-{spec.name}", create_if_missing=True)
    image = (
        modal.Image.from_registry("lmsys/sglang:latest", add_python="3.11")
        .pip_install("huggingface_hub", "hf_transfer")
        .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
    )

    @app.cls(
        gpu=spec.gpu,
        image=image,
        volumes={f"/weights/{spec.name}": weights_vol},
        container_idle_timeout=600,
        enable_memory_snapshot=True,
        concurrency_limit=10,
    )
    class _SGLangServer:
        @modal.enter(snap=True)
        def load(self) -> None:
            from huggingface_hub import snapshot_download

            model_path = f"/weights/{spec.name}"
            snapshot_download(spec.hf_repo, local_dir=model_path)

            cmd = [
                "python",
                "-m",
                "sglang.launch_server",
                "--model-path",
                model_path,
                "--host",
                "0.0.0.0",
                "--port",
                str(spec.port),
                "--attention-backend",
                "flashinfer",
                "--enable-torch-compile",
                "--enable-prefix-caching",
                "--mem-fraction-static",
                "0.88",
            ]
            if spec.quantization == "fp8":
                cmd += ["--quantization", "fp8", "--kv-cache-dtype", "fp8_e5m2"]
            elif spec.quantization == "awq":
                cmd += ["--quantization", "awq"]

            subprocess.Popen(cmd)
            for _ in range(60):
                try:
                    response = requests.get(
                        f"http://localhost:{spec.port}/health",
                        timeout=2,
                    )
                    if response.status_code == 200:
                        return
                except Exception:
                    pass
                time.sleep(5)
            raise RuntimeError(f"SGLang server {spec.name} did not become healthy")

        @modal.method()
        def url(self) -> str:
            return f"http://localhost:{spec.port}/v1"

    _SGLangServer.__name__ = f"SGLangServer_{spec.name.replace('-', '_')}"
    return _SGLangServer
