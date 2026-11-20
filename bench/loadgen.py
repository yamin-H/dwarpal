"""Closed-loop load test: latency and time to first token, split by cache result.

    python bench/loadgen.py --key dk_live_... --requests 300 --concurrency 20 --label kong

Setup for meaningful numbers:
  * DWARPAL_MOCK_DELAY_MS=300 so a cache miss costs something like a real LLM call.
  * Semantic cache OFF: every run uses fresh question text, so all hits are exact-match.
  * Through Kong the rate limit (120/min) returns 429s. Temporarily raise `minute` in
    kong/kong.yml for the run (do not commit it), or test the gateway directly on :8001.
"""
import argparse
import asyncio
import json
import math
import random
import sys
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import httpx

QUESTIONS = [
    "How much zakat do I have to pay on my savings",
    "What are the five daily prayers",
    "How do I reset my app password",
    "How can I download a song for offline listening",
    "How do I pay my credit card bill",
    "What are the benefits of fasting",
    "How do I update my phone number in the app",
    "How do I perform wudu step by step",
    "zakat koto taka dite hoy",
    "fajr namaz koy rakat",
    "password bhule gele ki korbo",
    "gaan offline kivabe shunbo",
    "card bill kivabe pay korbo",
    "ifter er dua ki",
    "যাকাত কত টাকা দিতে হয়",
    "ফজরের নামাজ কত রাকাত",
    "পাসওয়ার্ড ভুলে গেলে কী করব",
    "গান অফলাইনে কীভাবে শুনব",
    "ক্রেডিট কার্ডের বিল কীভাবে দেব",
    "ইফতারের দোয়া কী",
    "অজু করার নিয়ম কী",
    "রোজার নিয়ত কী",
]


@dataclass
class Sample:
    cache: str | None
    status: int
    latency: float
    ttft: float | None
    stream: bool
    error: str | None = None


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return ordered[int(k)]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def build_workload(n: int, unique: int, stream_ratio: float, seed: int, run_id: str) -> list[dict]:
    """Zipf-like repetition: a few questions are asked often, most rarely. Deterministic per seed."""
    if n < 1 or unique < 1:
        raise ValueError("requests and unique must both be >= 1")
    if not 0 <= stream_ratio <= 1:
        raise ValueError("stream ratio must be between 0 and 1")
    rng = random.Random(seed)
    pool = [f"{QUESTIONS[i % len(QUESTIONS)]} (variant {i}) [{run_id}]" for i in range(unique)]
    weights = [1 / (rank + 1) for rank in range(unique)]
    picks = rng.choices(range(unique), weights=weights, k=n)
    return [{"text": pool[i], "stream": rng.random() < stream_ratio} for i in picks]


async def one(client, base: str, headers: dict, item: dict, model: str) -> Sample:
    body = {"model": model, "stream": item["stream"],
            "messages": [{"role": "user", "content": item["text"]}]}
    url = f"{base}/v1/chat/completions"
    start = time.perf_counter()
    try:
        if item["stream"]:
            ttft = None
            async with client.stream("POST", url, json=body, headers=headers) as r:
                cache = r.headers.get("x-cache")
                if r.status_code != 200:
                    await r.aread()
                    return Sample(cache, r.status_code, time.perf_counter() - start, None, True)
                async for line in r.aiter_lines():
                    if ttft is None and line.startswith("data: ") and '"content"' in line:
                        ttft = time.perf_counter() - start
            return Sample(cache, 200, time.perf_counter() - start, ttft, True)
        r = await client.post(url, json=body, headers=headers)
        return Sample(r.headers.get("x-cache"), r.status_code, time.perf_counter() - start,
                      None, False)
    except httpx.HTTPError as exc:
        return Sample(None, 0, time.perf_counter() - start, None, item["stream"],
                      type(exc).__name__)


async def run_workload(client, base: str, key: str, workload: list[dict], model: str,
                       concurrency: int) -> tuple[list[Sample], float]:
    headers = {"Authorization": f"Bearer {key}"}
    queue: asyncio.Queue = asyncio.Queue()
    for item in workload:
        queue.put_nowait(item)
    samples: list[Sample] = []

    async def worker() -> None:
        while True:
            try:
                item = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            samples.append(await one(client, base, headers, item, model))

    start = time.perf_counter()
    await asyncio.gather(*(worker() for _ in range(max(1, concurrency))))
    return samples, time.perf_counter() - start


def _stats(values_ms: list[float]) -> dict:
    return {
        "count": len(values_ms),
        "p50_ms": round(percentile(values_ms, 50), 1),
        "p95_ms": round(percentile(values_ms, 95), 1),
        "p99_ms": round(percentile(values_ms, 99), 1),
        "mean_ms": round(sum(values_ms) / len(values_ms), 1),
    }


def summarize(samples: list[Sample], wall_seconds: float) -> dict:
    ok = [s for s in samples if s.status == 200]
    by_cache: dict[str, list[float]] = defaultdict(list)
    ttft_by_cache: dict[str, list[float]] = defaultdict(list)
    for s in ok:
        label = s.cache or "NONE"
        by_cache[label].append(s.latency * 1000)
        if s.stream and s.ttft is not None:
            ttft_by_cache[label].append(s.ttft * 1000)
    hits = sum(1 for s in ok if (s.cache or "").startswith("HIT"))
    return {
        "requests": len(samples),
        "ok": len(ok),
        "errors": len(samples) - len(ok),
        "status_counts": dict(Counter(str(s.status) for s in samples)),
        "wall_seconds": round(wall_seconds, 2),
        "rps": round(len(samples) / wall_seconds, 1) if wall_seconds > 0 else None,
        "hit_ratio": round(hits / len(ok), 3) if ok else 0.0,
        "by_cache": {k: _stats(v) for k, v in sorted(by_cache.items())},
        "ttft_ms_by_cache": {k: _stats(v) for k, v in sorted(ttft_by_cache.items())},
    }


def render_markdown(result: dict) -> str:
    s = result["summary"]
    lines = [
        f"{s['requests']} requests, {s['ok']} ok, {s['errors']} errors, {s['rps']} req/s, "
        f"hit ratio {s['hit_ratio']:.0%}",
        "",
        "| Cache result | Requests | p50 ms | p95 ms | p99 ms |",
        "|---|---|---|---|---|",
    ]
    for label, r in s["by_cache"].items():
        lines.append(f"| {label} | {r['count']} | {r['p50_ms']} | {r['p95_ms']} | {r['p99_ms']} |")
    if s["ttft_ms_by_cache"]:
        lines += ["", "Time to first token (streamed requests):", "",
                  "| Cache result | Requests | p50 ms | p95 ms |", "|---|---|---|---|"]
        for label, r in s["ttft_ms_by_cache"].items():
            lines.append(f"| {label} | {r['count']} | {r['p50_ms']} | {r['p95_ms']} |")
    if s["errors"]:
        lines += ["", f"Status counts: {s['status_counts']}"]
    return "\n".join(lines)


def public_config(args) -> dict:
    """Everything worth recording about a run. Never includes the API key."""
    return {
        "base_url": args.base_url, "model": args.model, "requests": args.requests,
        "concurrency": args.concurrency, "unique_questions": args.unique,
        "stream_ratio": args.stream_ratio, "seed": args.seed,
    }


async def run_all(args) -> dict:
    run_id = uuid.uuid4().hex[:6]
    workload = build_workload(args.requests, args.unique, args.stream_ratio, args.seed, run_id)
    limits = httpx.Limits(max_connections=args.concurrency,
                          max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(timeout=args.timeout, limits=limits) as client:
        samples, wall = await run_workload(
            client, args.base_url, args.key, workload, args.model, args.concurrency)
    return summarize(samples, wall)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--key", required=True)
    ap.add_argument("--model", default="auto")
    ap.add_argument("--requests", type=int, default=300)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--unique", type=int, default=30, help="distinct questions in the pool")
    ap.add_argument("--stream-ratio", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    result = {"label": args.label, "config": public_config(args),
              "summary": asyncio.run(run_all(args))}
    print(render_markdown(result))
    if result["summary"]["status_counts"].get("429"):
        print("\nWARNING: 429 responses. Kong's rate limit (or a tenant budget) is throttling "
              "this test, so the latency numbers are not representative.")
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {out}")
    return 0 if result["summary"]["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
