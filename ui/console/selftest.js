import { el, api, badge, shared, takeEvents, pageHead, fmtMs, reportError, toast } from "./lib.js";

class Skip extends Error {}
const skip = (message) => { throw new Skip(message); };

const TENANTS = [
  { id: "selftest-a", name: "Self-test A", models: ["auto", "mock-echo", "mock-fail"] },
  { id: "selftest-b", name: "Self-test B", models: ["auto", "mock-echo", "mock-fail"] },
  { id: "selftest-budget", name: "Self-test budget", models: ["auto"] },
  { id: "selftest-pinned", name: "Self-test pinned", models: ["mock-fail"], fallback: false },
];

const textOf = (r) => (r.json && r.json.choices && r.json.choices[0] && r.json.choices[0].message.content) || "";

async function chat(key, text, opts = {}) {
  const { model = "auto", stream = false, bypass = false, headers = {} } = opts;
  const h = { "Content-Type": "application/json", ...headers };
  if (key) h.Authorization = `Bearer ${key}`;
  if (bypass) h["X-Dwarpal-Cache"] = "bypass";
  const started = performance.now();
  const res = await fetch("/v1/chat/completions", {
    method: "POST", headers: h,
    body: JSON.stringify({ model, stream, messages: [{ role: "user", content: text }] }),
  });
  const out = {
    status: res.status, cache: res.headers.get("x-cache"), score: res.headers.get("x-cache-score"),
    reason: res.headers.get("x-cache-reason"), provider: res.headers.get("x-provider"),
    requestId: res.headers.get("x-request-id"), chunks: 0, done: false, firstMs: null, json: null, errorCode: null,
  };
  if (stream && res.ok) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = takeEvents(buffer);
      buffer = parsed.rest;
      for (const data of parsed.events) {
        if (data === "[DONE]") { out.done = true; continue; }
        try {
          const obj = JSON.parse(data);
          const piece = obj.choices && obj.choices[0] && obj.choices[0].delta.content;
          if (piece) { out.chunks += 1; if (out.firstMs === null) out.firstMs = performance.now() - started; }
        } catch (err) { /* ignore a malformed event */ }
      }
    }
  } else {
    const raw = await res.text();
    try { out.json = JSON.parse(raw); } catch (err) { out.json = null; }
    out.errorCode = out.json && out.json.error ? out.json.error.code : null;
  }
  out.ms = performance.now() - started;
  return out;
}

const patch = (id, body) => api(`/admin/tenants/${id}`, { method: "PATCH", body });
const purge = (id) => api(`/admin/tenants/${id}/cache`, { method: "DELETE" });

const SCENARIOS = [
  {
    id: "auth", title: "Authentication",
    description: "Requests without a valid key are rejected, and a valid key works.",
    async run({ step, keys }) {
      const none = await chat(null, "hello");
      step("No key gives 401 missing_api_key", none.status === 401 && none.errorCode === "missing_api_key", `got ${none.status} ${none.errorCode || ""}`);
      const bad = await chat("dk_live_not_a_real_key", "hello");
      step("Unknown key gives 401 invalid_api_key", bad.status === 401 && bad.errorCode === "invalid_api_key", `got ${bad.status} ${bad.errorCode || ""}`);
      const ok = await chat(keys["selftest-a"], "hello");
      step("Valid key gives 200", ok.status === 200, `got ${ok.status}`);
    },
  },
  {
    id: "stream", title: "Streaming",
    description: "Answers arrive as an event stream, progressively, and end with [DONE].",
    async run({ step, keys }) {
      const r = await chat(keys["selftest-a"], "one two three four five six", { stream: true, bypass: true });
      step("Returns 200", r.status === 200, `got ${r.status}`);
      step("Several content chunks arrive", r.chunks >= 3, `${r.chunks} chunks`);
      step("Stream ends with [DONE]", r.done);
      if (r.ms >= 400) step("First token arrives well before the end", r.firstMs < r.ms * 0.6, `first ${fmtMs(r.firstMs)} of ${fmtMs(r.ms)}`);
      else step("Progressive delivery", null, "response too fast to judge: set DWARPAL_MOCK_DELAY_MS=300 to verify");
    },
  },
  {
    id: "cache", title: "Exact cache and purge",
    description: "The same question is answered from the cache the second time, and clearing the cache brings the miss back.",
    async run({ step, keys }) {
      await purge("selftest-a");
      const q = "How many rakats are in the Fajr prayer";
      const first = await chat(keys["selftest-a"], q);
      if (first.cache === "DISABLED") skip("Caching is disabled (set DWARPAL_REDIS_URL or enable the semantic cache).");
      step("First ask is a MISS", first.cache === "MISS", `X-Cache: ${first.cache}`);
      const second = await chat(keys["selftest-a"], q);
      step("Same question again is a HIT", (second.cache || "").startsWith("HIT"), `X-Cache: ${second.cache}, ${fmtMs(first.ms)} then ${fmtMs(second.ms)}`);
      step("Cached answer is identical", textOf(first) === textOf(second) && textOf(first) !== "");
      await purge("selftest-a");
      const third = await chat(keys["selftest-a"], q);
      step("After clearing the tenant cache it is a MISS again", third.cache === "MISS", `X-Cache: ${third.cache}`);
    },
  },
  {
    id: "isolation", title: "Tenant isolation",
    description: "One tenant never receives another tenant's cached answer.",
    async run({ step, keys }) {
      await purge("selftest-a");
      await purge("selftest-b");
      const q = "What is the ruling on combining prayers while traveling";
      const a1 = await chat(keys["selftest-a"], q);
      if (a1.cache === "DISABLED") skip("Caching is disabled.");
      const a2 = await chat(keys["selftest-a"], q);
      step("Tenant A is served from its own cache", (a2.cache || "").startsWith("HIT"), `X-Cache: ${a2.cache}`);
      const b1 = await chat(keys["selftest-b"], q);
      step("Tenant B asking the same question gets a MISS", b1.cache === "MISS", `X-Cache: ${b1.cache}`);
    },
  },
  {
    id: "policy", title: "Cache policy",
    description: "Personal data and time-sensitive questions are never cached.",
    async run({ step, keys }) {
      const phone = await chat(keys["selftest-a"], "call me on 01712345678");
      if (phone.cache === "DISABLED") skip("Caching is disabled.");
      step("A phone number is skipped (personal-data)", phone.cache === "SKIP" && phone.reason === "personal-data", `${phone.cache} ${phone.reason || ""}`);
      const again = await chat(keys["selftest-a"], "call me on 01712345678");
      step("Asking again is still not cached", again.cache === "SKIP", `X-Cache: ${again.cache}`);
      const time = await chat(keys["selftest-a"], "namaz er time ajke koyta");
      step("A time-sensitive question is skipped", time.cache === "SKIP" && time.reason === "time-sensitive", `${time.cache} ${time.reason || ""}`);
    },
  },
  {
    id: "semantic", title: "Semantic cache",
    description: "A Banglish question reuses the answer to the Bangla one, but near-misses are not confused.",
    async run({ step, keys }) {
      const cache = shared.system.cache;
      if (!cache.semantic_enabled) skip("The semantic cache is off (DWARPAL_SEMANTIC_CACHE_ENABLED).");
      if (cache.embedder === "hash") skip("The hash embedder only matches similar spelling, not meaning.");
      await purge("selftest-a");
      const k = keys["selftest-a"];
      const first = await chat(k, "zakat koto taka dite hoy");
      step("First phrasing is a MISS", first.cache === "MISS", `X-Cache: ${first.cache}`);
      const para = await chat(k, "যাকাত কত টাকা দিতে হয়");
      step("The Bangla paraphrase is a HIT-SEMANTIC", para.cache === "HIT-SEMANTIC", `X-Cache: ${para.cache}${para.score ? `, score ${para.score}` : ""}`);
      await chat(k, "zakat on gold");
      const near = await chat(k, "zakat on silver");
      step("A near-miss (gold vs silver) is NOT served from the other's answer", near.cache !== "HIT-SEMANTIC",
        near.cache === "HIT-SEMANTIC" ? `threshold too loose, score ${near.score}` : `X-Cache: ${near.cache}`);
    },
  },
  {
    id: "controls", title: "Tenant controls",
    description: "Cache opt-out, the kill switch and the model allow-list.",
    async run({ step, keys }) {
      try {
        await patch("selftest-b", { cache_enabled: false });
        const off = await chat(keys["selftest-b"], "Is it allowed to pray in congregation at home");
        if (off.cache === "DISABLED") step("Cache opt-out", null, "caching is disabled globally");
        else step("Cache opt-out gives SKIP (tenant-policy)", off.cache === "SKIP" && off.reason === "tenant-policy", `${off.cache} ${off.reason || ""}`);
      } finally { await patch("selftest-b", { cache_enabled: true }); }
      try {
        await patch("selftest-b", { active: false });
        const blocked = await chat(keys["selftest-b"], "hello");
        step("A disabled tenant gets 401", blocked.status === 401, `got ${blocked.status}`);
      } finally { await patch("selftest-b", { active: true }); }
      const back = await chat(keys["selftest-b"], "hello");
      step("Re-enabling restores access", back.status === 200, `got ${back.status}`);
      const denied = await chat(keys["selftest-budget"], "hello", { model: "mock-echo" });
      step("A model outside the allow-list gives 403", denied.status === 403 && denied.errorCode === "model_not_allowed", `got ${denied.status} ${denied.errorCode || ""}`);
    },
  },
  {
    id: "budget", title: "Budgets",
    description: "Once a tenant reaches its monthly budget it gets 429, and raising the budget restores access immediately.",
    async run({ step, keys }) {
      const usage = (await api("/admin/tenants/selftest-budget/usage")).data;
      const used = usage.month_to_date.tokens;
      try {
        await patch("selftest-budget", { monthly_token_budget: used + 5 });
        const first = await chat(keys["selftest-budget"], "hello world", { bypass: true });
        step("Within the budget the request succeeds", first.status === 200, `got ${first.status}`);
        const second = await chat(keys["selftest-budget"], "hello world", { bypass: true });
        step("Over the budget gives 429 budget_exceeded", second.status === 429 && second.errorCode === "budget_exceeded", `got ${second.status} ${second.errorCode || ""}`);
        await patch("selftest-budget", { monthly_token_budget: used + 100000 });
        const third = await chat(keys["selftest-budget"], "hello world", { bypass: true });
        step("Raising the budget restores access without a restart", third.status === 200, `got ${third.status}`);
      } finally { await patch("selftest-budget", { monthly_token_budget: null }); }
    },
  },
  {
    id: "fallback", title: "Fallback and circuit breaker",
    description: "A failing provider is invisible to clients when a fallback exists, and its circuit opens.",
    async run({ step, keys }) {
      const chains = shared.system.routing.chains;
      if (!chains["mock-fail"]) skip("No fallback chain for mock-fail (set DWARPAL_ROUTING_CONFIG to config/routing.json).");
      const ok = await chat(keys["selftest-a"], "ping", { model: "mock-fail", bypass: true });
      step("A request for the failing model is still answered", ok.status === 200, `got ${ok.status}`);
      step("It was served by the fallback", !!ok.provider && ok.provider !== "mock-fail", `X-Provider: ${ok.provider}`);
      for (let i = 0; i < 4; i += 1) await chat(keys["selftest-pinned"], "ping", { model: "mock-fail", bypass: true });
      const pinned = await chat(keys["selftest-pinned"], "ping", { model: "mock-fail", bypass: true });
      step("A tenant with fallback disabled gets 502", pinned.status === 502 && pinned.errorCode === "upstream_error", `got ${pinned.status} ${pinned.errorCode || ""}`);
      const system = (await api("/admin/system")).data;
      step("The circuit for the failing model is open", system.routing.circuits["mock-fail"] === true, "it closes by itself after the cooldown");
    },
  },
  {
    id: "rotation", title: "Key rotation and revoke",
    description: "Rotation overlaps old and new keys, a zero overlap cuts over at once, and revoke is instant.",
    async run({ step, issueKey }) {
      const old = await issueKey("selftest-b");
      const r1 = (await api(`/admin/keys/${old.id}/rotate`, { method: "POST", body: { overlap_seconds: 0 } })).data;
      const n1 = { key: r1.api_key, id: r1.key_id };
      this.track(n1.id);
      step("Immediate cutover: the old key stops at once", (await chat(old.key, "hi")).status === 401);
      step("The new key works", (await chat(n1.key, "hi")).status === 200);
      const r2 = (await api(`/admin/keys/${n1.id}/rotate`, { method: "POST", body: { overlap_seconds: 60 } })).data;
      this.track(r2.key_id);
      step("With an overlap both keys work", (await chat(n1.key, "hi")).status === 200 && (await chat(r2.api_key, "hi")).status === 200);
      await api(`/admin/keys/${n1.id}`, { method: "DELETE" });
      step("Revoke is instant", (await chat(n1.key, "hi")).status === 401);
      try {
        await api(`/admin/keys/${n1.id}/rotate`, { method: "POST", body: { overlap_seconds: 0 } });
        step("A revoked key cannot be rotated", false, "rotation was accepted");
      } catch (err) { step("A revoked key cannot be rotated", err.status === 409, `got ${err.status}`); }
    },
  },
  {
    id: "tracing", title: "Request tracing",
    description: "Every response carries an X-Request-ID, and a valid incoming id is kept.",
    async run({ step, keys }) {
      const a = await chat(keys["selftest-a"], "hello", { bypass: true });
      const b = await chat(keys["selftest-a"], "hello", { bypass: true });
      step("Responses carry unique request ids", !!a.requestId && !!b.requestId && a.requestId !== b.requestId, `${(a.requestId || "").slice(0, 8)} and ${(b.requestId || "").slice(0, 8)}`);
      const mine = `selftest-${Math.random().toString(36).slice(2, 10)}`;
      const c = await chat(keys["selftest-a"], "hello", { bypass: true, headers: { "X-Request-ID": mine } });
      step("A valid incoming X-Request-ID is kept", c.requestId === mine, `got ${c.requestId}`);
    },
  },
  {
    id: "usage", title: "Usage accounting",
    description: "Requests and tokens show up in the tenant's usage numbers.",
    async run({ step, keys }) {
      const before = (await api("/admin/tenants/selftest-a/usage")).data;
      await chat(keys["selftest-a"], "hello world", { bypass: true });
      await chat(keys["selftest-a"], "hello world", { bypass: true });
      const after = (await api("/admin/tenants/selftest-a/usage")).data;
      step("The request count grew by 2", after.requests === before.requests + 2, `${before.requests} to ${after.requests}`);
      step("Token usage grew", after.total_tokens > before.total_tokens, `${before.total_tokens} to ${after.total_tokens}`);
    },
  },
];

async function prepare() {
  const keys = {};
  const created = [];
  for (const t of TENANTS) {
    try {
      await api("/admin/tenants", { method: "POST", body: { id: t.id, name: t.name, allowed_models: t.models, allow_fallback: t.fallback !== false } });
    } catch (err) { if (err.status !== 409) throw err; }
    await patch(t.id, {
      allowed_models: t.models, cache_enabled: true, allow_fallback: t.fallback !== false, active: true,
      semantic_threshold: null, monthly_token_budget: null, monthly_cost_budget_usd: null,
    });
    const issued = (await api(`/admin/tenants/${t.id}/keys`, { method: "POST" })).data;
    keys[t.id] = issued.api_key;
    created.push(issued.key_id);
  }
  return { keys, created };
}

async function runOne(scenario, env) {
  const steps = [];
  const started = performance.now();
  const ctx = {
    keys: env.keys,
    step: (label, ok, detail = "") => steps.push({ label, ok, detail }),
    issueKey: async (tenantId) => {
      const issued = (await api(`/admin/tenants/${tenantId}/keys`, { method: "POST" })).data;
      env.created.push(issued.key_id);
      return { key: issued.api_key, id: issued.key_id };
    },
    track: (id) => env.created.push(id),
  };
  let status = "pass";
  let message = "";
  try {
    await scenario.run.call(ctx, ctx);
  } catch (err) {
    if (err instanceof Skip) { status = "skip"; message = err.message; }
    else { status = "fail"; message = err.message; steps.push({ label: "Unexpected error", ok: false, detail: err.message }); }
  }
  if (status === "pass") {
    if (steps.some((s) => s.ok === false)) status = "fail";
    else if (steps.length && steps.every((s) => s.ok === null)) status = "skip";
  }
  return { status, steps, message, ms: performance.now() - started };
}

const STATUS_KIND = { pass: "ok", fail: "err", skip: "muted", running: "info", idle: "muted" };

export async function render(root) {
  let running = false;
  const state = new Map(SCENARIOS.map((s) => [s.id, { status: "idle", steps: [], message: "", ms: 0 }]));
  const summary = el("div", { class: "health" });
  const list = el("div");

  function draw() {
    const count = (k) => [...state.values()].filter((s) => s.status === k).length;
    summary.replaceChildren(badge(`${count("pass")} passed`, "ok"), badge(`${count("fail")} failed`, count("fail") ? "err" : "muted"),
      badge(`${count("skip")} skipped`, "muted"));
    list.replaceChildren(...SCENARIOS.map((sc) => {
      const r = state.get(sc.id);
      return el("div", { class: "card" },
        el("div", { class: "scenario-head" },
          el("div", {}, el("strong", {}, sc.title), " ", badge(r.status, STATUS_KIND[r.status]), r.ms ? el("span", { class: "muted" }, ` ${fmtMs(r.ms)}`) : null,
            el("div", { class: "muted" }, sc.description)),
          el("button", { class: "btn small", type: "button", disabled: running, onclick: () => run([sc]) }, "Run")),
        r.message ? el("p", { class: "hint" }, r.message) : null,
        r.steps.length ? el("ul", { class: "steps" }, r.steps.map((s) => el("li", {},
          s.ok === true ? badge("pass", "ok") : s.ok === false ? badge("fail", "err") : badge("skip", "muted"),
          el("div", {}, s.label, s.detail ? el("div", { class: "step-detail" }, s.detail) : null)))) : null);
    }));
  }

  async function run(scenarios) {
    if (running) return;
    running = true;
    let env = null;
    try {
      shared.system = (await api("/admin/system")).data;
      env = await prepare();
      for (const sc of scenarios) {
        state.set(sc.id, { status: "running", steps: [], message: "", ms: 0 });
        draw();
        state.set(sc.id, await runOne(sc, env));
        draw();
      }
    } catch (err) {
      reportError(err);
    } finally {
      if (env) {
        for (const id of env.created) { try { await api(`/admin/keys/${id}`, { method: "DELETE" }); } catch (err) { /* already revoked */ } }
      }
      running = false;
      draw();
      toast("Self-test finished. Test keys were revoked.", "info");
    }
  }

  root.append(
    pageHead("Self-test", "Runs the end-to-end checks against this gateway using four disposable selftest-* tenants.",
      el("button", { class: "btn primary", type: "button", disabled: false, onclick: () => run(SCENARIOS) }, "Run all")),
    summary,
    el("div", { class: "card" }, el("p", { class: "muted" },
      "These checks run from the browser straight against the gateway. They cannot test Kong's limits, the 404s on /admin at the public edge, or what happens when Redis or Qdrant are stopped: use the terminal checks in the testing guide for those.")),
    list);
  draw();
}
