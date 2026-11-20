import hashlib
import json
import logging
from dataclasses import asdict, dataclass

from app.api.schemas import ChatRequest
from app.core.errors import ApiError

log = logging.getLogger("dwarpal")


@dataclass
class CachedCompletion:
    content: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str = "stop"


def make_key(tenant_id: str, req: ChatRequest) -> str:
    """The tenant id is part of the key, so tenants can never share cache entries."""
    material = {
        "model": req.model,
        "messages": [{"role": m.role, "content": m.content.strip()} for m in req.messages],
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
    }
    raw = json.dumps(material, sort_keys=True, ensure_ascii=False).encode()
    return f"cache:v1:{tenant_id}:{hashlib.sha256(raw).hexdigest()}"


class NullCache:
    enabled = False

    async def get(self, key: str):
        return None

    async def set(self, key: str, value: CachedCompletion) -> None:
        return None

    async def ping(self) -> str:
        return "disabled"

    async def purge_tenant(self, tenant_id: str) -> int:
        return 0


class MemoryCache:
    """Dict-backed cache for tests and local runs without Redis. No TTL."""

    enabled = True

    def __init__(self) -> None:
        self._data: dict[str, CachedCompletion] = {}

    async def get(self, key: str):
        return self._data.get(key)

    async def set(self, key: str, value: CachedCompletion) -> None:
        self._data[key] = value

    async def ping(self) -> str:
        return "ok"

    async def purge_tenant(self, tenant_id: str) -> int:
        prefix = f"cache:v1:{tenant_id}:"
        keys = [k for k in self._data if k.startswith(prefix)]
        for k in keys:
            del self._data[k]
        return len(keys)


class RedisCache:
    enabled = True

    def __init__(self, client, ttl_seconds: int) -> None:
        self.client = client
        self.ttl = ttl_seconds

    async def get(self, key: str):
        try:
            raw = await self.client.get(key)
            return CachedCompletion(**json.loads(raw)) if raw else None
        except Exception:  # fail open: a broken cache must never break requests
            log.warning("cache get failed", exc_info=True)
            return None

    async def set(self, key: str, value: CachedCompletion) -> None:
        try:
            await self.client.set(key, json.dumps(asdict(value), ensure_ascii=False), ex=self.ttl)
        except Exception:
            log.warning("cache set failed", exc_info=True)

    async def ping(self) -> str:
        try:
            await self.client.ping()
            return "ok"
        except Exception:
            return "down"

    async def purge_tenant(self, tenant_id: str) -> int:
        pattern = f"cache:v1:{tenant_id}:*"
        deleted, batch = 0, []
        try:
            async for key in self.client.scan_iter(match=pattern, count=500):
                batch.append(key)
                if len(batch) >= 500:
                    deleted += await self.client.delete(*batch)
                    batch = []
            if batch:
                deleted += await self.client.delete(*batch)
        except Exception as exc:
            log.warning("cache purge failed", exc_info=True)
            raise ApiError(503, "Cache is unavailable.", "cache_unavailable", "api_error") from exc
        return deleted