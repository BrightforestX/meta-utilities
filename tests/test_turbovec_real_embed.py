def test_real_embedder_fallback_when_no_sentence_transformers():
    from index_with_turbovec import get_embedder
    embedder = get_embedder()
    assert embedder.__name__ == "simple_hash_embedding"  # or raises with install hint
