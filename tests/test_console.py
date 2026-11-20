import re
from pathlib import Path

from fastapi.testclient import TestClient
from helpers import app_settings

from app.api.console import FILES
from app.main import create_app

UI = Path(__file__).resolve().parents[1] / "ui" / "console"
ADMIN_PATH = re.compile(r"[\"'`](/admin/[^\"'`\s?]*)")
BANNED = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(",
          "new Function", "localStorage", "indexedDB", "srcdoc")


def make(enabled: bool) -> TestClient:
    return TestClient(create_app(app_settings(console_enabled=enabled)))


def js_files():
    return sorted(UI.glob("*.js"))


def test_console_is_off_by_default():
    c = make(False)
    for path in ("/console", "/console/app.js", "/console/style.css"):
        assert c.get(path).status_code == 404


def test_every_shipped_file_is_served_when_enabled():
    c = make(True)
    page = c.get("/console")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    for name in FILES:
        if (UI / name).is_file():
            assert c.get(f"/console/{name}").status_code == 200, name


def test_only_allow_listed_files_are_served():
    c = make(True)
    for path in ("/console/secret.txt", "/console/index.html", "/console/..%2Fapp.py",
                 "/console/%2e%2e/config.py"):
        assert c.get(path).status_code == 404, path


def test_security_headers():
    r = make(True).get("/console")
    csp = r.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"


def test_html_has_no_inline_script_or_style():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert not re.findall(r"<script(?![^>]*\bsrc=)", html)
    assert "<style" not in html and "style=" not in html and "onclick=" not in html
    assert all(u.startswith("/console/") for u in re.findall(r'(?:src|href)="([^"]+)"', html))


def test_js_avoids_dangerous_apis():
    for path in js_files():
        text = path.read_text(encoding="utf-8")
        for banned in BANNED:
            assert banned not in text, f"{path.name} uses {banned}"
        assert "setAttribute(\"style\"" not in text and ".cssText" not in text, path.name
        if path.name != "lib.js":
            assert "sessionStorage" not in text, f"{path.name} touches sessionStorage"


def test_all_imports_resolve_to_served_files():
    for path in js_files():
        for name in re.findall(r'from "\./([\w-]+\.js)"', path.read_text(encoding="utf-8")):
            assert name in FILES and (UI / name).is_file(), f"{path.name} imports {name}"


def test_every_admin_endpoint_the_console_calls_exists():
    c = make(False)
    paths = set()
    for path in js_files():
        for raw in ADMIN_PATH.findall(path.read_text(encoding="utf-8")):
            paths.add(re.sub(r"\$\{[^}]*\}", "x", raw))
    assert paths
    for path in sorted(paths):
        statuses = {c.request(m, path).status_code for m in ("GET", "POST", "PATCH", "DELETE")}
        assert 401 in statuses, f"{path} is not an admin endpoint ({statuses})"
