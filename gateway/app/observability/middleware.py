import logging
import re
import time
import uuid

from app.observability.logging import request_id_var

log = logging.getLogger("dwarpal")
VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
QUIET_PATHS = {"/healthz", "/readyz", "/metrics"}


class RequestContextMiddleware:
    """Pure ASGI (not BaseHTTPMiddleware) so streaming responses are never buffered."""

    def __init__(self, app, metrics=None) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = ""
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                incoming = value.decode("latin-1")
                break
        rid = incoming if VALID_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = rid
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status = 500

        async def send_with_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", rid.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            path = scope.get("path", "")
            state = scope.get("state", {})
            if self.metrics is not None and path != "/metrics":
                try:
                    self.metrics.observe_http(status)
                except Exception:
                    log.exception("metrics failed")
            log.log(
                logging.DEBUG if path in QUIET_PATHS else logging.INFO,
                "request",
                extra={
                    "method": scope.get("method"),
                    "path": path,  # never the query string, headers or body
                    "status": status,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "tenant": state.get("tenant_id"),
                    "cache": state.get("cache"),
                },
            )
            request_id_var.reset(token)