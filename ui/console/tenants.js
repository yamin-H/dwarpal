import { el, api, badge, toast, openDialog, confirmAction, showSecret, vault, shared, fmtInt, fmtUsd,
         fmtPct, relTime, progress, pageHead, errorBox, emptyBox, knownModels, reportError } from "./lib.js";

const DEMOS = [
  { id: "islamic-app", name: "Islamic app" },
  { id: "bank-app", name: "Bank app" },
  { id: "music-app", name: "Music app" },
];
const KEY_KIND = { active: "ok", expiring: "warn", expired: "muted", revoked: "err" };

export function render(root, ctx) {
  return ctx.arg ? detail(root, ctx.arg, ctx) : list(root, ctx);
}

// ---------- shared form ----------
function field(label, input, hint) {
  return el("label", { class: "field" }, el("span", { class: "field-label" }, label), input,
    hint ? el("span", { class: "hint" }, hint) : null);
}
const checkField = (label, input) => el("label", { class: "check" }, input, ` ${label}`);

function tenantForm(initial, creating) {
  const f = {
    id: el("input", { type: "text", maxlength: 40, placeholder: "e.g. islamic-app", disabled: !creating, value: initial.id || "" }),
    name: el("input", { type: "text", maxlength: 100, value: initial.name || "" }),
    models: el("input", { type: "text", value: (initial.allowed_models || ["auto", "mock-echo"]).join(", ") }),
    cache: el("input", { type: "checkbox", checked: initial.cache_enabled !== false }),
    fallback: el("input", { type: "checkbox", checked: initial.allow_fallback !== false }),
    threshold: el("input", { type: "number", step: "0.01", min: "0.5", max: "1", placeholder: "global default", value: initial.semantic_threshold ?? "" }),
    tokens: el("input", { type: "number", step: "1", min: "1", placeholder: "no limit", value: initial.monthly_token_budget ?? "" }),
    cost: el("input", { type: "number", step: "0.01", min: "0.01", placeholder: "no limit", value: initial.monthly_cost_budget_usd ?? "" }),
  };
  const node = el("div", { class: "form-grid" },
    creating ? field("Tenant id", f.id, "3-40 characters: lowercase letters, digits, dashes.") : null,
    field("Name", f.name),
    field("Allowed models", f.models, `Comma-separated, or * for all. Known: ${knownModels().join(", ")}`),
    field("Semantic threshold", f.threshold, "0.5 to 1. Empty uses the global default."),
    field("Monthly token budget", f.tokens, "Empty means no limit."),
    field("Monthly cost budget (USD)", f.cost, "Empty means no limit."),
    el("div", {}, checkField("Caching enabled", f.cache), checkField("Allow fallback providers", f.fallback)));

  function read() {
    const name = f.name.value.trim();
    if (!name) throw new Error("Name is required.");
    const models = f.models.value.split(",").map((m) => m.trim()).filter(Boolean);
    if (!models.length) throw new Error("Enter at least one allowed model (or *).");
    const num = (input, label, min, integer) => {
      const raw = input.value.trim();
      if (raw === "") return null;
      const n = Number(raw);
      if (!Number.isFinite(n) || n < min || (integer && !Number.isInteger(n))) throw new Error(`${label} is not valid.`);
      return n;
    };
    const payload = {
      name, allowed_models: models, cache_enabled: f.cache.checked, allow_fallback: f.fallback.checked,
      semantic_threshold: num(f.threshold, "Semantic threshold", 0.5, false),
      monthly_token_budget: num(f.tokens, "Token budget", 1, true),
      monthly_cost_budget_usd: num(f.cost, "Cost budget", 0.01, false),
    };
    if (payload.semantic_threshold !== null && payload.semantic_threshold > 1) {
      throw new Error("Semantic threshold must be between 0.5 and 1.");
    }
    if (creating) {
      const id = f.id.value.trim();
      if (!/^[a-z0-9][a-z0-9-]{2,39}$/.test(id)) throw new Error("Tenant id: 3-40 characters, lowercase letters, digits, dashes.");
      payload.id = id;
    }
    return payload;
  }
  return { node, read };
}

async function issueKey(tenantId, note) {
  const issued = (await api(`/admin/tenants/${tenantId}/keys`, { method: "POST" })).data;
  vault.setTenantKey(tenantId, issued.api_key);
  await showSecret("API key issued", issued.api_key,
    note || "Copy it now: it is shown once. It was also saved in this browser so the playground can use it.");
  return issued;
}

// ---------- list ----------
async function list(root, ctx) {
  const holder = el("div");

  async function demoSetup() {
    try {
      const lines = [];
      for (const d of DEMOS) {
        try {
          await api("/admin/tenants", { method: "POST", body: { id: d.id, name: d.name } });
          lines.push(`${d.name} created`);
        } catch (err) {
          if (err.status !== 409) throw err;
        }
        if (!vault.tenants[d.id]) {
          const issued = (await api(`/admin/tenants/${d.id}/keys`, { method: "POST" })).data;
          vault.setTenantKey(d.id, issued.api_key);
          lines.push(`${d.name} key saved in this browser`);
        }
      }
      toast(lines.length ? lines.join(" \u00b7 ") : "Demo tenants are ready.", "ok");
      await load();
    } catch (err) { reportError(err); }
  }

  async function createFlow() {
    const form = tenantForm({}, true);
    const message = el("p", { class: "form-error", role: "alert" });
    let created = null;
    await openDialog("New tenant", el("div", {}, form.node, message), [
      { label: "Cancel", value: false },
      {
        label: "Create and issue key", primary: true, value: true,
        onclick: async () => {
          try {
            const payload = form.read();
            await api("/admin/tenants", { method: "POST", body: payload });
            const issued = (await api(`/admin/tenants/${payload.id}/keys`, { method: "POST" })).data;
            vault.setTenantKey(payload.id, issued.api_key);
            created = { id: payload.id, key: issued.api_key };
            return true;
          } catch (err) { message.textContent = err.message; return false; }
        },
      },
    ]);
    if (created) {
      await showSecret("API key issued", created.key, "Copy it now: it is shown once. It was also saved in this browser.");
      ctx.navigate(`#/tenants/${created.id}`);
    }
  }

  function budgetCell(t) {
    const lines = [];
    if (t.monthly_token_budget) {
      lines.push(el("div", { class: "budget-line" }, `${fmtInt(t.month_tokens)} / ${fmtInt(t.monthly_token_budget)} tokens`,
        progress(t.month_tokens, t.monthly_token_budget)));
    }
    if (t.monthly_cost_budget_usd) {
      lines.push(el("div", { class: "budget-line" }, `${fmtUsd(t.month_cost_usd)} / ${fmtUsd(t.monthly_cost_budget_usd)}`,
        progress(t.month_cost_usd, t.monthly_cost_budget_usd)));
    }
    return lines.length ? lines : el("span", { class: "muted" }, "No limit");
  }

  function table(tenants) {
    return el("div", { class: "card table-wrap" }, el("table", {},
      el("thead", {}, el("tr", {}, ...["Tenant", "Status", "Models", "Cache", "Budget this month"].map((h) => el("th", {}, h)),
        ...["Requests", "Spend"].map((h) => el("th", { class: "num" }, h)), el("th", {}, "Keys"))),
      el("tbody", {}, tenants.map((t) => {
        const go = () => ctx.navigate(`#/tenants/${t.id}`);
        return el("tr", { class: "clickable", tabindex: 0, onclick: go, onkeydown: (e) => { if (e.key === "Enter") go(); } },
          el("td", {}, el("strong", {}, t.name), el("div", { class: "muted" }, el("code", {}, t.id))),
          el("td", {}, t.active ? badge("active", "ok") : badge("disabled", "err")),
          el("td", {}, t.allowed_models.join(", ")),
          el("td", {}, t.cache_enabled ? badge("on", "ok") : badge("off", "muted")),
          el("td", {}, budgetCell(t)),
          el("td", { class: "num" }, fmtInt(t.requests)), el("td", { class: "num" }, fmtUsd(t.cost_usd)),
          el("td", {}, `${t.active_keys} `, vault.tenants[t.id] ? badge("in browser", "info") : null));
      }))));
  }

  async function load() {
    try {
      const { tenants } = (await api("/admin/tenants")).data;
      holder.replaceChildren(tenants.length ? table(tenants)
        : emptyBox("No tenants yet", "A tenant is one app or customer with its own keys, budgets and cache. Create the three demo tenants to start testing.",
            el("button", { class: "btn primary", type: "button", onclick: demoSetup }, "Set up demo tenants")));
    } catch (err) { reportError(err); holder.replaceChildren(errorBox(err.message)); }
  }

  root.append(pageHead("Tenants", "Each tenant has its own keys, models, budgets and cache.",
    el("button", { class: "btn", type: "button", onclick: demoSetup }, "Demo setup"),
    el("button", { class: "btn primary", type: "button", onclick: createFlow }, "New tenant")), holder);
  await load();
}

// ---------- detail ----------
async function detail(root, id, ctx) {
  async function show() {
    let tenant, keys, usage;
    try {
      [tenant, keys, usage] = (await Promise.all([
        api(`/admin/tenants/${id}`), api(`/admin/tenants/${id}/keys`), api(`/admin/tenants/${id}/usage`),
      ])).map((r) => r.data);
    } catch (err) {
      if (err.status === 404) {
        root.replaceChildren(emptyBox("Tenant not found", `There is no tenant "${id}".`,
          el("a", { class: "btn", href: "#/tenants" }, "Back to tenants")));
        return;
      }
      throw err;
    }
    const form = tenantForm(tenant, false);
    const formError = el("p", { class: "form-error", role: "alert" });
    const month = usage.month_to_date;

    const act = (fn) => async () => { try { await fn(); await show(); } catch (err) { reportError(err); } };

    const toggle = act(async () => {
      if (tenant.active && !(await confirmAction("Disable tenant", `All keys of ${tenant.name} will stop working until you enable it again.`, "Disable", true))) return;
      await api(`/admin/tenants/${id}`, { method: "PATCH", body: { active: !tenant.active } });
      toast(tenant.active ? "Tenant disabled" : "Tenant enabled", "ok");
    });

    const save = async () => {
      try {
        const payload = form.read();
        await api(`/admin/tenants/${id}`, { method: "PATCH", body: payload });
        toast("Settings saved", "ok");
        await show();
      } catch (err) { formError.textContent = err.message; }
    };

    const rotate = (key) => act(async () => {
      const overlap = el("select", {}, [[0, "Immediate cutover"], [60, "1 minute"], [3600, "1 hour"], [86400, "24 hours"]]
        .map(([v, l]) => el("option", { value: v, selected: v === 86400 }, l)));
      const ok = await openDialog("Rotate key", el("div", {}, el("p", { class: "muted" }, `A new key is issued. The old key (${key.prefix}\u2026) keeps working for the overlap window.`), field("Keep the old key valid for", overlap)),
        [{ label: "Cancel", value: false }, { label: "Rotate", value: true, primary: true }]);
      if (!ok) return;
      const rotated = (await api(`/admin/keys/${key.key_id}/rotate`, { method: "POST", body: { overlap_seconds: Number(overlap.value) } })).data;
      vault.setTenantKey(id, rotated.api_key);
      await showSecret("New API key", rotated.api_key, `Copy it now. The old key stops working at ${new Date(rotated.old_key_expires_at).toLocaleString()}.`);
    });

    const revoke = (key) => act(async () => {
      if (!(await confirmAction("Revoke key", `Key ${key.prefix}\u2026 stops working immediately.`, "Revoke", true))) return;
      await api(`/admin/keys/${key.key_id}`, { method: "DELETE" });
      toast("Key revoked", "ok");
    });

    const purge = act(async () => {
      if (!(await confirmAction("Clear cache", `Delete every cached answer of ${tenant.name}? The next questions will call the providers again.`, "Clear cache", true))) return;
      const r = (await api(`/admin/tenants/${id}/cache`, { method: "DELETE" })).data;
      toast(`Cache cleared (${r.exact_deleted} exact entries${r.semantic_cleared ? ", semantic cleared" : ""})`, "ok");
    });

    const statBlock = (label, value, sub) => el("div", { class: "stat" }, el("div", { class: "stat-label" }, label),
      el("div", { class: "stat-value" }, value), sub ? el("div", { class: "stat-sub" }, sub) : null);

    root.replaceChildren(
      pageHead(tenant.name, null,
        el("a", { class: "btn", href: "#/tenants" }, "\u2190 All tenants"),
        el("a", { class: "btn", href: `#/playground/${id}` }, "Open in playground"),
        el("button", { class: tenant.active ? "btn danger" : "btn primary", type: "button", onclick: toggle },
          tenant.active ? "Disable tenant" : "Enable tenant")),
      el("p", { class: "muted" }, el("code", {}, id), " ", tenant.active ? badge("active", "ok") : badge("disabled", "err")),
      el("div", { class: "grid" },
        statBlock("Requests", fmtInt(usage.requests), `${fmtInt(usage.errors)} errors`),
        statBlock("Cache hit rate", fmtPct(usage.cache_hit_rate), `${fmtInt(usage.cache_hits)} hits, ${fmtInt(usage.semantic_hits)} semantic`),
        statBlock("Tokens (all time)", fmtInt(usage.total_tokens), `avg latency ${fmtInt(usage.avg_latency_ms)} ms`),
        statBlock("Spend (all time)", fmtUsd(usage.cost_usd))),
      el("div", { class: "card" }, el("h2", {}, "This month"),
        month.token_budget ? el("div", { class: "budget-line" }, `${fmtInt(month.tokens)} / ${fmtInt(month.token_budget)} tokens`, progress(month.tokens, month.token_budget))
          : el("p", { class: "muted" }, `${fmtInt(month.tokens)} tokens, no token budget`),
        month.cost_budget_usd ? el("div", { class: "budget-line" }, `${fmtUsd(month.cost_usd)} / ${fmtUsd(month.cost_budget_usd)}`, progress(month.cost_usd, month.cost_budget_usd))
          : el("p", { class: "muted" }, `${fmtUsd(month.cost_usd)}, no cost budget`),
        el("p", { class: "hint" }, "Budgets are soft caps: the request that crosses the line is still served. Months follow UTC.")),
      el("div", { class: "card" }, el("h2", {}, "Settings"), form.node, formError,
        el("button", { class: "btn primary", type: "button", onclick: save }, "Save settings")),
      el("div", { class: "card" },
        el("div", { class: "scenario-head" }, el("h2", {}, "API keys"),
          el("div", { class: "toolbar" },
            vault.tenants[id] ? badge("a key is saved in this browser", "info") : badge("no key in this browser", "muted"),
            vault.tenants[id] ? el("button", { class: "btn small", type: "button", onclick: () => { vault.forgetTenant(id); show(); } }, "Forget it") : null,
            el("button", { class: "btn primary small", type: "button", onclick: act(() => issueKey(id)) }, "Issue new key"))),
        el("div", { class: "table-wrap" }, el("table", {},
          el("thead", {}, el("tr", {}, ...["Key", "Status", "Created", "Expires", ""].map((h) => el("th", {}, h)))),
          el("tbody", {}, keys.keys.map((k) => el("tr", {},
            el("td", {}, el("code", {}, `${k.prefix}\u2026`)),
            el("td", {}, badge(k.status, KEY_KIND[k.status])),
            el("td", {}, relTime(k.created_at)),
            el("td", {}, k.expires_at ? new Date(k.expires_at).toLocaleString() : "\u2013"),
            el("td", { class: "num" }, k.status === "active" ? el("button", { class: "btn small", type: "button", onclick: rotate(k) }, "Rotate") : null, " ",
              k.status === "active" || k.status === "expiring" ? el("button", { class: "btn small danger", type: "button", onclick: revoke(k) }, "Revoke") : null)))))),
        el("p", { class: "hint" }, "The full key is shown once, when it is created. Only a hash is stored.")),
      el("div", { class: "card" }, el("h2", {}, "Maintenance"),
        el("p", { class: "muted" }, "Remove this tenant's cached answers, for example after changing a threshold or to repeat a test from a clean state."),
        el("button", { class: "btn danger", type: "button", onclick: purge }, "Clear cache")));
  }
  await show();
}
