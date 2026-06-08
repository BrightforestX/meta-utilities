"""
First-cut ontology ingest for Weaviate recall layer (meta_ontology collection) + LinkML Weaviate target.

Heavy logic here (per AGENTS: mcp-servers/ for heavy + optional research deps).
Thin surface in server.py (MCP tools) + cli.py (console).

Portable: no hard paths; uses agent_compiler discovery + META / walk for shared vector_backends.
Graceful degradation: if no weaviate-client or "research" extra or Weaviate down, clear structured return
and sources on disk (ontology/ + oteemo/ontology/) remain fully usable; pure-sim unaffected.

Chunking (first-cut, good enough):
- agents/*.yaml : one chunk per role (entity_type=role), per policy (policy), per tool (tool)
- memory/linkml_data_model.yaml : one per top-level class (class) + per attribute (attribute)
text includes name + desc + key fields + compact yaml snippet.
tags e.g. ["ontology", "agents", "oteemo" | "general"]

Properties (at minimum): source (rel portable), entity_type, name, text, tags (array), schema_version, indexed_at.

Idempotency strategy (documented): before (re)ingest for a source tree, delete prior objects
whose "source" property matches the walked relative paths (or source prefix for the tree).
Stable deterministic id = uuid5 from "meta_ontology:{source_rel}:{entity_type}:{name}".
This is safe for first-cut; later can move to hash-of-content or versioned.

Reuses canonical vector_backends (shared import when in-tree per research-memory pattern;
minimal fallback copy ONLY for standalone uvx/uv-tool per AGENTS self-contained mcp-servers rule).
Two-layer timeout: caller (server) wraps with asyncio.timeout(SCENARIO_RESEARCH_TIMEOUT_SEC).

Also exposes ensure_weaviate_collections_from_linkml (additive to Surreal path in linkml_surreal.py).
Used internally on LinkML files during ingest, or callable separately.

CLI: python -m scenario_research.ontology_ingest   or via `scenario-research ingest-ontology --target weaviate`
MCP: ingest_ontology(target="weaviate", paths=None), search_ontology(query, top_k=5), delete_ontology(name?, entity_type?, source?, delete_all=False)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .agent_compiler import PACKAGE_ONTOLOGY, OTEEMO_ONTOLOGY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ontology-ingest] %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)

# --- Two-layer timeout (client env; host via tool_timeouts in server registration) ---
try:
    from .timeouts import get_timeout_seconds
    INGEST_TIMEOUT_SEC: float = get_timeout_seconds()
except Exception:
    INGEST_TIMEOUT_SEC = 300.0  # shorter for ingest vs full sims

# Dedicated short timeout for delete (fast op, but respect two-layer)
DELETE_TIMEOUT_SEC: float = 60.0

# --- Collection name (portable, overridable) ---
DEFAULT_COLLECTION = "meta_ontology"
COLLECTION = os.getenv("RESEARCH_ONTOLOGY_COLLECTION") or os.getenv("WEAVIATE_ONTOLOGY_COLLECTION", DEFAULT_COLLECTION)

# --- Shared vector_backends load (exact pattern from research-memory; satisfies AGENTS portability + self-contained) ---
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
    def get_embedder(dim: int = 384):
        try:
            return _shared_vb.get_embedder(dim=dim)
        except Exception as e:
            logger.warning(f"shared get_embedder failed ({e}); falling back to hash embedder")
            try:
                import numpy as np  # type: ignore

                def _hash_embed(text: str, dim: int = dim):
                    vec = np.zeros(dim, dtype=np.float32)
                    for i, char in enumerate(text[:2000]):
                        vec[i % dim] += (ord(char) % 10) - 5
                    norm = np.linalg.norm(vec)
                    if norm > 0:
                        vec /= norm
                    return vec

                return _hash_embed
            except Exception as inner:
                raise RuntimeError(f"no embedder available (shared failed: {e}; fallback failed: {inner})") from inner

    def _get_weaviate_client():
        return _shared_vb.get_weaviate_client()

    def _ensure_weaviate_collection(client: Any, name: str, properties: list[Any] | None = None) -> bool:
        return _shared_vb.ensure_weaviate_collection(client, name, properties=properties)
else:
    # BEGIN STANDALONE FALLBACK (keep bodies in sync with vector_backends.py on changes)
    try:
        import numpy as np  # type: ignore
        NUMPY_AVAILABLE = True
    except Exception:
        np = None  # type: ignore
        NUMPY_AVAILABLE = False

    try:
        import weaviate  # type: ignore
        import weaviate.classes as wvc  # type: ignore
        WEAVIATE_AVAILABLE = True
    except Exception:
        weaviate = None  # type: ignore
        wvc = None  # type: ignore
        WEAVIATE_AVAILABLE = False

    def simple_hash_embedding(text: str, dim: int = 384):
        if not NUMPY_AVAILABLE:
            raise RuntimeError("numpy required for hash fallback")
        vec = np.zeros(dim, dtype=np.float32)
        for i, char in enumerate(text[:2000]):
            vec[i % dim] += (ord(char) % 10) - 5
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def get_embedder(dim: int = 384):
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            def embed(text: str, dim: int = dim):
                if not NUMPY_AVAILABLE:
                    raise RuntimeError("numpy required")
                v = model.encode(text, normalize_embeddings=True)[:dim]
                return v.astype(np.float32)
            return embed
        except Exception:
            logger.warning("sentence-transformers not installed — using hash fallback. uv pip install -e '.[research]' for quality.")
            def _h(text: str, dim: int = dim):
                return simple_hash_embedding(text, dim=dim)
            return _h

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
            logger.warning(f"Could not connect Weaviate at {url}: {e}")
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
            logger.warning(f"Weaviate ensure failed for {name}: {e}")
            return False
    # END STANDALONE FALLBACK

# --- Discovery (reuse agent_compiler constants + portable; never absolute outside tree) ---
def discover_ontology_roots() -> list[Path]:
    roots: list[Path] = []
    for p in (PACKAGE_ONTOLOGY, OTEEMO_ONTOLOGY):
        if p.exists():
            roots.append(p)
    # also support the memory linkml sibling
    mem = PACKAGE_ONTOLOGY.parent / "memory"
    if mem.exists():
        roots.append(mem)
    return roots

def _rel_to_pkg(p: Path) -> str:
    """Portable relative from the scenario-research package root (for source field)."""
    try:
        pkg_root = Path(__file__).resolve().parents[1]  # mcp-servers/scenario-research/
        return str(p.resolve().relative_to(pkg_root))
    except Exception:
        return str(p)

# --- Chunking (first-cut good enough; text has enough signal for semantic recall) ---
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _make_stable_id(source_rel: str, entity_type: str, name: str) -> str:
    key = f"meta_ontology:{source_rel}:{entity_type}:{name}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, key))

def _yaml_snippet(obj: Any, max_lines: int = 12) -> str:
    try:
        s = yaml.safe_dump(obj, sort_keys=True, allow_unicode=True)
        lines = s.strip().splitlines()[:max_lines]
        return "\n".join(lines)
    except Exception:
        return str(obj)[:300]

def _chunk_role(role: dict[str, Any], source_rel: str, schema_version: str, tags: list[str]) -> dict[str, Any]:
    name = role.get("name", "unknown")
    kind = role.get("kind", "")
    desc = role.get("description", "")
    text = f"ROLE {name} ({kind})\n{desc}\nprimary: {role.get('primary_accountability','')}\ntools: {role.get('tools',[])}\npolicies: {role.get('policies',[])}\n```yaml\n{_yaml_snippet(role)}\n```"
    return {
        "id": _make_stable_id(source_rel, "role", name),
        "source": source_rel,
        "entity_type": "role",
        "name": name,
        "text": text,
        "tags": tags + ["role"],
        "schema_version": schema_version,
        "indexed_at": _now_iso(),
    }

def _chunk_policy(name: str, pol: dict[str, Any], source_rel: str, schema_version: str, tags: list[str]) -> dict[str, Any]:
    desc = pol.get("description", "")
    text = f"POLICY {name}\n{desc}\nrules:\n" + "\n".join(f"- {r}" for r in pol.get("rules", [])) + f"\n```yaml\n{_yaml_snippet(pol)}\n```"
    return {
        "id": _make_stable_id(source_rel, "policy", name),
        "source": source_rel,
        "entity_type": "policy",
        "name": name,
        "text": text,
        "tags": tags + ["policy"],
        "schema_version": schema_version,
        "indexed_at": _now_iso(),
    }

def _chunk_tool(name: str, tool: dict[str, Any], source_rel: str, schema_version: str, tags: list[str]) -> dict[str, Any]:
    desc = tool.get("description", "")
    actions = tool.get("actions", [])
    text = f"TOOL {name}\n{desc}\nactions: {actions}\n```yaml\n{_yaml_snippet(tool)}\n```"
    return {
        "id": _make_stable_id(source_rel, "tool", name),
        "source": source_rel,
        "entity_type": "tool",
        "name": name,
        "text": text,
        "tags": tags + ["tool"],
        "schema_version": schema_version,
        "indexed_at": _now_iso(),
    }

def _chunk_linkml_class(cname: str, cdef: dict[str, Any], source_rel: str, schema_version: str, tags: list[str]) -> dict[str, Any]:
    desc = cdef.get("description", "")
    attrs = list(cdef.get("attributes", {}).keys())
    text = f"LINKML CLASS {cname}\n{desc}\nattributes: {attrs}\n```yaml\n{_yaml_snippet(cdef)}\n```"
    return {
        "id": _make_stable_id(source_rel, "class", cname),
        "source": source_rel,
        "entity_type": "class",
        "name": cname,
        "text": text,
        "tags": tags + ["linkml", "class"],
        "schema_version": schema_version,
        "indexed_at": _now_iso(),
    }

def _chunk_linkml_attr(cname: str, aname: str, adef: dict[str, Any], source_rel: str, schema_version: str, tags: list[str]) -> dict[str, Any]:
    text = f"LINKML ATTR {cname}.{aname}\nrange={adef.get('range','string')} multivalued={adef.get('multivalued',False)} required={adef.get('required',False)}\n```yaml\n{_yaml_snippet(adef)}\n```"
    return {
        "id": _make_stable_id(source_rel, "attribute", f"{cname}.{aname}"),
        "source": source_rel,
        "entity_type": "attribute",
        "name": f"{cname}.{aname}",
        "text": text,
        "tags": tags + ["linkml", "attribute"],
        "schema_version": schema_version,
        "indexed_at": _now_iso(),
    }

def _walk_and_chunk(root: Path, tags_base: list[str]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    schema_version = "odrs-agents/1"
    for yf in sorted(root.rglob("*.yaml")) + sorted(root.rglob("*.yml")):
        try:
            rel = _rel_to_pkg(yf)
            doc = yaml.safe_load(yf.read_text(encoding="utf-8", errors="ignore")) or {}
            sv = doc.get("schema_version", schema_version)
            if "roles" in doc:
                for r in doc.get("roles", []):
                    chunks.append(_chunk_role(r, rel, sv, tags_base))
            if "policies" in doc:
                for pn, pv in doc.get("policies", {}).items():
                    chunks.append(_chunk_policy(pn, pv, rel, sv, tags_base))
            if "tools" in doc:
                for tn, tv in doc.get("tools", {}).items():
                    chunks.append(_chunk_tool(tn, tv, rel, sv, tags_base))
            if "classes" in doc:
                for cn, cv in doc.get("classes", {}).items():
                    chunks.append(_chunk_linkml_class(cn, cv, rel, sv, tags_base))
                    for an, av in cv.get("attributes", {}).items():
                        chunks.append(_chunk_linkml_attr(cn, an, av, rel, sv, tags_base))
        except Exception as e:
            logger.warning(f"skip {yf}: {e}")
    return chunks

async def _ingest_impl(target: str = "weaviate", paths: list[str] | None = None, ctx: Any | None = None) -> dict[str, Any]:
    if target != "weaviate":
        return {"ok": False, "msg": "first-cut only supports --target weaviate (additive to disk sources + Surreal path)"}
    roots = [Path(p) for p in (paths or [])] or discover_ontology_roots()
    if not roots:
        return {"ok": False, "msg": "no ontology roots discovered (check package layout)"}

    client = _get_weaviate_client()
    if client is None or not _ensure_weaviate_collection(client, COLLECTION, properties=None):
        # Graceful: never crash callers; sources on disk are the source of truth
        disk_note = "ontology sources remain fully functional on disk under mcp-servers/scenario-research/ontology/ and oteemo/ontology/"
        return {
            "ok": False,
            "weaviate_available": False,
            "collection": COLLECTION,
            "msg": f"Weaviate not available — {disk_note}; pure-sim unaffected. Install with uv pip install -e '.[research]' and ensure WEAVIATE_URL.",
            "roots": [str(r) for r in roots],
        }
    # Initialize embedder only after Weaviate availability so missing ML deps don't block graceful return.
    embedder = get_embedder()

    # Idempotency: clear objects for the sources we are about to (re)index
    # Refactored to _delete_by_filter for DRY (standalone delete_ontology reuses same).
    coll = client.collections.get(COLLECTION)
    cleared = 0
    for root in roots:
        try:
            marker = _rel_to_pkg(root)
            from weaviate.classes.query import Filter  # type: ignore
            filt = Filter.by_property("source").like(f"*{marker}*")
            dres = _delete_by_filter(coll, filt)
            cleared += dres.get("deleted", 0) or 0
        except Exception as e:
            logger.warning(f"delete prior for {root} (non-fatal): {e}")

    # Build chunks
    all_chunks: list[dict[str, Any]] = []
    for root in roots:
        base_tags = ["ontology"]
        if "oteemo" in str(root):
            base_tags.append("oteemo")
        else:
            base_tags.append("general")
        all_chunks.extend(_walk_and_chunk(root, base_tags))

    # Also ensure any LinkML-derived collections (additive)
    linkml_ensured: list[str] = []
    for yf in (r / "linkml_data_model.yaml" for r in roots if (r / "linkml_data_model.yaml").exists()):
        try:
            from . import linkml_weaviate  # type: ignore
            lr = linkml_weaviate.ensure_weaviate_collections_from_linkml(str(yf), client=client)
            linkml_ensured.extend(lr.get("collections", []))
        except Exception as e:
            logger.warning(f"linkml weaviate ensure skipped for {yf}: {e}")

    # Insert fresh
    inserted = 0
    for ch in all_chunks:
        try:
            vec = embedder(ch["text"] if ch.get("text") else ch["name"]).tolist()
            coll.data.insert(
                properties={
                    "source": ch["source"],
                    "entity_type": ch["entity_type"],
                    "name": ch["name"],
                    "text": ch["text"],
                    "tags": ch["tags"],
                    "schema_version": ch.get("schema_version", ""),
                    "indexed_at": ch["indexed_at"],
                },
                vector=vec,
                uuid=ch["id"],
            )
            inserted += 1
        except Exception as e:
            logger.warning(f"insert chunk {ch.get('name')} failed: {e}")

    try:
        client.close()
    except Exception:
        pass

    if ctx:
        try:
            await ctx.info(f"ontology ingest complete: {inserted} chunks into {COLLECTION}")
        except Exception:
            pass

    return {
        "ok": True,
        "collection": COLLECTION,
        "inserted": inserted,
        "cleared_prior": cleared,
        "roots": [str(r) for r in roots],
        "linkml_collections_ensured": linkml_ensured,
        "msg": "meta_ontology updated (source of truth remains the YAMLs on disk; Weaviate is recall only)",
    }

async def ingest_ontology(target: str = "weaviate", paths: list[str] | None = None, ctx: Any | None = None) -> dict[str, Any]:
    """MCP/CLI entry. Respects two-layer timeout (client here)."""
    try:
        async with asyncio.timeout(INGEST_TIMEOUT_SEC):
            return await _ingest_impl(target=target, paths=paths, ctx=ctx)
    except asyncio.TimeoutError:
        logger.warning("ingest_ontology timed out after %ss", INGEST_TIMEOUT_SEC)
        if ctx:
            try:
                await ctx.error(f"timeout after {INGEST_TIMEOUT_SEC}s")
            except Exception:
                pass
        return {"ok": False, "error": "timeout", "collection": COLLECTION}

async def _search_impl(query: str, top_k: int = 5, ctx: Any | None = None) -> list[dict[str, Any]]:
    client = _get_weaviate_client()
    if client is None or not _ensure_weaviate_collection(client, COLLECTION, properties=None):
        return [{"error": "Weaviate not available", "hint": "sources on disk under .../ontology/ are canonical; use 'show ontology <name>' via disk walk or install [research] + WEAVIATE_URL"}]
    try:
        coll = client.collections.get(COLLECTION)
        embedder = get_embedder()
        qvec = embedder(query).tolist()
        resp = coll.query.near_vector(
            near_vector=qvec,
            limit=top_k,
            return_properties=["source", "entity_type", "name", "text", "tags", "schema_version", "indexed_at"],
        )
        hits = []
        for obj in resp.objects:
            hits.append({
                "score": float(getattr(obj.metadata, "distance", 0.0) or 0.0),
                "source": obj.properties.get("source"),
                "entity_type": obj.properties.get("entity_type"),
                "name": obj.properties.get("name"),
                "text": (obj.properties.get("text") or "")[:600],
                "tags": obj.properties.get("tags", []),
                "schema_version": obj.properties.get("schema_version"),
            })
        client.close()
        return hits[:top_k]
    except Exception as e:
        logger.warning(f"search failed: {e}")
        return [{"error": str(e)}]

async def search_ontology(query: str, top_k: int = 5, ctx: Any | None = None) -> list[dict[str, Any]]:
    try:
        async with asyncio.timeout(min(INGEST_TIMEOUT_SEC, 60)):
            return await _search_impl(query=query, top_k=top_k, ctx=ctx)
    except asyncio.TimeoutError:
        if ctx:
            try:
                await ctx.error("search timed out")
            except Exception:
                pass
        return [{"error": "timeout"}]


# --- Delete helper (internal, DRY for ingest clear + standalone delete_ontology) ---
# Uses same Filter patterns + client/ensure as ingest/search for consistency.
# Fetches matching names first (best-effort, capped) then delete_many for count + list.
def _delete_by_filter(coll: Any, where: Any | None) -> dict[str, Any]:
    """Delete by (optional) Weaviate Filter; returns {'deleted': int, 'removed': list[str]}.
    Safe for idempotent no-op (0 if nothing matches). Broad where=None deletes all in coll.
    """
    removed: list[str] = []
    deleted = 0
    try:
        # Best-effort name capture before delete (limit to keep first-cut reasonable)
        if where is not None:
            q = coll.query.fetch_objects(where=where, limit=500, return_properties=["name"])
            removed = [str(o.properties.get("name") or "") for o in q.objects if o.properties.get("name")]
        else:
            # Broad: sample names (do not enumerate millions in first-cut)
            q = coll.query.fetch_objects(limit=100, return_properties=["name"])
            removed = [str(o.properties.get("name") or "") for o in q.objects if o.properties.get("name")]
        res = coll.data.delete_many(where=where) if where is not None else coll.data.delete_many()
        deleted = getattr(res, "successful", 0) or len(removed) or 0
    except Exception as e:
        logger.warning(f"delete_by_filter non-fatal: {e}")
    return {"deleted": deleted, "removed": removed}


async def _delete_impl(
    name: str | None = None,
    entity_type: str | None = None,
    source: str | None = None,
    delete_all: bool = False,
    ctx: Any | None = None,
) -> dict[str, Any]:
    """Core delete for meta_ontology (and ready for LinkML-derived if passed collection).
    Selectors AND-combined when multiple. source treated as prefix (like *src*).
    delete_all=True with no selectors = broad delete (caller must warn).
    Graceful, idempotent, returns deleted + removed names sample.
    """
    client = _get_weaviate_client()
    if client is None or not _ensure_weaviate_collection(client, COLLECTION, properties=None):
        disk_note = "ontology sources remain fully functional on disk under mcp-servers/scenario-research/ontology/ and oteemo/ontology/"
        return {
            "ok": False,
            "weaviate_available": False,
            "collection": COLLECTION,
            "deleted": 0,
            "removed": [],
            "msg": f"Weaviate not available — {disk_note}; pure-sim unaffected. Install with uv pip install -e '.[research]' and ensure WEAVIATE_URL.",
            "selectors": {"name": name, "entity_type": entity_type, "source": source, "delete_all": delete_all},
        }

    coll = client.collections.get(COLLECTION)
    from weaviate.classes.query import Filter  # type: ignore

    filters: list[Any] = []
    if name:
        filters.append(Filter.by_property("name").equal(name))
    if entity_type:
        filters.append(Filter.by_property("entity_type").equal(entity_type))
    if source:
        # prefix/contains match, matching prior ingest clear behavior
        filters.append(Filter.by_property("source").like(f"*{source}*"))

    where: Any | None = None
    if filters:
        where = filters[0]
        for f in filters[1:]:
            where = where & f
    elif not delete_all:
        try:
            client.close()
        except Exception:
            pass
        return {
            "ok": False,
            "weaviate_available": True,
            "collection": COLLECTION,
            "deleted": 0,
            "removed": [],
            "msg": "No selector provided. Use name=, entity_type=, or source= (prefix). Or delete_all=True for broad (DANGEROUS).",
            "selectors": {"name": name, "entity_type": entity_type, "source": source, "delete_all": delete_all},
        }

    # Perform (names captured inside helper for the where)
    dres = _delete_by_filter(coll, where)

    try:
        client.close()
    except Exception:
        pass

    if ctx:
        try:
            await ctx.info(f"ontology delete complete: {dres['deleted']} removed from {COLLECTION}")
        except Exception:
            pass

    return {
        "ok": True,
        "collection": COLLECTION,
        "deleted": dres["deleted"],
        "removed": dres.get("removed", [])[:50],  # cap for render safety
        "selectors": {"name": name, "entity_type": entity_type, "source": source, "delete_all": delete_all},
        "msg": f"meta_ontology delete done (deleted {dres['deleted']}); disk YAMLs + pure-sim unaffected (Weaviate is recall only)",
        "weaviate_available": True,
    }


async def delete_ontology(
    name: str | None = None,
    entity_type: str | None = None,
    source: str | None = None,
    delete_all: bool = False,
    ctx: Any | None = None,
) -> dict[str, Any]:
    """Public entry (MCP/CLI/TUI). Respects two-layer timeout (client here; shorter for delete)."""
    try:
        async with asyncio.timeout(DELETE_TIMEOUT_SEC):
            return await _delete_impl(name=name, entity_type=entity_type, source=source, delete_all=delete_all, ctx=ctx)
    except asyncio.TimeoutError:
        logger.warning("delete_ontology timed out after %ss", DELETE_TIMEOUT_SEC)
        if ctx:
            try:
                await ctx.error(f"timeout after {DELETE_TIMEOUT_SEC}s")
            except Exception:
                pass
        return {"ok": False, "error": "timeout", "deleted": 0, "collection": COLLECTION}


# --- Re-export LinkML Weaviate for callers (additive) ---
try:
    from .linkml_weaviate import ensure_weaviate_collections_from_linkml  # type: ignore
except Exception:
    def ensure_weaviate_collections_from_linkml(*a: Any, **k: Any) -> dict[str, Any]:
        return {"ok": False, "msg": "linkml_weaviate not importable (install [research] or check vector client)"}

# --- Minimal direct CLI for `python -m scenario_research.ontology_ingest` ---
def _cli_main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Ontology ingest to Weaviate (first-cut)")
    ap.add_argument("--target", default="weaviate", choices=["weaviate"])
    ap.add_argument("--paths", nargs="*", default=None, help="Optional explicit ontology roots (else auto-discover shared + oteemo)")
    ap.add_argument("--search", default=None, help="If set, run search instead of ingest and print results")
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()
    if args.search:
        res = asyncio.run(search_ontology(args.search, top_k=args.top_k))
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        res = asyncio.run(ingest_ontology(target=args.target, paths=args.paths))
        print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    _cli_main()
