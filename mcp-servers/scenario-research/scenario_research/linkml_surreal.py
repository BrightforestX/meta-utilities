"""LinkML -> SurrealQL compiler + write/query adapter for ODRS memory artifacts.

Provides:
- compile_linkml_to_surrealql: derive DDL from LinkML schema
- plan_schema_reconcile: generate additive reconcile plan for existing DB schemas
- ScenarioSurrealWriter: idempotent, deterministic-ID writes into Surreal when healthy
  with local JSON fallback for offline/dev execution
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

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

UNIQUE_HINTS: dict[str, list[list[str]]] = {
    # LinkML memory model has no explicit identifier for these classes;
    # add practical uniqueness hints for operational idempotency.
    "ScenarioTrace": [["run_id", "period"]],
    "Attribution": [["policy_id"]],
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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _safe_token(raw: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_]+", "_", (raw or "").strip()).strip("_").lower()
    if not token:
        token = "x"
    if token[0].isdigit():
        token = f"n_{token}"
    return token


def _stable_id(*parts: str, prefix: str = "rec") -> str:
    norm = [_safe_token(p) for p in parts if p is not None]
    joined = "_".join(norm)
    digest = hashlib.sha1("|".join(norm).encode("utf-8")).hexdigest()[:10]
    base = f"{_safe_token(prefix)}_{joined}" if joined else _safe_token(prefix)
    if len(base) > 96:
        base = base[:84]
    return f"{base}_{digest}"


def _surreal_type(linkml_range: str, multivalued: bool = False) -> str:
    base = TYPE_MAP.get((linkml_range or "string").lower(), "string")
    if multivalued:
        return f"array<{base}>"
    return base


def _sorted_classes(schema: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    classes = schema.get("classes", {}) or {}
    return sorted(classes.items(), key=lambda x: x[0])


def _load_linkml_schema(linkml_path: Path | str) -> tuple[Path, dict[str, Any]]:
    import yaml

    p = Path(linkml_path)
    schema = yaml.safe_load(p.read_text()) or {}
    return p, schema


def compile_linkml_schema_spec(
    linkml_path: Path | str,
    *,
    namespace: str | None = None,
    database: str | None = None,
) -> dict[str, Any]:
    """Compile LinkML schema into a normalized spec for DDL/reconcile planning."""
    p, schema = _load_linkml_schema(linkml_path)
    ns = namespace or os.environ.get("SURREAL_NS", "odrs")
    db = database or os.environ.get("SURREAL_DB", "memory")
    schema_name = schema.get("name", p.stem)

    tables: dict[str, dict[str, Any]] = {}
    for class_name, class_def in _sorted_classes(schema):
        attrs = (class_def or {}).get("attributes", {}) or {}
        fields: dict[str, dict[str, Any]] = {}
        indexes: list[dict[str, Any]] = []
        identifier_fields: list[str] = []

        for attr_name in sorted(attrs.keys()):
            adef = attrs.get(attr_name) or {}
            linkml_range = str(adef.get("range", "string"))
            required = bool(adef.get("required", False))
            multivalued = bool(adef.get("multivalued", False))
            is_identifier = bool(adef.get("identifier", False))
            s_type = _surreal_type(linkml_range, multivalued=multivalued)
            fields[attr_name] = {"type": s_type, "required": required}
            if is_identifier:
                identifier_fields.append(attr_name)

        for ident in identifier_fields:
            indexes.append(
                {
                    "name": f"{class_name}_{ident}_uniq",
                    "columns": [ident],
                    "unique": True,
                }
            )
        for cols in UNIQUE_HINTS.get(class_name, []):
            if all(c in fields for c in cols):
                idx_name = f"{class_name}_{'_'.join(cols)}_uniq"
                if all(i["name"] != idx_name for i in indexes):
                    indexes.append(
                        {
                            "name": idx_name,
                            "columns": cols,
                            "unique": True,
                        }
                    )

        tables[class_name] = {
            "schemafull": True,
            "fields": fields,
            "indexes": indexes,
        }

    return {
        "schema_name": schema_name,
        "namespace": ns,
        "database": db,
        "tables": tables,
    }


def _render_full_ddl(spec: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"-- SurrealQL generated from LinkML name: {spec['schema_name']}")
    lines.append(f"DEFINE NAMESPACE IF NOT EXISTS {spec['namespace']};")
    lines.append(f"DEFINE DATABASE IF NOT EXISTS {spec['database']};")
    lines.append("")

    for table_name in sorted(spec["tables"].keys()):
        table = spec["tables"][table_name]
        lines.append(f"DEFINE TABLE IF NOT EXISTS {table_name} SCHEMAFULL;")
        fields = table.get("fields", {})
        for field_name in sorted(fields.keys()):
            fdef = fields[field_name]
            lines.append(f"DEFINE FIELD IF NOT EXISTS {field_name} ON TABLE {table_name} TYPE {fdef['type']};")
            if fdef.get("required"):
                lines.append(
                    f"DEFINE FIELD IF NOT EXISTS {field_name}_required ON TABLE {table_name} VALUE {field_name} ASSERT {field_name} != NONE;"
                )
        for idx in table.get("indexes", []):
            uniq = " UNIQUE" if idx.get("unique") else ""
            cols = ", ".join(idx.get("columns", []))
            lines.append(
                f"DEFINE INDEX IF NOT EXISTS {idx['name']} ON TABLE {table_name} COLUMNS {cols}{uniq};"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _normalize_existing_schema(existing_schema: dict[str, Any] | None) -> dict[str, Any]:
    if not existing_schema:
        return {"tables": {}}
    out: dict[str, Any] = {"tables": {}}
    tables = (existing_schema.get("tables", {}) or {}) if isinstance(existing_schema, dict) else {}
    for table_name, table_def in tables.items():
        tname = str(table_name)
        fields_in = (table_def or {}).get("fields", {}) or {}
        if isinstance(fields_in, list):
            fields = {str(x): {} for x in fields_in}
        else:
            fields = {str(k): (v or {}) for k, v in fields_in.items()}
        indexes_in = (table_def or {}).get("indexes", {}) or {}
        if isinstance(indexes_in, dict):
            indexes = {str(k): (v or {}) for k, v in indexes_in.items()}
        elif isinstance(indexes_in, list):
            indexes = {str(i): {} for i in indexes_in}
        else:
            indexes = {}
        out["tables"][tname] = {"fields": fields, "indexes": indexes}
    return out


def plan_schema_reconcile(
    linkml_path: Path | str,
    *,
    existing_schema: dict[str, Any] | None = None,
    namespace: str | None = None,
    database: str | None = None,
) -> dict[str, Any]:
    """Generate an additive schema reconcile plan from LinkML -> existing schema."""
    desired = compile_linkml_schema_spec(linkml_path, namespace=namespace, database=database)
    existing = _normalize_existing_schema(existing_schema)

    missing_tables: list[str] = []
    missing_fields: dict[str, list[str]] = {}
    missing_indexes: dict[str, list[str]] = {}
    lines: list[str] = []

    lines.append(f"DEFINE NAMESPACE IF NOT EXISTS {desired['namespace']};")
    lines.append(f"DEFINE DATABASE IF NOT EXISTS {desired['database']};")

    for table_name in sorted(desired["tables"].keys()):
        want_table = desired["tables"][table_name]
        have_table = existing["tables"].get(table_name)
        if have_table is None:
            missing_tables.append(table_name)
            lines.append(f"DEFINE TABLE IF NOT EXISTS {table_name} SCHEMAFULL;")
            missing_fields[table_name] = []
            for field_name in sorted(want_table.get("fields", {}).keys()):
                fdef = want_table["fields"][field_name]
                lines.append(
                    f"DEFINE FIELD IF NOT EXISTS {field_name} ON TABLE {table_name} TYPE {fdef['type']};"
                )
                if fdef.get("required"):
                    lines.append(
                        f"DEFINE FIELD IF NOT EXISTS {field_name}_required ON TABLE {table_name} VALUE {field_name} ASSERT {field_name} != NONE;"
                    )
                missing_fields[table_name].append(field_name)
            missing_indexes[table_name] = []
            for idx in want_table.get("indexes", []):
                cols = ", ".join(idx.get("columns", []))
                uniq = " UNIQUE" if idx.get("unique") else ""
                lines.append(
                    f"DEFINE INDEX IF NOT EXISTS {idx['name']} ON TABLE {table_name} COLUMNS {cols}{uniq};"
                )
                missing_indexes[table_name].append(idx["name"])
            continue

        have_fields = set((have_table.get("fields", {}) or {}).keys())
        for field_name in sorted(want_table.get("fields", {}).keys()):
            if field_name in have_fields:
                continue
            missing_fields.setdefault(table_name, []).append(field_name)
            fdef = want_table["fields"][field_name]
            lines.append(
                f"DEFINE FIELD IF NOT EXISTS {field_name} ON TABLE {table_name} TYPE {fdef['type']};"
            )
            if fdef.get("required"):
                lines.append(
                    f"DEFINE FIELD IF NOT EXISTS {field_name}_required ON TABLE {table_name} VALUE {field_name} ASSERT {field_name} != NONE;"
                )

        have_indexes = set((have_table.get("indexes", {}) or {}).keys())
        for idx in want_table.get("indexes", []):
            if idx["name"] in have_indexes:
                continue
            missing_indexes.setdefault(table_name, []).append(idx["name"])
            cols = ", ".join(idx.get("columns", []))
            uniq = " UNIQUE" if idx.get("unique") else ""
            lines.append(
                f"DEFINE INDEX IF NOT EXISTS {idx['name']} ON TABLE {table_name} COLUMNS {cols}{uniq};"
            )

    has_changes = bool(missing_tables or missing_fields or missing_indexes)
    return {
        "desired": desired,
        "existing": existing,
        "missing": {
            "tables": missing_tables,
            "fields": {k: v for k, v in missing_fields.items() if v},
            "indexes": {k: v for k, v in missing_indexes.items() if v},
        },
        "has_changes": has_changes,
        "sql": ("\n".join(lines).rstrip() + "\n"),
    }


def compile_linkml_to_surrealql(
    linkml_path: Path | str,
    *,
    namespace: str | None = None,
    database: str | None = None,
) -> str:
    """Compile LinkML memory schema into SurrealQL DDL."""
    p, _ = _load_linkml_schema(linkml_path)
    spec = compile_linkml_schema_spec(p, namespace=namespace, database=database)
    header = f"-- SurrealQL generated from LinkML: {p}\n"
    return header + _render_full_ddl(spec)


def _iter_strings(node: Any) -> Iterable[str]:
    if isinstance(node, str):
        yield node
        return
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _iter_strings(k)
            yield from _iter_strings(v)
        return
    if isinstance(node, list):
        for item in node:
            yield from _iter_strings(item)


def _extract_schema_from_info_payload(payload: dict[str, Any]) -> dict[str, Any]:
    table_re = re.compile(r"DEFINE TABLE .*?([A-Za-z0-9_]+)\s+SCHEMA", re.IGNORECASE)
    field_re = re.compile(
        r"DEFINE FIELD .*?([A-Za-z0-9_]+)\s+ON TABLE\s+([A-Za-z0-9_]+)\s+TYPE\s+([^;]+);",
        re.IGNORECASE,
    )
    index_re = re.compile(r"DEFINE INDEX .*?([A-Za-z0-9_]+)\s+ON TABLE\s+([A-Za-z0-9_]+)\s", re.IGNORECASE)

    tables: dict[str, dict[str, Any]] = {}
    for text in _iter_strings(payload):
        if "DEFINE " not in text:
            continue
        for m in table_re.finditer(text):
            t = m.group(1)
            tables.setdefault(t, {"fields": {}, "indexes": {}})
        for m in field_re.finditer(text):
            field = m.group(1)
            table = m.group(2)
            ftype = m.group(3).strip()
            tables.setdefault(table, {"fields": {}, "indexes": {}})
            tables[table]["fields"][field] = {"type": ftype}
        for m in index_re.finditer(text):
            idx_name = m.group(1)
            table = m.group(2)
            tables.setdefault(table, {"fields": {}, "indexes": {}})
            tables[table]["indexes"][idx_name] = {}
    return {"tables": tables}


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

    def inspect_schema(self) -> dict[str, Any]:
        """Best-effort schema inspection to support reconcile planning."""
        try:
            payload = self.execute_sql("INFO FOR DB;")
            return _extract_schema_from_info_payload(payload)
        except Exception:
            return {"tables": {}}


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
        if self.surreal is None or not self.surreal.is_healthy():
            return {"backend": "fallback", "schema_applied": False, "reason": "surreal_unavailable"}
        try:
            existing: dict[str, Any] = {"tables": {}}
            if _env_flag("SCENARIO_SURREAL_SCHEMA_RECONCILE", default=True):
                existing = self.surreal.inspect_schema()
            plan = plan_schema_reconcile(self.linkml_path, existing_schema=existing)
            sql = plan.get("sql", "")
            if sql.strip():
                resp = self.surreal.execute_sql(sql)
            else:
                resp = {"ok": True, "response": []}
            return {
                "backend": "surreal",
                "schema_applied": bool(sql.strip()),
                "has_changes": bool(plan.get("has_changes")),
                "missing": plan.get("missing", {}),
                "response": resp,
            }
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
        pdr_entries = trace.get("pdr_attributions", []) or []
        context_timestamp = (
            trace.get("timestamp")
            or run.finished_at
            or run.started_at
            or "1970-01-01T00:00:00+00:00"
        )

        live_context_id = _stable_id(
            trace_id or run.run_id,
            run.scenario,
            prefix="live_business_context",
        )
        live_context = {
            "timestamp": context_timestamp,
            "citations": [f"trace:{trace_id or run.run_id}"],
            "signals": {
                "scenario": run.scenario,
                "run_id": run.run_id,
                "n_agents": run.n_agents,
                "n_steps": run.n_steps,
                "status": run.status,
                "pdr_count": len(pdr_entries),
                "ontology_ref": ontology_ref,
            },
            "schema_version": "odrs-memory/1",
        }

        scenario_trace_id = _stable_id(
            run.run_id,
            str(run.n_steps),
            prefix="scenario_trace",
        )

        scenario_trace = {
            "run_id": run.run_id,
            "period": int(run.n_steps),
            "agent_decisions": policy or {},
            "pdr_attributions": pdr_entries,
            "live_business_context_ref": live_context_id,
            "schema_version": "odrs-memory/1",
            "ontology_ref": ontology_ref,
        }
        attributions: list[dict[str, Any]] = []
        attribution_ids: list[str] = []
        for idx, pdr in enumerate(pdr_entries):
            policy_id = f"{run.run_id}:{pdr.get('period', idx + 1)}"
            attributions.append(
                {
                    "policy_id": policy_id,
                    "delta": pdr.get("delta_util"),
                    "cost": pdr.get("invest_cost"),
                    "level": pdr.get("attribution_level", "policy"),
                    "schema_version": "odrs-memory/1",
                }
            )
            attribution_ids.append(_stable_id(policy_id, prefix="attribution"))
        return {
            "live_business_context_id": live_context_id,
            "live_business_context": live_context,
            "scenario_trace_id": scenario_trace_id,
            "scenario_trace": scenario_trace,
            "attribution_ids": attribution_ids,
            "attributions": attributions,
        }

    def _write_fallback(self, payload: dict[str, Any], run_id: str) -> Path:
        out = self.fallback_dir / f"{run_id}.json"
        out.write_text(json.dumps(payload, indent=2))
        return out

    def _surreal_writes(self, records: dict[str, Any]) -> str:
        q_lines = []
        q_lines.append(
            f"UPSERT LiveBusinessContext:{records['live_business_context_id']} CONTENT {json.dumps(records['live_business_context'])};"
        )
        q_lines.append(
            f"UPSERT ScenarioTrace:{records['scenario_trace_id']} CONTENT {json.dumps(records['scenario_trace'])};"
        )
        for rec_id, a in zip(records["attribution_ids"], records["attributions"]):
            q_lines.append(f"UPSERT Attribution:{rec_id} CONTENT {json.dumps(a)};")
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
                    "records_written": 2 + len(records["attributions"]),
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
            "records_written": 2 + len(records["attributions"]),
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
        "schema_spec": compile_linkml_schema_spec,
        "schema_reconcile": plan_schema_reconcile,
        "writer": ScenarioSurrealWriter,
        "persist": persist_run_artifacts,
    }
