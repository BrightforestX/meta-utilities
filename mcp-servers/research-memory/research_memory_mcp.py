#!/usr/bin/env python3
"""
Research Memory MCP Server (meta-utilities)

Specialized thin MCP for *research* artifacts: store full reports + sources/citations/metadata
as durable PARA-style human+machine files under CONTEXT_HOME/research/ (or META equiv),
with optional vector backend (Weaviate BYOV or local turbovec) for citation-graph-aware
semantic recall of prior reports. Designed for RAG in deep-research / batch pipelines.

Leverages shared canonical glue from skills/context-forge/scripts/vector_backends.py
(embedder + weaviate connect/ensure + basic turbovec load/save) + patterns from the
index-with-turbovec.py . Import of shared is attempted for in-repo/editable runs (no
runtime dup); standalone uvx installs use a minimal fallback copy of glue ONLY (kept in
sync) to satisfy AGENTS self-contained mcp-servers/ + uv tool independence (no implicit
skill tree dep for MCP package consumers). Research-specific logic (PARA records, citation
graph resolution, idmap for artifacts, store/search impls) is the thin specialized layer
with zero duplication.

Same env: WEAVIATE_URL, WEAVIATE_API_KEY, TURBOVEC_BIT_WIDTH, CONTEXT_HOME,
RESEARCH_MEMORY_HOME, META_UTILITIES_HOME.

Thin by design: heavy storage/index in MCP, discoverable thin layer in
skills/research-memory/SKILL.md . Two-layer timeouts (client RESEARCH_MEMORY_TIMEOUT_SEC
+ host tool_timeouts in .grok/config.toml etc; the client var is now actively used to
wrap async tool bodies for enforcement inside MCP).

This is the canonical portable version. No project-specific paths.

See README.md in this dir for install, usage, dogfood, integration with deep-research.

Dogfood: after `uv tool install -e mcp-servers/research-memory`, use python to store
gap-analysis.md or plan snippets then search_prior_reports to recall.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # required per pyproject

from fastmcp import Context, FastMCP

# --- Two-layer timeout (client env var used inside MCP for enforcement on long ops;
#     + host in templates/grok/*.toml for outer kill per AGENTS two-layer model.
#     Local file/PARA/turbovec/weaviate-local are fast; this protects against slow remote
#     weaviate or pathological search. Contrast deep-research which passes timeout= to LLM clients.
#     Declared+used inside the tool bodies (client level) as required by plan/AGENTS.
#     search_prior_reports is the longest (vector + file scan + graph resolve); default 120s.
RESEARCH_MEMORY_TIMEOUT_SEC: float = float(
    os.getenv("RESEARCH_MEMORY_TIMEOUT_SEC", "120")
)

# Configure logging to stderr only (MCP stdio requirement)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] research-memory: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="research-memory",
    instructions=(
        "Specialized memory for deep research artifacts. "
        "Use store_artifact after producing a report to persist it with citations/sources for later recall. "
        "Use search_prior_reports (with use_vector if available) to RAG prior findings into new research. "
        "retrieve_by_citation_graph to expand a known artifact into its citation neighborhood. "
        "Files are human-readable under CONTEXT_HOME/research/ (PARA style) + optional vector index. "
        "Supports Weaviate (env WEAVIATE_*) or local turbovec. Keyword fallback always available."
    ),
)

# --- Optional heavy deps (graceful; turbovec listed hard in pyproject per plan) ---
try:
    from turbovec import IdMapIndex
    import numpy as np

    TURBOVEC_AVAILABLE = True
except ImportError:
    TURBOVEC_AVAILABLE = False
    IdMapIndex = None  # type: ignore
    np = None  # type: ignore

try:
    import weaviate
    import weaviate.classes as wvc

    WEAVIATE_AVAILABLE = True
except ImportError:
    WEAVIATE_AVAILABLE = False


# --- Shared vector backends import (for dedup) ---
# Try to load from skills/context-forge/scripts/vector_backends.py when this MCP is
# running inside the meta-utilities source tree (common for `uv tool install -e` during
# development, tests, dogfood, CI). This makes the canonical glue the executed code.
# For fully standalone `uvx research-memory` (or uv tool in isolated env with no tree),
# _shared_vb will be None and we use the fallback inline definitions below (only the
# minimal glue; PARA/citation logic stays here, never copied from context-forge).
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


# --- Embedder (delegates to shared vector_backends.py when available for in-repo runs;
#     uses minimal fallback copy ONLY for standalone uvx/uv-tool MCP installs per AGENTS
#     self-contained rule for mcp-servers/. Canonical source: the vector_backends.py) ---
if _shared_vb is not None:

    def get_embedder(dim: int = 384):
        """Return embed fn from canonical shared (no runtime dup for dev/in-repo)."""
        return _shared_vb.get_embedder(dim=dim)

else:
    # BEGIN STANDALONE FALLBACK COPY (keep function body in sync with vector_backends.py:get_embedder + simple_hash_embedding)
    # This block is reached ONLY when the full meta tree is not adjacent to the installed MCP package.
    # It is the "lightweight copy of context-forge vector patterns" for uv tool independence.
    # Citation/PARA/research-memory specific code below is NOT part of any copy; it is original thin layer.
    def get_embedder(dim: int = 384):
        """Return embed fn (sentence-transformers if avail, else simple_hash)."""
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer("all-MiniLM-L6-v2")

            def embed(text: str, dim: int = dim) -> np.ndarray:  # type: ignore
                vec = model.encode(text, normalize_embeddings=True)[:dim]
                return vec.astype(np.float32)  # type: ignore

            return embed
        except ImportError:
            logger.warning(
                "sentence-transformers not installed — using hash fallback for vectors. "
                "For production quality: uv pip install sentence-transformers"
            )

            def simple_hash_embedding(text: str, dim: int = dim) -> np.ndarray:  # type: ignore
                vec = np.zeros(dim, dtype=np.float32)  # type: ignore
                for i, char in enumerate(text[:2000]):
                    vec[i % dim] += (ord(char) % 10) - 5
                norm = np.linalg.norm(vec)  # type: ignore
                if norm > 0:
                    vec /= norm
                return vec

            return simple_hash_embedding
    # END STANDALONE FALLBACK COPY


# --- Portable home (AGENTS.md: $META_UTILITIES_HOME or env or script detection + fallbacks; no hard oteemo paths) ---
def get_research_home() -> Path:
    """Resolve research artifacts root: RESEARCH_MEMORY_HOME > CONTEXT_HOME > $META_UTILITIES_HOME/.context/research > ~/.context/research"""
    explicit = os.getenv("RESEARCH_MEMORY_HOME") or os.getenv("CONTEXT_HOME")
    if explicit:
        return Path(explicit).expanduser().resolve() / "research"
    meta = os.getenv("META_UTILITIES_HOME")
    if meta:
        return Path(meta).expanduser().resolve() / ".context" / "research"
    # script-location fallback (if run from inside meta-utilities tree)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "AGENTS.md").exists() and (parent / "mcp-servers").exists():
            return parent / ".context" / "research"
    return Path.home() / ".context" / "research"


def _ensure_dirs() -> tuple[Path, Path, Path]:
    home = get_research_home()
    artifacts = home / "artifacts"
    indexes = home / "indexes"
    artifacts.mkdir(parents=True, exist_ok=True)
    indexes.mkdir(parents=True, exist_ok=True)
    return home, artifacts, indexes


# --- Weaviate thin client (delegates to shared vector_backends when possible; research-specific
#     schema only here. Pattern leveraged, not duplicated. Fallback copy kept for standalone.) ---
WEAVIATE_COLLECTION = os.getenv("RESEARCH_WEAVIATE_COLLECTION", "research_artifacts")


if _shared_vb is not None:

    def _get_weaviate_client():
        return _shared_vb.get_weaviate_client()

    def _ensure_weaviate_collection(client) -> bool:
        if not client:
            return False
        try:
            # Provide the research-memory specific collection schema (differs from general indexer's)
            props = [
                wvc.config.Property(name="artifact_id", data_type=wvc.config.DataType.TEXT),  # type: ignore
                wvc.config.Property(name="summary", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="tags", data_type=wvc.config.DataType.TEXT_ARRAY),
                wvc.config.Property(name="citations", data_type=wvc.config.DataType.TEXT_ARRAY),
                wvc.config.Property(name="stored_at", data_type=wvc.config.DataType.TEXT),
            ]
            return _shared_vb.ensure_weaviate_collection(client, WEAVIATE_COLLECTION, properties=props)
        except Exception as e:
            logger.warning(f"Weaviate collection ensure (via shared) failed: {e}")
            return False

else:
    # BEGIN STANDALONE FALLBACK COPY of _get/_ensure (sync with shared's get_weaviate_client + ensure_weaviate_collection on changes)
    def _get_weaviate_client():
        if not WEAVIATE_AVAILABLE:
            return None
        url = os.getenv("WEAVIATE_URL", "http://localhost:8080")
        key = os.getenv("WEAVIATE_API_KEY")
        try:
            if key:
                client = weaviate.connect_to_wcs(  # type: ignore
                    cluster_url=url, auth_credentials=weaviate.auth.AuthApiKey(key)  # type: ignore
                )
            else:
                client = weaviate.connect_to_local(url=url)  # type: ignore
            return client
        except Exception as e:
            logger.warning(f"Could not connect Weaviate at {url}: {e}")
            return None

    def _ensure_weaviate_collection(client) -> bool:
        if not client:
            return False
        try:
            if not client.collections.exists(WEAVIATE_COLLECTION):
                client.collections.create(
                    WEAVIATE_COLLECTION,
                    vector_config=wvc.config.Configure.Vectors.self_provided(),  # type: ignore
                    properties=[
                        wvc.config.Property(name="artifact_id", data_type=wvc.config.DataType.TEXT),  # type: ignore
                        wvc.config.Property(name="summary", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="tags", data_type=wvc.config.DataType.TEXT_ARRAY),
                        wvc.config.Property(name="citations", data_type=wvc.config.DataType.TEXT_ARRAY),
                        wvc.config.Property(name="stored_at", data_type=wvc.config.DataType.TEXT),
                    ],
                )
                logger.info(f"Created Weaviate collection {WEAVIATE_COLLECTION}")
            return True
        except Exception as e:
            logger.warning(f"Weaviate collection ensure failed: {e}")
            return False
    # END STANDALONE FALLBACK COPY


# --- Local turbovec research index (thin; idmap sidecar + .tvim; idx load/save delegated to shared) ---
LOCAL_TVIM = "research-memory.tvim"
LOCAL_IDMAP = "research-memory-idmap.json"


def _get_local_turbovec_paths() -> tuple[Path, Path]:
    _, _, indexes = _ensure_dirs()
    return indexes / LOCAL_TVIM, indexes / LOCAL_IDMAP


def _load_local_index(dim: int = 384, bit_width: int = 4):
    if not TURBOVEC_AVAILABLE:
        return None, {}
    tvim_path, idmap_path = _get_local_turbovec_paths()
    idx = None
    idmap: dict[str, str] = {}
    try:
        if _shared_vb is not None:
            # Use shared loader (handles create or load of the .tvim)
            idx, _ = _shared_vb.load_or_create_turbovec_index(
                tvim_path=str(tvim_path) if tvim_path.exists() else None, dim=dim, bit_width=bit_width
            )
        else:
            # Fallback (standalone)
            if tvim_path.exists():
                idx = IdMapIndex.load(str(tvim_path))  # type: ignore
            else:
                idx = IdMapIndex(dim=dim, bit_width=bit_width)  # type: ignore
        if idmap_path.exists():
            idmap = json.loads(idmap_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Failed loading local turbovec research index: {e}")
        if TURBOVEC_AVAILABLE:
            idx = IdMapIndex(dim=dim, bit_width=bit_width) if _shared_vb is None else None
            if idx is None and _shared_vb is not None:
                idx, _ = _shared_vb.load_or_create_turbovec_index(dim=dim, bit_width=bit_width)
            elif idx is None:
                idx = IdMapIndex(dim=dim, bit_width=bit_width)  # type: ignore
    return idx, idmap


def _save_local_index(idx, idmap: dict[str, str]) -> bool:
    if not TURBOVEC_AVAILABLE or idx is None:
        return False
    tvim_path, idmap_path = _get_local_turbovec_paths()
    try:
        if _shared_vb is not None:
            ok = _shared_vb.save_turbovec_index(idx, str(tvim_path))
        else:
            idx.write(str(tvim_path))
            ok = True
        if ok:
            idmap_path.write_text(json.dumps(idmap, indent=2), encoding="utf-8")
            return True
        return False
    except Exception as e:
        logger.warning(f"Failed saving local turbovec index: {e}")
        return False


# --- Core storage / search (pure helpers for tests + dogfood + tool impls) ---
def _make_artifact_id() -> str:
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summarize(text: str, max_chars: int = 800) -> str:
    t = " ".join(text.split())
    return t[:max_chars] + ("..." if len(t) > max_chars else "")


async def _store_artifact_impl(
    artifact: str | dict[str, Any],
    tags: list[str] | None = None,
    citations: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """
    Persist a research artifact (report text or structured) to PARA-style files + optional vector index.

    Returns: {"id": , "stored": true, "path": json path, "md_path": , "indexed_backend": "weaviate"|"turbovec"|"none"}
    """
    home, artifacts_dir, _ = _ensure_dirs()
    if ctx:
        await ctx.info(f"Storing research artifact under {home}")

    if isinstance(artifact, dict):
        content = artifact.get("content") or artifact.get("report") or json.dumps(artifact)
        title = artifact.get("title") or artifact.get("id") or "untitled"
    else:
        content = str(artifact)
        title = "report"

    art_id = _make_artifact_id()
    stored_at = _now_iso()
    tags = tags or []
    citations = citations or []
    metadata = metadata or {}

    summary = _summarize(content)
    record = {
        "id": art_id,
        "stored_at": stored_at,
        "title": title,
        "tags": tags,
        "citations": citations,
        "metadata": metadata,
        "content": content,
        "summary": summary,
    }

    json_path = artifacts_dir / f"{art_id}.json"
    md_path = artifacts_dir / f"{art_id}.md"

    json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

    md_content = f"""# Research Artifact: {title} ({art_id})

**Stored**: {stored_at}
**Tags**: {", ".join(tags) if tags else "(none)"}
**Citations / Sources**: {", ".join(citations) if citations else "(none)"}

## Summary
{summary}

## Full Content
{content[:4000]}{" (truncated in md; see json for full)" if len(content) > 4000 else ""}
"""
    md_path.write_text(md_content, encoding="utf-8")

    if ctx:
        await ctx.info(f"Wrote PARA files: {json_path} + {md_path}")

    indexed_backend = "none"
    embedder = get_embedder()

    # Weaviate first (preferred for cross-session/shared RAG, recent subagent work)
    w_client = _get_weaviate_client()
    if w_client and _ensure_weaviate_collection(w_client):
        try:
            coll = w_client.collections.get(WEAVIATE_COLLECTION)
            vec = embedder(summary or content[:2000]).tolist()
            coll.data.insert(
                properties={
                    "artifact_id": art_id,
                    "summary": summary,
                    "tags": tags,
                    "citations": citations,
                    "stored_at": stored_at,
                },
                vector=vec,
            )
            indexed_backend = "weaviate"
            if ctx:
                await ctx.info("Indexed into Weaviate research_artifacts")
            w_client.close()
        except Exception as e:
            logger.warning(f"Weaviate index insert failed: {e}")

    # Local turbovec fallback (maintains research-memory.tvim + idmap)
    elif TURBOVEC_AVAILABLE:
        idx, idmap = _load_local_index()
        if idx is not None:
            try:
                vec = embedder(summary or content[:2000]).reshape(1, -1).astype(np.float32)  # type: ignore
                ext_id = int(art_id[:8], 16) % (2**63)  # stable-ish numeric id
                idx.add_with_ids(vec, np.array([ext_id], dtype=np.uint64))  # type: ignore
                idmap[str(ext_id)] = art_id
                if _save_local_index(idx, idmap):
                    indexed_backend = "turbovec"
                    if ctx:
                        await ctx.info("Indexed into local turbovec research-memory.tvim")
            except Exception as e:
                logger.warning(f"Local turbovec index failed: {e}")

    result = {
        "id": art_id,
        "stored": True,
        "path": str(json_path),
        "md_path": str(md_path),
        "indexed_backend": indexed_backend,
        "tags": tags,
        "citations": citations,
    }
    logger.info(f"store_artifact id={art_id} backend={indexed_backend}")
    if ctx:
        await ctx.report_progress(100, 100, f"Stored {art_id}")
    return result


async def _retrieve_by_citation_graph_impl(
    artifact_id: str, ctx: Context | None = None
) -> dict[str, Any]:
    """Load artifact + follow its citations/sources to build a simple graph (resolve prior stored ids if present)."""
    _, artifacts_dir, _ = _ensure_dirs()
    json_path = artifacts_dir / f"{artifact_id}.json"
    if not json_path.exists():
        return {"error": f"artifact not found: {artifact_id}", "graph": {"nodes": [], "edges": []}}

    record = json.loads(json_path.read_text(encoding="utf-8"))
    if ctx:
        await ctx.info(f"Loaded artifact {artifact_id}; building citation graph")

    nodes = [{"id": artifact_id, "title": record.get("title"), "tags": record.get("tags", [])}]
    edges = []
    resolved = 0

    for c in record.get("citations", []):
        # If citation looks like a stored id (12 hex chars), try resolve
        if len(c) == 12 and all(ch in "0123456789abcdef" for ch in c):
            c_path = artifacts_dir / f"{c}.json"
            if c_path.exists():
                c_rec = json.loads(c_path.read_text(encoding="utf-8"))
                nodes.append({"id": c, "title": c_rec.get("title"), "tags": c_rec.get("tags", [])})
                edges.append({"from": artifact_id, "to": c, "type": "cites"})
                resolved += 1
                continue
        # else treat as external source
        edges.append({"from": artifact_id, "to": c, "type": "sources"})

    graph = {"nodes": nodes, "edges": edges, "resolved": resolved}
    result = {"artifact": record, "graph": graph}
    logger.info(f"retrieve_by_citation_graph id={artifact_id} resolved={resolved}")
    return result


async def _search_prior_reports_impl(
    query: str,
    top_k: int = 5,
    use_vector: bool = True,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """
    Semantic (if vector backend + use_vector) or keyword search over stored research artifacts.
    Returns ranked list with id, score/snippet, tags, path.
    """
    _, artifacts_dir, _ = _ensure_dirs()
    if ctx:
        await ctx.info(f"Searching prior reports for: {query[:80]} (vector={use_vector})")

    results: list[dict[str, Any]] = []

    # Vector path: Weaviate preferred
    w_client = _get_weaviate_client() if use_vector else None
    if w_client and _ensure_weaviate_collection(w_client):
        try:
            coll = w_client.collections.get(WEAVIATE_COLLECTION)
            embedder = get_embedder()
            qvec = embedder(query).tolist()
            resp = coll.query.near_vector(near_vector=qvec, limit=top_k, return_properties=["artifact_id", "summary", "tags", "citations"])
            for obj in resp.objects:
                props = obj.properties
                aid = props["artifact_id"]
                results.append(
                    {
                        "id": aid,
                        "score": getattr(obj, "metadata", {}).get("distance", 0.0) if hasattr(obj, "metadata") else 0.0,
                        "snippet": props.get("summary", "")[:300],
                        "tags": props.get("tags", []),
                        "path": str(artifacts_dir / f"{aid}.json"),
                    }
                )
            w_client.close()
            logger.info(f"search_prior_reports (weaviate) -> {len(results)}")
            return results[:top_k]
        except Exception as e:
            logger.warning(f"Weaviate search failed, falling back: {e}")

    # Local turbovec
    if use_vector and TURBOVEC_AVAILABLE:
        idx, idmap = _load_local_index()
        if idx is not None and idmap:
            try:
                embedder = get_embedder()
                qvec = embedder(query).reshape(1, -1).astype(np.float32)  # type: ignore
                scores, ids = idx.search(qvec, k=min(top_k, 20))
                for sc, eid in zip(scores[0], ids[0]):
                    aid = idmap.get(str(int(eid)))
                    if not aid:
                        continue
                    jpath = artifacts_dir / f"{aid}.json"
                    if not jpath.exists():
                        continue
                    rec = json.loads(jpath.read_text(encoding="utf-8"))
                    results.append(
                        {
                            "id": aid,
                            "score": float(sc),
                            "snippet": rec.get("summary", "")[:300],
                            "tags": rec.get("tags", []),
                            "path": str(jpath),
                        }
                    )
                logger.info(f"search_prior_reports (turbovec) -> {len(results)}")
                return sorted(results, key=lambda r: r["score"], reverse=True)[:top_k]
            except Exception as e:
                logger.warning(f"Local turbovec search failed, keyword fallback: {e}")

    # Keyword / file fallback (always works)
    q_lower = query.lower()
    candidates = []
    for jf in sorted(artifacts_dir.glob("*.json")):
        try:
            rec = json.loads(jf.read_text(encoding="utf-8"))
            text = " ".join(
                [rec.get("title", ""), rec.get("summary", ""), " ".join(rec.get("tags", [])), rec.get("content", "")]
            ).lower()
            score = sum(1 for w in q_lower.split() if w in text)
            if score > 0:
                candidates.append(
                    {
                        "id": rec["id"],
                        "score": float(score),
                        "snippet": rec.get("summary", "")[:300],
                        "tags": rec.get("tags", []),
                        "path": str(jf),
                    }
                )
        except Exception:
            continue
    candidates.sort(key=lambda r: r["score"], reverse=True)
    logger.info(f"search_prior_reports (keyword) -> {len(candidates[:top_k])}")
    return candidates[:top_k]


# Internal pure impl (no @mcp.tool; used by tests/CLI direct + the list_artifacts wrapper below).
# (Previously the @ was mistakenly on the _impl, which would have exposed an underscore-named tool.)
async def _list_artifacts_impl(limit: int = 20, ctx: Context | None = None) -> dict[str, Any]:
    """List recent stored research artifacts (for discovery)."""
    _, artifacts_dir, _ = _ensure_dirs()
    items = []
    for jf in sorted(artifacts_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            rec = json.loads(jf.read_text(encoding="utf-8"))
            items.append(
                {
                    "id": rec["id"],
                    "title": rec.get("title"),
                    "stored_at": rec.get("stored_at"),
                    "tags": rec.get("tags", []),
                    "path": str(jf),
                }
            )
        except Exception:
            pass
    if ctx:
        await ctx.info(f"Listed {len(items)} artifacts")
    logger.info(f"list_artifacts -> {len(items)}")
    return {"count": len(items), "artifacts": items}


# --- MCP tool wrappers (async + ctx + progress per batch/deep patterns) ---
# Names chosen to exactly match pre-registered tool_timeouts in templates/grok/full-recommended.toml
# RESEARCH_MEMORY_TIMEOUT_SEC is actively enforced here via asyncio.timeout (client layer of two-layer model).
@mcp.tool()
async def store_artifact(
    artifact: str | dict[str, Any],
    tags: list[str] | None = None,
    citations: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Store research artifact (report) with citations/tags for durable recall + citation graphs."""
    try:
        async with asyncio.timeout(RESEARCH_MEMORY_TIMEOUT_SEC):
            return await _store_artifact_impl(artifact, tags, citations, metadata, ctx)
    except asyncio.TimeoutError:
        logger.warning("store_artifact timed out after %ss", RESEARCH_MEMORY_TIMEOUT_SEC)
        if ctx:
            try:
                await ctx.error(f"timeout after {RESEARCH_MEMORY_TIMEOUT_SEC}s")
            except Exception:
                pass
        return {"id": "", "stored": False, "error": "timeout", "path": "", "md_path": "", "indexed_backend": "none"}


# Alias for compatibility with plan text, manifest prompts, README, architecture docs (primary name remains store_artifact for toml timeouts + batch checks)
@mcp.tool()
async def store_research_artifact(
    artifact: str | dict[str, Any],
    tags: list[str] | None = None,
    citations: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Alias for store_artifact (for prompt/docs compatibility)."""
    try:
        async with asyncio.timeout(RESEARCH_MEMORY_TIMEOUT_SEC):
            return await _store_artifact_impl(artifact, tags, citations, metadata, ctx)
    except asyncio.TimeoutError:
        logger.warning("store_research_artifact timed out after %ss", RESEARCH_MEMORY_TIMEOUT_SEC)
        if ctx:
            try:
                await ctx.error(f"timeout after {RESEARCH_MEMORY_TIMEOUT_SEC}s")
            except Exception:
                pass
        return {"id": "", "stored": False, "error": "timeout", "path": "", "md_path": "", "indexed_backend": "none"}


@mcp.tool()
async def retrieve_by_citation_graph(
    artifact_id: str, ctx: Context | None = None
) -> dict[str, Any]:
    """Retrieve one artifact + expand to citation graph (resolves prior stored ids)."""
    try:
        async with asyncio.timeout(RESEARCH_MEMORY_TIMEOUT_SEC):
            return await _retrieve_by_citation_graph_impl(artifact_id, ctx)
    except asyncio.TimeoutError:
        logger.warning("retrieve_by_citation_graph timed out after %ss", RESEARCH_MEMORY_TIMEOUT_SEC)
        if ctx:
            try:
                await ctx.error(f"timeout after {RESEARCH_MEMORY_TIMEOUT_SEC}s")
            except Exception:
                pass
        return {"error": "timeout", "graph": {"nodes": [], "edges": []}}


@mcp.tool()
async def search_prior_reports(
    query: str,
    top_k: int = 5,
    use_vector: bool = True,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Search prior research reports (vector if backend ready, else keyword). Use for RAG before new deep research."""
    try:
        async with asyncio.timeout(RESEARCH_MEMORY_TIMEOUT_SEC):
            return await _search_prior_reports_impl(query, top_k, use_vector, ctx)
    except asyncio.TimeoutError:
        logger.warning("search_prior_reports timed out after %ss", RESEARCH_MEMORY_TIMEOUT_SEC)
        if ctx:
            try:
                await ctx.error(f"timeout after {RESEARCH_MEMORY_TIMEOUT_SEC}s")
            except Exception:
                pass
        return []


@mcp.tool()
async def list_artifacts(limit: int = 20, ctx: Context | None = None) -> dict[str, Any]:
    """List recent stored research artifacts (for discovery)."""
    try:
        async with asyncio.timeout(RESEARCH_MEMORY_TIMEOUT_SEC):
            return await _list_artifacts_impl(limit, ctx)
    except asyncio.TimeoutError:
        logger.warning("list_artifacts timed out after %ss", RESEARCH_MEMORY_TIMEOUT_SEC)
        if ctx:
            try:
                await ctx.error(f"timeout after {RESEARCH_MEMORY_TIMEOUT_SEC}s")
            except Exception:
                pass
        return {"count": 0, "artifacts": [], "error": "timeout"}



def main():
    """Entry point for `uvx research-memory` and console script (matches pre-registered toml).

    Supports both MCP server mode and direct CLI for dogfood:
        research-memory store --artifact docs/gap-analysis.md --tags meta-utilities,deep-research
        research-memory search --query "..." [--tags ...]
        research-memory graph --id <art-id>
    Falls back to MCP serve if no cmd.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Research Memory MCP Server (PARA + turbovec/Weaviate)")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8020)
    # CLI subcommand support for exact plan task 1.3 + README dogfood flows (no extra deps)
    parser.add_argument("cmd", nargs="?", choices=["store", "search", "graph", "list"], default=None,
                        help="CLI action (store/search/graph/list); omit to run as MCP server")
    parser.add_argument("--artifact", help="Path to artifact file for 'store' (or '-' for stdin)")
    parser.add_argument("--tags", help="Comma-separated tags for store/search filter")
    parser.add_argument("--query", help="Query string for 'search'")
    parser.add_argument("--id", help="Artifact id for 'graph'")
    parser.add_argument("--limit", type=int, default=10, help="Limit for list")
    args = parser.parse_args()

    if args.cmd:
        # Direct CLI path (used by plan: research-memory store --artifact ... --tags ...)
        if args.cmd == "store":
            if not args.artifact:
                print("Error: --artifact <path> required for store", file=sys.stderr)
                sys.exit(1)
            if args.artifact == "-":
                content = sys.stdin.read()
            else:
                content = Path(args.artifact).read_text(encoding="utf-8", errors="ignore")
            tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
            res = asyncio.run( _store_artifact_impl(artifact=content, tags=tags) )
            print(json.dumps(res, indent=2))
            sys.exit(0)
        elif args.cmd == "search":
            tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
            # Note: search_prior_reports MCP sig has no tags filter in this build; pass query only (tags noted in meta)
            res = asyncio.run( _search_prior_reports_impl(query=args.query or "", top_k=5, use_vector=True) )
            print(json.dumps(res, indent=2))
            sys.exit(0)
        elif args.cmd == "graph":
            if not args.id:
                print("Error: --id <artifact_id> required for graph", file=sys.stderr)
                sys.exit(1)
            res = asyncio.run( _retrieve_by_citation_graph_impl(artifact_id=args.id) )
            print(json.dumps(res, indent=2))
            sys.exit(0)
        elif args.cmd == "list":
            res = asyncio.run( _list_artifacts_impl(limit=args.limit) )
            print(json.dumps(res, indent=2))
            sys.exit(0)

    # Default: run as MCP server (for host registration)
    logger.info("Starting research-memory MCP (stdio by default; supports research RAG + citation graphs)")
    if args.transport == "http":
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
