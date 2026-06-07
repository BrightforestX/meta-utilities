#!/usr/bin/env bash
set -euo pipefail
if ! command -v firecrawl &> /dev/null; then
  echo "Installing Firecrawl CLI..."
  npm install -g firecrawl-cli || { echo "npm required or auth issue — see rules/install.mdc"; exit 1; }
fi
firecrawl --version || echo "Run 'firecrawl login' if needed"
echo "Firecrawl ready. Two-layer: export FIRECRAWL_TIMEOUT_SEC=300 in client env; add to host tool_timeouts."
