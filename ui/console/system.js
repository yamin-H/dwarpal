import { el, api, badge, shared, pageHead, reportError } from "./lib.js";

const row = (k, v) => el("tr", {}, el("td", { class: "muted" }, k), el("td", {}, v));
const yesNo = (v, onText = "yes", offText = "no") => badge(v ? onText : offText, v ? "ok" : "muted");

export async function render(root) {
  const body = el("div");
  async function load() {
    try {
      const s = (await api("/admin/system")).data;
      shared.system = s;
      const checkKind = (v) => (v === "ok" ? "ok" : v === "down" ? "err" : "muted");
      const chains = Object.entries(s.routing.chains);
      body.replaceChildren(
        el("div", { class: "two" },
          el("div", { class: "card" }, el("h2", {}, "Dependencies"), el("table", {}, el("tbody", {},
            ...Object.entries(s.checks).map(([k, v]) => row(k, badge(v, checkKind(v))))))),
          el("div", { class: "card" }, el("h2", {}, "Gateway"), el("table", {}, el("tbody", {},
            row("Version", s.version), row("Environment", s.environment),
            row("Admin console", yesNo(s.features.console)), row("Edge playground", yesNo(s.features.playground)),
            row("Auto migrations", yesNo(s.features.auto_migrate)))))),
        el("div", { class: "two" },
          el("div", { class: "card" }, el("h2", {}, "Caching"), el("table", {}, el("tbody", {},
            row("Exact cache (Redis)", yesNo(s.cache.exact_enabled, "on", "off")),
            row("Semantic cache (Qdrant)", yesNo(s.cache.semantic_enabled, "on", "off")),
            row("Default threshold", s.cache.semantic_enabled ? String(s.cache.semantic_threshold) : "\u2013"),
            row("Embedder", s.cache.embedder ? `${s.cache.embedder} ${s.cache.embedding_model || ""}` : "\u2013"),
            row("Entry lifetime", `${s.cache.ttl_seconds} s`)))),
          el("div", { class: "card" }, el("h2", {}, "Provider API keys"), el("table", {}, el("tbody", {},
            ...Object.entries(s.providers_configured).map(([k, v]) => row(k, yesNo(v, "configured", "not set"))))),
            el("p", { class: "hint" }, "Only whether a key is set is shown, never its value. The mock models need none.")),
        ),
        el("div", { class: "card" }, el("h2", {}, "Routing and circuit breaker"),
          el("p", { class: "muted" }, `A model's circuit opens after ${s.routing.failure_threshold} failures and is probed again after ${s.routing.cooldown_seconds} s.`),
          chains.length ? el("div", { class: "table-wrap" }, el("table", {},
            el("thead", {}, el("tr", {}, el("th", {}, "Requested model"), el("th", {}, "Fallbacks"), el("th", {}, "Circuit"))),
            el("tbody", {}, chains.map(([model, chain]) => el("tr", {},
              el("td", {}, el("code", {}, model)), el("td", {}, chain.join(" \u2192 ") || "\u2013"),
              el("td", {}, s.routing.circuits[model] === undefined ? badge("no calls yet", "muted")
                : s.routing.circuits[model] ? badge("open", "warn") : badge("closed", "ok")))))))
            : el("p", { class: "muted" }, "No fallback chains configured (set DWARPAL_ROUTING_CONFIG).")),
        el("div", { class: "card" }, el("h2", {}, "Price table (USD per million tokens)"),
          el("div", { class: "table-wrap" }, el("table", {},
            el("thead", {}, el("tr", {}, el("th", {}, "Model"), el("th", { class: "num" }, "Input"), el("th", { class: "num" }, "Output"))),
            el("tbody", {}, Object.entries(s.prices).map(([m, p]) => el("tr", {}, el("td", {}, el("code", {}, m)),
              el("td", { class: "num" }, String(p.input_per_million)), el("td", { class: "num" }, String(p.output_per_million)))))))),
        el("div", { class: "card" }, el("h2", {}, "Monitoring"),
          el("p", {}, el("a", { href: "http://localhost:3000", target: "_blank", rel: "noopener noreferrer" }, "Grafana"), " (dashboards), ",
            el("a", { href: "http://localhost:9090/alerts", target: "_blank", rel: "noopener noreferrer" }, "Prometheus alerts"), "."),
          el("p", { class: "hint" }, "Every response carries an X-Request-ID. Search the gateway logs for it: docker compose logs gateway | grep <id>.")));
    } catch (err) { reportError(err); body.replaceChildren(el("div", { class: "card error-card" }, el("p", {}, err.message))); }
  }
  root.append(pageHead("System", "Health, configuration and routing state.",
    el("button", { class: "btn", type: "button", onclick: load }, "Refresh")), body);
  await load();
}
