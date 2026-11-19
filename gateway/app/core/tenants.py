import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.keys import generate_key, hash_key

TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")
DEFAULT_MODELS = ["auto", "mock-echo"]


class TenantExists(Exception):
    pass


class TenantNotFound(Exception):
    pass


@dataclass
class Tenant:
    id: str
    name: str
    allowed_models: list[str] = field(default_factory=lambda: list(DEFAULT_MODELS))
    active: bool = True

    def allows(self, model: str) -> bool:
        return "*" in self.allowed_models or model in self.allowed_models


@dataclass
class ApiKeyRecord:
    id: str
    tenant_id: str
    key_hash: str
    prefix: str
    created_at: datetime
    revoked: bool = False


class Store:
    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}
        self._by_hash: dict[str, ApiKeyRecord] = {}
        self._by_id: dict[str, ApiKeyRecord] = {}

    def create_tenant(self, tenant_id: str, name: str, allowed_models=None) -> Tenant:
        if not TENANT_ID_RE.match(tenant_id):
            raise ValueError("invalid tenant id")
        if tenant_id in self._tenants:
            raise TenantExists(tenant_id)
        models = list(allowed_models) if allowed_models else list(DEFAULT_MODELS)
        tenant = Tenant(tenant_id, name, models)
        self._tenants[tenant_id] = tenant
        return tenant

    def issue_key(self, tenant_id: str) -> tuple[str, ApiKeyRecord]:
        if tenant_id not in self._tenants:
            raise TenantNotFound(tenant_id)
        raw = generate_key()
        rec = ApiKeyRecord(
            id="key_" + secrets.token_hex(6),
            tenant_id=tenant_id,
            key_hash=hash_key(raw),
            prefix=raw[:12],
            created_at=datetime.now(timezone.utc),
        )
        self._by_hash[rec.key_hash] = rec
        self._by_id[rec.id] = rec
        return raw, rec

    def revoke_key(self, key_id: str) -> bool:
        rec = self._by_id.get(key_id)
        if rec is None:
            return False
        rec.revoked = True
        return True

    def resolve(self, raw_key: str) -> Tenant | None:
        rec = self._by_hash.get(hash_key(raw_key))
        if rec is None or rec.revoked:
            return None
        tenant = self._tenants.get(rec.tenant_id)
        return tenant if tenant and tenant.active else None