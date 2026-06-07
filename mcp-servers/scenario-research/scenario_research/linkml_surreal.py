"""LinkML -> SurrealQL compiler + write adapter for ODRS memory artifacts.

Provides:
- compile_linkml_to_surrealql: derive DDL from LinkML schema
- ScenarioSurrealWriter: write scenario traces/attributions into Surreal when healthy
  with local JSON fallback for offline/dev execution
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .models import ScenarioRun


TYPE_MAP = {
    "string": "string",
    "integer": "int",
    "float": "float",
    "double": "float",
    "number": "float",
    "boolean": "bool",
    "date": "datetime",
    "datetime": "datetime",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_linkml_model_path() -> Path:
    return _repo_root() / "ontology" / "memory" / "linkml_data_model.yaml"


def _default_fallback_dir() -> Path:
    configured = os.environ.get("SCENARIO_SURREAL_FALLBACK_DIR")
    if configured:
        p = Path(configured)
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = _repo_root() / ".context" / "scenario-surreal-writes"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _surreal_type(linkml_range: str, multivalued: bool = False) -> str:
    base = TYPE_MAP.get((linkml_range or "string").lower(), "string")
    if multivalued:
        return f"array<{base}>"
    return base


def _sorted_classes(schema: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    classes = schema.get("classes", {}) or {}
    return sorted(classes.items(), key=lambda x: x[0])


def compile_linkml_to_surrealql(
    linkml_path: Path | str,
    *,
    namespace: str | None = None,
    database: str | None = None,
) -> str:
    """Compile LinkML memory schema into SurrealQL DDL."""
    import yaml

    p = Path(linkml_path)
    schema = yaml.safe_load(p.read_text()) or {}
    ns = namespace or os.environ.get("SURREAL_NS", "odrs")
    db = database or os.environ.get("SURREAL_DB", "memory")
    schema_name = schema.get("name", p.stem)

    lines: list[str] = []
    lines.append(f"-- SurrealQL generated from LinkML: {p}")
    lines.append(f"-- LinkML name: {schema_name}")
    lines.append(f"DEFINE NAMESPACE IF NOT EXISTS {ns};")
    lines.append(f"DEFINE DATABASE IF NOT EXISTS {db};")
    lines.append("")

    for class_name, class_def in _sorted_classes(schema):
        attrs = (class_def or {}).get("attributes", {}) or {}
        lines.append(f"DEFINE TABLE IF NOT EXISTS {class_name} SCHEMAFULL;")

        identifier_fields: list[str] = []
        for attr_name, attr_def in attrs.items():
            adef = attr_def or {}
            linkml_range = str(adef.get("range", "string"))
            required = bool(adef.get("required", False))
            multivalued = bool(adef.get("multivalued", False))
            is_identifier = bool(adef.get("identifier", False))

            s_type = _surreal_type(linkml_range, multivalued=multivalued)
            lines.append(f"DEFINE FIELD IF NOT EXISTS {attr_name} ON TABLE {class_name} TYPE {s_type};")
            if required:
                lines.append(
                    f"DEFINE FIELD IF NOT EXISTS {attr_name}_required ON TABLE {class_name} VALUE {attr_name} ASSERT {attr_name} != NONE;"
                )
            if is_identifier:
                identifier_fields.append(attr_name)

        for ident in identifier_fields:
            lines.append(
                f"DEFINE INDEX IF NOT EXISTS {class_name}_{ident}_uniq ON TABLE {class_name} COLUMNS {ident} UNIQUE;"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


class SurrealHTTP:
    """Very small Surreal HTTP wrapper (no external deps)."""

    def __init__(
        self,
        *,
        base_url: str,
        namespace: str,
        database: str,
        username: str | None = None,
        password: str | None = None,
        timeout_sec: float = 2.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.namespace = namespace
        self.database = database
        self.username = username
        self.password = password
        self.timeout_sec = timeout_sec

    def _headers(self, *, content_type: str = "text/plain") -> dict[str, str]:
        h = {
            "Accept": "application/json",
            "Content-Type": content_type,
            "NS": self.namespace,
            "DB": self.database,
        }
        if self.username and self.password:
            token = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("utf-8")
            h["Authorization"] = f"Basic {token}"
        return h

    def is_healthy(self) -> bool:
        try:
            req = urllib.request.Request(url=f"{self.base_url}/health", method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                code = int(getattr(resp, "status", 200))
                return 200 <= code < 300
        except Exception:
            return False

    def execute_sql(self, sql: str) -> dict[str, Any]:
        data = sql.encode("utf-8")
        req = urllib.request.Request(
            url=f"{self.base_url}/sql",
            data=data,
            headers=self._headers(content_type="text/plain"),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"raw": raw}
            return {"ok": True, "response": parsed}


class ScenarioSurrealWriter:
    """Persist scenario artifacts into Surreal with local fallback."""

    def __init__(
        self,
        *,
        surreal: SurrealHTTP | None = None,
        fallback_dir: Path | None = None,
        linkml_path: Path | None = None,
    ) -> None:
        self.linkml_path = linkml_path or _default_linkml_model_path()
        self.fallback_dir = fallback_dir or _default_fallback_dir()
        self.fallback_dir.mkdir(parents=True, exist_ok=True)
        self.surreal = surreal or self._from_env()

    def _from_env(self) -> SurrealHTTP | None:
        url = os.environ.get("SURREAL_URL")
        if not url:
            return None
        return SurrealHTTP(
            base_url=url,
            namespace=os.environ.get("SURREAL_NS", "odrs"),
            database=os.environ.get("SURREAL_DB", "memory"),
            username=os.environ.get("SURREAL_USER"),
            password=os.environ.get("SURREAL_PASS"),
            timeout_sec=float(os.environ.get("SURREAL_TIMEOUT_SEC", "2.0")),
        )

    def ensure_schema(self) -> dict[str, Any]:
        ddl = compile_linkml_to_surrealql(self.linkml_path)
        if self.surreal is None or not self.surreal.is_healthy():
            return {"backend": "fallback", "schema_applied": False, "reason": "surreal_unavailable"}
        try:
            resp = self.surreal.execute_sql(ddl)
            return {"backend": "surreal", "schema_applied": True, "response": resp}
        except Exception as exc:
            return {"backend": "fallback", "schema_applied": False, "reason": f"{type(exc).__name__}: {exc}"}

    def _load_trace_payload(self, run: ScenarioRun) -> dict[str, Any]:
        if not run.db_path:
            return {}
        p = Path(run.db_path)
        if not p.exists() or p.suffix.lower() != ".json":
            return {}
        try:
            doc = json.loads(p.read_text())
            return doc.get("trace", doc) if isinstance(doc, dict) else {}
        except Exception:
            return {}

    def _build_records(
        self,
        *,
        run: ScenarioRun,
        trace_id: str | None = None,
        ontology_ref: str | None = None,
    ) -> dict[str, Any]:
        trace = self._load_trace_payload(run)
        policy = (run.config_snapshot or {}).get("policy")

        scenario_trace = {
            "run_id": run.run_id,
            "period": int(run.n_steps),
            "agent_decisions": policy or {},
            "pdr_attributions": trace.get("pdr_attributions", []),
            "live_business_context_ref": trace_id,
            "schema_version": "odrs-memory/1",
            "ontology_ref": ontology_ref,
        }
        attributions: list[dict[str, Any]] = []
        for idx, pdr in enumerate(trace.get("pdr_attributions", []) or []):
            attributions.append(
                {
                    "policy_id": f"{run.run_id}:{pdr.get('period', idx + 1)}",
                    "delta": pdr.get("delta_util"),
                    "cost": pdr.get("invest_cost"),
                    "level": pdr.get("attribution_level", "policy"),
                    "schema_version": "odrs-memory/1",
                }
            )
        return {"scenario_trace": scenario_trace, "attributions": attributions}

    def _write_fallback(self, payload: dict[str, Any], run_id: str) -> Path:
        out = self.fallback_dir / f"{run_id}.json"
        out.write_text(json.dumps(payload, indent=2))
        return out

    def _surreal_writes(self, records: dict[str, Any]) -> str:
        q_lines = []
        q_lines.append(f"CREATE ScenarioTrace CONTENT {json.dumps(records['scenario_trace'])};")
        for a in records["attributions"]:
            q_lines.append(f"CREATE Attribution CONTENT {json.dumps(a)};")
        return "\n".join(q_lines) + "\n"

    def store_scenario_run(
        self,
        run: ScenarioRun,
        *,
        trace_id: str | None = None,
        ontology_ref: str | None = None,
    ) -> dict[str, Any]:
        records = self._build_records(run=run, trace_id=trace_id, ontology_ref=ontology_ref)
        schema = self.ensure_schema()

        if schema["backend"] == "surreal" and self.surreal is not None:
            try:
                sql = self._surreal_writes(records)
                resp = self.surreal.execute_sql(sql)
                return {
                    "backend": "surreal",
                    "schema": schema,
                    "records_written": 1 + len(records["attributions"]),
                    "response": resp,
                }
            except Exception as exc:
                fallback_payload = {"schema": schema, "records": records, "error": f"{type(exc).__name__}: {exc}"}
                out = self._write_fallback(fallback_payload, run.run_id)
                return {
                    "backend": "fallback",
                    "schema": schema,
                    "records_written": 0,
                    "fallback_path": str(out),
                    "error": f"{type(exc).__name__}: {exc}",
                }

        fallback_payload = {"schema": schema, "records": records}
        out = self._write_fallback(fallback_payload, run.run_id)
        return {
            "backend": "fallback",
            "schema": schema,
            "records_written": 1 + len(records["attributions"]),
            "fallback_path": str(out),
        }


def persist_run_artifacts(
    run: ScenarioRun,
    *,
    trace_id: str | None = None,
    ontology_ref: str | None = None,
) -> dict[str, Any]:
    """Convenience wrapper used by CLI/MCP paths."""
    writer = ScenarioSurrealWriter()
    return writer.store_scenario_run(run, trace_id=trace_id, ontology_ref=ontology_ref)


def get_typed_helpers() -> dict[str, Any]:
    """Return adapter and helper references for call sites/tests."""
    return {
        "compiler": compile_linkml_to_surrealql,
        "writer": ScenarioSurrealWriter,
        "persist": persist_run_artifacts,
    }
