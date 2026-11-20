import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass

from qdrant_client import models as qm

from app.api.schemas import ChatRequest
from app.cache.exact import CachedCompletion

log = logging.getLogger("dwarpal")
COLLECTION = "dwarpal_semantic"
MAX_QUERY_CHARS = 1000


def eligible(req: ChatRequest) -> bool:
    """Only single-turn questions: multi-turn answers depend on earlier context."""
    users = [m for m in req.messages if m.role == "user"]
    if len(users) != 1 or any(m.role == "assistant" for m in req.messages):
        return False
    return 0 < len(users[0].content.strip()) <= MAX_QUERY_CHARS


def _query_text(req: ChatRequest) -> str:
    return next(m.content for m in req.messages if m.role == "user").strip()


def _context_hash(req: ChatRequest) -> str:
    """Entries are only reused under the same model, system prompt and sampling settings."""
    system = "\n".join(m.content.strip() for m in req.messages if m.role == "system")
    raw = json.dumps(
        {"model": req.model, "system": system, "t": req.temperature, "max": req.max_tokens},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass
class SemanticLookup:
    hit: CachedCompletion | None = None
    score: float | None = None
    vector: list[float] | None = None


class NullSemanticCache:
    enabled = False

    async def lookup(self, tenant_id: str, req: ChatRequest, threshold=None) -> SemanticLookup:
        return SemanticLookup()

    async def store(self, tenant_id, req, vector, completion) -> None:
        return None


class SemanticCache:
    enabled = True

    def __init__(self, client, embedder, threshold: float, ttl_seconds: int,
                 collection: str = COLLECTION, clock=time.time) -> None:
        self.client, self.embedder = client, embedder
        self.threshold, self.ttl = threshold, ttl_seconds
        self.collection, self.clock = collection, clock
        self._ready = False
        self._lock = asyncio.Lock()

    async def _ensure(self, dim: int) -> None:
        if self._ready:
            return
        async with self._lock:
            if self._ready:
                return
            if not await self.client.collection_exists(self.collection):
                await self.client.create_collection(
                    collection_name=self.collection,
                    vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
                )
            for field, schema in (
                ("tenant_id", qm.PayloadSchemaType.KEYWORD),
                ("context", qm.PayloadSchemaType.KEYWORD),
                ("created_at", qm.PayloadSchemaType.FLOAT),
            ):
                try:
                    await self.client.create_payload_index(
                        collection_name=self.collection, field_name=field, field_schema=schema
                    )
                except Exception:  # indexes are an optimisation only
                    log.warning("payload index %s not created", field, exc_info=True)
            self._ready = True

    def _filter(self, tenant_id: str, req: ChatRequest) -> qm.Filter:
        return qm.Filter(must=[
            qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tenant_id)),
            qm.FieldCondition(key="context", match=qm.MatchValue(value=_context_hash(req))),
            qm.FieldCondition(key="created_at", range=qm.Range(gte=self.clock() - self.ttl)),
        ])

    async def lookup(self, tenant_id: str, req: ChatRequest, threshold=None) -> SemanticLookup:
        if not eligible(req):
            return SemanticLookup()
        try:
            vector = await self.embedder.embed_one(_query_text(req))
            await self._ensure(len(vector))
            res = await self.client.query_points(
                collection_name=self.collection,
                query=vector,
                query_filter=self._filter(tenant_id, req),
                limit=1,
                score_threshold=self.threshold if threshold is None else threshold,
                with_payload=True,
            )
        except Exception:  # fail open: a broken semantic cache must never break requests
            log.warning("semantic lookup failed", exc_info=True)
            return SemanticLookup()
        if res.points:
            p = res.points[0]
            data = p.payload or {}
            hit = CachedCompletion(
                data["content"], data.get("prompt_tokens", 0),
                data.get("completion_tokens", 0), data.get("finish_reason", "stop"),
            )
            return SemanticLookup(hit, float(p.score), vector)
        return SemanticLookup(vector=vector)

    async def store(self, tenant_id: str, req: ChatRequest, vector: list[float],
                    completion: CachedCompletion) -> None:
        if not eligible(req) or not completion.content:
            return
        try:
            await self._ensure(len(vector))
            point_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL, f"{tenant_id}|{_context_hash(req)}|{_query_text(req)}"
            ))
            await self.client.upsert(
                collection_name=self.collection,
                points=[qm.PointStruct(id=point_id, vector=vector, payload={
                    "tenant_id": tenant_id,
                    "context": _context_hash(req),
                    "content": completion.content,
                    "prompt_tokens": completion.prompt_tokens,
                    "completion_tokens": completion.completion_tokens,
                    "finish_reason": completion.finish_reason,
                    "created_at": self.clock(),
                })],
            )
        except Exception:
            log.warning("semantic store failed", exc_info=True)