import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, literal_column, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.keys import generate_key, hash_key
from app.core.tenants import (
    DEFAULT_MODELS,
    TENANT_ID_RE,
    ApiKeyRecord,
    KeyNotFound,
    KeyNotRotatable,
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


def _aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes. All stored times are UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _usage_view(row: UsageRow) -> dict:
    provider = row.provider or ""
    cache = {"cache:semantic": "HIT-SEMANTIC", "cache": "HIT"}.get(provider)
    return {
        "id": row.id,
        "created_at": _aware(row.created_at).isoformat(),
        "tenant_id": row.tenant_id,
        "model": row.model,
        "served_model": row.served_model,
        "provider": provider,
        "cache": cache,
        "stream": row.stream,
        "status": row.status,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "cost_usd": round((row.cost_micros or 0) / 1_000_000, 6),
        "latency_ms": row.latency_ms,
    }


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
        now = self._clock()
        with self._sf() as s:
            row = s.execute(
                select(TenantRow)
                .join(ApiKeyRow, ApiKeyRow.tenant_id == TenantRow.id)
                .where(
                    ApiKeyRow.key_hash == hash_key(raw_key),
                    ApiKeyRow.revoked.is_(False),
                    TenantRow.active.is_(True),
                    or_(ApiKeyRow.expires_at.is_(None), ApiKeyRow.expires_at > now),
                )
            ).scalar_one_or_none()
            return _tenant(row) if row else None

    def rotate_key(self, key_id: str, overlap_seconds: int) -> tuple[str, ApiKeyRecord, datetime]:
        """Issue a new key for the same tenant. The old key keeps working for the overlap window."""
        now = self._clock()
        with self._sf() as s:
            old = s.get(ApiKeyRow, key_id)
            if old is None:
                raise KeyNotFound(key_id)
            if old.revoked:
                raise KeyNotRotatable("key is revoked")
            if old.expires_at is not None:
                raise KeyNotRotatable("key was already rotated")
            raw = generate_key()
            new = ApiKeyRow(
                id="key_" + secrets.token_hex(6),
                tenant_id=old.tenant_id,
                key_hash=hash_key(raw),
                prefix=raw[:12],
                revoked=False,
                created_at=now,
            )
            expires = now + timedelta(seconds=overlap_seconds)
            old.expires_at = expires
            s.add(new)
            s.commit()
            rec = ApiKeyRecord(new.id, new.tenant_id, new.prefix, now)
        return raw, rec, expires

    def list_keys(self, tenant_id: str) -> list[dict]:
        now = self._clock()
        with self._sf() as s:
            if s.get(TenantRow, tenant_id) is None:
                raise TenantNotFound(tenant_id)
            rows = s.execute(
                select(ApiKeyRow).where(ApiKeyRow.tenant_id == tenant_id)
                .order_by(ApiKeyRow.created_at)
            ).scalars().all()
        out = []
        for row in rows:
            expires = _aware(row.expires_at)
            if row.revoked:
                status = "revoked"
            elif expires is None:
                status = "active"
            else:
                status = "expiring" if expires > now else "expired"
            out.append({
                "key_id": row.id,
                "prefix": row.prefix,
                "status": status,
                "created_at": _aware(row.created_at).isoformat(),
                "expires_at": expires.isoformat() if expires else None,
            })
        return out

    def record_usage(
        self, *, tenant_id, model, provider, stream, status,
        prompt_tokens, completion_tokens, latency_ms, cost_micros=0, served_model=None,
    ) -> None:
        with self._sf() as s:
            s.add(
                UsageRow(
                    tenant_id=tenant_id, model=model, provider=provider, stream=stream,
                    status=status, prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens, latency_ms=latency_ms,
                    cost_micros=cost_micros, served_model=served_model,
                    created_at=self._clock(),
                )
            )
            s.commit()

    def month_usage(self, tenant_id: str) -> tuple[int, int]:
        """Successful tokens and cost (micro-USD) since the start of the current UTC month."""
        start = self._clock().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        with self._sf() as s:
            tokens, cost = s.execute(
                select(
                    func.coalesce(func.sum(UsageRow.prompt_tokens + UsageRow.completion_tokens), 0),
                    func.coalesce(func.sum(UsageRow.cost_micros), 0),
                ).where(
                    UsageRow.tenant_id == tenant_id,
                    UsageRow.status == "ok",
                    UsageRow.created_at >= start,
                )
            ).one()
        return int(tokens), int(cost)

    def usage_summary(self, tenant_id: str) -> dict:
        with self._sf() as s:
            tenant = s.get(TenantRow, tenant_id)
            if tenant is None:
                raise TenantNotFound(tenant_id)
            token_budget = tenant.monthly_token_budget
            cost_budget = tenant.monthly_cost_budget_micros
            n, pt, ct, avg_ms, errs, hits, sem, cost = s.execute(
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
                    func.coalesce(func.sum(UsageRow.cost_micros), 0),
                ).where(UsageRow.tenant_id == tenant_id)
            ).one()
        month_tokens, month_cost = self.month_usage(tenant_id)
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
            "cost_usd": round(int(cost) / 1_000_000, 6),
            "month_to_date": {
                "tokens": month_tokens,
                "cost_usd": round(month_cost / 1_000_000, 6),
                "token_budget": token_budget,
                "cost_budget_usd": None if cost_budget is None else cost_budget / 1_000_000,
            },
        }

    def ping(self) -> str:
        try:
            with self._sf() as s:
                s.execute(select(1))
            return "ok"
        except Exception:
            return "down"

    def list_tenants(self) -> list[tuple[Tenant, dict]]:
        now = self._clock()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        tokens = UsageRow.prompt_tokens + UsageRow.completion_tokens
        with self._sf() as s:
            tenants = s.execute(
                select(TenantRow).order_by(TenantRow.created_at, TenantRow.id)
            ).scalars().all()
            usage = {
                r[0]: r[1:] for r in s.execute(
                    select(
                        UsageRow.tenant_id,
                        func.count(UsageRow.id),
                        func.coalesce(func.sum(tokens), 0),
                        func.coalesce(func.sum(UsageRow.cost_micros), 0),
                        func.coalesce(
                            func.sum(case((UsageRow.provider.like("cache%"), 1), else_=0)), 0),
                    ).group_by(UsageRow.tenant_id)
                ).all()
            }
            month = {
                r[0]: (int(r[1]), int(r[2])) for r in s.execute(
                    select(
                        UsageRow.tenant_id,
                        func.coalesce(func.sum(tokens), 0),
                        func.coalesce(func.sum(UsageRow.cost_micros), 0),
                    ).where(UsageRow.status == "ok", UsageRow.created_at >= month_start)
                    .group_by(UsageRow.tenant_id)
                ).all()
            }
            keys = dict(s.execute(
                select(ApiKeyRow.tenant_id, func.count(ApiKeyRow.id)).where(
                    ApiKeyRow.revoked.is_(False),
                    or_(ApiKeyRow.expires_at.is_(None), ApiKeyRow.expires_at > now),
                ).group_by(ApiKeyRow.tenant_id)
            ).all())
        out = []
        for row in tenants:
            n, tok, cost, hits = usage.get(row.id, (0, 0, 0, 0))
            m_tok, m_cost = month.get(row.id, (0, 0))
            out.append((_tenant(row), {
                "requests": int(n),
                "total_tokens": int(tok),
                "cost_usd": round(int(cost) / 1_000_000, 6),
                "cache_hits": int(hits),
                "active_keys": int(keys.get(row.id, 0)),
                "month_tokens": m_tok,
                "month_cost_usd": round(m_cost / 1_000_000, 6),
            }))
        return out

    def overview(self, hours: int) -> dict:
        now = self._clock()
        current = now.replace(minute=0, second=0, microsecond=0)
        start = current - timedelta(hours=hours - 1)
        in_window = UsageRow.created_at >= start
        is_hit = UsageRow.provider.like("cache%")
        tokens = UsageRow.prompt_tokens + UsageRow.completion_tokens
        with self._sf() as s:
            if s.get_bind().dialect.name == "sqlite":
                bucket = func.strftime("%Y-%m-%dT%H", UsageRow.created_at)
            else:
                bucket = func.to_char(
                    func.date_trunc("hour", func.timezone("UTC", UsageRow.created_at)),
                    'YYYY-MM-DD"T"HH24',
                )
            rows = s.execute(
                select(
                    bucket.label("bucket"),
                    func.count(UsageRow.id),
                    func.coalesce(func.sum(case((is_hit, 1), else_=0)), 0),
                    func.coalesce(
                        func.sum(case((UsageRow.provider == "cache:semantic", 1), else_=0)), 0),
                    func.coalesce(func.sum(case((UsageRow.status != "ok", 1), else_=0)), 0),
                    func.coalesce(func.sum(tokens), 0),
                    func.coalesce(func.sum(UsageRow.cost_micros), 0),
                ).where(in_window).group_by(literal_column("bucket"))
            ).all()
            avg_hit, avg_miss, avg_all = s.execute(
                select(
                    func.avg(case((is_hit, UsageRow.latency_ms))),
                    func.avg(case((and_(~is_hit, UsageRow.status == "ok"), UsageRow.latency_ms))),
                    func.avg(UsageRow.latency_ms),
                ).where(in_window)
            ).one()
            by_provider = s.execute(
                select(UsageRow.provider, func.count(UsageRow.id)).where(in_window)
                .group_by(UsageRow.provider).order_by(func.count(UsageRow.id).desc())
            ).all()
            top = s.execute(
                select(
                    UsageRow.tenant_id,
                    func.count(UsageRow.id),
                    func.coalesce(func.sum(tokens), 0),
                    func.coalesce(func.sum(UsageRow.cost_micros), 0),
                ).where(in_window).group_by(UsageRow.tenant_id)
                .order_by(func.count(UsageRow.id).desc()).limit(5)
            ).all()
        by_key = {r[0]: r[1:] for r in rows}
        series = []
        for i in range(hours):
            moment = start + timedelta(hours=i)
            n, hits, sem, errs, tok, cost = by_key.get(moment.strftime("%Y-%m-%dT%H"), (0,) * 6)
            series.append({
                "hour": moment.strftime("%Y-%m-%dT%H:00:00Z"),
                "requests": int(n), "cache_hits": int(hits), "semantic_hits": int(sem),
                "errors": int(errs), "tokens": int(tok), "cost_usd": round(int(cost) / 1e6, 6),
            })
        requests = sum(p["requests"] for p in series)
        hits = sum(p["cache_hits"] for p in series)
        rnd = lambda v: None if v is None else round(float(v), 1)  # noqa: E731
        return {
            "hours": hours,
            "totals": {
                "requests": requests,
                "errors": sum(p["errors"] for p in series),
                "cache_hits": hits,
                "semantic_hits": sum(p["semantic_hits"] for p in series),
                "hit_rate": round(hits / requests, 3) if requests else 0.0,
                "tokens": sum(p["tokens"] for p in series),
                "cost_usd": round(sum(p["cost_usd"] for p in series), 6),
                "avg_latency_ms": rnd(avg_all),
                "avg_hit_ms": rnd(avg_hit),
                "avg_miss_ms": rnd(avg_miss),
            },
            "series": series,
            "by_provider": [{"provider": p, "requests": int(n)} for p, n in by_provider],
            "top_tenants": [
                {"tenant_id": t, "requests": int(n), "tokens": int(tok),
                 "cost_usd": round(int(cost) / 1e6, 6)}
                for t, n, tok, cost in top
            ],
        }

    def recent_requests(self, tenant_id=None, status=None, limit=50, before_id=None) -> list[dict]:
        query = select(UsageRow).order_by(UsageRow.id.desc()).limit(limit)
        if tenant_id:
            query = query.where(UsageRow.tenant_id == tenant_id)
        if status == "ok":
            query = query.where(UsageRow.status == "ok")
        elif status == "error":
            query = query.where(UsageRow.status != "ok")
        if before_id:
            query = query.where(UsageRow.id < before_id)
        with self._sf() as s:
            return [_usage_view(row) for row in s.execute(query).scalars().all()]