import { el, api, badge, cacheBadge, pageHead, errorBox, relTime, fmtInt, fmtUsd, fmtMs, reportError } from "./lib.js";

export async function render(root) {
  let timer = null;
  let before = null;
  const rows = [];
  const tbody = el("tbody");
  const more = el("button", { class: "btn", type: "button", onclick: () => load(true) }, "Load more");
  const status = el("select", { "aria-label": "Status", onchange: () => load(false) },
    [["", "All statuses"], ["ok", "Successful"], ["error", "Errors"]].map(([v, l]) => el("option", { value: v }, l)));
  const tenant = el("select", { "aria-label": "Tenant", onchange: () => load(false) }, el("option", { value: "" }, "All tenants"));
  const auto = el("input", { type: "checkbox", onchange: schedule });
  const note = el("p", { class: "hint" }, "Prompts and answers are never stored, so this log shows metadata only.");

  function draw() {
    tbody.replaceChildren(...rows.map((r) => el("tr", {},
      el("td", { title: r.created_at }, relTime(r.created_at)),
      el("td", {}, r.tenant_id),
      el("td", {}, r.model, r.served_model && r.served_model !== r.model ? el("div", { class: "muted" }, `\u2192 ${r.served_model}`) : null),
      el("td", {}, r.provider || "\u2013"),
      el("td", {}, r.cache ? cacheBadge(r.cache) : "\u2013"),
      el("td", {}, r.status === "ok" ? badge("ok", "ok") : badge(r.status, "err")),
      el("td", { class: "num" }, fmtInt(r.prompt_tokens + r.completion_tokens)),
      el("td", { class: "num" }, fmtUsd(r.cost_usd)),
      el("td", { class: "num" }, fmtMs(r.latency_ms)))));
    if (!rows.length) tbody.replaceChildren(el("tr", {}, el("td", { colspan: 9, class: "muted" }, "No requests match.")));
  }

  async function load(append) {
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (status.value) params.set("status", status.value);
      if (tenant.value) params.set("tenant_id", tenant.value);
      if (append && before) params.set("before_id", String(before));
      const { requests, next_before_id } = (await api(`/admin/requests?${params}`)).data;
      if (!append) rows.length = 0;
      rows.push(...requests);
      before = next_before_id;
      more.hidden = !before;
      draw();
    } catch (err) { reportError(err); }
  }

  function schedule() {
    if (timer) clearInterval(timer);
    timer = auto.checked ? setInterval(() => load(false), 5000) : null;
  }

  const { tenants } = (await api("/admin/tenants")).data;
  tenants.forEach((t) => tenant.append(el("option", { value: t.id }, t.id)));
  root.append(
    pageHead("Activity", "The most recent requests handled by the gateway.", tenant, status,
      el("label", { class: "check" }, auto, " Live (5 s)")),
    el("div", { class: "card table-wrap" }, el("table", {},
      el("thead", {}, el("tr", {}, ...["Time", "Tenant", "Model", "Served by", "Cache", "Status"].map((h) => el("th", {}, h)),
        ...["Tokens", "Cost", "Latency"].map((h) => el("th", { class: "num" }, h)))), tbody), note),
    more);
  await load(false);
  return () => { if (timer) clearInterval(timer); };
}
