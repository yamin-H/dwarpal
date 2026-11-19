import secrets

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.keys import generate_key, hash_key
from app.core.tenants import (
    DEFAULT_MODELS,
    TENANT_ID_RE,
    ApiKeyRecord,
    Tenant,
    TenantExists,
    TenantNotFound,
)
from app.db.models import ApiKeyRow, TenantRow, UsageRow


class Store:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def create_tenant(self, tenant_id: str, name: str, allowed_models=None) -> Tenant:
        if not TENANT_ID_RE.match(tenant_id):
            raise ValueError("invalid tenant id")
        models = list(allowed_models) if allowed_models else list(DEFAULT_MODELS)
        with self._sf() as s:
            s.add(TenantRow(id=tenant_id, name=name, allowed_models=models, active=True))
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                raise TenantExists(tenant_id) from None
        return Tenant(tenant_id, name, models, True)

    def set_active(self, tenant_id: str, active: bool) -> None:
        with self._sf() as s:
            row = s.get(TenantRow, tenant_id)
            if row is None:
                raise TenantNotFound(tenant_id)
            row.active = active
            s.commit()

    def issue_key(self, tenant_id: str) -> tuple[str, ApiKeyRecord]:
        raw = generate_key()
        with self._sf() as s:
            if s.get(TenantRow, tenant_id) is None:
                raise TenantNotFound(tenant_id)
            row = ApiKeyRow(
                id="key_" + secrets.token_hex(6),
                tenant_id=tenant_id,
                key_hash=hash_key(raw),
                prefix=raw[:12],
                revoked=False,
            )
            s.add(row)
            s.commit()
            rec = ApiKeyRecord(row.id, row.tenant_id, row.prefix, row.created_at)
        return raw, rec

    def revoke_key(self, key_id: str) -> bool:
        with self._sf() as s:
            result = s.execute(
                update(ApiKeyRow).where(ApiKeyRow.id == key_id).values(revoked=True)
            )
            s.commit()
            return result.rowcount > 0

    def resolve(self, raw_key: str) -> Tenant | None:
        with self._sf() as s:
            row = s.execute(
                select(TenantRow)
                .join(ApiKeyRow, ApiKeyRow.tenant_id == TenantRow.id)
                .where(
                    ApiKeyRow.key_hash == hash_key(raw_key),
                    ApiKeyRow.revoked.is_(False),
                    TenantRow.active.is_(True),
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return Tenant(row.id, row.name, list(row.allowed_models), row.active)

    def record_usage(
        self, *, tenant_id, model, provider, stream, status,
        prompt_tokens, completion_tokens, latency_ms,
    ) -> None:
        with self._sf() as s:
            s.add(
                UsageRow(
                    tenant_id=tenant_id, model=model, provider=provider, stream=stream,
                    status=status, prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens, latency_ms=latency_ms,
                )
            )
            s.commit()

    def usage_summary(self, tenant_id: str) -> dict:
        with self._sf() as s:
            if s.get(TenantRow, tenant_id) is None:
                raise TenantNotFound(tenant_id)
            n, pt, ct, avg_ms, errs, hits = s.execute(
                select(
                    func.count(UsageRow.id),
                    func.coalesce(func.sum(UsageRow.prompt_tokens), 0),
                    func.coalesce(func.sum(UsageRow.completion_tokens), 0),
                    func.coalesce(func.avg(UsageRow.latency_ms), 0),
                    func.coalesce(func.sum(case((UsageRow.status != "ok", 1), else_=0)), 0),
                    func.coalesce(func.sum(case((UsageRow.provider == "cache", 1), else_=0)), 0),
                ).where(UsageRow.tenant_id == tenant_id)
            ).one()
        return {
            "requests": int(n),
            "prompt_tokens": int(pt),
            "completion_tokens": int(ct),
            "total_tokens": int(pt) + int(ct),
            "errors": int(errs),
            "cache_hits": int(hits),
            "cache_hit_rate": round(int(hits) / int(n), 3) if int(n) else 0.0,
            "avg_latency_ms": round(float(avg_ms), 1),
        }