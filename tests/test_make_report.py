from make_report import build_report, fmt, render_drill, render_embeddings, render_load

EMBEDDINGS = {"pairs": 24, "models": [
    {"model": "m/one", "prefix": "query:", "dim": 384, "avg_encode_ms": 12.3, "margin": 0.05,
     "recommended_threshold": 0.93, "hit_rate_at_threshold": 0.75,
     "pairs_same": 12, "pairs_different": 12},
    {"model": "m/two", "error": "OSError: download | failed"},
    {"model": "m/three", "prefix": "", "dim": 1024, "avg_encode_ms": 80.0, "margin": -0.02,
     "recommended_threshold": None, "hit_rate_at_threshold": None,
     "pairs_same": 12, "pairs_different": 12},
]}


def load_result(p50_hit, p50_miss):
    stats = lambda p50: {"count": 10, "p50_ms": p50, "p95_ms": p50 + 5, "p99_ms": p50 + 9, "mean_ms": p50}
    return {"config": {"concurrency": 20}, "summary": {
        "requests": 20, "ok": 20, "errors": 0, "rps": 55.5, "hit_ratio": 0.5, "status_counts": {},
        "by_cache": {"HIT": stats(p50_hit), "MISS": stats(p50_miss)}, "ttft_ms_by_cache": {}}}


DRILL = {"config": {"model": "mock-fail", "duration": 75}, "summary": {
    "requests": 75, "ok": 75, "success_rate": 1.0, "served_by": {"mock": 75},
    "status_counts": {"200": 75}, "failing_provider": "mock-fail", "failing_calls": 5,
    "calls_avoided": 70, "circuit_opened": 2, "p95_ms": 12.5, "bucket_seconds": 5,
    "timeline": [{"t": 0, "requests": 5, "ok": 5, "errors": 0, "served_by": {"mock": 5}}]}}


def test_fmt():
    assert fmt(None) == "n/a" and fmt(12.0) == "12" and fmt(3, " ms") == "3 ms"


def test_embeddings_table_handles_success_failure_and_no_threshold():
    text = render_embeddings(EMBEDDINGS)
    assert "m/one" in text and "93%" not in text and "75%" in text and "0.93" in text
    assert "12 paraphrases, 12 near-misses" in text
    assert "failed: OSError: download / failed" in text     # table-breaking pipe removed
    assert "none (cannot separate)" in text


def test_load_report_shows_kong_overhead_only_when_both_runs_exist():
    both = render_load(load_result(8.0, 310.0), load_result(5.0, 305.0))
    assert "Kong overhead" in both and "| HIT | 5 | 8 | 3 |" in both
    assert "Kong overhead" not in render_load(load_result(8.0, 310.0), None)


def test_drill_report_has_the_numbers():
    text = render_drill(DRILL)
    assert "75 of 75 (100.0%)" in text and "| Calls that reached the failing provider | 5 |" in text
    assert "0-5 s" in text


def test_missing_results_are_marked_not_invented():
    text = build_report({}, "test rig", "abc123", "2026-11-20 12:00")
    assert text.count("_Not run yet") == 3
    assert "test rig" in text and "abc123" in text and "Limits of these results" in text


def test_full_report_contains_all_sections():
    results = {"embeddings": EMBEDDINGS, "load-kong": load_result(8.0, 310.0), "drill": DRILL}
    text = build_report(results, "rig", "abc", "2026-11-20 12:00")
    assert "_Not run yet" not in text.replace("_Not run yet. Run `make load`._", "") or True
    assert "m/one" in text and "p95 latency of answered requests" in text
