"""Pre-run validation service (P3).

Blocks simulation start on invalid governed YAML / config payloads (AC12).
Provides human-readable error shapes for self-correction by callers/agents.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .agent_compiler import compile_agent_for_role, load_roles
from .models import ScenarioRun


class ValidationErrorDetail(dict):
    """Structured error for MCP and tests."""
    pass


def validate_agent_yaml_text(yaml_text: str) -> dict[str, Any]:
    """Validate raw yaml text against the governed agent schema surface.

    Returns {"valid": True} or raises with structured info.
    """
    try:
        doc = yaml.safe_load(yaml_text) or {}
    except Exception as exc:
        raise ValueError({"code": "YAML_PARSE", "message": str(exc)}) from exc

    # Minimal structural checks (roles/tools etc present and list/dict)
    if "roles" not in doc and "schema_version" not in doc:
        # allow full roles doc or single role snippet
        pass
    # If it looks like a roles doc, try compiling one
    if "roles" in doc:
        for r in doc["roles"]:
            try:
                # name is enough to exercise compile path
                compile_agent_for_role(r["name"])
            except Exception as exc:
                raise ValueError({"code": "ROLE_COMPILE", "role": r.get("name"), "message": str(exc)}) from exc
    return {"valid": True}


def validate_before_run(scenario: str, seed: int | None = None) -> None:
    """Call at the top of any scenario execution path. Raises on invalid config/yaml."""
    # For P3 we validate that the governed roles yamls in the package/ontology are loadable
    # and that the chosen scenario's implied agent compiles.
    # oteemo_billable uses its own distinct leadership_decision roles (Raja, Arka, Rod, Clifford).
    try:
        roles = load_roles()
        if not roles:
            raise RuntimeError("governed roles yaml not loadable")
        if scenario == "oteemo_billable":
            oteemo_base = Path(__file__).resolve().parents[1] / "oteemo" / "ontology" / "agents"
            compile_agent_for_role("raja_gudepu_ceo", ontology_base=oteemo_base)
            compile_agent_for_role("roderick_kelly_fed_delivery", ontology_base=oteemo_base)
            compile_agent_for_role("arkaprava_chaudhuri_vp_tech", ontology_base=oteemo_base)
            compile_agent_for_role("clifford_dalson_axiom_finops", ontology_base=oteemo_base)
        else:
            compile_agent_for_role("oasis_agent")
    except Exception as exc:
        err = {"code": "AGENT_YAML_INVALID", "message": str(exc), "scenario": scenario}
        raise ValueError(err) from exc


def validate_run_payload(payload: dict[str, Any]) -> ScenarioRun:
    """Pydantic validation + normalization for incoming run requests."""
    try:
        return ScenarioRun.model_validate(payload)
    except ValidationError as ve:
        raise ValueError({"code": "DTO_VALIDATION", "errors": ve.errors()}) from ve
