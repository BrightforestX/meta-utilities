#!/usr/bin/env python3
"""
Context Forge - Project Setup Script

Run this in any project root to initialize Context Forge with good defaults.

This version lives in meta-utilities (the canonical portable home).

Usage:
    python /path/to/meta-utilities/skills/context-forge/scripts/setup-project.py [project_dir]
    # Examples:
    #   python setup-project.py                    # current dir
    #   python setup-project.py /path/to/my-project

You can also set CONTEXT_FORGE_HOME to point at the meta-utilities location.
"""

import os
import sys
from pathlib import Path

# Determine the Context Forge home for portable references
# Priority: $CONTEXT_FORGE_HOME > parent of this script (when run from meta-utilities) > fallback
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONTEXT_FORGE_HOME = SCRIPT_DIR.parent.parent.parent  # meta-utilities root
CONTEXT_FORGE_HOME = Path(os.getenv("CONTEXT_FORGE_HOME", DEFAULT_CONTEXT_FORGE_HOME))

def get_reference_path(relative_path: str) -> Path:
    """Return the best path to a reference file, preferring CONTEXT_FORGE_HOME."""
    return CONTEXT_FORGE_HOME / "skills" / "context-forge" / relative_path

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Set up Context Forge in a project")
    parser.add_argument("project_dir", nargs="?", default=".", help="Target project directory (default: current directory)")
    args = parser.parse_args()

    project_root = Path(args.project_dir).resolve()
    context_dir = project_root / ".context"

    print(f"Setting up Context Forge in: {project_root}")

    # Create .context directory
    context_dir.mkdir(exist_ok=True)
    (context_dir / "memory").mkdir(exist_ok=True)
    (context_dir / "knowledge").mkdir(exist_ok=True)

    # Create starter config if it doesn't exist
    config_path = context_dir / "config.yaml"
    if not config_path.exists():
        starter_config = """# Context Forge Configuration for this project
# See $CONTEXT_FORGE_HOME/skills/context-forge/references/configuration.md for full options

retrieval:
  prefer_structural: true
  max_symbol_tokens: 3500

memory:
  backend: "para"           # Start with your existing para-memory-files setup
  auto_decay: true

compression:
  enabled: true
  default_level: "balanced"

vector:
  enabled: false            # Set to true and configure when you want turbovec-powered semantic search
  engine: "turbovec"
  bit_width: 4
"""
        config_path.write_text(starter_config.strip() + "\n")
        print(f"Created {config_path}")

    # Create a basic .contextignore (like .gitignore for context)
    ignore_path = context_dir / ".contextignore"
    if not ignore_path.exists():
        ignore_content = """# Files and directories Context Forge should generally ignore for retrieval
node_modules/
dist/
build/
__pycache__/
*.pyc
*.log
*.tmp
.env
.env.*
*.min.js
*.min.css
coverage/
"""
        ignore_path.write_text(ignore_content.strip() + "\n")
        print(f"Created {ignore_path}")

    # Create a README for the .context folder
    readme_path = context_dir / "README.md"
    if not readme_path.exists():
        ref_path = get_reference_path("references/configuration.md")
        readme_content = f"""# Context Forge - Project Context

This directory contains configuration and memory for Context Forge.

## Structure

- `config.yaml` — Project-specific settings
- `memory/` — Episodic and working memory
- `knowledge/` — Semantic memory / long-term knowledge (can be indexed with turbovec)
- `.contextignore` — Patterns to exclude from retrieval

## Recommended Next Steps

1. Review `config.yaml`
2. If you use `para-memory-files`, point Context Forge at your existing memory location
3. Start using Smart Retrieval habits (see the skill for details)

For global configuration and more options, see:
    {ref_path}
"""
        readme_path.write_text(readme_content.strip() + "\n")
        print(f"Created {readme_path}")

    print("\nContext Forge project setup complete!")
    print("You can now start using /context-forge in this project.")

if __name__ == "__main__":
    main()