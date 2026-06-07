#!/usr/bin/env python3
"""
Shared vector backend glue for Context Forge + research-memory (embedder, Weaviate BYOV, turbovec helpers).

Single source of truth for:
- get_embedder (sentence-transformers if available, else simple_hash fallback + np)
- simple_hash_embedding
- get_weaviate_client / ensure_weaviate_collection (portable, works for different collections)

Portable: uses env WEAVIATE_URL / WEAVIATE_API_KEY, no project paths, $META fallbacks not needed here.

Used by:
- skills/context-forge/scripts/index-with-turbovec.py (canonical for general indexing)
- mcp-servers/research-memory/research_memory_mcp.py (thin specialized research layer; imports this when in-repo editable; falls back to inline copy ONLY for pure uvx standalone MCP installs per AGENTS self-contained mcp-servers/ rule)

Intent: eliminate glue duplication while preserving mcp standalone uv tool / uvx usability (no forced dep on full skills tree at install/runtime for MCP consumers).

When editing: update this file first; if changing embed/weaviate signatures, sync the fallback block in research_memory_mcp.py and callsites in indexer.

See AGENTS.md for self-contained + leverage not dup rules.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# --- Optional heavy deps (graceful in shared; callers enforce as needed) ---
try:
    import numpy as np  # type: ignore

    NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    NUMPY_AVAILABLE = False

try:
    from turbovec import IdMapIndex  # type: ignore

    TURBOVEC_AVAILABLE = True
except ImportError:
    TURBOVEC_AVAILABLE = False
    IdMapIndex = None  # type: ignore

try:
    import weaviate  # type: ignore
    import weaviate.classes as wvc  # type: ignore

    WEAVIATE_AVAILABLE = True
except ImportError:
    WEAVIATE_AVAILABLE = False
    weaviate = None  # type: ignore
    wvc = None  # type: ignore


def simple_hash_embedding(text: str, dim: int = 384) -> "np.ndarray":
    """Deterministic hash fallback embedding (when sentence-transformers absent)."""
    if not NUMPY_AVAILABLE:
        raise RuntimeError("numpy required for hash fallback embedding")
    vec = np.zeros(dim, dtype=np.float32)
    for i, char in enumerate(text[:2000]):
        vec[i % dim] += (ord(char) % 10) - 5
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def get_embedder(dim: int = 384):
    """Return embed fn (sentence-transformers if avail, else simple_hash).

    Returned function signature: embed(text: str, dim: int = dim) -> np.ndarray
    (dim arg allows override at call time; default matches the one passed to get_embedder).
    """
    if not NUMPY_AVAILABLE:
        # Will fail at use time in embed; callers that require vectors should have checked
        pass

    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")

        def embed(text: str, dim: int = dim) -> "np.ndarray":  # type: ignore
            if not NUMPY_AVAILABLE:
                raise RuntimeError("numpy required for embeddings")
            vec = model.encode(text, normalize_embeddings=True)[:dim]
            return vec.astype(np.float32)  # type: ignore

        return embed
    except ImportError:
        _warn(
            "sentence-transformers not installed — using hash fallback for vectors. "
            "For production quality: uv pip install sentence-transformers"
        )

        def simple_hash_embedding_local(text: str, dim: int = dim) -> "np.ndarray":  # type: ignore
            return simple_hash_embedding(text, dim=dim)

        return simple_hash_embedding_local


def _warn(msg: str) -> None:
    print(f"WARN: {msg}", file=sys.stderr)


def get_weaviate_client(
    url: str | None = None, api_key: str | None = None
) -> Any | None:
    """Connect to Weaviate (local or WCS) using env or args. Returns client or None on fail."""
    if not WEAVIATE_AVAILABLE:
        return None
    url = url or os.getenv("WEAVIATE_URL", "http://localhost:8080")
    key = api_key or os.getenv("WEAVIATE_API_KEY")
    try:
        if key:
            client = weaviate.connect_to_wcs(  # type: ignore
                cluster_url=url, auth_credentials=weaviate.auth.AuthApiKey(key)  # type: ignore
            )
        else:
            client = weaviate.connect_to_local(url=url)  # type: ignore
        return client
    except Exception as e:
        _warn(f"Could not connect Weaviate at {url}: {e}")
        return None


def ensure_weaviate_collection(
    client: Any,
    collection_name: str,
    properties: list[Any] | None = None,
    vector_config: Any | None = None,
) -> bool:
    """Ensure collection exists (self-provided vectors). Returns True on success (exists or created)."""
    if not client or not WEAVIATE_AVAILABLE:
        return False
    try:
        if not client.collections.exists(collection_name):
            cfg = vector_config or wvc.config.Configure.Vectors.self_provided()  # type: ignore
            props = properties or [
                wvc.config.Property(name="text", data_type=wvc.config.DataType.TEXT),  # type: ignore
            ]
            client.collections.create(
                collection_name,
                vector_config=cfg,
                properties=props,
            )
            _warn(f"Created Weaviate collection {collection_name}")
        return True
    except Exception as e:
        _warn(f"Weaviate collection ensure failed for {collection_name}: {e}")
        return False


# --- Minimal turbovec helpers (for load/create/save; idmap is caller-specific) ---
def get_turbovec_index_class():
    """Return (available, IdMapIndex, np) tuple."""
    return TURBOVEC_AVAILABLE, IdMapIndex, np


def load_or_create_turbovec_index(
    tvim_path: str | Path | None = None, dim: int = 384, bit_width: int = 4
):
    """Load existing .tvim or create fresh IdMapIndex. Returns (idx or None, was_loaded)."""
    if not TURBOVEC_AVAILABLE:
        return None, False
    idx = None
    loaded = False
    try:
        if tvim_path and Path(tvim_path).exists():
            idx = IdMapIndex.load(str(tvim_path))  # type: ignore
            loaded = True
        else:
            idx = IdMapIndex(dim=dim, bit_width=bit_width)  # type: ignore
    except Exception as e:
        _warn(f"Failed loading/creating turbovec index at {tvim_path}: {e}")
        if TURBOVEC_AVAILABLE:
            idx = IdMapIndex(dim=dim, bit_width=bit_width)  # type: ignore
    return idx, loaded


def save_turbovec_index(idx: Any, tvim_path: str | Path) -> bool:
    """Persist .tvim. Returns success."""
    if not TURBOVEC_AVAILABLE or idx is None:
        return False
    try:
        idx.write(str(tvim_path))
        return True
    except Exception as e:
        _warn(f"Failed saving turbovec index to {tvim_path}: {e}")
        return False


if __name__ == "__main__":
    # Quick smoke for the shared module itself
    print("vector_backends: checking availability...")
    print(f"  numpy: {NUMPY_AVAILABLE}")
    print(f"  turbovec: {TURBOVEC_AVAILABLE}")
    print(f"  weaviate: {WEAVIATE_AVAILABLE}")
    emb = get_embedder(dim=8)
    v = emb("hello world for embed test")
    print(f"  embed smoke dim={len(v)} (first 3: {v[:3]})")
    print("vector_backends self-smoke OK")
