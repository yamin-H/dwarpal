import { el, api, badge, cacheBadge, toast, vault, takeEvents, pageHead, emptyBox, knownModels,
         fmtMs, reportError } from "./lib.js";

const SAMPLES = [
  ["Banglish", "zakat koto taka dite hoy"],
  ["Bangla", "যাকাত কত টাকা দিতে হয়"],
  ["English", "How much zakat do I have to pay?"],
  ["Gold", "zakat on gold"],
  ["Silver", "zakat on silver"],
  ["Personal data", "call me on 01712345678"],
  ["Time-sensitive", "namaz er time ajke koyta"],
];

export async function render(root, ctx) {
  const { tenants } = (await api("/admin/tenants")).data;
  if (!tenants.length) {
    root.append(pageHead("Playground"), emptyBox("No tenants yet", "Create the demo tenants first.",
      el("a", { class: "btn primary", href: "#/tenants" }, "Go to Tenants")));
    return;
  }
  const history = [];
  let busy = false;
  let lastPrompt = "";

  const tenantSel = el("select", { "aria-label": "Tenant", onchange: showKeyState }, tenants.map((t) =>
    el("option", { value: t.id }, `${t.name} (${t.id})${vault.tenants[t.id] ? "" : " - no key here"}`)));
  const wanted = ctx.arg && tenants.some((t) => t.id === ctx.arg) ? ctx.arg
    : (tenants.find((t) => vault.tenants[t.id]) || tenants[0]).id;
  tenantSel.value = wanted;

  const keyState = el("div", { class: "hint" });
  const model = el("input", { type: "text", value: "auto", list: "model-list", "aria-label": "Model" });
  const models = el("datalist", { id: "model-list" }, knownModels().map((m) => el("option", { value: m })));
  const stream = el("input", { type: "checkbox", checked: true });
  const bypass = el("input", { type: "checkbox" });
  const keep = el("input", { type: "checkbox" });
  const system = el("textarea", { rows: 2, placeholder: "Optional system prompt" });
  const prompt = el("textarea", { rows: 3, placeholder: "Ask in Bangla, English or Banglish. Ctrl+Enter sends.", "aria-label": "Question" });
  const send = el("button", { class: "btn primary", type: "button", onclick: () => ask(prompt.value) }, "Send");
  const log = el("div", { class: "chat", "aria-live": "polite" });

  function showKeyState() {
    const id = tenantSel.value;
    keyState.replaceChildren();
    if (vault.tenants[id]) { keyState.append(badge("key ready", "ok")); return; }
    keyState.append(badge("no key in this browser", "warn"), " ",
      el("button", { class: "btn small", type: "button", onclick: async () => {
        try {
          const issued = (await api(`/admin/tenants/${id}/keys`, { method: "POST" })).data;
          vault.setTenantKey(id, issued.api_key);
          toast("Key issued and saved in this browser", "ok");
          showKeyState();
        } catch (err) { reportError(err); }
      } }, "Issue key"));
  }

  async function readStream(res, answer, onFirst) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let text = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = takeEvents(buffer);
      buffer = parsed.rest;
      for (const data of parsed.events) {
        if (data === "[DONE]") continue;
        let obj;
        try { obj = JSON.parse(data); } catch (err) { continue; }
        if (obj.error) { answer.classList.add("err"); answer.textContent += `\n[error: ${obj.error.message}]`; continue; }
        const piece = obj.choices && obj.choices[0] && obj.choices[0].delta.content;
        if (piece) { onFirst(); text += piece; answer.textContent = text; }
      }
    }
    return text;
  }

  async function ask(raw) {
    const text = raw.trim();
    if (!text || busy) return;
    const key = vault.tenants[tenantSel.value];
    if (!key) { toast('No API key for this tenant in this browser. Use "Issue key".', "err"); return; }
    lastPrompt = text;
    const messages = [];
    if (system.value.trim()) messages.push({ role: "system", content: system.value.trim() });
    if (keep.checked) messages.push(...history);
    messages.push({ role: "user", content: text });
    const headers = { "Content-Type": "application/json", Authorization: `Bearer ${key}` };
    if (bypass.checked) headers["X-Dwarpal-Cache"] = "bypass";

    const answer = el("div", { class: "msg-a" }, "\u2026");
    const meta = el("div", { class: "msg-meta" });
    log.prepend(el("article", { class: "card" }, el("div", { class: "msg-q" }, text), answer, meta));
    busy = true;
    send.disabled = true;
    const started = performance.now();
    let first = null;
    let info = {};
    let reply = "";
    try {
      const res = await fetch("/v1/chat/completions", {
        method: "POST", headers,
        body: JSON.stringify({ model: model.value.trim() || "auto", stream: stream.checked, messages }),
      });
      info = {
        cache: res.headers.get("x-cache"), score: res.headers.get("x-cache-score"),
        reason: res.headers.get("x-cache-reason"), provider: res.headers.get("x-provider"),
        id: res.headers.get("x-request-id"), status: res.status,
      };
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        answer.classList.add("err");
        answer.textContent = `Error ${res.status}: ${data.error ? data.error.message : "request failed"}`;
      } else if (stream.checked) {
        answer.textContent = "";
        reply = await readStream(res, answer, () => { if (first === null) first = performance.now() - started; });
      } else {
        reply = (await res.json()).choices[0].message.content;
        answer.textContent = reply;
      }
    } catch (err) {
      answer.classList.add("err");
      answer.textContent = "Network error: is the gateway running?";
    } finally {
      busy = false;
      send.disabled = false;
    }
    const total = performance.now() - started;
    meta.append(cacheBadge(info.cache),
      info.score ? el("span", {}, `score ${info.score}`) : null,
      info.reason ? el("span", {}, `reason: ${info.reason}`) : null,
      info.provider ? el("span", {}, `provider: ${info.provider}`) : null,
      first !== null ? el("span", {}, `first token ${fmtMs(first)}`) : null,
      el("span", {}, `total ${fmtMs(total)}`),
      info.status && info.status !== 200 ? badge(`HTTP ${info.status}`, "err") : null,
      info.id ? el("code", { title: "Search the gateway logs for this id" }, info.id.slice(0, 8)) : null);
    if (keep.checked && reply) history.push({ role: "user", content: text }, { role: "assistant", content: reply });
  }

  root.append(
    pageHead("Playground", "Chat as a tenant and watch what the gateway does with each question.",
      el("button", { class: "btn", type: "button", onclick: () => { history.length = 0; log.replaceChildren(); } }, "Clear chat")),
    el("div", { class: "split" },
      el("div", { class: "card" },
        field("Tenant", tenantSel), keyState,
        field("Model", model), models,
        el("label", { class: "check" }, stream, " Stream the answer"),
        el("label", { class: "check" }, bypass, " Bypass cache"),
        el("label", { class: "check" }, keep, " Keep conversation (multi-turn)"),
        el("p", { class: "hint" }, "Multi-turn questions skip the semantic cache by design. Requests go straight to the gateway, not through Kong."),
        field("System prompt", system)),
      el("div", {},
        el("div", { class: "card" }, prompt,
          el("div", { class: "chips" }, SAMPLES.map(([label, text]) =>
            el("button", { class: "chip", type: "button", title: text, onclick: () => { prompt.value = text; prompt.focus(); } }, label))),
          el("div", { class: "toolbar" }, send,
            el("button", { class: "btn", type: "button", onclick: () => ask(lastPrompt) }, "Repeat last"))),
        log)));
  prompt.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) ask(prompt.value); });
  showKeyState();
}

function field(label, input) {
  return el("label", { class: "field" }, el("span", { class: "field-label" }, label), input);
}
