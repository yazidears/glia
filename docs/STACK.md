# Stack & architecture

Every choice here is made. Rationale and rejected alternatives are recorded so nobody relitigates them at 16:00.

## The product

**Glia is a voice-powered visual thinking tool. You speak until you see it.**

The screen starts almost empty and says *Speak your mind*. As you talk, Glia transcribes you live and starts surfacing visual references — images that drift in and reorganise as the idea sharpens. You pin the ones that resonate. Every pin teaches Glia more about the subject, mood, style, palette and composition you actually mean. When the direction feels right you hit **Generate**, and Glia composes the live conversation, the distilled essence of the idea, your pinned references and the visual direction it discovered into one original image — shown next to the transcript and a concise prompt that captures what you imagined.

It is for people who can describe a feeling but cannot write the perfect visual prompt. The gap between *"something warm and brutalist, but lonely"* and a working diffusion prompt is where this product lives.

Glial cells do not fire. They connect, insulate and route — the tissue that makes signal possible. That is the job: between a half-formed thought and an image, Glia is the connective layer.

## The pipeline

```
  mic ──WebRTC──▶ OpenAI Realtime (gpt-live-transcribe)
                        │ transcript deltas paint locally
                        │ settled turns ──▶ FastAPI over WebSocket
                        ▼
              ┌─────────────────────────────────────────┐
              │ DISTILL   Pioneer GLiNER2               │
              │ transcript → {subject, mood, style,     │
              │ palette, composition, medium, era}      │
              │ encoder model, milliseconds, ~free      │
              └───────────────┬─────────────────────────┘
                              │ gate: did the idea MATERIALLY change?
                              │ no → stop here, spend nothing
                              ▼ yes
        ┌─────────────────────┴──────────────────────┐
        │                                            │
   LANE A — cited                              LANE B — open
   Cala entity resolution                      Wikimedia Commons
   + knowledge/search                          + Openverse
   → context[].origins[].document.url          → direct image results
   → fetch those pages, extract og:image
        │                                            │
        └─────────────────────┬──────────────────────┘
                              ▼
              normalise · perceptual-hash dedupe · rank
                              │
                    WebSocket ▼  candidates stream to the grid
                        ┌──────────────┐
                        │  user pins   │
                        └──────┬───────┘
                               ▼ Generate
              prompt synthesis (transcript + attributes
              + pinned refs + visual direction)
                               │
                               ▼
              fal — flux-pro/kontext/max/multi
              pinned image URLs passed as image_urls,
              so the pins genuinely condition the output
                               │
                               ▼
              final image + transcript + the prompt
```

Two properties of this design matter more than any individual technology.

**The distiller is a cost gate, not a feature.** Cala's free tier is 100 credits *per month*. A naive "query on every pause" loop exhausts it in seconds. GLiNER2 runs on every pause because it is an encoder model at $0.15/1M tokens, and only a material change in the distilled attributes is allowed to spend a Cala credit. That is what makes a continuous loop affordable, and it is why Pioneer is load-bearing rather than optional.

**Pins are functional.** A pinned image is not a mood-board sticker that quietly gets summarised into an adjective. Its URL goes to fal as a real conditioning input. Unpin an image and the output visibly changes. If pins were decorative the product would be a demo; because they are wired to `image_urls`, it is a tool.

## What Cala actually does here

This needs stating plainly, because the naive version of this product is not buildable and the honest version is better.

**Cala returns no images.** There is no `image`, `image_url`, `thumbnail`, `logo` or `media` field anywhere in its OpenAPI schema. Its own documentation positions it as the opposite of web search: *"Web search APIs crawl the open web and return URLs, scraped text, and HTML fragments… Cala is different. It's a verified entity graph."*

What Cala does is decide **what you are talking about** and **which sources are authoritative about it**:

1. **Entity resolution.** `GET /v1/entities?name=…` turns a messy spoken mention into a canonical typed entity with a stable UUID. Speech is ambiguous; this is real disambiguation, and it makes everything downstream precise instead of keyword soup.
2. **Source discovery.** `POST /v1/knowledge/search` returns `context[].origins[].document.url` — real article pages on real publications, each paired with the publisher name and the evidence quote. We fetch those specific pages and extract `og:image`, `twitter:image` and lead images. **The reference images come from documents Cala selected and cited as evidence.**
3. **Salience.** `explainability[]` tells us which facts actually carried the answer, so we illustrate the thing that matters rather than every noun in the transcript. This also throttles query volume, which we need anyway.

So the honest claim, and the one the UI makes: *Cala identifies what you mean and which sources are credible; the references come from what it cites.* Every Lane A image carries its publisher and source document in the UI. That is something keyword image search structurally cannot offer.

**Lane B is first-class, not a fallback.** Cala's coverage is finance, legal, healthcare, HR and agro. Most of what people say out loud when thinking visually is none of those. Wikimedia Commons and Openverse carry the general cultural and visual load — free, permissively licensed, no credit anxiety. Candidates are badged **cited** or **open** in the UI. Being explicit about which lane an image came from is what keeps the Cala integration honest and worth advertising.

## Shape of the repo

```
glia/
├── apps/
│   ├── web/                    # Vite + React 19 + TS — one screen, four phases
│   └── api/                    # FastAPI — realtime session broker + discovery loop
├── packages/
│   ├── ui/                     # shadcn primitives, Tailwind v4 preset
│   ├── api-client/             # generated from the FastAPI OpenAPI schema
│   └── tsconfig/               # shared TS + Biome config
├── infra/
│   ├── docker-compose.yml      # postgres 17, redis 7
│   └── Dockerfile.*
├── docs/
└── .github/workflows/
```

`pnpm-workspace.yaml` covers `apps/*` and `packages/*`. The Python app lives in the same repo, managed by `uv`; Turborepo shells out to `uv run`. One repo, two package managers, one lockfile each — and Aikido scans lockfiles in subfolders, so a single connected repository covers both halves.

## Monorepo

**pnpm 10 workspaces + Turborepo.** pnpm for the content-addressed store and, more importantly, the strict non-flat `node_modules` that prevents phantom dependencies — a correctness property, not a speed one. Turborepo for content-hash task caching, which on a one-day build with three people pushing constantly is the difference between a 4-second and a 90-second loop.

*Rejected:* Nx (more config than a one-day project can amortise). Bun workspaces (fast, but pnpm's lockfile is what Aikido SCA reads).

## Frontend

**Vite 7 + React 19 + TypeScript strict.**

Vite for millisecond dev-server startup. If builds ever hurt, alias `vite` to `rolldown-vite` — one line, Rust bundler, drop-in. Do not do this on day one.

React 19 for the compiler. This app re-renders a live-updating image grid against a streaming transcript; auto-memoisation is exactly the workload it was built for, and it saves us hand-writing `useMemo` under time pressure.

**No router.** Glia is one screen with four phases — `idle → listening → converging → generated`. That is a state machine, not a navigation graph. A discriminated union in Zustand covers it. Adding TanStack Router here would be ceremony.

**Zustand** is the centre of the client. It holds the phase, the transcript buffer, the candidate pool, the pin set and the generation result. Everything else is derived. **TanStack Query** only for the few request/response calls (session bootstrap, history) — the live channel is a WebSocket, and pushing streamed data through Query is fighting the tool.

**Motion** (framer-motion) is not decoration here, it is the product's feel. Images arriving, reflowing and settling as the idea sharpens is the thing a judge remembers. `layoutId` for shared-element transitions when a candidate becomes a pin, `AnimatePresence` for arrival and departure, staggered entry so a batch of eight images lands as a wave rather than a flash. Budget real time for this.

**Tailwind CSS v4** — Rust Oxide engine, CSS-first `@theme` config, sub-millisecond rebuilds. **shadcn/ui** on Radix for accessible components we own the source of. **Biome** instead of ESLint + Prettier: one Rust binary, one config, nobody argues about formatting and CI takes two seconds.

**Audio.** `getUserMedia` → `RTCPeerConnection` straight to OpenAI. The browser talks to OpenAI directly using a short-lived ephemeral token our backend mints; raw audio never touches our server. Lowest latency, smallest PII surface, and our API key never leaves the backend.

*Rejected:* Next.js. The backend is Python, so Next would be a second server that only proxies, with a slower build and one more process holding secrets. *Rejected:* a canvas/WebGL grid — CSS grid with Motion is faster to build and looks better; reach for canvas only past a few hundred simultaneous images, which we will not have.

## Backend

**Python 3.13 + FastAPI + uvicorn, managed by `uv`.**

`uv` resolves and installs in seconds, and `uv.lock` is a real lockfile that Aikido's SCA scanner reads. `pyproject.toml` alone is not scannable, and dependency findings are the only ones that can gate CI on Aikido's free tier — so the lockfile is a security requirement, not a preference.

FastAPI because this service is almost entirely concurrent fan-out — one distiller call, one or two Cala calls, then eight to twenty parallel page fetches and image probes — so the async model *is* the performance story. Native WebSocket support carries the live channel. Pydantic v2 gives validation and an OpenAPI schema that generates `packages/api-client`, so frontend types cannot drift from backend reality.

**PostgreSQL 17** for sessions, transcript turns, candidates, pins and generations. **Redis 7** for the candidate cache, the perceptual-hash dedupe set, rate limiting, the fal webhook → WebSocket pubsub bridge, and the **Cala credit ledger** (see below).

**No task queue.** The discovery fan-out lives in `asyncio.TaskGroup` on the WebSocket connection, and fal's slow work is handled by its own queue plus a webhook. Adding taskiq or Celery would be a third moving part earning nothing in seven hours. If a job ever needs to outlive a connection, revisit.

**httpx** with hard timeouts and `tenacity` retries for every outbound call. **selectolax** for HTML parsing — a C-backed parser, roughly an order of magnitude faster than BeautifulSoup, and we are parsing twenty pages inside a live loop. **Pillow + imagehash** for perceptual dedupe. **structlog** JSON logs. **ruff** and **mypy --strict**.

*Rejected:* Litestar (nice, smaller ecosystem). Django (weight, and the async story). Node backend (the brief says Python, and that is where the AI tooling lives).

## The technologies, and what each one actually does

| | Role | Why it and not something else |
|---|---|---|
| **OpenAI** | Live transcription (`gpt-live-transcribe`, ~$0.017/min) and prompt synthesis | The only realtime STT with true incremental deltas and browser WebRTC. Deltas are what make the screen feel alive; turn-level transcription would make it feel like a form. |
| **Cala** | Entity resolution + cited-source discovery + salience | Nothing else turns a spoken mention into a canonical entity with authoritative sources attached. It is the reason our references carry publishers instead of being anonymous pixels. |
| **Pioneer** (Fastino) | GLiNER2 structured extraction of visual attributes from speech; the cost gate | An encoder model returns typed attributes in milliseconds at $0.15/1M. Asking a frontier model to do this on every pause would be slower and ~100× the cost. This is the right tool, used for the right reason. |
| **fal** | Final generation, conditioned on pinned references | `flux-pro/kontext/max/multi` accepts multiple `image_urls`, which is what makes pinning functional instead of theatrical. |
| **Aikido** | Zen runtime firewall, CI gating, safe-chain, live security panel | We fetch arbitrary URLs discovered from the open web. That is a textbook SSRF surface and Zen is a real answer to it, not a sponsor logo. |
| **Entire** | Every commit bound to the agent session that produced it | Same instinct as the product: keep the reasoning attached to the artefact. |

Six partner technologies. The rules require three.

## Cost model — read this before writing the loop

| | Unit cost | Per 3-minute session |
|---|---|---|
| OpenAI `gpt-live-transcribe` | $0.017/min | ~$0.05 |
| Pioneer GLiNER2 | $0.15/1M tokens | rounding error |
| **Cala** | **1 credit per query** | **~5–15 credits** |
| Wikimedia / Openverse | free | free |
| fal `flux/schnell` | per output | cents |

**Cala is the only scarce resource.** Free tier is **100 credits per month** — roughly three queries a day. The $50 Explore tier is 1,100 credits. Buy it; it is the cheapest risk to retire.

Controls, all mandatory:

- **Distiller gate.** No Cala call unless the distilled attribute set changed materially against the last query. Cheap string/set diff on subject + medium + era.
- **Debounce.** Minimum 8 seconds of new settled speech between queries, regardless of change.
- **Cache.** Every Cala response stored in Postgres keyed by a hash of the query input, with the raw JSON kept for the source panel. Cache hits never bill.
- **Ledger.** A Redis counter of credits spent, exposed in the dev HUD. If it climbs during idle, something is wrong and you find out in seconds instead of on stage.
- **Pre-warm.** The demo runs against a warm cache. State this openly in the demo — it reads as engineering judgment, not a dodge.

## Deploy

Docker Compose locally. For the demo: API on Fly.io or Railway (one container plus Postgres and Redis), web on Vercel or Cloudflare Pages as a static SPA. Neither is load-bearing — pick whichever authenticates fastest at 17:00 and spend no more time on it.

Two constraints the deploy must satisfy: **HTTPS**, because `getUserMedia` requires a secure context, and a **publicly reachable webhook URL** for fal.

## Version pins

Pin exact versions in both lockfiles and commit them. `pnpm install --frozen-lockfile` and `uv sync --frozen` in CI, always. A transitive dependency shifting at 17:45 is the failure mode that ends runs.
