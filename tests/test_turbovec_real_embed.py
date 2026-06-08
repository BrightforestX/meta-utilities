def test_real_embedder_fallback_when_no_sentence_transformers():
    import sys

    from index_with_turbovec import get_embedder

    # Deterministically exercise the documented fallback path (the test name says
    # "when_no_sentence_transformers"): force the `from sentence_transformers import ...`
    # inside get_embedder to raise ImportError, regardless of whether the package is
    # installed in this env. Setting the module to None in sys.modules makes the import
    # raise, and avoids a live HuggingFace model download when sentence-transformers IS present.
    saved = sys.modules.get("sentence_transformers")
    sys.modules["sentence_transformers"] = None  # type: ignore[assignment]
    try:
        embedder = get_embedder()
    finally:
        if saved is not None:
            sys.modules["sentence_transformers"] = saved
        else:
            sys.modules.pop("sentence_transformers", None)

    assert embedder.__name__ == "simple_hash_embedding"  # or raises with install hint
