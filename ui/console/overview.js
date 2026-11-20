import { el, api, badge, shared, fmtInt, fmtUsd, fmtMs, fmtPct, pageHead, errorBox, stackedBars,
         hbarRow, reportError } from "./lib.js";

const RANGES = [[6, "Last 6 hours"], [24, "Last 24 hours"], [72, "Last 3 days"], [168, "Last 7 days"]];
const LAYERS = [
  { key: "misses", label: "Provider calls", cls: "miss" },
  { key: "hits", label: "Cache hits", cls: "hit" },
  { key: "errors", label: "Errors", cls: "err" },
];
const PROVIDER_NAMES = { cache: "Exact cache", "cache:semantic": "Semantic cache", mock: "Mock provider" };
const providerName = (p) => PROVIDER_NAMES[p] || p.replace(/^litellm:/, "");

const stat = (label, value, sub) => el("div", { class: "stat" },
  el("div", { class: "stat-label" }, label), el("div", { class: "stat-value" }, value),
  sub ? el("div", { class: "stat-sub" }, sub) : null);

function healthStrip(system) {
  const kind = (v) => (v === "ok" ? "ok" : v === "down" ? "err" : "muted");
  const open = Object.values(system.routing.circuits).filter(Boolean).length;
  return el("div", { class: "health", "aria-label": "System health" },
    ...["database", "redis", "qdrant"].map((name) =>
      badge(`${name}: ${system.checks[name]}`, kind(system.checks[name]))),
    open ? badge(`${open} open circuit${open > 1 ? "s" : ""}`, "warn") : badge("no open circuits", "ok"));
}

export async function render(root) {
  let hours = 24;
  let timer = null;
  const content = el("div");
  const select = el("select", {
    "aria-label": "Time range",
    onchange: () => { hours = Number(select.value); refresh(); },
  }, RANGES.map(([v, l]) => el("option", { value: v, selected: v === hours }, l)));
  const auto = el("input", { type: "checkbox", checked: true, onchange: schedule });

  function schedule() {
    if (timer) clearInterval(timer);
    timer = auto.checked ? setInterval(refresh, 10000) : null;
  }

  function draw(o, system) {
    const t = o.totals;
    if (t.requests === 0) {
      content.replaceChildren(healthStrip(system), el("div", { class: "card empty" },
        el("h2", {}, "No traffic in this period yet"),
        el("p", {}, "Create the demo tenants, then send a few questions from the playground or run the self-test."),
        el("div", { class: "toolbar" },
          el("a", { class: "btn primary", href: "#/tenants" }, "Set up demo tenants"),
          el("a", { class: "btn", href: "#/playground" }, "Open playground"),
          el("a", { class: "btn", href: "#/selftest" }, "Run self-test"))));
      return;
    }
    const total = o.by_provider.reduce((s, p) => s + p.requests, 0);
    const points = o.series.map((p) => {
      const d = new Date(p.hour);
      return {
        label: d.toLocaleString(),
        short: hours > 72 ? d.toLocaleDateString([], { month: "short", day: "numeric" })
                          : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        misses: Math.max(p.requests - p.cache_hits - p.errors, 0), hits: p.cache_hits, errors: p.errors,
      };
    });
    content.replaceChildren(
      healthStrip(system),
      el("div", { class: "grid" },
        stat("Requests", fmtInt(t.requests), `${fmtInt(t.errors)} errors`),
        stat("Cache hit rate", fmtPct(t.hit_rate), `${fmtInt(t.cache_hits)} hits, ${fmtInt(t.semantic_hits)} semantic`),
        stat("Latency: hit vs miss", `${fmtMs(t.avg_hit_ms)} vs ${fmtMs(t.avg_miss_ms)}`, "average per request"),
        stat("Tokens", fmtInt(t.tokens), "streamed counts are estimates"),
        stat("Estimated spend", fmtUsd(t.cost_usd), "from the price table")),
      el("div", { class: "card" }, el("h2", {}, "Requests over time"), stackedBars(points, LAYERS),
        el("div", { class: "legend" }, ...LAYERS.map((l) =>
          el("span", {}, el("span", { class: `dot ${l.cls === "miss" ? "miss" : l.cls}` }), l.label)))),
      el("div", { class: "two" },
        el("div", { class: "card" }, el("h2", {}, "Who served the requests"),
          ...o.by_provider.map((p) => hbarRow(providerName(p.provider), p.requests, total,
            `${fmtInt(p.requests)} (${fmtPct(p.requests / total)})`))),
        el("div", { class: "card" }, el("h2", {}, "Top tenants"),
          el("div", { class: "table-wrap" }, el("table", {},
            el("thead", {}, el("tr", {}, el("th", {}, "Tenant"), el("th", { class: "num" }, "Requests"),
              el("th", { class: "num" }, "Tokens"), el("th", { class: "num" }, "Spend"))),
            el("tbody", {}, o.top_tenants.map((r) => el("tr", {},
              el("td", {}, el("a", { href: `#/tenants/${r.tenant_id}` }, r.tenant_id)),
              el("td", { class: "num" }, fmtInt(r.requests)), el("td", { class: "num" }, fmtInt(r.tokens)),
              el("td", { class: "num" }, fmtUsd(r.cost_usd))))))))));
  }

  async function refresh() {
    try {
      const [overview, system] = await Promise.all([
        api(`/admin/overview?hours=${hours}`), api("/admin/system"),
      ]);
      shared.system = system.data;
      draw(overview.data, system.data);
    } catch (err) {
      reportError(err);
      content.replaceChildren(errorBox(err.message));
    }
  }

  root.append(
    pageHead("Overview", "Traffic, cache efficiency and health of the gateway.", select,
      el("label", { class: "check" }, auto, " Auto-refresh")),
    content);
  await refresh();
  schedule();
  return () => { if (timer) clearInterval(timer); };
}
