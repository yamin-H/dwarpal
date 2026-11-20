"use strict";

// label -> API key. Memory only: never written to any browser storage.
const tenants = new Map();
const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

function refreshTenants(selected) {
    const select = $("tenant");
    select.replaceChildren();
    for (const label of tenants.keys()) {
        const option = el("option", "", label);
        option.value = label;
        select.appendChild(option);
    }
    if (selected) select.value = selected;
}

function addTenant() {
    const label = $("label").value.trim();
    const key = $("key").value.trim();
    if (!label || !key) return;
    tenants.set(label, key);
    $("key").value = "";
    refreshTenants(label);
}

// Splits an SSE buffer into complete "data:" payloads and the unfinished remainder.
function takeEvents(buffer) {
    const parts = buffer.replace(/\r\n/g, "\n").split("\n\n");
    const rest = parts.pop();
    const events = [];
    for (const part of parts) {
        for (const line of part.split("\n")) {
            if (line.startsWith("data: ")) events.push(line.slice(6));
        }
    }
    return { events, rest };
}

function readMeta(res) {
    return {
        cache: res.headers.get("x-cache"),
        score: res.headers.get("x-cache-score"),
        reason: res.headers.get("x-cache-reason"),
        provider: res.headers.get("x-provider"),
        requestId: res.headers.get("x-request-id"),
    };
}

function showTag(node, meta, totalMs, ttftMs) {
    const parts = ["cache: " + (meta.cache || "n/a")];
    if (meta.score) parts.push("score " + meta.score);
    if (meta.reason) parts.push("reason " + meta.reason);
    if (meta.provider) parts.push("provider " + meta.provider);
    if (ttftMs !== null) parts.push("first token " + Math.round(ttftMs) + " ms");
    parts.push("total " + Math.round(totalMs) + " ms");
    if (meta.requestId) parts.push("id " + meta.requestId.slice(0, 8));
    node.textContent = parts.join("  \u00b7  ");
    node.classList.toggle("hit", (meta.cache || "").startsWith("HIT"));
}

function fail(node, message) {
    node.textContent = message;
    node.classList.add("err");
}

async function readStream(res, answer, onFirstToken) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (; ;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parsed = takeEvents(buffer);
        buffer = parsed.rest;
        for (const data of parsed.events) {
            if (data === "[DONE]") continue;
            let obj;
            try {
                obj = JSON.parse(data);
            } catch (err) {
                continue;
            }
            if (obj.error) {
                answer.classList.add("err");
                answer.textContent += "\n[error: " + obj.error.message + "]";
                continue;
            }
            const piece = obj.choices && obj.choices[0] && obj.choices[0].delta.content;
            if (piece) {
                onFirstToken();
                answer.textContent += piece;
            }
        }
    }
}

async function send() {
    const key = tenants.get($("tenant").value);
    const prompt = $("prompt").value.trim();
    if (!key) {
        window.alert("Add a tenant API key first.");
        return;
    }
    if (!prompt) return;

    const stream = $("stream").checked;
    const headers = { "Content-Type": "application/json", Authorization: "Bearer " + key };
    if ($("bypass").checked) headers["X-Dwarpal-Cache"] = "bypass";
    const body = JSON.stringify({
        model: $("model").value.trim() || "auto",
        stream: stream,
        messages: [{ role: "user", content: prompt }],
    });

    const card = el("article", "card");
    const answer = el("div", "a", "\u2026");
    const tag = el("div", "tag", "");
    card.append(el("div", "q", prompt), answer, tag);
    $("log").prepend(card);

    const button = $("send");
    button.disabled = true;
    const start = performance.now();
    let firstToken = null;
    let meta = {};
    try {
        const res = await fetch("/v1/chat/completions", { method: "POST", headers: headers, body: body });
        meta = readMeta(res);
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            const message = data.error && data.error.message ? data.error.message : "request failed";
            fail(answer, "Error " + res.status + ": " + message);
        } else if (stream) {
            answer.textContent = "";
            await readStream(res, answer, () => {
                if (firstToken === null) firstToken = performance.now() - start;
            });
        } else {
            const data = await res.json();
            answer.textContent = data.choices[0].message.content;
        }
    } catch (err) {
        fail(answer, "Network error: is the gateway running?");
    } finally {
        button.disabled = false;
    }
    showTag(tag, meta, performance.now() - start, firstToken);
}

$("add").addEventListener("click", addTenant);
$("send").addEventListener("click", send);
$("prompt").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) send();
});