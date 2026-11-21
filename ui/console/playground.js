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

function inlineNodes(text) {
  const nodes = [];
  const regex = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
  let lastIdx = 0;
  let match;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIdx) {
      nodes.push(document.createTextNode(text.slice(lastIdx, match.index)));
    }
    const m = match[0];
    if (m.startsWith("**") && m.endsWith("**")) {
      nodes.push(el("strong", {}, m.slice(2, -2)));
    } else if (m.startsWith("`") && m.endsWith("`")) {
      nodes.push(el("code", {}, m.slice(1, -1)));
    } else if (m.startsWith("*") && m.endsWith("*")) {
      nodes.push(el("em", {}, m.slice(1, -1)));
    }
    lastIdx = regex.lastIndex;
  }
  if (lastIdx < text.length) {
    nodes.push(document.createTextNode(text.slice(lastIdx)));
  }
  return nodes;
}

function renderMarkdown(raw, container) {
  container.replaceChildren();
  if (!raw) return;
  const lines = raw.split("\n");
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i++;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++;
      container.append(el("pre", { class: "msg-pre" }, el("code", {}, codeLines.join("\n"))));
      continue;
    }

    if (/^(\-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      container.append(el("hr", { class: "msg-hr" }));
      i++;
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const tag = level <= 2 ? "h3" : "h4";
      container.append(el(tag, { class: `msg-h msg-h${level}` }, inlineNodes(headingMatch[2])));
      i++;
      continue;
    }

    if (trimmed.startsWith("|") && trimmed.endsWith("|") && i + 1 < lines.length && /^\|[\s\-:|]+\|$/.test(lines[i + 1].trim())) {
      const headerRow = trimmed.slice(1, -1).split("|").map((c) => c.trim());
      i += 2;
      const bodyRows = [];
      while (i < lines.length && lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|")) {
        bodyRows.push(lines[i].trim().slice(1, -1).split("|").map((c) => c.trim()));
        i++;
      }
      const table = el("table", {},
        el("thead", {}, el("tr", {}, headerRow.map((h) => el("th", {}, inlineNodes(h))))),
        el("tbody", {}, bodyRows.map((row) => el("tr", {}, row.map((cell) => el("td", {}, inlineNodes(cell)))))));
      container.append(el("div", { class: "msg-table-wrap" }, table));
      continue;
    }

    if (/^[\*\-]\s+/.test(trimmed)) {
      const items = [];
      while (i < lines.length && /^[\*\-]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[\*\-]\s+/, ""));
        i++;
      }
      container.append(el("ul", { class: "msg-list" }, items.map((item) => el("li", {}, inlineNodes(item)))));
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
        i++;
      }
      container.append(el("ol", { class: "msg-list" }, items.map((item) => el("li", {}, inlineNodes(item)))));
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quotes = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quotes.push(lines[i].trim().replace(/^>\s?/, ""));
        i++;
      }
      container.append(el("blockquote", { class: "msg-quote" }, inlineNodes(quotes.join(" "))));
      continue;
    }

    const pLines = [trimmed];
    i++;
    while (i < lines.length) {
      const nextTrimmed = lines[i].trim();
      if (!nextTrimmed ||
          nextTrimmed.startsWith("#") ||
          nextTrimmed.startsWith("```") ||
          nextTrimmed.startsWith("|") ||
          /^[\*\-]\s+/.test(nextTrimmed) ||
          /^\d+\.\s+/.test(nextTrimmed) ||
          nextTrimmed.startsWith(">") ||
          /^(\-{3,}|\*{3,}|_{3,})$/.test(nextTrimmed)) {
        break;
      }
      pLines.push(nextTrimmed);
      i++;
    }
    container.append(el("p", { class: "msg-p" }, inlineNodes(pLines.join(" "))));
  }
}

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
        renderMarkdown(reply, answer);
      } else {
        reply = (await res.json()).choices[0].message.content;
        renderMarkdown(reply, answer);
      }
    } catch (err) {
      answer.classList.add("err");
      answer.textContent = "Network error: is the gateway running?";
    } finally {
      busy = false;
      send.disabled = false;
    }
    const total = performance.now() - started;
    const metaItems = [
      cacheBadge(info.cache),
      info.score ? el("span", {}, `score ${info.score}`) : null,
      info.reason ? el("span", {}, `reason: ${info.reason}`) : null,
      info.provider ? el("span", {}, `provider: ${info.provider}`) : null,
      first !== null ? el("span", {}, `first token ${fmtMs(first)}`) : null,
      el("span", {}, `total ${fmtMs(total)}`),
      info.status && info.status !== 200 ? badge(`HTTP ${info.status}`, "err") : null,
      info.id ? el("code", { title: "Search the gateway logs for this id" }, info.id.slice(0, 8)) : null,
    ].filter(Boolean);
    meta.append(...metaItems);
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
