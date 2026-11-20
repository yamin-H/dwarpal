from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

UI_DIR = Path(__file__).resolve().parents[3] / "ui" / "console"

FILES = {
    "app.js": "text/javascript", "lib.js": "text/javascript", "overview.js": "text/javascript",
    "tenants.js": "text/javascript", "playground.js": "text/javascript",
    "activity.js": "text/javascript", "system.js": "text/javascript",
    "selftest.js": "text/javascript", "style.css": "text/css",
}

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

router = APIRouter(include_in_schema=False)


def _serve(name: str, media_type: str) -> FileResponse:
    path = UI_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type=media_type, headers=SECURITY_HEADERS)


@router.get("/console")
def console_page() -> FileResponse:
    return _serve("index.html", "text/html")


@router.get("/console/{name}")
def console_asset(name: str) -> FileResponse:
    if name not in FILES:  # a fixed allow-list: no path is ever built from user input
        raise HTTPException(status_code=404)
    return _serve(name, FILES[name])
