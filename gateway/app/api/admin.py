from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.auth import require_admin
from app.core.errors import ApiError
from app.core.tenants import DEFAULT_MODELS, TenantExists, TenantNotFound

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class TenantCreate(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,39}$")
    name: str = Field(min_length=1, max_length=100)
    allowed_models: list[str] = Field(default_factory=lambda: list(DEFAULT_MODELS))


@router.post("/tenants", status_code=201)
def create_tenant(body: TenantCreate, request: Request):
    try:
        t = request.app.state.store.create_tenant(body.id, body.name, body.allowed_models)
    except TenantExists:
        raise ApiError(409, "Tenant already exists.", "tenant_exists") from None
    return {"id": t.id, "name": t.name, "allowed_models": t.allowed_models}


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