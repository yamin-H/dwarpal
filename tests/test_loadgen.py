import argparse
import asyncio
import json
from collections import Counter

import httpx
import pytest
from fastapi.testclient import TestClient
from helpers import app_settings, create_tenant
from loadgen import (QUESTIONS, Sample, build_workload, percentile, public_config,
                     render_markdown, run_workload, summarize)

from app.api.schemas import ChatRequest, Message
from app.cache.exact import MemoryCache
from app.cache.policy import cache_decision
from app.main import create_app


def test_percentile():
    assert percentile([1, 2, 3, 4, 5], 50) == 3
    assert percentile([1, 2, 3, 4, 5], 0) == 1 and percentile([1, 2, 3, 4, 5], 100) == 5
    assert percentile([1, 2, 3, 4, 5], 95) == pytest.approx(4.8)
    assert percentile([7], 99) == 7 and percentile([], 50) is None


def test_workload_is_deterministic_and_sized():
    a = build_workload(50, 5, 0.3, seed=7, run_id="r1")
    assert a == build_workload(50, 5, 0.3, seed=7, run_id="r1")
    assert len(a) == 50 and len({w["text"] for w in a}) <= 5


def test_stream_ratio_extremes():
    assert not any(w["stream"] for w in build_workload(40, 5, 0.0, 1, "r"))
    assert all(w["stream"] for w in build_workload(40, 5, 1.0, 1, "r"))


def test_a_few_questions_dominate():
    counts = Counter(w["text"] for w in build_workload(2000, 10, 0.0, 3, "r"))
    ordered = [text for text, _ in counts.most_common()]
    assert counts[ordered[0]] > 3 * counts[ordered[-1]]


def test_workload_validation():
    with pytest.raises(ValueError):
        build_workload(0, 5, 0.3, 1, "r")
    with pytest.raises(ValueError):
        build_workload(10, 5, 1.5, 1, "r")


def test_all_questions_are_cacheable_by_policy():
    for q in QUESTIONS:
        req = ChatRequest(messages=[Message(role="user", content=f"{q} (variant 3) [ab12cd]")])
        assert cache_decision(req).cacheable, q


def test_summarize_groups_by_cache_and_counts_errors():
    samples = [
        Sample("MISS", 200, 0.300, 0.300, True),
        Sample("MISS", 200, 0.500, None, False),
        Sample("HIT", 200, 0.010, 0.005, True),
        Sample("HIT", 200, 0.020, None, False),
        Sample("HIT", 429, 0.001, None, False),
        Sample(None, 0, 1.0, None, False, "ConnectError"),
    ]
    s = summarize(samples, wall_seconds=2.0)
    assert (s["requests"], s["ok"], s["errors"]) == (6, 4, 2)
    assert s["status_counts"] == {"200": 4, "429": 1, "0": 1}
    assert s["by_cache"]["MISS"]["p50_ms"] == 400.0
    assert s["by_cache"]["HIT"]["count"] == 2
    assert s["hit_ratio"] == 0.5 and s["rps"] == 3.0
    assert s["ttft_ms_by_cache"]["HIT"]["count"] == 1 and s["ttft_ms_by_cache"]["MISS"]["count"] == 1


def test_markdown_contains_the_table():
    result = {"summary": summarize([Sample("HIT", 200, 0.01, None, False)], 1.0)}
    text = render_markdown(result)
    assert "| HIT | 1 |" in text and "hit ratio 100%" in text


def test_public_config_never_contains_the_key():
    args = argparse.Namespace(base_url="http://x", model="auto", requests=1, concurrency=1,
                              unique=1, stream_ratio=0.0, seed=1, key="dk_live_secret")
    assert "dk_live_secret" not in json.dumps(public_config(args))


def test_workload_runs_against_an_in_process_gateway():
    app = create_app(app_settings(), cache=MemoryCache())
    key = create_tenant(TestClient(app))["Authorization"].split()[1]
    workload = build_workload(30, 3, 0.5, seed=1, run_id="t1")

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await run_workload(client, "http://test", key, workload, "auto", concurrency=1)

    samples, wall = asyncio.run(scenario())
    s = summarize(samples, wall)
    assert s["ok"] == 30 and s["errors"] == 0
    assert s["hit_ratio"] >= 0.85          # at most 3 distinct questions can miss
    assert set(s["by_cache"]) == {"HIT", "MISS"}
