import hashlib

from qdrant_client import AsyncQdrantClient

from app.cache.embedder import build_embedder
from app.cache.semantic import COLLECTION, NullSemanticCache, SemanticCache
from app.config import Settings


def build_semantic_cache(settings: Settings):
    if not settings.semantic_cache_enabled:
        return NullSemanticCache()
    if not settings.qdrant_url:
        raise ValueError(
            "DWARPAL_QDRANT_URL is required when the semantic cache is enabled "
            "(use ':memory:' for in-process dev)."
        )
    embedder = build_embedder(
        settings.embedder, settings.embedding_model, settings.embedding_prefix
    )
    if settings.qdrant_url == ":memory:":
        client = AsyncQdrantClient(location=":memory:")
    else:
        client = AsyncQdrantClient(
            url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=2
        )
    # The collection name includes the model: vectors from different models must never mix.
    tag = hashlib.sha1(f"{settings.embedder}:{settings.embedding_model}".encode()).hexdigest()[:8]
    return SemanticCache(
        client, embedder, settings.semantic_threshold, settings.cache_ttl_seconds,
        collection=f"{COLLECTION}_{tag}",
    )