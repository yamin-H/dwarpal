from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator

from app.core.auth import require_admin
from app.core.errors import ApiError
from app.core.tenants import DEFAULT_MODELS, Tenant, TenantExists, TenantNotFound

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