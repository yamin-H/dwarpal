import secrets
from datetime import datetime, timezone

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

OPTION_FIELDS = {
    "cache_enabled", "allow_fallback", "semantic_threshold",
    "monthly_token_budget", "monthly_cost_budget_micros",
}
UPDATE_FIELDS = OPTION_FIELDS | {"name", "allowed_models", "active"}


def _tenant(row: TenantRow) -> Tenant:
    return Tenant(
        id=row.id,
        name=row.name,
        allowed_models=list(row.allowed_models),
        active=row.active,
        cache_enabled=row.cache_enabled,
        allow_fallback=row.allow_fallback,
        semantic_threshold=row.semantic_threshold,
        monthly_token_budget=row.monthly_token_budget,
        monthly_cost_budget_micros=row.monthly_cost_budget_micros,
    )


class Store:
    def __init__(self, session_factory, clock=None) -> None:
        self._sf = session_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def create_tenant(self, tenant_id: str, name: str, allowed_models=None, **options) -> Tenant:
        if not TENANT_ID_RE.match(tenant_id):
            raise ValueError("invalid tenant id")
        unknown = set(options) - OPTION_FIELDS
        if unknown:
            raise ValueError(f"unknown tenant options: {sorted(unknown)}")
        models = list(allowed_models) if allowed_models else list(DEFAULT_MODELS)
        row = TenantRow(
            id=tenant_id,
            name=name,
            allowed_models=models,
            active=True,
            cache_enabled=options.get("cache_enabled", True),
            allow_fallback=options.get("allow_fallback", True),
            semantic_threshold=options.get("semantic_threshold"),
            monthly_token_budget=options.get("monthly_token_budget"),
            monthly_cost_budget_micros=options.get("monthly_cost_budget_micros"),
        )
        with self._sf() as s:
            s.add(row)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                raise TenantExists(tenant_id) from None
            return _tenant(row)

    def get_tenant(self, tenant_id: str) -> Tenant:
        with self._sf() as s:
            row = s.get(TenantRow, tenant_id)
            if row is None:
                raise TenantNotFound(tenant_id)
            return _tenant(row)

    def update_tenant(self, tenant_id: str, **changes) -> Tenant:
        unknown = set(changes) - UPDATE_FIELDS
        if unknown:
            raise ValueError(f"unknown tenant fields: {sorted(unknown)}")
        with self._sf() as s:
            row = s.get(TenantRow, tenant_id)
            if row is None:
                raise TenantNotFound(tenant_id)
            for key, value in changes.items():
                setattr(row, key, list(value) if key == "allowed_models" else value)
            s.commit()
            return _tenant(row)

    def set_active(self, tenant_id: str, active: bool) -> None:
        self.update_tenant(tenant_id, active=active)

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
                created_at=self._clock(),
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
            return _tenant(row) if row else None

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
            n, pt, ct, avg_ms, errs, hits, sem = s.execute(
                select(
                    func.count(UsageRow.id),
                    func.coalesce(func.sum(UsageRow.prompt_tokens), 0),
                    func.coalesce(func.sum(UsageRow.completion_tokens), 0),
                    func.coalesce(func.avg(UsageRow.latency_ms), 0),
                    func.coalesce(func.sum(case((UsageRow.status != "ok", 1), else_=0)), 0),
                    func.coalesce(
                        func.sum(case((UsageRow.provider.like("cache%"), 1), else_=0)), 0),
                    func.coalesce(
                        func.sum(case((UsageRow.provider == "cache:semantic", 1), else_=0)), 0),
                ).where(UsageRow.tenant_id == tenant_id)
            ).one()
        return {
            "requests": int(n),
            "prompt_tokens": int(pt),
            "completion_tokens": int(ct),
            "total_tokens": int(pt) + int(ct),
            "errors": int(errs),
            "cache_hits": int(hits),
            "semantic_hits": int(sem),
            "cache_hit_rate": round(int(hits) / int(n), 3) if int(n) else 0.0,
            "avg_latency_ms": round(float(avg_ms), 1),
        }