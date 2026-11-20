# Runbook

## A provider is down (alert: ProviderCircuitOpen, or users see X-Provider change)
1. Grafana "Provider calls per second" shows which provider is failing. Logs show `circuit opened`.
2. If fallbacks are serving traffic, nothing is urgent. The breaker probes the provider every
   `cooldown_seconds` and closes by itself on success.
3. If the whole chain fails, clients get 502 `upstream_error`. Edit the chain in the routing
   config (`config/routing.json`), add a priced fallback model, and restart the gateway.
4. Check the provider's status page before changing anything.

## An API key leaked
1. `DELETE /admin/keys/{key_id}` revokes it instantly (list ids with `GET /admin/tenants/{id}/keys`).
2. Issue a new key, or rotate with `POST /admin/keys/{key_id}/rotate`.
3. Review `GET /admin/tenants/{id}/usage` and the request logs (filter by tenant) for abuse.
4. If a provider key leaked, rotate it at the provider and update `.env`.

## A tenant reports 429 budget_exceeded
1. `GET /admin/tenants/{id}/usage` shows month-to-date tokens and cost against the budget.
2. Raise it: `PATCH /admin/tenants/{id}` with `monthly_token_budget` or `monthly_cost_budget_usd`.
   It takes effect immediately. Budgets are soft caps and months follow UTC.

## Someone reports a wrong cached answer
1. Immediate mitigation: `PATCH /admin/tenants/{id}` with `{"cache_enabled": false}`. The tenant
   stops being served from the cache at once.
2. Raise `semantic_threshold` for that tenant if the cache is otherwise useful.
3. There is no purge endpoint yet. Entries disappear when `DWARPAL_CACHE_TTL_SECONDS` passes.
4. Add the question pair to `data/bench/pairs.jsonl` as a `different` pair and re-run `make bench`.

## The gateway is down (alert: GatewayDown)
1. `docker compose ps` and `docker compose logs gateway`.
2. Redis or Qdrant down: requests still work (caches fail open), only slower and costlier.
3. Postgres down: authentication fails, so requests fail. Restore Postgres first.
4. Migrations run on startup. If they fail, the gateway refuses to start. Read the log.
