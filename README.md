<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0b1220,50:1d4ed8,100:06b6d4&height=200&section=header&animation=fadeIn" alt="Dwarpal banner" width="100%" />

<h1>🛡️ Dwarpal (দ্বারপাল)</h1>

<h3>The High-Performance Multi-Tenant LLM Gateway & Resilient Semantic Cache</h3>

<a href="https://github.com/your-username/dwarpal">
  <img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=20&duration=3200&pause=900&color=22D3EE&center=true&vCenter=true&repeat=true&width=760&height=40&lines=Zero-Downtime+Resilience;Strict+Cost+Governance;Sub-Millisecond+Semantic+Caching;Bangla,+English+%26+Banglish+(Code-Mixed)" alt="Typing animation" />
</a>

<br/>

*Engineered for zero-downtime resilience, strict cost governance, and sub-millisecond semantic caching across Bangla, English, and Banglish (code-mixed) queries.*

<br/>

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white&labelColor=0f172a)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white&labelColor=0f172a)](https://fastapi.tiangolo.com)
[![Kong](https://img.shields.io/badge/Kong_Gateway-3.7-003459?style=flat-square&logo=kong&logoColor=white&labelColor=0f172a)](https://konghq.com)
[![Redis](https://img.shields.io/badge/Redis-7.0-DC382D?style=flat-square&logo=redis&logoColor=white&labelColor=0f172a)](https://redis.io)
[![Qdrant](https://img.shields.io/badge/Qdrant-1.12-D62B54?style=flat-square&logo=qdrant&logoColor=white&labelColor=0f172a)](https://qdrant.tech)

[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white&labelColor=0f172a)](https://postgresql.org)
[![Prometheus](https://img.shields.io/badge/Prometheus-v2.53-E6522C?style=flat-square&logo=prometheus&logoColor=white&labelColor=0f172a)](https://prometheus.io)
[![Grafana](https://img.shields.io/badge/Grafana-Ready-F46800?style=flat-square&logo=grafana&logoColor=white&labelColor=0f172a)](https://grafana.com)
[![License](https://img.shields.io/badge/License-Apache--2.0-22c55e?style=flat-square&labelColor=0f172a)](LICENSE)

<br/>

<a href="#overview"><img src="https://img.shields.io/badge/OVERVIEW-0ea5e9?style=for-the-badge" alt="Overview" /></a>
<a href="#architecture"><img src="https://img.shields.io/badge/ARCHITECTURE-2563eb?style=for-the-badge" alt="Architecture" /></a>
<a href="#capabilities"><img src="https://img.shields.io/badge/CAPABILITIES-4f46e5?style=for-the-badge" alt="Capabilities" /></a>
<a href="#interfaces"><img src="https://img.shields.io/badge/INTERFACES-7c3aed?style=for-the-badge" alt="Interfaces" /></a>
<a href="#quickstart"><img src="https://img.shields.io/badge/QUICKSTART-9333ea?style=for-the-badge" alt="Quickstart" /></a>
<a href="#benchmarks"><img src="https://img.shields.io/badge/BENCHMARKS-c026d3?style=for-the-badge" alt="Benchmarks" /></a>
<a href="#configuration"><img src="https://img.shields.io/badge/CONFIG-db2777?style=for-the-badge" alt="Configuration" /></a>
<a href="#security"><img src="https://img.shields.io/badge/SECURITY-e11d48?style=for-the-badge" alt="Security" /></a>
<a href="#runbook"><img src="https://img.shields.io/badge/RUNBOOK-ea580c?style=for-the-badge" alt="Runbook" /></a>

<br/><br/>

<img src="https://img.shields.io/badge/L1_HIT_TTFT_p50-79.6_ms-0ea5e9?style=for-the-badge&labelColor=0f172a" alt="L1 HIT TTFT p50 79.6 ms" />
<img src="https://img.shields.io/badge/False_Positives_@_0.97-0.00%25-22c55e?style=for-the-badge&labelColor=0f172a" alt="0.00% false positives at threshold 0.97" />
<img src="https://img.shields.io/badge/Outage_HTTP_200-75_of_75-8b5cf6?style=for-the-badge&labelColor=0f172a" alt="75 of 75 HTTP 200 during outage" />
<img src="https://img.shields.io/badge/Failing_Upstream_Calls_Avoided-93.3%25-f97316?style=for-the-badge&labelColor=0f172a" alt="93.3% calls avoided failing upstream" />

</div>

<!--
  OPTIONAL: drop a demo GIF / screenshot of the console here.
  <p align="center">
    <img src="docs/assets/console-demo.gif" alt="Dwarpal Admin Console demo" width="90%" />
  </p>
-->

<br/>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0ea5e9,100:6366f1&height=2" width="100%" alt="" />

<h2 align="center" id="overview">📌 Executive Summary</h2>

Modern product teams integrating LLM capabilities directly into backend microservices inevitably hit four critical architectural bottlenecks:

<table>
<tr>
<td width="50%" valign="top">

**🔑 1. API Key Sprawl & Security Risks**

Unmanaged provider credentials hardcoded across teams, lacking instant revocation or overlap rotation.

</td>
<td width="50%" valign="top">

**💸 2. Runaway Operational Costs**

Identical or semantically equivalent prompts repeatedly hit costly upstream LLMs.

</td>
</tr>
<tr>
<td width="50%" valign="top">

**🔌 3. Provider Outage Fragility**

When an upstream AI provider degrades, client applications crash without automated, streaming-safe failovers.

</td>
<td width="50%" valign="top">

**🌐 4. Language & Region Under-Optimization**

Generic semantic caches fail on South Asian code-mixed text (*Banglish*) and non-Latin scripts (*Bangla*), either missing cacheable prompts or returning false-positive answers on tricky near-misses.

</td>
</tr>
</table>

> **Dwarpal (দ্বারপাল)** is an open-source, enterprise-grade AI gateway that sits between client applications and upstream LLM providers (Groq, OpenAI, Google Gemini, Anthropic Claude, Ollama, etc.). It acts as a single, drop-in OpenAI-compatible endpoint providing **multi-tenant isolation, two-tier hybrid caching (L1 Exact + L2 Semantic), streaming-safe circuit breaking, automated cost governance, and full-stack observability.**

<br/>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0ea5e9,100:6366f1&height=2" width="100%" alt="" />

<h2 align="center" id="architecture">🏛️ System Architecture</h2>

Dwarpal follows a defense-in-depth, zero-trust edge topology. Public traffic terminates at an API gateway edge, while internal administration, vector storage, and state databases remain isolated.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#0f172a", "primaryTextColor": "#e2e8f0", "primaryBorderColor": "#38bdf8", "lineColor": "#38bdf8", "textColor": "#e2e8f0", "edgeLabelBackground": "#0f172a", "fontFamily": "ui-sans-serif, system-ui, sans-serif"}, "flowchart": {"curve": "basis"}}}%%
flowchart TD
    subgraph Clients["Client Tier"]
        App1["App / Microservice A<br/>(dk_live_...)"]
        App2["App / Microservice B<br/>(dk_live_...)"]
        ConsoleUI["Admin Console & Playground<br/>(Internal Port :8001)"]
    end

    subgraph Edge["Edge Security Tier (Kong Gateway :8000)"]
        Kong["Kong API Gateway<br/>• 120 req/min Rate Limiting<br/>• 1 MB Payload Size Cap<br/>• X-Accel-Buffering: no (Realtime SSE)<br/>• Strips /admin, /metrics, /docs"]
    end

    subgraph Core["Core Gateway Tier (FastAPI Engine :8000)"]
        GW["Dwarpal Gateway Engine"]
        Auth["Tenant & Key Authenticator<br/>(SHA-256 Hash Verification)"]
        Budget["Budget & Metering Engine<br/>(Monthly Token & Cost Cap)"]
        Guard["Cache Policy Guard<br/>• PII Filter (8+ digits, emails)<br/>• Temporal Filter (Bangla/Banglish/EN)"]

        subgraph Caching["Hybrid Two-Tier Cache"]
            L1[("L1 Exact Cache<br/>Redis (Sub-ms)")]
            L2[("L2 Semantic Cache<br/>Qdrant + Multilingual-E5")]
        end

        subgraph Resiliency["Resilient Routing Engine"]
            Router["LiteLLM Multi-Provider Router"]
            Breaker["Circuit Breaker<br/>• Per-provider error tracking<br/>• Stream-safe failover (Pre-token only)<br/>• Cooldown probing"]
        end
    end

    subgraph Upstreams["Upstream LLM Providers"]
        P_Groq["Groq<br/>(Llama / Qwen)"]
        P_OpenAI["OpenAI<br/>(GPT-4o / Mini)"]
        P_Gemini["Google Gemini<br/>(2.0 Flash)"]
        P_Claude["Anthropic Claude"]
        P_Local["Local / Ollama"]
    end

    subgraph Persistence["Storage & Telemetry"]
        PG[("PostgreSQL 16<br/>Tenants, Hashed Keys, Usage")]
        Prom["Prometheus<br/>Metrics Scraper"]
        Graf["Grafana<br/>Executive Dashboard"]
    end

    %% Flow connections
    App1 -->|"HTTP POST /v1/chat/completions"| Kong
    App2 -->|"HTTP POST /v1/chat/completions"| Kong
    ConsoleUI -.->|"Direct Admin / Playground"| GW

    Kong -->|"/v1 traffic only"| GW
    GW --> Auth
    Auth -->|"Check limits"| Budget
    Budget --> Guard

    Guard -->|"Clean query"| L1
    L1 -->|"L1 Cache Miss"| L2

    L1 -->|"L1 HIT (Sub-ms)"| GW
    L2 -->|"L2 HIT (Vector Cosine)"| GW

    L2 -->|"L2 Miss"| Router
    Router --> Breaker
    Breaker -->|"Active Circuit"| P_Groq
    Breaker -.->|"Fallback on Failure"| P_Gemini
    Breaker -.->|"Secondary Fallback"| P_OpenAI

    GW -->|"Audit logs & billing"| PG
    GW -->|"Metrics /metrics"| Prom
    Prom --> Graf

    %% Styling
    classDef client fill:#0f172a,stroke:#38bdf8,stroke-width:1.5px,color:#e2e8f0
    classDef kong fill:#1e1b4b,stroke:#818cf8,stroke-width:1.5px,color:#e0e7ff
    classDef core fill:#0c4a6e,stroke:#38bdf8,stroke-width:1.5px,color:#e0f2fe
    classDef cache fill:#064e3b,stroke:#34d399,stroke-width:1.5px,color:#d1fae5
    classDef route fill:#4c1d95,stroke:#a78bfa,stroke-width:1.5px,color:#ede9fe
    classDef upstream fill:#7c2d12,stroke:#fb923c,stroke-width:1.5px,color:#ffedd5
    classDef store fill:#831843,stroke:#f472b6,stroke-width:1.5px,color:#fce7f3

    class App1,App2,ConsoleUI client
    class Kong kong
    class GW,Auth,Budget,Guard core
    class L1,L2 cache
    class Router,Breaker route
    class P_Groq,P_OpenAI,P_Gemini,P_Claude,P_Local upstream
    class PG,Prom,Graf store

    style Clients color:#38bdf8
    style Edge color:#818cf8
    style Core color:#0ea5e9
    style Caching color:#10b981
    style Resiliency color:#8b5cf6
    style Upstreams color:#f97316
    style Persistence color:#ec4899
```

<br/>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0ea5e9,100:6366f1&height=2" width="100%" alt="" />

<h2 align="center" id="capabilities">⚡ Core Engineering Capabilities</h2>

### 🧠 1. Two-Tier Hybrid Semantic Caching (Exact + Semantic)

* **L1 Redis Cache**: Sub-millisecond exact match caching keyed on SHA-256 hash of `(tenant_id, model_name, system_prompt, user_messages)`.
* **L2 Qdrant Vector Cache**: Dense vector similarity search using multilingual embeddings (`intfloat/multilingual-e5-small` with `query:` prefix). Matches semantically identical requests phrased differently or across languages.
* **Strict Tenant Isolation**: Caches are strictly partitioned by tenant ID and system prompt. Prompts cached by Tenant A will **never** be exposed to Tenant B.

### 🕵️ 2. Privacy Guardrails & Temporal Cache Freshness

* **PII Detection**: Automatically bypasses the cache when user prompts contain personal identifiable information (8+ digit numbers, credit cards, telephone sequences, or email addresses).
* **Temporal Freshness Filter**: Automatically bypasses caching on time-sensitive inquiries across three language profiles:
  * **English**: `today`, `now`, `current`, `latest`, `tomorrow`, `yesterday`
  * **Bangla (বাংলা)**: `আজ`, `আজকে`, `আজকের`, `এখন`, `বর্তমান`, `আগামীকাল`, `গতকাল`
  * **Banglish (Code-Mixed)**: `ajke`, `aj`, `ajker`, `ekhon`, `kal`

### 🔄 3. Streaming-Safe Circuit Breaker & Resilient Routing

* **Unified LiteLLM Routing**: Route requests to any AI provider (Groq, OpenAI, Gemini, Claude, Ollama) via standard model IDs.
* **Stream-Safe Fallback Guarantee**: If an upstream provider fails or throttles, the router immediately trips the circuit and redirects to the configured fallback model. Crucially, **failover occurs strictly before the first byte is streamed to the client**, guaranteeing zero corrupted or concatenated response streams.
* **Fail-Open Breaker Mechanics**: If all configured fallback models are temporarily cooling down, the breaker fails open to attempt fulfillment rather than prematurely rejecting user requests.

### 🏢 4. Multi-Tenant Governance & Cryptographic Auth

* **Secure API Keys**: Client keys are generated as `dk_live_<random_bytes>` and stored exclusively as SHA-256 hashes in PostgreSQL. Raw keys are shown only once upon generation.
* **Zero-Downtime Key Rotation**: Seamless key rotation featuring an overlap grace window, allowing client applications to deploy new keys before old keys expire.
* **Budget Enforcement**: Hard and soft monthly limits (token count and USD cost) with instant `429 budget_exceeded` rejection.
* **Tenant Controls**: Granular per-tenant model allow-lists, cache opt-out switches, and instant kill switches.

### 🧱 5. Production Zero-Trust Edge Security

* **Kong API Gateway**: Fronts all external traffic on port `8000`. Strips internal routes, blocks `/admin`, `/metrics`, and `/docs`, enforces a 1 MB payload ceiling, and maintains 120 req/min rate limits per consumer.
* **Zero Logging of Secrets**: Dwarpal’s structured JSON logger tracks request IDs, latency, token consumption, and cache state, while strictly omitting raw prompts, completions, and authorization headers.

<br/>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0ea5e9,100:6366f1&height=2" width="100%" alt="" />

<h2 align="center" id="interfaces">🖥️ Modern Management Interfaces</h2>

Dwarpal includes two built-in browser interfaces served directly by the gateway on its private administrative port (`8001`):

<table>
<tr>
<td width="50%" valign="top">

### 1. The Dwarpal Admin Console (`/console`)

A minimalist, dark-mode/light-mode studio control panel (inspired by Linear and Vercel design systems) with zero build steps, zero external CDNs, and strict CSP:

* **Analytics Overview**: Real-time traffic throughput, cache hit/miss ratios, total token savings, and active tenants.
* **Tenant Lifecycle Management**: Issue, inspect, rotate, and revoke tenant keys; configure monthly USD budgets and model allow-lists; instant cache purge.
* **System Telemetry**: Real-time health metrics, upstream provider key status, routing circuits, and pricing configurations.
* **12-Step Automated Self-Test**: One-click in-browser test suite validating authentication, caching isolation, budget enforcement, and streaming.

</td>
<td width="50%" valign="top">

### 2. Interactive AI Playground (`/playground`)

A clean developer testing console for live interaction:

* Full Server-Sent Events (SSE) streaming support.
* Integrated Markdown rendering for formatted answers, code blocks, lists, and tables.
* Real-time telemetry badges displaying cache resolution (`HIT-EXACT`, `HIT-SEMANTIC`, `MISS`), Time-to-First-Token (TTFT), and total duration in milliseconds.

</td>
</tr>
</table>

<br/>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0ea5e9,100:6366f1&height=2" width="100%" alt="" />

<h2 align="center" id="quickstart">🚀 Quickstart Guide</h2>

### Prerequisites

- Docker Engine 24.0+ and Docker Compose v2.20+
- (Optional for local development) Python 3.11+

### 1. Clone & Configure Environment

```bash
git clone https://github.com/your-username/dwarpal.git
cd dwarpal

# Copy the example environment file
cp .env.example .env
```

Edit `.env` to configure your admin secret and upstream provider API keys:

```dotenv
# Administrative credentials
DWARPAL_ADMIN_KEY=your-secure-admin-secret-key

# Upstream LLM Provider Keys (add any you use)
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
OPENAI_API_KEY=sk-...

# Enable private admin console & playground (localhost:8001)
DWARPAL_CONSOLE_ENABLED=true
DWARPAL_PLAYGROUND_ENABLED=true
```

### 2. Launch the Stack

```bash
docker compose up -d --build
```

Verify that all containers are healthy:

```bash
docker compose ps
```

| Service | Port | Description |
|:---|:---:|:---|
| 🚪 **Kong Gateway** | `8000` | Public API Gateway (Routes `/v1/chat/completions`) |
| ⚙️ **FastAPI Gateway** | `8001` | Private Admin API & Console (`/console`, `/admin`) |
| 🐘 **PostgreSQL** | `5432` | Internal state database |
| 🔴 **Redis** | `6379` | Internal L1 exact cache |
| 🧭 **Qdrant** | `6333` | Internal L2 vector semantic cache |
| 🔥 **Prometheus** | `9090` | Metrics scraper & time-series database |
| 📊 **Grafana** | `3000` | Telemetry & Observability dashboards |

### 3. Create a Tenant & Generate an API Key

Issue a tenant and secret key using the Admin API:

```bash
ADMIN_KEY="your-secure-admin-secret-key"

# 1. Create a tenant
curl -s -X POST http://localhost:8001/admin/tenants \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "fintech-app",
    "name": "Fintech Mobile Application",
    "monthly_cost_budget_usd": 50.0,
    "allowed_models": ["*"]
  }'

# 2. Issue an API key for this tenant
curl -s -X POST http://localhost:8001/admin/tenants/fintech-app/keys \
  -H "Authorization: Bearer $ADMIN_KEY"
```

Output:

```json
{
  "id": "k_18f9a2",
  "name": "default",
  "key": "dk_live_a1b2c3d4e5f6...",
  "created_at": "2026-11-20T14:30:00Z"
}
```

> [!IMPORTANT]
> Save the returned `dk_live_...` key. It is hashed with SHA-256 and will never be shown again.

### 4. Execute OpenAI-Compatible Requests

Dwarpal is a drop-in replacement for the OpenAI API. Only `base_url` and `api_key` change.

#### 🐍 Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",  # Point to Kong edge gateway
    api_key="dk_live_a1b2c3d4e5f6...",    # Your Dwarpal tenant key
)

# 1. First call: Cache MISS (queries upstream provider)
response1 = client.chat.completions.create(
    model="groq/openai/gpt-oss-20b",
    messages=[{"role": "user", "content": "How much zakat do I have to pay on savings?"}]
)
print("Response 1:", response1.choices[0].message.content)

# 2. Second call (identical): L1 Cache HIT (sub-millisecond from Redis)
response2 = client.chat.completions.create(
    model="groq/openai/gpt-oss-20b",
    messages=[{"role": "user", "content": "How much zakat do I have to pay on savings?"}]
)

# 3. Third call (paraphrase in Banglish): L2 Cache HIT (semantic match from Qdrant)
response3 = client.chat.completions.create(
    model="groq/openai/gpt-oss-20b",
    messages=[{"role": "user", "content": "zakat koto taka dite hoy"}]
)
```

#### 🌊 cURL (Streaming SSE)

```bash
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer dk_live_a1b2c3d4e5f6..." \
  -H "Content-Type: application/json" \
  -d '{
    "model": "groq/openai/gpt-oss-20b",
    "messages": [{"role": "user", "content": "Tell me a short 2-sentence joke."}],
    "stream": true
  }'
```

<br/>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0ea5e9,100:6366f1&height=2" width="100%" alt="" />

<h2 align="center" id="benchmarks">📊 Reproducible Benchmarks & Performance Data</h2>

Dwarpal includes a standalone benchmark harness in `bench/` to evaluate semantic embedding quality, cache latency, throughput, and circuit breaker behavior.

> [!NOTE]
> **Zero Fabricated Claims**: Dwarpal's benchmarking suite uses reproducible, transparent test harnesses. Load tests use a configurable synthetic upstream delay (`DWARPAL_MOCK_DELAY_MS=300`) to strictly isolate gateway and cache mechanics from variable public LLM API network latencies.

### 🏁 The Benchmark Matrix (Measured Results)

All figures below are extracted directly from `bench/results/` and verified with `bench/make_report.py`:

| Evaluation Category | Benchmark Scope | Measured Value | Production SLA & Impact |
|:---|:---|:---|:---|
| **Optimal Embedding Model** | `intfloat/multilingual-e5-small` | **Threshold `0.97`** (Margin `-0.1627`) | **0.00% False Positives** on near-miss queries |
| **Streamed TTFT (L1 Exact HIT)** | Streamed SSE replay via Kong | **`79.6 ms` (p50)** / `557.6 ms` (p95) | Sub-100ms instant token delivery |
| **Streamed TTFT (L2 Semantic HIT)** | Vector similarity retrieval via Kong | **`296.0 ms` (p50)** | Instantaneous cross-lingual cache retrieval |
| **Throughput & Cache Hit Ratio** | 100-request closed-loop load test | **100% Hit Ratio** @ `6.6 req/s` (0 errors) | Zero upstream LLM billing on repeated queries |
| **Outage Resiliency (HTTP 200)** | Provider outage drill (75 requests over 75s) | **75 of 75 (100.0%)** | Zero user-facing errors during upstream outage |
| **Failing Provider Isolation** | Circuit breaker tripping on consecutive errors | **70 of 75 (93.3%)** calls avoided failing upstream | Breaker tripped 3 times; p95 latency `430.9 ms` |

<br/>

### 📈 Measured Calibration: Semantic Threshold Sweep

Real empirical results from evaluating `intfloat/multilingual-e5-small` against `data/bench/pairs.jsonl` (12 true paraphrase pairs across Bangla, Banglish, and English vs. 12 high-risk near-misses):

| Cosine Threshold | Cache Hit Rate (True Paraphrases) | False Positive Rate (Wrong Answers on Near-Misses) | Production Safety Status |
|:---:|:---:|:---:|:---|
| `0.85` | **83%** | 100% | ❌ Dangerous (returns incorrect cached answers) |
| `0.90` | **67%** | 83% | ❌ Critical intent collisions |
| `0.94` | **42%** | 50% | ❌ Half of near-misses falsely cached |
| `0.95` | **33%** | 25% | ⚠️ Risky (collides on card limits and prayer types) |
| `0.96` | **33%** | 17% | ⚠️ Near boundary |
| **`0.97`** | **25%** | **0.00%** | ✅ **Recommended Zero-Collision Threshold** |

```mermaid
%%{init: {"theme": "base", "themeVariables": {"xyChart": {"plotColorPalette": "#06b6d4, #ef4444"}}}}%%
xychart-beta
    title "Semantic Threshold Sweep (bars: hit rate % | line: false-positive rate %)"
    x-axis ["0.85", "0.90", "0.94", "0.95", "0.96", "0.97"]
    y-axis "Rate (%)" 0 --> 100
    bar [83, 67, 42, 33, 33, 25]
    line [100, 83, 50, 25, 17, 0]
```

#### 🚨 The 5 Most Dangerous Near-Miss Collisions Detected

1. **`0.969` Cosine Similarity**:
   `"How do I increase my card limit?"` ↔ `"How do I decrease my card limit?"` *(Antonym collision)*
2. **`0.965` Cosine Similarity**:
   `"ক্রেডিট কার্ড চালু করব কীভাবে?"` ↔ `"ক্রেডিট কার্ড বন্ধ করব কীভাবে?"` *(Activate vs. Cancel card in Bangla)*
3. **`0.957` Cosine Similarity**:
   `"How to download a song?"` ↔ `"How to delete a downloaded song?"`
4. **`0.945` Cosine Similarity**:
   `"zakat on gold"` ↔ `"zakat on silver"` *(Distinct Islamic jurisprudence rulings)*
5. **`0.943` Cosine Similarity**:
   `"সফরে নামাজ কীভাবে পড়ব?"` ↔ `"অসুস্থ অবস্থায় নামাজ কীভাবে পড়ব?"` *(Traveler prayer vs. Sickness prayer)*

> [!TIP]
> **Key Architectural Takeaway**: In fintech and production services, false-positive cache hits (e.g. serving a card activation guide when a user asked how to cancel their card) are fatal. Setting `DWARPAL_SEMANTIC_THRESHOLD=0.97` guarantees **0.00% false positives** on tricky near-misses while reliably capturing genuine cross-lingual paraphrases (*"যাকাত কত টাকা দিতে হয়"* ↔ *"zakat koto taka dite hoy"*).

<br/>

### 🔬 Empirical Multilingual Embedding Model Comparison

Evaluated on CPU across 24 labeled Bangla, Banglish, and English query pairs (`data/bench/pairs.jsonl`):

| Embedding Model | Vector Dim | Encode Speed (CPU) | Separation Margin | Recommended Threshold (0% Wrong Hits) | Safe Cache Hit Rate | Production Verdict |
|:---|:---:|:---:|:---:|:---:|:---:|:---|
| **`intfloat/multilingual-e5-small`** | **384** | **61.9 ms/query** | **-0.1627** | **0.97** | **25%** | 🏆 **Default / Best Balance** (Strongest separation, compact memory footprint) |
| `paraphrase-multilingual-MiniLM-L12-v2` | 384 | 56.6 ms/query | -0.4545 | 0.93 | 17% | ⚠️ Weaker cross-lingual separation on Bengali code-mixed queries |
| `BAAI/bge-m3` | 1024 | 660.9 ms/query | -0.5191 | 0.91 | 33% | ❌ 10x slower on CPU; high memory footprint without GPU acceleration |

<sub>*Note: Separation Margin is calculated as `min(true_paraphrase_similarity) - max(near_miss_similarity)`. A higher margin (closer to 0) means the model can more sharply delineate genuine paraphrases from tricky near-misses.*</sub>

<br/>

### 🧪 Executing the Benchmark Suite

To measure real performance data on your hardware, execute the following commands in order:

#### 1. Calibrate Semantic Similarity Thresholds

Sweeps cosine similarity thresholds across labeled Bangla, Banglish, and English paraphrase pairs vs. tricky near-misses (e.g., *"How many rakats in Fajr?"* vs. *"How many rakats in Maghrib?"*):

```bash
# Evaluates intfloat/multilingual-e5-small on data/bench/pairs.jsonl
make bench
```

#### 2. Multilingual Embeddings Model Evaluation

Compares multiple embedding backends (`intfloat/multilingual-e5-small`, `paraphrase-multilingual-MiniLM-L12-v2`, `BAAI/bge-m3`) for encoding speed, separation margin, and recommended threshold:

```bash
make bench-embeddings
```

*Output saved to `bench/results/embeddings.json`.*

#### 3. Closed-Loop Load Testing (Throughput & TTFT)

Executes concurrent load testing measuring p50, p95, and p99 latency split by cache state (`HIT` vs `MISS`):

```bash
# A. Measure latency through the Kong edge gateway (port 8000)
make load KEY=dk_live_... LABEL=kong

# B. Measure latency directly to the FastAPI gateway (port 8001) to isolate Kong overhead
make load KEY=dk_live_... BASE=http://localhost:8001 LABEL=direct
```

*Outputs saved to `bench/results/load-kong.json` and `bench/results/load-direct.json`.*

#### 4. Upstream Provider Outage Drill

Simulates an upstream provider failure to verify circuit breaker trip timing, error shedding, and fallback routing:

```bash
make drill KEY=dk_live_...
```

*Output saved to `bench/results/drill.json`.*

#### 5. Compile Live Benchmark Report

Aggregates all JSON test results into a unified Markdown report at `docs/benchmark-report.md`:

```bash
make report HARDWARE="Intel Core i7-13700K, 32GB RAM"
```

<br/>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0ea5e9,100:6366f1&height=2" width="100%" alt="" />

<h2 align="center" id="configuration">⚙️ Configuration Reference</h2>

All settings can be specified via environment variables or the `.env` file:

| Variable | Default | Purpose |
|:---|:---|:---|
| `DWARPAL_ADMIN_KEY` | `dev-admin-secret` | Master secret for `/admin` API and `/console` |
| `DWARPAL_CONSOLE_ENABLED` | `false` | Enables private admin console UI at `:8001/console` |
| `DWARPAL_PLAYGROUND_ENABLED` | `false` | Enables chat playground UI at `:8000/playground` |
| `DWARPAL_DATABASE_URL` | `postgresql+psycopg://...` | Connection URL for PostgreSQL 16 |
| `DWARPAL_REDIS_URL` | `redis://:password@redis:6379/0` | Connection URL for Redis L1 cache |
| `DWARPAL_QDRANT_URL` | `http://qdrant:6333` | Connection URL for Qdrant L2 vector database |
| `DWARPAL_EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Multilingual embedding model for semantic caching |
| `DWARPAL_SEMANTIC_THRESHOLD` | `0.95` | Cosine similarity threshold for L2 semantic match |
| `DWARPAL_CACHE_TTL_SECONDS` | `86400` (24h) | Time-to-live for cache entries in Redis and Qdrant |
| `DWARPAL_MOCK_DELAY_MS` | `0` | Artificial delay for synthetic provider benchmarks |
| `DWARPAL_ROUTING_CONFIG` | `/srv/config/routing.json` | Path to upstream routing & fallback configuration |
| `DWARPAL_PRICES_CONFIG` | `/srv/config/prices.json` | Path to model token pricing dictionary (for budgets) |

<br/>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0ea5e9,100:6366f1&height=2" width="100%" alt="" />

<h2 align="center" id="security">🔒 Security Architecture</h2>

<table>
<tr>
<td width="50%" valign="top">

**🧱 1. Edge Boundary**

Kong exposes only `/v1` and health endpoints. Administrative routes (`/admin`), documentation (`/docs`, `/openapi.json`), metrics (`/metrics`), and the console (`/console`) cannot be resolved from the edge.

</td>
<td width="50%" valign="top">

**🔑 2. Key Storage**

Tenant API keys are salted and hashed with SHA-256. If the PostgreSQL database is compromised, plaintext API keys are not exposed.

</td>
</tr>
<tr>
<td width="50%" valign="top">

**🧼 3. Data Sanitization**

Logs never record user prompts, completions, headers, or query parameters.

</td>
<td width="50%" valign="top">

**📦 4. Sandboxed Console**

The web console runs under strict Content Security Policy (`script-src 'self' 'unsafe-inline'`), uses zero third-party CDNs, and keeps secrets in page memory.

</td>
</tr>
</table>

<br/>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0ea5e9,100:6366f1&height=2" width="100%" alt="" />

<h2 align="center" id="runbook">🛠️ Production Runbook</h2>

<details>
<summary><b>🔥 Upstream Provider Outage</b> (<code>ProviderCircuitOpen</code> Alert)</summary>
<br/>

1. Inspect the Grafana *Provider Calls / Second* panel to identify the failing upstream.
2. Verify that traffic has automatically shifted to fallback models.
3. If all fallbacks fail, update `config/routing.json` with an alternate model and reload.

</details>

<details>
<summary><b>🔑 API Key Compromise</b></summary>
<br/>

1. Revoke key immediately: `DELETE /admin/keys/{key_id}`.
2. Issue a replacement key via `POST /admin/tenants/{id}/keys`.

</details>

<details>
<summary><b>💸 Budget Exceeded</b> (HTTP 429)</summary>
<br/>

1. Inspect tenant month-to-date usage: `GET /admin/tenants/{id}/usage`.
2. Raise the budget dynamically: `PATCH /admin/tenants/{id}` with `monthly_cost_budget_usd`.

</details>

<details>
<summary><b>🧊 Stale or Incorrect Cached Answer</b></summary>
<br/>

1. Immediately bypass cache for that tenant: `PATCH /admin/tenants/{id}` with `{"cache_enabled": false}`.
2. Calibrate threshold or add near-miss query pair to `data/bench/pairs.jsonl` and run `make bench`.

</details>

<br/>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0ea5e9,100:6366f1&height=2" width="100%" alt="" />

<h2 align="center" id="license">📄 License</h2>

<div align="center">

Distributed under the Apache 2.0 License. See [LICENSE](LICENSE) for details.

<br/>

<a href="#top"><img src="https://img.shields.io/badge/⬆_BACK_TO_TOP-0f172a?style=for-the-badge" alt="Back to top" /></a>

</div>

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0b1220,50:1d4ed8,100:06b6d4&height=140&section=footer" alt="footer" width="100%" />