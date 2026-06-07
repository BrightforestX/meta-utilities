"""YAML-to-runtime CAMEL agent compiler (P2).

Loads the governed ontology yamls (roles, tools, policies, population_templates)
and produces runtime-ready dicts for CAMEL role construction.

All runtime agent config MUST come from here (no inline role definitions in python).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .scaffold_adapter import get_scaffold_root

PACKAGE_ONTOLOGY = Path(__file__).resolve().parents[1] / "ontology" / "agents"
OTEEMO_ONTOLOGY = Path(__file__).resolve().parents[1] / "oteemo" / "ontology" / "agents"


def _load_yaml(name: str, ontology_base: Path | None = None) -> dict[str, Any]:
    """Prefer supplied ontology_base (e.g. oteemo/), then package ontology/, then scaffold.
    This enables scenario-specific governed YAML (oteemo leadership) without duplication in shared.
    """
    bases: list[Path] = []
    if ontology_base:
        bases.append(ontology_base)
    bases += [PACKAGE_ONTOLOGY, get_scaffold_root() / "ontology" / "agents"]
    for base in bases:
        p = base / name
        if p.exists():
            return yaml.safe_load(p.read_text()) or {}
    # last resort: empty
    return {}


def load_roles(ontology_base: Path | None = None) -> dict[str, Any]:
    return _load_yaml("roles.yaml", ontology_base)


def load_tools(ontology_base: Path | None = None) -> dict[str, Any]:
    return _load_yaml("tools.yaml", ontology_base)


def load_policies(ontology_base: Path | None = None) -> dict[str, Any]:
    return _load_yaml("policies.yaml", ontology_base)


def load_population_templates(ontology_base: Path | None = None) -> dict[str, Any]:
    return _load_yaml("population_templates.yaml", ontology_base)


def compile_agent_for_role(role_name: str, ontology_base: Path | None = None) -> dict[str, Any]:
    """Return a canonical runtime spec for the given role name.

    Shape (stable across runs):
    {
      "name": "...",
      "kind": "...",
      "model_endpoint": "local|frontier",
      "tools": [ ... ],
      "policies": [ ... ],
      "population_template": "..." | null,
      "source": "odrs-agents/1@<version>"
    }

    When ontology_base is supplied (or scenario=='oteemo_billable' in callers),
    the oteemo/ slice is preferred for leadership roles (no duplication in shared).
    """
    roles = (load_roles(ontology_base) if ontology_base else load_roles()).get("roles", [])
    tools = (load_tools(ontology_base) if ontology_base else load_tools()).get("tools", {})
    policies = (load_policies(ontology_base) if ontology_base else load_policies()).get("policies", {})
    pops = (load_population_templates(ontology_base) if ontology_base else load_population_templates()).get("templates", {})

    role = next((r for r in roles if r.get("name") == role_name), None)
    if role is None:
        raise ValueError(f"unknown governed role {role_name!r}")

    roles_dict = load_roles(ontology_base) if ontology_base else load_roles()
    spec: dict[str, Any] = {
        "name": role["name"],
        "kind": role.get("kind"),
        "model_endpoint": role.get("model_endpoint"),
        "tools": role.get("tools", []),
        "policies": role.get("policies", []),
        "population_template": role.get("population_template"),
        "source": f"odrs-agents/1@{roles_dict.get('version', '0')}",
    }
    # Expand tool names to their action lists for convenience (optional, keeps governed)
    expanded = {}
    for t in spec["tools"]:
        if t in tools:
            expanded[t] = tools[t]
    if expanded:
        spec["tools_expanded"] = expanded
    return spec


def canonical_runtime_config(role_name: str, ontology_base: Path | None = None) -> str:
    """Deterministic, canonical JSON string for the compiled role (for snapshot/repro tests)."""
    spec = compile_agent_for_role(role_name, ontology_base)
    # sort keys, no whitespace variance
    return json.dumps(spec, sort_keys=True, separators=(",", ":"))
