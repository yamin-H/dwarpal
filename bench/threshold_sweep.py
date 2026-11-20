"""Choose a semantic-cache threshold from labeled question pairs.

    python bench/threshold_sweep.py                          # intfloat/multilingual-e5-small
    python bench/threshold_sweep.py --embedder hash          # offline smoke test, NOT meaningful
    python bench/threshold_sweep.py --model BAAI/bge-m3 --prefix ""
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))

from app.cache.embedder import build_embedder  # noqa: E402
from app.cache.evaluation import (  # noqa: E402
    cosine, recommend, separation_margin, sweep, thresholds, validate_pairs,
)


def load_pairs(path: str) -> list[dict]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    pairs = [json.loads(line) for line in lines if line.strip()]
    problems = validate_pairs(pairs)
    if problems:
        raise ValueError("invalid pairs file:\n  " + "\n  ".join(problems[:10]))
    return pairs


async def score_pairs(pairs: list[dict], embedder) -> list[float]:
    texts = sorted({t for p in pairs for t in (p["a"], p["b"])})
    vectors = {t: await embedder.embed_one(t) for t in texts}
    return [cosine(vectors[p["a"]], vectors[p["b"]]) for p in pairs]


def evaluate(pairs: list[dict], scores: list[float], max_wrong: float) -> dict:
    same = [s for p, s in zip(pairs, scores) if p["label"] == "same"]
    diff = [s for p, s in zip(pairs, scores) if p["label"] == "different"]
    if not same or not diff:
        raise ValueError("need both 'same' and 'different' pairs")
    rows = sweep(same, diff, thresholds())
    best = recommend(rows, max_wrong)
    hit = next((r["hit_rate"] for r in rows if r["threshold"] == best), None)
    return {
        "pairs_same": len(same),
        "pairs_different": len(diff),
        "same_mean": round(sum(same) / len(same), 4),
        "diff_max": round(max(diff), 4),
        "margin": round(separation_margin(same, diff), 4),
        "max_wrong_rate": max_wrong,
        "recommended_threshold": best,
        "hit_rate_at_threshold": hit,
        "rows": rows,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="data/bench/pairs.jsonl")
    ap.add_argument("--embedder", default="sentence-transformers")
    ap.add_argument("--model", default="intfloat/multilingual-e5-small")
    ap.add_argument("--prefix", default="query:")
    ap.add_argument("--max-wrong", type=float, default=0.0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    pairs = load_pairs(args.pairs)
    embedder = build_embedder(args.embedder, args.model, args.prefix)
    scores = asyncio.run(score_pairs(pairs, embedder))
    result = evaluate(pairs, scores, args.max_wrong)

    print(f"{result['pairs_same']} same / {result['pairs_different']} different | "
          f"embedder={args.embedder} model={args.model}")
    print("threshold  hit_rate  wrong_hit_rate")
    for r in result["rows"]:
        print(f"{r['threshold']:<10.2f} {r['hit_rate']:<9.2f} {r['wrong_hit_rate']:.2f}")

    risky = sorted(
        ((s, p) for p, s in zip(pairs, scores) if p["label"] == "different"),
        key=lambda x: -x[0],
    )[:5]
    print("\nMost dangerous 'different' pairs (highest similarity):")
    for s, p in risky:
        print(f"  {s:.3f}  {p['a']}  |  {p['b']}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"embedder": args.embedder, "model": args.model, "prefix": args.prefix, **result}
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    best = result["recommended_threshold"]
    if best is None:
        print(f"\nNo threshold in 0.70-0.99 keeps wrong hits <= {args.max_wrong}. "
              "This model cannot separate your near-misses.")
        return 2
    print(f"\nRecommended threshold (wrong-hit rate <= {args.max_wrong}): {best}")
    print(f"Hit rate at that threshold: {result['hit_rate_at_threshold']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
