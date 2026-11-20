"""Compare embedding models on the labeled pairs. Each model downloads on first use.

    python bench/embeddings_eval.py --out bench/results/embeddings.json
    python bench/embeddings_eval.py --models intfloat/multilingual-e5-small

Verify language support on each model's card. This run measures it on YOUR pairs.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from threshold_sweep import evaluate, load_pairs, score_pairs

from app.cache.embedder import SentenceTransformerEmbedder

MODELS = [
    ("intfloat/multilingual-e5-small", "query:"),
    ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", ""),
    ("BAAI/bge-m3", ""),   # large (about 2 GB). Slow on CPU: skip it with --models if needed.
]


async def time_encode(embedder, texts: list[str], n: int = 20) -> float:
    sample = texts[:n]
    start = time.perf_counter()
    for text in sample:
        await embedder.embed_one(text)
    return (time.perf_counter() - start) / len(sample) * 1000


async def evaluate_model(name: str, prefix: str, pairs: list[dict], max_wrong: float) -> dict:
    embedder = SentenceTransformerEmbedder(name, prefix)
    scores = await score_pairs(pairs, embedder)          # the first call loads the model
    texts = sorted({t for p in pairs for t in (p["a"], p["b"])})
    result = evaluate(pairs, scores, max_wrong)
    result.update(
        model=name, prefix=prefix,
        dim=len(await embedder.embed_one(texts[0])),
        avg_encode_ms=round(await time_encode(embedder, texts), 1),
    )
    return result


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="data/bench/pairs.jsonl")
    ap.add_argument("--models", default="", help="comma-separated subset of model names")
    ap.add_argument("--max-wrong", type=float, default=0.0)
    ap.add_argument("--out", default="bench/results/embeddings.json")
    args = ap.parse_args()

    pairs = load_pairs(args.pairs)
    wanted = {m.strip() for m in args.models.split(",") if m.strip()}
    chosen = [(n, p) for n, p in MODELS if not wanted or n in wanted]
    results = []
    for name, prefix in chosen:
        print(f"Evaluating {name} ...", flush=True)
        try:
            results.append(asyncio.run(evaluate_model(name, prefix, pairs, args.max_wrong)))
        except Exception as exc:  # one failed download must not lose the other results
            results.append({"model": name, "error": f"{type(exc).__name__}: {str(exc)[:150]}"})
        last = results[-1]
        if "error" in last:
            print(f"  failed: {last['error']}")
        else:
            print(f"  margin {last['margin']}  threshold {last['recommended_threshold']}  "
                  f"hit rate {last['hit_rate_at_threshold']}  {last['avg_encode_ms']} ms/query")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"pairs": len(pairs), "models": results}, indent=2,
                              ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
