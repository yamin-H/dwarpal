"""Provider outage drill: steady traffic to a model whose provider is failing.

Shows that clients keep getting answers (served by the fallback) while the circuit breaker
stops the failing provider from being hammered.

Prerequisites:
  * DWARPAL_ROUTING_CONFIG points at a config with a chain for the model
    (config/routing.example.json has "mock-fail": ["mock-echo"]).
  * The tenant is allowed to call that model, and nothing else is sending traffic meanwhile.
  * /metrics is reachable (use the localhost-only port: http://localhost:8001/metrics).

    python bench/outage_drill.py --key dk_live_... --duration 75 --rate 1

Through Kong the rate limit is 120/min, so keep --rate at 2 or less, or use --base-url
http://localhost:8001 for a faster drill.
"""
import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

import httpx
from loadgen import percentile
from prometheus_client.parser import text_string_to_metric_families

BUCKET_SECONDS = 5


def parse_metrics(text: str) -> list[tuple[str, dict, float]]:
    samples = []
    for family in text_string_to_metric_families(text):
        for s in family.samples:
            samples.append((s.name, dict(s.labels), s.value))
    return samples


def metric_value(samples, name: str, **labels) -> float:
    return sum(
        value for n, lbl, value in samples
        if n == name and all(lbl.get(k) == v for k, v in labels.items())
    )


def bucket_timeline(records: list[dict], bucket_seconds: int = BUCKET_SECONDS) -> list[dict]:
    buckets: dict[int, dict] = {}
    for rec in records:
        b = buckets.setdefault(int(rec["t"] // bucket_seconds),
                               {"requests": 0, "ok": 0, "served_by": Counter()})
        b["requests"] += 1
        if rec["status"] == 200:
            b["ok"] += 1
            b["served_by"][rec["provider"] or "unknown"] += 1
    return [
        {"t": index * bucket_seconds, "requests": b["requests"], "ok": b["ok"],
         "errors": b["requests"] - b["ok"], "served_by": dict(b["served_by"])}
        for index, b in sorted(buckets.items())
    ]


def summarize_drill(records, before, after, failing_provider: str, model: str) -> dict:
    total = len(records)
    ok = [r for r in records if r["status"] == 200]
    failing_calls = int(
        metric_value(after, "dwarpal_provider_calls_total",
                     provider=failing_provider, outcome="failure")
        - metric_value(before, "dwarpal_provider_calls_total",
                       provider=failing_provider, outcome="failure"))
    opened = int(
        metric_value(after, "dwarpal_circuit_opened_total", model=model)
        - metric_value(before, "dwarpal_circuit_opened_total", model=model))
    p95 = percentile([r["latency"] * 1000 for r in ok], 95)
    return {
        "requests": total,
        "ok": len(ok),
        "success_rate": round(len(ok) / total, 4) if total else 0.0,
        "served_by": dict(Counter(r["provider"] or "unknown" for r in ok)),
        "status_counts": dict(Counter(str(r["status"]) for r in records)),
        "failing_provider": failing_provider,
        "failing_calls": failing_calls,
        "calls_avoided": max(total - failing_calls, 0),
        "circuit_opened": opened,
        "p95_ms": None if p95 is None else round(p95, 1),
        "bucket_seconds": BUCKET_SECONDS,
        "timeline": bucket_timeline(records),
    }


async def fire(client, base: str, headers: dict, body: dict, start: float) -> dict:
    sent = time.perf_counter()
    try:
        r = await client.post(f"{base}/v1/chat/completions", json=body, headers=headers)
        status, provider = r.status_code, r.headers.get("x-provider")
    except httpx.HTTPError:
        status, provider = 0, None
    rec = {"t": sent - start, "status": status, "provider": provider,
           "latency": time.perf_counter() - sent}
    print(f"t={rec['t']:6.1f}s  status={status}  served_by={provider or '-'}  "
          f"{rec['latency'] * 1000:.0f} ms", flush=True)
    return rec


async def run_drill(client, base: str, headers: dict, scrape, model: str,
                    failing_provider: str, duration: float, rate: float) -> dict:
    headers = {**headers, "X-Dwarpal-Cache": "bypass"}
    body = {"model": model, "messages": [{"role": "user", "content": "outage drill ping"}]}
    before = parse_metrics(await scrape())
    start = time.perf_counter()
    tasks = []
    for i in range(max(1, int(duration * rate))):
        wait = start + i / rate - time.perf_counter()
        if wait > 0:
            await asyncio.sleep(wait)
        tasks.append(asyncio.create_task(fire(client, base, headers, body, start)))
    records = await asyncio.gather(*tasks)
    after = parse_metrics(await scrape())
    return summarize_drill(records, before, after, failing_provider, model)


def describe(s: dict) -> list[str]:
    lines = [
        "",
        f"Answered with HTTP 200: {s['ok']} of {s['requests']} ({s['success_rate']:.1%})",
        f"Served by: {s['served_by']}",
        f"Calls that reached the failing provider ({s['failing_provider']}): {s['failing_calls']}",
        f"Requests that never touched it: {s['calls_avoided']}",
        f"Times the circuit opened: {s['circuit_opened']}",
    ]
    if s["failing_calls"] == 0:
        lines.append("WARNING: no call reached the failing provider. Is the model configured with "
                     "a fallback chain, and is the failing provider label right?")
    if s["ok"] < s["requests"]:
        lines.append(f"WARNING: some requests failed: {s['status_counts']}")
    return lines


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--metrics-url", default="http://localhost:8001/metrics")
    ap.add_argument("--key", required=True)
    ap.add_argument("--model", default="mock-fail")
    ap.add_argument("--failing-provider", default="mock-fail",
                    help="provider label in the metrics, e.g. litellm:gpt-4o-mini")
    ap.add_argument("--duration", type=float, default=75)
    ap.add_argument("--rate", type=float, default=1)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    async def go() -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            async def scrape() -> str:
                r = await client.get(args.metrics_url, timeout=5)
                r.raise_for_status()
                return r.text

            headers = {"Authorization": f"Bearer {args.key}"}
            return await run_drill(client, args.base_url, headers, scrape, args.model,
                                   args.failing_provider, args.duration, args.rate)

    summary = asyncio.run(go())
    print("\n".join(describe(summary)))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        config = {"base_url": args.base_url, "model": args.model,
                  "failing_provider": args.failing_provider,
                  "duration": args.duration, "rate": args.rate}
        out.write_text(json.dumps({"label": "drill", "config": config, "summary": summary},
                                  indent=2), encoding="utf-8")
        print(f"\nWrote {out}")
    return 0 if summary["success_rate"] == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
