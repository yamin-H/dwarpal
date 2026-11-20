"""Render docs/benchmark-report.md from bench/results/*.json.

Sections without data say so. Nothing is estimated or invented.

    python bench/make_report.py --hardware "Ryzen 5 5600, 16 GB RAM"
"""
import argparse
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "bench" / "results"
FILES = {"embeddings": "embeddings.json", "load-kong": "load-kong.json",
         "load-direct": "load-direct.json", "drill": "drill.json"}

REPRODUCE = """```bash
docker compose up -d --build
make bench-embeddings                                   # model comparison
make load KEY=<key> LABEL=kong                          # latency through Kong
make load KEY=<key> BASE=http://localhost:8001 LABEL=direct
make drill KEY=<key>                                    # provider outage drill
make report HARDWARE="<your CPU and RAM>"
```"""

LIMITS = """- Load tests use the mock provider with an artificial delay. They measure the gateway and the
  cache, not real LLM latency or quality.
- Client and server share one machine, so absolute numbers depend on that machine.
- The load test uses exact-match caching only. The embedding cost of a semantic lookup is
  shown by the encode time per query in the model table.
- The labeled pair set is small. A threshold with zero wrong hits on it is not proof of safety.
- The outage drill uses a synthetic provider that fails fast. Real providers also fail slowly,
  and the current provider timeout is 60 s.
- Streamed token counts are word-count estimates, so streamed cost is undercounted."""


def fmt(value, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:g}{suffix}"
    return f"{value}{suffix}"


def _clean(text: str) -> str:
    return str(text).replace("|", "/")


def _table(headers: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return out


def render_embeddings(data: dict | None) -> str:
    if not data:
        return "_Not run yet. Run `make bench-embeddings`._"
    ok = [m for m in data["models"] if "error" not in m]
    intro = f"{data['pairs']} labeled pairs"
    if ok:
        intro += f" ({ok[0]['pairs_same']} paraphrases, {ok[0]['pairs_different']} near-misses)"
    rows = []
    for m in data["models"]:
        name = _clean(m["model"])
        if "error" in m:
            rows.append([name, f"failed: {_clean(m['error'])}", "-", "-", "-", "-"])
            continue
        t = m["recommended_threshold"]
        rows.append([
            name, m["dim"], fmt(m["avg_encode_ms"]), fmt(m["margin"]),
            "none (cannot separate)" if t is None else f"{t:g}",
            "-" if t is None else f"{m['hit_rate_at_threshold']:.0%}",
        ])
    lines = [
        intro + ". This is a small sample, so treat the numbers as indicative.", "",
        *_table(["Model", "Dim", "Encode ms/query", "Margin", "Recommended threshold",
                 "Hit rate there"], rows),
        "",
        "Margin is the lowest similarity of a true paraphrase minus the highest similarity of a "
        "near-miss. Positive means some threshold separates them perfectly on this data. "
        "The recommended threshold allows zero wrong hits.",
    ]
    return "\n".join(lines)


def _load_section(title: str, data: dict) -> list[str]:
    s, c = data["summary"], data.get("config", {})
    lines = [
        f"**{title}**: {s['requests']} requests, concurrency {c.get('concurrency', '?')}, "
        f"{fmt(s['rps'])} req/s, hit ratio {s['hit_ratio']:.0%}, errors {s['errors']}", "",
        *_table(["Cache result", "Requests", "p50 ms", "p95 ms", "p99 ms"],
                [[k, r["count"], r["p50_ms"], r["p95_ms"], r["p99_ms"]]
                 for k, r in s["by_cache"].items()]),
    ]
    if s["ttft_ms_by_cache"]:
        lines += ["", "Time to first token (streamed requests):", "",
                  *_table(["Cache result", "Requests", "p50 ms", "p95 ms"],
                          [[k, r["count"], r["p50_ms"], r["p95_ms"]]
                           for k, r in s["ttft_ms_by_cache"].items()])]
    if s["errors"]:
        lines += ["", f"Status counts: {s['status_counts']}"]
    return lines


def render_load(kong: dict | None, direct: dict | None) -> str:
    if not kong and not direct:
        return "_Not run yet. Run `make load`._"
    lines: list[str] = []
    for title, data in (("Through Kong", kong), ("Direct to the gateway", direct)):
        if data:
            lines += _load_section(title, data) + [""]
    if kong and direct:
        rows = []
        for label, k in kong["summary"]["by_cache"].items():
            d = direct["summary"]["by_cache"].get(label)
            if d:
                rows.append([label, fmt(d["p50_ms"]), fmt(k["p50_ms"]),
                             fmt(round(k["p50_ms"] - d["p50_ms"], 1))])
        if rows:
            lines += ["Kong overhead at p50 (indicative: two separate runs):", "",
                      *_table(["Cache result", "Direct p50 ms", "Via Kong p50 ms", "Difference ms"],
                              rows)]
    return "\n".join(lines).rstrip()


def render_drill(data: dict | None) -> str:
    if not data:
        return "_Not run yet. Run `make drill`._"
    s, c = data["summary"], data.get("config", {})
    served = ", ".join(f"{k}: {v}" for k, v in s["served_by"].items()) or "-"
    size = s["bucket_seconds"]
    timeline = [[f"{b['t']}-{b['t'] + size} s", b["requests"], b["ok"], b["errors"],
                 ", ".join(f"{k}: {v}" for k, v in b["served_by"].items()) or "-"]
                for b in s["timeline"]]
    lines = [
        f"Model `{c.get('model', '?')}` with a failing primary provider: {s['requests']} requests "
        f"over {c.get('duration', '?')} s.", "",
        *_table(["Metric", "Value"], [
            ["Requests answered (HTTP 200)", f"{s['ok']} of {s['requests']} ({s['success_rate']:.1%})"],
            ["Served by", served],
            ["Calls that reached the failing provider", s["failing_calls"]],
            ["Requests that never touched it", s["calls_avoided"]],
            ["Times the circuit opened", s["circuit_opened"]],
            ["p95 latency of answered requests", fmt(s["p95_ms"], " ms")],
        ]),
        "", f"Timeline ({size} s buckets):", "",
        *_table(["Window", "Requests", "OK", "Errors", "Served by"], timeline),
    ]
    return "\n".join(lines)


def build_report(results: dict, hardware: str, commit: str, generated_at: str) -> str:
    return "\n".join([
        "# Benchmark report", "",
        "_Generated by `bench/make_report.py`. Every number comes from `bench/results/*.json`. "
        "Sections without data say so._", "",
        "## Environment", "",
        f"- Date (UTC): {generated_at}",
        f"- Commit: {commit}",
        f"- Python: {platform.python_version()}",
        f"- Hardware: {hardware}", "",
        "## Embedding models and cache thresholds", "",
        render_embeddings(results.get("embeddings")), "",
        "## Load test: latency by cache result", "",
        render_load(results.get("load-kong"), results.get("load-direct")), "",
        "## Provider outage drill", "",
        render_drill(results.get("drill")), "",
        "## How to reproduce", "", REPRODUCE, "",
        "## Limits of these results", "", LIMITS, "",
    ])


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hardware", default="not recorded")
    ap.add_argument("--out", default=str(ROOT / "docs" / "benchmark-report.md"))
    args = ap.parse_args()
    results = {}
    for key, name in FILES.items():
        path = RESULTS / name
        results[key] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_report(results, args.hardware, git_commit(), stamp), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
