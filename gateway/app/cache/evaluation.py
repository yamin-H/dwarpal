import math


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def thresholds(lo: float = 0.70, hi: float = 0.99, step: float = 0.01) -> list[float]:
    return [round(lo + i * step, 4) for i in range(round((hi - lo) / step) + 1)]


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



def separation_margin(same_scores: list[float], diff_scores: list[float]) -> float | None:
    """Lowest paraphrase similarity minus highest near-miss similarity.
    Positive means some threshold separates the two groups perfectly on this data."""
    if not same_scores or not diff_scores:
        return None
    return min(same_scores) - max(diff_scores)


def validate_pairs(pairs: list) -> list[str]:
    """Return problems found in a labeled pairs file. One label typo can skew a threshold."""
    errors: list[str] = []
    seen: dict[frozenset, tuple[str, int]] = {}
    for i, p in enumerate(pairs, start=1):
        where = f"pair {i}"
        if not isinstance(p, dict):
            errors.append(f"{where}: not an object")
            continue
        a, b, label = p.get("a"), p.get("b"), p.get("label")
        if not isinstance(a, str) or not isinstance(b, str) or not a.strip() or not b.strip():
            errors.append(f"{where}: 'a' and 'b' must be non-empty strings")
            continue
        if label not in ("same", "different"):
            errors.append(f"{where}: label must be 'same' or 'different', got {label!r}")
            continue
        if a.strip() == b.strip():
            errors.append(f"{where}: both texts are identical")
            continue
        key = frozenset((a.strip(), b.strip()))
        if key in seen:
            prev_label, prev_index = seen[key]
            problem = "contradicts" if prev_label != label else "duplicates"
            errors.append(f"{where}: {problem} pair {prev_index}")
        else:
            seen[key] = (label, i)
    return errors
