import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Callable

from app.api.schemas import ChatRequest
from app.core.errors import ApiError
from app.routing.providers import Completion, Provider

log = logging.getLogger("dwarpal")
RETRYABLE = "upstream_error"  # only this error code triggers a fallback


@dataclass
class RoutingConfig:
    chains: dict[str, list[str]] = field(default_factory=dict)
    cooldown_seconds: float = 30.0
    failure_threshold: int = 3


def load_routing_config(path: str) -> RoutingConfig:
    if not path:
        return RoutingConfig()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    chains = data.get("chains", {})
    valid = isinstance(chains, dict) and all(
        isinstance(k, str) and isinstance(v, list) and all(isinstance(m, str) for m in v)
        for k, v in chains.items()
    )
    if not valid:
        raise ValueError("routing config: 'chains' must map model names to lists of model names")
    cfg = RoutingConfig(
        chains={k: list(v) for k, v in chains.items()},
        cooldown_seconds=float(data.get("cooldown_seconds", 30)),
        failure_threshold=int(data.get("failure_threshold", 3)),
    )
    if cfg.failure_threshold < 1 or cfg.cooldown_seconds < 0:
        raise ValueError("routing config: failure_threshold must be >= 1, cooldown_seconds >= 0")
    return cfg


class Health:
    """Per-model circuit breaker. After the cooldown the next call is a probe: if it fails,
    the circuit reopens immediately, because the failure count is still at the threshold."""

    def __init__(self, threshold: int, cooldown: float, clock=time.monotonic) -> None:
        self.threshold, self.cooldown, self.clock = threshold, cooldown, clock
        self._failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}

    def available(self, key: str) -> bool:
        return self.clock() >= self._open_until.get(key, 0.0)

    def success(self, key: str) -> None:
        self._failures[key] = 0
        self._open_until.pop(key, None)

    def failure(self, key: str) -> bool:
        """Returns True when this failure newly opened the circuit."""
        count = self._failures.get(key, 0) + 1
        self._failures[key] = count
        if count < self.threshold:
            return False
        newly = self.available(key)
        self._open_until[key] = self.clock() + self.cooldown
        return newly

    def snapshot(self) -> dict[str, bool]:
        return {key: not self.available(key) for key in self._failures}


def _all_failed(tried: int) -> ApiError:
    message = "Upstream provider error." if tried <= 1 else "All configured providers failed."
    return ApiError(502, message, RETRYABLE, "api_error")


class Router:
    def __init__(
        self,
        factory: Callable[[str], Provider],
        config: RoutingConfig | None = None,
        metrics=None,
        clock=time.monotonic,
    ) -> None:
        self.factory = factory
        self.config = config or RoutingConfig()
        self.metrics = metrics
        self.health = Health(self.config.failure_threshold, self.config.cooldown_seconds, clock)
        # Only models named in the config are tracked. Anything else a tenant sends
        # must not grow our state or our metric labels.
        self._tracked = set(self.config.chains) | {
            m for chain in self.config.chains.values() for m in chain
        }

    def candidates(self, model: str, allow_fallback: bool = True) -> list[str]:
        chain = self.config.chains.get(model, []) if allow_fallback else []
        seen: set[str] = set()
        out: list[str] = []
        for m in [model, *chain]:
            if m not in seen:
                seen.add(m)
                out.append(m)
        return out

    def order(self, model: str, allow_fallback: bool = True) -> list[str]:
        cands = self.candidates(model, allow_fallback)
        healthy = [m for m in cands if self.health.available(m)]
        return healthy or cands  # everything cooling down: fail open and try anyway

    def provider_for(self, model: str, allow_fallback: bool = True) -> "RoutedProvider":
        return RoutedProvider(self, model, allow_fallback)

    def record_success(self, key: str, provider_name: str) -> None:
        if key in self._tracked:
            self.health.success(key)
        if self.metrics:
            self.metrics.provider_call(provider_name, True)

    def record_failure(self, key: str, provider_name: str) -> None:
        newly_open = key in self._tracked and self.health.failure(key)
        if self.metrics:
            self.metrics.provider_call(provider_name, False)
            if newly_open:
                self.metrics.circuit_opened(key)
        if newly_open:
            log.warning(
                "circuit opened",
                extra={"model": key, "cooldown_s": self.config.cooldown_seconds},
            )


class RoutedProvider:
    """Looks like a Provider to the chat endpoint. `name` and `served_model` always describe
    the provider and model that actually served (or last attempted) the request."""

    def __init__(self, router: Router, model: str, allow_fallback: bool = True) -> None:
        self.router, self.model, self.allow_fallback = router, model, allow_fallback
        self.name = router.factory(model).name
        self.served_model = model

    def _log_fallback(self, served_by: str) -> None:
        if served_by != self.model:
            log.warning(
                "fallback used", extra={"requested_model": self.model, "served_by": served_by}
            )

    async def complete(self, req: ChatRequest) -> Completion:
        tried = 0
        for cand in self.router.order(self.model, self.allow_fallback):
            provider = self.router.factory(cand)
            self.name, self.served_model = provider.name, cand
            tried += 1
            try:
                result = await provider.complete(req)
            except ApiError as exc:
                if exc.code != RETRYABLE:
                    raise
                self.router.record_failure(cand, provider.name)
                continue
            self.router.record_success(cand, provider.name)
            self._log_fallback(cand)
            return result
        raise _all_failed(tried)

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        tried = 0
        for cand in self.router.order(self.model, self.allow_fallback):
            provider = self.router.factory(cand)
            self.name, self.served_model = provider.name, cand
            tried += 1
            it = provider.stream(req).__aiter__()
            try:
                first = await it.__anext__()
            except StopAsyncIteration:
                self.router.record_success(cand, provider.name)
                return
            except ApiError as exc:
                if exc.code != RETRYABLE:
                    raise
                self.router.record_failure(cand, provider.name)
                continue
            # Committed: tokens are already on their way to the client, so no more switching.
            self._log_fallback(cand)
            try:
                yield first
                async for piece in it:
                    yield piece
            except ApiError:
                self.router.record_failure(cand, provider.name)
                raise
            finally:
                aclose = getattr(it, "aclose", None)
                if aclose is not None:
                    await aclose()
            self.router.record_success(cand, provider.name)
            return
        raise _all_failed(tried)