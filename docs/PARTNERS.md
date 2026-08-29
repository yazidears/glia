# Partner technology reference

Five partner technologies. The rules require three. Every entry below records exact base URLs, auth headers, identifiers and gotchas, verified against vendor documentation on 29 Aug 2026. Where something is undocumented it says so — do not guess in the submission writeup.

Environment variables are listed per section and collected in `.env.example`.

---

## 1. Cala — verified data with provenance

Cala is the grounding layer. It returns structured facts with citations instead of pages to parse.

**Base URL** `https://api.cala.ai/v1`
**Auth header** `X-API-KEY: <key>` — *not* `Authorization: Bearer`
**Env var** `CALA_API_KEY` (our convention; Cala documents no server-side convention)
**Keys** https://console.cala.ai/api-keys
**SDK** none. Raw HTTP. OpenAPI spec at `https://api.cala.ai/openapi.json` if we want to codegen.

### Endpoints

| Endpoint | Method | Returns |
|---|---|---|
| `/v1/knowledge/search` | POST | Markdown answer + claim-level citations |
| `/v1/knowledge/query` | POST | Typed JSON rows (no citations) |
| `/v1/entities` | GET | Fuzzy entity name search |
| `/v1/entities/{entity_id}` | **POST** | Full entity with field-level sources |
| `/v1/entities/{entity_id}/introspection` | GET | What fields exist, before you ask for them |

Note `/v1/entities/{id}` is **POST**, not GET — the body selects which properties and relationships to return.

### `/v1/knowledge/search` — the one that gives us provenance

```bash
curl -X POST https://api.cala.ai/v1/knowledge/search \
  -H "X-API-KEY: $CALA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "Who founded Anthropic and what is their background?"}'
```

Request: `input` (string, required), `explainability` (bool, default `true`), `return_entities` (bool, default `true`).

Response shape, and how it maps onto our editor:

```jsonc
{
  "content": "markdown answer",              // → the block's text
  "explainability": [                         // → per-claim provenance
    { "content": "supporting statement",
      "references": ["<knowbit-uuid>"] }      // → points into context[]
  ],
  "context": [                                // → the sources panel
    { "id": "<knowbit-uuid>",
      "content": "the quoted evidence",
      "origins": [
        { "source":   { "name": "Impact Loop", "url": "https://..." },
          "document": { "name": "Article title", "url": "https://..." },
          "breadcrumb": [""] }
      ] }
  ],
  "entities": [                               // → EntityCard blocks
    { "id": "<uuid>", "name": "Altano Energy",
      "entity_type": "Company", "mentions": ["Altano Energy", "Altano"] }
  ]
}
```

`explainability[].references` → `context[].id` → `origins[].source.url`. That chain is the `VerifiedFact` block. `entities[].mentions` gives the surface strings to link spans in `content` back to canonical entity UUIDs.

### `/v1/knowledge/query` — typed rows, **no citations**

```bash
curl -X POST https://api.cala.ai/v1/knowledge/query \
  -H "X-API-KEY: $CALA_API_KEY" -H "Content-Type: application/json" \
  -d '{"input": "startups.location=Spain.funding>10M.funding<=50M"}'
```

Returns `{ "results": [...], "entities": [...] }`. **Two traps:**
1. There is no `explainability` and no `context` on this endpoint. Rows are unattributed. If a block needs provenance, use `/knowledge/search`, or query for entity ids and then `POST /v1/entities/{id}` for sourced fields.
2. `results` row keys are derived per query, not a fixed schema. Never assume stable column names — render dynamically from the returned keys.

### Cala QL (dot notation)

Chained navigation with inline filters. Operators: `.` navigate, `=` match, `!=` exclude, `>` `<` `>=` `<=` compare. Magnitude suffixes (`10M`) work.

```
OpenAI.founded.year
ibex35.companies.employee_count>2000
companies.founder.incorporation>2020.previous_job=Google
startups.location=Spain.funding>10M.funding<50M
```

Both `/knowledge/*` endpoints accept plain natural language in the same `input` field, interchangeably. **Undocumented:** OR, grouping, sorting, pagination, escaping of literals containing `.` or `=`. Do not build a UI that promises them.

### Entity search and detail

```bash
curl "https://api.cala.ai/v1/entities?name=OpenAI&entity_types=Company&limit=20" \
  -H "X-API-KEY: $CALA_API_KEY"
```

`name` (required), `entity_types` (array), `limit` (1–100, default 20). Entity types seen: `Entity, Company, Person, Product, Organization, GPE, Country, CountryRegion, EducationalInstitution, Facility, Industry, Language, Law, Location, CorporateEvent, WorkOfArt, Animal, Award`.

Call `GET /v1/entities/{id}/introspection` first to discover available properties, relationships and numerical observations, then request only what you need:

```bash
curl -X POST https://api.cala.ai/v1/entities/<uuid> \
  -H "X-API-KEY: $CALA_API_KEY" -H "Content-Type: application/json" \
  -d '{
    "properties": ["name", "aliases", "registered_address", "employee_count"],
    "relationships": { "outgoing": {"IS_ULTIMATE_PARENT": {"limit": 5}},
                       "incoming": {"IS_CEO_OF": {}} }
  }'
```

### Two provenance shapes — write two parsers

`/knowledge/search` origins:
```json
{ "source": {"name": "...", "url": "..."},
  "document": {"name": "...", "url": "..."}, "breadcrumb": [""] }
```

`/entities/{id}` property sources — **this is the auditable one**:
```json
{ "name": "GLEIF",
  "document": { "endpoint": "https://api.gleif.org/api/v1/lei-records?...",
                "params": {},
                "response_hash": "7089723cc94015908b284e2637d34fca0d700bccca36b0f83e4fb6e93c211437" },
  "date": "2026-02-26" }
```

A re-fetchable upstream endpoint plus a SHA-256 of the response. **This is our headline demo moment:** re-hit the source, hash it, compare. That is verification, not a citation link.

Handle `sources: []` — some derived fields (`aliases`, `bics`) carry no attribution. Render those as unattributed rather than pretending.

### MCP

```json
{ "mcpServers": {
    "Cala": { "url": "https://api.cala.ai/mcp/",
              "headers": { "X-API-KEY": "YOUR_CALA_API_KEY" } } } }
```

VS Code uses `"servers"` + `"type": "http"`. Claude Desktop bridges stdio via `npx mcp-remote https://api.cala.ai/mcp/ --header "X-API-KEY: ..."`. Tools: `knowledge_search`, `knowledge_query`, `entity_search`, `entity_introspection`, `retrieve_entity`.

### Limits — plan around these

| Plan | Credits/mo | Rate limit |
|---|---|---|
| Starter (free) | 100 | **10 req/min** |
| Explore $50 | 1,100 | 100 req/min |
| Build $200 | 5,000 | 100 req/min |

1 credit = 1 query. **10 requests per minute on free tier is the real constraint on the demo.** Mitigations, all mandatory:
- Cache every Cala response in Postgres keyed by a hash of `input`, with the raw JSON kept for the provenance panel.
- Redis token-bucket in front of the client at 8 req/min, queued not dropped.
- Pre-warm the demo document's queries before going on stage. Do not do live cold Cala calls at 20:00.

`429` returns `{"error": "rate_limit_exceeded", ...}`; `422` for validation. **Undocumented:** whether entity/introspection calls consume credits, `Retry-After` headers, concurrency limits.

Coverage is finance- and compliance-heavy: SEC/EDGAR, GLEIF, business registries, OFAC/EU/UN sanctions, PEPs, PACER and CourtListener, Fed/ECB/BIS series, Moody's/S&P/Fitch, Reuters and PR Newswire. Healthcare, HR and agro are advertised but have no named sources — **do not build the demo on those verticals.** Freshness has no SLA, but entity properties carry a per-field `date`, so recency is observable at read time. Show that date in the UI; it is honest and it looks rigorous.

---

## 2. Pioneer (Fastino Labs) — the single model gateway

**API root** `https://api.pioneer.ai`
**OpenAI-compatible base_url** `https://api.pioneer.ai/v1` → `/chat/completions`, `/completions`, `/responses`, `/models`
**Anthropic-compatible** same base URL → `/v1/messages`
**Native** `POST https://api.pioneer.ai/inference`
**Auth** `X-API-Key: <key>`, or `Authorization: Bearer <key>`
**Env var** `PIONEER_API_KEY` (docs convention; the SDK does not read it automatically — pass it explicitly)
**Keys** `agent.pioneer.ai/api-keys`

### Drop-in usage

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["PIONEER_API_KEY"],
    base_url="https://api.pioneer.ai/v1",
)

resp = client.chat.completions.create(
    model="pioneer/auto",                       # router picks the model
    messages=[{"role": "user", "content": "..."}],
)
```

Pioneer-specific fields (`schema`, `include_confidence`, `include_spans`) go through `extra_body` when using the OpenAI SDK.

### Model ids

| Class | Ids |
|---|---|
| Router | `pioneer/auto` |
| Frontier | `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-5`, `gpt-5.5`, `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol`, `deepseek-ai/DeepSeek-V4-Flash`, `zai-org/GLM-5.2`, `zai-org/GLM-5.2-Fast` |
| Open decoders | `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16`, `fastino/Fastino-Nemotron-3.5-Lightning-Finance`, `fastino/Fastino-Nemotron-3.5-Lightning-Healthcare` |
| Encoders (trainable) | `fastino/gliner2-base-v1`, `fastino/gliner2-large-v1`, `fastino/gliner2-multi-v1`, `fastino/gliner2-multi-large-v1` |
| Encoders (inference only) | `fastino/gliguard-LLMGuardrails-300M`, `fastino/gliner2-privacy-filter-PII-multi`, `fastino/gliguard-PII-multi` |

Encoder models are **$0.15 / 1M tokens** — cheap enough to run on every single request, which is why the redaction chokepoint is affordable.

### PII redaction before egress — our security chokepoint

```bash
curl -X POST "https://api.pioneer.ai/v1/chat/completions" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $PIONEER_API_KEY" \
  -d '{
    "model": "fastino/gliner2-privacy-filter-PII-multi",
    "messages": [{"role":"user","content":"I am John Smith, john@acme.com, +1-555-0192."}],
    "schema": {"entities": ["person", "email", "phone_number"]},
    "include_confidence": true,
    "include_spans": true
  }'
```

42 labels including `person, email, phone_number, address, government_id, passport_number, iban, payment_card, card_number, api_key, access_token, password, secret`. Languages EN, FR, ES, DE, IT, PT, NL.

**Two things to budget for.** There is **no masking helper** — we do the span surgery ourselves from `include_spans` offsets, replacing each span with a stable placeholder (`«PERSON_1»`) and rehydrating after generation. And **no example response body is published anywhere in Pioneer's docs**; the `result` field is documented only as "shape depends on the schema and task". Spend the first 15 minutes of the AI work on a spike that prints the actual response and pins the parser. Do not build against an assumed shape.

Adjacent: `fastino/gliguard-LLMGuardrails-300M` screens prompts for injection and abuse before we spend a frontier-model token.

### Structured extraction (native endpoint)

```json
POST /inference
{ "model_id": "fastino/gliner2-base-v1",
  "text": "Apple announced the MacBook Pro at WWDC in Cupertino.",
  "schema": { "entities": ["organization", "product", "event", "location"] },
  "threshold": 0.5 }
```

`schema` accepts `entities`, `classifications` (`[{task, labels[]}]`), `structures` (JSON shapes with `name`/`dtype`/`choices`), and `relations`. `text` accepts a string **or an array** for batching. Response is a discriminated union on `type`: `encoder` → `{inference_id, result, model_id, latency_ms, token_usage, model_used}`, `decoder` → `{inference_id, completion, reasoning_trace, ...}`.

### Adaptive inference (Felix)

Every call is logged; Pioneer clusters failures, retrains automatically on high-signal traces and evaluates against a held-out set. **Promotion is manual** — you choose when a new version goes live. Feedback:

```bash
curl -X POST https://api.pioneer.ai/inferences/<INFERENCE_ID>/feedback \
  -H "X-API-Key: $PIONEER_API_KEY" -H "Content-Type: application/json" \
  -d '{"verdict":"incorrect","corrected_output":{"entities":[{"text":"Tim Cook","label":"person","start":10,"end":18}]}}'
```

Endpoints live under `/felix/training-jobs` and `/felix/evaluations`. **Adaptive Inference is not available on the free plan.** If we want it in the demo, someone needs a Pro seat ($20/seat/mo incl. $40 credits).

Wire the thumbs-down in the editor to this endpoint. "Correcting a claim in the document trains the extractor" is a strong 20-second demo beat, and it costs one HTTP call.

### Rate limits

| Path | Limit |
|---|---|
| `/inference` | 5,000/min |
| `/v1/chat/completions`, `/completions`, `/responses`, `/messages` | 5,000/min |
| `/felix/training-jobs` | 20/min |
| default | 20,000/min |

`429` with `Retry-After`; `402` when credits run out; `403` at the overage ceiling. Not a constraint for us. **Data usage: Pioneer may use your data to improve models by default; opt-out is Pro/Custom only.** Given that, the PII redaction step is not optional — it is what makes routing our users' document text through Pioneer defensible.

---

## 3. fal — generative media

**Sync base** `https://fal.run`
**Queue base** `https://queue.fal.run`
**Auth header** `Authorization: Key $FAL_KEY` — *not* `Bearer`
**Env var** `FAL_KEY`
**Python** `pip install fal-client` → `import fal_client`
**JS/TS** `npm i @fal-ai/client` (the old `@fal-ai/serverless-client` is superseded)

### Key handling — non-negotiable

Keys are **account-scoped, not user-scoped**, and scoped `API` or `ADMIN`. An `ADMIN` key can deploy and delete apps and mint further keys. A leaked key bills our prepaid balance. The browser never sees it: `FAL_KEY` exists only in the FastAPI process.

### Server-side proxy (we implement this in FastAPI)

fal only publishes a handler for Next.js (`@fal-ai/server-proxy/nextjs`). There is **no documented framework-agnostic export**. The proxy contract is three rules, so we reimplement it:

1. read the target from the **`x-fal-target-url`** header
2. inject `Authorization: Key <FAL_KEY>`
3. stream the response back

**The published sample proxy does not validate the target URL — that is an open proxy.** Ours enforces an allowlist on both host (`fal.run`, `queue.fal.run`) and model id prefix, and requires an authenticated session. Client side:

```ts
import { fal } from "@fal-ai/client";
fal.config({ proxyUrl: "/api/fal/proxy" });
```

### Python client

```python
import fal_client

# blocking, polls the queue for you, gives progress callbacks
result = fal_client.subscribe(
    "fal-ai/flux/dev",
    arguments={"prompt": "..."},
    with_logs=True,
    on_queue_update=lambda s: log.info("fal", status=s),
)

# fire and forget — the production path, pairs with our webhook
handle = fal_client.submit(
    "fal-ai/flux/dev",
    arguments={"prompt": "..."},
    webhook_url="https://api.glia.app/webhooks/fal",
)
```

`run()` for scripts, `subscribe()` when a request can block, `submit()` + webhook for anything slow. Async twins exist for all three (`run_async`, `subscribe_async`, `submit_async`) — use those inside FastAPI. Uploads: `upload_file`, `upload_image`, `upload` return a fal CDN URL to pass as `image_url`/`audio_url`.

### Queue over raw HTTP

| Op | Call |
|---|---|
| Submit | `POST https://queue.fal.run/{model_id}` |
| Status | `GET https://queue.fal.run/{model_id}/requests/{id}/status` (`?logs=1`) |
| Status stream | `GET .../status/stream` (SSE) |
| Result | `GET https://queue.fal.run/{model_id}/requests/{id}` |
| Cancel | `PUT .../cancel` |

Statuses `IN_QUEUE` → `IN_PROGRESS` → `COMPLETED`. Requests are never dropped, retried up to 10 times, no queue size limit.

### Webhooks — verify the signature, this is graded

Attach with the `?fal_webhook=<url>` query param on submit (or `webhook_url=` / `webhookUrl`). Payload:

```json
{ "request_id": "...", "gateway_request_id": "...",
  "status": "OK" | "ERROR", "payload": {}, "error": "...", "payload_error": "..." }
```

Headers: `X-Fal-Webhook-Request-Id`, `X-Fal-Webhook-User-Id`, `X-Fal-Webhook-Timestamp`, `X-Fal-Webhook-Signature` (hex Ed25519).

Verification algorithm — implement exactly:

1. Fetch JWKS from `https://rest.fal.ai/.well-known/jwks.json`, cache 24 h.
2. Reject if `abs(now - timestamp) > 300` seconds.
3. Message = `"\n".join([request_id, user_id, timestamp, sha256_hex(raw_body)])`, UTF-8.
4. Ed25519-verify the hex signature against each JWKS key's base64url `x` field until one passes.

```python
message = "\n".join([request_id, user_id, timestamp,
                     hashlib.sha256(raw_body).hexdigest()]).encode()
VerifyKey(base64.urlsafe_b64decode(key["x"]).hex(), encoder=HexEncoder) \
    .verify(message, bytes.fromhex(signature_hex))
```

Needs `pynacl`. **Hash the raw bytes. Parse JSON only after verification succeeds.** Return 2xx to confirm delivery.

### Model endpoint ids

| Task | Ids |
|---|---|
| Text→image | `fal-ai/flux/schnell` (fast), `fal-ai/flux/dev`, `fal-ai/flux-pro/v1.1-ultra`, `fal-ai/flux-2-pro`, `fal-ai/z-image-turbo`, `fal-ai/nano-banana-pro` |
| Image edit | `fal-ai/flux-pro/kontext`, `fal-ai/flux-pro/kontext/max`, `fal-ai/flux-pro/kontext/max/multi`, `fal-ai/flux-2-pro/edit`, `fal-ai/flux/dev/image-to-image` |
| Utilities | `fal-ai/birefnet` (bg removal), `fal-ai/imageutils`, `fal-ai/topaz-upscale` |
| Text→video | `fal-ai/veo3.1`, `fal-ai/sora-2/text-to-video`, `fal-ai/sora-2/text-to-video/pro` |
| TTS | `xai/tts/v1` — note the `xai/` namespace, not `fal-ai/` |
| STT | `fal-ai/whisper` (`audio_url`, `task`, `language`, `chunk_level`, `diarize`) |

Overview pages sometimes render doc slugs that are not the canonical endpoint id — confirm any new id on its own model page before hardcoding.

**Use `fal-ai/flux/schnell` for the live demo.** Latency beats quality on stage.

### Limits and useful headers

The throttle is **concurrency, not RPS**. New accounts start at **2 concurrent requests**, up to 40 self-serve. Only `IN_PROGRESS` counts. A `429` of type `concurrent_requests_limit` with header `X-Fal-needs-retry: 1` means retry, not fail — `subscribe()` handles it transparently.

| Header | Use |
|---|---|
| `X-Fal-Store-IO: 0` | **Suppress the 30-day payload retention.** Set this on every call — user document text goes into these prompts. |
| `X-Fal-Queue-Priority` | `normal` / `low` |
| `X-Fal-Request-Timeout` | server-side time-to-start deadline |
| `X-Fal-No-Retry: 1` | disable retries where a duplicate would be wrong |

Billed per successful output. Server errors are not billed; queue wait is free.

---

## 4. Aikido — security, and the side challenge we intend to win

Free tier: 10 repos, 2 users, 2 container images, 1 domain, 1 cloud account, 10 AI autofixes/mo, **250,000 protected requests/mo** (the Zen quota), rescan every 3 days.

### Connect the repo

GitHub **App**, not a token — Aikido stores no tokens. Sign in at https://app.aikido.dev, connect the org, grant access to **this repository only**, scanning starts automatically and first results land in about a minute. A **separate** "Aikido PR Checks app" handles PR gating.

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
      - name: Detect new vulnerabilities
        uses: AikidoSec/github-actions-workflow@v1.0.13
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

`secret-key` comes from https://app.aikido.dev/settings/integrations/continuous-integration.

Two caveats worth stating out loud in the writeup, because getting them right is itself a signal:
- Aikido's README **deprecates this Action** in favour of dashboard PR gating (no CI minutes, better bulk management). We run **both**: the Action because it is visible, reviewable evidence in a public repo for the jury, and dashboard gating because it is the recommended path. Say so.
- On the free tier only **dependency** findings can fail a build. SAST findings appear in the dashboard but cannot gate. Do not claim otherwise.

### Local scanning

```bash
# Docker-distributed local scanner
docker run --rm -v "$PWD:/repo" aikidosecurity/local-scanner:latest \
  aikido-local-scanner scan /repo \
  --apikey "$AIKIDO_API_KEY" --repositoryname glia --branchname main \
  --scan-types code dependencies iac secrets --fail-on critical
```

Flags: `--gating-mode release|pr`, `--base-commit-id`/`--head-commit-id`, `--exclude`, `--include-dev-deps`, `--no-snippets`, `--scan-timeout` (default 900000 ms).

### safe-chain — free malware blocking for pnpm **and** uv

```bash
curl -fsSL https://github.com/AikidoSec/safe-chain/releases/latest/download/install-safe-chain.sh | sh
npm safe-chain-verify          # confirm the shims are live
# in CI, append --ci to the installer (executable shims, not shell aliases)
```

Intercepts installs and checks them against Aikido Intel before they hit disk. Covers **npm, npx, yarn, pnpm, pnpx, bun, bunx** and **pip, pip3, uv, poetry, uvx, pipx, pdm** — exactly both halves of our stack. Blocks packages published in the last 48 hours by default. Tokenless and free, which matters because Aikido's own malware-in-dependencies scanner is a paid feature. This is the cheapest real security win available today.

### Secrets pre-commit hook

```bash
curl -fsSL https://raw.githubusercontent.com/AikidoSec/pre-commit/6cc79e039ee78b206520f143d618a44665c904b3/installation-samples/install-global/install-aikido-hook.sh | bash
```

Installs to `~/.git-hooks`, backed by `aikido-local-scanner`. A hackathon repo is exactly where a key gets committed at 18:50.

### Scanner coverage for our stack

| Scanner | Coverage | Engine |
|---|---|---|
| SAST | Python ✅, TypeScript ✅, JavaScript ✅ — cross-file taint analysis | Aikido + Opengrep |
| SCA | `pnpm-lock.yaml` ✅, `uv.lock` ✅ — scans **subfolder lockfiles**, so the monorepo is covered by one connection | Aikido SCA |
| Secrets | all files, with **live secret validation** | Aikido + Gitleaks |
| IaC | Terraform, YAML IaC | Aikido + Checkov |
| Container images | separate scanner, 2 images on free | — |
| Malware in deps | **paid only** → use safe-chain | Aikido Intel |

`pyproject.toml` alone is **not** a supported Python dependency file. `uv.lock` is. This is why the backend uses `uv` — commit the lockfile or we lose SCA coverage.

### Zen — runtime protection (the differentiator)

`aikido_zen`, AGPL-3.0, supports **FastAPI ^0.70**. Blocks SQL injection, NoSQL injection, command injection, path traversal and SSRF at runtime, plus attack-wave detection, per-route rate limiting, bot and country blocking, user tracking, and auto-generated API docs from live traffic. It also instruments `openai`/`anthropic` SDK calls for model and token usage.

```python
# apps/api/glia/main.py — Zen MUST be the first import, before everything else
import aikido_zen
aikido_zen.protect()

from fastapi import FastAPI
from aikido_zen.middleware import AikidoFastAPIMiddleware
from aikido_zen import set_user

app = FastAPI()
app.add_middleware(AikidoFastAPIMiddleware)   # enables rate limiting + user identification
# in the auth dependency, after resolving the principal:
#   set_user({"id": user.id, "name": user.email})
```

```bash
uv add aikido_zen
export AIKIDO_TOKEN=AIK_RUNTIME_...
AIKIDO_BLOCK=false uvicorn glia.main:app --reload   # detect-only while building
AIKIDO_BLOCK=true  uvicorn glia.main:app            # blocking, for the demo
```

`AIKIDO_BLOCK` **defaults to detect-only** — it must be explicitly `true` to actually block. Token from https://app.aikido.dev/runtime/services → apps → Add app → Generate token.

Demo beat: fire a SQLi payload at a live endpoint with `AIKIDO_BLOCK=true`, show the request blocked, show the event in the Zen dashboard, then show the same event surfaced inside Glia's own security panel via the API below. Instrumented DBs include psycopg/asyncpg, so our stack is covered.

### Public REST API — powers our in-app security dashboard

**Base** `https://app.aikido.dev/api/public/v1` (EU). **Auth** OAuth 2.0 client credentials against `https://app.aikido.dev/api/oauth/token`, HTTP Basic with `client_id:client_secret`, returns a bearer JWT.

```bash
curl -X POST https://app.aikido.dev/api/oauth/token \
  -H "Authorization: Basic $(printf '%s' "$ID:$SECRET" | base64)" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials"
```

| Endpoint | Use |
|---|---|
| `GET /open-issue-groups` | live open findings; paginate on the `X-Has-Next-Page` header |
| `GET /issues/export?format=json&filter_status=open&filter_severities=critical` | findings table + severity counts |
| `GET /repositories/code` | resolve `code_repo_id` |
| `GET /repositories/code/{id}/licenses/export?format=sbom&include_vex=1` | **CycloneDX SBOM** for the dependency panel |

Two calls give a real dashboard. **Call this from FastAPI only** — the client secret and bearer token must never reach the browser. Cache 30–60 s.

---

## 5. Entire — provenance for the build itself

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

Writes `.entire/settings.json`, `.entire/.gitignore` and `.entire/redactors/` (**commit these**), plus `.entire/settings.local.json`, `logs/`, `tmp/`, `metadata/`, `current_session` (**do not commit** — the generated `.gitignore` handles it). Agent hooks go into `.claude/settings.json`.

Agents supported: `claude-code`, `codex`, `gemini`, `opencode`, `cursor`, `copilot-cli`, `factoryai-droid`, `pi`, `custom`.

The GitHub App is **not required for local capture** — only for the hosted view, mirrors and collaborator verification.

### How it binds to commits

Not git notes. Default backend since CLI 0.10.0 is `git-refs`: one ref per checkpoint at `refs/entire/checkpoints/<shard>/<id>`, ids are 26-char ULIDs. The link to a commit is a **commit-message trailer, `Entire-Checkpoint`**, written by a git hook at commit time. On `git commit` you are prompted to link the active agent session; answer `[a]lways` once and forget it.

### Commands we actually use

```bash
entire why apps/api/glia/grounding/cala.py      # the demo command — prompt behind the code
entire blame apps/api/glia/grounding/cala.py    # git blame + checkpoint metadata
entire checkpoint list --json
entire checkpoint explain HEAD~3
entire search "why did we cache cala responses"  # hybrid semantic + keyword
entire session resume                            # pick up an agent session across worktrees
entire recap                                     # summary of recent activity
entire review                                    # multi-agent review vs current branch
entire doctor                                    # fix stuck sessions
```

`entire session resume BRANCH --force` **can reset git state** to the last checkpointed commit. Do not run it with `--force` during the event.

### Privacy — read this before enabling on a public repo

**Checkpoints live in our own git repository, not on Entire's servers.** On a **public** repo that history is public. Five always-on redaction passes run before anything is written: entropy scoring (10+ chars, Shannon > 4.5), ~260 Betterleaks patterns, credentialed URIs, database connection strings, and bounded credential values.

Turn on the optional layers too, in `.entire/settings.json`:

```json
{ "redaction": {
    "pii": { "enabled": true },
    "openai_privacy_filter": { "enabled": true, "categories": { "private_person": true } },
    "externalize_images": true },
  "telemetry": false }
```

Telemetry is on by default (PostHog, EU) and captures command names and flag names, not values — we turn it off. Fully local mode if needed: `entire configure --project --skip-push-sessions`.

Pricing is not documented anywhere. The CLI is MIT-licensed and stores data in our own repo, so local capture works without a paid account. Treat hosted limits as an open question.

---

## Environment variables

```dotenv
# Cala
CALA_API_KEY=

# Pioneer (Fastino Labs)
PIONEER_API_KEY=
PIONEER_BASE_URL=https://api.pioneer.ai/v1

# fal — server-side only, never in apps/web
FAL_KEY=

# Aikido
AIKIDO_TOKEN=                 # Zen runtime
AIKIDO_BLOCK=false            # true for the demo
AIKIDO_API_CLIENT_ID=         # public REST API
AIKIDO_API_CLIENT_SECRET=

# App
DATABASE_URL=postgresql+asyncpg://glia:glia@localhost:5432/glia
REDIS_URL=redis://localhost:6379/0
JWT_PRIVATE_KEY=              # EdDSA, generated per environment
```

`apps/web` receives **no** provider keys. Any variable prefixed `VITE_` is compiled into the bundle and is therefore public — never put a secret behind that prefix.

## Undocumented — do not assert these in the submission

- Cala: whether entity/introspection calls consume credits; `Retry-After` headers; formal Cala QL grammar; data freshness SLA.
- Pioneer: the literal `result` response body for GLiNER2; per-token pricing for frontier decoders; whether `threshold` is honoured on the chat-completions path.
- fal: a framework-agnostic `@fal-ai/server-proxy` export; a published requests/second rate limit.
- Aikido: exact GitHub App permission scopes; the complete IaC filetype list; which Zen features are free vs paid.
- Entire: the exact git hook names installed; encryption at rest; retention periods; pricing.
