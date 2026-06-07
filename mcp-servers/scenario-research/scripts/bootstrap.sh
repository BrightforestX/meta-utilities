#!/usr/bin/env bash
# ODRS / scenario-research bootstrap (P1 required tier)
# Satisfies AC1: on a clean machine with Homebrew, runs and prints the exact next happy-path command.
#
# This script:
# - Ensures prereqs (uv, python 3.11 via uv, git)
# - Installs the mcp package + the camel-oasis-scaffold editable
# - Prints instructions for the ~4.5GB MLX model + serve + data + key
# - Prints the exact next command to run a smoke scenario
#
# Idempotent where possible. Safe to re-run.
set -euo pipefail

DRY="${BOOTSTRAP_DRY:-0}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCAFFOLD_DIR="${ROOT_DIR}/../../camel-oasis-scaffold"
VENV_DIR="${ROOT_DIR}/.venv"

echo "== ODRS bootstrap (required tier) =="
echo "Package dir: ${ROOT_DIR}"

if [ "$DRY" != "1" ]; then
  # 1. uv (required)
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found. Install with: brew install uv   (or curl -LsSf https://astral.sh/uv/install.sh | sh)"
    exit 1
  fi
  echo "uv: $(uv --version)"

  # 2. Python 3.11 via uv (creates isolated if needed)
  echo "Ensuring Python 3.11 ..."
  uv python install 3.11 || true

  # 3. Install editable packages (mcp + scaffold). Scaffold brings heavy runtime (camel, oasis, pymc, ...)
  echo "Installing scenario-research-mcp + camel-oasis-scaffold (editable) ..."
  cd "${ROOT_DIR}"
  uv venv .venv --python=3.11 --seed || true
  # shellcheck disable=SC1091
  source .venv/bin/activate
  uv pip install -e ".[dev]"
  if [ -d "${SCAFFOLD_DIR}" ]; then
    uv pip install -e "${SCAFFOLD_DIR}"
  else
    echo "WARNING: scaffold not found at ${SCAFFOLD_DIR}; you will need it for full runs."
  fi
else
  echo "[DRY] Skipping installs (BOOTSTRAP_DRY=1)"
fi

echo ""
echo "== Required artifacts (manual or follow scaffold scripts) =="
echo "1) MLX model ( ~4.5 GB ):"
echo "   cd ${SCAFFOLD_DIR}"
echo "   ./scripts/setup_mlx.sh     # pulls mlx-community/Qwen2.5-7B-Instruct-4bit"
echo "   ./scripts/serve_local.sh   # in a SECOND terminal: mlx_lm.server --host 127.0.0.1 --port 8080"
echo ""
echo "2) Sample profiles (mandatory data):"
echo "   mkdir -p ${SCAFFOLD_DIR}/data/reddit"
echo "   # Place user_data_36.json (from reference) into ${SCAFFOLD_DIR}/data/reddit/user_data_36.json"
echo ""
echo "3) Frontier key:"
echo "   export ANTHROPIC_API_KEY=sk-...   # or OPENAI_API_KEY"
echo ""
echo "== Happy path next command (after 1+2+3) =="
echo "   source ${ROOT_DIR}/.venv/bin/activate"
echo "   scenario-research run info_spread --agents 20 --steps 3"
echo ""
echo "Bootstrap complete. Follow the printed steps, then run the command above."
echo "For full MCP usage: scenario-research-mcp   (register via templates/)"
