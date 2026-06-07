#!/usr/bin/env bash
# Pull a CAMEL-friendly model with Ollama. Ollama serves an OpenAI-compatible
# API at http://localhost:11434/v1.
set -euo pipefail

if ! command -v ollama >/dev/null 2>&1; then
  echo "Install Ollama from https://ollama.com first."; exit 1
fi
ollama pull qwen2.5:7b-instruct
echo "Ready. Point configs/models.yaml base_url at http://127.0.0.1:11434/v1"
