# Decisions

- **Kong at the edge, FastAPI for logic.** Kong owns auth-adjacent limits, size caps and what is
  routable (no route for /admin, /docs, /metrics). FastAPI owns tenancy, caching and routing.
- **Own small router instead of LiteLLM's Router.** LiteLLM is used as the provider adapter. The
  routing layer is ours because we need streaming-aware fallback (only before the first token),
  per-model health with metrics hooks, and tests that run with no network.
- **No retries on the same provider.** A retried POST can be billed twice. The fallback chain is the
  retry policy. Kong is also configured with retries: 0.
- **Circuit breaker fails open.** If every candidate is cooling down we still try them.
- **Health state only for configured models.** Prevents unbounded memory and metric labels when a
  tenant is allowed "*" and sends arbitrary model names.
- **Caches fail open.** A broken Redis or Qdrant means a miss, never an error.