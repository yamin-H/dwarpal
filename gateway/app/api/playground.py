from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

UI_DIR = Path(__file__).resolve().parents[3] / "ui" / "playground"

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

router = APIRouter(include_in_schema=False)


def _serve(name: str, media_type: str) -> FileResponse:
    return FileResponse(UI_DIR / name, media_type=media_type, headers=SECURITY_HEADERS)


@router.get("/playground")
def playground_page() -> FileResponse:
    return _serve("index.html", "text/html")


@router.get("/playground/app.js")
def playground_script() -> FileResponse:
    return _serve("app.js", "text/javascript")


@router.get("/playground/style.css")
def playground_style() -> FileResponse:
    return _serve("style.css", "text/css")