import json
import math
from dataclasses import dataclass
from pathlib import Path

FREE_MODELS = ("auto", "mock-echo", "mock-fail")


@dataclass(frozen=True)
class Price:
    input_per_million: float
    output_per_million: float


class PriceTable:
    def __init__(self, prices: dict[str, Price] | None = None) -> None:
        self._prices = {m: Price(0.0, 0.0) for m in FREE_MODELS}
        self._prices.update(prices or {})

    def knows(self, model: str) -> bool:
        return model in self._prices

    def cost_micros(self, model: str, prompt_tokens: int, completion_tokens: int) -> int | None:
        """USD per million tokens equals micro-USD per token. None means the model has no price."""
        price = self._prices.get(model)
        if price is None:
            return None
        return round(
            max(prompt_tokens, 0) * price.input_per_million
            + max(completion_tokens, 0) * price.output_per_million
        )

    def table(self) -> dict[str, dict[str, float]]:
        return {
            m: {"input_per_million": p.input_per_million, "output_per_million": p.output_per_million}
            for m, p in sorted(self._prices.items())
        }


def load_price_table(path: str) -> PriceTable:
    if not path:
        return PriceTable()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = data.get("per_million_tokens")
    if not isinstance(raw, dict):
        raise ValueError("price config: 'per_million_tokens' must be an object")
    prices: dict[str, Price] = {}
    for model, entry in raw.items():
        try:
            inp, out = float(entry["input"]), float(entry["output"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"price config: bad entry for '{model}'") from None
        if not (math.isfinite(inp) and math.isfinite(out)) or inp < 0 or out < 0:
            raise ValueError(f"price config: prices for '{model}' must be finite and >= 0")
        prices[model] = Price(inp, out)
    return PriceTable(prices)


def validate_routing_prices(chains: dict[str, list[str]], prices: PriceTable) -> None:
    models = set(chains) | {m for chain in chains.values() for m in chain}
    missing = sorted(m for m in models if not prices.knows(m))
    if missing:
        raise ValueError(
            "these models in the routing config have no price: " + ", ".join(missing)
            + " (add them to the price config)"
        )