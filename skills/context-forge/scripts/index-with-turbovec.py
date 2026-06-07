#!/usr/bin/env python3
"""
Context Forge + turbovec / Weaviate Integration Helper

Index docs into turbovec .tvim (local quantized) OR Weaviate (BYOV + optional server quant).
Portable: env WEAVIATE_URL, WEAVIATE_API_KEY, TURBOVEC_BIT_WIDTH, CONTEXT_HOME.
Enhances deep-research RAG with compressed vectors; self-dogfoods on meta-utilities/docs/.

Leverages shared vector glue from ./vector_backends.py (single source for embedder + weaviate connect/ensure;
avoids duplication with research-memory MCP which imports the same when possible).

Usage (local):
    python .../index-with-turbovec.py ./docs --output .context/knowledge.tvim --bit-width 4

Usage (Weaviate):
    WEAVIATE_URL=http://localhost:8080 WEAVIATE_API_KEY=... \
    python .../index-with-turbovec.py ./docs --backend weaviate --collection meta_knowledge --create-collection
"""

import argparse
import sys
import os
from pathlib import Path

try:
    from turbovec import IdMapIndex
    import numpy as np
except ImportError:
    print("Error: turbovec + numpy required for local backend.", file=sys.stderr)
    sys.exit(1)

# Import canonical shared vector backends (embedder, weaviate helpers) from sibling in scripts/.
# This removes duplication of embed/hash/weaviate glue; see vector_backends.py for the source.
# (When run as script from skills/... this path insert makes it work without package install.)
SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from vector_backends import (  # type: ignore
    get_embedder,
    get_weaviate_client,
    ensure_weaviate_collection,
    # WEAVIATE_AVAILABLE etc are internal to shared but not re-exported; we check via client result
)

# weaviate.classes for property defs in caller (shared ensure hides its import to keep clean)
try:
    import weaviate.classes as wvc  # type: ignore
except Exception:
    wvc = None  # type: ignore


def main():
    parser = argparse.ArgumentParser(description="Index with turbovec (local) or Weaviate (BYOV)")
    parser.add_argument("directory", help="Dir with .md/.txt to index")
    parser.add_argument("--output", "-o", default=".context/knowledge.tvim", help="Local .tvim output")
    parser.add_argument("--bit-width", type=int, choices=[2, 4], default=int(os.environ.get("TURBOVEC_BIT_WIDTH", "4")))
    parser.add_argument("--dim", type=int, default=384)
    parser.add_argument("--backend", choices=["local", "weaviate"], default="local")
    parser.add_argument("--weaviate-url", default=os.environ.get("WEAVIATE_URL", "http://localhost:8080"))
    parser.add_argument("--weaviate-api-key", default=os.environ.get("WEAVIATE_API_KEY"))
    parser.add_argument("--collection", default="meta_knowledge")
    parser.add_argument("--create-collection", action="store_true")
    args = parser.parse_args()

    root = Path(args.directory).resolve()
    files = list(root.rglob("*.md")) + list(root.rglob("*.txt"))
    if not files:
        print(f"No files in {root}")
        return
    print(f"Found {len(files)} docs in {root}")

    embedder_fn = get_embedder(dim=args.dim)

    if args.backend == "local":
        index = IdMapIndex(dim=args.dim, bit_width=args.bit_width)
        id_to_path = {}
        for i, file in enumerate(files):
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
                if len(text) < 50: continue
                embedding = embedder_fn(text, dim=args.dim).astype(np.float32)
                external_id = i + 1_000_000
                index.add_with_ids(embedding.reshape(1, -1), np.array([external_id], dtype=np.uint64))
                id_to_path[external_id] = str(file.relative_to(root))
                if (i + 1) % 50 == 0: print(f"  Indexed {i+1}...")
            except Exception as e:
                print(f"  Skip {file}: {e}")
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        index.write(str(out))
        print(f"Done! {index.count} docs → {out} (bit-width {args.bit_width})")
    else:
        client = get_weaviate_client(url=args.weaviate_url, api_key=args.weaviate_api_key)
        if client is None:
            print("weaviate-client not installed or connect failed. uv pip install weaviate-client", file=sys.stderr)
            sys.exit(1)
        # Use shared ensure (idempotent create-if-missing). --create-collection now means "ensure exists".
        if args.create_collection:
            props = [
                wvc.config.Property(name="text", data_type=wvc.config.DataType.TEXT),  # type: ignore
                wvc.config.Property(name="path", data_type=wvc.config.DataType.TEXT),  # type: ignore
            ]
            if ensure_weaviate_collection(client, args.collection, properties=props):
                print(f"Ensured collection {args.collection}")
        coll = client.collections.get(args.collection)
        batch_objs = []
        for i, file in enumerate(files):
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
                if len(text) < 50:
                    continue
                vec = embedder_fn(text, dim=args.dim).tolist()
                batch_objs.append(
                    wvc.data.DataObject(  # type: ignore
                        properties={"text": text[:500], "path": str(file.relative_to(root))}, vector=vec
                    )
                )
                if len(batch_objs) >= 100:
                    coll.data.insert_many(batch_objs)
                    batch_objs = []
                    print(f"  Upserted batch up to {i+1}")
            except Exception as e:
                print(f"  Skip {file}: {e}")
        if batch_objs:
            coll.data.insert_many(batch_objs)
        print(f"Done! Indexed into Weaviate collection {args.collection} at {args.weaviate_url}")
        client.close()


if __name__ == "__main__":
    main()