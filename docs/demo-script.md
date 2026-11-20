# Demo script (about 90 seconds)

Before recording: stack up with `DWARPAL_PLAYGROUND_ENABLED=true` and `DWARPAL_MOCK_DELAY_MS=300`,
Grafana open on the dashboard, a terminal ready, two tenants created (`islamic-app`, `bank-app`
with a small token budget), and their keys pasted into the playground.

1. (0:00) One sentence: "This is a gateway between apps and LLM providers. Auth, caching,
   routing, budgets and monitoring live in one place."
2. (0:10) Playground, tenant `islamic-app`: ask "zakat koto taka dite hoy". Point at the tag:
   `cache: MISS`, about 300 ms.
3. (0:25) Ask "যাকাত কত টাকা দিতে হয়". The tag shows `HIT-SEMANTIC` with a score, in milliseconds.
   Say: "Different language, same question, no provider call."
4. (0:40) Ask "zakat on gold", then "zakat on silver". The second must be a MISS. Say: "The
   threshold was chosen from labeled near-misses, not guessed."
5. (0:55) Switch to `bank-app` and ask the same Bangla question: MISS. "Caches never cross tenants."
6. (1:05) Keep sending with `bank-app` until the red 429 appears. "Budgets are enforced per tenant."
7. (1:15) Terminal: `make drill KEY=...`. Show 100% answered while the failing provider got only
   a handful of calls. Switch to Grafana: circuit-open panel and fallback traffic.
8. (1:30) End on the README results table. "Everything here is reproducible: `docker compose up`."

Do not read numbers you did not measure. Show the files in `bench/results/` if asked.
