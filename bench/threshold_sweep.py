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

from app.cache.embedder import build_embedder
from app.cache.evaluation import cosine, recommend, sweep, thresholds


def load_pairs(path: str) -> list[dict]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


async def score_pairs(pairs: list[dict], embedder) -> list[float]:
    texts = sorted({t for p in pairs for t in (p["a"], p["b"])})
    vectors = {t: await embedder.embed_one(t) for t in texts}
    return [cosine(vectors[p["a"]], vectors[p["b"]]) for p in pairs]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="data/bench/pairs.jsonl")
    ap.add_argument("--embedder", default="sentence-transformers")
    ap.add_argument("--model", default="intfloat/multilingual-e5-small")
    ap.add_argument("--prefix", default="query:")
    ap.add_argument("--max-wrong", type=float, default=0.0)
    args = ap.parse_args()

    pairs = load_pairs(args.pairs)
    embedder = build_embedder(args.embedder, args.model, args.prefix)
    scores = asyncio.run(score_pairs(pairs, embedder))
    same = [s for p, s in zip(pairs, scores) if p["label"] == "same"]
    diff = [s for p, s in zip(pairs, scores) if p["label"] == "different"]
    if not same or not diff:
        print("Need both 'same' and 'different' pairs.")
        return 1

    rows = sweep(same, diff, thresholds())
    print(f"{len(same)} same / {len(diff)} different | embedder={args.embedder} model={args.model}")
    print("threshold  hit_rate  wrong_hit_rate")
    for r in rows:
        print(f"{r['threshold']:<10.2f} {r['hit_rate']:<9.2f} {r['wrong_hit_rate']:.2f}")

    risky = sorted(
        ((s, p) for p, s in zip(pairs, scores) if p["label"] == "different"),
        key=lambda x: -x[0],
    )[:5]
    print("\nMost dangerous 'different' pairs (highest similarity):")
    for s, p in risky:
        print(f"  {s:.3f}  {p['a']}  |  {p['b']}")

    best = recommend(rows, args.max_wrong)
    if best is None:
        print(f"\nNo threshold in 0.70-0.99 keeps wrong hits <= {args.max_wrong}. "
              "This model cannot separate your near-misses.")
        return 2
    print(f"\nRecommended threshold (wrong-hit rate <= {args.max_wrong}): {best}")
    print(f"Hit rate at that threshold: {next(r for r in rows if r['threshold'] == best)['hit_rate']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())