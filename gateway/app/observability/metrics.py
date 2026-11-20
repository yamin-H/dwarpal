from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily

CONTENT_TYPE = CONTENT_TYPE_LATEST
LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60)
TTFT_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10)


class _CircuitCollector:
    """Computed at scrape time, so the gauge drops to 0 on its own when the cooldown ends."""

    def __init__(self, router) -> None:
        self.router = router

    def collect(self):
        family = GaugeMetricFamily(
            "dwarpal_provider_circuit_open", "1 while a model's circuit breaker is open",
            labels=["model"],
        )
        for model, is_open in self.router.health.snapshot().items():
            family.add_metric([model], 1.0 if is_open else 0.0)
        yield family


class Metrics:
    """One registry per app instance (a global registry breaks when create_app runs twice)."""

    def __init__(self, registry: CollectorRegistry | None = None, max_labels: int = 50) -> None:
        self.registry = registry or CollectorRegistry()
        self.max_labels = max_labels
        self._seen: dict[str, set[str]] = {"model": set(), "provider": set()}
        reg = self.registry
        self._requests = Counter(
            "dwarpal_requests_total", "Chat requests by outcome",
            ["tenant", "model", "status", "cache"], registry=reg)
        self._duration = Histogram(
            "dwarpal_request_duration_seconds", "End-to-end chat request duration",
            ["cache"], buckets=LATENCY_BUCKETS, registry=reg)
        self._ttft = Histogram(
            "dwarpal_ttft_seconds", "Time to first streamed token",
            ["source"], buckets=TTFT_BUCKETS, registry=reg)
        self._tokens = Counter(
            "dwarpal_tokens_total", "Tokens processed (estimates for streams)",
            ["tenant", "type"], registry=reg)
        self._provider_calls = Counter(
            "dwarpal_provider_calls_total", "Upstream provider calls",
            ["provider", "outcome"], registry=reg)
        self._circuit_opened = Counter(
            "dwarpal_circuit_opened_total", "Times a model's circuit opened",
            ["model"], registry=reg)
        self._http = Counter(
            "dwarpal_http_responses_total", "HTTP responses by status class",
            ["status_class"], registry=reg)
        self._cost = Counter(
            "dwarpal_cost_usd_total", "Estimated spend in USD", ["tenant"], registry=reg)
        self._unpriced = Counter(
            "dwarpal_unpriced_requests_total", "Requests served by a model with no price",
            ["model"], registry=reg)
        self._budget_rejections = Counter(
            "dwarpal_budget_rejections_total", "Requests rejected by a tenant budget",
            ["tenant", "kind"], registry=reg)

    def _bounded(self, kind: str, value: str) -> str:
        """Cap label cardinality: a tenant allowed '*' must not be able to mint unlimited series."""
        seen = self._seen[kind]
        if value in seen:
            return value
        if len(seen) < self.max_labels:
            seen.add(value)
            return value
        return "other"

    def observe_request(self, *, tenant, model, status, cache, duration_s,
                        prompt_tokens, completion_tokens, cost_usd: float = 0.0) -> None:
        self._requests.labels(
            tenant=tenant, model=self._bounded("model", model), status=status, cache=cache
        ).inc()
        self._duration.labels(cache=cache).observe(duration_s)
        self._tokens.labels(tenant=tenant, type="prompt").inc(max(prompt_tokens, 0))
        self._tokens.labels(tenant=tenant, type="completion").inc(max(completion_tokens, 0))
        self._cost.labels(tenant=tenant).inc(max(cost_usd, 0.0))

    def unpriced(self, model: str) -> None:
        self._unpriced.labels(model=self._bounded("model", model)).inc()

    def budget_rejected(self, tenant: str, kind: str) -> None:
        self._budget_rejections.labels(tenant=tenant, kind=kind).inc()

    def observe_ttft(self, source: str, seconds: float) -> None:
        self._ttft.labels(source=self._bounded("provider", source)).observe(seconds)

    def provider_call(self, provider: str, ok: bool) -> None:
        self._provider_calls.labels(
            provider=self._bounded("provider", provider),
            outcome="success" if ok else "failure",
        ).inc()

    def circuit_opened(self, model: str) -> None:
        self._circuit_opened.labels(model=self._bounded("model", model)).inc()

    def observe_http(self, status: int) -> None:
        self._http.labels(status_class=f"{status // 100}xx").inc()

    def bind_router(self, router) -> None:
        self.registry.register(_CircuitCollector(router))

    def render(self) -> bytes:
        return generate_latest(self.registry)