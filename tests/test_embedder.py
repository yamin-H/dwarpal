import asyncio
import importlib.util

import pytest

from app.cache.embedder import HashEmbedder, build_embedder
from app.cache.evaluation import cosine


def embed(text):
    return asyncio.run(HashEmbedder().embed_one(text))


def test_hash_embedder_is_deterministic_and_normalized():
    a = embed("zakat koto taka")
    assert a == embed("zakat koto taka")
    assert abs(sum(x * x for x in a) - 1) < 1e-9


def test_hash_embedder_prefers_similar_spelling():
    base = embed("zakat koto taka dite hoy")
    assert cosine(base, embed("zakat koto taka dite hoy?")) > cosine(base, embed("fajr namaz rakat"))


def test_empty_text_is_safe():
    v = embed("")
    assert len(v) == 256 and abs(sum(x * x for x in v) - 1) < 1e-9


def test_build_embedder():
    assert isinstance(build_embedder("hash"), HashEmbedder)
    with pytest.raises(ValueError):
        build_embedder("nope")


def test_missing_ml_package_fails_fast(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    with pytest.raises(RuntimeError, match="requirements-ml"):
        build_embedder("sentence-transformers")