import hmac

from fastapi import Request

from app.core.errors import ApiError


def bearer_token(request: Request) -> str | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    token = token.strip()
    return token if scheme.lower() == "bearer" and token else None


def require_admin(request: Request) -> None:
    admin_key = request.app.state.settings.admin_key
    if not admin_key:
        raise ApiError(403, "Admin API is disabled.", "admin_disabled", "permission_error")
    token = bearer_token(request)
    if token is None or not hmac.compare_digest(token, admin_key):
        raise ApiError(401, "Invalid admin key.", "invalid_admin_key", "authentication_error")