export const shared = { system: null };

const SVG_NS = "http://www.w3.org/2000/svg";
export const $ = (selector, root = document) => root.querySelector(selector);

export function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "style" || key === "srcdoc") throw new Error(`"${key}" is blocked by the CSP`);
    if (key === "class") node.className = value;
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2), value);
    } else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function svgEl(tag, attrs, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, String(value));
  for (const child of children.flat()) {
    if (child) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// ---------- key vault: memory only, unless the user opts in to sessionStorage ----------
const STORE = { persist: "dwarpal.persist", admin: "dwarpal.admin", tenants: "dwarpal.tenants" };

export const vault = {
  admin: "",
  tenants: {},
  persist: false,
  load() {
    try {
      if (sessionStorage.getItem(STORE.persist) !== "1") return;
      this.persist = true;
      this.admin = sessionStorage.getItem(STORE.admin) || "";
      this.tenants = JSON.parse(sessionStorage.getItem(STORE.tenants) || "{}");
    } catch (err) {
      this.tenants = {};
    }
  },
  save() {
    try {
      if (this.persist) {
        sessionStorage.setItem(STORE.persist, "1");
        sessionStorage.setItem(STORE.admin, this.admin);
        sessionStorage.setItem(STORE.tenants, JSON.stringify(this.tenants));
      } else {
        for (const k of Object.values(STORE)) sessionStorage.removeItem(k);
      }
    } catch (err) {
      /* storage unavailable: keep memory only */
    }
  },
  setTenantKey(id, key) { this.tenants[id] = key; this.save(); },
  forgetTenant(id) { delete this.tenants[id]; this.save(); },
  clear() { this.admin = ""; this.tenants = {}; this.persist = false; this.save(); },
};

// ---------- API client ----------
export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function describeDetail(detail) {
  if (!Array.isArray(detail)) return String(detail);
  return detail
    .map((d) => `${(d.loc || []).filter((p) => p !== "body").join(".")}: ${d.msg}`)
    .join("; ");
}

export async function api(path, { method = "GET", body, key, headers = {} } = {}) {
  const token = key === undefined ? vault.admin : key;
  const init = { method, headers: { ...headers } };
  if (token) init.headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch (err) {
    throw new ApiError(0, "network", "Cannot reach the gateway. Is it running?");
  }
  const raw = await res.text();
  let data = null;
  try { data = raw ? JSON.parse(raw) : null; } catch (err) { data = null; }
  if (!res.ok) {
    const e = data && data.error ? data.error : null;
    const message = e ? e.message : data && data.detail ? describeDetail(data.detail) : `HTTP ${res.status}`;
    throw new ApiError(res.status, e ? e.code : "http_error", message);
  }
  return { data, headers: res.headers };
}

// Splits an SSE buffer into complete "data:" payloads and the unfinished remainder.
export function takeEvents(buffer) {
  const parts = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = parts.pop();
  const events = [];
  for (const part of parts) {
    for (const line of part.split("\n")) if (line.startsWith("data: ")) events.push(line.slice(6));
  }
  return { events, rest };
}

// ---------- formatting ----------
const numberFormat = new Intl.NumberFormat("en-US");
export const fmtInt = (n) => numberFormat.format(Math.round(n || 0));
export function fmtUsd(n) {
  const v = n || 0;
  if (v === 0) return "$0";
  if (v < 0.01) return "$" + v.toFixed(6).replace(/0+$/, "");
  return "$" + v.toFixed(v < 1 ? 4 : 2);
}
export const fmtMs = (ms) => {
  if (ms === null || ms === undefined) return "\u2013";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`;
};
export const fmtPct = (n) => `${Math.round((n || 0) * 1000) / 10}%`;
export function relTime(iso) {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${Math.floor(seconds)}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

// ---------- UI pieces ----------
export const badge = (text, kind = "muted") => el("span", { class: `badge ${kind}` }, text);
const CACHE_KIND = { HIT: "ok", "HIT-SEMANTIC": "info", MISS: "muted", SKIP: "warn",
                     BYPASS: "warn", DISABLED: "muted" };
export const cacheBadge = (value) => badge(value || "n/a", CACHE_KIND[value] || "muted");

export function toast(message, kind = "info") {
  const node = el("div", { class: `toast ${kind}`, role: "status" }, message);
  document.getElementById("toasts").append(node);
  setTimeout(() => node.remove(), kind === "err" ? 7000 : 3500);
}

export function reportError(err) {
  if (err && err.status === 401) window.dispatchEvent(new Event("dwarpal:unauthorized"));
  else toast((err && err.message) || String(err), "err");
}

export const pageHead = (title, subtitle, ...actions) =>
  el("div", { class: "page-head" },
    el("div", {}, el("h1", {}, title), subtitle ? el("p", { class: "muted" }, subtitle) : null),
    el("div", { class: "toolbar" }, actions));

export const errorBox = (message) => el("div", { class: "card error-card" }, el("p", {}, message));

export const emptyBox = (title, text, ...actions) =>
  el("div", { class: "card empty" }, el("h2", {}, title), el("p", {}, text),
    el("div", { class: "toolbar" }, actions));

export async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (err) { return false; }
}

export function knownModels() {
  const system = shared.system;
  const names = new Set(["auto", "mock-echo"]);
  if (system) {
    Object.keys(system.prices || {}).forEach((m) => names.add(m));
    Object.entries((system.routing && system.routing.chains) || {}).forEach(([m, chain]) => {
      names.add(m);
      chain.forEach((c) => names.add(c));
    });
  }
  return [...names];
}

export function openDialog(title, content, buttons = [{ label: "Close" }]) {
  return new Promise((resolve) => {
    const dialog = el("dialog", { class: "dlg" });
    const close = (value) => { dialog.close(); dialog.remove(); resolve(value); };
    const actions = el("div", { class: "dlg-actions" }, buttons.map((b) =>
      el("button", {
        class: b.primary ? "btn primary" : b.danger ? "btn danger" : "btn",
        type: "button",
        onclick: async () => {
          if (b.onclick && (await b.onclick()) === false) return;  // false keeps the dialog open
          close(b.value !== undefined ? b.value : b.label);
        },
      }, b.label)));
    dialog.append(el("h3", {}, title), content, actions);
    dialog.addEventListener("cancel", () => { dialog.remove(); resolve(null); });
    document.body.append(dialog);
    dialog.showModal();
  });
}

export const confirmAction = (title, message, label = "Confirm", danger = false) =>
  openDialog(title, el("p", {}, message), [
    { label: "Cancel", value: false },
    { label, value: true, danger, primary: !danger },
  ]);

export function showSecret(title, secret, note) {
  const copy = el("button", {
    class: "btn", type: "button",
    onclick: async () => toast((await copyText(secret)) ? "Copied" : "Copy failed: select the text", "info"),
  }, "Copy");
  return openDialog(title, el("div", {},
    el("p", { class: "muted" }, note),
    el("div", { class: "secret-row" }, el("code", { class: "secret" }, secret), copy)),
  [{ label: "Done", primary: true }]);
}

export function progress(value, max) {
  const ratio = max > 0 ? value / max : 0;
  const fill = el("div", {
    class: "progress-fill" + (ratio >= 1 ? " over" : ratio >= 0.8 ? " near" : ""),
  });
  fill.style.width = `${Math.min(ratio, 1) * 100}%`;
  return el("div", {
    class: "progress", role: "progressbar", "aria-valuemin": 0, "aria-valuemax": 100,
    "aria-valuenow": Math.round(Math.min(ratio, 1) * 100),
  }, fill);
}

export function stackedBars(points, layers, { width = 720, height = 170 } = {}) {
  const pad = { l: 40, r: 8, t: 8, b: 22 };
  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;
  const max = Math.max(1, ...points.map((p) => layers.reduce((s, l) => s + (p[l.key] || 0), 0)));
  const slot = innerW / Math.max(points.length, 1);
  const barW = Math.max(1, slot * 0.7);
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart", role: "img",
                             "aria-label": "Requests over time" });
  [0, 0.5, 1].forEach((f) => {
    const y = pad.t + innerH * (1 - f);
    svg.append(
      svgEl("line", { x1: pad.l, x2: width - pad.r, y1: y, y2: y, class: "grid" }),
      svgEl("text", { x: pad.l - 6, y: y + 4, class: "axis", "text-anchor": "end" }, fmtInt(max * f)),
    );
  });
  const every = Math.ceil(points.length / 8);
  points.forEach((p, i) => {
    const x = pad.l + i * slot + (slot - barW) / 2;
    const tip = `${p.label}\n` + layers.map((l) => `${l.label}: ${fmtInt(p[l.key])}`).join("\n");
    const group = svgEl("g", {}, svgEl("title", {}, tip));
    let y = pad.t + innerH;
    for (const layer of layers) {
      const h = (innerH * (p[layer.key] || 0)) / max;
      if (h <= 0) continue;
      y -= h;
      group.append(svgEl("rect", { x, y, width: barW, height: h, class: layer.cls }));
    }
    svg.append(group);
    if (i % every === 0) {
      svg.append(svgEl("text", { x: x + barW / 2, y: height - 6, class: "axis",
                                 "text-anchor": "middle" }, p.short));
    }
  });
  return svg;
}

export function hbarRow(label, value, total, sub) {
  const fill = el("div", { class: "hbar-fill" });
  fill.style.width = `${total > 0 ? (value / total) * 100 : 0}%`;
  return el("div", { class: "hrow" },
    el("div", { class: "hrow-top" }, el("span", {}, label),
      el("span", { class: "muted" }, sub || fmtInt(value))),
    el("div", { class: "hbar" }, fill));
}
