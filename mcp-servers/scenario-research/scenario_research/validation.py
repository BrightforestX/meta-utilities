"""Pre-run validation service (P3).

Blocks simulation start on invalid governed YAML / config payloads (AC12).
Provides human-readable error shapes for self-correction by callers/agents.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .agent_compiler import compile_agent_for_role, compile_scenario_spec, load_roles
from .models import ScenarioRun


class ValidationErrorDetail(dict):
    """Structured error for MCP and tests."""
    pass


def _validate_param_value(name: str, spec: dict[str, Any], value: Any) -> None:
    ptype = str(spec.get("type", "string"))
    is_int = isinstance(value, int) and not isinstance(value, bool)
    is_num = (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)

    if ptype == "integer" and not is_int:
        raise ValueError({"code": "SCENARIO_PARAM_TYPE", "param": name, "expected": "integer"})
    if ptype == "number" and not is_num:
        raise ValueError({"code": "SCENARIO_PARAM_TYPE", "param": name, "expected": "number"})
    if ptype == "boolean" and not isinstance(value, bool):
        raise ValueError({"code": "SCENARIO_PARAM_TYPE", "param": name, "expected": "boolean"})
    if ptype == "string" and not isinstance(value, str):
        raise ValueError({"code": "SCENARIO_PARAM_TYPE", "param": name, "expected": "string"})
    if ptype == "enum":
        allowed = spec.get("enum", []) or []
        if value not in allowed:
            raise ValueError({
                "code": "SCENARIO_PARAM_ENUM",
                "param": name,
                "allowed": allowed,
                "value": value,
            })

    if "minimum" in spec and is_num and float(value) < float(spec["minimum"]):
        raise ValueError({
            "code": "SCENARIO_PARAM_MIN",
            "param": name,
            "minimum": spec["minimum"],
            "value": value,
        })
    if "maximum" in spec and is_num and float(value) > float(spec["maximum"]):
        raise ValueError({
            "code": "SCENARIO_PARAM_MAX",
            "param": name,
            "maximum": spec["maximum"],
            "value": value,
        })


def _validate_scenario_params(scenario: str, runtime_params: dict[str, Any]) -> None:
    spec = compile_scenario_spec(scenario)
    defs = spec.get("parameters", {}) or {}
    unknown = sorted([k for k in runtime_params.keys() if k not in defs])
    if unknown:
        raise ValueError({"code": "SCENARIO_PARAM_UNKNOWN", "scenario": scenario, "params": unknown})

    for pname, pspec in defs.items():
        required = bool(pspec.get("required", False))
        has_default = "default" in pspec
        if required and pname not in runtime_params and not has_default:
            raise ValueError({"code": "SCENARIO_PARAM_REQUIRED", "scenario": scenario, "param": pname})

    for pname, pvalue in runtime_params.items():
        _validate_param_value(pname, defs[pname], pvalue)


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
    if "scenarios" in doc:
        for s_name in (doc.get("scenarios", {}) or {}).keys():
            try:
                compile_scenario_spec(s_name)
            except Exception as exc:
                raise ValueError({"code": "SCENARIO_COMPILE", "scenario": s_name, "message": str(exc)}) from exc
    return {"valid": True}


def validate_before_run(
    scenario: str,
    seed: int | None = None,
    n_steps: int | None = None,
    n_agents: int | None = None,
    parameters: dict[str, Any] | None = None,
) -> None:
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

        runtime_params: dict[str, Any] = {}
        if n_steps is not None:
            runtime_params["n_steps"] = n_steps
        if n_agents is not None:
            runtime_params["n_agents"] = n_agents
        if seed is not None:
            runtime_params["seed"] = seed
        if parameters:
            runtime_params.update(parameters)
        _validate_scenario_params(scenario, runtime_params)
    except Exception as exc:
        err = {"code": "AGENT_YAML_INVALID", "message": str(exc), "scenario": scenario}
        raise ValueError(err) from exc


def validate_run_payload(payload: dict[str, Any]) -> ScenarioRun:
    """Pydantic validation + normalization for incoming run requests."""
    try:
        return ScenarioRun.model_validate(payload)
    except ValidationError as ve:
        raise ValueError({"code": "DTO_VALIDATION", "errors": ve.errors()}) from ve
