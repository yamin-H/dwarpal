import pytest

from app.cache.factory import build_semantic_cache
from app.cache.semantic import NullSemanticCache, SemanticCache
from app.config import Settings


def s(**kw):
    return Settings(database_url="sqlite://", _env_file=None, **kw)


def test_disabled_by_default():
    assert isinstance(build_semantic_cache(s()), NullSemanticCache)


def test_enabled_requires_qdrant_url():
    with pytest.raises(ValueError):
        build_semantic_cache(s(semantic_cache_enabled=True))


def test_enabled_in_memory():
    cache = build_semantic_cache(
        s(semantic_cache_enabled=True, qdrant_url=":memory:", embedder="hash")
    )
    assert isinstance(cache, SemanticCache)