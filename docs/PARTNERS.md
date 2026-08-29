# Partner technology reference

Six partner technologies. The rules require three. Every entry records exact base URLs, auth headers, identifiers and gotchas, verified against vendor documentation on 29 Aug 2026. Where something is undocumented it says so — **do not guess in the submission writeup.**

| | Role in Glia |
|---|---|
| [OpenAI](#1-openai--live-transcription) | Live transcription of speech; prompt synthesis at Generate |
| [Cala](#2-cala--entity-resolution-and-cited-source-discovery) | Resolves what you mean; finds the authoritative sources our references come from |
| [Pioneer](#3-pioneer-fastino-labs--visual-attribute-extraction) | GLiNER2 extracts visual attributes from speech; gates Cala spend |
| [fal](#4-fal--the-final-image) | Generates the final image, conditioned on pinned references |
| [Aikido](#5-aikido--security) | Zen runtime firewall (SSRF matters here), CI gating, safe-chain, live security panel |
| [Entire](#6-entire--provenance-for-the-build) | Binds every commit to the agent session behind it |

Environment variables are per-section and collected at the end.

---

## 1. OpenAI — live transcription

**Docs moved.** `platform.openai.com/docs/*` now 302s to `developers.openai.com/api/docs/*`.

**The model landscape changed in late July 2026.** `gpt-4o-transcribe` and `gpt-4o-mini-transcribe` are now listed under *legacy support*. Any tutorial using `?intent=transcription` plus `gpt-4o-transcribe` and the `OpenAI-Beta: realtime=v1` header is describing the deprecated Beta shape. Ignore it.

| | |
|---|---|
| Realtime WS | `wss://api.openai.com/v1/realtime` |
| Ephemeral token | `POST https://api.openai.com/v1/realtime/client_secrets` |
| WebRTC SDP exchange | `POST https://api.openai.com/v1/realtime/calls` |
| File transcription | `POST https://api.openai.com/v1/audio/transcriptions` |
| **Deprecated** | `POST /v1/realtime/transcription_sessions`, `POST /v1/realtime/sessions` |
| Env var | `OPENAI_API_KEY` |

### Models

| Model | Use | Price |
|---|---|---|
| **`gpt-live-transcribe`** | **Ours.** Low-latency realtime with continuous deltas. Tunable `delay`, plus `prompt`, `keywords`, `languages` hints. No timestamps, no speaker labels, no confidence. | $0.017/min |
| `gpt-transcribe` | High accuracy, but in Realtime only emits on **committed turns** — no interim deltas. Default for the file API. | $0.0045/min |
| `gpt-realtime-whisper` | **Avoid.** Turn detection must be `null`; VAD is unsupported. | $0.017/min |
| `whisper-1` | Legacy; kept for timestamps and translation. | — |

Continuous transcription is roughly **$1.02/hour/speaker**. `gpt-live-transcribe` is ~3.8× `gpt-transcribe` — that is the price of deltas, and deltas are the product's feel, so we pay it.

### Session type

There is a transcription-only mode, but the mechanism changed: open a normal `/v1/realtime` connection and declare `session.type = "transcription"`. Do **not** call the deprecated `/realtime/transcription_sessions` endpoint.

### Backend mints the ephemeral token

`expires_after.seconds` accepts **10–7200, default 600**. Keep it short.

```python
from openai import OpenAI
client = OpenAI()

@app.post("/api/realtime-token")
def mint_token():
    secret = client.realtime.client_secrets.create(
        expires_after={"anchor": "created_at", "seconds": 600},
        session={
            "type": "transcription",
            "audio": {"input": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "noise_reduction": {"type": "near_field"},
                "transcription": {
                    "model": "gpt-live-transcribe",
                    "languages": ["en", "es"],
                    "delay": "low",
                    "prompt": "A person thinking out loud about an image they want to create.",
                },
                "turn_detection": {
                    "type": "semantic_vad",
                    "eagerness": "low",
                },
            }},
        },
    )
    return {"value": secret.value, "expires_at": secret.expires_at}
```

Realtime is now a **top-level** SDK resource — `client.realtime.*`, not `client.beta.realtime.*`. Send `OpenAI-Safety-Identifier: <hashed-user-id>` on the mint call.

The `prompt` field is a genuine quality lever for us: telling the model the speaker is describing an imagined image measurably improves how it handles visual vocabulary. The `keywords` field is worth trying with art-movement and style terms.

### Browser: WebRTC

```js
const { value: EPHEMERAL_KEY } = await (await fetch("/api/realtime-token", { method: "POST" })).json();

const pc = new RTCPeerConnection();
const ms = await navigator.mediaDevices.getUserMedia({ audio: true });
pc.addTrack(ms.getTracks()[0]);

const dc = pc.createDataChannel("oai-events");   // the name is required

dc.addEventListener("message", (e) => {
  const ev = JSON.parse(e.data);
  switch (ev.type) {
    case "conversation.item.input_audio_transcription.delta":
      paintInterim(ev.item_id, ev.delta);
      break;
    case "conversation.item.input_audio_transcription.completed":
      sendSettledTurn(ev.item_id, ev.transcript);   // → our WebSocket
      break;
    case "input_audio_buffer.speech_stopped":
      markPause();                                   // → triggers the distiller
      break;
  }
});

const offer = await pc.createOffer();
await pc.setLocalDescription(offer);
const answer = await fetch("https://api.openai.com/v1/realtime/calls", {
  method: "POST",
  body: offer.sdp,
  headers: { Authorization: `Bearer ${EPHEMERAL_KEY}`, "Content-Type": "application/sdp" },
});
await pc.setRemoteDescription({ type: "answer", sdp: await answer.text() });
```

**Three traps, all verified:**

1. **Do not append `?model=` to `/v1/realtime/calls`** — it returns an empty `400`. The model is already baked into the ephemeral secret.
2. The docs show **two body shapes** for `/realtime/calls`: the guide's working sample posts raw SDP with `Content-Type: application/sdp`; the API reference describes a form body with `sdp` and `session` parts. Start with raw SDP. Which is canonical is unverified.
3. **There is no documented end-to-end WebRTC + transcription-session example.** `client_secrets` explicitly accepts a transcription session, so it is supported on paper, but the combination is unproven in the docs. Since we send audio only, we may need `pc.addTransceiver('audio', { direction: 'sendonly' })` — undocumented.

**De-risk this first.** It is the single highest-uncertainty item in the build. If WebRTC resists after 30 minutes, fall back to browser → our FastAPI WebSocket → OpenAI WebSocket, which is fully documented. Cost: one extra hop of latency and our server carries audio bytes.

### WebSocket fallback

`wss://api.openai.com/v1/realtime`, header `Authorization: Bearer $OPENAI_API_KEY`, no `OpenAI-Beta` header. Audio is **16-bit PCM, 24 kHz, mono, little-endian, base64**, declared as `{"type": "audio/pcm", "rate": 24000}`. Max 15 MB per appended chunk.

Client → server: `session.update`, `input_audio_buffer.append` (`{type, audio}`), `input_audio_buffer.commit`, `input_audio_buffer.clear`.

Server → client: `conversation.item.input_audio_transcription.delta` (`{type, item_id, content_index, delta}`), `.completed` (`{type, item_id, content_index, transcript}`), `.failed`, `.segment`, `input_audio_buffer.speech_started`, `.speech_stopped`, `.committed`, `.cleared`, `.timeout_triggered`.

Reconcile deltas by `item_id` — finals can arrive across turns.

### Turn detection — the trigger for our whole loop

Set at `session.audio.input.turn_detection`. Three states: `null` (manual commit), `server_vad`, `semantic_vad`.

- `server_vad`: `threshold` (0–1, default 0.5), `prefix_padding_ms`, `silence_duration_ms`.
- `semantic_vad`: `eagerness` — `low | medium | high | auto` (auto ≡ medium). `low` waits longer before calling end-of-turn.

**Use `semantic_vad` with `eagerness: "low"`.** People thinking out loud pause mid-sentence constantly; silence-based VAD would fire the distiller on every breath and shred the transcript into fragments. `create_response` and `interrupt_response` are conversation-mode only and irrelevant to us.

Trigger downstream work on `input_audio_buffer.speech_stopped`, then use the `...transcription.completed` for that `item_id` as the settled text.

### SDKs

Backend: the `openai` Python package, used **only** for `client.realtime.client_secrets.create`. Browser: plain `RTCPeerConnection`, ~30 lines. The agents SDKs (`openai-agents`, `@openai/agents-realtime`) are built for bidirectional voice agents and **do not document transcription-only sessions** — skip them.

### Limits

`gpt-live-transcribe`: Tier 1 500 RPM / 60,000 TPM, rising to 10,000 RPM / 780,000 TPM at Tier 5. **A concurrent Realtime session cap is not documented** and could not be verified. For long-lived audio streams TPM is the binding constraint — do not plan high concurrency without confirming.

### Prompt synthesis at Generate

A second, ordinary call — `gpt-5.x` chat completion, or routed through Pioneer — that turns the transcript, the distilled attributes, the pinned reference descriptions and the Cala visual direction into one concise image prompt. This prompt is shown to the user next to the result. It is part of the product, not a hidden internal: *"here is what we understood you to mean."*

The event provides claimable OpenAI credits — claim them from the event page before you start.

---

## 2. Cala — entity resolution and cited-source discovery

**Read `docs/STACK.md` § "What Cala actually does here" before writing any code against this API.** Cala returns **no images**. There is no `image`, `image_url`, `thumbnail`, `logo`, `media`, `photo` or `avatar` field anywhere in its OpenAPI schema — verified against `https://api.cala.ai/openapi.json`. It does not crawl the web. Its own docs say so explicitly.

| | |
|---|---|
| Base URL | `https://api.cala.ai/v1` |
| Auth header | `X-API-KEY: <key>` — **not** `Authorization: Bearer` |
| Env var | `CALA_API_KEY` (our convention; Cala documents none server-side) |
| Keys | https://console.cala.ai/api-keys |
| SDK | none — raw HTTP. OpenAPI at `https://api.cala.ai/openapi.json` |

### Endpoints

| Endpoint | Method | Returns |
|---|---|---|
| `/v1/knowledge/search` | POST | Markdown answer + claim-level citations. **The one that yields scrapeable pages.** |
| `/v1/knowledge/query` | POST | Typed JSON rows, **no citations** |
| `/v1/entities` | GET | Fuzzy entity name search — our resolution step |
| `/v1/entities/{id}` | **POST** | Full entity, properties as `{value, sources[]}` |
| `/v1/entities/{id}/introspection` | GET | What fields exist, before you ask |

`/v1/entities/{id}` is **POST**, not GET — the body selects properties and relationships.

### Step 1 — resolve the spoken subject

```bash
curl "https://api.cala.ai/v1/entities?name=Bauhaus&limit=10" -H "X-API-KEY: $CALA_API_KEY"
```

`name` (required), `entity_types` (array), `limit` (1–100, default 20). Returns `{id, name, entity_type, description}`.

Entity types are listed inconsistently across docs pages — 16 on the feature page, 31 in the API reference. Confirmed useful for us: `Company, Person, Product, Organization, WorkOfArt, Location, GPE, Country, EducationalInstitution, Facility, Industry, CorporateEvent, Award, Animal`. Do not hardcode the full list from one page.

### Step 2 — find cited sources

```bash
curl -X POST https://api.cala.ai/v1/knowledge/search \
  -H "X-API-KEY: $CALA_API_KEY" -H "Content-Type: application/json" \
  -d '{"input": "Bauhaus design movement visual characteristics"}'
```

Request: `input` (required), `explainability` (bool, default true), `return_entities` (bool, default true).

```jsonc
{
  "content": "markdown answer",
  "explainability": [                       // → salience: which facts carried the answer
    { "content": "supporting statement", "references": ["<knowbit-uuid>"] }
  ],
  "context": [
    { "id": "<knowbit-uuid>",
      "content": "the quoted evidence",
      "origins": [
        { "source":   { "name": "Impact Loop", "url": "https://www.impactloop.com/" },
          "document": { "name": "Article title",
                        "url": "https://www.impactloop.com/artikel/..." },   // ← SCRAPE THIS
          "breadcrumb": [""] } } ] },
  "entities": [
    { "id": "<uuid>", "name": "…", "entity_type": "Company", "mentions": ["…"] } ]
}
```

**`context[].origins[].document.url` is the whole image pipeline.** Documented examples are ordinary article pages on real publications (impactloop.com, seedtable.com, cleantechforeurope.com) — pages that carry `og:image` and inline article images. We fetch those, extract, and badge each resulting candidate with `source.name` and `document.name`.

### The trap: entity sources are NOT scrapeable

`POST /v1/entities/{id}` property sources use a **completely different `document` shape**:

```json
{ "name": "GLEIF",
  "document": { "endpoint": "https://api.gleif.org/api/v1/lei-records?filter…",
                "params": {},
                "response_hash": "7089723cc94015908b284e2637d34fca…" },
  "date": "2026-02-26" }
```

Those are raw JSON API endpoints. No `og:image`, nothing to scrape. **Only the `knowledge/search` path yields images.** Two different `document` schemas on two endpoints — write two parsers and do not confuse them.

(The `response_hash` is a SHA-256 of the upstream response, which makes entity properties genuinely auditable. Not needed for the image loop, but a nice detail if a judge asks how deep the provenance goes.)

### `/v1/knowledge/query` — not for us

Returns `{results, entities}` with **no `explainability` and no `context`**, so no citations and no URLs. Row keys are also derived per query rather than a fixed schema. Useful for tabular lookups, useless for image discovery. Cala QL dot-notation (`OpenAI.founded.year`, `startups.location=Spain.funding>10M`) works on both knowledge endpoints, but our inputs come from speech, so we send natural language.

### Credits — the budget

| Plan | Credits/month | Rate limit |
|---|---|---|
| Starter (free) | 100 | 10 req/min |
| Explore $50 | 1,100 | 100 req/min |
| Build $200 | 5,000 | 100 req/min |

**1 credit = 1 query, and the binding constraint is the monthly cap, not the rate limit.** Free tier is 100 credits *per month* — roughly three queries a day, which a continuous speech loop exhausts in seconds.

**We have 1,100 credits** (100 plan + 1,000 purchased, plan renews 29 Sep 2026). That is comfortable but not infinite: it is roughly 70–200 full demo sessions, or far fewer if the loop leaks. Purchased credits never expire.

Budget for today:

| | Credits |
|---|---|
| Development and debugging | ~300 |
| Rehearsals | ~100 |
| Live demo (×2, including the finalist stage) | ~30 |
| Headroom | the rest |

Four controls, all mandatory — the budget is comfortable only because they exist:

1. **Distiller gate** — no Cala call unless the GLiNER2 attribute set changed materially.
2. **Debounce** — 8 s minimum of new settled speech between queries.
3. **Cache** — Postgres, keyed on a hash of `input`, raw JSON retained for the source panel. Re-running the demo script must cost zero.
4. **Ledger** — Redis counter, surfaced in the dev HUD. A leaking loop is then visible in seconds rather than at 18:00.

`429` returns `{"error": "rate_limit_exceeded", …}`; `422` for validation. **Undocumented:** whether `/v1/entities` and introspection consume credits, `Retry-After` headers, `X-RateLimit-*` headers, concurrency limits. Measure entity-call cost against the console meter in the first hour — do not assume lookups are free, and do not discover they are not on credit 900.

### Coverage

Finance and compliance dominate: SEC/EDGAR, GLEIF, business registries, OFAC/EU/UN sanctions, PEPs, PACER, CourtListener, Fed/ECB/BIS series, Moody's/S&P/Fitch, Reuters, PR Newswire. Healthcare, legal, HR and agro are advertised; only legal has named sources.

**Plan for misses.** Most spoken visual thinking is not finance. Cala will often return nothing usable, which is exactly why Lane B is first-class. For the scripted demo, choose a subject inside Cala's coverage so Lane A visibly fires — a company, a product, a place, a named work — and let free-form talk fall through to Lane B.

### MCP (dev convenience, not runtime)

```json
{ "mcpServers": { "Cala": { "url": "https://api.cala.ai/mcp/",
                            "headers": { "X-API-KEY": "YOUR_CALA_API_KEY" } } } }
```

Tools: `knowledge_search`, `knowledge_query`, `entity_search`, `entity_introspection`, `retrieve_entity`. Useful for exploring coverage while building. **Every MCP call spends a credit** — do not leave an agent looping on it.

---

## 3. Pioneer (Fastino Labs) — visual attribute extraction

Pioneer is the **cost gate**. It runs on every speech pause; Cala runs only when Pioneer says the idea actually moved. Encoder models cost $0.15/1M tokens and return in milliseconds, so this is affordable at a cadence that a frontier model never would be.

| | |
|---|---|
| API root | `https://api.pioneer.ai` |
| OpenAI-compatible | `https://api.pioneer.ai/v1` → `/chat/completions`, `/completions`, `/responses`, `/models` |
| Anthropic-compatible | same base → `/v1/messages` |
| Native | `POST https://api.pioneer.ai/inference` |
| Auth | `X-API-Key: <key>` or `Authorization: Bearer <key>` |
| Env var | `PIONEER_API_KEY` (docs convention; the SDK does **not** read it automatically) |
| Keys | `agent.pioneer.ai/api-keys` |

### The distiller

GLiNER2's `schema.structures` is built for exactly this: pull typed fields out of free text in one pass.

```json
POST /inference
{
  "model_id": "fastino/gliner2-large-v1",
  "text": "<the settled transcript window>",
  "schema": {
    "structures": [{
      "name": "visual_direction",
      "fields": [
        {"name": "subject",     "dtype": "str"},
        {"name": "mood",        "dtype": "list"},
        {"name": "style",       "dtype": "list"},
        {"name": "palette",     "dtype": "list"},
        {"name": "composition", "dtype": "str"},
        {"name": "medium",      "dtype": "str",
         "choices": ["photograph","painting","illustration","3d render","collage","film still"]},
        {"name": "era",         "dtype": "str"}
      ]
    }],
    "entities": ["person", "organization", "location", "product", "work_of_art"]
  },
  "threshold": 0.5
}
```

The `entities` block does double duty: those spans are the candidate names we feed to Cala's `GET /v1/entities` for resolution. One call gives us both the attribute vector and the things worth looking up.

`schema` also accepts `classifications` (`[{task, labels[]}]`) and `relations`. `text` accepts a string **or an array** for batching. Response is a discriminated union on `type`: encoder → `{inference_id, result, model_id, latency_ms, token_usage, model_used}`; decoder → `{inference_id, completion, reasoning_trace, …}`.

**Spike this before building on it.** Pioneer documents `result` only as *"shape depends on the schema and task"* and publishes **no example response body anywhere**. Print the real response, pin the parser, then write the gate. Fifteen minutes now saves an hour at 16:00. The nearest documented evidence for entity shape is `{"text", "label", "start", "end"}` per entity — strongly implied, not confirmed.

### The gate

Compare the new `visual_direction` against the last one that triggered a Cala query. Spend a credit only when it materially moved:

- `subject` changed (normalised string compare), **or**
- `medium` or `era` changed, **or**
- Jaccard distance on `mood ∪ style ∪ palette` exceeds a threshold (start at 0.4, tune live)

Otherwise: update the UI from local state and spend nothing. Log the gate decision — during the demo you want to be able to say why a query fired.

### Model ids

| Class | Ids |
|---|---|
| Router | `pioneer/auto` |
| Frontier | `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-5`, `gpt-5.5`, `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol`, `deepseek-ai/DeepSeek-V4-Flash`, `zai-org/GLM-5.2`, `zai-org/GLM-5.2-Fast` |
| Encoders (trainable) | `fastino/gliner2-base-v1`, `fastino/gliner2-large-v1`, `fastino/gliner2-multi-v1`, `fastino/gliner2-multi-large-v1` |
| Encoders (inference only) | `fastino/gliguard-LLMGuardrails-300M`, `fastino/gliner2-privacy-filter-PII-multi`, `fastino/gliguard-PII-multi` |

Use `gliner2-large-v1` for quality, `multi-*` if the demo may be in Spanish or Catalan — worth considering in Barcelona.

### Drop-in usage

```python
from openai import OpenAI
client = OpenAI(api_key=os.environ["PIONEER_API_KEY"], base_url="https://api.pioneer.ai/v1")

resp = client.chat.completions.create(
    model="fastino/gliner2-large-v1",
    messages=[{"role": "user", "content": transcript_window}],
    extra_body={"schema": SCHEMA, "include_confidence": True, "include_spans": True},
)
```

Pioneer-specific fields go through `extra_body` when using the OpenAI SDK.

### PII redaction — optional, cheap, and a good answer to an obvious question

Speech is personal. If a user says a name, an address or a phone number while thinking out loud, that text currently flows into Cala queries and the fal prompt. `fastino/gliner2-privacy-filter-PII-multi` covers 42 labels (`person, email, phone_number, address, government_id, iban, payment_card, api_key, …`) across EN, FR, ES, DE, IT, PT, NL, with character spans.

There is **no masking helper** — do the span surgery yourself, replacing each span with a stable placeholder. Given the distiller already runs on every pause, adding this is one more cheap encoder call. It also matters because **Pioneer may use your data to improve models by default** (opt-out is Pro/Custom only).

Worth doing if there is time after 16:00. If a judge asks "what happens if I say my address out loud", having an answer is worth more than the code cost.

### Adaptive inference (Felix) — stretch

Every call is logged; Pioneer clusters failures and retrains automatically, with **manual promotion**. Feedback:

```bash
curl -X POST https://api.pioneer.ai/inferences/<INFERENCE_ID>/feedback \
  -H "X-API-Key: $PIONEER_API_KEY" -H "Content-Type: application/json" \
  -d '{"verdict":"incorrect","corrected_output":{"entities":[{"text":"brutalist","label":"style","start":10,"end":19}]}}'
```

**Not available on the free plan** (Pro is $20/seat/mo including $40 credits). If we take it: an "that's not what I meant" control next to the distilled attributes, wired to this endpoint, is a strong 15-second beat — correcting the interpretation trains the extractor.

### Rate limits

`/inference` and the OpenAI-compatible completion paths: 5,000/min. `/felix/training-jobs`: 20/min. Default 20,000/min. `429` with `Retry-After`, `402` when credits exhaust. Not a constraint for us.

---

## 4. fal — the final image

| | |
|---|---|
| Sync base | `https://fal.run` |
| Queue base | `https://queue.fal.run` |
| Auth header | `Authorization: Key $FAL_KEY` — **not** `Bearer` |
| Env var | `FAL_KEY` |
| Python | `pip install fal-client` → `import fal_client` |
| JS/TS | `npm i @fal-ai/client` (the old `@fal-ai/serverless-client` is superseded) |

### Key handling

Keys are **account-scoped, not user-scoped**, and scoped `API` or `ADMIN`. An `ADMIN` key can deploy and delete apps and mint further keys — **use an `API` key**. A leak bills our prepaid balance. `FAL_KEY` exists only in the FastAPI process; the browser never sees it and never calls fal directly.

We do not need fal's browser proxy at all, because generation is a backend action triggered over our WebSocket. (For reference: fal only ships a Next.js proxy handler, and its published generic sample validates nothing — it is an open proxy as written. We avoid the whole category.)

### The generation call — where pins become real

```python
result = await fal_client.subscribe_async(
    "fal-ai/flux-pro/kontext/max/multi",
    arguments={
        "prompt": synthesised_prompt,
        "image_urls": [p.url for p in pinned][:4],   # the pins, as actual conditioning
    },
    with_logs=True,
    on_queue_update=lambda s: publish(session_id, s),
)
```

`kontext/max/multi` accepts **multiple reference images** via `image_urls`. This is the single most important integration decision in the product: it is what makes pinning functional rather than theatrical. Unpin an image, regenerate, and the output visibly changes — demo that.

Fall back to `fal-ai/flux/schnell` with prompt only when there are no pins, and for any speed-critical moment on stage.

### Model ids

| Task | Ids |
|---|---|
| **Reference-conditioned** | `fal-ai/flux-pro/kontext/max/multi` (multiple `image_urls`), `fal-ai/flux-pro/kontext/max` (single `image_url`), `fal-ai/flux-pro/kontext` |
| Text→image | `fal-ai/flux/schnell` (fast), `fal-ai/flux/dev`, `fal-ai/flux-pro/v1.1-ultra`, `fal-ai/flux-2-pro`, `fal-ai/z-image-turbo` |
| Edit | `fal-ai/flux-2-pro/edit`, `fal-ai/flux/dev/image-to-image` |
| Utilities | `fal-ai/birefnet` (bg removal), `fal-ai/topaz-upscale` |

Overview pages sometimes render doc slugs that are not canonical endpoint ids — confirm any new id on its own model page.

### Client patterns

`run()` for scripts, `subscribe()` when a request can block (polls the queue for you, gives progress callbacks), `submit()` + webhook for anything slow. Async twins exist for all three — **use those inside FastAPI**. `upload_file` / `upload_image` return a fal CDN URL for passing as `image_url`.

For a 3-minute demo, `subscribe_async` with progress pushed over our WebSocket is simpler than a webhook round-trip and gives the user a live progress bar. Implement the webhook path only if generation latency makes it necessary.

### Queue over raw HTTP

| Op | Call |
|---|---|
| Submit | `POST https://queue.fal.run/{model_id}` |
| Status | `GET https://queue.fal.run/{model_id}/requests/{id}/status` (`?logs=1`) |
| Result | `GET https://queue.fal.run/{model_id}/requests/{id}` |
| Cancel | `PUT .../cancel` |

`IN_QUEUE` → `IN_PROGRESS` → `COMPLETED`. Requests are never dropped and retry up to 10 times.

### Webhooks — if used, verify the signature

Attach with `?fal_webhook=<url>` on submit. Payload: `{request_id, gateway_request_id, status: "OK"|"ERROR", payload, error, payload_error}`. Headers: `X-Fal-Webhook-Request-Id`, `-User-Id`, `-Timestamp`, `-Signature` (hex Ed25519).

1. Fetch JWKS from `https://rest.fal.ai/.well-known/jwks.json`, cache 24 h.
2. Reject if `abs(now - timestamp) > 300` s.
3. Message = `"\n".join([request_id, user_id, timestamp, sha256_hex(raw_body)])`, UTF-8.
4. Ed25519-verify against each JWKS key's base64url `x` field.

```python
message = "\n".join([request_id, user_id, timestamp,
                     hashlib.sha256(raw_body).hexdigest()]).encode()
VerifyKey(base64.urlsafe_b64decode(key["x"]).hex(), encoder=HexEncoder) \
    .verify(message, bytes.fromhex(signature_hex))
```

Needs `pynacl`. **Hash the raw bytes; parse JSON only after verification passes.** Return 2xx to confirm delivery.

### Limits and headers

The throttle is **concurrency, not RPS**. New accounts start at **2 concurrent requests**, up to 40 self-serve. A `429` of type `concurrent_requests_limit` with `X-Fal-needs-retry: 1` means retry, not fail — `subscribe()` handles it.

| Header | Why |
|---|---|
| `X-Fal-Store-IO: 0` | **Set on every call.** Suppresses 30-day payload retention — our prompts contain user speech. |
| `X-Fal-Queue-Priority` | `normal` / `low` |
| `X-Fal-No-Retry: 1` | where a duplicate would be wrong |

Billed per successful output; server errors are not billed and queue wait is free.

---

## Image lanes — the reference sources

Not a hackathon partner, but load-bearing, so it is documented here.

**Lane A — cited (Cala-driven).** For each `context[].origins[].document.url` from `knowledge/search`: fetch the page, parse with **selectolax**, extract in priority order `og:image` → `twitter:image` → `<link rel="image_src">` → the largest `<img>` in the article body. Carry `source.name` and `document.name` through to the candidate so the UI can badge it with its publisher.

**Lane B — open (always on).** Runs in parallel with Lane A, every time.

- **Wikimedia Commons** — `https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch=<q>&gsrlimit=20&prop=imageinfo&iiprop=url|extmetadata&format=json`. Free, no key, excellent for people, places, works and historical material. Respect the User-Agent policy: send a real UA with a contact URL.
- **Openverse** — `https://api.openverse.org/v1/images/?q=<q>`. Permissively licensed, broad, has a documented anonymous rate limit; register for a client id if it bites.

Both lanes converge on one normalisation step: fetch headers only first, reject non-image content types, cap size, decode with Pillow, reject anything under ~400px on the short edge, compute a perceptual hash, dedupe against the session's Redis hash set, then stream to the client.

**Every candidate carries its lane and its attribution** — `cited` shows the publisher and document; `open` shows the licence and author. Displaying that distinction is what makes the Cala claim honest, and it costs one badge component.

**This fetcher is the app's main attack surface.** It requests arbitrary URLs discovered from the open web. See `docs/SECURITY.md` — allowlisting, redirect limits, private-IP rejection and size caps are not optional, and it is the reason Aikido Zen's SSRF detection is a real answer rather than a sponsor logo.

---

## 5. Aikido — security

Free tier: 10 repos, 2 users, 2 container images, 1 domain, 1 cloud account, 10 AI autofixes/mo, **250,000 protected requests/mo** (the Zen quota), rescan every 3 days.

Aikido matters more in this product than in most. We run a service that **fetches arbitrary URLs discovered from the open web** and feeds the results into an image decoder. That is an SSRF surface and a malformed-media surface at the same time. Zen is a genuine control here, not a checkbox.

### Connect the repo

GitHub **App**, not a token — Aikido stores no tokens. Sign in at https://app.aikido.dev, connect the org, grant access to **this repository only**. First results land in about a minute. A **separate** "Aikido PR Checks app" handles PR gating.

### CI gating

```yaml
# .github/workflows/aikido.yml
name: Aikido Security
on:
  pull_request:
    branches: ['*']

jobs:
  aikido-security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: AikidoSec/github-actions-workflow@v1.0.13
        with:
          secret-key: ${{ secrets.AIKIDO_SECRET_KEY }}
          fail-on-timeout: true
          fail-on-dependency-scan: true      # works on free tier
          fail-on-sast-scan: false           # paid plans only
          fail-on-iac-scan: false            # paid plans only
          minimum-severity: 'CRITICAL'
          timeout-seconds: 180
          post-scan-status-comment: 'only_if_new_findings'
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

`secret-key` from https://app.aikido.dev/settings/integrations/continuous-integration.

Two things to state openly in the writeup, because getting them right is itself a signal:

- Aikido's README **deprecates this Action** in favour of dashboard PR gating (no CI minutes, better bulk management). We run **both** — the Action because it is visible, reviewable evidence in a public repo, and dashboard gating because it is the recommended path.
- On the free tier only **dependency** findings can fail a build. SAST findings appear in the dashboard but cannot gate. Do not claim otherwise.

### safe-chain — free malware blocking for pnpm **and** uv

```bash
curl -fsSL https://github.com/AikidoSec/safe-chain/releases/latest/download/install-safe-chain.sh | sh
npm safe-chain-verify
# in CI, append --ci to the installer
```

Intercepts installs and checks against Aikido Intel before packages hit disk. Covers **npm, npx, yarn, pnpm, pnpx, bun, bunx** and **pip, pip3, uv, poetry, uvx, pipx, pdm** — both halves of our stack. Blocks packages published in the last 48 hours by default. Tokenless and free, which matters because Aikido's own malware-in-dependencies scanner is paid. Cheapest real security win available today.

### Secrets pre-commit hook

```bash
curl -fsSL https://raw.githubusercontent.com/AikidoSec/pre-commit/6cc79e039ee78b206520f143d618a44665c904b3/installation-samples/install-global/install-aikido-hook.sh | bash
```

Installs to `~/.git-hooks`, backed by `aikido-local-scanner`. We hold six provider keys in a public repo's working directory. Install it on all three machines at 09:30.

### Local scanning

```bash
docker run --rm -v "$PWD:/repo" aikidosecurity/local-scanner:latest \
  aikido-local-scanner scan /repo --apikey "$AIKIDO_API_KEY" \
  --repositoryname glia --branchname main \
  --scan-types code dependencies iac secrets --fail-on critical
```

### Scanner coverage

| Scanner | Coverage |
|---|---|
| SAST | Python ✅, TypeScript ✅ — cross-file taint analysis (Aikido + Opengrep) |
| SCA | `pnpm-lock.yaml` ✅, `uv.lock` ✅ — scans **subfolder lockfiles**, so one connection covers the monorepo |
| Secrets | all files, with **live secret validation** (Aikido + Gitleaks) |
| IaC | Terraform, YAML IaC (Aikido + Checkov) |
| Malware in deps | **paid only** → use safe-chain |

`pyproject.toml` alone is **not** a supported Python dependency file. `uv.lock` is. Commit it or we lose SCA coverage — which is also the only coverage that can gate CI on free.

### Zen — runtime protection

`aikido_zen`, AGPL-3.0, supports **FastAPI ^0.70**. Blocks SQL injection, NoSQL injection, command injection, path traversal and **SSRF** at runtime, plus attack-wave detection, per-route rate limiting, bot and country blocking, user tracking, and auto-generated API docs from live traffic. Instrumented DBs include psycopg and asyncpg.

```python
# apps/api/glia/main.py — Zen MUST be the first import, before everything else
import aikido_zen
aikido_zen.protect()

from fastapi import FastAPI
from aikido_zen.middleware import AikidoFastAPIMiddleware

app = FastAPI()
app.add_middleware(AikidoFastAPIMiddleware)
```

```bash
uv add aikido_zen
export AIKIDO_TOKEN=AIK_RUNTIME_...
AIKIDO_BLOCK=false uvicorn glia.main:app --reload   # detect-only while building
AIKIDO_BLOCK=true  uvicorn glia.main:app            # blocking, for the demo
```

`AIKIDO_BLOCK` **defaults to detect-only** — it must be explicitly `true` to block. Token from https://app.aikido.dev/runtime/services → apps → Add app → Generate token.

Build in detect-only. Our image fetcher deliberately makes outbound requests to unfamiliar hosts, and a false positive at 18:00 would break the demo path. Flip to blocking at 17:30 and re-run the happy path before recording.

**Demo beat:** speak a prompt containing a crafted URL, or hit an endpoint with an SSRF payload, and show Zen blocking it live — then show the same event in Glia's own security panel via the API below. That lands better than a generic SQLi demo because it is a threat this product actually has.

### Public REST API — powers the in-app security panel

**Base** `https://app.aikido.dev/api/public/v1` (EU). **Auth** OAuth 2.0 client credentials against `https://app.aikido.dev/api/oauth/token`, HTTP Basic with `client_id:client_secret`, returns a bearer JWT.

| Endpoint | Use |
|---|---|
| `GET /open-issue-groups` | live open findings; paginate on `X-Has-Next-Page` |
| `GET /issues/export?format=json&filter_status=open` | findings table + severity counts |
| `GET /repositories/code` | resolve `code_repo_id` |
| `GET /repositories/code/{id}/licenses/export?format=sbom&include_vex=1` | CycloneDX SBOM |

**Call from FastAPI only** — the client secret and bearer token must never reach the browser. Cache 30–60 s.

---

## 6. Entire — provenance for the build

```bash
brew tap entireio/tap && brew trust entireio/tap && brew install --cask entire
# or: curl -fsSL https://entire.io/install.sh | bash
entire version
```

### Enable

```bash
cd glia
entire enable -y --agent claude-code
entire status
```

Writes `.entire/settings.json`, `.entire/.gitignore`, `.entire/redactors/` (**commit these**) and `.entire/settings.local.json`, `logs/`, `tmp/`, `metadata/`, `current_session` (**do not commit** — the generated `.gitignore` handles it). Agent hooks go into `.claude/settings.json`.

Agents: `claude-code`, `codex`, `gemini`, `opencode`, `cursor`, `copilot-cli`, `factoryai-droid`, `pi`, `custom`. The GitHub App is **not required for local capture** — only for the hosted view and mirrors.

### How it binds to commits

Not git notes. Default backend since CLI 0.10.0 is `git-refs`: one ref per checkpoint at `refs/entire/checkpoints/<shard>/<id>`, ids are 26-char ULIDs. The link is a **commit-message trailer, `Entire-Checkpoint`**, written by a git hook. At commit time you are prompted to link the active agent session — answer `[a]lways` once.

### Commands we use

```bash
entire why apps/api/glia/discovery/lanes.py     # the demo command
entire blame apps/api/glia/discovery/lanes.py
entire checkpoint list --json
entire checkpoint explain HEAD~3
entire search "why do we badge cited vs open"
entire session resume
entire recap
entire doctor
```

`entire session resume BRANCH --force` **can reset git state** to the last checkpointed commit. Do not run it with `--force` today.

### Privacy — read before enabling on a public repo

**Checkpoints live in our own git repository, not Entire's servers.** On a **public** repo that history is public. Five always-on redaction passes run first: entropy scoring (10+ chars, Shannon > 4.5), ~260 Betterleaks patterns, credentialed URIs, database connection strings, bounded credential values.

Enable the optional layers too, in `.entire/settings.json`:

```json
{ "redaction": {
    "pii": { "enabled": true },
    "openai_privacy_filter": { "enabled": true, "categories": { "private_person": true } },
    "externalize_images": true },
  "telemetry": false }
```

Telemetry is on by default (PostHog, EU) capturing command and flag names, not values — we turn it off. Fully local mode: `entire configure --project --skip-push-sessions`.

Pricing is undocumented. The CLI is MIT-licensed and stores data in our own repo, so local capture works without a paid account.

---

## Environment variables

```dotenv
# OpenAI — realtime transcription + prompt synthesis
OPENAI_API_KEY=
OPENAI_TRANSCRIBE_MODEL=gpt-live-transcribe
OPENAI_SYNTHESIS_MODEL=gpt-5.5
OPENAI_REALTIME_TOKEN_TTL=600

# Cala — entity resolution + cited-source discovery
CALA_API_KEY=
CALA_BASE_URL=https://api.cala.ai/v1
CALA_MIN_SECONDS_BETWEEN_QUERIES=8
CALA_CREDIT_BUDGET=1100

# Pioneer (Fastino Labs) — the distiller
PIONEER_API_KEY=
PIONEER_BASE_URL=https://api.pioneer.ai/v1
PIONEER_DISTILL_MODEL=fastino/gliner2-large-v1
PIONEER_PII_MODEL=fastino/gliner2-privacy-filter-PII-multi

# fal — generation. Use an API-scoped key, never ADMIN.
FAL_KEY=
FAL_REFERENCE_MODEL=fal-ai/flux-pro/kontext/max/multi
FAL_FALLBACK_MODEL=fal-ai/flux/schnell

# Image lanes
OPENVERSE_CLIENT_ID=
OPENVERSE_CLIENT_SECRET=
IMAGE_FETCH_USER_AGENT=glia/0.1 (https://github.com/<org>/glia)

# Aikido
AIKIDO_TOKEN=
AIKIDO_BLOCK=false            # true for the demo
AIKIDO_API_CLIENT_ID=
AIKIDO_API_CLIENT_SECRET=
AIKIDO_API_BASE_URL=https://app.aikido.dev/api/public/v1

# App
DATABASE_URL=postgresql+asyncpg://glia:glia@localhost:5432/glia
REDIS_URL=redis://localhost:6379/0
WEB_ORIGIN=http://localhost:5173
LOG_LEVEL=info

# Frontend — anything VITE_ prefixed is PUBLIC. Never a credential.
VITE_API_BASE_URL=http://localhost:8000
```

`apps/web` receives **no** provider keys. The browser's only credential is the short-lived OpenAI ephemeral token, which our backend mints, scopes to a transcription session and expires in 600 seconds.

## Undocumented — do not assert these in the submission

- **OpenAI:** no end-to-end WebRTC + transcription-session example exists; whether `/realtime/calls` wants raw SDP or a form body; whether `sendonly` transceiver config is needed; concurrent Realtime session caps; whether `?model=` is accepted on the WebSocket URL.
- **Cala:** whether `/v1/entities` and introspection consume credits; `Retry-After` and `X-RateLimit-*` headers; the formal Cala QL grammar; any data-freshness SLA. **And: Cala returns no images — never imply otherwise.**
- **Pioneer:** the literal `result` response body for GLiNER2; per-token pricing for frontier decoders; whether `threshold` is honoured on the chat-completions path.
- **fal:** a framework-agnostic proxy export; a published requests/second rate limit.
- **Aikido:** exact GitHub App permission scopes; the complete IaC filetype list; which Zen features are free vs paid.
- **Entire:** the exact git hook names installed; encryption at rest; retention periods; pricing.
