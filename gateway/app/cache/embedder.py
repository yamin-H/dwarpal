import hashlib
import importlib.util
import math
import threading
from typing import Protocol

from fastapi.concurrency import run_in_threadpool


class Embedder(Protocol):
    async def embed_one(self, text: str) -> list[float]: ...


class HashEmbedder:
    """DEV ONLY: hashed character trigrams. Matches similar spellings, NOT similar meanings."""

    DIM = 256

    async def embed_one(self, text: str) -> list[float]:
        padded = f"  {' '.join(text.lower().split())}  "
        vec = [0.0] * self.DIM
        for i in range(len(padded) - 2):
            h = int(hashlib.sha1(padded[i : i + 3].encode("utf-8")).hexdigest()[:8], 16)
            vec[h % self.DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            vec[0], norm = 1.0, 1.0
        return [x / norm for x in vec]


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, prefix: str = "") -> None:
        self.model_name = model_name
        self.prefix = prefix.strip()
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(self.model_name)
        return self._model

    def _encode(self, text: str) -> list[float]:
        text = f"{self.prefix} {text}" if self.prefix else text
        return self._load().encode(text, normalize_embeddings=True).tolist()

    async def embed_one(self, text: str) -> list[float]:
        return await run_in_threadpool(self._encode, text)


def build_embedder(name: str, model: str = "", prefix: str = "") -> Embedder:
    if name == "hash":
        return HashEmbedder()
    if name == "sentence-transformers":
        if importlib.util.find_spec("sentence_transformers") is None:
            raise RuntimeError(
                "sentence-transformers is not installed. Run: pip install -r requirements-ml.txt "
                "(or set DWARPAL_EMBEDDER=hash for non-semantic dev runs)."
            )
        return SentenceTransformerEmbedder(model, prefix)
    raise ValueError(f"unknown embedder '{name}'")