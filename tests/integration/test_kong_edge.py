import os

import httpx
import pytest

BASE = os.getenv("DWARPAL_E2E_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="set DWARPAL_E2E_URL to run edge tests")
BODY = {"model": "auto", "messages": [{"role": "user", "content": "hi"}]}


def test_health_is_public():
    assert httpx.get(f"{BASE}/healthz").status_code == 200


def test_admin_is_not_routed_at_the_edge():
    r = httpx.post(
        f"{BASE}/admin/tenants",
        json={"id": "abc", "name": "x"},
        headers={"Authorization": "Bearer anything"},
    )
    assert r.status_code == 404


def test_docs_and_openapi_are_not_exposed():
    assert httpx.get(f"{BASE}/docs").status_code == 404
    assert httpx.get(f"{BASE}/openapi.json").status_code == 404


def test_v1_requires_a_key_through_kong():
    assert httpx.post(f"{BASE}/v1/chat/completions", json=BODY).status_code == 401


def test_oversized_payload_is_rejected_by_kong():
    big = {"model": "auto", "messages": [{"role": "user", "content": "x" * 2_000_000}]}
    assert httpx.post(f"{BASE}/v1/chat/completions", json=big).status_code == 413