#!/bin/bash
#
# Context Forge - One-command "Enable Full Default Optimization" script
#
# This is a convenience wrapper. It runs the project setup and offers
# to index common knowledge folders with turbovec.
#
# Usage:
#   bash $CONTEXT_FORGE_HOME/skills/context-forge/scripts/enable-full-default.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(pwd)"

echo "🚀 Enabling full default optimization stack for: $PROJECT_ROOT"

# 1. Run the standard project setup
python "$SCRIPT_DIR/setup-project.py"

# 2. Offer (or flag-driven) to index common knowledge folders with turbovec.
# Headless / CI / non-tty: default to NO index (safe, non-mutating). Use --yes / -y to force.
Y_INDEX=false
for a in "$@"; do
  case "$a" in
    --yes|-y|--index) Y_INDEX=true ;;
  esac
done

do_index=false
if $Y_INDEX; then
  do_index=true
elif [ -t 0 ]; then
  echo ""
  echo "Would you like to index common knowledge folders with turbovec? (y/n)"
  read -r answer
  if [[ "$answer" =~ ^[Yy]$ ]]; then do_index=true; fi
else
  # non-interactive: skip (user can pass --yes for full enable in scripts)
  do_index=false
fi

if $do_index; then
    for folder in docs specs architecture research decisions; do
        if [ -d "$PROJECT_ROOT/$folder" ]; then
            echo "→ Indexing $folder/ ..."
            python "$SCRIPT_DIR/index-with-turbovec.py" "$PROJECT_ROOT/$folder" \
                --output "$PROJECT_ROOT/.context/knowledge.tvim" \
                --bit-width 4 || true
        fi
    done
    echo "✓ turbovec indexing attempted."
fi

echo ""
echo "✅ Basic default optimization enabled."
echo "Next steps:"
echo "  - Review .context/config.yaml"
echo "  - Make sure the Context Forge MCP is connected in Cursor/Claude Code"
echo "  - Start using /context-forge in your sessions"
echo ""
echo "For the complete recommended defaults, see:"
echo "  $CONTEXT_FORGE_HOME/skills/context-forge/references/default-optimization-playbook.md"