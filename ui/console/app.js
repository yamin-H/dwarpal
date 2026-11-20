import { $, el, vault, api, shared, badge } from "./lib.js";
import * as overview from "./overview.js";
import * as tenants from "./tenants.js";
import * as playground from "./playground.js";
import * as activity from "./activity.js";
import * as system from "./system.js";
import * as selftest from "./selftest.js";

const PAGES = [
  { id: "overview", label: "Overview", module: overview },
  { id: "tenants", label: "Tenants", module: tenants },
  { id: "playground", label: "Playground", module: playground },
  { id: "activity", label: "Activity", module: activity },
  { id: "system", label: "System", module: system },
  { id: "selftest", label: "Self-test", module: selftest },
];

const app = document.getElementById("app");
let cleanup = null;
let routeToken = 0;
let signedIn = false;

function loginScreen(message) {
  signedIn = false;
  const key = el("input", { type: "password", autocomplete: "off", placeholder: "DWARPAL_ADMIN_KEY" });
  const remember = el("input", { type: "checkbox" });
  const error = el("p", { class: "form-error", role: "alert" }, message || "");
  const button = el("button", { class: "btn primary", type: "button" }, "Connect");
  const connect = async () => {
    const value = key.value.trim();
    if (!value) { error.textContent = "Enter the admin key."; return; }
    button.disabled = true;
    error.textContent = "";
    vault.admin = value;
    vault.persist = remember.checked;
    try {
      shared.system = (await api("/admin/system")).data;
      vault.save();
      showShell();
    } catch (err) {
      vault.admin = "";
      vault.persist = false;
      error.textContent = err.status === 401 ? "That key was not accepted."
        : err.status === 403 ? "The admin API is disabled: set DWARPAL_ADMIN_KEY on the gateway."
        : err.message;
    } finally {
      button.disabled = false;
    }
  };
  button.addEventListener("click", connect);
  key.addEventListener("keydown", (e) => { if (e.key === "Enter") connect(); });
  app.replaceChildren(el("main", { class: "login" }, el("div", { class: "card login-card" },
    el("h1", {}, "Dwarpal Console"),
    el("p", { class: "muted" }, "Sign in with the admin key from your .env file (DWARPAL_ADMIN_KEY)."),
    el("label", { class: "field" }, el("span", { class: "field-label" }, "Admin key"), key),
    el("label", { class: "check" }, remember, " Remember keys in this browser tab until it is closed"),
    error, button,
    el("p", { class: "hint" }, "Keys stay in this page's memory unless you tick the box. Nothing is sent anywhere except to this gateway."))));
  key.focus();
}

function signOut(message) {
  if (cleanup) { try { cleanup(); } catch (err) { /* ignore */ } cleanup = null; }
  vault.clear();
  shared.system = null;
  loginScreen(typeof message === "string" ? message : "");
}

function showShell() {
  signedIn = true;
  const sys = shared.system;
  const nav = el("nav", { class: "nav", "aria-label": "Main" },
    PAGES.map((p) => el("a", { href: `#/${p.id}`, "data-page": p.id }, p.label)));
  app.replaceChildren(el("div", { class: "shell" },
    el("aside", { class: "side" },
      el("div", { class: "brand" }, "Dwarpal", el("span", {}, "Console")),
      nav,
      el("div", { class: "side-foot" },
        badge(sys.environment, "muted"), el("span", { class: "muted" }, `v${sys.version}`),
        el("button", { class: "btn small", type: "button", onclick: () => signOut() }, "Sign out"))),
    el("main", { id: "view", class: "view" })));
  route();
}

async function route() {
  if (!signedIn) return;
  const token = ++routeToken;
  if (cleanup) { try { cleanup(); } catch (err) { /* ignore */ } cleanup = null; }
  const [id, arg] = location.hash.replace(/^#\//, "").split("/");
  const page = PAGES.find((p) => p.id === id) || PAGES[0];
  for (const a of document.querySelectorAll(".nav a")) {
    a.classList.toggle("active", a.getAttribute("data-page") === page.id);
  }
  const view = el("div");
  view.append(el("div", { class: "loading" }, "Loading\u2026"));
  $("#view").replaceChildren(view);
  try {
    view.replaceChildren();
    const result = await page.module.render(view, {
      arg, navigate: (hash) => { location.hash = hash; },
    });
    if (token !== routeToken) { if (typeof result === "function") result(); return; }
    if (typeof result === "function") cleanup = result;
    document.title = `${page.label} \u00b7 Dwarpal Console`;
  } catch (err) {
    if (token !== routeToken) return;
    if (err.status === 401) { signOut("Your session is no longer valid. Sign in again."); return; }
    view.replaceChildren(el("div", { class: "card error-card" },
      el("strong", {}, "Something went wrong"), el("p", {}, err.message || String(err)),
      el("button", { class: "btn", type: "button", onclick: route }, "Retry")));
  }
}

window.addEventListener("hashchange", route);
window.addEventListener("dwarpal:unauthorized", () => signOut("Your session is no longer valid. Sign in again."));

vault.load();
if (vault.admin) {
  api("/admin/system")
    .then(({ data }) => { shared.system = data; showShell(); })
    .catch(() => { vault.clear(); loginScreen(); });
} else {
  loginScreen();
}
