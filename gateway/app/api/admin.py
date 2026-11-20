import os

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, model_validator

from app.core.auth import require_admin
from app.core.errors import ApiError
from app.core.tenants import (
    DEFAULT_MODELS, KeyNotFound, KeyNotRotatable, Tenant, TenantExists, TenantNotFound,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

NON_NULLABLE = ("name", "allowed_models", "cache_enabled", "allow_fallback", "active")


def usd_to_micros(usd: float | None) -> int | None:
    return None if usd is None else round(usd * 1_000_000)


def tenant_view(t: Tenant) -> dict:
    budget = t.monthly_cost_budget_micros
    return {
        "id": t.id,
        "name": t.name,
        "active": t.active,
        "allowed_models": t.allowed_models,
        "cache_enabled": t.cache_enabled,
        "allow_fallback": t.allow_fallback,
        "semantic_threshold": t.semantic_threshold,
        "monthly_token_budget": t.monthly_token_budget,
        "monthly_cost_budget_usd": None if budget is None else budget / 1_000_000,
    }


class TenantCreate(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,39}$")
    name: str = Field(min_length=1, max_length=100)
    allowed_models: list[str] = Field(default_factory=lambda: list(DEFAULT_MODELS))
    cache_enabled: bool = True
    allow_fallback: bool = True
    semantic_threshold: float | None = Field(default=None, ge=0.5, le=1.0)
    monthly_token_budget: int | None = Field(default=None, gt=0)
    monthly_cost_budget_usd: float | None = Field(default=None, gt=0)


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    allowed_models: list[str] | None = None
    active: bool | None = None
    cache_enabled: bool | None = None
    allow_fallback: bool | None = None
    semantic_threshold: float | None = Field(default=None, ge=0.5, le=1.0)
    monthly_token_budget: int | None = Field(default=None, gt=0)
    monthly_cost_budget_usd: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _only_limits_may_be_cleared(self):
        for name in NON_NULLABLE:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"'{name}' cannot be null")
        return self


@router.post("/tenants", status_code=201)
def create_tenant(body: TenantCreate, request: Request):
    options = body.model_dump(exclude={"id", "name", "allowed_models"})
    options["monthly_cost_budget_micros"] = usd_to_micros(options.pop("monthly_cost_budget_usd"))
    try:
        t = request.app.state.store.create_tenant(
            body.id, body.name, body.allowed_models, **options
        )
    except TenantExists:
        raise ApiError(409, "Tenant already exists.", "tenant_exists") from None
    return tenant_view(t)


@router.get("/tenants/{tenant_id}")
def get_tenant(tenant_id: str, request: Request):
    try:
        return tenant_view(request.app.state.store.get_tenant(tenant_id))
    except TenantNotFound:
        raise ApiError(404, "Tenant not found.", "tenant_not_found") from None


@router.patch("/tenants/{tenant_id}")
def update_tenant(tenant_id: str, body: TenantUpdate, request: Request):
    changes = body.model_dump(exclude_unset=True)  # explicit null clears a limit
    if "monthly_cost_budget_usd" in changes:
        changes["monthly_cost_budget_micros"] = usd_to_micros(changes.pop("monthly_cost_budget_usd"))
    if not changes:
        raise ApiError(400, "No fields to update.", "empty_update")
    try:
        return tenant_view(request.app.state.store.update_tenant(tenant_id, **changes))
    except TenantNotFound:
        raise ApiError(404, "Tenant not found.", "tenant_not_found") from None


@router.post("/tenants/{tenant_id}/keys", status_code=201)
def issue_key(tenant_id: str, request: Request):
    try:
        raw, rec = request.app.state.store.issue_key(tenant_id)
    except TenantNotFound:
        raise ApiError(404, "Tenant not found.", "tenant_not_found") from None
    return {
        "key_id": rec.id,
        "api_key": raw,
        "prefix": rec.prefix,
        "note": "Store this key now. It will not be shown again.",
    }


@router.delete("/keys/{key_id}")
def revoke_key(key_id: str, request: Request):
    if not request.app.state.store.revoke_key(key_id):
        raise ApiError(404, "Key not found.", "key_not_found")
    return {"revoked": True}


@router.get("/tenants/{tenant_id}/usage")
def tenant_usage(tenant_id: str, request: Request):
    try:
        return request.app.state.store.usage_summary(tenant_id)
    except TenantNotFound:
        raise ApiError(404, "Tenant not found.", "tenant_not_found") from None


MAX_OVERLAP_SECONDS = 7 * 24 * 3600


class RotateRequest(BaseModel):
    overlap_seconds: int = Field(default=24 * 3600, ge=0, le=MAX_OVERLAP_SECONDS)


@router.post("/keys/{key_id}/rotate", status_code=201)
def rotate_key(key_id: str, request: Request, body: RotateRequest = RotateRequest()):
    try:
        raw, rec, expires = request.app.state.store.rotate_key(key_id, body.overlap_seconds)
    except KeyNotFound:
        raise ApiError(404, "Key not found.", "key_not_found") from None
    except KeyNotRotatable as exc:
        raise ApiError(409, f"Key cannot be rotated: {exc}.", "key_not_rotatable") from None
    return {
        "key_id": rec.id,
        "api_key": raw,
        "prefix": rec.prefix,
        "old_key_id": key_id,
        "old_key_expires_at": expires.isoformat(),
        "note": "Store this key now. The old key stops working at the time shown.",
    }


@router.get("/tenants/{tenant_id}/keys")
def list_keys(tenant_id: str, request: Request):
    try:
        return {"keys": request.app.state.store.list_keys(tenant_id)}
    except TenantNotFound:
        raise ApiError(404, "Tenant not found.", "tenant_not_found") from None


PROVIDER_KEY_NAMES = ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY")


@router.get("/tenants")
def list_tenants(request: Request):
    return {"tenants": [
        {**tenant_view(tenant), **stats}
        for tenant, stats in request.app.state.store.list_tenants()
    ]}


@router.get("/overview")
def overview(request: Request, hours: int = Query(24, ge=1, le=168)):
    return request.app.state.store.overview(hours)


@router.get("/requests")
def request_log(
    request: Request,
    tenant_id: str | None = Query(None, max_length=40),
    status: str | None = Query(None, pattern="^(ok|error)$"),
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(None, ge=1),
):
    rows = request.app.state.store.recent_requests(tenant_id, status, limit, before_id)
    return {"requests": rows, "next_before_id": rows[-1]["id"] if len(rows) == limit else None}


@router.get("/system")
async def system(request: Request):
    """Everything here is safe to show: booleans and names only, never keys or URLs."""
    st = request.app.state
    settings, semantic, route = st.settings, st.semantic, st.router
    return {
        "version": request.app.version,
        "environment": settings.app_env,
        "checks": {
            "database": await run_in_threadpool(st.store.ping),
            "redis": await st.cache.ping(),
            "qdrant": await semantic.ping(),
        },
        "cache": {
            "exact_enabled": st.cache.enabled,
            "semantic_enabled": semantic.enabled,
            "ttl_seconds": settings.cache_ttl_seconds,
            "semantic_threshold": getattr(semantic, "threshold", None),
            "embedder": settings.embedder if semantic.enabled else None,
            "embedding_model": settings.embedding_model if semantic.enabled else None,
        },
        "routing": {
            "chains": route.config.chains,
            "cooldown_seconds": route.config.cooldown_seconds,
            "failure_threshold": route.config.failure_threshold,
            "circuits": route.health.snapshot(),
        },
        "prices": st.prices.table(),
        "providers_configured": {name: bool(os.environ.get(name)) for name in PROVIDER_KEY_NAMES},
        "features": {
            "console": settings.console_enabled,
            "playground": settings.playground_enabled,
            "auto_migrate": settings.auto_migrate,
        },
    }


@router.delete("/tenants/{tenant_id}/cache")
async def purge_tenant_cache(tenant_id: str, request: Request):
    try:
        request.app.state.store.get_tenant(tenant_id)
    except TenantNotFound:
        raise ApiError(404, "Tenant not found.", "tenant_not_found") from None
    exact = await request.app.state.cache.purge_tenant(tenant_id)
    semantic = await request.app.state.semantic.purge_tenant(tenant_id)
    return {"exact_deleted": exact, "semantic_cleared": semantic}