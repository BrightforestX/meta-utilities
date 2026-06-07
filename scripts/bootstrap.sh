#!/bin/bash
# meta-utilities bootstrap script
# Usage: bash /path/to/meta-utilities/scripts/bootstrap.sh [project-root] [--wire-skills]

set -e

WIRE_SKILLS=false
if [[ "$2" == "--wire-skills" || "$1" == "--wire-skills" ]]; then
    WIRE_SKILLS=true
fi

META_UTILITIES_HOME="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="${1:-$(pwd)}"

echo "=== meta-utilities Bootstrap ==="
echo "meta-utilities home: $META_UTILITIES_HOME"
echo "Target project:      $TARGET_DIR"
echo

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "Warning: 'uv' not found in PATH. Some features (uv tool install) will not work."
    echo "Install uv: https://docs.astral.sh/uv/getting-started/installation/"
fi

mkdir -p "$TARGET_DIR/.context/memory" "$TARGET_DIR/.context/knowledge"

# Copy context templates
if [ -f "$META_UTILITIES_HOME/templates/context/config.yaml" ]; then
    cp -n "$META_UTILITIES_HOME/templates/context/config.yaml" "$TARGET_DIR/.context/config.yaml" 2>/dev/null || true
    echo "✓ .context/config.yaml"
fi

if [ -f "$META_UTILITIES_HOME/templates/context/.contextignore" ]; then
    cp -n "$META_UTILITIES_HOME/templates/context/.contextignore" "$TARGET_DIR/.context/.contextignore" 2>/dev/null || true
    echo "✓ .context/.contextignore"
fi

# Grok templates
mkdir -p "$TARGET_DIR/.grok"
if [ -f "$META_UTILITIES_HOME/templates/grok/grok-config-snippet.toml" ]; then
    cp -n "$META_UTILITIES_HOME/templates/grok/grok-config-snippet.toml" "$TARGET_DIR/.grok/deep-research.example.toml" 2>/dev/null || true
    echo "✓ .grok/deep-research.example.toml (merge recommended)"
fi
if [ -f "$META_UTILITIES_HOME/templates/grok/combined-context-and-research.toml" ]; then
    cp -n "$META_UTILITIES_HOME/templates/grok/combined-context-and-research.toml" "$TARGET_DIR/.grok/combined.example.toml" 2>/dev/null || true
    echo "✓ .grok/combined.example.toml"
fi

# Cursor template
if [ -f "$META_UTILITIES_HOME/templates/cursor/mcp.json.example" ]; then
    mkdir -p "$TARGET_DIR/.cursor"
    cp -n "$META_UTILITIES_HOME/templates/cursor/mcp.json.example" "$TARGET_DIR/.cursor/mcp.json.example" 2>/dev/null || true
    echo "✓ .cursor/mcp.json.example"
fi

echo
echo "=== Recommended Next Steps ==="
echo
echo "1. Install the Deep Research MCP (highly recommended):"
echo "   uv tool install -e \"$META_UTILITIES_HOME\"/mcp-servers/deep-research"
echo
echo "2. Wire the skills (Grok Build example):"
echo "   ln -sfn \"$META_UTILITIES_HOME\"/skills/context-forge ~/.grok/skills/context-forge"
echo "   ln -sfn \"$META_UTILITIES_HOME\"/skills/deep-research  ~/.grok/skills/deep-research"
echo
echo "3. (Optional) Wire for Claude Code / Cursor as well:"
echo "   ln -sfn \"$META_UTILITIES_HOME\"/skills/context-forge ~/.claude/skills/context-forge"
echo
echo "4. Start a new agent session in $TARGET_DIR and try:"
echo "   /context-forge"
echo "   /deep-research \"your ambitious research question\""
echo
if $WIRE_SKILLS; then
    echo
    echo "Attempting to wire skills..."
    mkdir -p ~/.grok/skills ~/.claude/skills
    ln -sfn "$META_UTILITIES_HOME/skills/context-forge" ~/.grok/skills/context-forge 2>/dev/null || true
    ln -sfn "$META_UTILITIES_HOME/skills/deep-research"  ~/.grok/skills/deep-research 2>/dev/null || true
    ln -sfn "$META_UTILITIES_HOME/skills/context-forge" ~/.claude/skills/context-forge 2>/dev/null || true
    echo "Skills wired (symlinks created where possible)."
fi

echo
echo "Tip: You can manually wire skills with the commands shown above, or use the patterns in INSTALLATION.md."
echo
echo "Bootstrap complete. See docs/ and INSTALLATION.md for more patterns."

