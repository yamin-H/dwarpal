import math


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def thresholds(lo: float = 0.70, hi: float = 0.99, step: float = 0.01) -> list[float]:
    return [round(lo + i * step, 4) for i in range(int(round((hi - lo) / step)) + 1)]


def sweep(same_scores: list[float], diff_scores: list[float], ts: list[float]) -> list[dict]:
    """hit_rate: paraphrases correctly reused. wrong_hit_rate: different questions wrongly reused."""
    rows = []
    for t in ts:
        hit = sum(s >= t for s in same_scores) / len(same_scores) if same_scores else 0.0
        wrong = sum(s >= t for s in diff_scores) / len(diff_scores) if diff_scores else 0.0
        rows.append({"threshold": t, "hit_rate": hit, "wrong_hit_rate": wrong})
    return rows


def recommend(rows: list[dict], max_wrong_rate: float = 0.0) -> float | None:
    """Lowest threshold (so the highest hit rate) whose wrong-hit rate is acceptable."""
    ok = [r["threshold"] for r in rows if r["wrong_hit_rate"] <= max_wrong_rate]
    return min(ok) if ok else None