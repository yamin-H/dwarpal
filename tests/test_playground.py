import re
from pathlib import Path

from fastapi.testclient import TestClient
from helpers import app_settings

from app.main import create_app

UI = Path(__file__).resolve().parents[1] / "ui" / "playground"


def make_client(enabled: bool) -> TestClient:
    return TestClient(create_app(app_settings(playground_enabled=enabled)))


def test_playground_is_off_by_default():
    client = make_client(False)
    for path in ("/playground", "/playground/app.js", "/playground/style.css"):
        assert client.get(path).status_code == 404


def test_playground_serves_all_three_files_when_enabled():
    client = make_client(True)
    page = client.get("/playground")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert "javascript" in client.get("/playground/app.js").headers["content-type"]
    assert client.get("/playground/style.css").headers["content-type"].startswith("text/css")


def test_playground_sends_strict_security_headers():
    r = make_client(True).get("/playground")
    csp = r.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"


def test_html_has_no_inline_script_or_style_and_only_local_assets():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert not re.findall(r"<script(?![^>]*\bsrc=)", html)   # every script has a src
    assert "<style" not in html and "style=" not in html and "onclick=" not in html
    urls = re.findall(r'(?:src|href)="([^"]+)"', html)
    assert urls and all(u.startswith("/playground/") for u in urls)


def test_script_avoids_dangerous_apis_and_never_persists_keys():
    js = (UI / "app.js").read_text(encoding="utf-8")
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write",
                   "eval(", "new Function", "localStorage", "sessionStorage", "indexedDB"):
        assert banned not in js, banned


def test_script_reads_the_headers_the_gateway_actually_sends():
    js = (UI / "app.js").read_text(encoding="utf-8")
    for header in ("x-cache", "x-cache-score", "x-cache-reason", "x-provider", "x-request-id"):
        assert f'"{header}"' in js
