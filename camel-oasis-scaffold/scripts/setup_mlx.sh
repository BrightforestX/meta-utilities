#!/usr/bin/env bash
# Install MLX + pull a 4-bit-quantized Qwen2.5-7B-Instruct (~4.5 GB).
# Tested on Apple M4 with macOS 15.
set -euo pipefail

uv pip install -e ".[mlx]"
python -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/Qwen2.5-7B-Instruct-4bit')"
echo "MLX setup complete. Start the server with: ./scripts/serve_local.sh"
