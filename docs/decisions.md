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

- **Forward-only migrations.** Rolling back a schema is riskier than rolling forward. Back up first.
- **Budgets are soft caps and fail closed on money.** A cost budget needs a price for every model it
  can reach, including fallbacks. Startup fails if a routing chain has an unpriced model.
- **Cache hits ignore budgets.** They cost nothing, so they are always served.
- **Rotation overlap instead of a hard cutover.** Clients can deploy the new key before the o

- **Playground is gated, same-origin and strict.** Off by default. Served by the gateway so the demo
  goes through Kong. CSP forbids inline script and style, the page uses `textContent` only, and
  API keys live in page memory and are never stored. Tests enforce these rules.
- **Admin console on the direct port only.** `/console` is served by the gateway, off by default,
  and Kong has no route for it. It uses the admin key, so it must never be reachable publicly.
- **The console is vanilla JS with no build step and no CDN.** The CSP forbids inline script and
  style, the code uses `textContent` only, and tests enforce both.
- **Keys live in page memory** unless the user opts in to sessionStorage for the tab's lifetime.
- **The self-test uses fixed `selftest-*` tenants** and revokes its keys afterwards, so repeated
  runs do not pile up tenants or keys.

