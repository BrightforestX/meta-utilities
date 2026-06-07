"""
LinkML -> Weaviate collection + property derivation (additive to the Surreal path in linkml_surreal.py).

Given a LinkML YAML (e.g. ontology/memory/linkml_data_model.yaml), ensure Weaviate collections
named odrs_<classname> (lowercased) with properties mapped from attributes:
- string / default -> TEXT
- multivalued: true -> TEXT_ARRAY
- (first-cut: integers/bools also TEXT for simplicity; extend as needed)

Portable, graceful, reuses vector_backends ensure/get_client.
Intended to be called from ontology_ingest when LinkML files are encountered,
or directly for governance "ensure the model collections exist in the recall layer".

This is additive only: the canonical Surreal governance path (compile_linkml_to_surrealql etc.)
is untouched and remains the source of truth for instances.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [linkml-weaviate] %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)

# Reuse the same shared vb load pattern (duplicated tiny loader to keep this module self-contained when imported standalone)
def _try_load_shared_vector_backends():
    try:
        here = Path(__file__).resolve()
        for parent in [here] + list(here.parents):
            if (
                (parent / "AGENTS.md").exists()
                and (parent / "mcp-servers").exists()
                and (parent / "skills" / "context-forge" / "scripts" / "vector_backends.py").exists()
            ):
                shared_dir = parent / "skills" / "context-forge" / "scripts"
                if str(shared_dir) not in sys.path:
                    sys.path.insert(0, str(shared_dir))
                import vector_backends as vb  # type: ignore
                return vb
        return None
    except Exception:
        return None

_shared_vb = _try_load_shared_vector_backends()

if _shared_vb is not None:
    def _get_weaviate_client():
        return _shared_vb.get_weaviate_client()

    def _ensure_weaviate_collection(client: Any, name: str, properties: list[Any] | None = None) -> bool:
        return _shared_vb.ensure_weaviate_collection(client, name, properties=properties)
else:
    try:
        import weaviate  # type: ignore
        import weaviate.classes as wvc  # type: ignore
        WEAVIATE_AVAILABLE = True
    except Exception:
        weaviate = None  # type: ignore
        wvc = None  # type: ignore
        WEAVIATE_AVAILABLE = False

    def _get_weaviate_client():
        if not WEAVIATE_AVAILABLE:
            return None
        url = os.getenv("WEAVIATE_URL", "http://localhost:8080")
        key = os.getenv("WEAVIATE_API_KEY")
        try:
            if key:
                return weaviate.connect_to_wcs(cluster_url=url, auth_credentials=weaviate.auth.AuthApiKey(key))
            return weaviate.connect_to_local(url=url)
        except Exception as e:
            logger.warning(f"Could not connect Weaviate: {e}")
            return None

    def _ensure_weaviate_collection(client: Any, name: str, properties: list[Any] | None = None) -> bool:
        if not client or not WEAVIATE_AVAILABLE:
            return False
        try:
            if not client.collections.exists(name):
                cfg = wvc.config.Configure.Vectors.self_provided()
                props = properties or [wvc.config.Property(name="text", data_type=wvc.config.DataType.TEXT)]
                client.collections.create(name, vector_config=cfg, properties=props)
                logger.info(f"Created Weaviate collection {name}")
            return True
        except Exception as e:
            logger.warning(f"ensure {name} failed: {e}")
            return False

def ensure_weaviate_collections_from_linkml(linkml_path: str | Path, client: Any | None = None) -> dict[str, Any]:
    """
    Derive/ensure Weaviate collections + properties from LinkML classes/attributes.
    Returns {"ok": bool, "collections": list[str], "msg": ...}
    """
    p = Path(linkml_path)
    if not p.exists():
        return {"ok": False, "collections": [], "msg": f"LinkML not found: {p}"}

    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8", errors="ignore")) or {}
    except Exception as e:
        return {"ok": False, "collections": [], "msg": f"yaml parse error: {e}"}

    classes = doc.get("classes", {})
    if not classes:
        return {"ok": True, "collections": [], "msg": "no classes section; nothing to ensure"}

    c = client or _get_weaviate_client()
    if c is None:
        return {"ok": False, "collections": [], "msg": "Weaviate client unavailable (graceful; Surreal path unaffected)"}

    created: list[str] = []
    for cname, cdef in classes.items():
        coll_name = f"odrs_{cname.lower()}"  # e.g. odrs_memoryitem
        attrs = cdef.get("attributes", {}) or {}
        props: list[Any] = []
        for aname, adef in attrs.items():
            # first-cut mapping
            if isinstance(adef, dict) and adef.get("multivalued"):
                dt = wvc.config.DataType.TEXT_ARRAY if 'wvc' in dir() else "TEXT_ARRAY"
            else:
                dt = wvc.config.DataType.TEXT if 'wvc' in dir() else "TEXT"
            try:
                props.append( wvc.config.Property(name=aname, data_type=dt) )  # type: ignore
            except Exception:
                # fallback if wvc not in this scope (standalone)
                pass
        if not props:
            props = None  # let ensure use default
        if _ensure_weaviate_collection(c, coll_name, properties=props):
            created.append(coll_name)
    try:
        if client is None:
            c.close()
    except Exception:
        pass
    return {"ok": True, "collections": created, "msg": "LinkML-derived Weaviate collections ensured (additive to Surreal)"}
