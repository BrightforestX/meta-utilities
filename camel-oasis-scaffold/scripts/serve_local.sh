#!/usr/bin/env bash
# Serve the local model over an OpenAI-compatible HTTP endpoint at :8080.
set -euo pipefail

python -m mlx_lm.server \
  --model mlx-community/Qwen2.5-7B-Instruct-4bit \
  --host 127.0.0.1 \
  --port 8080
