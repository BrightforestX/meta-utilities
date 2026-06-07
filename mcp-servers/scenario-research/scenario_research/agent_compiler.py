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

PACKAGE_ONTOLOGY_ROOT = Path(__file__).resolve().parents[1] / "ontology"
PACKAGE_ONTOLOGY = PACKAGE_ONTOLOGY_ROOT / "agents"
OTEEMO_ONTOLOGY = Path(__file__).resolve().parents[1] / "oteemo" / "ontology" / "agents"


def _safe_scaffold_ontology_root() -> Path | None:
    try:
        return get_scaffold_root() / "ontology"
    except Exception:
        return None


def list_ontology_refs() -> list[dict[str, str]]:
    """List discoverable ontology references (folder + LinkML name).

    Supports user-facing ontology references by either:
    - folder name under ontology/
    - LinkML `name` field in the ontology's linkml yaml
    """
    refs: list[dict[str, str]] = []
    roots = [PACKAGE_ONTOLOGY_ROOT]
    scaffold_root = _safe_scaffold_ontology_root()
    if scaffold_root is not None:
        roots.append(scaffold_root)

    seen_folders: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if child.name in seen_folders:
                continue

            linkml_name = ""
            for candidate in ("linkml_schema.yaml", "linkml_data_model.yaml"):
                f = child / candidate
                if f.exists():
                    try:
                        doc = yaml.safe_load(f.read_text()) or {}
                        linkml_name = str(doc.get("name", "")).strip()
                    except Exception:
                        linkml_name = ""
                    break
            refs.append({
                "folder": child.name,
                "linkml_name": linkml_name,
                "path": str(child),
            })
            seen_folders.add(child.name)
    return refs


def resolve_ontology_base(reference: str | None) -> Path:
    """Resolve ontology reference by folder name or LinkML `name`."""
    if reference is None or reference.strip() == "":
        return PACKAGE_ONTOLOGY

    ref = reference.strip()
    direct = Path(ref)
    if direct.exists() and direct.is_dir():
        return direct.resolve()

    for row in list_ontology_refs():
        if row["folder"] == ref or row["linkml_name"] == ref:
            return Path(row["path"]).resolve()
    raise ValueError(f"unknown ontology reference {reference!r}")


def _load_yaml(name: str, ontology_base: Path | None = None) -> dict[str, Any]:
    """Prefer supplied ontology_base (e.g. oteemo/), then package ontology/, then scaffold.
    This enables scenario-specific governed YAML (oteemo leadership) without duplication in shared.
    """
    bases: list[Path] = []
    if ontology_base:
        bases.append(ontology_base)
    bases.append(PACKAGE_ONTOLOGY)
    scaffold_root = _safe_scaffold_ontology_root()
    if scaffold_root is not None:
        bases.append(scaffold_root / "agents")
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


def load_scenarios(ontology_base: Path | None = None) -> dict[str, Any]:
    return _load_yaml("scenarios.yaml", ontology_base)


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


def compile_scenario_spec(scenario_name: str, ontology_base: Path | None = None) -> dict[str, Any]:
    """Return a canonical runtime spec for a governed scenario definition.

    Shape (stable across runs):
    {
      "name": "...",
      "type": "...",
      "description": "...",
      "execution_risk_default": "low|medium|high",
      "parameters": {"n_steps": {...}, ...},
      "source": "odrs-scenarios/1@<version>"
    }
    """
    doc = load_scenarios(ontology_base)
    scenarios = doc.get("scenarios", {}) or {}
    raw = scenarios.get(scenario_name)
    if raw is None:
        raise ValueError(f"unknown governed scenario {scenario_name!r}")

    params = raw.get("parameters", {}) or {}
    spec: dict[str, Any] = {
        "name": scenario_name,
        "type": raw.get("type", "unspecified"),
        "description": raw.get("description", ""),
        "execution_risk_default": raw.get("execution_risk_default", "medium"),
        "parameters": params,
        "source": f"odrs-scenarios/1@{doc.get('version', '0')}",
    }
    return spec


def canonical_runtime_config(role_name: str, ontology_base: Path | None = None) -> str:
    """Deterministic, canonical JSON string for the compiled role (for snapshot/repro tests)."""
    spec = compile_agent_for_role(role_name, ontology_base)
    # sort keys, no whitespace variance
    return json.dumps(spec, sort_keys=True, separators=(",", ":"))


def canonical_scenario_config(scenario_name: str, ontology_base: Path | None = None) -> str:
    """Deterministic, canonical JSON string for a scenario definition."""
    spec = compile_scenario_spec(scenario_name, ontology_base)
    return json.dumps(spec, sort_keys=True, separators=(",", ":"))
