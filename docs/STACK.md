# Stack & architecture

Every choice here is made. Rationale and rejected alternatives are recorded so nobody relitigates them at 16:00.

## The product, in one paragraph

**Glia is a verifiable workspace.** It looks like Notion: blocks, slash commands, drag handles. The difference is that every AI-written claim carries provenance. Ask Glia to draft a section and it grounds each claim in Cala's verified entity graph, so the sentence you read is backed by a publisher URL, a re-fetchable upstream API endpoint and a SHA-256 hash of the response that produced it. Claims that cannot be grounded are rendered as visibly unverified rather than silently asserted. Media is generated with fal, all model traffic is routed and PII-scrubbed through Pioneer, the runtime is defended by Aikido Zen, and the repo itself is auditable because Entire binds every commit to the agent session that produced it.

The thesis is one word: **provenance, all the way down** — from a sentence in a document, to the API response that justifies it, to the commit that shipped the code, to the prompt that wrote the commit.

Glial cells do not fire. They connect, insulate and route. That is the product.

## Shape of the repo

```
glia/
├── apps/
│   ├── web/                 # Vite + React 19 + TS — the workspace UI
│   └── api/                 # FastAPI + Python 3.13 — the only thing holding secrets
├── packages/
│   ├── ui/                  # shadcn-based primitives, Tailwind v4 preset
│   ├── editor/              # BlockNote custom blocks (VerifiedFact, EntityCard, Media)
│   ├── api-client/          # generated from the FastAPI OpenAPI schema
│   └── tsconfig/            # shared TS + Biome config
├── infra/
│   ├── docker-compose.yml   # postgres 17 + pgvector, redis 7
│   └── Dockerfile.*         # api, web
├── docs/
└── .github/workflows/
```

`pnpm-workspace.yaml` covers `apps/*` and `packages/*`. The Python app lives inside the same repo but is managed by `uv`, not pnpm — Turborepo shells out to `uv run` for its tasks. One repo, two package managers, one lockfile each. Aikido scans lockfiles in subfolders, so this shape is fully covered by one connected repository.

## Monorepo

**pnpm 10 workspaces + Turborepo.**

pnpm because the content-addressed store makes installs fast and, more importantly, because its strict non-flat `node_modules` prevents phantom dependencies — a package can only import what it declares. That is a correctness property, not a speed one.

Turborepo for task orchestration and content-hash caching. `turbo run build` skips anything whose inputs did not change. On a one-day build with 3 people pushing constantly, this is the difference between a 4-second and a 90-second feedback loop.

*Rejected:* Nx (heavier, plugin-driven, more config than a one-day project can amortise). Bun workspaces (fast, but we need a boring toolchain today, and pnpm's lockfile is what Aikido SCA reads).

## Frontend

**Vite 7 + React 19 + TypeScript 5.x strict.**

Vite for dev-server startup measured in milliseconds. If the build ever feels slow, switch the bundler in one line by aliasing `vite` to `rolldown-vite` — Rolldown is Vite's Rust bundler and is a drop-in for our usage. Do not do this on day one; do it only if builds actually hurt.

React 19 for the compiler (auto-memoisation, so we stop hand-writing `useMemo` in an editor that re-renders constantly), Actions, and `use()`. A block editor is the exact workload where the compiler earns its keep.

**TanStack Router** for type-safe file-based routing — the route params and search params are typed end to end, which removes an entire class of runtime bugs we do not have time to debug. **TanStack Query v5** for all server state: caching, background refetch, optimistic updates, and request deduplication we would otherwise hand-roll.

**Tailwind CSS v4** — the Oxide engine is Rust, CSS-first config via `@theme`, no `tailwind.config.js`, and incremental rebuilds are sub-millisecond. **shadcn/ui** on Radix primitives for accessible components we own the source of, rather than a dependency we fight.

**Zustand** for the small amount of genuinely client-side state (panel open, selection, command palette). No Redux. Server state is Query's job; document state is Yjs's job; Zustand covers what is left, which is little.

**Biome** instead of ESLint + Prettier. One Rust binary, lint and format, ~20x faster, one config file. On a hackathon the value is that nobody argues about formatting and CI takes two seconds.

*Rejected:* Next.js. We do not need SSR or its server runtime — the backend is Python, so Next would be a second server doing nothing but proxying, and its build is slower. The one thing Next would have given us free is fal's `@fal-ai/server-proxy/nextjs` handler; we implement that 20-line proxy in FastAPI instead, which is where the key belongs anyway. *Rejected:* Remix/React Router 7 framework mode, same reason. *Rejected:* SvelteKit/Solid — faster, but we lose the BlockNote/TipTap ecosystem, which is the whole product surface.

## The Notion-like editor — the important choice

**BlockNote**, which sits on **TipTap v3**, which sits on **ProseMirror**.

ProseMirror is the correct document model: a schema-validated tree with transactional updates and a real position system. Every serious block editor (Notion, Linear, Coda) is built on something shaped like it. TipTap is the ergonomic layer over it. BlockNote is the Notion-shaped layer over TipTap — it ships block structure, the slash menu, drag handles, nested blocks, side menus and a formatting toolbar out of the box, and exposes a custom-block API.

Building those affordances from raw TipTap costs a full day. We have seven hours. Take BlockNote, spend the saved time on the custom blocks that are actually our product:

| Custom block | What it does |
|---|---|
| `VerifiedFact` | A claim plus its provenance chip. Click to expand the source panel: publisher, document, upstream endpoint, response hash, retrieval date. |
| `EntityCard` | A Cala entity rendered as a live card — properties with per-field sources, relationships, numerical observations. |
| `CitationChip` | Inline mark that links a text span to a `KnowBit` id from Cala's `context[]`. |
| `GeneratedMedia` | A fal output (image/video/audio) with the exact model id, prompt and request id recorded alongside it. |
| `UnverifiedClaim` | The honest one. Model asserted something Cala could not ground. Rendered with a warning treatment. This block is the demo's most persuasive moment. |

*Rejected:* Plate (Slate-based — Slate's document model has known selection and normalisation sharp edges under collaborative editing). Lexical (excellent and fast, but its plugin ecosystem for Notion-shaped UX is thinner, so we would be building drag handles ourselves). Raw TipTap (right answer with two more days).

**Persistence.** The document is a **Yjs** CRDT. Locally it syncs to IndexedDB via `y-indexeddb`, so the editor is instant and survives a refresh with no network. The server stores the Yjs update binary as a `bytea` column plus a derived JSON projection for search and for the AI to read. Multiplayer is a stretch goal: if there is time after freeze, drop in **Hocuspocus** (the TipTap team's y-websocket server) — but the CRDT choice means single-player today and multiplayer later is an additive change, not a rewrite. Note it does mean one Node process for the websocket if we get there; the Python API remains authoritative for everything else.

**Never store HTML.** Store ProseMirror/Yjs JSON. HTML in a database is an XSS vector waiting for a careless render; a schema-validated node tree is not.

## Backend

**Python 3.13 + FastAPI + uvicorn, managed by `uv`.**

`uv` because it resolves and installs in a second or two, and because `uv.lock` is a real lockfile that Aikido's SCA scanner reads. `pyproject.toml` alone is not scannable — the lockfile is what gets us dependency coverage, which matters since dependency findings are the ones that can gate our CI on the free tier.

FastAPI for async-native I/O — this service is almost entirely fan-out to Cala, Pioneer and fal, so the concurrency model is the whole performance story — plus Pydantic v2 (Rust core) giving us validation and an OpenAPI schema for free. That schema generates `packages/api-client`, so the frontend's types cannot drift from the backend's.

**SQLAlchemy 2.0 async + Alembic**, against **PostgreSQL 17 + pgvector**. One database. Documents, users, orgs, cached Cala responses and embeddings all live there — pgvector means no separate vector store to operate. **Redis 7** for rate-limit counters, response caching and the job queue.

**taskiq** (or `arq`) for background work: fal generations that outlive a request, Cala batch grounding, and re-verification sweeps. Not Celery — Celery's config surface and worker model cost more than they return here.

**httpx** with explicit timeouts and `tenacity` retries for every outbound call. **structlog** for JSON logs with a request id and, when applicable, the Entire session id — so a log line can be traced back to the prompt that caused the code that emitted it.

**ruff** (lint + format) and **mypy --strict**. Both are fast enough to run pre-commit.

*Rejected:* Litestar (genuinely nice, smaller ecosystem, and FastAPI's docs advantage matters when three people are moving fast). Django (ORM and admin are great; the async story and the weight are not what we want). Node for the backend — the brief specifies Python, and Python is where the AI tooling lives anyway.

## AI layer

Three providers with strictly separated jobs. This separation is the architectural argument, and it is what makes five partner integrations coherent rather than decorative.

```
                    ┌──────────────────────────────────────────┐
   user prompt ───▶ │ 1. GLiGuard    injection / abuse screen   │
                    │ 2. GLiNER2-PII redact spans → placeholders│
                    │ 3. Cala        ground claims, get sources │
                    │ 4. Pioneer     generate over grounded ctx │
                    │ 5. rehydrate   restore PII placeholders   │
                    │ 6. fal         media, if the block asks   │
                    └──────────────────────────────────────────┘
```

**Cala is the ground truth.** Not a search tool bolted on — the retrieval step that runs *before* generation. `POST /v1/knowledge/search` returns `content` plus `explainability[]` (claim → supporting quote ids) plus `context[]` (quote → publisher URL + document URL). That structure maps one-to-one onto our `VerifiedFact` block, which is why the product design and the API design agree. For entity detail we call `POST /v1/entities/{id}`, which returns each property as `{value, sources[]}` where a source carries the **upstream endpoint plus a SHA-256 `response_hash`** — genuinely auditable, because you can re-fetch and compare. Two provenance shapes, two parsers; see `docs/PARTNERS.md`.

**Pioneer is the only egress to a language model.** One OpenAI-compatible base URL, `pioneer/auto` for routing, `claude-opus-5` when a task needs the ceiling. Because there is exactly one gateway, PII redaction and guardrails are enforced in exactly one place — a security property, not a convenience. Its encoder models do the guarding: `fastino/gliner2-privacy-filter-PII-multi` returns 42 PII labels with character spans, and `fastino/gliguard-LLMGuardrails-300M` classifies prompts before they cost anything.

**fal is media only.** Server-proxied, never called from the browser, queue + webhook for anything slow, Ed25519 signature verification on the webhook, `X-Fal-Store-IO: 0` so payloads are not retained.

*Rejected:* calling OpenAI/Anthropic directly. It would work and we have credits, but it gives up the single-gateway property and the redaction chokepoint, and it drops a partner integration that is doing real work.

## Security posture

Full detail in `docs/SECURITY.md`. The stack-level decisions:

- **Aikido Zen** (`aikido_zen`) is the **first import** in the FastAPI entrypoint, before anything else. Runtime blocking of SQLi, NoSQLi, command injection, path traversal and SSRF, plus per-route rate limiting and user identification.
- **Aikido CI**: `AikidoSec/github-actions-workflow` gating on new critical dependency findings, plus dashboard PR checks.
- **`@aikidosec/safe-chain`** wraps both `pnpm` and `uv` installs and blocks malicious packages before they touch disk. Free, tokenless, and it covers the one gap in Aikido's free tier (malware detection in dependencies is paid).
- **Postgres row-level security** for tenant isolation, enforced in the database rather than in application `WHERE` clauses.
- **The frontend holds no secrets.** Not the fal key, not the Cala key, not the Pioneer key. Every third-party call is proxied by FastAPI. This is why we did not want a Next.js BFF: fewer places a key can leak.

## Provenance of the build itself

**Entire** is enabled on the repo with `--agent claude-code`. Every commit gets an `Entire-Checkpoint` trailer linking it to the agent session, prompts and tool calls that produced it, stored as git refs in our own repository with five always-on redaction passes.

This is not a checkbox. Our product's claim is that AI output should be traceable to its source. Entire makes that claim true of our own codebase, so the demo can end with `entire why apps/api/glia/grounding/cala.py:42` and show the prompt behind the code — the same accountability the product gives to documents, applied to itself. Judges notice when a submission's method matches its thesis.

## Deploy

Docker Compose locally. For the demo: API on **Fly.io** or **Railway** (one container, Postgres + Redis alongside), web on **Vercel** or **Cloudflare Pages** as a static SPA build. Neither is load-bearing — pick whichever authenticates fastest at 17:00 and do not spend a minute more on it.

## Version pins

Pin exact versions in both lockfiles and commit them. On a hackathon, a transitive dependency shifting under you at 17:45 is the failure mode that ends runs. `pnpm install --frozen-lockfile` and `uv sync --frozen` in CI, always.
